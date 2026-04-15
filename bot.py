import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
from datetime import datetime
import pytz
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

# 외부 로직 임포트
from personality import make_system_instruction
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide, 
    get_memory_from_db, save_to_memory, get_top_ranker_id, get_affinity_ranking,
    supabase # 랭킹 직접 조회를 위해 supabase 객체 필요
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
        intents.members, intents.message_content, intents.voice_states = True, True, True
        super().__init__(command_prefix='!', intents=intents)
        self.auto_join_enabled = True
        self.is_processing = False
        self.current_personality = "기본"
        self.active_model = "대기 중"

    async def setup_hook(self):
        # 외부 확장 로드
        for ext in ['tts', 'blackjack']:
            try:
                await self.load_extension(ext)
                print(f"✅ {ext} 로드 완료")
            except Exception as e:
                print(f"❌ {ext} 로드 실패: {e}")
        
        self.main_loop.start()
        self.rank_update_loop.start()
        await self.tree.sync()
        print("✅ 시스템 동기화 완료")

    @tasks.loop(minutes=1)
    async def main_loop(self):
        now = datetime.now(korea)
        guild1 = self.get_guild(GUILD_ID_1)
        guild2 = self.get_guild(GUILD_ID_2)

        if now.hour == 16 and now.minute == 0:
            for m in MODEL_STATUS: MODEL_STATUS[m]["is_available"] = True

        if guild1:
            study_ch = guild1.get_channel(STUDY_CHANNEL_ID)
            if study_ch:
                study_role = discord.utils.get(guild1.roles, name="스터디")
                is_time = 18 <= now.hour <= 23
                await study_ch.set_permissions(guild1.default_role, connect=False)
                await study_ch.set_permissions(study_role, connect=is_time)
                name = "🟢 스터디" if is_time else "🔴 스터디"
                if study_ch.name != name: await study_ch.edit(name=name)
            
            if self.auto_join_enabled:
                work_ch = guild1.get_channel(WORK_CHANNEL_ID)
                if work_ch and (not guild1.voice_client or not guild1.voice_client.is_connected()):
                    try: await work_ch.connect(reconnect=True, timeout=20)
                    except: pass

        if now.weekday() == 5 and now.hour == 17 and now.minute == 50 and guild2:
            ann_ch = guild2.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            role = discord.utils.get(guild2.roles, name="수강생")
            week = (now.day - 1) // 7 + 1
            if ann_ch and role:
                msg = "이번주는 휴강입니다." if week == 5 else f"{role.mention} 📢 수업 10분전 입니다!"
                await ann_ch.send(msg)

    @tasks.loop(hours=1)
    async def rank_update_loop(self):
        guild = self.get_guild(GUILD_ID_1)
        top_id = get_top_ranker_id()
        role = guild.get_role(RANK_1_ROLE_ID) if guild else None
        if role and top_id:
            if role.members and role.members[0].id == top_id: return
            for m in role.members: await m.remove_roles(role)
            winner = guild.get_member(top_id)
            if winner: await winner.add_roles(role)

bot = MyBot()

# --- 명령어: 친밀도 그룹 ---
친밀도 = app_commands.Group(name="친밀도", description="뜌비와의 관계를 관리해!")

@친밀도.command(name="확인", description="상대방과의 친밀도를 확인합니다.")
async def aff_check(it: discord.Interaction, 유저: discord.Member = None):
    target = 유저 or it.user
    score = get_user_affinity(target.id, target.display_name)
    
    # bot.py 기존 기준 유지
    if score > 70: status = "영원한 단짝 💖"
    elif score > 30: status = "친한 친구 😊"
    elif score >= 0: status = "안면 있는 사이 😐"
    else: status = "조심해야 할 사람 💀"
    
    await it.response.send_message(f"📊 **{target.display_name}**님과 뜌비의 친밀도는 `{score}점`이야! (상태: {status})")

@친밀도.command(name="랭킹", description="친밀도 TOP 30을 확인합니다.")
async def aff_ranking(it: discord.Interaction):
    await it.response.defer(ephemeral=False) # 타임아웃 방지
    try:
        ranking_data = get_affinity_ranking(30)
        if not ranking_data:
            return await it.followup.send("⚠️ 아직 기록된 데이터가 없는 것 같아.")

        rank_text = "🏆 **친밀도 TOP 30**\n" + "—" * 20 + "\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, user in enumerate(ranking_data):
            rank_icon = medals[i] if i < 3 else f"{i+1}위"
            rank_text += f"{rank_icon} **{user.get('user_name', '??')}** — `{user.get('affinity', 0)}점` (`💬 {user.get('chat_count', 0)}회`)\n"

        await it.followup.send(rank_text)
    except Exception as e:
        await it.followup.send("🚨 랭킹 로드 중에 문제가 생겼어!")

@친밀도.command(name="설정", description="친밀도 강제 설정 (슈비 전용)")
async def aff_set(it: discord.Interaction, 유저: discord.Member, 점수: int):
    if it.user.id != SHUVI_USER_ID: 
        return await it.response.send_message("뜌비의 마음은 엄마만 정할 수 있어! 😤", ephemeral=True)
    
    # reset=True 대신 현재 점수와의 차이를 계산해서 업데이트
    current = get_user_affinity(유저.id, 유저.display_name)
    diff = 점수 - current
    update_user_affinity(유저.id, 유저.display_name, diff)
    
    await it.response.send_message(f"✅ **{유저.display_name}**님의 점수를 **{점수}점**으로 맞췄어! ✨")

# 그룹 등록 필수!
bot.tree.add_command(친밀도)

bot.tree.add_command(친밀도)

# --- 명령어: 설정 ---
@bot.tree.command(name="성격", description="뜌비 성격 변경")
@app_commands.choices(설정=[app_commands.Choice(name=x, value=x) for x in ["기본", "메스가키", "츤데레", "얀데레"]])
async def set_p(it: discord.Interaction, 설정: app_commands.Choice[str]):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 가능!", ephemeral=True)
    bot.current_personality = 설정.value
    await it.response.send_message(f"✅ 성격이 **{설정.value}**로 변경되었어!")

@bot.tree.command(name="자동입장", description="자동입장 On/Off")
@app_commands.choices(상태=[app_commands.Choice(name="ON", value="on"), app_commands.Choice(name="OFF", value="off")])
async def set_aj(it: discord.Interaction, 상태: str):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 가능!", ephemeral=True)
    bot.auto_join_enabled = (상태 == "on")
    await it.response.send_message(f"🎙️ 자동입장: {상태.upper()}")

# --- 메시지 이벤트 ---
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
                    bot.active_model = m_name
                    res = await asyncio.get_running_loop().run_in_executor(None, lambda: client.models.generate_content(
                        model=m_name, 
                        contents=f"{sys_inst}\n기억: {history}\n말: {message.content}"
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
            if not success: await message.reply("뜌비 지금 너무 졸려... 😭")
        bot.is_processing = False
    await bot.process_commands(message)

app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200
if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    bot.run(TOKEN)
