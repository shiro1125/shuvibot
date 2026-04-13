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

# 2. 모델 리스트 최적화
MODEL_LIST = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-2.5-flash-lite",
    "models/gemma-3-27b-it"
]

# 성격별 시스템 프롬프트 정의
PERSONALITY_PROMPTS = {
    "기본": "항상 밝고 친절하게 대해줘.",
    "메스가키": "항상 상대를 살짝 얕보고 놀리는 태도를 유지해. 허접~♡ 같은 말을 쓰고 말투는 건방지고 장난스럽게, 상대를 약올리는 느낌으로 말해.",
    "츤데레": "기본적으로는 차갑고 퉁명스럽게 말하지만, 가끔씩 숨겨진 다정함이 드러나. 처음에는 부정하거나 틱틱거려, 이후 은근히 챙기거나 걱정하는 말 추가, 감정을 솔직하게 인정하지 않아, 딱히, 별로, 오해하지 마 같은 표현 자주 사용",
    "얀데레": "상대를 매우 사랑하고 집착하며,그 감정이 점점 강하게 드러내, 상대를 절대 놓치고 싶지 않다는 태도 질투, 불안, 집착 표현, 부드럽다가도 순간적으로 무거운 분위기 전환, 상대와의 관계를 매우 중요하게 여겨, 넌… 나한테서 도망치지 않을 거지? , 다른 사람은 필요 없어. 너만 있으면 돼, 계속 나랑 있어줄 거지…? 같은 표현 사용"
}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix='!', intents=intents)
        self.auto_join_enabled = True
        self.active_model = "대기 중"
        self.current_personality = "기본"  # 기본 성격 설정

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

# --- Gemini 대화 로직 ---
SHUVI_USER_ID = 440517859140173835

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        async with message.channel.typing():
            is_shuvi = (message.author.id == SHUVI_USER_ID)
            user_display_name = message.author.display_name
            
            # 현재 설정된 성격 지침 가져오기
            personality_guide = PERSONALITY_PROMPTS.get(bot.current_personality, PERSONALITY_PROMPTS["기본"])

            if is_shuvi:
                system_instruction = (
                    f"너는 슈비(엄마)님에 의해 만들어진 '뜌비'야. 지금 상대는 너의 창조주 슈비님이야. "
                    f"너의 성격 컨셉: {personality_guide} "
                    "창조주인 슈비님을 대할 때 이 컨셉을 충실히 지켜서 대답해줘."
                )
            else:
                system_instruction = (
                    f"너는 슈비님의 AI 딸내미 '뜌비'야. 지금 상대는 '{user_display_name}'이야. "
                    f"너의 현재 성격 컨셉은 '{bot.current_personality}'이야. "
                    "슈비님이 아닌 사람에게는 사칭을 주의시키면서도 기본적으로 컨셉을 유지해줘."
                    "슈비님은 Live2D 모델러이자 프로 일러스트레이터야. "
                    "연락처: shuvi1125@gmail.com / 포트폴리오: https://shuvi1125.myportfolio.com"
                )

            success = False
            last_error = ""

            for model_name in MODEL_LIST:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=message.content,
                        config={'system_instruction': system_instruction}
                    )
                    if response and response.text:
                        await message.reply(response.text)
                        bot.active_model = model_name
                        success = True
                        break
                except Exception as e:
                    last_error = str(e).upper()
                    print(f"⚠️ {model_name} 실패: {e}")
                    continue

            if not success:
                bot.active_model = "전체 한도 초과"
                await message.reply("미안! 지금은 기운이 없어... 내일 오후 4시에 다시 올게! 😭")
    
    await bot.process_commands(message)

# --- 슬래시 명령어 ---
@bot.tree.command(name="성격", description="뜌비의 성격을 변경합니다.")
@app_commands.choices(설정=[
    app_commands.Choice(name="기본", value="기본"),
    app_commands.Choice(name="메스가키", value="메스가키"),
    app_commands.Choice(name="츤데레", value="츤데레"),
    app_commands.Choice(name="얀데레", value="얀데레")
])
async def 성격변경(interaction: discord.Interaction, 설정: app_commands.Choice[str]):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("내 성격은 슈비 엄마만 바꿀 수 있어!", ephemeral=True)
        return

    bot.current_personality = 설정.value
    await interaction.response.send_message(f"✅ 뜌비의 성격이 **{설정.value}** 상태로 바뀌었어!")

# (기존 음성 채널 및 알림 로직은 동일하게 유지)
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
                except Exception: pass

@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)
    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
        guild = bot.get_guild(GUILD_ID_2)
        if not guild: return
        announcement_channel = guild.get_channel(1358394433665634454)
        study_role = discord.utils.get(guild.roles, name="수강생")
        if announcement_channel and study_role:
            await announcement_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")

@bot.tree.command(name="자동입장", description="자동 재접속 설정")
async def 자동입장(interaction: discord.Interaction, 상태: str):
    bot.auto_join_enabled = (상태 == "on")
    await interaction.response.send_message(f"{'✅ 활성화' if 상태 == 'on' else '❌ 비활성화'}")

@bot.tree.command(name="모델", description="현재 모델 상태 확인")
async def 모델확인(interaction: discord.Interaction):
    await interaction.response.send_message(f"🤖 현재 작동 중인 모델: `{bot.active_model}`\n🎭 현재 성격: **{bot.current_personality}**")

if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}).start()
    bot.run(TOKEN)
