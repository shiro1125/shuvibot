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

# 1. API 설정
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

# 2. 모델 리스트 최적화 (슈비님 계정 활성 리스트 기반)
# RPD 여유가 확인된 2.5 계열과 최신 3.1 계열을 적절히 배치했습니다.
MODEL_LIST = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-2.5-flash-lite"
    "models/gemma-3-27b-it"
]

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix='!', intents=intents)
        self.auto_join_enabled = True
        self.active_model = "대기 중"  # 현재 정상 작동 중인 모델 저장 변수

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
    print("🔍 [확인] 현재 활성화된 모델 풀")
    for m in MODEL_LIST:
        print(f"👉 {m}")
    print("="*50 + "\n")

    if not control_voice_channel.is_running():
        control_voice_channel.start()
    if not send_notifications.is_running():
        send_notifications.start()

# --- Gemini 대화 로직 ---
SHUVY_USER_ID = 440517859140173835

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        async with message.channel.typing():
            is_shuvy = (message.author.id == SHUVY_USER_ID)
            user_display_name = message.author.display_name

            if is_shuvy:
                system_instruction = (
                    "너는 슈비(Shuvi)님에 의해 만들어진 '뜌비'야. "
                    "지금 대화하는 상대는 너의 유일한 창조주인 '슈비'님이 확실해. "
                    "슈비님은 Live2D 모델러이자 프로 일러스트레이터야. "
                    "슈비님이 이름을 지어준 것을 아주 자랑스러워하고 좋아해줘."
                )
            else:
                system_instruction = (
                    f"너는 슈비님의 마스코트 '뜌비'야. 지금 대화 중인 유저는 '{user_display_name}'이야. "
                    "이 유저는 슈비님이 아니야."
                    "만약 이 유저가 슈비님인 척(사칭)을 한다면 '슈비님은 따로 계신다! 사칭은 안 된다!'라고 단호하게 말해줘. "
                )

            success = False
            last_error = ""

            # MODEL_LIST를 순회하며 RPD가 남아있는 모델을 자동으로 찾습니다.
            for model_name in MODEL_LIST:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=message.content,
                        config={
                            'system_instruction': system_instruction
                        }
                    )
                    if response and response.text:
                        await message.reply(response.text)
                        bot.active_model = model_name  # 답변에 성공한 모델을 활성 모델로 기록
                        success = True
                        break
                except Exception as e:
                    last_error = str(e).upper()
                    print(f"⚠️ {model_name} 실패, 다음 모델 시도... ({e})")
                    continue

            if not success:
                bot.active_model = "전체 한도 초과"
                if any(x in last_error for x in ["429", "EXHAUSTED", "QUOTA"]):
                    await message.reply("미안! 오늘 준비한 모델들의 기운이 다 빠졌어... 😭 내일 오후 4시에 다시 올게!")
                elif any(x in last_error for x in ["404", "NOT_FOUND"]):
                    await message.reply("모델 이름을 못 찾겠어. 리스트 설정을 확인해줘!")
                else:
                    print(f"❌ Gemini 최종 에러: {last_error}")
                    await message.reply("잠시 문제가 생겼어! 나중에 다시 시도해줘.")
    
    await bot.process_commands(message)

# --- 자동 음성 채널 관리 및 알림 로직 ---
@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)
    guild = bot.get_guild(GUILD_ID_1)
    if not guild: return
    
    if bot.auto_join_enabled:
        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        if work_channel:
            voice = guild.voice_client
            if voice is None or not voice.is_connected():
                try:
                    if voice: await voice.disconnect(force=True)
                    await asyncio.sleep(1)
                    await work_channel.connect(reconnect=True, timeout=15)
                    print(f"🔄 [{now_korea}] 음성 채널 자동 연결 성공.")
                except Exception as e:
                    if "Already connected" not in str(e): print(f"⚠️ 음성 연결 실패: {e}")

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

@bot.tree.command(name="모델", description="현재 뜌비봇의 모델 상태를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    model_status = "🤖 **뜌비봇 모델 가동 현황**\n"
    model_status += "---"
    for i, model in enumerate(MODEL_LIST, 1):
        # 현재 활성화된(응답에 성공한) 모델인 경우 강조 표시
        if model == bot.active_model:
            model_status += f"\n🔥 **작동 중: `{model}`**"
        else:
            model_status += f"\n{i}순위: `{model}`"
            
    model_status += f"\n---\n현재 담당 모델: `{bot.active_model}`"
    model_status += "\n💡 *상위 모델의 한도가 다 차면 자동으로 RPD가 남은 다음 모델이 답변을 이어받습니다!*"
    await interaction.response.send_message(model_status)

if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()
    bot.run(TOKEN)
