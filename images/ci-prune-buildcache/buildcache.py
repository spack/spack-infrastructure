import boto3
from botocore.config import Config
from urllib.parse import urlparse
from datetime import datetime
import helper
from io import StringIO
import math
import multiprocessing.pool as pool
import time


def s3_resource():
    config = Config(
        retries={
            "mode": "adaptive",
            "max_attempts": 10,
        }
    )
    return boto3.resource("s3", config=config)


class Object:
    def __init__(self, bucket_name: str, key: str, last_modified):
        self.bucket_name = bucket_name
        self.key = key
        if isinstance(last_modified, datetime):
            self.last_modified = last_modified
        else:
            self.last_modified = datetime.fromisoformat(last_modified)

    def delete(self):
        return False

    def get(self):
        return StringIO()

    def endswith(self, exts):
        return self.key.endswith(exts)


class S3Object(Object):
    def delete(self):
        print(f"Deleting s3://{self.bucket_name}/{self.key}")
        # s3 = s3_resource()
        # obj = s3.Object(self.bucket_name, self.key)
        # response = obj.delete()
        # return response["DeleteMarker"]
        return False

    def get(self):
        s3 = s3_resource()
        bucket = s3.Bucket(self.bucket_name)
        s3obj = bucket.Object(self.key)
        response = s3obj.get()
        return response["Body"]


class BuildCache:
    def __init__(self, url: str):
        self.url = urlparse(url)
        self._listed = []

    def snapshot(self):
        self._listed = []
        for obj in self._list():
            self._listed.append(self.object_type()(
                obj.bucket_name,
                obj.key,
                obj.last_modified,
            ))

        return self._listed

    def load(self, snapshot_data: list):
        self._listed = [self.object_type()(**item) for item in snapshot_data]

    def _list(self):
        return self._listed

    def list(self, key: str = "", ignore=lambda o: False):
        if self._listed:
            list_of_objects = self._listed
        else:
            list_of_objects = self._list()

        if key:
            for obj in list_of_objects:
                if obj.key == key:
                    yield obj
        else:
            for obj in list_of_objects:
                if ignore(obj):
                    continue
                yield obj

    def delete(self, objects: list = [], processes: int = 1, per_page: int = 1000):
        object_t = self.object_type()
        if objects:
            for obj in objects:
                object_t(self.url.netloc, obj, datetime.now()).delete()
        else:
            for obj in self.list():
                obj.delete()

    def object_type(self):
        return Object

    def get_index(self):
        key = f"{self.url.path}index.json".lstrip("/")
        obj = next(self.list(key=key))
        print("Fetching: ", key, obj)
        try:
            response = obj.get()
            index = helper.load_json(response)
        except Exception as e:
            print("Could not fetch index: ", key)
            raise e

        return index, obj


class S3BuildCache(BuildCache):
    def object_type(self):
        return S3Object

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

        s3 = s3_resource()
        bucket = s3.Bucket(self.url.netloc)

        def delete_keys_f(i: int):
            # time.sleep(1)
            return bucket.delete_objects(Delete={
                "Objects": delete_keys[i:nkeys:stride],
                "Quiet": True,
            }
            )

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
        s3 = s3_resource()
        bucket = s3.Bucket(self.url.netloc)
        for obj in bucket.objects.filter(Prefix=self.url.path.lstrip("/")):
            yield S3Object(
                obj.bucket_name,
                obj.key,
                obj.last_modified,
            )
