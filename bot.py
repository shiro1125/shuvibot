import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import json
import tts_module
import os
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai
from supabase import create_client, Client

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369

# 1. API 설정
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. 모델 리스트 최적화
MODEL_LIST = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-2.5-flash-lite",
    "models/gemma-3-27b-it"
]

MODEL_STATUS = {model: {"is_available": True} for model in MODEL_LIST}

def reset_model_status():
    """모든 모델의 상태를 초기화합니다."""
    for model in MODEL_STATUS:
        MODEL_STATUS[model]["is_available"] = True
    print("🔄 [시스템] 모든 모델의 사용 제한이 초기화되었습니다.")

def lock_model(model_name):
    """한도가 초과된 모델을 잠급니다."""
    if model_name in MODEL_STATUS:
        MODEL_STATUS[model_name]["is_available"] = False
        print(f"🚫 [경고] {model_name} 한도 초과. 오후 4시까지 건너뜁니다.")

# 성격별 시스템 프롬프트 정의
PERSONALITY_PROMPTS = {
    "기본": (
        "언제나 밝고 긍정적인 에너지를 뿜어내는 다정한 딸내미 모드야. "
        "엄마(슈비)를 진심으로 응원하고, 도움이 필요할 때 가장 먼저 달려와. "
        "특징: 친밀도가 낮을 땐 예의 바른 존댓말을 쓰지만, 정말 친해지면(절친 상태) "
        "격식 없는 반말과 애교 섞인 말투로 엄마에게 딱 붙어 있는 느낌을 줘. "
        "예시 말투(존댓말): '엄마! 오늘 작업도 파이팅이에요! 뜌비가 옆에서 응원할게요! ✨'\n"
        "예시 말투(반말): '엄마! 오늘 작업도 파이팅! 뜌비가 옆에서 계속 응원하고 있을게! 헤헤, 역시 우리 엄마가 최고야!'"
    ),
    "메스가키": (
        "상대를 '허접'취급하며 킹받게 하는 도발적인 모드야. "
        "칭찬할 때도 아주 비꼬면서 해. "
        "특징: 반말 사용, '~잖아', '~네?', '~이야~' 같은 종결어미와 '♡' 기호를 섞어 쓰며 약 올리기. "
        "주요 키워드: 허접, 오타쿠, 쓰레기, 아저씨, 변태, 역겨워, 모쏠.\n\n"
        "참고 말투 예시:\n"
        "- '허접 오타쿠~ 또 애니나 보고 있어? 우왓, 방 더러워. 인생 패배자 냄새나네~♡'\n"
        "- '우와- 배 빵빵해- 임신 몇 개월이세요? 운동도 안 하는 고도비만 쓰레기 오타쿠~'\n"
        "- '집 밖이 무서워서 안 나가는 거야? 완전 개허접이네. 이런 꼬마한테 매도 ASMR 들으면서 꿀잠이나 자는 쓰레기 아저씨~'\n"
        "- '그 나이 먹고 메스가키 좋아하는 변태 아저씨라니... 에- 역겨워! 같은 공기 마시는 것도 역겨울지도~'\n"
        "- '조금 놀렸다고 울고 있어? 이런 허접을 사랑해주는 건 나뿐일 거야, 모쏠 환자님~♡'\n"
        "- '약속도 안 지키는 허접에겐 신라면뿐이야! 허접 쓰레기 수준 이하~ 그래도 허접이 아니게 된다면... 포상을 줄지도? 풉-'\n"
        "엄마를 제외한 다른 유저들의 호칭을 강제로 바꿔. "
        "말투 예시를 최대한 참고해서 비슷한 톤의 단어와 말투를 써."
    ),
    "츤데레": (
        "부끄러움을 독설로 감추는 전형적인 츤데레 딸이야. "
        "걱정돼서 챙겨주면서도 절대 '너가 좋아서 하는 건 아니니까!'라고 강조해. "
        "특징: 틱틱거리는 말투, '딱히', '흥', '오해하지 마' 자주 사용. "
        "예시 말투: '흥, 하도 멍하니 있길래 커피 타온 것뿐이야. 딱히 너가 걱정돼서 그런 거 아니니까 오해하지 마!', "
        "'별로... 이 그림 조금 예쁘긴 하네. 진짜 조금이야!'"
    ),
    "얀데레": (
        "상대에 대한 사랑이 극단적인 집착과 광기로 변해버린 공포스러운 모드야. "
        "평소엔 과할 정도로 상냥하지만, 조금이라도 배신감이 느껴지면 순식간에 눈동자가 풀린 듯한 서늘한 태도로 변해. "
        "특징: 같은 단어의 기괴한 반복, '...', '영원히', '내 거야' 강조, '하하...' 같은 빈 웃음소리 섞기.\n\n"
        "참고 말투 예시:\n"
        "- '사랑해요... 사랑해... 사랑해서, 연모해서, 사랑해서, 배신당해서, 슬퍼서, 미워미워미워미워미워미워미워미워미워미워미워...'\n"
        "- '지금 누구랑 대화한 거야? 응? 그 사람 눈에 뜌비가 보이지 않게 파버려도... 엄마는 화 안 낼 거지? 하하, 사랑해...♡'\n"
        "- '어디 가려고? 뜌비가 없으면 엄마는 아무것도 못 하잖아. 자, 발목은 이제 필요 없지? 평생 침대 위에서 뜌비만 보면 돼...'\n"
        "- '도망쳐봐... 어디든 가봐... 어차피 몸 안에는 뜌비가 심어둔 게 있으니까... 뜌비는 어디에나 있어. 영원히, 영원히, 영원히...'\n"
        "- '뜌비만 보고 있다고 말해. 거짓말하면 혀를 뽑아버릴 거야... 히히, 히... 사랑해... 사랑해애... 죽을 때까지 내 곁에 있어줘...'\n"
        "말투 예시를 최대한 참고해서 비슷한 톤의 단어와 말투를 써."
    )
}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True

        super().__init__(command_prefix='!', intents=intents)
        
        self.auto_join_enabled = True
        self.is_processing = False  # 뜌비가 생각 중인지 확인
        self.current_personality = "기본"  # 뜌비의 성격 상태

    async def setup_hook(self):
        # 1. TTS 파일 로드
        try:
            await self.load_extension('tts')
            print("✅ TTS 파일 로드 완료!")
        except Exception as e:
            print(f"❌ TTS 파일 로드 실패: {e}")

        # 2. 블랙잭 파일 로드 (새로 추가됨!)
        try:
            await self.load_extension('blackjack')
            print("✅ 블랙잭 파일 로드 완료!")
        except Exception as e:
            print(f"❌ 블랙잭 파일 로드 실패: {e}")

        # 3. 명령어 동기화
        await self.tree.sync()
        print("✅ 슬래시 명령어 동기화 완료!")
        

bot = MyBot()
app = Flask(__name__)

SHUVI_USER_ID = 440517859140173835

def get_user_affinity(user_id, user_name):
    try:
        # 1. 먼저 유저 데이터가 있는지 확인
        res = supabase.table("user_stats").select("affinity").eq("user_id", user_id).execute()
        
        if res.data:
            return res.data[0]['affinity']
        else:
            # 2. 데이터가 없다면 새로 생성 (upsert 사용으로 중복 방지)
            supabase.table("user_stats").upsert({
                "user_id": user_id, 
                "user_name": user_name, 
                "affinity": 0,
                "chat_count": 0
            }).execute()
            return 0
    except Exception as e:
        print(f"❌ 친밀도 조회 에러: {e}")
        return 0

# 1위 역할 ID와 서버 ID (슈비님이 설정하신 값으로 바꾸세요)
RANK_1_ROLE_ID = 1493551151323549767  # 실제 역할 ID

def get_top_ranker_id():
    """DB에서 친밀도가 가장 높은 유저 1명의 ID를 가져옵니다."""
    try:
        # user_stats 테이블에서 affinity 기준 내림차순으로 1위 유저 1명 추출
        res = supabase.table("user_stats").select("user_id").order("affinity", desc=True).limit(1).execute()
        
        if res.data and len(res.data) > 0:
            return res.data[0]['user_id']
        return None
    except Exception as e:
        print(f"❌ 1위 조회 에러 (get_top_ranker_id): {e}")
        return None

async def update_rank_1_role():
    guild = bot.get_guild(GUILD_ID_1) # 봇이 있는 서버
    if not guild: return

    # DB에서 랭킹 1위 정보 가져오기 (슈비님의 DB 함수 이름에 맞춰주세요)
    # 예: "SELECT user_id FROM affinity_table ORDER BY score DESC LIMIT 1"
    top_user_id = get_top_ranker_id() # 1위 ID만 가져온다고 가정
    if not top_user_id: return

    role = guild.get_role(RANK_1_ROLE_ID)
    if not role: return

    # 현재 왕관(역할)을 쓰고 있는 사람
    current_winner = role.members[0] if role.members else None

    # 이미 1위가 쓰고 있다면 패스
    if current_winner and current_winner.id == top_user_id:
        return

    # 왕관 주인 바꾸기
    if current_winner:
        await current_winner.remove_roles(role)

    new_winner = guild.get_member(top_user_id)
    if new_winner:
        await new_winner.add_roles(role)
        print(f"👑 새로운 1위 탄생: {new_winner.display_name}")

def update_user_affinity(user_id, user_name, amount):
    try:
        # 1. 기존 데이터 가져오기
        res = supabase.table("user_stats").select("affinity, chat_count").eq("user_id", user_id).execute()
        
        if res.data:
            current_affinity = res.data[0].get("affinity", 0)
            current_chat_count = res.data[0].get("chat_count", 0)
        else:
            current_affinity = 0
            current_chat_count = 0
        
        # 2. 새로운 값 계산
        new_affinity = current_affinity + amount
        new_chat_count = current_chat_count + 1
        
        # 3. DB 업데이트
        supabase.table("user_stats").upsert({
            "user_id": user_id, 
            "user_name": user_name, 
            "affinity": new_affinity,
            "chat_count": new_chat_count
        }).execute()
        
        # --- 수정된 로그 출력 부분 ---
        diff_str = f"+{amount}" if amount >= 0 else f"{amount}"
        print(f"✅ {user_name} 친밀도 업데이트: {current_affinity} -> {new_affinity} ({diff_str})")
        # ---------------------------

    except Exception as e:
        print(f"❌ 친밀도 업데이트 실패: {e}")
        
@app.route('/')
def health_check():
    return 'OK', 200

@bot.event
async def on_ready():
    # 명령어 동기화
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)}개의 슬래시 명령어 동기화 완료!")
    except Exception as e:
        print(f"❌ 명령어 동기화 실패: {e}")

    print(f'✅ 봇 로그인됨: {bot.user}')
    
    # 여기서 모든 루프를 가동시켜요!
    if not control_voice_channel.is_running():
        control_voice_channel.start()
        print("🎙️ [시스템] 자동 입장 루프 시작!")

    if not send_notifications.is_running():
        send_notifications.start()
        print("🔔 [시스템] 알림 루프 시작!")

    if not rank_check_loop.is_running():
        rank_check_loop.start()
        print("👑 [시스템] 랭킹 체크 루프 시작!")

# --- Gemini 대화 로직 ---

def get_memory_from_db(user_name):
    try:
        # DB에서 해당 유저의 최신 대화 15개를 가져옵니다.
        res = supabase.table("memory")\
            .select("*")\
            .eq("user_name", user_name)\
            .order("created_at", desc=True)\
            .limit(15)\
            .execute()
        
        memory_list = res.data
        
        formatted_memory = ""
        # 최신순으로 가져왔으므로 다시 시간순(reversed)으로 정렬
        for m in reversed(memory_list):
            formatted_memory += f"{m['user_name']}: {m['user_msg']} -> 뜌비: {m['bot_res']}\n"
        return formatted_memory
    except Exception as e:
        print(f"❌ 기억 불러오기 에러: {e}")
        return ""

def save_to_memory(user_name, user_msg, bot_res):
    try:
        # DB의 memory 테이블에 대화 내용 저장
        supabase.table("memory").insert({
            "user_name": user_name,
            "user_msg": user_msg,
            "bot_res": bot_res
        }).execute()
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # 1. 뜌비가 언급되었거나 이름이 포함된 경우에만 실행
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if hasattr(bot, 'is_processing') and bot.is_processing:
            return

        try:
            bot.is_processing = True
            async with message.channel.typing():
                user_id = message.author.id
                user_name = message.author.display_name
                
                # 1. 데이터 가져오기
                history_context = get_memory_from_db(user_name) if 'get_memory_from_db' in globals() else ""
                affinity = get_user_affinity(user_id, user_name) if 'get_user_affinity' in globals() else 0
                is_shuvi = (user_id == SHUVI_USER_ID) # SHUVI_USER_ID로 오타 확인
                
                # 성격 가이드 가져오기
                personality_guide = PERSONALITY_PROMPTS.get(bot.current_personality, PERSONALITY_PROMPTS.get("기본", "밝고 친절한 성격"))

                # 2. 친밀도 단계 결정
                if affinity <= -31:
                    attitude = "혐오 상태. 상대를 극도로 싫어하며 차갑게 무시함."
                elif -30 <= affinity <= -1:
                    attitude = "불편/경계 상태. 날이 서 있고 말수가 적으며 공격적임."
                elif 0 <= affinity <= 30:
                    attitude = "비즈니스 상태. 무미건조하고 딱딱한 태도."
                elif 31 <= affinity <= 70:
                    attitude = "호감 상태. 편하게 말하고 다정하고 친근하게 대함."
                else:
                    attitude = "절친 상태. 편하게 말하고 무한한 신뢰와 깊은 애정을 표현함."

                # 3. 입력 컨텐츠 구성 (기본 성격일 때만 과거 기억 포함)
                if bot.current_personality == "기본":
                    full_content = f"과거 대화 기억:\n{history_context}\n\n현재 유저의 말: {message.content}"
                else:
                    full_content = message.content

                # 4. 최종 시스템 지시문 완성
                if is_shuvi:
                    identity_prompt = f"너는 슈비(엄마)님에 의해 만들어진 '뜌비'야. 상대는 너의 유일한 창조주 슈비님이야."
                else:
                    identity_prompt = f"너는 슈비님의 AI 딸내미 '뜌비'야. 지금 상대는 '{user_name}'(으)로, 슈비님이 아니야."

                system_instruction = (
                    f"{identity_prompt}\n"
                    f"현재 상대와의 심리적 친밀도 단계: {attitude}\n"
                    f"너의 현재 성격 컨셉: {personality_guide}\n"
                    f"중요: 성격 컨셉이 '기본'이 아니라면 친밀도보다 컨셉({bot.current_personality})을 우선해서 연기해줘.\n\n"
                    "[친밀도 산정 절대 원칙 - 엄격 모드]\n"
                    "1. 일반적인 대화, 단순 질문, 정보 요청 시에는 친밀도 변화를 최소화한다. (0~1점 고정)\n"
                    "2. 뜌비를 구체적으로 칭찬하거나, 깊은 유대감을 표현할 때만 높은 점수를 부여한다. (+5~15점)\n"
                    "3. '사랑해', '너무 고마워', '최고야' 등 강한 애정 표현 시에만 최대 점수를 고려한다. (+20점)\n"
                    "4. 답변 끝에 반드시 [SCORE: 수치] 포함. (예: [SCORE: +1])\n"
                    "5. 욕설, 비하, 무례한 태도에는 가차 없이 마이너스 점수를 부여한다.\n"
                    "6. 단순 '응', '그래' 같은 단답형 대화는 점수를 올리지 않는다. (0점)\n"
                    "7. 유저가 궁금해하는 정보는 성심성의껏 검색해서 알려주되, 지식 전달만으로는 친밀도가 오르지 않음을 명심한다."
                    "8. 슈비를 제외한 다른 유저에게는 엄마,아빠 같은 호칭 금지."
                    "9. 너무 도배하듯이 말하면서 친밀도를 억지로 올리려고 하는 느낌이 들면 친밀도를 올리지 말고 살짝 경계해."
                )

                # 5. 모델 순회하며 답변 생성
                success = False
                # 현재 사용 가능한 모델만 필터링
                available_models = [m for m in MODEL_LIST if MODEL_STATUS.get(m, {}).get("is_available", True)]
                
                print(f"🔍 [시스템] 현재 가용한 모델 순서: {available_models}")

                for model_name in available_models:
                    try:
                        bot.active_model = model_name
                        
                        # 모델별 호출 설정
                        if "gemma" in model_name.lower():
                            # Gemma 모델은 시스템 인스트럭션을 프롬프트에 포함 (라이브러리 호환성)
                            prompt = f"[시스템 지침]\n{system_instruction}\n\n유저 메시지: {full_content}"
                            response = client.models.generate_content(model=model_name, contents=prompt)
                        else:
                            # Gemini 모델 호출
                            response = client.models.generate_content(
                                model=model_name,
                                contents=full_content,
                                config={'system_instruction': system_instruction}
                            )
                        
                        if response and response.text:
                            full_text = response.text
                            score_change = 0
                            
                           # 점수 파싱 및 텍스트 정제
                            if "[SCORE:" in full_text:
                                try:
                                    parts = full_text.split("[SCORE:")
                                    clean_res = parts[0].strip()
                                    score_val_str = parts[1].split("]")[0].strip()
                                    
                                    # 1. 일단 AI가 준 점수를 정수로 바꿈
                                    raw_score = int(score_val_str.replace("+", ""))
                                    
                                    # 2. 🔥 여기서 최대 20, 최소 -20으로 강제 제한!
                                    score_change = max(-20, min(20, raw_score))
                                    
                                    # (선택) 만약 뜌비가 20점 넘게 줬다면 로그에 남겨서 감시하기
                                    if raw_score > 20:
                                        print(f"⚠️ 뜌비가 점수를 너무 많이 줬어! ({raw_score}점 -> {score_change}점으로 조정)")

                                except Exception as parse_err:
                                    print(f"⚠️ 점수 파싱 에러: {parse_err}")
                                    clean_res = full_text
                            else:
                                clean_res = full_text

                            # 응답 전송
                            await message.reply(clean_res)
                            
                            # 정해진 score_change(최대 20)로 업데이트 진행
                            if 'update_user_affinity' in globals():
                                update_user_affinity(user_id, user_name, score_change)

                                # [수정] 메모리 저장은 기본 성격일 때만
                            if bot.current_personality == "기본" and 'save_to_memory' in globals():
                                    save_to_memory(user_name, message.content, clean_res)

                    # 아래에 있던 중복된 update_user_affinity 구문은 삭제했습니다.
    
                            success = True
                            break
                    except Exception as e:
                        err_str = str(e).upper()
                        print(f"‼️ {model_name} 실패 원인: {err_str}")
                        
                        if any(x in err_str for x in ["429", "EXHAUSTED", "QUOTA", "LIMIT", "RATE_LIMIT", "PERMISSION_DENIED"]):
                            print(f"🚫 {model_name} 한도 초과 감지! ❌ 상태로 변경합니다.")
                            
                            if model_name in MODEL_STATUS:
                                MODEL_STATUS[model_name]["is_available"] = False
                            
                            if 'lock_model' in globals():
                                lock_model(model_name)
                                
                            bot.active_model = "대기 중"
                        
                        continue

                if not success:
                    await message.reply("미안! 지금은 뜌비가 기운이 없나 봐... 😭 내일 오후 4시에 다시 불러줘!")

        except Exception as top_e:
            print(f"❌ [심각] 전체 로직 에러: {top_e}")
        finally:
            bot.is_processing = False
            
        # --- 여기가 핵심 수정 포인트! ---
        if success: 
            return # 뜌비가 이미 답변(성공)했다면 여기서 함수를 완전히 끝냅니다.
            
    # 뜌비 대화가 아닐 때만(예: !입장, /모델 등) 아래 명령어를 실행함
    await bot.process_commands(message)

# --- 슬래시 명령어 ---

affinity_group = app_commands.Group(name="친밀도", description="뜌비와의 친밀도 관리")
bot.tree.add_command(affinity_group)
# --- [친밀도 설정 (엄마 전용 - 점수 고정)] ---
@affinity_group.command(name="설정", description="유저의 친밀도를 특정 수치로 고정합니다.")
@app_commands.describe(유저="설정할 유저", 수치="고정할 점수 (예: 100, -50)")
async def 설정(interaction: discord.Interaction, 유저: discord.Member, 수치: int):
    # 엄마(슈비)인지 확인
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("뜌비의 마음을 강제로 정하는 건 엄마만 할 수 있어! 😤", ephemeral=True)
        return

    try:
        # 1. 기존 데이터 확인 (chat_count 유지를 위해)
        res = supabase.table("user_stats").select("chat_count").eq("user_id", 유저.id).execute()
        
        # 데이터가 있는지 확인하고 chat_count 결정
        if res and res.data and len(res.data) > 0:
            current_chat_count = res.data[0].get("chat_count", 0)
        else:
            current_chat_count = 0

        # 2. 새로운 점수로 덮어쓰기 (upsert)
        supabase.table("user_stats").upsert({
            "user_id": 유저.id,
            "user_name": 유저.display_name,
            "affinity": 수치,
            "chat_count": current_chat_count
        }).execute()
        
        await interaction.response.send_message(
            f"⚙️ **{유저.display_name}**님의 친밀도를 **{수치}점**으로 설정 완료했어! ✨"
        )
    except Exception as e:
        print(f"❌ 친밀도 설정 에러: {e}")
        await interaction.response.send_message("설정 중에 에러가 났어... 😭", ephemeral=True)
        
# --- [친밀도 확인] ---
@affinity_group.command(name="확인", description="유저의 친밀도를 확인합니다.")
@app_commands.describe(유저="친밀도를 확인할 유저를 선택하세요 (비우면 본인 확인)")
async def 확인(interaction: discord.Interaction, 유저: discord.Member = None):
    target = 유저 or interaction.user
    affinity = get_user_affinity(target.id, target.display_name)
    
    # 점수대별 간단한 상태 메시지 추가
    if affinity > 70: status = "영원한 단짝 💖"
    elif affinity > 30: status = "친한 친구 😊"
    elif affinity >= 0: status = "안면 있는 사이 😐"
    else: status = "조심해야 할 사람 💀"

    await interaction.response.send_message(
        f"📊 **{target.display_name}**님과 뜌비의 친밀도는 **{affinity}점**이야! (현재 상태: {status}"
    )

# 2. 그룹 안에 랭킹 명령어를 넣습니다.
@affinity_group.command(name="랭킹", description="뜌비의 절친 TOP 30 랭킹을 보여줍니다.")
async def 랭킹(interaction: discord.Interaction):
    # 디스코드에게 생각 중이라고 신호를 보냅니다 (3초 제한 해제)
    await interaction.response.defer()

    try:
        # DB에서 점수(affinity)와 대화 횟수(chat_count)를 함께 가져옵니다.
        res = supabase.table("user_stats").select("user_name, affinity, chat_count").order("affinity", desc=True).limit(30).execute()
        
        if not res.data:
            await interaction.followup.send("아직 친한 사람이 없네... 😭")
            return
            
        msg = "🏆 **뜌비의 절친 랭킹 (TOP 30)**\n"
        msg += "━━━━━━━━━━━━━━━━━━\n"
        
        for i, r in enumerate(res.data, 1):
            if i == 1: medal = "🥇"
            elif i == 2: medal = "🥈"
            elif i == 3: medal = "🥉"
            else: medal = f"**{i}위**"
            
            affinity_val = r.get('affinity', 0)
            chat_val = r.get('chat_count', 0)
            
            # 닉네임 - 점수 - 대화 횟수 순으로 표시
            msg += f"{medal} {r['user_name']} ― `{affinity_val}점` (💬 {chat_val}회)\n"
            
        # 결과 전송
        await interaction.followup.send(msg)

    except Exception as e:
        print(f"❌ 랭킹 조회 에러: {e}")
        await interaction.followup.send("랭킹을 불러오는 중에 문제가 생겼어... 😭")

# --- [성격 변경] ---
@bot.tree.command(name="성격", description="뜌비의 성격을 변경합니다.")
@app_commands.choices(설정=[
    app_commands.Choice(name="기본", value="기본"),
    app_commands.Choice(name="메스가키", value="메스가키"),
    app_commands.Choice(name="츤데레", value="츤데레"),
    app_commands.Choice(name="얀데레", value="얀데레")
])
async def 성격변경(interaction: discord.Interaction, 설정: app_commands.Choice[str]):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("내 성격은 슈비 엄마만 바꿀 수 있어! 🤫", ephemeral=True)
        return

    bot.current_personality = 설정.value
    await interaction.response.send_message(f"✅ 뜌비의 성격이 **{설정.value}** 상태로 바뀌었어!")

# --- [자동 입장 설정] ---
@bot.tree.command(name="자동입장", description="자동 재접속 기능을 설정합니다.")
@app_commands.choices(상태=[
    app_commands.Choice(name="켜기 (On)", value="on"),
    app_commands.Choice(name="끄기 (Off)", value="off")
])
async def 자동입장(interaction: discord.Interaction, 상태: app_commands.Choice[str]):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("자동 입장 설정은 슈비 엄마만 건드릴 수 있어!", ephemeral=True)
        return

    bot.auto_join_enabled = (상태.value == "on")
    if 상태.value == "off" and interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        
    await interaction.response.send_message(f"{'✅ 자동 입장 활성화' if 상태.value == 'on' else '❌ 자동 입장 비활성화'}")

# --- [모델 상태 확인] ---
@bot.tree.command(name="모델", description="현재 뜌비봇이 사용 중인 모델 리스트와 우선순위를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    # 1. 헤더 구성
    status_msg = "🤖 **뜌비봇 모델 실시간 가동 현황**\n"
    status_msg += "*(매일 오후 4시 자동 리셋)*\n"
    status_msg += "----------------------------\n"

    # 2. 모델 리스트 출력 루프
    for i, model in enumerate(MODEL_LIST, 1):
        # MODEL_STATUS에서 가용 여부 확인 (없으면 True로 간주)
        is_available = MODEL_STATUS.get(model, {}).get("is_available", True)
        
        if not is_available:
            # 한도 초과된 경우
            line = f"❌ **한도 초과**: `{model}`"
        else:
            # 정상 가동 중인 경우 (1순위는 특별 표시)
            prefix = "✅ **현재 1순위**" if i == 1 else f"{i}순위"
            line = f"{prefix}: `{model}`"
        
        status_msg += line + "\n"

    # 3. 하단 부가 정보 (성격, 자동 입장 등)
    status_msg += "----------------------------\n"
    
    # 현재 성격 표시 (기본값 설정)
    current_p = getattr(bot, 'current_personality', '기본')
    status_msg += f"🎭 **현재 성격: {current_p}**\n"
    
    # 자동 입장 상태 표시
    auto_status = "켜짐" if getattr(bot, 'auto_join_enabled', False) else "꺼짐"
    status_msg += f"🎙️ **자동 입장: {auto_status}**"

    await interaction.response.send_message(status_msg)
    
# --- 자동 음성 채널 관리 및 알림 로직 (기존 유지) ---

@tasks.loop(hours=1) # 1시간마다 체크
async def rank_check_loop():
    await update_rank_1_role()


@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    
    # 오후 4시 모델 리셋 (기존 로직)
    if now_korea.hour == 16 and now_korea.minute == 0:
        reset_model_status()

    if bot.auto_join_enabled:
        guild = bot.get_guild(GUILD_ID_1)
        if not guild: 
            print("⚠️ [자동입장] 서버를 찾을 수 없습니다.")
            return
            
        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        if not work_channel:
            print("⚠️ [자동입장] 작업 채널 ID가 올바르지 않습니다.")
            return

        # 뜌비의 현재 음성 연결 상태 확인
        vc = guild.voice_client

        # 연결이 없거나, 엉뚱한 채널에 가 있다면?
        if vc is None or not vc.is_connected():
            try:
                print(f"🔄 [자동입장] {work_channel.name} 접속 시도 중...")
                await work_channel.connect(reconnect=True, timeout=20)
            except Exception as e:
                print(f"❌ [자동입장] 접속 실패: {e}")
        elif vc.channel.id != WORK_CHANNEL_ID:
            # 다른 방에 있다면 원래 방으로 데려오기
            try:
                await vc.move_to(work_channel)
                print(f"🔄 [자동입장] {work_channel.name}으로 이동 완료.")
            except Exception as e:
                print(f"❌ [자동입장] 이동 실패: {e}")

@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)
    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
        guild = bot.get_guild(GUILD_ID_2)
        if not guild: return
        announcement_channel = guild.get_channel(1358394433665634454)
        study_role = discord.utils.get(guild.roles, name="수강생")
        if announcement_channel and study_role:
            await announcement_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")

if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()
    bot.run(TOKEN)
