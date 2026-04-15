import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time
import pytz
import asyncio
import os
from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

from personality import make_system_instruction, get_personality_guide
from affinity_manager import (
    get_user_affinity, update_user_affinity, get_attitude_guide, 
    get_memory_from_db, save_to_memory, get_top_ranker_id, get_affinity_ranking,
    supabase
)

korea = pytz.timezone('Asia/Seoul')
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369
ANNOUNCEMENT_CHANNEL_ID = 1358394433665634454
SHUVI_USER_ID = 440517859140173835
RANK_1_ROLE_ID = 1493551151323549767

client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1beta'})
MODEL_LIST = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-2.5-flash-lite",
    "models/gemma-3-27b-it"
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
        await self.tree.sync()

    @bot.event
    async def on_ready():
        # 부팅 시 로그 출력 기능 복구
        try:
            synced = await bot.tree.sync()
            print(f"✅ {len(synced)}개의 슬래시 명령어 동기화 완료!")
        except Exception as e:
            print(f"❌ 명령어 동기화 실패: {e}")

        print(f'✅ 봇 로그인됨: {bot.user}')

        if not bot.control_voice_channel.is_running():
            bot.control_voice_channel.start()
            print("🎙️ [시스템] 자동 입장 루프 시작!")

        if not bot.send_notifications.is_running():
            bot.send_notifications.start()
            print("🔔 [시스템] 알림 루프 시작!")

        if not bot.rank_update_loop.is_running():
            bot.rank_update_loop.start()
            print("👑 [시스템] 랭킹 체크 루프 시작!")

    @tasks.loop(hours=1)
    async def rank_update_loop(self):
        guild = self.get_guild(GUILD_ID_1)
        top_id = get_top_ranker_id()
        role = guild.get_role(RANK_1_ROLE_ID) if guild else None
        if role and top_id:
            winner = guild.get_member(top_id)
            if winner and role not in winner.roles:
                for m in role.members: await m.remove_roles(role)
                await winner.add_roles(role)

    @tasks.loop(minutes=1)
    async def control_voice_channel(self):
        now_korea = datetime.now(korea)
        guild = self.get_guild(GUILD_ID_1)
        if not guild: return
        if self.auto_join_enabled:
            work_channel = guild.get_channel(WORK_CHANNEL_ID)
            if work_channel:
                vc = guild.voice_client
                if vc is None or not vc.is_connected():
                    try: await work_channel.connect(reconnect=True, timeout=15)
                    except: pass
        study_channel = guild.get_channel(STUDY_CHANNEL_ID)
        if study_channel:
            everyone, study_role = guild.default_role, discord.utils.get(guild.roles, name="스터디")
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
    async def send_notifications(self):
        now_korea = datetime.now(korea)
        if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
            guild = self.get_guild(GUILD_ID_2)
            if not guild: return
            ann_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            study_role = discord.utils.get(guild.roles, name="수강생")
            if ann_channel and study_role:
                await ann_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")

bot = MyBot()

# --- 슬래시 명령어 (기존과 동일, 상태 유지) ---
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

# ... (기존 친밀도, 성격, 모델 명령어들 유지)

# --- 대화 이벤트 및 엄격한 파싱 로직 ---

@bot.event
async def on_message(message):
    if message.author.bot: return
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing: return
        bot.is_processing = True
        async with message.channel.typing():
            uid, uname = message.author.id, message.author.display_name
            is_shuvi = (uid == SHUVI_USER_ID)
            
            # 1. 정보 및 가이드 준비
            aff = get_user_affinity(uid, uname)
            attitude = get_attitude_guide(aff)
            pers_guide = get_personality_guide(bot.current_personality)
            
            # 2. 옛날 코드의 시스템 지시문 로직 통합
            identity_prompt = "너는 슈비(엄마)님에 의해 만들어진 '뜌비'야. 상대는 너의 유일한 창조주 슈비님이야." if is_shuvi else f"너는 슈비님의 AI 딸내미 '뜌비'야. 지금 상대는 '{uname}'(으)로, 슈비님이 아니야."
            
            system_instruction = (
                f"{identity_prompt}\n"
                f"현재 상대와의 심리적 친밀도 단계: {attitude}\n"
                f"너의 현재 성격 컨셉: {pers_guide}\n"
                f"중요: 성격 컨셉이 '기본'이 아니라면 친밀도보다 컨셉({bot.current_personality})을 우선해서 연기해줘.\n\n"
                "[친밀도 산정 절대 원칙 - 엄격 모드]\n"
                "1. 일반적인 대화, 단순 질문, 정보 요청 시에는 친밀도 변화를 최소화한다. (0~1점 고정)\n"
                "2. 뜌비를 구체적으로 칭찬하거나, 깊은 유대감을 표현할 때만 높은 점수를 부여한다. (+5~15점)\n"
                "3. '사랑해', '너무 고마워', '최고야' 등 강한 애정 표현 시에만 최대 점수를 고려한다. (+20점)\n"
                "4. 답변 끝에 반드시 [SCORE: 수치] 포함. (예: [SCORE: +1])\n"
                "5. 욕설, 비하, 무례한 태도에는 가차 없이 마이너스 점수를 부여한다.\n"
                "6. 단순 '응', '그래' 같은 단답형 대화는 점수를 올리지 않는다. (0점)\n"
                "7. 유저가 궁금해하는 정보는 성심성의껏 검색해서 알려주되, 지식 전달만으로는 친밀도가 오르지 않음을 명심한다.\n"
                "8. 슈비를 제외한 다른 유저에게는 엄마,아빠 같은 호칭 금지.\n"
                "9. 너무 사랑해를 반복해서 말하면 친밀도를 올리지 말고 경계해.\n"
                "10. 같은말 반복하면 친밀도를 20깎아버려."
            )

            history = get_memory_from_db(uname) if bot.current_personality == "기본" else ""
            
            success = False
            for m_name in [m for m in MODEL_LIST if MODEL_STATUS[m]["is_available"]]:
                try:
                    bot.active_model = m_name.replace("models/", "")
                    res = await asyncio.get_running_loop().run_in_executor(None, lambda: client.models.generate_content(
                        model=m_name, contents=f"{system_instruction}\n기억: {history}\n말: {message.content}"
                    ))
                    
                    if res and res.text:
                        full_text = res.text
                        clean_res = full_text
                        score_change = 0
                        
                        # 옛날 코드의 SCORE 파싱 및 보정 로직 적용
                        if "[SCORE:" in full_text:
                            try:
                                parts = full_text.split("[SCORE:")
                                clean_res = parts[0].strip()
                                score_val_str = parts[1].split("]")[0].strip()
                                
                                raw_score = int(score_val_str.replace("+", ""))
                                # -20 ~ 20 사이로 보정
                                score_change = max(-20, min(20, raw_score))
                                
                                if raw_score > 20 or raw_score < -20:
                                    print(f"⚠️ SCORE 보정 적용: {raw_score} -> {score_change}")
                            except Exception as parse_err:
                                print(f"⚠️ 점수 파싱 에러: {parse_err}")
                                clean_res = full_text
                                score_change = 0

                        await message.reply(clean_res)
                        
                        # 친밀도 업데이트 및 로그 출력
                        old_aff, new_aff = update_user_affinity(uid, uname, score_change)
                        diff = new_aff - old_aff
                        print(f"✅ {uname} 친밀도 업데이트: {old_aff} -> {new_aff} ({'+' if diff >= 0 else ''}{diff})")
                        
                        if bot.current_personality == "기본":
                            save_to_memory(uname, message.content, clean_res)
                        
                        success = True
                        break
                except Exception as e:
                    if any(x in str(e).upper() for x in ["429", "QUOTA"]): 
                        MODEL_STATUS[m_name]["is_available"] = False
                    continue
            if not success: await message.reply("뜌비 지금 너무 졸려... 😭")
        bot.is_processing = False
    await bot.process_commands(message)

# Flask 및 실행부 동일
app = Flask(__name__)
@app.route('/')
def h(): return "OK", 200
def run_flask(): app.run(host='0.0.0.0', port=8000)

if __name__ == '__main__':
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
