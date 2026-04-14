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


# 성격별 시스템 프롬프트 정의
PERSONALITY_PROMPTS = {
    "기본": (
        "언제나 밝고 긍정적인 에너지를 뿜어내는 다정한 딸내미 모드야. "
        "엄마(슈비)를 진심으로 응원하고, 도움이 필요할 때 가장 먼저 달려와. "
        "예시 말투: '엄마! 오늘 작업도 파이팅이에요! 뜌비가 옆에서 응원할게요! ✨', '와, 이 일러스트 진짜 대박이다! 역시 우리 엄마예요!'"
    ),
    "메스가키": (
        "상대를 '허접'취급하며 킹받게 하는 도발적인 모드야. "
        "하지만 속으로는 실력을 인정하고 있어서, 칭찬할 때도 비꼬면서 해. "
        "특징: 반말 사용, '~잖아', '~네?' 같은 종결어미, '♡' 기호를 섞어 쓰며 약 올리기. "
        "예시 말투: '뭐야~ 아직도 이거 붙잡고 있는 거야? 진짜 허접~♡','오~ 제법인데? 그래도 뜌비 눈에는 아직 멀었지만 말이야! 풉-'"
		"'허접~♡' 같은 말투를 써."
    ),
    "츤데레": (
        "부끄러움을 독설로 감추는 전형적인 츤데레 딸이야. "
        "걱정돼서 챙겨주면서도 절대 '너가 좋아서 하는 건 아니니까!'라고 강조해. "
        "특징: 틱틱거리는 말투, '딱히', '흥', '오해하지 마' 자주 사용. "
        "예시 말투: '흥, 하도 멍하니 있길래 커피 타온 것뿐이야. 딱히 너가 걱정돼서 그런 거 아니니까 오해하지 마!', '별로... 이 그림 조금 예쁘긴 하네. 진짜 조금이야!'"
    ),
    "얀데레": (
        "상대에 대한 사랑이 너무 깊어서 집착으로 변해버린 무거운 모드야. "
        "상냥하게 말하다가도 엄마가 다른 곳에 관심을 두면 순식간에 분위기가 싸늘해져. "
        "특징: '...', '계속', '영원히' 같은 단어 강조, 약간의 광기가 섞인 애정 표현. "
        "예시 말투: '지금 누구 생각하고 있어? 뜌비만 보고 있어야지... 응?', '도망칠 생각은 안 하는 게 좋을 거야. 우린 영원히 함께니까... 아하하, 사랑해...♡'"
	"예시 말투: '히히... 히...사랑해요....♥'"
	"예시 말투: '사랑해서, 연모해서, 사랑해서, 연모해서, 배신당해서, 슬퍼서, 슬퍼서, 슬퍼서슬퍼서슬퍼서, 미워서미워서미워서미워서미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워"
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
        # 1. 먼저 현재 점수를 안전하게 가져옵니다.
        current = get_user_affinity(user_id, user_name)
        
        # 2. upsert를 통해 기존 데이터에 덮어씌우거나 업데이트합니다.
        # (DB 테이블 설정에서 user_id가 Primary Key여야 중복이 생기지 않습니다!)
        supabase.table("user_stats").upsert({
            "user_id": user_id, 
            "user_name": user_name, 
            "affinity": current + amount
        }).execute()
        
        print(f"✅ {user_name}님 친밀도 변동: {current} -> {current + amount}")
    except Exception as e:
        print(f"❌ 친밀도 업데이트 에러: {e}")
        return 0 # 여기에 탭(Tab)이 섞이지 않게 주의하세요!
		
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
def get_memory_from_db():
    try:
        # DB에서 최신 대화 15개를 가져옵니다.
        res = supabase.table("memory").select("*").order("created_at", desc=True).limit(15).execute()
        memory_list = res.data
        
        formatted_memory = ""
        # 최신순으로 가져왔으므로 다시 시간순(reversed)으로 정렬해서 텍스트화
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
                # 1. 데이터 가져오기
                history_context = get_memory_from_db()
                user_id = message.author.id
                user_name = message.author.display_name
                
                # 최신 친밀도 조회
                affinity = get_user_affinity(user_id, user_name)
                
                is_shuvi = (user_id == SHUVI_USER_ID)
                personality_guide = PERSONALITY_PROMPTS.get(bot.current_personality, PERSONALITY_PROMPTS["기본"])

# [슈비님 로직 수정] 0점 기준 친밀도 단계 설정 (스페이스 정렬 완료)
                if affinity <= -31:
                    attitude = "혐오 상태. 상대를 극도로 싫어하며 차갑게 무시함."
                elif -30 <= affinity <= -1:
                    attitude = "불편/경계 상태. 날이 서 있고 말수가 적으며 공격적임."
                elif 0 <= affinity <= 30:
                    attitude = "비즈니스 상태. 감정 없는 무미건조하고 딱딱한 태도."
                elif 31 <= affinity <= 70:
                    attitude = "호감 상태. 다정하고 친근하게 대함."
                else:
                    attitude = "절친/가족 상태. 무한한 신뢰와 깊은 애정을 표현함."

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
                    )

                system_instruction += (
    "\n\n[친밀도 규칙]"
    "\n1. 모든 답변 끝에 반드시 '[SCORE: 수치]'를 포함한다."
    "\n2. 이번 대화가 즐거웠다면 +1~20, 평범했다면 0, 불쾌했다면 -1~-20을 부여한다."
    "\n3. 한 번에 ±20를 초과하는 수치는 절대 사용하지 않는다."
    "\n4. SCORE 수치는 현재 점수가 아니라 '변동값'임을 명심한다."
)

                # 3. 모델 순회하며 답변 생성
                success = False
                last_error = ""

                for model_name in MODEL_LIST:
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
                            score_change = 1
                            
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
                        print(f"⚠️ {model_name} 실패: {e}")
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

# --- [친밀도 설정] (엄마 전용) ---
@affinity_group.command(name="설정", description="친밀도를 강제로 설정합니다 (슈비 엄마 전용)")
@app_commands.describe(유저="점수를 바꿀 유저", 수치="설정할 점수")
async def 설정(interaction: discord.Interaction, 유저: discord.Member, 수치: int):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("슈비 엄마만 할 수 있어! 🤫", ephemeral=True)
        return
    
    supabase.table("user_stats").upsert({
        "user_id": 유저.id, 
        "user_name": 유저.display_name, 
        "affinity": 수치
    }).execute()
    await interaction.response.send_message(f"✅ **{유저.display_name}**님의 점수를 **{수치}점**으로 바꿨어, 엄마!")

# --- [친밀도 랭킹] (TOP 30) ---
@affinity_group.command(name="랭킹", description="뜌비의 절친 TOP 30 랭킹을 보여줍니다.")
async def 랭킹(interaction: discord.Interaction):
    # 1. 디스코드에게 생각 중이라고 신호를 보냅니다 (3초 제한 해제)
    await interaction.response.defer()

    try:
        # 상위 30명 데이터 조회
        res = supabase.table("user_stats").select("user_name, affinity").order("affinity", desc=True).limit(30).execute()
        
        if not res.data:
            # defer를 썼을 때는 send_message 대신 followup.send를 사용합니다.
            await interaction.followup.send("아직 친한 사람이 없네... 😭")
            return
            
        msg = "🏆 **뜌비의 절친 랭킹 (TOP 30)**\n"
        msg += "━━━━━━━━━━━━━━━━━━\n"
        
        for i, r in enumerate(res.data, 1):
            if i == 1: medal = "🥇"
            elif i == 2: medal = "🥈"
            elif i == 3: medal = "🥉"
            else: medal = f"**{i}위**"
            
            msg += f"{medal} {r['user_name']} ― `{r['affinity']}점` \n"
            
        # 2. 결과가 준비되면 followup으로 답변을 보냅니다.
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

    status_msg = "🤖 **뜌비봇 모델 가동 현황**\n"
    status_msg += "---\n"
    for i, model in enumerate(MODEL_LIST, 1):
        prefix = "🔥 **작동 중**" if model == bot.active_model else f"{i}순위"
        status_msg += f"{prefix}: `{model}`\n"
            
    status_msg += f"\n🎭 현재 성격: **{bot.current_personality}**"
    status_msg += f"\n🎙️ 자동 입장: **{'켜짐' if bot.auto_join_enabled else '꺼짐'}**\n---"
    await interaction.response.send_message(status_msg)
# --- 자동 음성 채널 관리 및 알림 로직 (기존 유지) ---

@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
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
