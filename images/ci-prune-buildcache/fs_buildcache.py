import helper
import math
import multiprocessing.pool as pool
import os

from datetime import datetime
from buildcache import Object, BuildCache



class FileSystemObject(Object):
    def __init__(self, entry: os.DirEntry):
        lm = datetime.fromtimestamp(entry.stat_info.st_mtime)
        super().__init__(bucket_name=None, key=entry.path, last_modified = lm)
        if entry.is_file():
           self._get_method = self._get_file
        elif entry.is_dir():
            self._get_method = self._get_dir

    def _get_file(self):
        return open(self.key, "r")

    def _get_dir(self):
        # not sure if os.scandir would be better
        return os.listdir(self.key)

    def get(self):
            return self._get_method()

    def delete(self):
        print(f"Deleting {self.key}")
        return False


class FileSystemBuildCache(BuildCache):
    def object_type(self):
        return FileSystemObject

    def delete(self, keys : list = [], processes: int = 1, per_page: int = 1000):
        """Delete the listed keys from the buildcache, by default this will
        delete all of the keys that exist in the buildcache.

        Arguments:
            keys      (list(str), optional): list of keys to delete (default: all keys)
            processes (int,       optional): number of processes to use when calling delete
                                             (default: 1, max: <system dependent>)
            per_page  (int,       optional): The max number of items to delete at a time (default: 1000, max: 1000)
        """

        if not keys:
            keys = [obj.key for obj in self.list()]

        # Get the keys to delete that exists in this buildcache
        prefix = self.url.path.lstrip("/")
        delete_keys = [{"Key": k} for k in keys if prefix in k]

        # Nothing to delete
        if not delete_keys:
            return [], []

        max_del = 1000
        per_page = min(max_del, per_page)
        nkeys = len(delete_keys)
        stride = math.ceil(nkeys / per_page)

        # Auto detecte number of threads for per_page
        if processes < 1:
            processes = stride

        # Only spawn as many processes as needed
        processes = min(stride, processes)

        def delete_keys_f(i: int):
            # TODO need to implement
            return { "Deleted": [key for key in delete_keys[i:nkeys:stride]]}

        failures  = []
        errors = []
        if processes > 1:
            with pool.ThreadPool(processes) as tp:
                for response in tp.imap_unordered(helper.star(delete_keys_f), [(i,) for i in range(stride)]):
                    failures.extend([obj for obj in response.get("Deleted", []) if not obj["DeleteMarker"]])
                    errors.extend(response.get("Errors", []))
        else:
            for i in range(stride):
                response = delete_keys_f(i)
                failures.extend([obj for obj in response.get("Deleted", []) if not obj["DeleteMarker"]])
                errors.extend(response.get("Errors", []))

        return errors, failures

    def _list(self):
        for dir_obj in os.scandir(self.url.path.lstrip("/")):
            yield FileSystemObject(dir_obj)
