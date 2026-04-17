# reaction_state.py
# MODIFIED: 뜌비 반응 on/off 상태 저장 및 조회
import json
import os
from threading import Lock

_STATE_PATH = os.path.join(os.path.dirname(__file__), "reaction_state.json")
_LOCK = Lock()


def _blank():
    return {"guilds": {}, "users": {}}


def _load_state():
    if not os.path.exists(_STATE_PATH):
        return _blank()
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _blank()
        data.setdefault("guilds", {})
        data.setdefault("users", {})
        return data
    except Exception:
        return _blank()


def _save_state(state):
    temp_path = _STATE_PATH + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, _STATE_PATH)


def set_guild_reaction_enabled(guild_id: int, enabled: bool):
    with _LOCK:
        state = _load_state()
        state["guilds"][str(guild_id)] = bool(enabled)
        _save_state(state)


def is_guild_reaction_enabled(guild_id: int) -> bool:
    with _LOCK:
        state = _load_state()
        return state["guilds"].get(str(guild_id), True)


def set_user_reaction_enabled(user_id: int, enabled: bool):
    with _LOCK:
        state = _load_state()
        state["users"][str(user_id)] = bool(enabled)
        _save_state(state)


def is_user_reaction_enabled(user_id: int) -> bool:
    with _LOCK:
        state = _load_state()
        return state["users"].get(str(user_id), True)


# 기존 호출 호환
def set_dm_reaction_enabled(user_id: int, enabled: bool):
    set_user_reaction_enabled(user_id, enabled)


def is_dm_reaction_enabled(user_id: int) -> bool:
    return is_user_reaction_enabled(user_id)
