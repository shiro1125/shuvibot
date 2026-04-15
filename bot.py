import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

# 외부 모듈 임포트 (기능 분리)
from personality import make_system_instruction
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide, 
    get_memory_from_db, save_to_memory, get_top_ranker_id
)
from scheduler import setup_scheduler, RANK_1_ROLE_ID, GUILD_ID_1

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SHUVI_USER_ID = 440517859140173835

# Gemini API 설정
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})
MODEL_LIST = [
    "models/gemini-3-flash-preview", 
    "models/gemini-2.5-flash", 
    "models/gemini-3.1-flash-lite-preview"
]
MODEL_STATUS = {model: {"is_available": True} for model in MODEL_LIST}

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix='!', intents=intents)
        
        self.auto_join_enabled = True
        self.is_processing = False
        self.current_personality = "기본"
        self.active_model = "대기 중"

    async def setup_hook(self):
        # 1. 외부 기능(블랙잭, TTS) 로드
        for ext in ['tts', 'blackjack']:
            try:
                await self.load_extension(ext)
                print(f"✅ {ext} 확장 로드 완료!")
            except Exception as e:
                print(f"❌ {ext} 로드 실패: {e}")
        
        # 2. 스케줄러(스터디 관리, 수업 알림) 등록 및 시작
        self.study_loop, self.notif_loop = setup_scheduler(self)
        self.study_loop.start()
        self.notif_loop.start()
        
        # 3. 랭킹 체크 루프 시작
        self.rank_update_loop.start()
        
        await self.tree.sync()
        print("✅ 모든 명령어 및 루프 동기화 완료!")

    @tasks.loop(hours=1)
    async def rank_update_loop(self):
        """실시간 친밀도 1위 역할 부여 로직"""
        guild = self.get_guild(GUILD_ID_1)
        if not guild: return
        
        top_id = get_top_ranker_id()
        role = guild.get_role(RANK_1_ROLE_ID)
        if role and top_id:
            # 현재 역할을 가진 사람과 1위가 다를 경우에만 갱신
            if role.members and role.members[0].id == top_id:
                return
            for member in role.members:
                await member.remove_roles(role)
            winner = guild.get_member(top_id)
            if winner:
                await winner.add_roles(role)

bot = MyBot()

# --- 메시지 이벤트 (뜌비 대화 엔진) ---

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # 뜌비 언급 또는 키워드 포함 시 대화 시작
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing: return
        bot.is_processing = True
        
        async with message.channel.typing():
            uid, uname = message.author.id, message.author.display_name
            is_shuvi = (uid == SHUVI_USER_ID)
            
            # 사용자 데이터 로드
            affinity = get_user_affinity(uid, uname)
            attitude = get_attitude_guide(affinity)
            sys_inst = make_system_instruction(is_shuvi, uname, bot.current_personality, attitude)
            history = get_memory_from_db(uname) if bot.current_personality == "기본" else ""
            
            content = f"과거 대화:\n{history}\n\n유저 메시지: {message.content}" if history else message.content

            success = False
            for m_name in [m for m in MODEL_LIST if MODEL_STATUS[m]["is_available"]]:
                try:
                    bot.active_model = m_name
                    # Gemma 모델 대응용 설정 (필요 시)
                    cfg = {} if "gemma" in m_name.lower() else {'system_instruction': sys_inst}
                    prompt = f"[지침]\n{sys_inst}\n\n{content}" if "gemma" in m_name.lower() else content
                    
                    res = await asyncio.get_running_loop().run_in_executor(
                        None, lambda: client.models.generate_content(model=m_name, contents=prompt, config=cfg)
                    )
                    
                    if res and res.text:
                        # 점수 태그 제거 후 답변
                        reply_text = res.text.split("[SCORE:")[0].strip()
                        await message.reply(reply_text)
                        
                        # 점수 추출 및 친밀도 업데이트
                        if "[SCORE:" in res.text:
                            try:
                                score = int(res.text.split("[SCORE:")[1].split("]")[0].replace("+",""))
                                update_user_affinity(uid, uname, score)
                            except: pass
                        
                        if bot.current_personality == "기본":
                            save_to_memory(uname, message.content, reply_text)
                        success = True
                        break
                except Exception as e:
                    if any(x in str(e).upper() for x in ["429", "QUOTA"]):
                        MODEL_STATUS[m_name]["is_available"] = False
                    continue
            
            if not success:
                await message.reply("뜌비 지금 너무 졸려... 나중에 다시 불러줘! 😭")
        
        bot.is_processing = False
    
    await bot.process_commands(message)

# --- 슬래시 명령어 세트 ---

@bot.tree.command(name="성격", description="뜌비의 성격을 바꿉니다.")
@app_commands.choices(설정=[
    app_commands.Choice(name="기본", value="기본"),
    app_commands.Choice(name="메스가키", value="메스가키"),
    app_commands.Choice(name="츤데레", value="츤데레"),
    app_commands.Choice(name="얀데레", value="얀데레")
])
async def set_personality(it: discord.Interaction, 설정: app_commands.Choice[str]):
    if it.user.id != SHUVI_USER_ID:
        return await it.response.send_message("창조주 슈비님만 내 성격을 바꿀 수 있어!", ephemeral=True)
    bot.current_personality = 설정.value
    await it.response.send_message(f"✅ 뜌비의 성격이 **{설정.value}**(으)로 변경되었어!")

@bot.tree.command(name="내정보", description="나의 친밀도와 뜌비와의 관계를 확인합니다.")
async def my_info(it: discord.Interaction):
    aff = get_user_affinity(it.user.id, it.user.display_name)
    await it.response.send_message(f"📊 **{it.user.display_name}**님과 나의 친밀도는 **{aff}점**이야!")

@bot.tree.command(name="자동입장", description="보이스 채널 자동 입장 기능을 설정합니다.")
@app_commands.choices(상태=[
    app_commands.Choice(name="켜기", value="on"),
    app_commands.Choice(name="끄기", value="off")
])
async def set_auto_join(it: discord.Interaction, 상태: str):
    if it.user.id != SHUVI_USER_ID:
        return await it.response.send_message("엄마만 설정할 수 있어!", ephemeral=True)
    bot.auto_join_enabled = (상태 == "on")
    await it.response.send_message(f"🎙️ 자동 입장 기능이 **{상태.upper()}** 되었어!")

@bot.event
async def on_ready():
    print(f"✅ 로그인 성공: {bot.user}")

# --- 웹 서버 (Koyeb 유지용) ---
app = Flask(__name__)
@app.route('/')
def health_check(): return "OK", 200

if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    bot.run(TOKEN)
