import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime
import pytz
import asyncio
import os

from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

# [필독] 이 파일들이 같은 폴더에 있어야 합니다!
from personality import PERSONALITY_PROMPTS, make_system_instruction
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide,
    get_memory_from_db, save_to_memory, get_top_ranker_id, supabase
)

# 기본 설정 및 환경 변수
korea = pytz.timezone('Asia/Seoul')
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 서버 및 채널 설정 (슈비님 기존 ID 그대로 유지)
GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369
ANNOUNCEMENT_CHANNEL_ID = 1358394433665634454
SHUVI_USER_ID = 440517859140173835
RANK_1_ROLE_ID = 1493551151323549767

# 1. Gemini API 설정
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})

# 2. 모델 리스트 및 상태 관리
MODEL_LIST = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-2.5-flash-lite",
    "models/gemma-3-27b-it"
]
MODEL_STATUS = {model: {"is_available": True} for model in MODEL_LIST}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix='!', intents=intents)
        
        self.auto_join_enabled = True
        self.is_processing = False
        self.current_personality = "기본"
        self.active_model = "대기 중"

    async def setup_hook(self):
        # ✅ [복원] TTS 및 블랙잭 익스텐션 로드
        for ext in ['tts', 'blackjack']:
            try:
                await self.load_extension(ext)
                print(f"✅ {ext} 로드 완료!")
            except Exception as e:
                print(f"❌ {ext} 로드 실패: {e}")
        
        await self.tree.sync()
        print("✅ 모든 슬래시 명령어 동기화 완료!")

bot = MyBot()

# --- 루프 시스템: 알림, 음성 채널, 랭킹 ---

@tasks.loop(minutes=1)
async def send_notifications():
    """토요일 17:50 수업 알림 및 5주차 휴강 로직"""
    now = datetime.now(korea)
    if now.weekday() == 5 and now.hour == 17 and now.minute == 50:
        guild = bot.get_guild(GUILD_ID_2)
        if guild:
            ann_ch = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            role = discord.utils.get(guild.roles, name="수강생")
            week_num = (now.day - 1) // 7 + 1 # 주차 계산
            
            if ann_ch and role:
                if week_num == 5:
                    await ann_ch.send("이번주는 휴강입니다.")
                else:
                    await ann_ch.send(f"{role.mention} 📢 수업 10분전 입니다!")

@tasks.loop(minutes=1)
async def control_voice_channel():
    """오후 4시 모델 리셋 및 음성 채널 자동 입장/스터디 채널 관리"""
    now = datetime.now(korea)
    if now.hour == 16 and now.minute == 0:
        for m in MODEL_STATUS: MODEL_STATUS[m]["is_available"] = True
        print("🔄 모든 모델 한도 초기화 완료.")

    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return

    # 스터디 채널 상태 업데이트 (18:00 ~ 23:00)
    study_ch = guild.get_channel(STUDY_CHANNEL_ID)
    if study_ch:
        study_role = discord.utils.get(guild.roles, name="스터디")
        if study_role:
            is_study_time = 18 <= now.hour <= 23
            await study_ch.set_permissions(guild.default_role, connect=False)
            await study_ch.set_permissions(study_role, connect=is_study_time)
            status_name = "🟢 스터디" if is_study_time else "🔴 스터디"
            if study_ch.name != status_name: await study_ch.edit(name=status_name)

    # 작업 채널 자동 입장
    if bot.auto_join_enabled:
        work_ch = guild.get_channel(WORK_CHANNEL_ID)
        if work_ch and (not guild.voice_client or not guild.voice_client.is_connected()):
            try: await work_ch.connect(reconnect=True, timeout=20)
            except: pass

@tasks.loop(hours=1)
async def rank_check_loop():
    """실시간 친밀도 1위에게 역할 부여 (자동 갱신)"""
    guild = bot.get_guild(GUILD_ID_1)
    top_id = get_top_ranker_id()
    role = guild.get_role(RANK_1_ROLE_ID)
    if role and top_id:
        current_winners = role.members
        if current_winners and current_winners[0].id == top_id: return
        for m in current_winners: await m.remove_roles(role)
        winner = guild.get_member(top_id)
        if winner: await winner.add_roles(role)

# --- 메인 이벤트: 뜌비와의 대화 ---

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing: return
        bot.is_processing = True
        
        async with message.channel.typing():
            uid, uname = message.author.id, message.author.display_name
            is_shuvi = (uid == SHUVI_USER_ID)
            
            # 친밀도 및 기억 데이터 로드
            affinity = get_user_affinity(uid, uname)
            attitude = get_attitude_guide(affinity)
            history = get_memory_from_db(uname) if bot.current_personality == "기본" else ""
            
            # 시스템 지침 생성 (함수화)
            sys_inst = make_system_instruction(is_shuvi, uname, bot.current_personality, attitude)
            content = f"과거 대화 기억:\n{history}\n\n현재 말: {message.content}" if history else message.content

            success = False
            for m_name in [m for m in MODEL_LIST if MODEL_STATUS[m]["is_available"]]:
                try:
                    bot.active_model = m_name
                    is_gemma = "gemma" in m_name.lower()
                    cfg = {} if is_gemma else {'system_instruction': sys_inst}
                    prompt = f"[지침]\n{sys_inst}\n\n내용: {content}" if is_gemma else content
                    
                    res = await asyncio.get_running_loop().run_in_executor(None, lambda: client.models.generate_content(model=m_name, contents=prompt, config=cfg))
                    
                    if res and res.text:
                        text = res.text
                        clean_text, score = text, 0
                        if "[SCORE:" in text:
                            try:
                                clean_text = text.split("[SCORE:")[0].strip()
                                score_val = int(text.split("[SCORE:")[1].split("]")[0].replace("+",""))
                                score = max(-20, min(20, score_val))
                            except: pass
                        
                        await message.reply(clean_text)
                        update_user_affinity(uid, uname, score)
                        if bot.current_personality == "기본": save_to_memory(uname, message.content, clean_text)
                        success = True; break
                except Exception as e:
                    err = str(e).upper()
                    if any(x in err for x in ["429", "QUOTA", "LIMIT"]):
                        MODEL_STATUS[m_name]["is_available"] = False
                    continue
            
            if not success: await message.reply("뜌비가 지금 너무 졸려... 나중에 다시 불러줘! 😭")
        bot.is_processing = False
    
    await bot.process_commands(message)

# --- 슬래시 명령어: 관리 및 설정 ---

@bot.tree.command(name="성격", description="뜌비의 성격을 바꿉니다.")
@app_commands.choices(설정=[app_commands.Choice(name=v, value=v) for v in ["기본", "메스가키", "츤데레", "얀데레"]])
async def set_personality(it: discord.Interaction, 설정: app_commands.Choice[str]):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 바꿀 수 있어!", ephemeral=True)
    bot.current_personality = 설정.value
    await it.response.send_message(f"✅ 뜌비 성격이 **{설정.value}**로 바뀌었어!")

@bot.tree.command(name="내정보", description="나의 친밀도와 랭킹 상태 확인")
async def my_info(it: discord.Interaction):
    aff = get_user_affinity(it.user.id, it.user.display_name)
    status = "영원한 단짝 💖" if aff > 70 else "친한 친구 😊" if aff > 30 else "안면 있는 사이 😐" if aff >= 0 else "조심해야 할 사람 💀"
    await it.response.send_message(f"📊 **{it.user.display_name}**님 친밀도: **{aff}점** ({status})")

@bot.tree.command(name="자동입장", description="음성 채널 자동 입장 설정")
@app_commands.choices(상태=[app_commands.Choice(name="On", value="on"), app_commands.Choice(name="Off", value="off")])
async def set_auto_join(it: discord.Interaction, 상태: str):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 가능해!", ephemeral=True)
    bot.auto_join_enabled = (상태 == "on")
    if 상태 == "off" and it.guild.voice_client: await it.guild.voice_client.disconnect()
    await it.response.send_message(f"🎙️ 자동 입장: **{상태.upper()}**")

@bot.tree.command(name="모델", description="현재 뜌비의 뇌 상태(모델) 확인")
async def check_model(it: discord.Interaction):
    msg = "🤖 **뜌비 가동 현황**\n---\n"
    for i, m in enumerate(MODEL_LIST, 1):
        stat = "✅" if MODEL_STATUS[m]["is_available"] else "❌(한도초과)"
        msg += f"{i}순위: {stat} `{m}`\n"
    msg += f"---\n🎭 성격: {bot.current_personality} | 🧠 활성: {bot.active_model}"
    await it.response.send_message(msg)

# --- 봇 실행 및 서버 유지 ---

@bot.event
async def on_ready():
    for loop in [send_notifications, control_voice_channel, rank_check_loop]:
        if not loop.is_running(): loop.start()
    print(f"✅ {bot.user} 로그인 완료!")

app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200

if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    bot.run(TOKEN)
