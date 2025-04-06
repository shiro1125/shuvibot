import discord
from discord.ext import commands, tasks
from datetime import datetime
from dotenv import load_dotenv
import os
import pytz
from threading import Thread

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')

# .env 파일에서 환경변수 불러오기
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')  # 동일한 봇의 토큰
GUILD_ID_2 = 123456789012345678  # 두 번째 서버의 ID

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
    print(f'✅ 알림 봇 로그인됨: {bot.user}')
    send_notifications.start()  # 수강생 공지 작업 시작

@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)

    # 매일 7시 20분에 수업 알림
    if now_korea.hour == 19 and now_korea.minute == 20:
        guild = bot.get_guild(GUILD_ID_2)  # 수강생 공지를 보낼 서버의 ID
        announcement_channel = discord.utils.get(guild.text_channels, name="공지")  # "공지" 채널 이름
        study_role = discord.utils.get(guild.roles, name="수강생")  # "수강생" 역할 찾기
        
        if announcement_channel and study_role:
            mention_string = ' '.join([member.mention for member in study_role.members])  # 멘션 문자열 생성
            await announcement_channel.send(f"{mention_string} 📢 주간 수업 알림입니다!")  # 수업 알림 메시지
            print("📢 수업 알림 메시지를 보냈습니다.")

if __name__ == '__main__':
    # Flask 애플리케이션을 별도의 스레드에서 실행
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()

    bot.run(TOKEN)  # 동일한 봇의 토큰으로 실행
