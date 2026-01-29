# airtable_cache.py
import time
from threading import Lock

_lock = Lock()
_cache = {}

MONTH_CACHE_TTL_SEC = 90  # 例：30秒（10でも60でもOK）

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

# --- ここから追加：キャッシュの行操作（Airtable追加コールなし） ---

def month_cache_remove_record(person_id: str, year: int, month: int, record_id: str,
                              ttl_sec: int = MONTH_CACHE_TTL_SEC) -> bool:
    ...

    """当月キャッシュが存在する場合、その中の record_id を1件削除して保存し直す。"""
    key = month_key(person_id, year, month)
    rows = cache_get(key)
    if rows is None:
        return False
    new_rows = [r for r in rows if str(r.get("id")) != str(record_id)]
    if len(new_rows) == len(rows):
        # 見つからなかった（キャッシュ不整合 or 未キャッシュ）
        return False
    new_rows.sort(key=lambda x: x.get("WorkDay", "9999-12-31"))
    cache_set(key, new_rows, ttl_sec)
    return True

def month_cache_update_record(person_id: str, year: int, month: int, record_id: str, fields: dict,
                              ttl_sec: int = MONTH_CACHE_TTL_SEC) -> bool:
    ...

    """
    当月キャッシュが存在する場合、その中の record_id を更新して保存し直す。
    fields例: {"WorkDay": "...", "WorkOutput": 123}
    """
    key = month_key(person_id, year, month)
    rows = cache_get(key)
    if rows is None:
        return False

    updated = False
    new_rows = []
    for r in rows:
        if str(r.get("id")) == str(record_id):
            rr = dict(r)
            rr.update(fields)
            new_rows.append(rr)
            updated = True
        else:
            new_rows.append(r)

    if not updated:
        return False

    new_rows.sort(key=lambda x: x.get("WorkDay", "9999-12-31"))
    cache_set(key, new_rows, ttl_sec)
    return True

def month_cache_move_record(person_id: str, from_year: int, from_month: int, to_year: int, to_month: int, record_id: str, fields: dict,
                            ttl_sec: int = MONTH_CACHE_TTL_SEC) -> bool:
    """
    月跨ぎ編集用：
      - from月キャッシュがあれば record_id を取り出して削除
      - to月キャッシュがあれば（または fromから取れた場合）追加して保存
    ※ どちらもキャッシュが存在しない場合は何もしない（False）
    """
    from_key = month_key(person_id, from_year, from_month)
    to_key   = month_key(person_id, to_year, to_month)

    from_rows = cache_get(from_key)
    to_rows   = cache_get(to_key)

    if from_rows is None and to_rows is None:
        return False

    moved_row = None

    # 1) from側から取り出す
    if from_rows is not None:
        kept = []
        for r in from_rows:
            if str(r.get("id")) == str(record_id):
                moved_row = dict(r)
            else:
                kept.append(r)
        # fromに存在していたら保存し直し
        if moved_row is not None:
            kept.sort(key=lambda x: x.get("WorkDay", "9999-12-31"))
            cache_set(from_key, kept, ttl_sec)

    # 2) to側へ入れる（toキャッシュがある場合のみ）
    if to_rows is not None:
        if moved_row is None:
            # fromに無い場合は最小情報で追加（必要な列は records表示に足りるもの）
            moved_row = {"id": record_id}
        moved_row.update(fields)
        # 既に同IDが居たら置換
        new_to = []
        replaced = False
        for r in to_rows:
            if str(r.get("id")) == str(record_id):
                new_to.append(dict(moved_row))
                replaced = True
            else:
                new_to.append(r)
        if not replaced:
            new_to.append(dict(moved_row))
        new_to.sort(key=lambda x: x.get("WorkDay", "9999-12-31"))
        cache_set(to_key, new_to, ttl_sec)
        return True

    # toキャッシュが無い場合は fromだけ整えた（or 何もできなかった）
    return moved_row is not None
