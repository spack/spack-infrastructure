import boto3
import helper
import multiprocessing.pool as pool
import math
import time
from botocore.config import Config
from buildcache import Object, BuildCache

def s3_resource():
    config = Config(
        retries={
            "mode": "adaptive",
            "max_attempts": 10,
        }
    )
    return boto3.resource("s3", config=config)


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
