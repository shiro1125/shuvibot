import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Supabase 설정
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 테이블 이름 (bot.py 기준)
TABLE_NAME = "user_stats"

def get_user_affinity(user_id, user_name):
    """bot.py의 로직을 그대로 유지한 친밀도 조회 함수"""
    try:
        res = supabase.table(TABLE_NAME).select("affinity").eq("user_id", str(user_id)).execute()
        if res.data:
            return res.data[0]['affinity']
        else:
            # 신규 유저 등록
            supabase.table(TABLE_NAME).insert({
                "user_id": str(user_id),
                "user_name": user_name,
                "affinity": 0,
                "chat_count": 0
            }).execute()
            return 0
    except Exception as e:
        print(f"❌ 친밀도 조회 에러: {e}")
        return 0

def update_user_affinity(user_id, user_name, amount):
    """bot.py의 로직을 그대로 유지한 친밀도 업데이트 함수"""
    try:
        res = supabase.table(TABLE_NAME).select("affinity, chat_count").eq("user_id", str(user_id)).execute()
        
        if res.data:
            current_affinity = res.data[0].get("affinity", 0)
            current_chat_count = res.data[0].get("chat_count", 0)
        else:
            current_affinity = 0
            current_chat_count = 0

        new_affinity = current_affinity + amount
        new_chat_count = current_chat_count + 1

        supabase.table(TABLE_NAME).upsert({
            "user_id": str(user_id),
            "user_name": user_name,
            "affinity": new_affinity,
            "chat_count": new_chat_count
        }).execute()
        
        return new_affinity
    except Exception as e:
        print(f"❌ 친밀도 업데이트 실패: {e}")
        return 0

def get_attitude_guide(affinity):
    """bot.py 파일 184~194행에 정의된 기준을 그대로 적용"""
    if affinity <= -31:
        return "혐오 상태. 상대를 극도로 싫어하며 차갑게 무시함."
    elif -30 <= affinity <= -1:
        return "불편/경계 상태. 날이 서 있고 말수가 적으며 공격적임."
    elif 0 <= affinity <= 30:
        return "비즈니스 상태. 무미건조하고 딱딱한 태도."
    elif 31 <= affinity <= 70:
        return "호감 상태. 편하게 말하고 다정하고 친근하게 대함."
    else:
        return "절친 상태. 편하게 말하고 무한한 신뢰와 깊은 애정을 표현함."

def get_memory_from_db(user_name):
    """bot.py에서 임포트 에러가 났던 바로 그 함수입니다!"""
    try:
        res = (
            supabase.table("memory")
            .select("*")
            .eq("user_name", user_name)
            .order("created_at", desc=True)
            .limit(15)
            .execute()
        )
        memory_list = res.data or []
        formatted_memory = ""
        for m in reversed(memory_list):
            formatted_memory += f"{m['user_name']}: {m['user_msg']} -> 뜌비: {m['bot_res']}\n"
        return formatted_memory
    except Exception as e:
        print(f"❌ 기억 불러오기 에러: {e}")
        return ""

def save_to_memory(user_name, user_msg, bot_res):
    """대화 내용을 저장하는 함수"""
    try:
        supabase.table("memory").insert({
            "user_name": user_name,
            "user_msg": user_msg,
            "bot_res": bot_res
        }).execute()
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")

def get_top_ranker_id():
    """슈비를 포함하여 1위를 조회합니다."""
    try:
        res = supabase.table(TABLE_NAME).select("user_id").order("affinity", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]['user_id']
        return None
    except Exception as e:
        print(f"❌ 1위 조회 에러: {e}")
        return None

def get_affinity_ranking(limit=30):
    """랭킹 리스트를 가져오는 함수"""
    try:
        res = (
            supabase.table(TABLE_NAME)
            .select("user_name, affinity, chat_count")
            .order("affinity", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"❌ 랭킹 조회 에러: {e}")
        return []
