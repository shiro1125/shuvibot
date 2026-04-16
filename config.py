# config.py
# MODIFIED: 환경 변수 및 공통 설정 분리
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip().strip('"').strip("'")
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip().strip('"').strip("'")
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip().strip('"').strip("'")

GUILD_ID_1 = 1228372760212930652
SHUVI_USER_ID = 440517859140173835
MAX_USER_MESSAGE_LEN = 200

MODEL_LIST = [
    "models/gemini-2.5-flash-lite",
]
ACTIVE_MODEL_DEFAULT = "대기 중"

AFFINITY_CACHE_TTL_SECONDS = 600.0
MEMORY_CONTEXT_LIMIT = 3
MEMORY_CONTEXT_MAX_CHARS = 500
MEMORY_FLUSH_INTERVAL_SECONDS = 300
AFFINITY_FLUSH_INTERVAL_SECONDS = 60

SERPAPI_API_KEY = (os.getenv("SERPAPI_API_KEY") or "").strip().strip('"').strip("'")
SEARCH_ENABLED = (os.getenv("SEARCH_ENABLED") or "true").strip().lower() == "true"
SEARCH_DEBUG = (os.getenv("SEARCH_DEBUG") or "true").strip().lower() == "true"
SEARCH_MAX_RESULTS = int((os.getenv("SEARCH_MAX_RESULTS") or "3").strip())
SEARCH_TIMEOUT_SECONDS = int((os.getenv("SEARCH_TIMEOUT_SECONDS") or "3").strip())

# MODIFIED: 검색 판단/쿼리 생성 고도화 옵션
SEARCH_AI_DECISION_ENABLED = (os.getenv("SEARCH_AI_DECISION_ENABLED") or "true").strip().lower() == "true"
SEARCH_AI_QUERY_REWRITE_ENABLED = (os.getenv("SEARCH_AI_QUERY_REWRITE_ENABLED") or "true").strip().lower() == "true"
SEARCH_AI_MAX_MESSAGE_CHARS = int((os.getenv("SEARCH_AI_MAX_MESSAGE_CHARS") or "120").strip())
