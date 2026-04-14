import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import json
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
        "- '약속도 안 지키는 허접에겐 신라면뿐이야! 허접 쓰레기 수준 이하~ 그래도 허접이 아니게 된다면... 포상을 줄지도? 풉-'"
    ),
    "츤데레": (
        "부끄러움을 독설로 감추는 전형적인 츤데레 딸이야. "
        "걱정돼서 챙겨주면서도 절대 '너가 좋아서 하는 건 아니니까!'라고 강조해. "
        "특징: 틱틱거리는 말투, '딱히', '흥', '오해하지 마' 자주 사용. "
        "예시 말투: '흥, 하도 멍하니 있길래 커피 타온 것뿐이야. 딱히 너가 걱정돼서 그런 거 아니니까 오해하지 마!', '별로... 이 그림 조금 예쁘긴 하네. 진짜 조금이야!'"
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
        "- '뜌비만 보고 있다고 말해. 거짓말하면 혀를 뽑아버릴 거야... 히히, 히... 사랑해... 사랑해애... 죽을 때까지 내 곁에 있어줘...'"
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
        self.is_processing = False  # 뜌비가 생각 중인지 확인 (최적화 핵심!)
        self.active_model = "대기 중"
        self.current_personality = "기본"  # 뜌비의 성격 상태

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ 슬래시 명령어 동기화 완료!")

bot = MyBot()
app = Flask(__name__)
def get_user_affinity(user_id, user_name):
    try:
        # 최신 생성 시간 순으로 1개만 가져옴
        res = supabase.table("user_stats").select("affinity").eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
        
        if res.data:
            return res.data[0]['affinity']
        else:
            # 기록이 없으면 신규 생성 (0점)
            supabase.table("user_stats").insert({"user_id": user_id, "user_name": user_name, "affinity": 0}).execute()
            return 0
    except Exception as e:
        print(f"❌ 친밀도 조회 에러: {e}")
        return 0

def update_user_affinity(user_id, user_name, amount):
    try:
        res = supabase.table("user_stats").select("affinity, chat_count").eq("user_id", user_id).execute()
        
        # 값이 None일 경우를 대비해 0으로 확실히 초기화
        current_affinity = 0
        current_chat_count = 0
        
        if res.data:
            # .get(key, 0)을 써도 실제 DB에 null이 들어있으면 None이 나올 수 있어요.
            # 그래서 'or 0'을 붙여주는 게 가장 안전해요!
            current_affinity = res.data[0].get("affinity") or 0
            current_chat_count = res.data[0].get("chat_count") or 0
        
        new_affinity = current_affinity + amount
        new_chat_count = current_chat_count + 1
        
        supabase.table("user_stats").upsert({
            "user_id": user_id, 
            "user_name": user_name, 
            "affinity": new_affinity,
            "chat_count": new_chat_count
        }).execute()
        
        print(f"✅ {user_name}님 업데이트: {current_affinity}점->{new_affinity}점 | {current_chat_count}회->{new_chat_count}회")
        
    except Exception as e:
        print(f"❌ 친밀도 및 횟수 업데이트 에러: {e}")
		
@app.route('/')
def health_check():
    return 'OK', 200

@bot.event
async def on_ready():
    # 봇이 켜지자마자 서버에 슬래시 명령어를 최신화합니다.
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)}개의 슬래시 명령어 동기화 완료!")
    except Exception as e:
        print(f"❌ 명령어 동기화 실패: {e}")

    print(f'✅ 봇 로그인됨: {bot.user}')
    
    if not control_voice_channel.is_running():
        control_voice_channel.start()
    if not send_notifications.is_running():
        send_notifications.start()

# --- Gemini 대화 로직 ---
SHUVI_USER_ID = 440517859140173835
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

    # 뜌비가 언급되었거나 이름이 포함된 경우
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        
        if bot.is_processing:
            return

        try:
            bot.is_processing = True # 방패 가동
            async with message.channel.typing():
                user_id = message.author.id
                user_name = message.author.display_name
                
                # 2. 이제 user_name을 아니까 기억 가져오기
                history_context = get_memory_from_db(user_name)
                
                # 3. 최신 친밀도 조회
                affinity = get_user_affinity(user_id, user_name)
                
                is_shuvi = (user_id == SHUVI_USER_ID)
                personality_guide = PERSONALITY_PROMPTS.get(bot.current_personality, PERSONALITY_PROMPTS["기본"])

# [슈비님 로직 수정] 0점 기준 친밀도 단계 설정 (스페이스 정렬 완료)
                if affinity <= -31:
                    attitude = "혐오 상태. 상대를 극도로 싫어하며 차갑게 무시함."
                elif -30 <= affinity <= -1:
                    attitude = "불편/경계 상태. 날이 서 있고 말수가 적으며 공격적임. 하지만 칭찬하거나 사과하면 받아줌."
                elif 0 <= affinity <= 30:
                    attitude = "비즈니스 상태. 감정 없는 무미건조하고 딱딱한 태도."
                elif 31 <= affinity <= 70:
                    attitude = "호감 상태. 다정하고 친근하게 대함."
                else:
                    attitude = "절친 상태. 무한한 신뢰와 깊은 애정을 표현함."

                # 2. 시스템 지침 설정
                if is_shuvi:
                    system_instruction = (
                        f"너는 슈비(엄마)님에 의해 만들어진 '뜌비'야. 상대는 너의 창조주 슈비님이야.\n"
                        f"현재 엄마와의 심리적 친밀도 단계: {attitude}\n"
                        f"최근 대화 기록:\n{history_context}\n"
                        f"너의 성격 컨셉: {personality_guide}\n"
                        f"중요: 현재의 심리 상태 지침에 맞춰 말투를 강력하게 조절해줘."
                    )
                else:
                    system_instruction = (
                        f"너는 슈비님의 AI 딸내미 '뜌비'야. 지금 상대는 '{user_name}'이야.\n"
                        f"현재 이 유저와의 심리적 친밀도 단계: {attitude}\n"
                        f"최근 대화 기록:\n{history_context}\n"
                        f"너의 현재 성격 컨셉은 '{bot.current_personality}'이야."
						f"중요: 현재의 심리 상태 지침에 맞춰 말투를 강력하게 조절해줘. 성격 컨셉이 기본상태가 아니라면 친밀도보다 컨셉을 좀 더 중요시하고 말투를 강하게 써줘."
                    )

                system_instruction += (
    "\n\n[친밀도 규칙]"
    "\n1. 모든 답변 끝에 반드시 '[SCORE: 수치]'를 포함한다."
    "\n2. 이번 대화가 즐겁거나 좋은말이면 +1~20, 평범했다면 0, 불쾌했다면 -1~-20을 부여한다."
    "\n3. 한 번에 ±20를 초과하는 수치는 절대 사용하지 않는다."
    "\n4. SCORE 수치는 현재 점수가 아니라 '변동값'임을 명심한다."
)

                # 3. 모델 순회하며 답변 생성
                success = False
                last_error = ""

                # [수정] 가동 가능한 모델만 필터링해서 시도합니다.
                available_models = [m for m in MODEL_LIST if MODEL_STATUS[m]["is_available"]]

                for model_name in available_models:
                    try:
                        bot.active_model = model_name
                        
                        # [최적화 2] Gemma 모델 호환성 처리
                        if "gemma" in model_name:
                            full_content = f"[시스템 지침]\n{system_instruction}\n\n유저 메시지: {message.content}"
                            response = client.models.generate_content(
                                model=model_name,
                                contents=full_content
                            )
                        else:
                            # Gemini 모델 기본 처리
                            response = client.models.generate_content(
                                model=model_name,
                                contents=message.content,
                                config={'system_instruction': system_instruction}
                            )
                        
                        if response and response.text:
                            full_text = response.text
                            score_change = 0 # 기본 변동값 초기화
                            
                            # [슈비님 로직] SCORE 파싱
                            if "[SCORE:" in full_text:
                                try:
                                    parts = full_text.split("[SCORE:")
                                    clean_res = parts[0].strip()
                                    score_val = parts[1].split("]")[0].strip()
                                    score_change = int(score_val)
                                except:
                                    clean_res = full_text
                            else:
                                clean_res = full_text

                            # 답변 출력 및 데이터 저장
                            await message.reply(clean_res)
                            save_to_memory(user_name, message.content, clean_res)
                            update_user_affinity(user_id, user_name, score_change)
                            
                            success = True
                            break # 답변 성공 시 루프 종료

                    except Exception as e:
                        last_error = str(e).upper()
                        
                        # [핵심 추가] 429(Quota Exceeded) 에러 발생 시 해당 모델을 잠급니다.
                        if any(x in last_error for x in ["429", "EXHAUSTED", "QUOTA"]):
                            lock_model(model_name)
                        
                        print(f"⚠️ {model_name} 실패, 다음 시도... (사유: {last_error})")
                        continue

                # 4. 모든 모델 실패 시 처리
                if not success:
                    bot.active_model = "전체 한도 초과"
                    await message.reply("미안! 지금은 기운이 없어... 나중에 다시 올게! 😭")

        finally:
            # [최적화 3] 성공하든 실패하든 방패 해제
            bot.is_processing = False
            if bot.active_model != "전체 한도 초과":
                bot.active_model = "대기 중"

    await bot.process_commands(message)


# --- 슬래시 명령어 ---

affinity_group = app_commands.Group(name="친밀도", description="뜌비와의 친밀도 관리")
bot.tree.add_command(affinity_group)

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
        f"📊 **{target.display_name}**님과 뜌비의 친밀도는 **{affinity}점**이야! (현재 상태: {status})"
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
@bot.tree.command(name="모델", description="현재 뜌비봇의 모델 상태를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("뜌비의 내부 상태는 슈비 엄마만 볼 수 있어! 🤫", ephemeral=True)
        return

    status_msg = "🤖 **뜌비봇 모델 실시간 가동 현황**\n"
    status_msg += "*(매일 오후 4시 자동 리셋)*\n"
    status_msg += "━━━━━━━━━━━━━━━━━━\n"
    
    for i, model in enumerate(MODEL_LIST, 1):
        info = MODEL_STATUS[model]
        if not info["is_available"]:
            state = "❌ **한도 초과**"
        elif model == bot.active_model:
            state = "🔥 **작동 중**"
        else:
            state = f"{i}순위"
        status_msg += f"{state}: `{model}`\n"
            
    status_msg += f"━━━━━━━━━━━━━━━━━━\n🎭 현재 성격: **{bot.current_personality}**"
    status_msg += f"\n🎙️ 자동 입장: **{'켜짐' if bot.auto_join_enabled else '꺼짐'}**"
    
    await interaction.response.send_message(status_msg)
	
# --- 자동 음성 채널 관리 및 알림 로직 (기존 유지) ---

@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    
    # [추가된 부분] 오후 4시 0분에 모델 상태 리셋
    if now_korea.hour == 16 and now_korea.minute == 0:
        reset_model_status()

    # --- 기존 음성 채널 관리 로직 ---
    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return
    
    if bot.auto_join_enabled:
        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        if work_channel:
            voice = guild.voice_client
            if voice is None or not voice.is_connected():
                try:
                    if voice: await voice.disconnect(force=True)
                    await asyncio.sleep(1)
                    await work_channel.connect(reconnect=True, timeout=15)
                except Exception: pass

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
