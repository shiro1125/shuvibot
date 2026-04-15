import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Supabase 설정
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 테이블 이름
TABLE_NAME = "user_stats"

def get_user_affinity(user_id, user_name):
    """유저의 친밀도를 조회하고, 없으면 생성합니다."""
    try:
        res = supabase.table(TABLE_NAME).select("affinity").eq("user_id", str(user_id)).execute()
        if res.data:
            return res.data[0]['affinity']
        else:
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

def update_user_affinity(user_id, user_name, amount, reset=False):
    """친밀도와 채팅 횟수를 업데이트하고 업데이트 전/후 점수를 반환합니다."""
    try:
        res = supabase.table(TABLE_NAME).select("affinity, chat_count").eq("user_id", str(user_id)).execute()
        
        if res.data:
            old_affinity = res.data[0].get('affinity', 0)
            old_chats = res.data[0].get('chat_count', 0)
            
            new_affinity = amount if reset else old_affinity + amount
            new_chats = old_chats + 1
            
            supabase.table(TABLE_NAME).update({
                "affinity": new_affinity,
                "chat_count": new_chats,
                "user_name": user_name
            }).eq("user_id", str(user_id)).execute()
            
            return old_affinity, new_affinity
        else:
            new_score = amount
            supabase.table(TABLE_NAME).insert({
                "user_id": str(user_id),
                "user_name": user_name,
                "affinity": new_score,
                "chat_count": 1
            }).execute()
            return 0, new_score
    except Exception as e:
        print(f"❌ 업데이트 에러: {e}")
        return 0, 0

def get_affinity_ranking(limit=30):
    """친밀도 상위 랭킹을 가져옵니다."""
    try:
        res = supabase.table(TABLE_NAME).select("*").order("affinity", desc=True).limit(limit).execute()
        return res.data or []
    except Exception as e:
        print(f"❌ 랭킹 로딩 에러: {e}")
        return []

def get_attitude_guide(affinity):
    """친밀도에 따른 뜌비의 태도 가이드를 반환합니다."""
    if affinity >= 100: return "매우 친근하고 애교 섞인 태도"
    if affinity >= 50: return "친절하고 장난스러운 태도"
    if affinity >= 0: return "기본적인 예의를 지키는 태도"
    return "경계하고 쌀쌀맞은 태도"

def get_memory_from_db(user_name):
    """최근 대화 기억 15개를 불러옵니다."""
    try:
        res = supabase.table("memory").select("*").eq("user_name", user_name).order("created_at", desc=True).limit(15).execute()
        memory_list = res.data or []
        formatted_memory = ""
        for m in reversed(memory_list):
            formatted_memory += f"{m['user_name']}: {m['user_msg']} -> 뜌비: {m['bot_res']}\n"
        return formatted_memory
    except Exception as e:
        print(f"❌ 기억 불러오기 에러: {e}")
        return ""

def save_to_memory(user_name, user_msg, bot_res):
    """대화 내용을 DB에 저장합니다."""
    try:
        supabase.table("memory").insert({
            "user_name": user_name,
            "user_msg": user_msg,
            "bot_res": bot_res
        }).execute()
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")

def get_top_ranker_id():
    """전체 1위 유저의 ID를 가져옵니다."""
    try:
        res = supabase.table(TABLE_NAME).select("user_id").order("affinity", desc=True).limit(1).execute()
        if res.data and len(res.data) > 0:
            return int(res.data[0]['user_id'])
        return None
    except Exception as e:
        print(f"❌ 1위 조회 에러: {e}")
        return None
