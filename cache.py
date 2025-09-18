import time
from threading import Lock
from functools import wraps

_CACHE = {}
_LOCK = Lock()

def ttl_cache(ttl_seconds=60):
    """Simple thread-safe TTL cache decorator.

    Usage:
        @ttl_cache(30)
        def expensive(a, b):
            ...
    """
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            key = (fn.__name__, args, tuple(sorted(kwargs.items())))
            now = time.time()
            with _LOCK:
                rec = _CACHE.get(key)
                if rec and rec[0] > now:
                    return rec[1]
            # compute outside lock to avoid blocking long calls
            result = fn(*args, **kwargs)
            with _LOCK:
                _CACHE[key] = (now + ttl_seconds, result)
            return result
        return wrapped
    return deco
