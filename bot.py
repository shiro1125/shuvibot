import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import os
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

# 외부 로직 임포트
from personality import make_system_instruction
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide, 
    get_memory_from_db, save_to_memory, get_top_ranker_id, get_affinity_ranking,
    supabase
)

# 기본 설정
korea = pytz.timezone('Asia/Seoul')
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ID 설정
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
        self.rank_update_loop.start()
        self.control_voice_channel.start()
        self.send_notifications.start()

    @tasks.loop(hours=1)
    async def rank_update_loop(self):
        """1위 유저에게 전용 역할 부여"""
        guild = self.get_guild(GUILD_ID_1)
        top_id = get_top_ranker_id()
        role = guild.get_role(RANK_1_ROLE_ID) if guild else None
        if role and top_id:
            winner = guild.get_member(top_id)
            if winner and role not in winner.roles:
                for m in role.members: await m.remove_roles(role)
                await winner.add_roles(role)

    @tasks.loop(minutes=1)
    async def control_voice_channel(self):
        """음성 채널 자동 입장 및 스터디 채널 시간 제어"""
        now_korea = datetime.now(korea)
        guild = self.get_guild(GUILD_ID_1)
        if not guild: return
        
        # 작업 채널 자동 입장
        if self.auto_join_enabled:
            work_channel = guild.get_channel(WORK_CHANNEL_ID)
            if work_channel:
                vc = guild.voice_client
                if vc is None or not vc.is_connected():
                    try: await work_channel.connect(reconnect=True, timeout=15)
                    except: pass
        
        # 스터디 채널 상태 변경 (18:00~23:00)
        study_channel = guild.get_channel(STUDY_CHANNEL_ID)
        if study_channel:
            everyone, study_role = guild.default_role, discord.utils.get(guild.roles, name="스터디")
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
        """매주 토요일 수업 알림"""
        now_korea = datetime.now(korea)
        if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
            guild = self.get_guild(GUILD_ID_2)
            if not guild: return
            ann_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            study_role = discord.utils.get(guild.roles, name="수강생")
            if ann_channel and study_role:
                await ann_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")

bot = MyBot()

# --- 명령어 영역 ---

@bot.tree.command(name="모델", description="뜌비봇 가동 현황 확인")
async def 모델확인(interaction: discord.Interaction):
    model_status = "🤖 **뜌비봇 모델 가동 현황**\n---"
    for i, model in enumerate(MODEL_LIST, 1):
        indicator = "✅" if MODEL_STATUS[model]["is_available"] else "❌"
        model_status += f"\n{i}순위: {indicator} `{model}`"
    model_status += f"\n---\n🎭 성격: `{bot.current_personality}` | 🎙️ 자동입장: `{'ON' if bot.auto_join_enabled else 'OFF'}`"
    model_status += f"\n✨ 현재 활성 모델: `{bot.active_model}`"
    await interaction.response.send_message(model_status)

친밀도 = app_commands.Group(name="친밀도", description="관계 관리")

@친밀도.command(name="확인", description="친밀도와 채팅 수 확인")
async def aff_check(it: discord.Interaction, 유저: discord.Member = None):
    target = 유저 or it.user
    res = supabase.table("user_stats").select("affinity, chat_count").eq("user_id", str(target.id)).execute()
    score, chats = (res.data[0]['affinity'], res.data[0]['chat_count']) if res.data else (0, 0)
    await it.response.send_message(f"📊 **{target.display_name}**님 정보\n- 친밀도: `{score}점` \n- 채팅 수: `{chats}회`")

@친밀도.command(name="랭킹", description="친밀도 TOP 30 랭킹")
async def aff_ranking(it: discord.Interaction):
    await it.response.defer()
    data = get_affinity_ranking(30)
    msg = "🏆 **뜌비 랭킹 TOP 30**\n" + "—" * 20 + "\n"
    for i, u in enumerate(data):
        msg += f"{i+1}. **{u['user_name']}** — `{u['affinity']}점` (💬 {u.get('chat_count', 0)}회)\n"
    await it.followup.send(msg)

@친밀도.command(name="설정", description="친밀도 강제 설정 (슈비 전용)")
async def aff_set(it: discord.Interaction, 유저: discord.Member, 점수: int):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("슈비님만 가능해! 😤", ephemeral=True)
    update_user_affinity(유저.id, 유저.display_name, 점수, reset=True)
    await it.response.send_message(f"✅ **{유저.display_name}**님의 친밀도를 `{점수}점`으로 설정했어!")

bot.tree.add_command(친밀도)

@bot.tree.command(name="성격", description="뜌비의 성격을 변경합니다 (슈비 전용)")
@app_commands.choices(설정=[
    app_commands.Choice(name="기본", value="기본"),
    app_commands.Choice(name="메스가키", value="메스가키"),
    app_commands.Choice(name="츤데레", value="츤데레"),
    app_commands.Choice(name="얀데레", value="얀데레")
])
async def set_personality(it: discord.Interaction, 설정: str):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("슈비님만 가능해! 😤", ephemeral=True)
    bot.current_personality = 설정
    await it.response.send_message(f"✅ 성격이 **{설정}**으로 변경되었어!")

@bot.tree.command(name="자동입장", description="자동 재접속 기능 On/Off")
async def toggle_auto_join(it: discord.Interaction, 상태: bool):
    bot.auto_join_enabled = 상태
    await it.response.send_message(f"🎙️ 자동 입장 기능이 **{'켜졌어' if 상태 else '꺼졌어'}**!")

@bot.tree.command(name="입장", description="음성 채널 호출")
async def join_vc(it: discord.Interaction):
    channel = it.user.voice.channel if it.user.voice else it.guild.get_channel(WORK_CHANNEL_ID)
    if channel:
        if it.guild.voice_client: await it.guild.voice_client.move_to(channel)
        else: await channel.connect()
        await it.response.send_message(f"✅ {channel.name} 입장!")
    else: await it.response.send_message("⚠️ 채널을 못 찾겠어.")

@bot.tree.command(name="퇴장", description="음성 채널 퇴장")
async def leave_vc(it: discord.Interaction):
    if it.guild.voice_client:
        await it.guild.voice_client.disconnect()
        await it.response.send_message("👋 안녕!")
    else: await it.response.send_message("❌ 연결된 채널이 없어.")

# --- 대화 이벤트 ---

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
                    bot.active_model = m_name.replace("models/", "")
                    res = await asyncio.get_running_loop().run_in_executor(None, lambda: client.models.generate_content(
                        model=m_name, contents=f"{sys_inst}\n기억: {history}\n말: {message.content}"
                    ))
                    if res and res.text:
                        reply = res.text.split("[SCORE:")[0].strip()
                        await message.reply(reply)
                        
                        score_val = 0
                        if "[SCORE:" in res.text:
                            try: score_val = int(res.text.split("[SCORE:")[1].split("]")[0].replace("+",""))
                            except: pass
                        
                        # 업데이트 전/후 점수 받아와서 로그 출력
                        old_aff, new_aff = update_user_affinity(uid, uname, score_val)
                        diff = new_aff - old_aff
                        print(f"✅ {uname} 친밀도 업데이트: {old_aff} -> {new_aff} ({'+' if diff >= 0 else ''}{diff})")
                        
                        if bot.current_personality == "기본": save_to_memory(uname, message.content, reply)
                        success = True; break
                except Exception as e:
                    if any(x in str(e).upper() for x in ["429", "QUOTA"]): MODEL_STATUS[m_name]["is_available"] = False
                    continue
            if not success: await message.reply("뜌비 지금 너무 졸려... 😭")
        bot.is_processing = False
    await bot.process_commands(message)

# Flask 및 실행부
app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200
def run_flask(): app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
