# memory_service.py
# MODIFIED: 기억 캐시 / 5분 주기 저장 분리
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, List

from config import MEMORY_CONTEXT_LIMIT, MEMORY_CONTEXT_MAX_CHARS
from db_client import get_supabase

_memory_lock = threading.RLock()
_recent_context: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=MEMORY_CONTEXT_LIMIT + 5))
_pending_inserts: List[dict] = []
_loaded_users: set[str] = set()


def _ensure_loaded(user_name: str):
    with _memory_lock:
        if user_name in _loaded_users:
            return

    supabase = get_supabase()
    if not supabase:
        with _memory_lock:
            _loaded_users.add(user_name)
        return

    try:
        res = (
            supabase.table("memory")
            .select("user_name, user_msg, bot_res")
            .eq("user_name", user_name)
            .order("created_at", desc=True)
            .limit(MEMORY_CONTEXT_LIMIT)
            .execute()
        )
        rows = list(reversed(res.data or []))
        with _memory_lock:
            bucket = _recent_context[user_name]
            for row in rows:
                bucket.append({
                    "user_name": row.get("user_name", user_name),
                    "user_msg": str(row.get("user_msg", "")),
                    "bot_res": str(row.get("bot_res", "")),
                })
            _loaded_users.add(user_name)
    except Exception as e:
        print(f"❌ 기억 불러오기 에러: {e}")
        with _memory_lock:
            _loaded_users.add(user_name)


def get_memory_context(user_name: str, limit: int = MEMORY_CONTEXT_LIMIT, max_chars: int = MEMORY_CONTEXT_MAX_CHARS) -> str:
    _ensure_loaded(user_name)

    with _memory_lock:
        rows = list(_recent_context.get(user_name, deque()))[-limit:]

    lines = []
    total_chars = 0
    for row in rows:
        line = f"{row['user_name']}: {str(row['user_msg'])[:120]} -> 뜌비: {str(row['bot_res'])[:120]}"
        total_chars += len(line)
        if total_chars > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)


def queue_memory_save(user_name: str, user_msg: str, bot_res: str):
    row = {
        "user_name": user_name,
        "user_msg": user_msg,
        "bot_res": bot_res,
    }
    with _memory_lock:
        _recent_context[user_name].append(row)
        _pending_inserts.append(row)
        _loaded_users.add(user_name)


def flush_memory_to_db():
    with _memory_lock:
        if not _pending_inserts:
            return 0
        payload = list(_pending_inserts)
        _pending_inserts.clear()

    supabase = get_supabase()
    if not supabase:
        return 0

    try:
        supabase.table("memory").insert(payload).execute()
        return len(payload)
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")
        with _memory_lock:
            _pending_inserts[:0] = payload
        return 0
