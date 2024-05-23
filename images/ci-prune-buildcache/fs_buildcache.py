import helper
import math
import multiprocessing.pool as pool
import os

from datetime import datetime
from buildcache import Object, BuildCache



class FileSystemObject(Object):
    def __init__(self, entry: os.DirEntry):
        lm = datetime.fromtimestamp(entry.stat().st_mtime)
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

    def load(self, snapshot_data: list):
        raise Exception("Not implemented")

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
        prefix = self.url.path
        delete_keys = [k for k in keys if prefix in k]

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
            """
            Delete keys/files and parent directory if it is empty
            after the key has been removed
            """
            deleted = []
            errors = []
            failures = []
            for key in delete_keys[i:nkeys:stride]:
                parent_directory = os.path.dirname(key)
                try:
                    os.remove(key)
                    if  not os.listdir(parent_directory):
                        os.rmdir(parent_directory)
                    deleted.append(key)
                except PermissionError:
                    failures.append((key, "permissions"))
                except FileNotFoundError:
                    errors.append((key, "file not found"))
            return { "Deleted": deleted, "Errors": errors, "Failures": failures}

        failures  = []
        errors = []
        if processes > 1:
            with pool.ThreadPool(processes) as tp:
                for response in tp.imap_unordered(helper.star(delete_keys_f), [(i,) for i in range(stride)]):
                    errors.extend(response.get("Errors", []))
                    failures.extend(response.get("Failures", []))
        else:
            for i in range(stride):
                response = delete_keys_f(i)
                errors.extend(response.get("Errors", []))
                failures.extend(response.get("Failures", []))

        return errors, failures

    def _list(self):
        def traverse_directory(directory):
            for entry in os.scandir(directory):
                if entry.is_file():
                    yield entry
                elif entry.is_dir():
                    yield from traverse_directory(entry.path)

        for file_obj in traverse_directory(self.url.path):
            yield FileSystemObject(file_obj)



    def get_index(self):
        key = f"{self.url.path}index.json"
        obj = next(self.list(key=key))
        print("Fetching: ", key)
        try:
            response = obj.get()
            index = helper.load_json(response)
        except Exception as e:
            print("Could not fetch index: ", key)
            raise e

        return index, obj
