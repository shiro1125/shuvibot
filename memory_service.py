# memory_service.py
# MODIFIED: 일반 대화 기억 캐시 / 5분 저장 / 캐시 확인 분리
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Dict, List

from config import MEMORY_CONTEXT_LIMIT, MEMORY_CONTEXT_MAX_CHARS
from db_client import get_supabase

_memory_lock = threading.RLock()
_persisted_rows_by_user: Dict[str, List[dict]] = defaultdict(list)
_pending_rows_by_user: Dict[str, List[dict]] = defaultdict(list)
_pending_inserts: List[dict] = []
_all_loaded = False
_loaded_users: set[str] = set()


def clear_cache():
    global _all_loaded
    with _memory_lock:
        _persisted_rows_by_user.clear()
        _pending_rows_by_user.clear()
        _pending_inserts.clear()
        _loaded_users.clear()
        _all_loaded = False


def _merge_rows(user_name: str) -> List[dict]:
    persisted = _persisted_rows_by_user.get(user_name, [])
    pending = _pending_rows_by_user.get(user_name, [])
    return list(persisted) + list(pending)


def _load_user_from_db(user_name: str):
    global _all_loaded
    with _memory_lock:
        if _all_loaded or user_name in _loaded_users:
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
            .order("created_at", desc=False)
            .execute()
        )
        rows = []
        for row in res.data or []:
            rows.append({
                "user_name": str(row.get("user_name", user_name)),
                "user_msg": str(row.get("user_msg", "")),
                "bot_res": str(row.get("bot_res", "")),
            })
        with _memory_lock:
            _persisted_rows_by_user[user_name] = rows
            _loaded_users.add(user_name)
    except Exception as e:
        print(f"❌ 기억 불러오기 에러: {e}")
        with _memory_lock:
            _loaded_users.add(user_name)


def load_all_from_db_to_cache() -> int:
    global _all_loaded
    supabase = get_supabase()
    if not supabase:
        return 0

    try:
        res = supabase.table("memory").select("user_name, user_msg, bot_res").order("created_at", desc=False).execute()
        grouped: Dict[str, List[dict]] = defaultdict(list)
        for row in res.data or []:
            user_name = str(row.get("user_name", "")).strip()
            if not user_name:
                continue
            grouped[user_name].append({
                "user_name": user_name,
                "user_msg": str(row.get("user_msg", "")),
                "bot_res": str(row.get("bot_res", "")),
            })
        with _memory_lock:
            _persisted_rows_by_user.clear()
            _pending_rows_by_user.clear()
            _pending_inserts.clear()
            for user_name, rows in grouped.items():
                _persisted_rows_by_user[user_name] = rows
            _loaded_users.clear()
            _loaded_users.update(grouped.keys())
            _all_loaded = True
        return sum(len(rows) for rows in grouped.values())
    except Exception as e:
        print(f"❌ 전체 기억 불러오기 에러: {e}")
        return 0


def get_memory_context(user_name: str, limit: int = MEMORY_CONTEXT_LIMIT, max_chars: int = MEMORY_CONTEXT_MAX_CHARS) -> str:
    _load_user_from_db(user_name)
    with _memory_lock:
        rows = _merge_rows(user_name)[-limit:]

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
        _pending_rows_by_user[user_name].append(row)
        _pending_inserts.append(row)
        _loaded_users.add(user_name)


def flush_memory_to_db(clear_cache: bool = False, flush_all_cached: bool = False) -> int:
    global _all_loaded
    supabase = get_supabase()
    if not supabase:
        return 0

    with _memory_lock:
        if flush_all_cached:
            payload = []
            for user_name in set(_persisted_rows_by_user.keys()) | set(_pending_rows_by_user.keys()):
                payload.extend(_merge_rows(user_name))
        else:
            payload = list(_pending_inserts)

        if not payload:
            if clear_cache:
                _persisted_rows_by_user.clear()
                _pending_rows_by_user.clear()
                _loaded_users.clear()
                _all_loaded = False
            return 0

        if not flush_all_cached:
            _pending_inserts.clear()

    try:
        if flush_all_cached:
            supabase.table("memory").delete().neq("user_name", "").execute()
            if payload:
                supabase.table("memory").insert(payload).execute()
        else:
            supabase.table("memory").insert(payload).execute()

        with _memory_lock:
            if flush_all_cached:
                grouped: Dict[str, List[dict]] = defaultdict(list)
                for row in payload:
                    grouped[str(row.get("user_name", ""))].append(dict(row))
                _persisted_rows_by_user.clear()
                for user_name, rows in grouped.items():
                    _persisted_rows_by_user[user_name] = rows
                _pending_rows_by_user.clear()
            else:
                for row in payload:
                    user_name = str(row.get("user_name", ""))
                    _persisted_rows_by_user[user_name].append(dict(row))
                for row in payload:
                    user_name = str(row.get("user_name", ""))
                    pending = _pending_rows_by_user.get(user_name, [])
                    if pending:
                        try:
                            pending.remove(row)
                        except ValueError:
                            pass
            if clear_cache:
                _persisted_rows_by_user.clear()
                _pending_rows_by_user.clear()
                _loaded_users.clear()
                _all_loaded = False
        return len(payload)
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")
        with _memory_lock:
            _pending_inserts[:0] = payload
        return 0


def get_recent_memory_rows(user_name: str, limit: int = 10) -> list[dict]:
    _load_user_from_db(user_name)
    with _memory_lock:
        rows = _merge_rows(user_name)[-limit:]
    return [dict(row) for row in rows]


def get_recent_user_inputs_cache(user_name: str, limit: int = 10) -> list[str]:
    with _memory_lock:
        rows = list(_pending_rows_by_user.get(user_name, []))[-limit:]
    return [str(row.get("user_msg", "")) for row in rows if str(row.get("user_msg", "")).strip()]
