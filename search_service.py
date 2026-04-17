# search_service.py
# MODIFIED: SerpAPI 기반 검색 + DuckDuckGo fallback + AI 검색 판단/쿼리 생성 + 불필요 검색 차단
from __future__ import annotations

import html
import re
from typing import List, Dict, Tuple

import requests

import ai_service
from config import (
    SEARCH_ENABLED,
    SEARCH_DEBUG,
    SEARCH_MAX_RESULTS,
    SEARCH_TIMEOUT_SECONDS,
    SERPAPI_API_KEY,
    SEARCH_AI_DECISION_ENABLED,
    SEARCH_AI_QUERY_REWRITE_ENABLED,
    SEARCH_AI_MAX_MESSAGE_CHARS,
)

VOCATIVE_WORDS = [
    "뜌비야", "뜌비", "슈비야", "슈비", "봇아",
]

NOISE_PHRASES = [
    "알려줘", "알려 줘", "말해줘", "말해 줘", "뭐야", "뭔지", "어때", "대해서",
    "혹시", "지금", "현재", "요즘", "좀", "부탁해", "설명해줘", "설명해 줘",
    "이름 다", "전부", "목록 좀", "상세히", "자세히", "말해줄래", "말해 줄래",
]

SEARCH_KEYWORDS = [
    "최신", "지금", "현재", "가격", "얼마", "언제", "날짜", "순위", "뉴스", "검색",
    "누구", "멤버", "버전", "비교", "프로필", "소속", "정보", "목록", "이름", "공식",
    "기업", "회사", "인물", "출시", "발매", "시세",
]

SEARCH_PATTERNS = [
    r"누구(야|에요)?",
    r"멤버.*누구",
    r"최신.*(버전|모델|정보)",
    r"(가격|얼마|시세)",
    r"(언제|날짜|발매|출시)",
    r"(멤버|구성원|목록).*(다|전부|이름)",
]

SELF_KEYWORDS = ["너", "네", "너의", "뜌비", "이 봇", "봇", "너희", "네가"]
INTERNAL_KEYWORDS = [
    "코드", "시스템", "로직", "프롬프트", "에러", "버그", "캐시", "상태", "구조",
    "파일", "함수", "명령어", "설정", "모듈", "db", "데이터베이스", "반응", "검색기능",
]
NON_SEARCH_PATTERNS = [
    r"(너|네|너의|뜌비|봇).*(코드|시스템|로직|상태|구조|에러|버그|캐시|설정)",
    r"(이|내).*(코드|파일|함수|명령어).*(뭐|어때|상태|문제)",
    r"(왜|어째서).*(답|반응|말투)",
    r"(검색).*(왜|어째서|판정|트리거)",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ShuviBot/1.0; +https://example.com/bot)"
}




def is_search_runtime_enabled() -> bool:
    return SEARCH_ENABLED

def _debug(message: str) -> None:
    if SEARCH_DEBUG:
        print(message)


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _strip_noise(message: str) -> str:
    query = (message or "").strip()

    for word in VOCATIVE_WORDS:
        query = query.replace(word, " ")

    for phrase in NOISE_PHRASES:
        query = query.replace(phrase, " ")

    query = re.sub(r"<@!?\d+>", " ", query)
    query = re.sub(r"[?？！!,.。]+", " ", query)
    return _normalize_space(query)


def _should_never_search(message: str) -> bool:
    content = _normalize_space(message)
    if not content:
        return True

    if any(re.search(pattern, content) for pattern in NON_SEARCH_PATTERNS):
        return True

    if any(k in content for k in SELF_KEYWORDS) and any(k in content for k in INTERNAL_KEYWORDS):
        return True

    if content.startswith("왜 ") and any(k in content for k in ["검색", "반응", "코드", "상태"]):
        return True

    return False


def _heuristic_should_search(message: str) -> bool:
    if not SEARCH_ENABLED:
        return False

    content = _normalize_space(message)
    if not content:
        return False

    if _should_never_search(content):
        return False

    if any(keyword in content for keyword in SEARCH_KEYWORDS):
        return True

    return any(re.search(pattern, content) for pattern in SEARCH_PATTERNS)


def _ai_should_search(message: str) -> bool:
    if not SEARCH_AI_DECISION_ENABLED:
        return False

    content = _normalize_space(message)
    if not content or len(content) > SEARCH_AI_MAX_MESSAGE_CHARS:
        return False

    if _should_never_search(content):
        return False

    prompt = f"""아래 사용자의 질문이 '외부 검색'이 필요한 질문인지 판단하세요.
기준:
- 최신 정보, 인물/단체 멤버, 가격, 일정, 날짜, 순위, 뉴스, 프로필, 소속, 버전 비교는 YES
- 봇 자신의 상태, 코드, 시스템, 로직, 설정, 에러, 캐시, 현재 대화 설명은 NO
- 일상 대화, 감정 표현, 잡담, 창작 요청은 NO
정답은 YES 또는 NO 한 단어로만 답하세요.

질문: {content}"""
    try:
        result = ai_service.generate_simple_text(prompt)
        answer = result.strip().upper()
        _debug(f"[SEARCH] ai_decision_raw={answer}")
        return answer.startswith("YES")
    except Exception as e:
        _debug(f"[SEARCH] ai_decision_failed={e}")
        return False


def should_search(message: str) -> Tuple[bool, str]:
    if not SEARCH_ENABLED:
        return False, "disabled"

    if _should_never_search(message):
        return False, "blocked"

    if _heuristic_should_search(message):
        return True, "heuristic"

    if _ai_should_search(message):
        return True, "ai"

    return False, "none"


def clean_query(message: str) -> str:
    query = _strip_noise(message)

    query = query.replace("누구야", " ").replace("누구", " ")
    query = query.replace("뭐야", " ").replace("뭔지", " ")
    query = query.replace("있는 그룹", " 그룹")
    query = query.replace("이 있는 그룹", " 그룹")
    query = query.replace("이름 다", " 목록")
    query = query.replace("이름", " ")
    query = query.replace(" 다", " ")
    query = query.replace("에 대해서", " ")
    query = query.replace("에 대해", " ")
    query = query.replace("대해", " ")

    query = _normalize_space(query)

    if "멤버" in query and "목록" not in query:
        query = query.replace("멤버", " 멤버 목록 ")
    if "프로필" in query and "공식" not in query:
        query = query + " 공식"
    if "소속" in query and "프로필" not in query:
        query = query + " 프로필"

    query = _normalize_space(query)
    return query or _normalize_space(message)


def _ai_rewrite_query(message: str, fallback_query: str) -> str:
    if not SEARCH_AI_QUERY_REWRITE_ENABLED:
        return fallback_query

    content = _normalize_space(message)
    if not content or len(content) > SEARCH_AI_MAX_MESSAGE_CHARS:
        return fallback_query

    prompt = f"""아래 사용자 질문을 웹 검색엔진용 키워드 쿼리로 바꾸세요.
규칙:
- 한국어로 답하세요
- 군더더기 표현(알려줘, 뭐야, 혹시, 지금 등)은 제거하세요
- 핵심 명사만 2~6단어 정도로 구성하세요
- 최신/프로필/멤버/소속/가격/버전 질문이면 그 의도에 맞는 검색어로 바꾸세요
- 봇 자신의 코드/상태/시스템 관련 질문이면 기본 후보를 그대로 유지하세요
- 따옴표, 설명, 문장부호 없이 검색어만 한 줄로 출력하세요

질문: {content}
기본 후보: {fallback_query}"""
    try:
        rewritten = ai_service.generate_simple_text(prompt)
        rewritten = rewritten.splitlines()[0].strip()
        rewritten = re.sub(r'^[\\"\'\`\-•]+|[\\"\'\`]+$', "", rewritten).strip()
        rewritten = _normalize_space(rewritten)
        if not rewritten:
            return fallback_query
        return rewritten
    except Exception as e:
        _debug(f"[SEARCH] ai_rewrite_failed={e}")
        return fallback_query


def _rank_results(results: List[Dict], query: str) -> List[Dict]:
    query_terms = [t for t in re.split(r"\s+", query.lower()) if t]
    preferred_domains = [
        "official", "officia", "stellive", "hololive", "youtube", "namu.wiki", "wikipedia"
    ]

    def score(item: Dict) -> int:
        title = (item.get("title") or "").lower()
        snippet = (item.get("snippet") or "").lower()
        link = (item.get("link") or "").lower()
        value = 0
        for term in query_terms:
            if term in title:
                value += 8
            if term in snippet:
                value += 3
            if term in link:
                value += 4
        for domain in preferred_domains:
            if domain in link:
                value += 6
        if any(x in title for x in ["talents", "members", "프로필", "소속", "공식"]):
            value += 5
        return value

    return sorted(results, key=score, reverse=True)


def _normalize_results(raw_results: List[Dict], provider: str) -> List[Dict]:
    results: List[Dict] = []
    for item in raw_results[: max(SEARCH_MAX_RESULTS * 2, SEARCH_MAX_RESULTS)]:
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or item.get("body") or "").strip()
        link = (item.get("link") or item.get("url") or "").strip()

        if not title and not snippet:
            continue

        results.append({
            "title": html.unescape(title),
            "snippet": html.unescape(snippet),
            "link": link,
            "provider": provider,
        })

    return results


def _search_serpapi(query: str) -> List[Dict]:
    if not SERPAPI_API_KEY:
        return []

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "hl": "ko",
        "gl": "kr",
        "num": SEARCH_MAX_RESULTS,
    }
    try:
        res = requests.get(
            "https://serpapi.com/search.json",
            params=params,
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        payload = res.json()
        organic = payload.get("organic_results") or []
        normalized = _normalize_results(
            [{"title": x.get("title"), "snippet": x.get("snippet"), "link": x.get("link")} for x in organic],
            "serpapi",
        )
        normalized = _rank_results(normalized, query)[:SEARCH_MAX_RESULTS]
        _debug(f"[SEARCH] provider=serpapi results={len(normalized)}")
        return normalized
    except Exception as e:
        _debug(f"[SEARCH] provider=serpapi failed: {e}")
        return []


def _search_duckduckgo(query: str) -> List[Dict]:
    try:
        res = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "kl": "kr-ko"},
            headers=HEADERS,
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        text = res.text

        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
            re.S,
        )
        items = []
        for match in pattern.finditer(text):
            title = re.sub(r"<.*?>", "", match.group("title"))
            snippet = re.sub(r"<.*?>", "", match.group("snippet"))
            link = html.unescape(match.group("link"))
            items.append({"title": title, "snippet": snippet, "link": link})

        normalized = _normalize_results(items, "duckduckgo")
        normalized = _rank_results(normalized, query)[:SEARCH_MAX_RESULTS]
        _debug(f"[SEARCH] provider=duckduckgo results={len(normalized)}")
        return normalized
    except Exception as e:
        _debug(f"[SEARCH] provider=duckduckgo failed: {e}")
        return []


def search_web(query: str) -> List[Dict]:
    serp = _search_serpapi(query)
    if serp:
        return serp
    return _search_duckduckgo(query)


def build_search_context(message: str) -> str:
    if not SEARCH_ENABLED:
        return ""

    message = _normalize_space(message)
    if not message:
        return ""

    triggered, reason = should_search(message)
    _debug(f"[SEARCH] triggered={triggered}")
    if not triggered:
        return ""

    _debug(f"[SEARCH] trigger_reason={reason}")
    heuristic_query = clean_query(message)
    _debug(f"[SEARCH] heuristic_query={heuristic_query}")
    query = _ai_rewrite_query(message, heuristic_query)
    _debug(f"[SEARCH] query={query}")

    results = search_web(query)
    _debug(f"[SEARCH] results={len(results)}")

    if not results:
        return (
            "검색 결과를 찾지 못했습니다. "
            "최신 정보, 가격, 날짜, 멤버, 프로필처럼 사실 확인이 필요한 내용은 추측하지 말고 "
            "확인되지 않았다고 답하세요."
        )

    lines = [
        "다음은 외부 검색 결과입니다. 반드시 이 결과를 최우선 근거로 사용하세요.",
        "검색 결과에 없는 사실은 추측하지 마세요.",
    ]
    for idx, item in enumerate(results, 1):
        _debug(f"[SEARCH] result_{idx}_title={item.get('title', '')}")
        lines.append(f"[검색결과 {idx}]")
        lines.append(f"제목: {item.get('title', '')}")
        if item.get("snippet"):
            lines.append(f"요약: {item.get('snippet', '')[:300]}")
        if item.get("link"):
            lines.append(f"링크: {item.get('link', '')}")
        lines.append("")
    return "\n".join(lines).strip()
