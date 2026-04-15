import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Supabase 설정
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 테이블 이름을 user_stats로 통일
TABLE_NAME = "user_stats"

def get_user_affinity(user_id, display_name):
    """유저의 친밀도 점수를 가져옵니다."""
    try:
        # 필드명: user_id, user_name, affinity
        response = supabase.table(TABLE_NAME).select("*").eq("user_id", str(user_id)).execute()
        if response.data:
            return response.data[0]['affinity']
        else:
            # 신규 유저 등록 (user_stats 구조에 맞춤)
            supabase.table(TABLE_NAME).insert({
                "user_id": str(user_id),
                "user_name": display_name,
                "affinity": 0,
                "chat_count": 0
            }).execute()
            return 0
    except Exception as e:
        print(f"❌ 친밀도 로드 에러: {e}")
        return 0

def update_user_affinity(user_id, display_name, score_change, reset=False):
    """친밀도 점수 및 채팅 횟수를 업데이트합니다."""
    try:
        if reset:
            new_score = score_change
        else:
            current_score = get_user_affinity(user_id, display_name)
            new_score = current_score + score_change
        
        # 채팅 횟수도 1씩 증가시키도록 처리 (필요 시)
        supabase.table(TABLE_NAME).update({
            "affinity": new_score,
            "user_name": display_name
        }).eq("user_id", str(user_id)).execute()
        
        # 채팅 횟수 증가 (on_message에서 호출될 때)
        if not reset:
             supabase.rpc('increment_chat_count', {'row_id': str(user_id)}).execute()
             
        return new_score
    except Exception as e:
        print(f"❌ 친밀도 업데이트 에러: {e}")
        return 0

def get_attitude_guide(affinity):
    """친밀도 점수에 따른 뜌비의 태도 가이드를 반환합니다."""
    if affinity >= 1000: # 캡처본에 1000점 넘는 분들이 계셔서 기준을 높였습니다.
        return "상대방을 매우 신뢰하고 사랑스럽게 대함. 애교가 많음."
    elif affinity >= 500:
        return "친근하고 장난을 자주 침. 호의적임."
    elif affinity >= 0:
        return "예의는 차리지만 약간의 거리가 있음. 평범한 말투."
    else:
        return "상대방을 경계하거나 쌀쌀맞게 대함. 무관심하거나 독설을 함."

def get_memory_from_db(display_name):
    """유저와의 최근 대화 기억을 가져옵니다."""
    try:
        response = supabase.table("memory") \
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
        supabase.table("memory").insert({
            "display_name": display_name,
            "memory_text": memory_text[:200]
        }).execute()
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")

def get_top_ranker_id():
    """친밀도 1위 유저의 ID를 가져옵니다 (슈비 제외)."""
    try:
        response = supabase.table(TABLE_NAME) \
            .select("user_id") \
            .neq("user_id", "440517859140173835") \
            .order("affinity", descending=True) \
            .limit(1) \
            .execute()
        if response.data:
            return int(response.data[0]['user_id'])
        return None
    except Exception as e:
        print(f"❌ 1위 로드 에러: {e}")
        return None

def get_affinity_ranking(limit=30):
    """친밀도 상위 유저 리스트를 가져옵니다."""
    try:
        response = supabase.table(TABLE_NAME) \
            .select("user_name, affinity, chat_count") \
            .order("affinity", descending=True) \
            .limit(limit) \
            .execute()
        return response.data
    except Exception as e:
        print(f"❌ 랭킹 로드 에러: {e}")
        return []
