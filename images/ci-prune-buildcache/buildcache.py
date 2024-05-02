from urllib.parse import urlparse
from datetime import datetime
import helper
from io import StringIO


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
