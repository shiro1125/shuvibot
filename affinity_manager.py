import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Supabase 설정
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_affinity(user_id, display_name):
    """유저의 친밀도 점수를 가져오거나 없으면 새로 생성합니다."""
    try:
        response = supabase.table("user_affinity").select("*").eq("user_id", str(user_id)).execute()
        if response.data:
            return response.data[0]['affinity_score']
        else:
            # 신규 유저 등록
            supabase.table("user_affinity").insert({
                "user_id": str(user_id),
                "display_name": display_name,
                "affinity_score": 0
            }).execute()
            return 0
    except Exception as e:
        print(f"❌ 친밀도 로드 에러: {e}")
        return 0

def update_user_affinity(user_id, display_name, score_change, reset=False):
    """친밀도 점수를 업데이트합니다. reset=True일 경우 해당 점수로 고정합니다."""
    try:
        if reset:
            new_score = score_change
        else:
            current_score = get_user_affinity(user_id, display_name)
            new_score = current_score + score_change
        
        supabase.table("user_affinity").update({
            "affinity_score": new_score,
            "display_name": display_name  # 닉네임 변경 반영
        }).eq("user_id", str(user_id)).execute()
        return new_score
    except Exception as e:
        print(f"❌ 친밀도 업데이트 에러: {e}")
        return 0

def get_attitude_guide(affinity):
    """친밀도 점수에 따른 뜌비의 태도 가이드를 반환합니다."""
    if affinity >= 70:
        return "상대방을 매우 신뢰하고 사랑스럽게 대함. 애교가 많음."
    elif affinity >= 30:
        return "친근하고 장난을 자주 침. 호의적임."
    elif affinity >= 0:
        return "예의는 차리지만 약간의 거리가 있음. 평범한 말투."
    else:
        return "상대방을 경계하거나 쌀쌀맞게 대함. 무관심하거나 독설을 함."

def get_memory_from_db(display_name):
    """유저와의 최근 대화 기억을 가져옵니다."""
    try:
        response = supabase.table("user_memory") \
            .select("memory_text") \
            .eq("display_name", display_name) \
            .order("created_at", descending=True) \
            .limit(3) \
            .execute()
        if response.data:
            return "\n".join([row['memory_text'] for row in response.data])
        return ""
    except Exception as e:
        print(f"❌ 기억 로드 에러: {e}")
        return ""

def save_to_memory(display_name, user_msg, bot_res):
    """대화 내용을 요약하여 기억 저장소에 저장합니다."""
    try:
        memory_text = f"유저: {user_msg} / 뜌비: {bot_res}"
        supabase.table("user_memory").insert({
            "display_name": display_name,
            "memory_text": memory_text[:200]  # 너무 길지 않게 제한
        }).execute()
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")

def get_top_ranker_id():
    """친밀도 1위 유저의 ID를 가져옵니다 (슈비 제외)."""
    try:
        # 슈비님 ID(440517859140173835) 제외하고 1위 추출
        response = supabase.table("user_affinity") \
            .select("user_id") \
            .neq("user_id", "440517859140173835") \
            .order("affinity_score", descending=True) \
            .limit(1) \
            .execute()
        if response.data:
            return int(response.data[0]['user_id'])
        return None
    except Exception as e:
        print(f"❌ 1위 로드 에러: {e}")
        return None

def get_affinity_ranking(limit=30):
    """친밀도 상위 유저 리스트를 가져옵니다 (ImportError 해결용)."""
    try:
        response = supabase.table("user_affinity") \
            .select("display_name, affinity_score") \
            .order("affinity_score", descending=True) \
            .limit(limit) \
            .execute()
        return response.data
    except Exception as e:
        print(f"❌ 랭킹 로드 에러: {e}")
        return []
