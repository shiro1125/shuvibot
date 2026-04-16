"""
reaction_speed.py
====================

이 모듈은 디스코드 봇에 반응속도 게임을 추가하는 Cog를 정의합니다. 사용자는 `/반응속도` 명령어를 통해
손쉽게 반응속도를 측정할 수 있으며, 개인 최고 기록과 서버별 랭킹이 Supabase에 저장됩니다.

Supabase 설정
--------------

본 모듈은 환경변수 `SUPABASE_URL`과 `SUPABASE_KEY`를 통해 Supabase 인스턴스에 접속합니다.
따라서 `.env` 파일에 다음 항목을 추가해야 합니다:

```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_or_service_key
```

Supabase 테이블 구조
-------------------

`reaction_best` 테이블을 생성해야 하며, 아래와 같은 구조를 갖습니다:

| 컬럼명      | 타입    | 설명                              |
|-----------|--------|-----------------------------------|
| user_id   | text   | 디스코드 사용자 ID                 |
| username  | text   | 디스코드 사용자 이름               |
| guild_id  | text   | 길드(서버) ID                       |
| best_ms   | int    | 개인 최고 반응속도 기록(ms)         |
| created_at| timestamptz | 레코드 생성 시간 (자동)        |

`user_id`와 `guild_id` 조합을 기본 키로 설정하거나, Supabase의 `upsert` 기능을 사용해 동일한
사용자/서버 조합에 대해 레코드가 하나만 유지되도록 할 수 있습니다.

사용법
------

이 Cog를 로드하면 `/반응속도` 명령으로 반응속도 게임을 시작할 수 있고, `/반응속도랭킹` 명령으로
서버 내 랭킹을 확인할 수 있습니다. 봇 메인 파일(bot.py)에서 `reaction_speed` 모듈을 로드하도록
설정하면 슬래시 명령어가 자동으로 동기화됩니다.
"""

import os
import random
import time
import asyncio
from typing import Optional, List

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

try:
    # supabase 패키지가 설치되어 있어야 합니다. 설치되어 있지 않다면
    # pip install supabase 를 통해 설치해 주세요.
    from supabase import create_client, Client
except ImportError:
    # Supabase가 설치되어 있지 않은 경우에도 코드가 임포트 단계에서 실패하지 않도록
    # 더미 create_client를 정의합니다. 실사용 시엔 반드시 supabase 패키지를 설치해야 합니다.
    def create_client(url: str, key: str):  # type: ignore
        raise ImportError(
            "Supabase 패키지가 설치되어 있지 않습니다. 'pip install supabase' 명령으로 설치하세요."
        )


load_dotenv()

# 환경 변수에서 Supabase 설정을 불러옵니다. 실제 서비스 환경에서는 .env에 값을 추가해야 합니다.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Supabase 클라이언트 생성
supabase: Optional["Client"] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Supabase 클라이언트 생성 실패: {e}")
else:
    print("⚠️ Supabase 설정이 누락되었습니다. .env에 SUPABASE_URL 및 SUPABASE_KEY를 설정하세요.")


def get_user_best(user_id: int, guild_id: int) -> Optional[int]:
    """해당 사용자의 현재 최고 기록(ms)을 가져옵니다. 없으면 None을 반환합니다."""
    if not supabase:
        return None
    try:
        response = (
            supabase.table("reaction_best")
            .select("best_ms")
            .eq("user_id", str(user_id))
            .eq("guild_id", str(guild_id))
            .execute()
        )
        # supabase-python의 실행 결과는 APIResponse 또는 PostgrestResponse 객체입니다.
        # data 속성에 결과 리스트가 저장되어 있습니다.
        data = getattr(response, "data", [])
        if data:
            # 첫 번째 레코드의 best_ms 값을 반환
            return data[0].get("best_ms")  # type: ignore[return-value]
    except Exception as e:
        print(f"❌ Supabase 조회 실패: {e}")
    return None


def upsert_user_best(user_id: int, guild_id: int, username: str, ms: int) -> None:
    """해당 사용자의 최고 기록을 업데이트합니다. 기존 기록보다 우수할 경우에만 덮어씁니다.

    Supabase에서는 `on_conflict` 매개변수를 사용하려면 해당 컬럼에 대한 unique constraint가 있어야 합니다.
    프로젝트 환경에서 제약조건이 없는 경우를 고려하여 upsert 대신 조회 후 업데이트/삽입 로직을 사용합니다.
    """
    if not supabase:
        return
    try:
        # 먼저 기존 레코드가 있는지 확인합니다.
        existing = (
            supabase.table("reaction_best")
            .select("best_ms")
            .eq("user_id", str(user_id))
            .eq("guild_id", str(guild_id))
            .execute()
        )
        existing_data = getattr(existing, "data", [])
        if existing_data:
            # 업데이트 수행
            supabase.table("reaction_best").update(
                {
                    "username": username,
                    "best_ms": ms,
                }
            ).eq("user_id", str(user_id)).eq("guild_id", str(guild_id)).execute()
        else:
            # 신규 삽입
            supabase.table("reaction_best").insert(
                {
                    "user_id": str(user_id),
                    "guild_id": str(guild_id),
                    "username": username,
                    "best_ms": ms,
                }
            ).execute()
    except Exception as e:
        print(f"❌ Supabase upsert 실패: {e}")


def get_ranking(guild_id: int, limit: int = 10) -> List[dict]:
    """서버 내 최상위 기록을 가져옵니다. limit 개수만큼 반환합니다."""
    if not supabase:
        return []
    try:
        response = (
            supabase.table("reaction_best")
            .select("user_id, username, best_ms")
            .eq("guild_id", str(guild_id))
            .order("best_ms", desc=False)
            .limit(limit)
            .execute()
        )
        data = getattr(response, "data", [])
        return data  # type: ignore[return-value]
    except Exception as e:
        print(f"❌ Supabase 랭킹 조회 실패: {e}")
        return []


def get_user_ranking(user_id: int, guild_id: int) -> Optional[int]:
    """해당 사용자가 서버 내에서 몇 등인지 계산하여 반환합니다."""
    if not supabase:
        return None
    try:
        response = (
            supabase.table("reaction_best")
            .select("user_id, best_ms")
            .eq("guild_id", str(guild_id))
            .order("best_ms", desc=False)
            .execute()
        )
        data = getattr(response, "data", [])
        for index, row in enumerate(data, start=1):
            if row.get("user_id") == str(user_id):
                return index
    except Exception as e:
        print(f"❌ Supabase 등수 조회 실패: {e}")
    return None


class ReactionSpeedView(discord.ui.View):
    """사용자가 버튼을 클릭할 수 있는 View. 클릭 시 반응속도를 측정합니다.

    이 뷰는 반응속도 게임의 상태를 내부에 저장합니다. 버튼은 게임 시작 단계인 "준비" 상태에도
    표시되며, 이때 누르면 실격 처리됩니다. "지금!" 상태가 된 후 누르면 반응속도를 계산합니다.
    """

    def __init__(self, user_id: int, guild_id: int, username: str) -> None:
        super().__init__(timeout=None)
        self.user_id: int = user_id
        self.guild_id: int = guild_id
        self.username: str = username
        # 게임이 시작되기 전에는 start_time이 None입니다. 시작 후에는 perf_counter 값이 저장됩니다.
        self.start_time: Optional[float] = None
        # 메시지 객체를 저장합니다. command에서 설정됩니다.
        self.message: Optional[discord.Message] = None
        # 사용자가 이미 클릭했는지 여부를 표시합니다.
        self.clicked: bool = False

    def set_message(self, message: discord.Message) -> None:
        """뷰에서 나중에 메시지를 수정할 수 있도록 메시지 객체를 저장합니다."""
        self.message = message

    @discord.ui.button(label="클릭!", style=discord.ButtonStyle.primary)
    async def click_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """버튼 클릭 시 호출되는 콜백.

        게임의 상태에 따라 조기 클릭인지 정상 클릭인지 판단하고, 결과를 메시지에 반영합니다.
        """
        # 명령을 실행한 사용자만 버튼을 클릭할 수 있도록 제한합니다.
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "이 버튼은 명령을 실행한 사용자만 누를 수 있어요!",
                ephemeral=True,
            )
            return

        # 이미 클릭했다면 중복 실행을 막습니다.
        if self.clicked:
            await interaction.response.send_message(
                "이미 기록이 저장되었습니다!",
                ephemeral=True,
            )
            return

        # 클릭 플래그 설정
        self.clicked = True

        # 메시지가 설정되어 있지 않다면 오류. 일반적으로 발생하지 않음.
        if not self.message:
            await interaction.response.send_message(
                "내부 오류: 메시지를 찾을 수 없습니다.",
                ephemeral=True,
            )
            return

        # 아직 게임이 시작되지 않았다면 (준비 상태)
        if self.start_time is None:
            # 버튼 비활성화
            button.disabled = True
            # 실격 메시지
            embed = discord.Embed(title="반응속도 게임", color=discord.Color.red())
            embed.add_field(name="결과", value="❌ 너무 빠르게 눌렀습니다!", inline=False)
            embed.set_footer(text="다시 도전해보세요.")
            await interaction.response.edit_message(embed=embed, view=self)
            # 게임 종료
            self.stop()
            return

        # 여기까지 왔으면 정상적으로 "지금!" 이후 클릭한 것
        end_time = time.perf_counter()
        reaction_ms = int((end_time - self.start_time) * 1000)
        # 버튼 비활성화
        button.disabled = True

        # Supabase에서 현재 최고 기록을 가져와 업데이트 여부 확인
        previous_best = get_user_best(self.user_id, self.guild_id)
        new_record = False
        if previous_best is None or reaction_ms < previous_best:
            upsert_user_best(self.user_id, self.guild_id, self.username, reaction_ms)
            new_record = True

        # 등수 계산
        ranking = get_user_ranking(self.user_id, self.guild_id)

        # 결과 Embed 작성
        embed = discord.Embed(title="반응속도 게임", color=discord.Color.green())
        embed.add_field(name="반응속도", value=f"{reaction_ms}ms", inline=False)
        if new_record:
            embed.add_field(name="🎉 기록 갱신", value="개인 최고 기록을 갱신했습니다!", inline=False)
        if ranking:
            embed.add_field(name="서버 등수", value=f"현재 서버 내 {ranking}위", inline=False)
        embed.set_footer(text="게임이 종료되었습니다.")

        await interaction.response.edit_message(embed=embed, view=self)
        # 게임 종료
        self.stop()


class ReactionSpeedCog(commands.Cog):
    """반응속도 게임 기능을 제공하는 Cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(discord.Object(id=1228372760212930652))
    @app_commands.command(name="반응속도", description="반응속도 게임을 시작합니다.")
    async def reaction_speed(self, interaction: discord.Interaction) -> None:
        """사용자와 반응속도 게임을 진행합니다.

        이 명령은 한 개의 메시지에 버튼을 포함하여 게임을 진행합니다. '준비...' 단계에서 버튼을
        표시하고, 정해진 시간이 지난 후 '지금!'으로 전환합니다. 너무 빨리 누르면 실격 처리되며,
        정상적으로 누르면 반응속도를 계산합니다.
        """
        # MODIFIED: 인터랙션 만료 방지를 위해 즉시 defer 합니다.
        await interaction.response.defer()

        # 초기 안내 Embed
        embed = discord.Embed(title="반응속도 게임", color=discord.Color.blue())
        embed.add_field(
            name="준비...", value="버튼이 활성화될 때까지 기다렸다가 눌러주세요!", inline=False
        )
        embed.set_footer(text="너무 일찍 누르면 실격입니다.")

        # View 생성 (start_time은 None)
        view = ReactionSpeedView(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else 0,
            username=interaction.user.display_name,
        )

        # 메시지 전송
        await interaction.followup.send(embed=embed, view=view)
        # InteractionResponse.send_message는 메시지를 반환하지 않으므로,
        # original_response()를 통해 메시지 객체를 가져옵니다.
        try:
            message = await interaction.original_response()
            view.set_message(message)
        except Exception:
            message = None

        # 2~5초 사이 랜덤 대기
        await asyncio.sleep(random.uniform(2.0, 5.0))

        # '지금!' 메시지로 embed 업데이트
        embed_now = discord.Embed(title="반응속도 게임", color=discord.Color.gold())
        embed_now.add_field(
            name="지금!", value="지금 버튼을 누르세요!", inline=False
        )
        embed_now.set_footer(text="버튼을 눌러서 반응속도를 측정해보세요.")

        # 메시지 수정 후 반응 시작 시각을 기록합니다. 네트워크 지연을 고려하여
        # 메시지 수정이 완료된 직후에 start_time을 설정합니다.
        if view.message:
            await view.message.edit(embed=embed_now, view=view)
            # 메시지 수정 후 시점을 start_time으로 저장
            view.start_time = time.perf_counter()

    @app_commands.guilds(discord.Object(id=1228372760212930652))
    @app_commands.command(name="반응속도랭킹", description="서버 내 반응속도 랭킹을 확인합니다.")
    async def reaction_speed_ranking(self, interaction: discord.Interaction) -> None:
        """현재 서버의 반응속도 랭킹을 출력합니다."""
        guild_id = interaction.guild.id if interaction.guild else 0
        records = get_ranking(guild_id, limit=10)
        if not records:
            await interaction.response.send_message(
                "아직 반응속도 기록이 없습니다.\n\n`/반응속도` 명령어로 기록을 남겨보세요!",
                ephemeral=False,
            )
            return
        lines = []
        for idx, row in enumerate(records, start=1):
            user_display = row.get("username") or row.get("user_id")
            best_ms = row.get("best_ms")
            lines.append(f"{idx}. {user_display} - {best_ms}ms")
        ranking_msg = "\n".join(lines)
        await interaction.response.send_message(
            f"🏆 **반응속도 TOP {len(records)}**\n{ranking_msg}",
            ephemeral=False,
        )


async def setup(bot: commands.Bot) -> None:
    """Cog를 비동기로 로드합니다."""
    await bot.add_cog(ReactionSpeedCog(bot))
