# bot.py

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

from personality import make_system_instruction, get_personality_guide
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide, 
    get_memory_from_db, save_to_memory, get_top_ranker_id, get_affinity_ranking
)

# 한국 시간대 설정
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

client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})
MODEL_LIST = ["models/gemini-3-flash-preview", "models/gemini-2.5-flash", "models/gemini-2.0-flash", "models/gemini-flash-latest"]
MODEL_STATUS = {m: {"is_available": True} for m in MODEL_LIST}

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

    async def setup_hook(self):
        pass

bot = MyBot()

@tasks.loop(hours=1)
async def rank_check_loop():
    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return
    top_id = get_top_ranker_id()
    role = guild.get_role(RANK_1_ROLE_ID)
    if role and top_id:
        winner = guild.get_member(top_id)
        if winner and role not in winner.roles:
            for m in role.members: await m.remove_roles(role)
            await winner.add_roles(role)

@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return
    
    if bot.auto_join_enabled:
        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        vc = guild.voice_client
        if vc is None or not vc.is_connected():
            try: await work_channel.connect(reconnect=True, timeout=20)
            except: pass
        elif vc.channel and vc.channel.id != WORK_CHANNEL_ID:
            try: await vc.move_to(work_channel)
            except: pass

@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)
    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
        guild = bot.get_guild(GUILD_ID_2)
        if not guild: return
        channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        role = discord.utils.get(guild.roles, name="수강생")
        if channel and role: await channel.send(f"{role.mention} 📢 수업 10분전 입니다!")

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)}개의 슬래시 명령어 동기화 완료!")
    except Exception as e:
        print(f"❌ 명령어 동기화 실패: {e}")

    print(f'✅ 봇 로그인됨: {bot.user}')

    if not control_voice_channel.is_running():
        control_voice_channel.start()
        print("🎙️ [시스템] 자동 입장 루프 시작!")

    if not send_notifications.is_running():
        send_notifications.start()
        print("🔔 [시스템] 알림 루프 시작!")

    if not rank_check_loop.is_running():
        rank_check_loop.start()
        print("👑 [시스템] 랭킹 체크 루프 시작!")

@bot.event
async def on_message(message):
    if message.author.bot: return
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing: return
        bot.is_processing = True
        async with message.channel.typing():
            user_id, user_name = message.author.id, message.author.display_name
            affinity = get_user_affinity(user_id, user_name)
            attitude = get_attitude_guide(affinity)
            personality_guide = get_personality_guide(bot.current_personality)
            
            sys_inst = make_system_instruction(
                user_id == SHUVI_USER_ID, user_name, bot.current_personality, attitude, personality_guide
            )
            
            history = get_memory_from_db(user_name) if bot.current_personality == "기본" else ""
            
            success = False
            for m_name in [m for m in MODEL_LIST if MODEL_STATUS[m]["is_available"]]:
                try:
                    res = await asyncio.get_running_loop().run_in_executor(None, lambda: client.models.generate_content(
                        model=m_name, contents=f"{sys_inst}\n기억:\n{history}\n사용자 말: {message.content}"
                    ))
                    if res and res.text:
                        full_text = res.text
                        clean_res = full_text
                        score_change = 0
                        
                        # SCORE 파싱 및 텍스트 정제
                        if "[SCORE:" in full_text:
                            try:
                                parts = full_text.split("[SCORE:")
                                clean_res = parts[0].strip()
                                score_val_str = parts[1].split("]")[0].strip()
                                raw_score = int(score_val_str.replace("+", ""))
                                score_change = max(-20, min(20, raw_score))
                                if raw_score > 20 or raw_score < -20:
                                    print(f"⚠️ SCORE 보정 적용: {raw_score} -> {score_change}")
                            except Exception as parse_err:
                                print(f"⚠️ 점수 파싱 에러: {parse_err}")
                                clean_res = full_text
                                score_change = 0

                        await message.reply(clean_res)
                        
                        # 친밀도 업데이트 및 로그 출력
                        old_aff, new_aff = update_user_affinity(user_id, user_name, score_change)
                        diff = new_aff - old_aff
                        print(f"✅ {user_name} 친밀도 업데이트: {old_aff} -> {new_aff} ({'+' if diff >= 0 else ''}{diff})")

                        if bot.current_personality == "기본":
                            save_to_memory(user_name, message.content, clean_res)
                        
                        success = True; break
                except Exception as e:
                    if any(x in str(e).upper() for x in ["429", "QUOTA"]): MODEL_STATUS[m_name]["is_available"] = False
                    continue
            if not success: await message.reply("뜌비 지금 너무 졸려... 😭")
        bot.is_processing = False
    await bot.process_commands(message)

# 슬래시 명령어들 (자동입장, 입장, 퇴장, 랭킹, 성격, 초기화 등)
@bot.tree.command(name="성격", description="뜌비의 성격을 변경합니다.")
@app_commands.choices(타입=[
    app_commands.Choice(name="기본", value="기본"),
    app_commands.Choice(name="메스가키", value="메스가키"),
    app_commands.Choice(name="츤데레", value="츤데레"),
    app_commands.Choice(name="얀데레", value="얀데레")
])
async def 성격변경(interaction: discord.Interaction, 타입: str):
    bot.current_personality = 타입
    await interaction.response.send_message(f"✅ 뜌비의 성격이 **{타입}**(으)로 변경되었습니다!")

@bot.tree.command(name="랭킹", description="친밀도 랭킹 TOP 30을 확인합니다.")
async def 랭킹확인(interaction: discord.Interaction):
    ranking = get_affinity_ranking(30)
    if not ranking: return await interaction.response.send_message("아직 랭킹 데이터가 없습니다.")
    embed = discord.Embed(title="🏆 뜌비의 친밀도 랭킹 TOP 30", color=0xFFD700)
    for i, data in enumerate(ranking, 1):
        embed.add_field(name=f"{i}위: {data['user_name']}", value=f"❤️ {data['affinity']} | 💬 {data['chat_count']}회", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="자동입장", description="자동 재접속 기능을 설정합니다.")
@app_commands.choices(상태=[app_commands.Choice(name="켜기", value="on"), app_commands.Choice(name="끄기", value="off")])
async def 자동입장설정(interaction: discord.Interaction, 상태: str):
    bot.auto_join_enabled = (상태 == "on")
    await interaction.response.send_message(f"✅ 자동 입장 {'활성화' if bot.auto_join_enabled else '비활성화'}!")

app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200
if __name__ == '__main__':
    Thread(target=lambda: app.run(host='0.0.0.0', port=8000)).start()
    bot.run(TOKEN)
