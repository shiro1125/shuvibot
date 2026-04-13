import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import os
import pytz
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369

# 1. 다시 v1beta 통로로 돌아갑니다 (슈비님 계정 맞춤형)
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'} # 다시 beta로 변경
)

# 이름을 리스트에 있던 가장 안정적인 'gemini-2-flash'로 변경합니다.
MODEL_ID = "models/gemini-3-flash-preview"

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix='!', intents=intents)
        self.auto_join_enabled = True

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ 슬래시 명령어 동기화 완료!")

bot = MyBot()
app = Flask(__name__)

@app.route('/')
def health_check():
    return 'OK', 200
@bot.event
async def on_ready():
    print(f'✅ 봇 로그인됨: {bot.user}')
    
    print("\n" + "="*50)
    print("🔍 [최종 확인] 슈비님 계정 모델 본명 리스트")
    try:
        # 조건 없이 모든 모델의 이름을 출력합니다.
        models = client.models.list()
        for m in models:
            print(f"👉 {m.name}") # m.name만 출력해서 에러 소지를 없앴습니다.
    except Exception as e:
        print(f"❌ 목록 출력 실패: {e}")
    print("="*50 + "\n")

    if not control_voice_channel.is_running():
        control_voice_channel.start()
    if not send_notifications.is_running():
        send_notifications.start()
# --- Gemini 대화 (on_message) ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # 멘션이나 '뜌비' 단어 포함 시 대답
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        try:
            async with message.channel.typing():
                # v1 통로를 통해 Gemini 3 모델 호출
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=message.content
                )
                if response and response.text:
                    await message.reply(response.text)
        except Exception as e:
            print(f"❌ Gemini 에러: {e}")
            await message.reply(f"미안! 에러가 났어: {e}")
    
    await bot.process_commands(message)

# --- 슬래시 명령어 정의 ---

@bot.tree.command(name="자동입장", description="봇의 음성 채널 자동 재접속 기능을 켜거나 끕니다.")
@app_commands.choices(상태=[
    app_commands.Choice(name="켜기 (On)", value="on"),
    app_commands.Choice(name="끄기 (Off)", value="off")
])
async def 자동입장(interaction: discord.Interaction, 상태: str):
    if 상태 == "on":
        bot.auto_join_enabled = True
        await interaction.response.send_message("✅ 이제부터 봇이 작업방에 자동으로 입장합니다.")
    else:
        bot.auto_join_enabled = False
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("❌ 자동 입장 기능을 껐습니다.")

@bot.tree.command(name="입장", description="봇을 현재 채널이나 작업방으로 부릅니다.")
async def 입장(interaction: discord.Interaction):
    if interaction.user.voice:
        channel = interaction.user.voice.channel
    else:
        guild = bot.get_guild(GUILD_ID_1)
        channel = guild.get_channel(WORK_CHANNEL_ID)
    
    if channel:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        await interaction.response.send_message(f"✅ {channel.name} 채널에 입장했습니다!")
    else:
        await interaction.response.send_message("⚠️ 채널을 찾을 수 없습니다.")

@bot.tree.command(name="퇴장", description="봇을 음성 채널에서 내보냅니다.")
async def 퇴장(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 퇴장했습니다.")
    else:
        await interaction.response.send_message("❌ 음성 채널에 있지 않습니다.")

# --- 매 분마다 실행되는 루프 기능 ---
@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return
    
    if bot.auto_join_enabled:
        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        if work_channel:
            # 1. 봇의 현재 음성 상태(voice_client)를 가져옵니다.
            voice = guild.voice_client
            
            # 2. 연결이 '아예 없거나' 혹은 '연결이 끊어진 상태'일 때만 접속 시도
            if voice is None or not voice.is_connected():
                try:
                    await work_channel.connect(reconnect=True, timeout=10)
                    print(f"🔄 [{now_korea}] 음성 채널 연결 성공!")
                except Exception as e:
                    # 이미 연결되었다는 에러(Already connected)는 무시하도록 예외 처리
                    if "Already connected" not in str(e):
                        print(f"⚠️ 음성 연결 실패: {e}")
            else:
                # 이미 잘 연결되어 있다면 로그를 남기지 않고 그냥 넘어갑니다.
                pass

    # 2. 스터디 채널 관리
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
async def send_notifications():
    now_korea = datetime.now(korea)
    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
        week_number = (now_korea.day - 1) // 7 + 1
        guild = bot.get_guild(GUILD_ID_2)
        if not guild: return
        announcement_channel = guild.get_channel(1358394433665634454)
        study_role = discord.utils.get(guild.roles, name="수강생")
        if announcement_channel and study_role:
            if week_number == 5:
                await announcement_channel.send("이번주는 휴강입니다.")
            else:
                await announcement_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")

if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()
    bot.run(TOKEN)
