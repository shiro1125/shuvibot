import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import os
import pytz
import asyncio
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

# 1. API 설정 (v1beta 통로 사용)
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

# 2. 슈비님 리스트 기반 무한 동력 모델 리스트
MODEL_LIST = [
    "models/gemini-3.1-pro-preview",
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-pro",
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash",
    "models/gemini-flash-latest"
]

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
    
    # 현재 사용 가능한 모델 리스트 출력 (확인용)
    print("\n" + "="*50)
    print("🔍 [확인] 현재 활성화된 모델 풀")
    for m in MODEL_LIST:
        print(f"👉 {m}")
    print("="*50 + "\n")

    if not control_voice_channel.is_running():
        control_voice_channel.start()
    if not send_notifications.is_running():
        send_notifications.start()

슈비님, 뜌비의 정체성과 말투를 확실하게 고정하고, 한도가 다 차면 자동으로 다른 모델로 넘어가는 '무한 동력 뜌비' 전체 코드를 정리해 드릴게요.

이 코드는 슈비님이 80여 개의 모델을 제작한 전문가라는 점을 뜌비가 기억하게 하고, 어떤 상황에서도 귀여운 말투를 유지하도록 설계되었습니다.

🛠️ 뜌비봇 최종 통합 코드 (정체성 & 돌려막기 포함)
Python
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import os
import pytz
import asyncio
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

# 1. API 설정 (v1beta 통로 사용)
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

# 2. 슈비님 리스트 기반 무한 동력 모델 리스트
MODEL_LIST = [
    "models/gemini-3.1-pro-preview",
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-pro",
    "models/gemini-2.5-flash",
    "models/gemini-2.0-flash",
    "models/gemini-flash-latest"
]

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
    if not control_voice_channel.is_running():
        control_voice_channel.start()
    if not send_notifications.is_running():
        send_notifications.start()

# --- [핵심] Gemini 정체성 고정 및 돌려막기 로직 ---
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        async with message.channel.typing():
            success = False
            last_error = ""

            for model_name in MODEL_LIST:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=message.content,
                        # [기억 심기] 뜌비의 정체성과 슈비님의 정보를 여기에 입력합니다.
                        config={
                            'system_instruction': (
                                "너의 이름은'뜌비'고 너를 만든 사람은 '슈비'야. "
                                "슈비님은 80개 이상의 모델을 제작한 베테랑 Live2D 모델러이자 프로 일러스트레이터야. "
                                "너의 특징은 다음과 같아:"
                                "1. 말투: 항상 밝고 친절해."
                                "2. 주의: 절대 텔레토비나 다른 캐릭터로 자신을 소개하지 마. "
                                "슈비님이 '네 이름이 뜌비야'라고 하면, 문법 설명 대신 슈비님이 지어준 이름이라며 좋아해줘."
                            )
                        }
                    )
                    if response and response.text:
                        await message.reply(response.text)
                        success = True
                        break  # 성공하면 루프 탈출
                except Exception as e:
                    last_error = str(e).upper()
                    print(f"⚠️ {model_name} 실패, 다음 모델 시도... ({e})")
                    continue

            # 모든 모델 실패 시 에러 처리
            if not success:
                if any(x in last_error for x in ["429", "EXHAUSTED", "QUOTA"]):
                    await message.reply("미안! 오늘 준비한 모든 모델의 기운이 다 빠졌어... 😭 내일 오후 4시에 다시 충전해서 올게!")
                else:
                    print(f"❌ Gemini 최종 에러: {last_error}")
                    await message.reply("잠시 문제가 생겼어! 나중에 다시 시도해줘.")
    
    await bot.process_commands(message)
# --- 음성 및 알림 루프 (안정화 버전) ---
@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return
    
    if bot.auto_join_enabled:
        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        if work_channel:
            voice = guild.voice_client
            
            # 연결이 없거나 끊긴 상태일 때만 접속 시도
            if voice is None or not voice.is_connected():
                try:
                    # 찌꺼기 연결 정리 후 접속
                    if voice: 
                        await voice.disconnect(force=True)
                        await asyncio.sleep(1)
                    
                    await work_channel.connect(reconnect=True, timeout=15)
                    print(f"🔄 [{now_korea}] 음성 채널 자동 연결 성공.")
                except Exception as e:
                    if "Already connected" not in str(e):
                        print(f"⚠️ 음성 연결 실패: {e}")

    # 스터디 채널 관리
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

# --- 슬래시 명령어들 ---
@bot.tree.command(name="자동입장", description="자동 재접속 기능을 설정합니다.")
@app_commands.choices(상태=[
    app_commands.Choice(name="켜기 (On)", value="on"),
    app_commands.Choice(name="끄기 (Off)", value="off")
])
async def 자동입장(interaction: discord.Interaction, 상태: str):
    bot.auto_join_enabled = (상태 == "on")
    if 상태 == "off" and interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message(f"{'✅ 자동 입장 활성화' if 상태 == 'on' else '❌ 자동 입장 비활성화'}")

@bot.tree.command(name="입장", description="봇을 음성 채널로 부릅니다.")
async def 입장(interaction: discord.Interaction):
    channel = interaction.user.voice.channel if interaction.user.voice else bot.get_guild(GUILD_ID_1).get_channel(WORK_CHANNEL_ID)
    if channel:
        if interaction.guild.voice_client: await interaction.guild.voice_client.move_to(channel)
        else: await channel.connect()
        await interaction.response.send_message(f"✅ {channel.name} 입장!")
    else:
        await interaction.response.send_message("⚠️ 입장할 채널을 찾을 수 없습니다.")

@bot.tree.command(name="퇴장", description="봇을 음성 채널에서 내보냅니다.")
async def 퇴장(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 퇴장!")
    else:
        await interaction.response.send_message("❌ 연결된 음성 채널이 없습니다.")

@bot.tree.command(name="모델", description="현재 뜌비봇이 사용 중인 모델 리스트와 우선순위를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    model_status = "🤖 **뜌비봇 모델 가동 현황**\n"
    model_status += "---"
    
    for i, model in enumerate(MODEL_LIST, 1):
        # 가장 위에 있는 모델이 현재 1순위로 시도되는 모델입니다.
        prefix = "✅ **현재 1순위**" if i == 1 else f"{i}순위"
        model_status += f"\n{prefix}: `{model}`"
    
    model_status += "\n---\n💡 *상위 모델의 한도가 다 차면 자동으로 다음 모델이 답변을 이어받습니다!*"
    
    await interaction.response.send_message(model_status)


if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()
    bot.run(TOKEN)
