import discord
from discord.ext import commands, tasks
from datetime import datetime, time
from dotenv import load_dotenv
import os

# .env 파일에서 환경변수 불러오기
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 1228372760212930652
VOICE_CHANNEL_ID = 1358176930725236968

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ 봇 로그인됨: {bot.user}')
    control_voice_channel.start()

@tasks.loop(minutes=1)
async def control_voice_channel():
    now = datetime.now().time()
    guild = bot.get_guild(GUILD_ID)
    channel = guild.get_channel(VOICE_CHANNEL_ID)

    if guild is None or channel is None:
        print("⚠️ 서버 또는 채널을 찾을 수 없음")
        return

    everyone = guild.default_role
    study_role = discord.utils.get(guild.roles, name="스터디")

    if study_role is None:
        print("⚠️ '스터디' 역할을 찾을 수 없음")
        return

    # 항상 @everyone은 입장 불가
    await channel.set_permissions(everyone, connect=False)

    # 오후 6시 ~ 오후 9시 → '스터디' 역할 입장 허용
    if time(18, 0) <= now <= time(21, 0):
        await channel.set_permissions(study_role, connect=True)
        print("🟢 '스터디' 역할 입장 허용")
    else:
        await channel.set_permissions(study_role, connect=False)
        print("🔴 '스터디' 역할 입장 차단")

bot.run(TOKEN)
