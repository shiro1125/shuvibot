import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import os
import pytz
from flask import Flask
from threading import Thread
from dotenv import load_dotenv

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')

# .env 파일에서 환경변수 불러오기
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID_1 = 1228372760212930652  # 스터디 기능 서버
GUILD_ID_2 = 1170313139225640972  # 공지 기능 서버
STUDY_CHANNEL_ID = 1358176930725236968  # 스터디 채널 ID (권한 관리용)
WORK_CHANNEL_ID = 1296431232045027369   # 작업방 채널 ID (자동 입장용)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        # 자동 입장 상태 저장 변수 (기본값: On)
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
    if not control_voice_channel.is_running():
        control_voice_channel.start()
    if not send_notifications.is_running():
        send_notifications.start()

# --- 슬래시 명령어 정의 ---

@bot.tree.command(name="자동입장", description="봇의 음성 채널 자동 재접속 기능을 켜거나 끕니다.")
@app_commands.describe(상태="자동 입장을 켤지(on) 끌지(off) 선택하세요.")
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
        await interaction.response.send_message("❌ 자동 입장 기능을 껐습니다. 봇이 채널에서 퇴장합니다.")

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
        await interaction.response.send_message("👋 음성 채널에서 퇴장했습니다.")
    else:
        await interaction.response.send_message("❌ 봇이 음성 채널에 있지 않습니다.")

# --- 매 분마다 실행되는 루프 기능 ---

@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    guild = bot.get_guild(GUILD_ID_1)
    
    # 1. 자동 입장 로직 (작업방 대상)
    if bot.auto_join_enabled:
        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        if work_channel and guild.voice_client is None:
            try:
                await work_channel.connect()
                print(f"🔄 [{now_korea}] 자동 재접속: 작업방 입장 완료.")
            except Exception as e:
                print(f"⚠️ 재접속 실패: {e}")

    # 2. 스터디 채널 권한 및 이름 관리
    study_channel = guild.get_channel(STUDY_CHANNEL_ID)
    if guild and study_channel:
        everyone = guild.default_role
        study_role = discord.utils.get(guild.roles, name="스터디")
        
        if study_role:
            await study_channel.set_permissions(everyone, connect=False)
            if time(18, 0) <= now_korea.time() <= time(23, 0):
                await study_channel.set_permissions(study_role, connect=True)
                if study_channel.name != "🟢 스터디":
                    await study_channel.edit(name="🟢 스터디")
            else:
                await study_channel.set_permissions(study_role, connect=False)
                if study_channel.name != "🔴 스터디":
                    await study_channel.edit(name="🔴 스터디")

@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)
    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
        week_number = (now_korea.day - 1) // 7 + 1
        guild = bot.get_guild(GUILD_ID_2)
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
