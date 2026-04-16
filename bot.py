# bot.py
# MODIFIED: bot.py는 초기화/이벤트 연결만 담당하도록 경량화
import asyncio
from threading import Thread
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

import affinity_manager
import ai_service
import search_service
from config import (
    ACTIVE_MODEL_DEFAULT,
    AFFINITY_FLUSH_INTERVAL_SECONDS,
    DISCORD_TOKEN,
    GUILD_ID_1,
    MEMORY_FLUSH_INTERVAL_SECONDS,
    SHUVI_USER_ID,
)
from memory_service import flush_memory_to_db
from perf_utils import PerfTracker
from response_service import (
    build_system_instruction,
    build_user_content,
    fetch_context,
    parse_ai_response,
    persist_after_response,
    should_respond,
)

TOKEN = DISCORD_TOKEN

app = Flask(__name__)


@app.route("/")
def health_check():
    return "OK", 200


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)

        self.auto_join_enabled = True
        self.current_personality = "기본"
        self.active_model = ACTIVE_MODEL_DEFAULT
        self.model_list = ai_service.get_model_list()
        self.model_status = {model: {"is_available": True} for model in self.model_list}
        self.channel_locks: Dict[int, asyncio.Lock] = {}
        self.flush_tasks_started = False

    def get_channel_lock(self, channel_id: int) -> asyncio.Lock:
        if channel_id not in self.channel_locks:
            self.channel_locks[channel_id] = asyncio.Lock()
        return self.channel_locks[channel_id]

    def reset_model_status(self):
        for model in self.model_status:
            self.model_status[model]["is_available"] = True
        print("🔄 [시스템] 모든 모델의 사용 제한이 초기화되었습니다.")

    def lock_model(self, model_name):
        if model_name in self.model_status:
            self.model_status[model_name]["is_available"] = False
            print(f"🚫 [경고] {model_name} 한도 초과. 오후 4시까지 건너뜁니다.")

    async def setup_hook(self):
        extensions = ["tts", "blackjack", "scheduler", "voicechat", "reaction_speed", "trpg"]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"✅ {ext} 모듈 로드 완료!")
            except Exception as e:
                print(f"❌ {ext} 모듈 로드 실패: {e}")


bot = MyBot()
affinity_group = app_commands.Group(name="친밀도", description="뜌비와의 친밀도 관리")
bot.tree.add_command(affinity_group)


async def affinity_flush_loop():
    while True:
        await asyncio.sleep(AFFINITY_FLUSH_INTERVAL_SECONDS)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, affinity_manager.flush_affinity_updates)


async def memory_flush_loop():
    while True:
        await asyncio.sleep(MEMORY_FLUSH_INTERVAL_SECONDS)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, flush_memory_to_db)


@bot.event
async def on_ready():
    try:
        synced_global = await bot.tree.sync()
        print(f"✅ {len(synced_global)}개의 글로벌 명령어 동기화 완료!")
        guild = discord.Object(id=GUILD_ID_1)
        synced_guild = await bot.tree.sync(guild=guild)
        print(f"✅ {len(synced_guild)}개의 길드 명령어 동기화 완료! (Guild ID: {GUILD_ID_1})")
    except Exception as e:
        print(f"❌ 명령어 동기화 실패: {e}")

    if not bot.flush_tasks_started:
        asyncio.create_task(affinity_flush_loop())
        asyncio.create_task(memory_flush_loop())
        bot.flush_tasks_started = True

    print(f"✅ 봇 로그인됨: {bot.user}")


@bot.event
async def on_message(message):
    if not should_respond(bot, message):
        await bot.process_commands(message)
        return

    channel_lock = bot.get_channel_lock(message.channel.id)
    if channel_lock.locked():
        return

    perf = PerfTracker(enabled=True)
    perf.log("message_received")

    async with channel_lock:
        try:
            user_id = message.author.id
            user_name = message.author.display_name
            user_message = message.content.strip()

            affinity, history_context = await fetch_context(user_id, user_name, bot.current_personality)
            search_context = await asyncio.get_running_loop().run_in_executor(
                None, search_service.build_search_context, user_message
            )
            perf.log("preprocess")

            system_instruction = build_system_instruction(user_id, user_name, bot.current_personality, affinity)
            full_content = build_user_content(history_context, user_message, bot.current_personality, search_context)
            if search_context:
                print("[SEARCH] injected_into_prompt=True")

            available_models = [m for m in bot.model_list if bot.model_status.get(m, {}).get("is_available", True)]

            success = False
            for model_name in available_models:
                try:
                    bot.active_model = model_name
                    response = await ai_service.generate_reply(model_name, system_instruction, full_content)
                    perf.log("ai_request")

                    if response and getattr(response, "text", None):
                        clean_res, score_change = parse_ai_response(response.text, user_name, user_message)
                        await message.reply(clean_res)
                        perf.log("response_send")

                        await persist_after_response(
                            user_id=user_id,
                            user_name=user_name,
                            user_message=user_message,
                            clean_res=clean_res,
                            score_change=score_change,
                            personality_name=bot.current_personality,
                        )
                        perf.log("postprocess")
                        success = True
                        break

                except Exception as e:
                    err_str = str(e)
                    print(f"‼️ {model_name} 실패 원인: {err_str.upper()}")
                    if ai_service.is_quota_error(err_str):
                        print(f"🚫 {model_name} 한도 초과 감지! ❌ 상태로 변경합니다.")
                        bot.lock_model(model_name)
                        bot.active_model = ACTIVE_MODEL_DEFAULT
                    continue

            if not success:
                bot.active_model = ACTIVE_MODEL_DEFAULT
                await message.reply("미안! 지금은 뜌비가 기운이 없나 봐... 😭 내일 오후 4시에 다시 불러줘!")
                perf.log("response_send")

        except Exception as top_e:
            print(f"❌ [심각] 전체 로직 에러: {top_e}")
        finally:
            perf.total()

    await bot.process_commands(message)


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
@app_commands.describe(유저="친밀도를 확인할 유저의 이름 또는 멘션을 입력하세요 (비우면 본인 확인)")
async def 확인(interaction: discord.Interaction, 유저: str = None):
    target: discord.Member
    if 유저:
        guild = interaction.guild
        member: Optional[discord.Member] = None
        if guild:
            if 유저.startswith("<@") and 유저.endswith(">"):
                try:
                    user_id = int(유저.strip("<@!>"))
                    member = guild.get_member(user_id)
                except Exception:
                    member = None
            elif 유저.isdigit():
                member = guild.get_member(int(유저))
            else:
                member = guild.get_member_named(유저)
        if member is None:
            await interaction.response.send_message(
                f"❌ 입력한 유저를 찾을 수 없습니다: {유저}",
                ephemeral=True,
            )
            return
        target = member
    else:
        target = interaction.user

    try:
        affinity = affinity_manager.get_user_affinity(target.id, target.display_name)
    except Exception as e:
        await interaction.response.send_message(
            f"❌ 친밀도 정보를 가져오는 중 오류가 발생했습니다: {e}",
            ephemeral=True,
        )
        return

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
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, affinity_manager.get_affinity_ranking, 30)

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
    app_commands.Choice(name="얀데레", value="얀데레"),
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
    app_commands.Choice(name="끄기 (Off)", value="off"),
])
async def 자동입장(interaction: discord.Interaction, 상태: app_commands.Choice[str]):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("자동 입장 설정은 슈비 엄마만 건드릴 수 있어!", ephemeral=True)
        return

    bot.auto_join_enabled = 상태.value == "on"
    if 상태.value == "off" and interaction.guild and interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()

    await interaction.response.send_message(f"{'✅ 자동 입장 활성화' if 상태.value == 'on' else '❌ 자동 입장 비활성화'}")


@bot.tree.command(name="모델", description="현재 뜌비봇이 사용 중인 모델 리스트와 우선순위를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    lines = []
    lines.append("🤖 **뜌비봇 모델 실시간 가동 현황**")
    lines.append("*(매일 오후 4시 자동 리셋)*")
    lines.append("----------------------------")

    for i, model in enumerate(bot.model_list, 1):
        model = str(model).strip()
        is_available = bot.model_status.get(model, {}).get("is_available", True)

        if not is_available:
            lines.append(f"❌ **한도 초과**: `{model}`")
        else:
            prefix = "✅ 현재 1순위" if i == 1 else f"{i}순위"
            lines.append(f"{prefix}: `{model}`")

    lines.append("----------------------------")
    lines.append(f"🎭 현재 성격: {bot.current_personality}")
    lines.append(f"🎙️ 자동 입장: {'켜짐' if bot.auto_join_enabled else '꺼짐'}")
    lines.append(f"🧠 현재 활성 모델: {bot.active_model}")

    status_msg = "\n".join(lines)
    await interaction.response.send_message(status_msg)


if __name__ == "__main__":
    Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 8000}, daemon=True).start()
    bot.run(TOKEN)
