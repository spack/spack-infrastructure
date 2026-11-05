#!/usr/bin/env spack-python
"""
Regenerate the buildcache view index for each stack, listing the mirror only once.

`spack buildcache update-index --name <view> <mirror> <env>` lists every spec
manifest in the mirror on each call. Running it once per stack meant one full
listing of the mirror per stack, so this script lists once and reuses the result
for every view.

CI appends to stack views while this runs, so each stack view is written as its
stack's specs plus the entries of the view's current index that CI pushed after
this run started and that the prune won't delete (see carry_over_view_entries),
read just before the write.

Before writing anything, it stops if any index in the mirror is in a format newer
than this spack writes (see check_index_formats).

This script is meant to be run using:
    `spack python update_views.py --mirror <mirror> --keeplist <file> --run-started <time> <stack_file> [...]`
"""

import argparse
import contextlib
import json
import pathlib
import tempfile
import time
from typing import Callable, Dict, Iterator, List, Set

import sentry_sdk

import spack.binary_distribution as bindist
import spack.config
import spack.spec
import spack.stage
import spack.util.url as url_util
import spack.util.web as web_util
from spack.enums import InstallRecordStatus
from spack.mirrors.utils import require_mirror_name
from spack.util import tty

class IndexFormatError(Exception):
    """An index in the mirror is in a format this spack can't write."""


sentry_sdk.init(
    # This cron job only runs every other day,
    # so just record all transactions.
    traces_sample_rate=1.0,
)


def manifest_hash(manifest: str) -> str:
    # Same parsing as spack.binary_distribution._read_specs_and_push_index
    return manifest.split("/")[-1].split("-")[-1].split(".")[0]


def buildcache_class():
    return bindist.get_url_buildcache_class(
        layout_version=bindist.CURRENT_BUILD_CACHE_LAYOUT_VERSION
    )


def prune_cutoff(url: str) -> float:
    """The time before which prune.py may delete specs that are not in the keep list.

    Mirrors spack.buildcache_prune.prune_buildcache: the top-level index's mtime,
    or now if the mirror has no top-level index.
    """
    stat = web_util.stat_url(buildcache_class().get_index_url(url))
    return stat[1] if stat is not None else time.time()


def add_specs_from_mirror(db, manifests, read_fn, hashes: Set[str]) -> None:
    """Add the specs in hashes that have a manifest in the mirror to db.

    Same as the read loop in spack.binary_distribution._read_specs_and_push_index,
    which can't be used directly because it also pushes the index.
    """
    for manifest in manifests:
        if manifest_hash(manifest) not in hashes:
            continue

        cache_entry = None
        try:
            cache_entry = read_fn(manifest)
            spec = spack.spec.Spec.from_dict(cache_entry.fetch_metadata())
        except Exception as e:
            tty.warn(f"Unable to fetch spec for manifest {manifest} due to: {e}")
            continue
        finally:
            if cache_entry:
                cache_entry.destroy()
        db.add(spec)
        db.mark(spec, "in_buildcache", True)


def add_specs_from_db(db, source, hashes: Set[str]) -> None:
    """Add the specs in hashes that source lists as in the build cache to db."""
    for spec_hash in hashes:
        record = source.query_local_by_spec_hash(spec_hash)
        if record and record.in_buildcache:
            db.add(record.spec)
            db.mark(record.spec, "in_buildcache", True)


def read_view_index(db, url: str, view: str) -> bool:
    """Load the current index of a view into db; False if the view has no index.

    Same as `spack buildcache update-index --append`. An empty cache entry makes
    spack fetch the index from the mirror instead of trusting its local cache.
    """
    metadata = bindist.MirrorMetadata(url, bindist.CURRENT_BUILD_CACHE_LAYOUT_VERSION, view)
    try:
        bindist.BINARY_INDEX._fetch_and_cache_index(metadata, cache_entry={})
    except bindist.BuildcacheIndexNotExists:
        return False
    cache_key = bindist.BINARY_INDEX._local_index_cache[str(metadata)]["index_path"]
    with bindist.BINARY_INDEX._index_file_cache.read_transaction(cache_key) as f:
        db._read_from_stream(f)
    return True


def listed_specs(db) -> Iterator[spack.spec.Spec]:
    """The specs a view index says are in the build cache.

    Skips dependencies the index knows about but doesn't provide.
    """
    for spec in db.query_local(installed=InstallRecordStatus.ANY):
        record = db.query_local_by_spec_hash(spec.dag_hash())
        if record and record.in_buildcache:
            yield spec


def carry_over_view_entries(
    db, url: str, view: str, carry_over: Callable[[spack.spec.Spec], bool]
) -> int:
    """Add to db the entries of the view's current index that carry_over selects.

    This keeps specs that CI appended to the view while this job ran, which the
    stack's lockfiles don't include yet. Returns the number of entries carried over.
    """
    carried = 0
    with temporary_database() as current:
        if not read_view_index(current, url, view):
            return 0
        for spec in listed_specs(current):
            existing = db.query_local_by_spec_hash(spec.dag_hash())
            if existing and existing.in_buildcache:
                continue
            if not carry_over(spec):
                continue
            db.add(spec)
            db.mark(spec, "in_buildcache", True)
            carried += 1
    return carried


def list_view_indices(url: str) -> Dict[str, float]:
    """Map each view in the mirror to the mtime of its index manifest.

    The top-level index is reported as view "". spack's own listing
    (get_entries_from_cache with BuildcacheComponent.INDEX) can't be used here: its
    include pattern ".*index.manifest.json" is matched as a glob, so it only
    matches file names that start with a dot.
    """
    cache_class = buildcache_class()
    prefix = url_util.join(
        url, *cache_class.get_relative_path_components(bindist.BuildcacheComponent.INDEX)
    )
    views = {}
    for entry in web_util.list_url(prefix, recursive=True):
        if entry.split("/")[-1] != "index.manifest.json":
            continue
        stat = web_util.stat_url(url_util.join(prefix, entry))
        if stat is not None:
            views[entry.removesuffix("index.manifest.json").rstrip("/")] = stat[1]
    return views


def index_records(url: str, view: str) -> List[dict]:
    """The blob records of a view's index manifest, one per index format."""
    manifest = json.loads(web_util.read_text(buildcache_class().get_index_url(url, view)))
    return manifest["data"]


def check_index_formats(url: str, views: Dict[str, float]) -> None:
    """Stop if any index in the mirror is in a format this spack doesn't know.

    Writing an index only replaces the index in the format this spack writes; an
    index in another format is kept (spack/spack#53094), and newer clients read
    the newest format they know. If CI runs a spack that writes a newer format than
    this one, that newer index would keep listing every spec this run prunes, for
    every client that reads it. So the pruner's spack must be at least as new as
    CI's.
    """
    known = buildcache_class().component_to_media_types(bindist.BuildcacheComponent.INDEX)
    unknown = {}
    for view in sorted(views):
        types = sorted({record["mediaType"] for record in index_records(url, view)} - set(known))
        if types:
            unknown[view or "(top-level)"] = types
    if unknown:
        details = "; ".join(f"{view}: {', '.join(types)}" for view, types in unknown.items())
        raise IndexFormatError(
            f"Index formats unknown to this spack (which writes {known[0]}) found in {url}: "
            f"{details}. Update the spack commit in images/ci-prune-buildcache/Dockerfile "
            "to one that writes the newest format; aborting before writing any index."
        )


@contextlib.contextmanager
def temporary_database():
    with tempfile.TemporaryDirectory(
        dir=spack.stage.stage_root(spack.config.CONFIG)
    ) as tmpdir:
        db = bindist.BuildCacheDatabase(tmpdir)
        db._write()
        yield db


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mirror",
        required=True,
        help="name of a configured mirror",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what each view index would contain without pushing anything",
    )
    parser.add_argument(
        "--keeplist",
        required=True,
        help="keep list passed to prune.py (written by fetch_keeplists.py)",
    )
    parser.add_argument(
        "--run-started",
        type=float,
        required=True,
        help="when this run started, in seconds since the epoch; only view entries "
        "pushed after it are carried over",
    )
    parser.add_argument(
        "stack_files",
        nargs="+",
        help="files listing a stack's spec hashes, one per line (written by "
        "fetch_keeplists.py); each file name without .txt is the view name",
    )
    args = parser.parse_args()

    mirror = require_mirror_name(args.mirror)
    url = mirror.push_url

    tty.info(f"Listing spec manifests in {url}...")
    manifest_to_mtime, read_fn = bindist.get_entries_from_cache(
        url, component_type=bindist.BuildcacheComponent.SPEC
    )
    manifests = list(manifest_to_mtime.keys())
    tty.info(f"Found {len(manifests)} spec manifests")

    # What prune.py will keep: specs in the keep list, plus specs whose manifest is
    # newer than its cutoff
    keep = set(pathlib.Path(args.keeplist).read_text().split())
    pruned_before = prune_cutoff(url)
    hash_to_mtime = {manifest_hash(m): mtime for m, mtime in manifest_to_mtime.items()}

    def manifest_exists(spec: spack.spec.Spec) -> bool:
        manifest_url = buildcache_class().get_manifest_url(spec, url)
        return web_util.stat_url(manifest_url) is not None

    def survives_prune(spec: spack.spec.Spec) -> bool:
        spec_hash = spec.dag_hash()
        if spec_hash in keep:
            return True
        if spec_hash in hash_to_mtime:
            # spack prunes objects modified at or before its cutoff
            return hash_to_mtime[spec_hash] > pruned_before
        # Not in the listing: pushed since then, or already gone from the mirror
        return manifest_exists(spec)

    def pushed_during_run_and_kept(spec: spack.spec.Spec) -> bool:
        """Whether CI pushed spec after this run started, and the prune won't delete it.

        Older entries are deliberately not carried over, even if the prune keeps them
        (e.g. because a snapshot needs them): a stack view lists the stack's recent
        specs, not everything that happens to survive.
        """
        spec_hash = spec.dag_hash()
        if spec_hash in hash_to_mtime:
            return hash_to_mtime[spec_hash] > args.run_started and survives_prune(spec)
        # Not in the listing: pushed since then, or already gone from the mirror. Check
        # the manifest even if the hash is in the keep list: lockfiles list specs that
        # were never pushed, or have already been deleted. A manifest pushed since the
        # listing is newer than the prune's cutoff, so it survives the prune.
        return manifest_exists(spec)

    tty.info(f"Listing view indices in {url}...")
    views = list_view_indices(url)
    check_index_formats(url, views)

    view_hashes: Dict[str, Set[str]] = {}
    for stack_file in map(pathlib.Path, args.stack_files):
        view = stack_file.name.removesuffix(".txt")
        view_hashes[view] = set(stack_file.read_text().split())
        if not view_hashes[view]:
            tty.warn(f"No specs found for view {view}, creating an empty index")

    if args.dry_run:
        for view, hashes in view_hashes.items():
            count = sum(1 for m in manifests if manifest_hash(m) in hashes)
            with temporary_database() as db:
                carried = carry_over_view_entries(
                    db,
                    url,
                    view,
                    lambda spec: spec.dag_hash() not in hashes and pushed_during_run_and_kept(spec),
                )
            tty.info(
                f"Would update view index {view} with {count} of {len(hashes)} specs, "
                f"plus {carried} entries carried over from its current index"
            )
    else:
        # Stacks share many specs (compilers, common dependencies), so fetch each
        # needed spec manifest once and build every view from that
        needed = set().union(*view_hashes.values())
        tty.info(f"Fetching {len(needed)} specs for {len(view_hashes)} view indices...")
        with temporary_database() as fetched:
            add_specs_from_mirror(fetched, manifests, read_fn, needed)
            for view, hashes in view_hashes.items():
                tty.info(f"Updating view index {view}...")
                with temporary_database() as db:
                    add_specs_from_db(db, fetched, hashes)
                    # Read the current index as late as possible, right before the write
                    carried = carry_over_view_entries(db, url, view, pushed_during_run_and_kept)
                    bindist._push_index(db, str(db.database_directory), url, view)
                tty.info(f"Updating view index {view}... done! ({carried} entries carried over)")
