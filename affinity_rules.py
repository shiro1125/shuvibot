import re
from collections import defaultdict, deque
from difflib import SequenceMatcher
from typing import Deque, Dict, List

MAX_HISTORY = 10
RECENT_SIMILAR_WINDOW = 5

_user_message_history: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=MAX_HISTORY))
_user_positive_history: Dict[str, Deque[bool]] = defaultdict(lambda: deque(maxlen=10))

SHORT_EMOTION_PATTERNS = [
    r"(귀여워\s*){2,}",
    r"(좋아\s*){2,}",
    r"(사랑해\s*){2,}",
    r"(고마워\s*){2,}",
    r"(최고야\s*){2,}",
]

FARMING_PATTERNS = [
    r"점수\s*올려",
    r"점수\s*줘",
    r"친밀도\s*올려",
    r"친밀도\s*줘",
    r"스코어\s*줘",
    r"score\s*plz",
    r"score\s*please",
]

RUDE_PATTERNS = [
    r"꺼져",
    r"닥쳐",
    r"멍청",
    r"바보",
    r"짜증나",
]

POSITIVE_PATTERNS = [
    r"고마워",
    r"감사",
    r"좋아",
    r"귀엽",
    r"편하",
    r"즐겁",
    r"최고",
    r"사랑해",
]


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _recent_similar_count(user_name: str, normalized_text: str) -> int:
    recent: List[str] = list(_user_message_history[user_name])[-RECENT_SIMILAR_WINDOW:]
    count = 0
    for old in recent:
        if old == normalized_text or _similar(old, normalized_text) >= 0.88:
            count += 1
    return count


def apply_score_rules(user_name: str, raw_message: str, raw_score: int) -> int:
    text = _normalize(raw_message)
    final_score = raw_score

    if any(re.search(pattern, text) for pattern in FARMING_PATTERNS):
        final_score = min(final_score, 0)
        final_score = max(final_score, -10)

    if any(re.search(pattern, text) for pattern in SHORT_EMOTION_PATTERNS):
        final_score = 0

    similar_count = _recent_similar_count(user_name, text)
    if similar_count >= 3:
        final_score = 0 if final_score >= 0 else max(final_score, -30)
    elif similar_count >= 2:
        final_score = int(final_score * 0.5)

    if list(_user_message_history[user_name]) and list(_user_message_history[user_name])[-1] == text:
        final_score = -30

    if any(re.search(pattern, text) for pattern in RUDE_PATTERNS):
        final_score = min(final_score, -5)
        final_score = max(final_score, -20)

    positive_ratio_bonus = 0
    positives = list(_user_positive_history[user_name])
    if len(positives) >= 10 and sum(positives) / len(positives) >= 0.7 and similar_count < 2:
        positive_ratio_bonus = 2

    final_score += positive_ratio_bonus
    final_score = max(-30, min(20, final_score))

    is_positive = any(re.search(pattern, text) for pattern in POSITIVE_PATTERNS) and final_score > 0
    _user_message_history[user_name].append(text)
    _user_positive_history[user_name].append(is_positive)

    return final_score
