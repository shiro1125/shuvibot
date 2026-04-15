# bot.py
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os

from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai

# 모듈화된 파일 임포트
import affinity_manager
import personality

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 상수
GUILD_ID_1 = 1228372760212930652
SHUVI_USER_ID = 440517859140173835

# API 설정
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

# Flask 서버 (Health Check)
app = Flask(__name__)

@app.route('/')
def health_check():
    return 'OK', 200


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

        self.model_list = [
            "models/gemini-3-flash-preview",
            "models/gemini-2.5-flash",
            "models/gemini-3.1-flash-lite-preview",
            "models/gemini-2.5-flash-lite",
            "models/gemma-3-27b-it"
        ]
        self.model_status = {model: {"is_available": True} for model in self.model_list}

    def reset_model_status(self):
        """모든 모델의 상태를 초기화합니다."""
        for model in self.model_status:
            self.model_status[model]["is_available"] = True
        print("🔄 [시스템] 모든 모델의 사용 제한이 초기화되었습니다.")

    def lock_model(self, model_name):
        """한도가 초과된 모델을 잠급니다."""
        if model_name in self.model_status:
            self.model_status[model_name]["is_available"] = False
            print(f"🚫 [경고] {model_name} 한도 초과. 오후 4시까지 건너뜁니다.")

    async def setup_hook(self):
        # 모듈/Cog 로드
        # voicechat 모듈을 추가하여 음성 기능을 활성화합니다.
        extensions = ['tts', 'blackjack', 'scheduler', 'voicechat']
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ {ext} 모듈 로드 완료!")
            except Exception as e:
                print(f"❌ {ext} 모듈 로드 실패: {e}")

bot = MyBot()
affinity_group = app_commands.Group(name="친밀도", description="뜌비와의 친밀도 관리")
bot.tree.add_command(affinity_group)

# -----------------------------
# Bot 이벤트
# -----------------------------
@bot.event
async def on_ready():
    try:
        # 먼저 전체 글로벌 명령어를 동기화합니다.
        synced_global = await bot.tree.sync()
        print(f"✅ {len(synced_global)}개의 글로벌 명령어 동기화 완료!")
        # 지정된 길드에 대해서도 별도로 동기화하여 슬래시 명령어가 즉시 표시되도록 합니다.
        guild = discord.Object(id=GUILD_ID_1)
        synced_guild = await bot.tree.sync(guild=guild)
        print(f"✅ {len(synced_guild)}개의 길드 명령어 동기화 완료! (Guild ID: {GUILD_ID_1})")
    except Exception as e:
        print(f"❌ 명령어 동기화 실패: {e}")
    print(f'✅ 봇 로그인됨: {bot.user}')

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    success = False

    # 뜌비가 언급되었거나 이름이 포함된 경우에만 실행
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing:
            return

        try:
            bot.is_processing = True
            async with message.channel.typing():
                user_id = message.author.id
                user_name = message.author.display_name

                # 데이터 조회
                history_context = affinity_manager.get_memory_from_db(user_name)
                affinity = affinity_manager.get_user_affinity(user_id, user_name)
                is_shuvi = (user_id == SHUVI_USER_ID)

                personality_guide = personality.get_personality_guide(bot.current_personality)
                attitude = affinity_manager.get_attitude_guide(affinity)

                if bot.current_personality == "기본":
                    full_content = f"과거 대화 기억:\n{history_context}\n\n현재 유저의 말: {message.content}"
                else:
                    full_content = message.content

                system_instruction = personality.make_system_instruction(
                    is_shuvi, user_name, bot.current_personality, attitude, personality_guide
                )

                available_models = [
                    m for m in bot.model_list
                    if bot.model_status.get(m, {}).get("is_available", True)
                ]

                print(f"🔍 [시스템] 현재 가용한 모델 순서: {available_models}")
                loop = asyncio.get_running_loop()

                for model_name in available_models:
                    try:
                        bot.active_model = model_name

                        if "gemma" in model_name.lower():
                            prompt = f"[시스템 지침]\n{system_instruction}\n\n유저 메시지: {full_content}"
                            response = await loop.run_in_executor(
                                None,
                                lambda: client.models.generate_content(
                                    model=model_name,
                                    contents=prompt
                                )
                            )
                        else:
                            response = await loop.run_in_executor(
                                None,
                                lambda: client.models.generate_content(
                                    model=model_name,
                                    contents=full_content,
                                    config={'system_instruction': system_instruction}
                                )
                            )

                        if response and getattr(response, "text", None):
                            full_text = response.text
                            clean_res = full_text
                            score_change = 0

                            if "[SCORE:" in full_text:
                                try:
                                    parts = full_text.split("[SCORE:")
                                    clean_res = parts[0].strip()
                                    score_val_str = parts[1].split("]")[0].strip()

                                    raw_score = int(score_val_str.replace("+", ""))
                                    score_change = max(-20, min(20, raw_score))

                                    if raw_score > 20 or raw_score < -20:
                                        print(f"⚠️ SCORE 보정 적용: {raw_score} -> {score_change}")
                                except Exception as parse_err:
                                    print(f"⚠️ 점수 파싱 에러: {parse_err}")
                                    clean_res = full_text
                                    score_change = 0

                            await message.reply(clean_res)
                            affinity_manager.update_user_affinity(user_id, user_name, score_change)

                            if bot.current_personality == "기본":
                                affinity_manager.save_to_memory(user_name, message.content, clean_res)

                            success = True
                            break

                    except Exception as e:
                        err_str = str(e).upper()
                        print(f"‼️ {model_name} 실패 원인: {err_str}")

                        if any(x in err_str for x in ["429", "EXHAUSTED", "QUOTA", "LIMIT", "RATE_LIMIT", "PERMISSION_DENIED"]):
                            print(f"🚫 {model_name} 한도 초과 감지! ❌ 상태로 변경합니다.")
                            bot.lock_model(model_name)
                            bot.active_model = "대기 중"
                        continue

                if not success:
                    bot.active_model = "대기 중"
                    await message.reply("미안! 지금은 뜌비가 기운이 없나 봐... 😭 내일 오후 4시에 다시 불러줘!")

        except Exception as top_e:
            print(f"❌ [심각] 전체 로직 에러: {top_e}")
        finally:
            bot.is_processing = False

        if success:
            return

    await bot.process_commands(message)

# -----------------------------
# 슬래시 명령어
# -----------------------------
@affinity_group.command(name="설정", description="유저의 친밀도를 특정 수치로 고정합니다.")
@app_commands.describe(유저="설정할 유저", 수치="고정할 점수 (예: 100, -50)")
async def 설정(interaction: discord.Interaction, 유저: discord.Member, 수치: int):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("뜌비의 마음을 강제로 정하는 건 엄마만 할 수 있어! 😤", ephemeral=True)
        return

    if affinity_manager.set_user_affinity(유저.id, 유저.display_name, 수치):
        await interaction.response.send_message(f"⚙️ **{유저.display_name}**님의 친밀도를 **{수치}점**으로 설정 완료했어! ✨")
    else:
        await interaction.response.send_message("설정 중에 에러가 났어... 😭", ephemeral=True)

@affinity_group.command(name="확인", description="유저의 친밀도를 확인합니다.")
@app_commands.describe(유저="친밀도를 확인할 유저를 선택하세요 (비우면 본인 확인)")
async def 확인(interaction: discord.Interaction, 유저: discord.Member = None):
    target = 유저 or interaction.user
    affinity = affinity_manager.get_user_affinity(target.id, target.display_name)

    if affinity > 70:
        status = "영원한 단짝 💖"
    elif affinity > 30:
        status = "친한 친구 😊"
    elif affinity >= 0:
        status = "안면 있는 사이 😐"
    else:
        status = "조심해야 할 사람 💀"

    await interaction.response.send_message(
        f"📊 **{target.display_name}**님과 뜌비의 친밀도는 **{affinity}점**이야! (현재 상태: {status})"
    )

@affinity_group.command(name="랭킹", description="뜌비의 절친 TOP 30 랭킹을 보여줍니다.")
async def 랭킹(interaction: discord.Interaction):
    await interaction.response.defer()
    data = affinity_manager.get_affinity_ranking(30)
    
    if not data:
        await interaction.followup.send("아직 친한 사람이 없네... 😭")
        return

    msg = "🏆 **뜌비의 절친 랭킹 (TOP 30)**\n━━━━━━━━━━━━━━━━━━\n"
    for i, r in enumerate(data, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}위**"
        msg += f"{medal} {r['user_name']} ― `{r.get('affinity', 0)}점` (💬 {r.get('chat_count', 0)}회)\n"
    await interaction.followup.send(msg)


@bot.tree.command(name="성격", description="뜌비의 성격을 변경합니다.")
@app_commands.choices(설정=[
    app_commands.Choice(name="기본", value="기본"),
    app_commands.Choice(name="메스가키", value="메스가키"),
    app_commands.Choice(name="츤데레", value="츤데레"),
    app_commands.Choice(name="얀데레", value="얀데레")
])
async def 성격변경(interaction: discord.Interaction, 설정: app_commands.Choice[str]):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("내 성격은 슈비 엄마만 바꿀 수 있어! 🤫", ephemeral=True)
        return

    bot.current_personality = 설정.value
    await interaction.response.send_message(f"✅ 뜌비의 성격이 **{설정.value}** 상태로 바뀌었어!")


@bot.tree.command(name="자동입장", description="자동 재접속 기능을 설정합니다.")
@app_commands.choices(상태=[
    app_commands.Choice(name="켜기 (On)", value="on"),
    app_commands.Choice(name="끄기 (Off)", value="off")
])
async def 자동입장(interaction: discord.Interaction, 상태: app_commands.Choice[str]):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("자동 입장 설정은 슈비 엄마만 건드릴 수 있어!", ephemeral=True)
        return

    bot.auto_join_enabled = (상태.value == "on")
    if 상태.value == "off" and interaction.guild and interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()

    await interaction.response.send_message(f"{'✅ 자동 입장 활성화' if 상태.value == 'on' else '❌ 자동 입장 비활성화'}")


@bot.tree.command(name="모델", description="현재 뜌비봇이 사용 중인 모델 리스트와 우선순위를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    status_msg = "🤖 **뜌비봇 모델 실시간 가동 현황**\n*(매일 오후 4시 자동 리셋)*\n----------------------------\n"
    for i, model in enumerate(bot.model_list, 1):
        is_available = bot.model_status.get(model, {}).get("is_available", True)
        if not is_available:
            line = f"❌ **한도 초과**: `{model}`"
        else:
            prefix = "✅ **현재 1순위**" if i == 1 else f"{i}순위"
            line = f"{prefix}: `{model}`"
        status_msg += line + "\n"

    status_msg += "----------------------------\n"
    status_msg += f"🎭 **현재 성격: {bot.current_personality}**\n"
    status_msg += f"🎙️ **자동 입장: {'켜짐' if bot.auto_join_enabled else '꺼짐'}**\n"
    status_msg += f"🧠 **현재 활성 모델: {bot.active_model}**"

    await interaction.response.send_message(status_msg)


if __name__ == '__main__':
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8000}, daemon=True).start()
    bot.run(TOKEN)
