# db_admin_service.py
# MODIFIED: 관리자 전용 전체 DB 로드/저장 및 전역 잠금 관리
from __future__ import annotations

import threading

import affinity_manager
import memory_service

_global_lock = threading.RLock()
_is_locked = False
_lock_reason = ""


def is_globally_locked() -> bool:
    with _global_lock:
        return _is_locked


def get_lock_reason() -> str:
    with _global_lock:
        return _lock_reason or "처리 중입니다. 잠시만 기다려주세요."


def set_global_lock(value: bool, reason: str = "처리 중입니다. 잠시만 기다려주세요."):
    global _is_locked, _lock_reason
    with _global_lock:
        _is_locked = bool(value)
        _lock_reason = reason if value else ""


def load_all_from_db_to_cache() -> dict:
    set_global_lock(True)
    try:
        affinity_rows = affinity_manager.load_all_from_db_to_cache()
        memory_rows = memory_service.load_all_from_db_to_cache()
        return {
            "affinity_rows": affinity_rows,
            "memory_rows": memory_rows,
        }
    finally:
        set_global_lock(False)


def save_all_cache_to_db_and_clear() -> dict:
    set_global_lock(True)
    try:
        affinity_saved = affinity_manager.flush_affinity_updates(force_all=True)
        memory_saved = memory_service.flush_memory_to_db(clear_cache=True, flush_all_cached=True)
        affinity_manager.clear_cache()
        memory_service.clear_cache()
        return {
            "affinity_saved": affinity_saved,
            "memory_saved": memory_saved,
        }
    finally:
        set_global_lock(False)
