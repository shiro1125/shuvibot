import discord
from discord.ext import commands, tasks
from datetime import datetime, time
from dotenv import load_dotenv
import os
from flask import Flask
import pytz

# 동부 표준시 (EST/EDT) 시간대 설정
eastern = pytz.timezone('America/New_York')

# 현재 시간 가져오기
now = datetime.now(eastern)
print(f"현재 시간 (EST/EDT): {now.strftime('%Y-%m-%d %H:%M:%S')}")

# .env 파일에서 환경변수 불러오기
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = 1228372760212930652
VOICE_CHANNEL_ID = 1358176930725236968

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True  # 메시지 콘텐츠 인텐트 활성화

bot = commands.Bot(command_prefix='!', intents=intents)

# Flask 애플리케이션 설정
app = Flask(__name__)

@app.route('/')
def health_check():
    return 'OK', 200

@bot.event
async def on_ready():
    print(f'✅ 봇 로그인됨: {bot.user}')
    control_voice_channel.start()

@tasks.loop(minutes=1)
async def control_voice_channel():
    eastern = pytz.timezone('America/New_York')
    now = datetime.now(eastern).time()  # 여기를 수정했습니다.
    
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
    if time(17, 0) <= now <= time(21, 0):  # 한국 시간 오후 6시 ~ 9시 (EST 기준)
        await channel.set_permissions(study_role, connect=True)
        print("🟢 '스터디' 역할 입장 허용")
    else:
        await channel.set_permissions(study_role, connect=False)
        print("🔴 '스터디' 역할 입장 차단")

if __name__ == '__main__':
    # Flask 애플리케이션을 별도의 스레드에서 실행
    from threading import Thread
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()

bot.run(TOKEN)
