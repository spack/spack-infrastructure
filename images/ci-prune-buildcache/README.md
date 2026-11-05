# Binary Cache Mirror Pruner

Spack's public build caches grow every day as CI builds new specs for a growing number of stacks. Left alone, they become slow to search for CI pipelines and for users of the public mirrors. This image prunes the `develop` build cache (`s3://spack-binaries/develop`) down to the binaries that recent CI and unexpired snapshots still need, keeps the per-stack and per-snapshot **view indices** consistent with what is left, and cleans up PR build caches.

It runs as the `prune-buildcache-v3` CronJob in the `custom` namespace (`k8s/production/custom/prune-buildcache/cron-jobs.yaml`), at midnight UTC on even-numbered days.

## How a run works

`entrypoint.sh` runs these steps in order. Any failure stops the run before anything later happens (`set -euo pipefail`).

1. **Build the keep list** (`fetch_keeplists.py`). See [Keep list](#keep-list).
2. **Update view indices** (`update_views.py`). Rebuild each active stack's view, and empty views for retired stacks and expired snapshots. See [View indices](#view-indices).
3. **Prune the mirror** (`prune.py`). Delete everything the keep list doesn't protect. See [Pruning](#pruning).
4. **Rebuild the top-level index** with `spack buildcache update-index develop`.
5. **Prune PR mirrors** (`prune_pr_mirrors.py`). Delete PR build caches in `spack-binaries-prs` for pull requests to `spack/spack` and `spack/spack-packages` that are no longer open.

View indices are updated **before** the prune on purpose. Spack's pruning only deletes objects; it never touches an index. A view index that still listed a pruned spec would send clients to a binary that no longer exists. Rewriting the views first means no view lists a spec while it is being deleted.

## Keep list

The keep list (`keeplist.txt`, one spec hash per line) is every hash that must survive the prune. `fetch_keeplists.py` builds it from the `spack.lock` artifacts of successful `generate` jobs in GitLab pipelines on `develop` for `spack/spack-packages`:

* **Rolling window**: every pipeline updated in the last `PRUNE_SINCE_DAYS` days (14 by default).
* **Snapshots**: every `refs/snapshots/develop-YYYY-MM-DD` ref on GitHub dated within the last 2 months. Each snapshot points at the commit of a successful develop pipeline (see `images/snapshot-release-tags`), which may have finished days before the snapshot was taken. So pipelines are looked up by commit SHA, not by date. Snapshots older than 2 months have expired, and their specs are pruned unless something else keeps them.

The snapshot window must stay safely below GitLab's 90-day artifact expiry (`default_artifacts_expire_in` in `terraform/modules/spack_gitlab/application_settings.tf`), or the lockfiles it depends on will no longer exist.

`fetch_keeplists.py` also writes:

* `stacks/<stack>.txt`: the spec hashes of each stack, one per line, from that stack's lockfiles in every rolling-window pipeline. These are the inputs for the stack view indices. Only the hashes are kept, so lockfiles written by different spack versions never need to be merged.
* `snapshot_views.json`: the names of the unexpired snapshot views, used by `update_views.py`.
* `keeplist.txt` is also copied to `s3://spack-logs/pruning/<date>/keeplist.txt` for later debugging.

A keep list was chosen over a purely date-based approach (prune everything older than N days) because the latter almost always removes dependencies of binaries that are still in use. Fixing that means walking up the dependency graph from every pruned spec, which becomes very aggressive and breaks running pipelines and user installs as binaries disappear underneath them.

## View indices

A view index lists only a subset of the mirror's specs and lives at `v3/manifests/index/<view>/index.manifest.json`, next to the top-level index. Clients configured with a view only see that subset. The develop mirror has three kinds:

* **Stack views** (e.g. `e4s/`), which CI also appends to as it pushes binaries.
* **Dated snapshot views** (`snapshots/develop-YYYY-MM-DD/`), each written once by the snapshot job.
* **`snapshots/develop-latest/`**, meant to match the newest snapshot.

`update_views.py` lists the mirror's spec manifests once and reuses that listing for every view; calling `spack buildcache update-index --name` once per stack would list the whole mirror every time. Stacks share many specs (compilers and common dependencies), so it also fetches each spec manifest that any stack view needs only once, and builds every stack view from those. It then handles each existing view:

| View | Action |
| --- | --- |
| Stack in `stacks/` | Rebuilt from the stack's hashes (every one whose spec exists in the mirror), plus entries CI added to it during the run. See below. |
| Unexpired dated snapshot | Left alone. Its specs are in the keep list. |
| Expired dated snapshot | Emptied. |
| `snapshots/develop-latest` | Kept while every spec it lists survives the prune; otherwise emptied. |
| Any other view (e.g. a stack removed from CI) | Emptied once it hasn't been updated for `PRUNE_SINCE_DAYS` days. A recently updated one is left alone and logged. |

CI keeps appending to stack views while the pruner runs, and specs from pipelines that started after the keep list was built aren't in the stack's hashes yet. So a stack view isn't simply overwritten. Just before writing it, `update_views.py` re-reads the view's current index and carries over the entries CI pushed after the run started (`--run-started`), as long as the prune won't delete them: their hash is in the keep list, or their spec manifest is newer than the prune's cutoff (see [Pruning](#pruning)). An entry that wasn't in the initial listing is carried over only if its manifest still exists. Older entries are not carried over, even when the prune keeps them (for example because a snapshot needs them), so a stack view lists the stack's recent specs rather than everything that survives.

Stale views are **emptied, not deleted**. A client then sees "no binaries" and builds from source, instead of finding a binary that is missing. An emptied view is also easy to recreate. A view that is already empty is left alone, so expired views aren't rewritten on every run and keep the modification time of when they were emptied.

`develop-latest` isn't protected by name because its view can lag behind the `develop-latest` ref. For example, it was still identical to `develop-2026-10-19` well after newer snapshots were taken. Rather than work out which snapshot it describes, `update_views.py` checks the property that matters: that none of its specs are about to be pruned.

## Pruning

`prune.py` calls spack's `prune_buildcache` with the keep list, which does two passes:

1. **Direct pruning**: delete every spec manifest whose hash is not in the keep list.
2. **Orphan pruning**: delete blobs (binaries and other files) that no remaining manifest references.

`prune.py` stops the orphan pass, before it deletes anything, if any manifest couldn't be read (`UnreadableManifestsError`). spack skips such a manifest with a warning, which makes the blobs it references look like orphans, so an S3 error or expired credentials would otherwise delete binaries of specs that still exist.

Both passes only consider objects older than the top-level `index.manifest.json`'s modification time. Anything pushed after the index was last rebuilt is never pruned in that run. This protects specs pushed while the run is in progress, but it also means a stale top-level index holds the cutoff back.

## Fail-safes

The main risk is over-pruning: deleting binaries that a pipeline, a snapshot, or a user still needs. So the run stops, without deleting anything, when it can't be sure what to keep:

* A `spack.lock` artifact can't be downloaded from GitLab (for example it was deleted or has expired).
* An unexpired snapshot has no matching develop pipeline, or none of its pipelines produced any specs (`SnapshotError`).
* No stacks were found in the rolling window, meaning there were no successful generate jobs. Pruning with that keep list would delete nearly every non-snapshot binary.
* An index in the mirror is in a format newer than the pinned spack writes (`IndexFormatError`). See [Index formats](#index-formats).

All of these checks happen before any view index is written. A run they stop leaves the mirror and its view indices unchanged; the only cost is that the cache keeps growing until the cause is fixed. The Python errors are reported to Sentry (`python-scripts-sentry-config`). The empty-stacks check is a shell check in `entrypoint.sh`, so it shows up only as a failed Job.

The orphan pass has its own check, described under [Pruning](#pruning): it runs after the views are written and after direct pruning, but stops before any orphan is deleted.

The safety of snapshot pruning also depends on GitLab not deleting old pipelines automatically. Automatic pipeline cleanup is disabled for `spack/spack-packages`. If it were enabled, deleted snapshot pipelines would make the run stop (see above) rather than prune silently, but only for snapshots still inside the window.

## Index formats

An index manifest can list one index per spack database format, for example `application/vnd.spack.db.v9+json` and `...v8+json`. A client reads the newest format it knows, falling back to older ones. When spack writes an index, it replaces only the format it writes and keeps the others ([spack/spack#53094](https://github.com/spack/spack/pull/53094)).

That makes the order of spack versions matter:

* **The pruner's spack must be at least as new as CI's.** If CI starts writing a newer format, CI keeps that index current and newer clients read it. The pruner would only replace the older format, so after the prune, the newer index would still list every pruned spec. `update_views.py` therefore stops before writing anything if any index in the mirror has a format the pinned spack doesn't know. The fix is to update the spack commit in this image's `Dockerfile`.
* **Older formats are left as they are.** In November 2026, 19 of the 51 index manifests on the develop mirror also carried a v8 index, which current spack never updates. Clients that can only read v8 see that frozen index, so after pruning they can try to download binaries that are gone, fail, and build from source. Removing the v8 index instead would leave those clients unable to read the view at all (spack raises an error when no format matches), which is worse.

## Configuration

Set on the CronJob:

| Variable | Default | Meaning |
| --- | --- | --- |
| `GITLAB_URL` | `https://gitlab.spack.io` | GitLab instance to read pipelines from. |
| `GITLAB_PROJECT` | `spack/spack-packages` | GitLab project, and also the GitHub repository whose snapshot refs are read. |
| `BUILDCACHE_URL` | `s3://spack-binaries/develop/` | Mirror to prune. |
| `PRUNE_REF` | `develop` | Branch whose pipelines feed the keep list. |
| `PRUNE_SINCE_DAYS` | `14` | Rolling pipeline window, and how long a view with no stack must be idle before it is emptied. |
| `PRUNE_DRY_RUN` | `false` | See [Dry runs](#dry-runs). |
| `PR_BUILDCACHE_BUCKET` | (required) | Bucket holding PR build caches. |
| `GITHUB_TOKEN` | (unset) | Token for reading snapshot refs and PR state. Without it GitHub is read anonymously, which has a much lower rate limit. |
| `SPACK_ROOT` | `/app/spack` | Spack checkout to use; the image pins a specific spack commit in its `Dockerfile`. |

## Dry runs

With `PRUNE_DRY_RUN=true`, every step still runs and reads from GitLab, GitHub and S3, but nothing in the mirrors is changed:

* `update_views.py` reports how many specs each stack view would hold and which views it would empty.
* `prune.py` and `prune_pr_mirrors.py` report what they would delete.
* The top-level index update is printed, not run.

The keep list is still uploaded to `s3://spack-logs/pruning/`.

## Known limitations

* **CI and the pruner can still race on a stack view.** Neither side writes the view index conditionally, so:
  * an entry CI appends between the pruner's re-read of a view and its write (a few seconds) is lost until CI appends it again;
  * if CI reads a view just before the pruner rewrites it and writes just after, it puts back entries the pruner removed. Those entries point at pruned binaries until the next run.
* **The carry-over relies on the prune's cutoff.** If the top-level index is rebuilt between the view step and the prune (for example by protected-publish), the prune deletes slightly more than `update_views.py` expected. A carried-over entry can then point at a pruned spec until the next run.
* **Spack can't list view indices itself.** Its include pattern for index manifests (`.*index.manifest.json`) is matched as a glob, so it only matches file names starting with a dot. `update_views.py` lists them directly instead.
