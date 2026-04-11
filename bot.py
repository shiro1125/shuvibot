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
GUILD_ID_2 = 1170313139225640972  # 두 번째 서버의 ID (공지 기능)
VOICE_CHANNEL_ID = 1358176930725236968  # 음성 채널 ID

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True  # 메시지 콘텐츠 인텐트 활성화

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
async def 입장(ctx):
    # 명령어를 친 사람이 음성 채널에 있는지 확인
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        # 봇이 이미 다른 곳에 연결되어 있다면 이동, 아니면 접속
        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f"✅ {channel.name} 채널에 입장했습니다!")
    else:
        # 사용자가 음성 채널에 없을 경우, 특정 ID의 채널로 입장 시도
        guild = bot.get_guild(GUILD_ID_1)
        channel = guild.get_channel(VOICE_CHANNEL_ID)
        if channel:
            await channel.connect()
            await ctx.send(f"✅ 설정된 스터디 채널({channel.name})에 입장했습니다!")
        else:
            await ctx.send("⚠️ 먼저 음성 채널에 들어가 있거나, 채널 ID를 확인해주세요.")

@bot.command()
async def 퇴장(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 음성 채널에서 퇴장했습니다.")
    else:
        await ctx.send("❌ 봇이 음성 채널에 있지 않습니다.")



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
    if time(18, 0) <= datetime.now(korea).time() <= time(23, 0):  # KST 기준
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

    # 매주 토요일 5시 50분에 알림
    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:  # 5:50 PM
        month = now_korea.month
        week_number = (now_korea.day - 1) // 7 + 1  # 주차 계산

        guild = bot.get_guild(GUILD_ID_2)  # 수강생 공지를 보낼 서버의 ID
        announcement_channel_id = 1358394433665634454  # 공지 채널의 ID로 수정
        announcement_channel = guild.get_channel(announcement_channel_id)  # 채널 ID로 찾기
        study_role = discord.utils.get(guild.roles, name="수강생")  # "수강생" 역할 찾기
        
        if announcement_channel and study_role:
            if week_number == 5:  # 5주차인 경우
                await announcement_channel.send("이번주는 휴강입니다.")  # 휴강 메시지 (멘션 없음)
            else:
                await announcement_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")  # 수업 알림 메시지
            print("📢 알림 메시지를 보냈습니다.")



if __name__ == '__main__':
    # Flask 애플리케이션을 별도의 스레드에서 실행
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()

    bot.run(TOKEN)  # 동일한 봇의 토큰으로 실행
