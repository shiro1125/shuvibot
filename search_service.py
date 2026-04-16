# search_service.py
# MODIFIED: SerpAPI 기반 검색 + DuckDuckGo fallback + AI 검색 판단/쿼리 생성
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
    "이름 다", "전부", "목록 좀",
]

SEARCH_KEYWORDS = [
    "최신", "지금", "현재", "가격", "얼마", "언제", "날짜", "순위", "뉴스", "검색",
    "누구", "멤버", "버전", "비교", "프로필", "소속", "정보", "목록", "이름", "공식",
]

SEARCH_PATTERNS = [
    r"누구(야|에요)?",
    r"멤버.*누구",
    r"최신.*(버전|모델|정보)",
    r"(가격|얼마|시세)",
    r"(언제|날짜|발매|출시)",
    r"(멤버|구성원|목록).*(다|전부|이름)",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ShuviBot/1.0; +https://example.com/bot)"
}


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


def _heuristic_should_search(message: str) -> bool:
    if not SEARCH_ENABLED:
        return False

    content = _normalize_space(message)
    if not content:
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

    prompt = f"""아래 사용자의 질문이 '외부 검색'이 필요한 질문인지 판단하세요.
기준:
- 최신 정보, 인물/단체 멤버, 가격, 일정, 날짜, 순위, 뉴스, 프로필, 소속, 버전 비교는 YES
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

    if _heuristic_should_search(message):
        return True, "heuristic"

    if _ai_should_search(message):
        return True, "ai"

    return False, "none"


def clean_query(message: str) -> str:
    query = _strip_noise(message)

    # 질문 유형별 보정
    query = query.replace("누구야", " ").replace("누구", " ")
    query = query.replace("뭐야", " ").replace("뭔지", " ")
    query = query.replace("있는 그룹", " 그룹")
    query = query.replace("이 있는 그룹", " 그룹")
    query = query.replace("이름 다", " 목록")
    query = query.replace("이름", " ")
    query = query.replace("다", " ")
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
- 따옴표, 설명, 문장부호 없이 검색어만 한 줄로 출력하세요

질문: {content}
기본 후보: {fallback_query}"""
    try:
        rewritten = ai_service.generate_simple_text(prompt)
        rewritten = rewritten.splitlines()[0].strip()
        rewritten = re.sub(r'^[\\"\'`\-•]+|[\\"\'`]+$', "", rewritten).strip()
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
        link = (item.get("link") or item.get("href") or "").strip()
        if not title and not snippet:
            continue
        results.append({
            "title": title,
            "snippet": snippet,
            "link": link,
            "provider": provider,
        })
    return results


def _search_serpapi(query: str) -> List[Dict]:
    if not SERPAPI_API_KEY:
        return []

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "hl": "ko",
        "gl": "kr",
        "safe": "off",
        "num": max(SEARCH_MAX_RESULTS * 2, SEARCH_MAX_RESULTS),
    }
    resp = requests.get(url, params=params, headers=HEADERS, timeout=SEARCH_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    organic = data.get("organic_results") or []
    normalized = []
    for item in organic:
        normalized.append({
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "link": item.get("link", ""),
        })
    return _normalize_results(normalized, "serpapi")


def _search_duckduckgo(query: str) -> List[Dict]:
    url = "https://html.duckduckgo.com/html/"
    resp = requests.post(
        url,
        data={"q": query, "kl": "kr-ko", "kp": "-2"},
        headers=HEADERS,
        timeout=SEARCH_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    text = resp.text

    blocks = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="(?P<link>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet1>.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(?P<snippet2>.*?)</div>)',
        text,
        flags=re.S,
    )

    results = []
    for link, title, snippet1, snippet2 in blocks[: max(SEARCH_MAX_RESULTS * 2, SEARCH_MAX_RESULTS)]:
        title_clean = re.sub(r"<.*?>", "", html.unescape(title)).strip()
        snippet_raw = snippet1 or snippet2 or ""
        snippet_clean = re.sub(r"<.*?>", "", html.unescape(snippet_raw)).strip()
        results.append({
            "title": title_clean,
            "snippet": snippet_clean,
            "link": html.unescape(link),
        })

    return _normalize_results(results, "duckduckgo")


def search_web(message: str) -> Tuple[bool, str, List[Dict]]:
    triggered, reason = should_search(message)
    _debug(f"[SEARCH] triggered={triggered}")
    if not triggered:
        return False, "", []

    _debug(f"[SEARCH] trigger_reason={reason}")

    heuristic_query = clean_query(message)
    final_query = _ai_rewrite_query(message, heuristic_query)
    if not final_query:
        final_query = heuristic_query

    _debug(f"[SEARCH] heuristic_query={heuristic_query}")
    _debug(f"[SEARCH] query={final_query}")

    results: List[Dict] = []
    if SERPAPI_API_KEY:
        try:
            results = _search_serpapi(final_query)
            results = _rank_results(results, final_query)[:SEARCH_MAX_RESULTS]
            _debug(f"[SEARCH] provider=serpapi results={len(results)}")
        except Exception as e:
            _debug(f"[SEARCH] provider=serpapi failed: {e}")

    if not results:
        try:
            results = _search_duckduckgo(final_query)
            results = _rank_results(results, final_query)[:SEARCH_MAX_RESULTS]
            _debug(f"[SEARCH] provider=duckduckgo results={len(results)}")
        except Exception as e:
            _debug(f"[SEARCH] provider=duckduckgo failed: {e}")
            results = []

    _debug(f"[SEARCH] results={len(results)}")
    for idx, item in enumerate(results[:SEARCH_MAX_RESULTS], start=1):
        _debug(f"[SEARCH] result_{idx}_title={item.get('title', '')}")

    return True, final_query, results


def build_search_context(message: str) -> str:
    triggered, query, results = search_web(message)
    if not triggered:
        return ""

    if not results:
        return (
            "외부 검색을 시도했지만 신뢰할 수 있는 결과를 찾지 못했습니다.\n"
            "최신 정보, 멤버, 소속, 날짜, 가격, 순위처럼 확인이 필요한 내용은 추측하지 말고 "
            "확인되지 않았다고 답하세요."
        )

    lines = [
        "다음은 외부 검색 결과입니다. 반드시 아래 결과를 최우선 근거로 사용하세요.",
        "검색 결과에 없는 내용은 추측하지 말고, 확실하지 않으면 모른다고 답하세요.",
        f"검색어: {query}",
        "",
    ]
    for idx, item in enumerate(results[:SEARCH_MAX_RESULTS], start=1):
        title = item.get("title", "").strip()
        snippet = item.get("snippet", "").strip()
        link = item.get("link", "").strip()
        lines.append(f"[검색결과 {idx}]")
        if title:
            lines.append(f"제목: {title}")
        if snippet:
            lines.append(f"내용: {snippet}")
        if link:
            lines.append(f"링크: {link}")
        lines.append("")

    return "\n".join(lines).strip()