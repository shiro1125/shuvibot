# response_service.py
# MODIFIED: 응답 흐름 보조 함수 분리
import asyncio
from typing import Tuple

import discord

import affinity_manager
import affinity_rules
import personality
from config import MAX_USER_MESSAGE_LEN, SHUVI_USER_ID
from memory_service import get_memory_context, queue_memory_save


def should_respond(bot, message: discord.Message) -> bool:
    if message.author.bot or not bot.user:
        return False
    content = (message.content or "").strip()
    if not content:
        return False
    if len(content) > MAX_USER_MESSAGE_LEN:
        return False
    return bot.user.mentioned_in(message) or "뜌비" in content


def build_user_content(history_context: str, user_message: str, personality_name: str, search_context: str = "") -> str:
    parts = []

    if search_context:
        parts.append(search_context)

    if personality_name == "기본" and history_context:
        parts.append(f"과거 대화 기억:\n{history_context}")

    parts.append(f"현재 유저의 말: {user_message}")
    return "\n\n".join(parts)


def parse_ai_response(full_text: str, user_name: str, user_message: str) -> Tuple[str, int]:
    clean_res = full_text
    score_change = 0

    if "[SCORE:" not in full_text:
        return clean_res, score_change

    try:
        parts = full_text.split("[SCORE:")
        clean_res = parts[0].strip()
        score_val_str = parts[1].split("]")[0].strip()
        raw_score = int(score_val_str.replace("+", ""))
        score_change = affinity_rules.apply_score_rules(user_name, user_message, raw_score)
        if raw_score != score_change:
            print(f"⚠️ SCORE 보정 적용: {raw_score} -> {score_change}")
    except Exception as parse_err:
        print(f"⚠️ 점수 파싱 에러: {parse_err}")
        clean_res = full_text
        score_change = 0

    return clean_res, score_change


async def fetch_context(user_id: int, user_name: str, personality_name: str):
    loop = asyncio.get_running_loop()
    affinity_task = loop.run_in_executor(None, affinity_manager.get_user_affinity, user_id, user_name)
    if personality_name == "기본":
        history_task = loop.run_in_executor(None, get_memory_context, user_name)
    else:
        history_task = None

    affinity = await affinity_task
    history_context = await history_task if history_task else ""
    return affinity, history_context


def build_system_instruction(user_id: int, user_name: str, current_personality: str, affinity: int) -> str:
    is_shuvi = user_id == SHUVI_USER_ID
    personality_guide = personality.get_personality_guide(current_personality)
    attitude = affinity_manager.get_attitude_guide(affinity)
    return personality.make_system_instruction(
        is_shuvi,
        user_name,
        current_personality,
        attitude,
        personality_guide,
    )


async def persist_after_response(
    user_id: int,
    user_name: str,
    user_message: str,
    clean_res: str,
    score_change: int,
    personality_name: str,
):
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, affinity_manager.update_user_affinity, user_id, user_name, score_change)
    ]
    if personality_name == "기본":
        tasks.append(loop.run_in_executor(None, queue_memory_save, user_name, user_message, clean_res))
    await asyncio.gather(*tasks, return_exceptions=True)
