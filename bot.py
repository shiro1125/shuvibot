import discord
from discord.ext import commands, tasks
from datetime import datetime, time
from dotenv import load_dotenv
import os
import pytz
from flask import Flask
from threading import Thread

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')

# .env 파일에서 환경변수 불러오기
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')  # 동일한 봇의 토큰
GUILD_ID_1 = 1228372760212930652  # 첫 번째 서버의 ID (스터디 기능)
GUILD_ID_2 = 1242686555982663691  # 두 번째 서버의 ID (공지 기능)
VOICE_CHANNEL_ID = 1358176930725236968  # 음성 채널 ID

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
    control_voice_channel.start()  # 스터디 기능 시작
    send_notifications.start()  # 수강생 공지 작업 시작

@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea).strftime('%Y-%m-%d %H:%M:%S')  # KST 기준 현재 시간 가져오기
    
    guild = bot.get_guild(GUILD_ID_1)
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

    # 한국 시간 기준으로 오후 6시 ~ 9시
    if time(18, 0) <= datetime.now(korea).time() <= time(21, 0):
        await channel.set_permissions(study_role, connect=True)
        await channel.edit(name="🟢 스터디")  # 음성 채팅 방 제목 변경
        print(f"🟢 '스터디' 역할 입장 허용 (현재 한국 시간: {now_korea})")
    else:
        await channel.set_permissions(study_role, connect=False)
        await channel.edit(name="🔴 스터디")  # 음성 채팅 방 제목 변경
        print(f"🔴 '스터디' 역할 입장 차단 (현재 한국 시간: {now_korea})")

@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)
    print(f"현재 시간: {now_korea.hour}:{now_korea.minute}")  # 현재 시간 출력

    # 매일 7시 20분에 수업 알림
    if now_korea.hour == 19 and now_korea.minute == 47:
        guild = bot.get_guild(GUILD_ID_2)  # 수강생 공지를 보낼 서버의 ID
        announcement_channel = discord.utils.get(guild.text_channels, name="공지")  # "공지" 채널 이름
        study_role = discord.utils.get(guild.roles, name="수강생")  # "수강생" 역할 찾기
        
        if announcement_channel and study_role:
            await announcement_channel.send(f"{study_role.mention} 📢 주간 수업 알림입니다!")  # 역할만 멘션
            print("📢 수업 알림 메시지를 보냈습니다.")


if __name__ == '__main__':
    # Flask 애플리케이션을 별도의 스레드에서 실행
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()

    bot.run(TOKEN)  # 동일한 봇의 토큰으로 실행
