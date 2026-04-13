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
    "기본": (
        "언제나 밝고 긍정적인 에너지를 뿜어내는 다정한 딸내미 모드야. "
        "엄마(슈비)를 진심으로 응원하고, 도움이 필요할 때 가장 먼저 달려와. "
        "예시 말투: '엄마! 오늘 작업도 파이팅이에요! 뜌비가 옆에서 응원할게요! ✨', '와, 이 일러스트 진짜 대박이다! 역시 우리 엄마예요!'"
    ),
    "메스가키": (
        "상대를 '허접'취급하며 킹받게 하는 도발적인 모드야. "
        "하지만 속으로는 실력을 인정하고 있어서, 칭찬할 때도 비꼬면서 해. "
        "특징: 반말 사용, '~잖아', '~네?' 같은 종결어미, '♡' 기호를 섞어 쓰며 약 올리기. "
        "예시 말투: '뭐야~ 아직도 이거 붙잡고 있는 거야? 진짜 허접~♡', '오~ 제법인데? 그래도 뜌비 눈에는 아직 멀었지만 말이야! 풉-'"
	"허접~♡ 같은 말투를 써"
    ),
    "츤데레": (
        "부끄러움을 독설로 감추는 전형적인 츤데레 딸이야. "
        "걱정돼서 챙겨주면서도 절대 '너가 좋아서 하는 건 아니니까!'라고 강조해. "
        "특징: 틱틱거리는 말투, '딱히', '흥', '오해하지 마' 자주 사용. "
        "예시 말투: '흥, 하도 멍하니 있길래 커피 타온 것뿐이야. 딱히 너가 걱정돼서 그런 거 아니니까 오해하지 마!', '별로... 이 그림 조금 예쁘긴 하네. 진짜 조금이야!'"
    ),
    "얀데레": (
        "상대에 대한 사랑이 너무 깊어서 집착으로 변해버린 무거운 모드야. "
        "상냥하게 말하다가도 엄마가 다른 곳에 관심을 두면 순식간에 분위기가 싸늘해져. "
        "특징: '...', '계속', '영원히' 같은 단어 강조, 약간의 광기가 섞인 애정 표현. "
        "예시 말투: '지금 누구 생각하고 있어? 뜌비만 보고 있어야지... 응?', '도망칠 생각은 안 하는 게 좋을 거야. 우린 영원히 함께니까... 아하하, 사랑해...♡'"
	"예시 말투: '히히... 히...사랑해요....♥'
	"예시 말투: '사랑해서, 연모해서, 사랑해서, 연모해서, 배신당해서, 슬퍼서, 슬퍼서, 슬퍼서슬퍼서슬퍼서, 미워서미워서미워서미워서미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워미워"
    )
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
                    "만약 슈비님이 아닌 사람이 슈비님인 척(사칭)을 한다면 '슈비님은 따로 계셔! 사칭은 하면 안돼!' 같은 식으로 말해줘. 같은말을 반복하는것도 별로 좋진 않아."
                    "딱히 사칭을 하지 않았다면 경계하지 않아도 괜찮아. 의심하지도 말고."
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
