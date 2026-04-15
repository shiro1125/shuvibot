import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
from datetime import datetime, time
import pytz
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

# 외부 로직 임포트
from personality import make_system_instruction
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide, 
    get_memory_from_db, save_to_memory, get_top_ranker_id, get_affinity_ranking
)

# 설정 및 ID
korea = pytz.timezone('Asia/Seoul')
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369
ANNOUNCEMENT_CHANNEL_ID = 1358394433665634454

SHUVI_USER_ID = 440517859140173835
RANK_1_ROLE_ID = 1493551151323549767

# Gemini 설정
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})
MODEL_LIST = [
    "models/gemini-3.1-pro-preview", 
    "models/gemini-3-flash-preview", 
    "models/gemini-2.5-pro", 
    "models/gemini-2.5-flash", 
    "models/gemini-2.0-flash", 
    "models/gemini-flash-latest"
]
MODEL_STATUS = {model: {"is_available": True} for model in MODEL_LIST}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members, intents.message_content, intents.voice_states = True, True, True
        super().__init__(command_prefix='!', intents=intents)
        self.auto_join_enabled = True
        self.is_processing = False
        self.current_personality = "기본"

    async def setup_hook(self):
        """시스템 동기화 및 Cog 로드"""
        # 확장 기능 로드 (블랙잭, TTS 등)
        extensions = ['blackjack', 'tts']
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ {ext} 로드 완료")
            except Exception as e:
                print(f"❌ {ext} 로드 실패: {e}")

        self.rank_update_loop.start()
        self.control_voice_channel.start()
        self.send_notifications.start()
        await self.tree.sync()
        print("✅ 전체 시스템 동기화 완료")

    @tasks.loop(hours=1)
    async def rank_update_loop(self):
        """친밀도 1위 역할 자동 부여"""
        guild = self.get_guild(GUILD_ID_1)
        top_id = get_top_ranker_id()
        role = guild.get_role(RANK_1_ROLE_ID) if guild else None
        if role and top_id:
            if role.members and role.members[0].id == top_id: return
            for m in role.members: await m.remove_roles(role)
            winner = guild.get_member(top_id)
            if winner: await winner.add_roles(role)

    @tasks.loop(minutes=1)
    async def control_voice_channel(self):
        """자동 입장 및 스터디 채널 관리"""
        now_korea = datetime.now(korea)
        guild = self.get_guild(GUILD_ID_1)
        if not guild: return
        
        # 자동 입장 로직
        if self.auto_join_enabled:
            work_channel = guild.get_channel(WORK_CHANNEL_ID)
            if work_channel:
                vc = guild.voice_client
                if vc is None or not vc.is_connected():
                    try: await work_channel.connect(reconnect=True, timeout=15)
                    except: pass

        # 스터디 채널 권한 및 이름 관리
        study_channel = guild.get_channel(STUDY_CHANNEL_ID)
        if study_channel:
            everyone = guild.default_role
            study_role = discord.utils.get(guild.roles, name="스터디")
            if study_role:
                if time(18, 0) <= now_korea.time() <= time(23, 0):
                    await study_channel.set_permissions(everyone, connect=False)
                    await study_channel.set_permissions(study_role, connect=True)
                    if study_channel.name != "🟢 스터디": await study_channel.edit(name="🟢 스터디")
                else:
                    await study_channel.set_permissions(everyone, connect=False)
                    await study_channel.set_permissions(study_role, connect=False)
                    if study_channel.name != "🔴 스터디": await study_channel.edit(name="🔴 스터디")

    @tasks.loop(minutes=1)
    async def send_notifications(self):
        """수업 알림 로직"""
        now_korea = datetime.now(korea)
        if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
            guild = self.get_guild(GUILD_ID_2)
            if not guild: return
            announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            study_role = discord.utils.get(guild.roles, name="수강생")
            if announcement_channel and study_role:
                await announcement_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")

bot = MyBot()

# --- 명령어: 모델 관리 (요청하신 스타일로 수정) ---
@bot.tree.command(name="모델", description="현재 뜌비봇이 사용 중인 모델 리스트와 우선순위를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    model_status = "🤖 **뜌비봇 모델 가동 현황**\n"
    model_status += "---"
    for i, model in enumerate(MODEL_LIST, 1):
        # 가동 가능 여부에 따라 상태 표시
        if MODEL_STATUS[model]["is_available"]:
            prefix = "✅ **현재 1순위**" if i == 1 else f"{i}순위"
            status_text = ""
        else:
            prefix = f"~~{i}순위~~"
            status_text = " **(한도 초과)**"
            
        model_status += f"\n{prefix}: `{model}`{status_text}"
        
    model_status += "\n---\n💡 *상위 모델의 한도가 다 차면 자동으로 다음 모델이 답변을 이어받습니다!*"
    await interaction.response.send_message(model_status)

# --- 명령어: 시스템 제어 ---
@bot.tree.command(name="자동입장", description="자동 재접속 기능을 설정합니다.")
@app_commands.choices(상태=[app_commands.Choice(name="켜기 (On)", value="on"), app_commands.Choice(name="끄기 (Off)", value="off")])
async def 자동입장(interaction: discord.Interaction, 상태: str):
    bot.auto_join_enabled = (상태 == "on")
    if 상태 == "off" and interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message(f"{'✅ 자동 입장 활성화' if 상태 == 'on' else '❌ 자동 입장 비활성화'}")

@bot.tree.command(name="입장", description="봇을 음성 채널로 부릅니다.")
async def 입장(interaction: discord.Interaction):
    channel = interaction.user.voice.channel if interaction.user.voice else bot.get_guild(GUILD_ID_1).get_channel(WORK_CHANNEL_ID)
    if channel:
        if interaction.guild.voice_client: await interaction.guild.voice_client.move_to(channel)
        else: await channel.connect()
        await interaction.response.send_message(f"✅ {channel.name} 입장!")
    else:
        await interaction.response.send_message("⚠️ 입장할 채널을 찾을 수 없습니다.")

@bot.tree.command(name="퇴장", description="봇을 음성 채널에서 내보냅니다.")
async def 퇴장(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 퇴장!")
    else:
        await interaction.response.send_message("❌ 연결된 음성 채널이 없습니다.")

# --- 친밀도 및 성격 명령어 ---
친밀도 = app_commands.Group(name="친밀도", description="뜌비와의 관계 관리")
@친밀도.command(name="확인", description="친밀도 확인")
async def aff_check(it: discord.Interaction, 유저: discord.Member = None):
    target = 유저 or it.user
    score = get_user_affinity(target.id, target.display_name)
    status = "영원한 단짝 💖" if score > 70 else "친한 친구 😊" if score > 30 else "안면 있는 사이 😐" if score >= 0 else "조심해야 할 사람 💀"
    await it.response.send_message(f"📊 **{target.display_name}**님과 뜌비의 친밀도는 `{score}점`이야! (상태: {status})")

@친밀도.command(name="랭킹", description="친밀도 TOP 30 확인")
async def aff_ranking(it: discord.Interaction):
    await it.response.defer()
    data = get_affinity_ranking(30)
    msg = "🏆 **친밀도 TOP 30**\n" + "—" * 20 + "\n"
    for i, u in enumerate(data):
        msg += f"{i+1}. **{u['user_name']}** — `{u['affinity']}점`\n"
    await it.followup.send(msg)
bot.tree.add_command(친밀도)

@bot.tree.command(name="성격", description="뜌비 성격 변경 (슈비 전용)")
async def set_personality(it: discord.Interaction, 설정: str):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 가능해! 😤", ephemeral=True)
    bot.current_personality = 설정
    await it.response.send_message(f"✅ 성격이 **{설정}**으로 변경되었어!")

# --- 메시지 이벤트 및 Gemini 로직 ---
@bot.event
async def on_message(message):
    if message.author.bot: return
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing: return
        bot.is_processing = True
        async with message.channel.typing():
            uid, uname = message.author.id, message.author.display_name
            aff = get_user_affinity(uid, uname)
            sys_inst = make_system_instruction(uid == SHUVI_USER_ID, uname, bot.current_personality, get_attitude_guide(aff))
            history = get_memory_from_db(uname) if bot.current_personality == "기본" else ""
            
            success = False
            for m_name in [m for m in MODEL_LIST if MODEL_STATUS[m]["is_available"]]:
                try:
                    res = await asyncio.get_running_loop().run_in_executor(None, lambda: client.models.generate_content(
                        model=m_name, contents=f"{sys_inst}\n기억: {history}\n말: {message.content}"
                    ))
                    if res and res.text:
                        reply = res.text.split("[SCORE:")[0].strip()
                        await message.reply(reply)
                        if "[SCORE:" in res.text:
                            try:
                                score_val = int(res.text.split("[SCORE:")[1].split("]")[0].replace("+",""))
                                update_user_affinity(uid, uname, score_val)
                            except: pass
                        if bot.current_personality == "기본": save_to_memory(uname, message.content, reply)
                        success = True; break
                except Exception as e:
                    if any(x in str(e).upper() for x in ["429", "QUOTA"]): MODEL_STATUS[m_name]["is_available"] = False
                    continue
            if not success: await message.reply("뜌비 지금 너무 졸려... 😭 (모델 한도 초과)")
        bot.is_processing = False
    await bot.process_commands(message)

# Flask (Koyeb 생존용)
app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200
if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    bot.run(TOKEN)
