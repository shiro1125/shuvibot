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
        data = response.get("data", [])
        if data:
            return data[0].get("best_ms")  # type: ignore[return-value]
    except Exception as e:
        print(f"❌ Supabase 조회 실패: {e}")
    return None


def upsert_user_best(user_id: int, guild_id: int, username: str, ms: int) -> None:
    """해당 사용자의 최고 기록을 업데이트합니다. 기존 기록보다 우수할 경우에만 덮어씁니다."""
    if not supabase:
        return
    try:
        supabase.table("reaction_best").upsert(
            {
                "user_id": str(user_id),
                "guild_id": str(guild_id),
                "username": username,
                "best_ms": ms,
            },
            on_conflict=["user_id", "guild_id"],
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
            # asc=True 는 supabase-py에서 지원하지 않으므로 desc=False로 지정합니다.
            .order("best_ms", desc=False)
            .limit(limit)
            .execute()
        )
        return response.get("data", [])  # type: ignore[return-value]
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
        data = response.get("data", [])
        for index, row in enumerate(data, start=1):
            if row.get("user_id") == str(user_id):
                return index
    except Exception as e:
        print(f"❌ Supabase 등수 조회 실패: {e}")
    return None


class ReactionSpeedView(discord.ui.View):
    """사용자가 버튼을 클릭할 수 있는 View. 클릭 시 반응속도를 측정합니다."""

    def __init__(self, user_id: int, guild_id: int, username: str, start_time: float):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.guild_id = guild_id
        self.username = username
        self.start_time = start_time
        self.clicked = False

    @discord.ui.button(label="클릭!", style=discord.ButtonStyle.primary)
    async def click_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
        """버튼 클릭 시 호출되는 콜백."""
        # 명령을 실행한 사용자만 버튼을 클릭할 수 있도록 제한합니다.
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("이 버튼은 명령을 실행한 사용자만 누를 수 있어요!", ephemeral=True)
            return
        # 이미 클릭했다면 중복 실행을 막습니다.
        if self.clicked:
            await interaction.response.send_message("이미 기록이 저장되었습니다!", ephemeral=True)
            return

        self.clicked = True
        # 반응속도 계산
        end_time = time.perf_counter()
        reaction_ms = int((end_time - self.start_time) * 1000)
        # 버튼 비활성화
        button.disabled = True
        await interaction.response.edit_message(view=self)

        # Supabase에서 현재 최고 기록을 가져와 업데이트 여부 확인
        previous_best = get_user_best(self.user_id, self.guild_id)
        new_record = False
        if previous_best is None or reaction_ms < previous_best:
            upsert_user_best(self.user_id, self.guild_id, self.username, reaction_ms)
            new_record = True

        # 등수 계산
        ranking = get_user_ranking(self.user_id, self.guild_id)

        # 결과 메시지 작성
        result_msg = f"반응속도: {reaction_ms}ms"
        if new_record:
            result_msg += " 🎉 새로운 개인 최고 기록!"
        if ranking:
            result_msg += f" (서버 내 {ranking}위)"

        await interaction.followup.send(result_msg, ephemeral=False)
        # View 종료
        self.stop()


class ReactionSpeedCog(commands.Cog):
    """반응속도 게임 기능을 제공하는 Cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(discord.Object(id=1228372760212930652))
    @app_commands.command(name="반응속도", description="반응속도 게임을 시작합니다.")
    async def reaction_speed(self, interaction: discord.Interaction) -> None:
        """사용자와 반응속도 게임을 진행합니다."""
        # 게임 시작을 알리는 메시지
        await interaction.response.send_message("준비...", ephemeral=False)
        # 2~5초 사이 랜덤 대기 후 '지금!' 메시지를 출력
        await asyncio.sleep(random.uniform(2.0, 5.0))
        start_time = time.perf_counter()
        view = ReactionSpeedView(
            user_id=interaction.user.id,
            guild_id=interaction.guild.id if interaction.guild else 0,
            username=interaction.user.display_name,
            start_time=start_time,
        )
        await interaction.followup.send("지금!", view=view, ephemeral=False)

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
