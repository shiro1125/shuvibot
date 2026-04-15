"""
trpg.py
===========

이 모듈은 Discord 봇에 자유도 기반 TRPG 시스템을 추가합니다. 캐릭터 생성, 자유 행동
판정, 주사위 굴림, 스탯 기반 성공/실패 판정 등을 제공하며, 게임 데이터는 Supabase에
저장됩니다. 상황 서술은 Gemini API를 사용하여 생성하되, 시스템 규칙을 우선 적용합니다.

환경 변수
-----------

- `SUPABASE_URL`: Supabase 인스턴스 URL
- `SUPABASE_KEY`: Supabase API 키
- `GEMINI_API_KEY`: Google Gemini API 키

Supabase 테이블
----------------

**trpg_characters**

- user_id (text) – 디스코드 사용자 ID
- guild_id (text) – 길드(서버) ID
- name (text) – 캐릭터 이름
- gender (text) – 성별
- job (text) – 직업
- stats (json) – STR/DEX/INT/HP/CHA 값을 포함한 JSON
- hp (int) – 현재 HP
- inventory (json) – 아이템 목록(JSON 배열)
- created_at (timestamptz) – 자동 생성 시각

`user_id`와 `guild_id` 조합에 unique 제약을 두어 한 서버당 하나의 캐릭터만 생성되도록 설정하는 것을 권장합니다.

**trpg_logs** (선택)

행동 로그를 저장하려면 추가 테이블을 만들어 사용할 수 있습니다.

사용 예
-------

봇에 이 모듈을 로드하면 `/캐릭터 생성` 명령어로 캐릭터를 만들 수 있고, `/행동` 명령어로
자유롭게 행동을 입력하여 주사위 판정을 수행할 수 있습니다. 허용되지 않는 행동은
필터링되며, 결과와 상황 서술은 채팅으로 전송됩니다.
"""

import os
import random
import time
import json
import asyncio
from typing import Optional, Dict, Tuple, List

import discord
from discord.ext import commands
from discord import app_commands

try:
    # Supabase 클라이언트 불러오기
    from supabase import create_client, Client
except ImportError:
    # supabase 패키지가 설치되어 있지 않으면 안내 메시지 출력
    def create_client(url: str, key: str):  # type: ignore
        raise ImportError(
            "Supabase 패키지가 설치되어 있지 않습니다. 'pip install supabase' 명령으로 설치하세요."
        )

# Gemini API 클라이언트
try:
    from google import genai
except ImportError:
    genai = None

# 환경변수 로딩
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

supabase: Optional["Client"] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Supabase 클라이언트 생성 실패: {e}")
else:
    print("⚠️ Supabase 설정이 누락되었습니다. .env에 SUPABASE_URL 및 SUPABASE_KEY를 설정하세요.")

# Gemini 클라이언트 설정
gemini_client: Optional[genai.Client] = None
if genai and GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"❌ Gemini 클라이언트 초기화 실패: {e}")


########## 데이터베이스 헬퍼 함수 ##########

def get_character(user_id: int, guild_id: int) -> Optional[Dict[str, any]]:
    """사용자의 캐릭터를 Supabase에서 불러옵니다."""
    if not supabase:
        return None
    try:
        response = (
            supabase.table("trpg_characters")
            .select("*")
            .eq("user_id", str(user_id))
            .eq("guild_id", str(guild_id))
            .single()
            .execute()
        )
        data = getattr(response, "data", None)
        return data
    except Exception as e:
        print(f"❌ Supabase 캐릭터 조회 실패: {e}")
        return None


def upsert_character(user_id: int, guild_id: int, name: str, gender: str, job: str, stats: Dict[str, int], inventory: Optional[List[str]] = None) -> None:
    """캐릭터를 생성하거나 업데이트합니다. 동일한 user/guild 조합이면 덮어씁니다."""
    if not supabase:
        return
    inventory = inventory or []
    payload = {
        "user_id": str(user_id),
        "guild_id": str(guild_id),
        "name": name,
        "gender": gender,
        "job": job,
        "stats": stats,
        "hp": stats.get("HP", 10),
        "inventory": inventory,
    }
    try:
        # 먼저 기존 레코드가 있는지 확인
        existing = (
            supabase.table("trpg_characters")
            .select("id")
            .eq("user_id", str(user_id))
            .eq("guild_id", str(guild_id))
            .execute()
        )
        existing_data = getattr(existing, "data", [])
        if existing_data:
            # 업데이트
            supabase.table("trpg_characters").update(payload).eq("user_id", str(user_id)).eq("guild_id", str(guild_id)).execute()
        else:
            supabase.table("trpg_characters").insert(payload).execute()
    except Exception as e:
        print(f"❌ Supabase 캐릭터 upsert 실패: {e}")


def update_character_hp(user_id: int, guild_id: int, new_hp: int) -> None:
    """캐릭터 HP를 업데이트합니다."""
    if not supabase:
        return
    try:
        supabase.table("trpg_characters").update({"hp": new_hp}).eq("user_id", str(user_id)).eq("guild_id", str(guild_id)).execute()
    except Exception as e:
        print(f"❌ Supabase HP 업데이트 실패: {e}")


########## 게임 로직 함수 ##########

def is_action_allowed(action: str) -> bool:
    """허용되지 않는 키워드가 포함되어 있는지 확인합니다."""
    banned_keywords = [
        "신이 된다",
        "모든",
        "즉사",
        "죽인다",
        "모두 죽",  # "모두 죽인다" 등
        "전부 죽",
        "무적",
        "불멸",
        "무한",
    ]
    lowered = action.lower()
    for word in banned_keywords:
        if word.replace(" ", "") in lowered:
            return False
    return True


def classify_action(action: str) -> Tuple[str, int]:
    """행동 문자열을 분석하여 사용할 스탯과 난이도를 결정합니다.

    반환값: (stat_key, difficulty)
    stat_key는 "STR", "DEX", "INT", "CHA" 중 하나이며, 인식하지 못하면 "INT"를 기본값으로 사용합니다.
    difficulty는 10~18 사이의 난수를 기본으로 하되, 키워드에 따라 조정할 수 있습니다.
    """
    # 기본 설정
    stat_key = "INT"
    difficulty = random.randint(10, 18)
    text = action.lower()
    # 키워드 매핑
    if any(kw in text for kw in ["유혹", "매혹", "설득", "친해지", "미인"]):
        stat_key = "CHA"
        difficulty = random.randint(8, 16)
    elif any(kw in text for kw in ["공격", "부수", "때리", "베기", "찌르"]):
        stat_key = "STR"
        difficulty = random.randint(10, 18)
    elif any(kw in text for kw in ["은신", "몰래", "도둑", "숨", "피하", "회피"]):
        stat_key = "DEX"
        difficulty = random.randint(10, 18)
    elif any(kw in text for kw in ["분석", "조사", "연구", "지식", "파악"]):
        stat_key = "INT"
        difficulty = random.randint(10, 18)
    else:
        # 알 수 없는 행동은 INT 기반으로 판정
        stat_key = "INT"
        difficulty = random.randint(12, 20)
    return stat_key, difficulty


def roll_dice(stat_value: int) -> Tuple[int, int, str]:
    """1d20 주사위를 굴려 스탯을 더해 결과를 도출합니다.

    반환값: (natural_roll, total, outcome)
    outcome은 "critical_success", "success", "failure", "critical_failure" 중 하나입니다.
    """
    natural = random.randint(1, 20)
    total = natural + stat_value
    outcome: str
    if natural == 20:
        outcome = "critical_success"
    elif natural == 1:
        outcome = "critical_failure"
    else:
        outcome = "pending"  # 후속 판정에서 결정
    return natural, total, outcome


########## Discord Cog 정의 ##########

class TRPGCog(commands.Cog):
    """자유도 기반 TRPG 시스템을 제공하는 Cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(discord.Object(id=1228372760212930652))
    @app_commands.command(name="캐릭터", description="TRPG 캐릭터를 생성합니다.")
    @app_commands.describe(
        이름="캐릭터 이름",
        성별="성별 (예: 남성, 여성, 기타)",
        직업="직업 (예: 전사, 도적, 마법사 등)",
        힘="힘(STR) 스탯 (8~18)",
        민첩="민첩(DEX) 스탯 (8~18)",
        지능="지능(INT) 스탯 (8~18)",
        체력="체력(HP) 스탯 (8~18)",
        매력="매력(CHA) 스탯 (8~18)",
    )
    async def create_character(
        self,
        interaction: discord.Interaction,
        이름: str,
        성별: str,
        직업: str,
        힘: Optional[int] = None,
        민첩: Optional[int] = None,
        지능: Optional[int] = None,
        체력: Optional[int] = None,
        매력: Optional[int] = None,
    ) -> None:
        """새로운 TRPG 캐릭터를 생성합니다. 각 스탯을 제공하지 않으면 8~18 사이의 무작위 값이 지정됩니다."""
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else 0

        # 스탯 기본값 설정
        stats = {
            "STR": 힘 if 힘 is not None else random.randint(8, 15),
            "DEX": 민첩 if 민첩 is not None else random.randint(8, 15),
            "INT": 지능 if 지능 is not None else random.randint(8, 15),
            "HP": 체력 if 체력 is not None else random.randint(8, 15),
            "CHA": 매력 if 매력 is not None else random.randint(8, 15),
        }

        # Supabase 저장
        upsert_character(user_id, guild_id, 이름, 성별, 직업, stats, [])

        # 성공 메시지
        embed = discord.Embed(title="캐릭터 생성", color=discord.Color.blue())
        embed.add_field(name="이름", value=이름, inline=False)
        embed.add_field(name="성별", value=성별, inline=False)
        embed.add_field(name="직업", value=직업, inline=False)
        embed.add_field(name="스탯", value=f"STR: {stats['STR']}, DEX: {stats['DEX']}, INT: {stats['INT']}, HP: {stats['HP']}, CHA: {stats['CHA']}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.guilds(discord.Object(id=1228372760212930652))
    @app_commands.command(name="행동", description="TRPG 행동을 수행합니다.")
    @app_commands.describe(
        내용="자유롭게 입력하는 행동 내용 (예: 상인을 유혹한다, 문을 부순다 등)"
    )
    async def perform_action(self, interaction: discord.Interaction, 내용: str) -> None:
        """사용자가 입력한 행동을 해석하고 주사위 판정을 수행합니다."""
        user_id = interaction.user.id
        guild_id = interaction.guild.id if interaction.guild else 0

        # 캐릭터 확인
        character = get_character(user_id, guild_id)
        if character is None:
            await interaction.response.send_message(
                "❌ 먼저 `/캐릭터` 명령으로 캐릭터를 생성하세요!",
                ephemeral=True,
            )
            return

        # 행동 검증
        if not is_action_allowed(내용):
            await interaction.response.send_message(
                "❌ 해당 행동은 시스템 규칙에 의해 허용되지 않습니다. 다른 행동을 시도해 주세요.",
                ephemeral=True,
            )
            return

        # 행동 분류 및 난이도 설정
        stat_key, difficulty = classify_action(내용)
        stat_value = character["stats"].get(stat_key, 0)

        # 주사위 굴림
        natural, total, outcome = roll_dice(stat_value)
        # 기본 outcome 보정
        if outcome == "pending":
            if total >= difficulty:
                outcome = "success"
            else:
                outcome = "failure"

        # 간단한 전투나 HP 감소 처리 (STR 기반 행동 실패 시 패널티)
        hp_change = 0
        if stat_key == "STR" and outcome in ("failure", "critical_failure"):
            # 실패 시 약간의 HP 감소
            hp_change = -random.randint(1, 5)
            new_hp = max(0, character["hp"] + hp_change)
            update_character_hp(user_id, guild_id, new_hp)

        # AI를 통한 상황 서술 생성
        narrative = ""
        if gemini_client:
            try:
                prompt = (
                    "TRPG 상황을 서술하는 시스템입니다. 규칙을 준수하며 현재 캐릭터의 행동과 결과를 한글로 묘사하십시오."\
                    f"\n\n캐릭터 정보: 이름={character['name']}, 직업={character['job']}, 성별={character['gender']}"\
                    f", 스탯={{STR:{character['stats']['STR']}, DEX:{character['stats']['DEX']}, INT:{character['stats']['INT']}, HP:{character['hp']}, CHA:{character['stats']['CHA']}}}"\
                    f"\n행동: {내용}"\
                    f"\n주사위: natural={natural}, total={total}, 난이도={difficulty}, 결과={outcome}"\
                    "\n행동이 성공했을 때는 성공적으로 수행된 장면을, 실패했을 때는 실패한 장면을 묘사하세요. 시스템 규칙을 우선 적용하며, 결과에 어울리는 짧은 서술을 작성하세요."
                )
                # Gemini API 호출
                resp = gemini_client.models.generate_content(
                    model="models/gemini-2.5-flash-lite",
                    contents=prompt,
                )
                narrative = resp.text if hasattr(resp, "text") else ""
            except Exception as e:
                print(f"⚠️ Gemini 응답 실패: {e}")
                narrative = ""

        # Embed 작성
        embed = discord.Embed(title="행동 결과", color=discord.Color.purple())
        embed.add_field(name="행동", value=내용, inline=False)
        embed.add_field(name="사용 스탯", value=stat_key, inline=True)
        embed.add_field(name="스탯 값", value=str(stat_value), inline=True)
        embed.add_field(name="주사위 (1d20)", value=str(natural), inline=True)
        embed.add_field(name="총합", value=str(total), inline=True)
        embed.add_field(name="난이도", value=str(difficulty), inline=True)
        result_text = {
            "critical_success": "대성공!",
            "success": "성공",
            "failure": "실패",
            "critical_failure": "대실패",
        }[outcome]
        embed.add_field(name="결과", value=result_text, inline=False)
        if hp_change < 0:
            embed.add_field(name="HP 감소", value=f"{abs(hp_change)} 감소", inline=False)
        if narrative:
            embed.add_field(name="상황 서술", value=narrative[:1024], inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Cog를 비동기로 등록합니다."""
    await bot.add_cog(TRPGCog(bot))
