# affinity_manager.py
# MODIFIED: 친밀도 캐시 / 즉시 반영 / 주기적 DB 저장 구조로 전면 재구성
import threading
from typing import Dict, Optional

from cache_store import TTLCache
from config import AFFINITY_CACHE_TTL_SECONDS
from db_client import get_supabase

_affinity_cache = TTLCache[dict](AFFINITY_CACHE_TTL_SECONDS)
_affinity_lock = threading.RLock()
_dirty_users: set[str] = set()


def _cache_key(user_id) -> str:
    return str(user_id)


def clear_cache():
    with _affinity_lock:
        _affinity_cache.clear()
        _dirty_users.clear()


def _load_from_db(user_id, user_name) -> dict:
    supabase = get_supabase()
    if not supabase:
        return {"user_id": str(user_id), "user_name": user_name, "affinity": 0, "chat_count": 0}

    try:
        res = (
            supabase.table("user_stats")
            .select("user_id, user_name, affinity, chat_count")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            return {
                "user_id": str(user_id),
                "user_name": row.get("user_name", user_name),
                "affinity": int(row.get("affinity", 0)),
                "chat_count": int(row.get("chat_count", 0)),
            }

        row = {"user_id": str(user_id), "user_name": user_name, "affinity": 0, "chat_count": 0}
        supabase.table("user_stats").upsert(row).execute()
        return row
    except Exception as e:
        print(f"❌ 친밀도 조회 에러: {e}")
        return {"user_id": str(user_id), "user_name": user_name, "affinity": 0, "chat_count": 0}


def load_all_from_db_to_cache() -> int:
    supabase = get_supabase()
    if not supabase:
        return 0
    try:
        res = supabase.table("user_stats").select("user_id, user_name, affinity, chat_count").execute()
        rows = res.data or []
        with _affinity_lock:
            _affinity_cache.clear()
            _dirty_users.clear()
            for row in rows:
                normalized = {
                    "user_id": str(row.get("user_id", "")),
                    "user_name": str(row.get("user_name", "")),
                    "affinity": int(row.get("affinity", 0) or 0),
                    "chat_count": int(row.get("chat_count", 0) or 0),
                }
                if normalized["user_id"]:
                    _affinity_cache.set(_cache_key(normalized["user_id"]), normalized)
        return len(rows)
    except Exception as e:
        print(f"❌ 전체 친밀도 불러오기 에러: {e}")
        return 0


def _ensure_cached(user_id, user_name) -> dict:
    key = _cache_key(user_id)
    cached = _affinity_cache.get(key)
    if cached is not None:
        return dict(cached)

    row = _load_from_db(user_id, user_name)
    _affinity_cache.set(key, row)
    return dict(row)


def get_user_affinity(user_id, user_name):
    row = _ensure_cached(user_id, user_name)
    return int(row.get("affinity", 0))


def update_user_affinity(user_id, user_name, amount):
    key = _cache_key(user_id)
    with _affinity_lock:
        row = _ensure_cached(user_id, user_name)
        row["user_name"] = user_name
        row["affinity"] = int(row.get("affinity", 0)) + int(amount)
        row["chat_count"] = int(row.get("chat_count", 0)) + 1
        _affinity_cache.set(key, row)
        _dirty_users.add(key)
        current_affinity = int(row["affinity"])

    diff_str = f"+{amount}" if amount >= 0 else f"{amount}"
    print(f"✅ {user_name} 친밀도 업데이트: {current_affinity - int(amount)} -> {current_affinity} ({diff_str})", flush=True)
    return current_affinity


def set_user_affinity(user_id, user_name, target_score):
    key = _cache_key(user_id)
    with _affinity_lock:
        row = _ensure_cached(user_id, user_name)
        row["user_name"] = user_name
        row["affinity"] = int(target_score)
        _affinity_cache.set(key, row)
        _dirty_users.add(key)
    return flush_user_affinity(user_id)


def flush_user_affinity(user_id) -> bool:
    key = _cache_key(user_id)
    row = _affinity_cache.get(key)
    if not row:
        return False

    supabase = get_supabase()
    if not supabase:
        return False

    try:
        supabase.table("user_stats").upsert({
            "user_id": str(row["user_id"]),
            "user_name": row["user_name"],
            "affinity": int(row.get("affinity", 0)),
            "chat_count": int(row.get("chat_count", 0)),
        }).execute()
        with _affinity_lock:
            _dirty_users.discard(key)
        return True
    except Exception as e:
        print(f"❌ 친밀도 저장 실패: {e}")
        return False


def flush_affinity_updates(force_all: bool = False) -> int:
    with _affinity_lock:
        keys = list(_dirty_users)
        if force_all:
            keys = list(_affinity_cache._data.keys())

    if not keys:
        return 0

    supabase = get_supabase()
    if not supabase:
        return 0

    payload = []
    for key in keys:
        row = _affinity_cache.get(key)
        if row:
            payload.append({
                "user_id": str(row["user_id"]),
                "user_name": row["user_name"],
                "affinity": int(row.get("affinity", 0)),
                "chat_count": int(row.get("chat_count", 0)),
            })

    if not payload:
        return 0

    try:
        supabase.table("user_stats").upsert(payload).execute()
        with _affinity_lock:
            for key in keys:
                _dirty_users.discard(key)
        return len(payload)
    except Exception as e:
        print(f"❌ 친밀도 일괄 저장 실패: {e}")
        return 0



def get_cached_affinity_only(user_id):
    row = _affinity_cache.get(_cache_key(user_id))
    if not row:
        return None
    return int(dict(row).get("affinity", 0))


def apply_immediate_affinity_change(user_id, user_name, amount, increment_chat=False):
    key = _cache_key(user_id)
    with _affinity_lock:
        row = _ensure_cached(user_id, user_name)
        before = int(row.get("affinity", 0))
        row["user_name"] = user_name
        row["affinity"] = before + int(amount)
        if increment_chat:
            row["chat_count"] = int(row.get("chat_count", 0)) + 1
        _affinity_cache.set(key, row)
        _dirty_users.add(key)
        after = int(row.get("affinity", 0))

    if flush_user_affinity(user_id):
        print(f"✅ {user_name} 친밀도 즉시 저장: {before} -> {after} ({'+' if int(amount) >= 0 else ''}{int(amount)})", flush=True)
    else:
        print(f"⚠️ {user_name} 친밀도 즉시 저장 실패, 캐시에만 반영됨: {before} -> {after}", flush=True)
    return after

def get_top_ranker_id():
    supabase = get_supabase()
    if not supabase:
        return None
    try:
        res = supabase.table("user_stats").select("user_id").order("affinity", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]["user_id"]
        return None
    except Exception as e:
        print(f"❌ 1위 조회 에러 (get_top_ranker_id): {e}")
        return None


def get_affinity_ranking(limit=30):
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        res = (
            supabase.table("user_stats")
            .select("user_name, affinity, chat_count")
            .order("affinity", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"❌ 랭킹 조회 에러: {e}")
        return []


def get_memory_from_db(user_name, limit: int = 3, max_chars: int = 500):
    from memory_service import get_memory_context
    return get_memory_context(user_name, limit=limit, max_chars=max_chars)


def save_to_memory(user_name, user_msg, bot_res):
    from memory_service import queue_memory_save
    queue_memory_save(user_name, user_msg, bot_res)


def get_attitude_guide(affinity):
    if affinity <= -31:
        return "혐오 상태. 상대를 극도로 싫어하며 차갑게 무시함."
    elif -30 <= affinity <= -1:
        return "불편/경계 상태. 날이 서 있고 말수가 적으며 공격적임."
    elif 0 <= affinity <= 500:
        return "비즈니스 상태. 무미건조하고 딱딱한 태도."
    elif 501 <= affinity <= 1000:
        return "호감 상태. 편하게 말하고 다정하고 친근하게 대하지만 절친보다는 어색함."
    else:
        return "절친 상태. 편하게 말하고 무한한 신뢰와 깊은 애정을 표현함."
