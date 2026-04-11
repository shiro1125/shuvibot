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
VOICE_CHANNEL_ID = 1358176930725236968  # 음성 채널 ID

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        # 슬래시 명령어를 디스코드 서버에 등록(동기화)하는 중요한 단계입니다.
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

@bot.tree.command(name="입장", description="봇을 음성 채널로 부릅니다.")
async def 입장(interaction: discord.Interaction):
    # 슬래시 명령어에서는 ctx 대신 interaction을 사용합니다.
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect()
        await interaction.response.send_message(f"✅ {channel.name} 채널에 입장했습니다!")
    else:
        guild = bot.get_guild(GUILD_ID_1)
        channel = guild.get_channel(VOICE_CHANNEL_ID)
        if channel:
            await channel.connect()
            await interaction.response.send_message(f"✅ 설정된 스터디 채널({channel.name})에 입장했습니다!")
        else:
            await interaction.response.send_message("⚠️ 입장할 음성 채널을 찾을 수 없습니다.")

@bot.tree.command(name="퇴장", description="봇을 음성 채널에서 내보냅니다.")
async def 퇴장(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 음성 채널에서 퇴장했습니다.")
    else:
        await interaction.response.send_message("❌ 봇이 음성 채널에 있지 않습니다.")

# --- 기존 루프 기능 (그대로 유지) ---

@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    guild = bot.get_guild(GUILD_ID_1)
    channel = guild.get_channel(VOICE_CHANNEL_ID)

    if guild is None or channel is None: return

    everyone = guild.default_role
    study_role = discord.utils.get(guild.roles, name="스터디")
    if study_role is None: return

    await channel.set_permissions(everyone, connect=False)

    if time(18, 0) <= now_korea.time() <= time(23, 0):
        await channel.set_permissions(study_role, connect=True)
        if channel.name != "🟢 스터디":
            await channel.edit(name="🟢 스터디")
    else:
        await channel.set_permissions(study_role, connect=False)
        if channel.name != "🔴 스터디":
            await channel.edit(name="🔴 스터디")

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
