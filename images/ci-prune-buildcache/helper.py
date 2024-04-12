from datetime import datetime
import json
import re


hash_re = re.compile(r"-([a-zA-Z0-9]{32})\.")


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, datetime):
            return str(obj.isoformat())
        return json.JSONEncoder.default(self, obj)


def write_json(fd, data):
    fd.write(json.dumps(data, cls=JSONEncoder))


def load_json(source):
    if type(source) in (bytearray, bytes, str):
        return json.loads(source)
    else:
        return json.load(source)


def star(func):
    def _wrapper(args):
        return func(*args)

    return _wrapper


def extract_hash(key: str):
    """ Extract the hash from the object key
    """
    h = hash_re.findall(key)
    if len(h) == 1:
        h = h[0]
    else:
        h = None
    return h

