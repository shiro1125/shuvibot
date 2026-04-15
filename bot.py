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
    get_memory_from_db, save_to_memory, get_top_ranker_id, get_affinity_ranking
)

# 설정 및 ID
korea = pytz.timezone('Asia/Seoul')
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

GUILD_ID_1 = 1228372760212930652
SHUVI_USER_ID = 440517859140173835
RANK_1_ROLE_ID = 1493551151323549767

# Gemini 설정
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})
MODEL_LIST = ["models/gemini-3-flash-preview", "models/gemini-2.5-flash", "models/gemini-2.0-flash"]
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
        self.rank_update_loop.start()
        await self.tree.sync()
        print("✅ 시스템 동기화 완료")

    @tasks.loop(hours=1)
    async def rank_update_loop(self):
        """1시간마다 친밀도 1위에게 특별 역할을 부여합니다."""
        guild = self.get_guild(GUILD_ID_1)
        top_id = get_top_ranker_id()
        role = guild.get_role(RANK_1_ROLE_ID) if guild else None
        if role and top_id:
            if role.members and role.members[0].id == top_id: return
            for m in role.members: await m.remove_roles(role)
            winner = guild.get_member(top_id)
            if winner: await winner.add_roles(role)

bot = MyBot()

# --- 명령어: 모델 관리 ---
@bot.tree.command(name="모델", description="현재 사용 중인 AI 모델 상태를 확인합니다.")
async def model_info(it: discord.Interaction):
    msg = f"🤖 **뜌비 상태 보고**\n- 현재 성격: `{bot.current_personality}`\n\n**모델 가동 현황:**\n"
    for m in MODEL_LIST:
        status = "✅ 가동 가능" if MODEL_STATUS[m]["is_available"] else "❌ 한도 초과"
        msg += f"- `{m}`: {status}\n"
    await it.response.send_message(msg)


# --- 명령어: 친밀도 그룹 ---
친밀도 = app_commands.Group(name="친밀도", description="뜌비와의 관계를 관리해!")

@친밀도.command(name="확인", description="상대방과의 친밀도를 확인합니다.")
async def aff_check(it: discord.Interaction, 유저: discord.Member = None):
    target = 유저 or it.user
    score = get_user_affinity(target.id, target.display_name)
    status = "영원한 단짝 💖" if score > 70 else "친한 친구 😊" if score > 30 else "안면 있는 사이 😐" if score >= 0 else "조심해야 할 사람 💀"
    await it.response.send_message(f"📊 **{target.display_name}**님과 뜌비의 친밀도는 `{score}점`이야! (상태: {status})")

@친밀도.command(name="랭킹", description="친밀도 TOP 30을 확인합니다.")
async def aff_ranking(it: discord.Interaction):
    await it.response.defer(ephemeral=False)
    try:
        ranking_data = get_affinity_ranking(30)
        if not ranking_data: return await it.followup.send("⚠️ 아직 데이터가 없어!")
        
        rank_text = "🏆 **친밀도 TOP 30**\n" + "—" * 20 + "\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, user in enumerate(ranking_data):
            icon = medals[i] if i < 3 else f"{i+1}위"
            rank_text += f"{icon} **{user['user_name']}** — `{user['affinity']}점` (`💬 {user['chat_count']}회`)\n"
        await it.followup.send(rank_text)
    except:
        await it.followup.send("🚨 랭킹 로드 실패! DB를 확인해줘.")

@친밀도.command(name="설정", description="친밀도 강제 설정 (슈비 전용)")
async def aff_set(it: discord.Interaction, 유저: discord.Member, 점수: int):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 가능해! 😤", ephemeral=True)
    update_user_affinity(유저.id, 유저.display_name, 점수, reset=True)
    await it.response.send_message(f"✅ **{유저.display_name}**님의 점수를 **{점수}점**으로 고정했어!")

bot.tree.add_command(친밀도)

# --- 명령어: 시스템 설정 ---
@bot.tree.command(name="성격", description="뜌비 성격 변경 (슈비 전용)")
@app_commands.choices(설정=[app_commands.Choice(name=x, value=x) for x in ["기본", "메스가키", "츤데레", "얀데레"]])
async def set_p(it: discord.Interaction, 설정: app_commands.Choice[str]):
    if it.user.id != SHUVI_USER_ID: return await it.response.send_message("엄마만 가능!", ephemeral=True)
    bot.current_personality = 설정.value
    await it.response.send_message(f"✅ 성격이 **{설정.value}**로 변경되었어!")

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
                        break
                except Exception as e:
                    if "429" in str(e): MODEL_STATUS[m_name]["is_available"] = False
                    continue
        bot.is_processing = False
    await bot.process_commands(message)

# Flask (Koyeb 생존용)
app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200
if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    bot.run(TOKEN)
