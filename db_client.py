# db_client.py
# MODIFIED: Supabase 지연 초기화 분리
from typing import Optional

from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL

_supabase: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    global _supabase
    if _supabase is not None:
        return _supabase

    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    try:
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _supabase
    except Exception as e:
        print(f"❌ Supabase 클라이언트 생성 실패: {e}")
        return None
