# dating_bridge.py
# MODIFIED: 메인 봇에서 미연시 DB 상태 조회/초기화/호칭 연동만 담당
from __future__ import annotations

import threading
from typing import Optional

from cache_store import TTLCache
from db_client import get_supabase

_title_cache = TTLCache[dict](300.0)
_lock = threading.RLock()


def _default_state(user_id: int, user_name: str) -> dict:
    return {
        "user_id": str(user_id),
        "user_name": user_name,
        "affection": 0,
        "relationship_stage": "어색한 친구",
        "assigned_personality": "기본",
        "current_day": 1,
        "ending_type": "",
        "marriage_title": "",
    }


def get_admin_state_summary(user_id: int, user_name: str) -> dict:
    supabase = get_supabase()
    if not supabase:
        return _default_state(user_id, user_name)
    try:
        res = (
            supabase.table("dating_state")
            .select("user_id, user_name, affection, relationship_stage, assigned_personality, current_day, ending_type, marriage_title")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        if res.data:
            row = dict(res.data[0])
            row.setdefault("user_name", user_name)
            row.setdefault("assigned_personality", "기본")
            row.setdefault("relationship_stage", "어색한 친구")
            row.setdefault("ending_type", "")
            row.setdefault("current_day", 1)
            row.setdefault("affection", 0)
            row.setdefault("marriage_title", "")
            return row
    except Exception as e:
        print(f"❌ 미연시 정보 조회 에러: {e}")
    return _default_state(user_id, user_name)


def reset_state(user_id: int) -> bool:
    supabase = get_supabase()
    if not supabase:
        return False
    try:
        supabase.table("dating_state").delete().eq("user_id", str(user_id)).execute()
        supabase.table("dating_event_logs").delete().eq("user_id", str(user_id)).execute()
        with _lock:
            _title_cache.delete_prefix(str(user_id))
        return True
    except Exception as e:
        print(f"❌ 미연시 상태 초기화 에러: {e}")
        return False


def _load_title_row(user_id: int, user_name: str) -> dict:
    cached = _title_cache.get(str(user_id))
    if cached is not None:
        return dict(cached)
    supabase = get_supabase()
    row = {"user_id": str(user_id), "user_name": user_name, "ending_type": "", "marriage_title": ""}
    if not supabase:
        _title_cache.set(str(user_id), row)
        return row
    try:
        res = (
            supabase.table("dating_state")
            .select("user_id, user_name, ending_type, marriage_title")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        if res.data:
            row.update(dict(res.data[0]))
    except Exception as e:
        print(f"❌ 미연시 호칭 조회 에러: {e}")
    _title_cache.set(str(user_id), row)
    return row


def get_general_chat_override(user_id: int, user_name: str, affinity: int) -> str:
    if int(affinity) < 1000:
        return ""
    row = _load_title_row(user_id, user_name)
    if str(row.get("ending_type", "")) == "결혼" and str(row.get("marriage_title", "")).strip():
        title = str(row.get("marriage_title", "")).strip()
        return f"상대를 반드시 '{title}'라고 불러. 이 호칭은 절대 바꾸지 마. 다른 호칭으로 대체하지 마. 문장 첫머리에서도 유지해."
    return ""
