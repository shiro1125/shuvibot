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

# [중요] 우리가 분리한 파일들을 불러옵니다.
from personality import make_system_instruction
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide,
    get_memory_from_db, save_to_memory, get_top_ranker_id
)

# 기본 설정
korea = pytz.timezone('Asia/Seoul')
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 서버/채널 ID (기존 데이터와 동일)
GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369
ANNOUNCEMENT_CHANNEL_ID = 1358394433665634454
SHUVI_USER_ID = 440517859140173835
RANK_1_ROLE_ID = 1493551151323549767

client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})

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
        await self.tree.sync()

bot = MyBot()

# --- 루프 시스템 (알림/보이스/랭킹) ---

@tasks.loop(minutes=1)
async def send_notifications():
    """수업 10분 전 알림 (토요일 17:50)"""
    now = datetime.now(korea)
    if now.weekday() == 5 and now.hour == 17 and now.minute == 50:
        guild = bot.get_guild(GUILD_ID_2)
        if guild:
            ann_ch = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            role = discord.utils.get(guild.roles, name="수강생")
            week_num = (now.day - 1) // 7 + 1
            if ann_ch and role:
                msg = "이번주는 휴강입니다." if week_num == 5 else f"{role.mention} 📢 수업 10분전 입니다!"
                await ann_ch.send(msg)

@tasks.loop(minutes=1)
async def control_voice_channel():
    """보이스 채널 자동 관리 및 모델 리셋"""
    now = datetime.now(korea)
    if now.hour == 16 and now.minute == 0:
        for m in MODEL_STATUS: MODEL_STATUS[m]["is_available"] = True
    
    guild = bot.get_guild(GUILD_ID_1)
    if guild:
        # 스터디 채널 관리
        study_ch = guild.get_channel(STUDY_CHANNEL_ID)
        if study_ch:
            study_role = discord.utils.get(guild.roles, name="스터디")
            if study_role:
                is_study_time = 18 <= now.hour <= 23
                await study_ch.set_permissions(guild.default_role, connect=False)
                await study_ch.set_permissions(study_role, connect=is_study_time)
                new_name = "🟢 스터디" if is_study_time else "🔴 스터디"
                if study_ch.name != new_name: await study_ch.edit(name=new_name)
        
        # 워크 채널 자동 입장
        if bot.auto_join_enabled:
            work_ch = guild.get_channel(WORK_CHANNEL_ID)
            if work_ch and (not guild.voice_client or not guild.voice_client.is_connected()):
                await work_ch.connect(reconnect=True, timeout=20)

@tasks.loop(hours=1)
async def rank_check_loop():
    """실시간 1위 역할 부여"""
    guild = bot.get_guild(GUILD_ID_1)
    top_id = get_top_ranker_id()
    role = guild.get_role(RANK_1_ROLE_ID) if guild else None
    if role and top_id:
        if role.members and role.members[0].id == top_id: return
        for m in role.members: await m.remove_roles(role)
        winner = guild.get_member(top_id)
        if winner: await winner.add_roles(role)

# --- 메시지 이벤트 (뜌비 반응) ---

@bot.event
async def on_message(message):
    if message.author.bot: return
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing: return
        bot.is_processing = True
        async with message.channel.typing():
            uid, uname = message.author.id, message.author.display_name
            is_shuvi = (uid == SHUVI_USER_ID)
            
            # 외부 모듈 호출
            affinity = get_user_affinity(uid, uname)
            attitude = get_attitude_guide(affinity)
            sys_inst = make_system_instruction(is_shuvi, uname, bot.current_personality, attitude)
            
            history = get_memory_from_db(uname) if bot.current_personality == "기본" else ""
            content = f"기억:\n{history}\n질문: {message.content}" if history else message.content

            success = False
            for m_name in [m for m in MODEL_LIST if MODEL_STATUS[m]["is_available"]]:
                try:
                    bot.active_model = m_name
                    # Gemma 예외처리 포함
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
                                score = int(text.split("[SCORE:")[1].split("]")[0].replace("+",""))
                            except: pass
                        
                        await message.reply(clean_text)
                        update_user_affinity(uid, uname, score)
                        if bot.current_personality == "기본": save_to_memory(uname, message.content, clean_text)
                        success = True; break
                except Exception as e:
                    if any(x in str(e).upper() for x in ["429", "QUOTA"]): MODEL_STATUS[m_name]["is_available"] = False
                    continue
            if not success: await message.reply("뜌비 기운이 없어... 나중에 불러줘!")
        bot.is_processing = False
    await bot.process_commands(message)

# --- 슬래시 명령어 (전체 복원) ---

@bot.tree.command(name="성격", description="뜌비 성격 변경")
@app_commands.choices(설정=[app_commands.Choice(name=v, value=v) for v in ["기본", "메스가키", "츤데레", "얀데레"]])
async def set_p(it: discord.Interaction, 설정: app_commands.Choice[str]):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 가능해!", ephemeral=True)
    bot.current_personality = 설정.value
    await it.response.send_message(f"✅ 성격이 **{설정.value}**로 변경됐어!")

@bot.tree.command(name="내정보", description="나의 친밀도 확인")
async def my_info(it: discord.Interaction):
    aff = get_user_affinity(it.user.id, it.user.display_name)
    await it.response.send_message(f"📊 {it.user.display_name}님의 친밀도: **{aff}**")

@bot.tree.command(name="자동입장", description="보이스 채널 자동입장 설정")
@app_commands.choices(상태=[app_commands.Choice(name="ON", value="on"), app_commands.Choice(name="OFF", value="off")])
async def auto_join(it: discord.Interaction, 상태: str):
    bot.auto_join_enabled = (상태 == "on")
    await it.response.send_message(f"✅ 자동입장: {상태.upper()}")

@bot.event
async def on_ready():
    for l in [send_notifications, control_voice_channel, rank_check_loop]:
        if not l.is_running(): l.start()
    print(f"✅ {bot.user} 준비 완료!")

app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200
if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    bot.run(TOKEN)
