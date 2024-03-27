from buildcache import BuildCache, Object
from datetime import datetime, timedelta, timezone
import helper
import multiprocessing.pool as pool


class PrunedObject(Object):
    def __init__(self, obj: Object, method: str):
        self.__dict__.update(obj.__dict__)
        self.method = method


class BasePruner:
    spec_ext = (".spec.json", ".spec.yaml", ".spec.json.sig")
    tarball_ext = (".spack", ".tar.gz")

    def __init__(self, buildcache: BuildCache, keep_hash_list, cli_args):
        self.buildcache = buildcache
        self.keep_hashes = keep_hash_list
        self.cli_args = cli_args

        self.prunable_hashes = set()
        self.prune_ext = self.spec_ext + self.tarball_ext

        self.start_date = datetime.fromisoformat(cli_args.start_date)

        self.enable_delete = self.cli_args.delete

        self.pruned = []

    def _is_prunable(self, obj: Object):
        """ Check if object is prunable
        """
        h = helper.extract_hash(obj.key)
        if self.prunable_hashes:
            # print(f"{h} found in prunable list")
            return h in self.prunable_hashes

        if self.keep_hashes:
            # print(f"{h} not found in keep list")
            return h not in self.keep_hashes

        return False

    def determine_prunable_hashes(self):
        """ Determine the hashes to prune
        """
        hashes = []
        for obj in self._list(ext=self.prune_ext, wrapped=False):
            h = helper.extract_hash(obj.key)
            if h not in self.keep_hashes:
                hashes.append(h)

        self.prunable_hashes.update(hashes)
        return self.prunable_hashes

    def _prune_buildcache(self, obj: Object):
        """ Apply pruning to buildcache object
        """
        prunit = self._is_prunable(obj)
        return obj, prunit

    def _list(self, ext=None, wrapped=True):
        """ List objects that are valid for pruning

        Args:
            ext : extension(s) to filter by
        """
        for obj in self.buildcache.list(ignore=lambda o: ext and not o.endswith(ext)):
            if wrapped:
                yield (obj,)
            else:
                yield obj

    def prune(self, prunable_hashes=None):
        """ Prune the buildcache
        """
        # Get the list of prunable hashes
        if not prunable_hashes:
            self.prunable_hashes = self.determine_prunable_hashes()
        else:
            self.prunable_hashes = prunable_hashes

        # There is nothing to prune, so prune nothing
        if not self.prunable_hashes:
            return self.pruned

        # Apply pruning
        with pool.ThreadPool(self.cli_args.nprocs) as tp:
            for obj, pruned in tp.imap_unordered(helper.star(self._prune_buildcache), self._list(self.prune_ext)):
                if pruned:
                    self.pruned.append(PrunedObject(obj, str(self)))
                elif pruned is None:
                    print(f"Failed to prune file {obj.key}")

        # Validate that all of the spec files have matching tarballs
        spec_hashes = []
        binary_hashes = []
        error_list = []
        for obj in self.pruned:
            if obj.endswith(self.tarball_ext):
                binary_hashes.append(helper.extract_hash(obj.key))
            elif obj.endswith(self.spec_ext):
                spec_hashes.append(helper.extract_hash(obj.key))
            else:
                error_list.append(obj)

        # This should only be pruning spec files and binaries
        # Everything else is an error
        if error_list:
            print("Error objs")
            print(error_list)
            raise Exception

        # Make sure all of the spec files have a matching binary
        if any([h not in binary_hashes for h in spec_hashes]):
            print("Warning - Unmatched specs in binary list")

        # Return list of pruned files
        return self.pruned


class DirectPruner(BasePruner):
    """Pruning strategy looking directly at the binaries/specs in the buildcache
    """
    # now = datetime.now(timezone.utc)
    # yesterday = now - timedelta(days=14)

    def __str__(self):
        return "direct-pruner"

    def _is_prunable(self, obj: Object):
        # check binary date for Direct Pruning to avoid
        # deleteing something just uploaded but not in the
        # keep_hashes list
        if obj.key.endswith(self.tarball_ext):
            if obj.last_modified.timestamp() > self.start_date.timestamp():
                # print(f"{obj.key} is too new")
                return False

        return BasePruner._is_prunable(self, obj)

    def determine_prunable_hashes(self):
        if not self.prunable_hashes:
            # Direct pruning requires filtering tarballs first due to one day buffer
            hashes: list = []
            self.enable_delete = False
            with pool.ThreadPool(self.cli_args.nprocs) as tp:
                for obj, pruned in tp.imap_unordered(helper.star(self._prune_buildcache), self._list(self.tarball_ext)):
                    if pruned:
                        self.pruned.append(PrunedObject(obj, str(self)))
                        hashes.append(helper.extract_hash(obj.key))
                    elif pruned is None:
                        print(f"Failed to prune file {obj.key}")

            self.prunable_hashes.update(hashes)

            # Now go and only prune the spec files associated with the pruned spackballs
            self.prune_ext = self.spec_ext

        self.enable_delete = self.cli_args.delete
        return self.prunable_hashes


class IndexPruner(BasePruner):
    """Pruning strategy based on the index.json in the buildcache
    """
    def __str__(self):
        return "index-pruner"

    def _is_prunable(self, obj: Object):
        """ Check if object is prunable via self.prunable_hashes only
        """
        h = helper.extract_hash(obj.key)
        return h in self.prunable_hashes

    def determine_prunable_hashes(self):
        """Determine hashes to prune bashed on the hashes in the index.json for buildcache
        """
        index, _ = self.buildcache.get_index()
        database = index.get("database", {})
        installs = database.get("installs", {})

        hashes = [key for key, item in installs.items() if item["in_buildcache"]]
        self.prunable_hashes.update([h for h in hashes if h not in self.keep_hashes])

        return self.prunable_hashes


class OrphanPruner(BasePruner):
    """Pruning Strategy that looks for .spack binaries with no matching spec.json
       buildcache
    """
    def __init__(self, buildcache: BuildCache, date_cutoff: datetime, cli_args):
        BasePruner.__init__(self, buildcache, None, cli_args)
        self.date_cutoff = datetime.fromisoformat(cli_args.start_date)

    def __str__(self):
        return "orphan-pruner"

    def determine_prunable_hashes(self):
        """ Determine the hashes to prune
        """
        print("Getting index")
        index, index_obj = self.buildcache.get_index()
        database = index.get("database", {})
        installs = database.get("installs", {})

        index_hashes = set()
        index_hashes.update([key for key, item in installs.items() if item["in_buildcache"]])

        # Get list of spec_hashes that have been indexed
        # Specs not in index may be transient and be false positives for pruning
        spec_hashes = []
        for obj in self._list(self.spec_ext, wrapped=False):
            h = helper.extract_hash(obj.key)
            if h in index_hashes:
                spec_hashes.append(h)

        unique_specs = set()
        unique_specs.update(spec_hashes)

        binary_hashes = []
        all_binary_hashes = []

        if index_obj.last_modified.timestamp() < self.date_cutoff.timestamp():
            print(f"-- Warning: Adjusting Orphan Pruning cutoff date to {index_obj.last_modified.isoformat()}")
            self.date_cutoff = index_obj.last_modified

        # If Tarball is missing a matching spec file, prune it
        for obj in self._list(self.tarball_ext, wrapped=False):
            h = helper.extract_hash(obj.key)
            all_binary_hashes.append(h)

            if obj.last_modified.timestamp() <= self.date_cutoff.timestamp():
                binary_hashes.append(h)

        unique_binaries = set()
        unique_binaries.update(all_binary_hashes)

        def a_not_in_b(a, b):
            return [ia for ia in a if ia not in b]

        self.unmatched_binaries = a_not_in_b(binary_hashes, unique_specs)
        self.unmatched_specs = a_not_in_b(unique_specs, unique_binaries)

        self.prunable_hashes.update(self.unmatched_binaries)
        self.prunable_hashes.update(self.unmatched_specs)

        # Print a reverse lookup sanity check
        # if self.unmatched_specs:
        #     print("Warning -- Unmatched spec files detected")
        #     print("\n".join(self.unmatched_specs))

        # if self.unmatched_binaries:
        #     print("Warning -- Unmatched spec files detected")
        #     print("\n".join(self.unmatched_binaries))

        return self.prunable_hashes
