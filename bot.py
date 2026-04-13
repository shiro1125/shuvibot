import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import os
import pytz
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
import google.generativeai as genai

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')

# 환경변수 불러오기
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')
GUILD_ID_1 = 1228372760212930652 
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968 
WORK_CHANNEL_ID = 1296431232045027369
# 💬 뜌비봇과 수다 떨 채널 ID
CHAT_CHANNEL_ID = 1228378104662196254 

# Gemini 설정
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-3-flash')

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True 
        super().__init__(command_prefix='!', intents=intents)
        self.auto_join_enabled = True

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ 뜌비봇 대화 모드 및 자동 입장 시스템 가동!")

bot = MyBot()
app = Flask(__name__)

@app.route('/')
def health_check(): return 'OK', 200

# --- 🤖 실시간 대화 기능 (on_message) ---

@bot.event
async def on_message(message):
    # 봇 본인의 메시지는 무시
    if message.author == bot.user:
        return

    # 지정된 채널이거나 봇이 언급되었을 때만 응답
    if message.channel.id == CHAT_CHANNEL_ID or bot.user.mentioned_in(message):
        async with message.channel.typing():
            try:
                # 뜌비봇 페르소나 설정
                prompt = (
                    f"너는 일러스트레이터 슈비님의 유능한 비서 '뜌비봇'이야. "
                    f"말투는 귀엽고 친절하게, 말 끝에는 무조건 '~뜌비'를 붙여줘. "
                    f"답변은 너무 길지 않게 핵심만 말해줘. 질문: {message.content}"
                )
                response = model.generate_content(prompt)
                
                answer = response.text
                if len(answer) > 1900: answer = answer[:1900] + "...(너무 길다뜌비!)"
                
                await message.reply(answer)
            except Exception as e:
                print(f"Gemini Error: {e}")

    await bot.process_commands(message)

# --- ⚙️ 슬래시 명령어 및 루프 설정 ---

@bot.event
async def on_ready():
    print(f'✅ 봇 로그인 완료: {bot.user}')
    if not control_voice_channel.is_running(): control_voice_channel.start()
    if not send_notifications.is_running(): send_notifications.start()

@bot.tree.command(name="자동입장", description="작업방 자동 재접속 기능을 켜거나 끕니다.")
@app_commands.choices(상태=[
    app_commands.Choice(name="켜기 (On)", value="on"),
    app_commands.Choice(name="끄기 (Off)", value="off")
])
async def 자동입장(interaction: discord.Interaction, 상태: str):
    if 상태 == "on":
        bot.auto_join_enabled = True
        await interaction.response.send_message("✅ 이제 튕겨도 작업방으로 다시 돌아온다뜌비!")
    else:
        bot.auto_join_enabled = False
        if interaction.guild.voice_client: await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("❌ 자동 입장 기능을 껐다뜌비. 이제 자유다뜌비!")

@bot.tree.command(name="입장", description="봇을 현재 채널이나 작업방으로 부릅니다.")
async def 입장(interaction: discord.Interaction):
    channel = interaction.user.voice.channel if interaction.user.voice else bot.get_guild(GUILD_ID_1).get_channel(WORK_CHANNEL_ID)
    if channel:
        if interaction.guild.voice_client: await interaction.guild.voice_client.move_to(channel)
        else: await channel.connect()
        await interaction.response.send_message(f"✅ {channel.name} 입장 완료뜌비!")
    else: await interaction.response.send_message("⚠️ 입장할 채널이 없다뜌비.")

@bot.tree.command(name="퇴장", description="봇을 음성 채널에서 퇴장시킵니다.")
async def 퇴장(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 다음에 또 보자뜌비!")
    else: await interaction.response.send_message("❌ 지금 채널에 없다뜌비.")

@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return

    # 자동 입장 로직
    if bot.auto_join_enabled:
        work_ch = guild.get_channel(WORK_CHANNEL_ID)
        if work_ch and guild.voice_client is None:
            try: await work_ch.connect()
            except: pass

    # 스터디 채널 관리 로직
    study_ch = guild.get_channel(STUDY_CHANNEL_ID)
    if study_ch:
        everyone = guild.default_role
        study_role = discord.utils.get(guild.roles, name="스터디")
        if study_role:
            await study_ch.set_permissions(everyone, connect=False)
            if time(18, 0) <= now_korea.time() <= time(23, 0):
                await study_ch.set_permissions(study_role, connect=True)
                if study_ch.name != "🟢 스터디": await study_ch.edit(name="🟢 스터디")
            else:
                await study_ch.set_permissions(study_role, connect=False)
                if study_ch.name != "🔴 스터디": await study_ch.edit(name="🔴 스터디")

@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)
    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
        week = (now_korea.day - 1) // 7 + 1
        guild = bot.get_guild(GUILD_ID_2)
        ann_ch = guild.get_channel(1358394433665634454)
        role = discord.utils.get(guild.roles, name="수강생")
        if ann_ch and role:
            msg = "이번주는 휴강입니다." if week == 5 else f"{role.mention} 📢 수업 10분전 입니다!"
            await ann_ch.send(msg)

if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()
    bot.run(TOKEN)
