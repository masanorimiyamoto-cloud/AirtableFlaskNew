# airtable_cache.py
import time
from threading import Lock

_lock = Lock()
_cache = {}

def month_key(person_id: str, year: int, month: int) -> str:
    return f"airtable:month:{person_id}:{year:04d}-{month:02d}"

def cache_get(key: str):
    now = time.time()
    with _lock:
        item = _cache.get(key)
        if not item:
            return None
        value, expire_at = item
        if expire_at < now:
            _cache.pop(key, None)
            return None
        return value

def cache_set(key: str, value, ttl_sec: int):
    expire_at = time.time() + ttl_sec
    with _lock:
        _cache[key] = (value, expire_at)

def cache_delete(key: str):
    with _lock:
        _cache.pop(key, None)
