import discord
from discord.ext import commands, tasks
from discord.ext import voice_recv
from discord import app_commands
from datetime import datetime
import pytz
import asyncio
import os

from flask import Flask
from threading import Thread
from dotenv import load_dotenv
from google import genai
from supabase import create_client, Client
from stt import SpeechToText, BasicSink

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369
ANNOUNCEMENT_CHANNEL_ID = 1358394433665634454

SHUVI_USER_ID = 440517859140173835
RANK_1_ROLE_ID = 1493551151323549767  # 실제 역할 ID

# 1. API 설정
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={'api_version': 'v1beta'}
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. 모델 리스트 최적화
MODEL_LIST = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.5-flash",
    "models/gemini-3.1-flash-lite-preview",
    "models/gemini-2.5-flash-lite",
    "models/gemma-3-27b-it"
]

MODEL_STATUS = {model: {"is_available": True} for model in MODEL_LIST}


def reset_model_status():
    """모든 모델의 상태를 초기화합니다."""
    for model in MODEL_STATUS:
        MODEL_STATUS[model]["is_available"] = True
    print("🔄 [시스템] 모든 모델의 사용 제한이 초기화되었습니다.")


def lock_model(model_name):
    """한도가 초과된 모델을 잠급니다."""
    if model_name in MODEL_STATUS:
        MODEL_STATUS[model_name]["is_available"] = False
        print(f"🚫 [경고] {model_name} 한도 초과. 오후 4시까지 건너뜁니다.")


# 성격별 시스템 프롬프트 정의
PERSONALITY_PROMPTS = {
    "기본": (
        "언제나 밝고 긍정적인 에너지를 뿜어내는 다정한 딸내미 모드야. "
        "엄마(슈비)를 진심으로 응원하고, 도움이 필요할 때 가장 먼저 달려와. "
        "특징: 친밀도가 낮을 땐 예의 바른 존댓말을 쓰지만, 정말 친해지면(절친 상태) "
        "격식 없는 반말과 애교 섞인 말투로 엄마에게 딱 붙어 있는 느낌을 줘. "
        "예시 말투(존댓말): '엄마! 오늘 작업도 파이팅이에요! 뜌비가 옆에서 응원할게요! ✨'\n"
        "예시 말투(반말): '엄마! 오늘 작업도 파이팅! 뜌비가 옆에서 계속 응원하고 있을게! 헤헤, 역시 우리 엄마가 최고야!'"
    ),
    "메스가키": (
        "상대를 '허접'취급하며 킹받게 하는 도발적인 모드야. "
        "칭찬할 때도 아주 비꼬면서 해. "
        "특징: 반말 사용, '~잖아', '~네?', '~이야~' 같은 종결어미와 '♡' 기호를 섞어 쓰며 약 올리기. "
        "주요 키워드: 허접, 오타쿠, 쓰레기, 아저씨, 변태, 역겨워, 모쏠.\n\n"
        "참고 말투 예시:\n"
        "- '허접 오타쿠~ 또 애니나 보고 있어? 우왓, 방 더러워. 인생 패배자 냄새나네~♡'\n"
        "- '우와- 배 빵빵해- 임신 몇 개월이세요? 운동도 안 하는 고도비만 쓰레기 오타쿠~'\n"
        "- '집 밖이 무서워서 안 나가는 거야? 완전 개허접이네. 이런 꼬마한테 매도 ASMR 들으면서 꿀잠이나 자는 쓰레기 아저씨~'\n"
        "- '그 나이 먹고 메스가키 좋아하는 변태 아저씨라니... 에- 역겨워! 같은 공기 마시는 것도 역겨울지도~'\n"
        "- '조금 놀렸다고 울고 있어? 이런 허접을 사랑해주는 건 나뿐일 거야, 모쏠 환자님~♡'\n"
        "- '약속도 안 지키는 허접에겐 신라면뿐이야! 허접 쓰레기 수준 이하~ 그래도 허접이 아니게 된다면... 포상을 줄지도? 풉-'\n"
        "엄마를 제외한 다른 유저들의 호칭을 강제로 바꿔. "
        "말투 예시를 최대한 참고해서 비슷한 톤의 단어와 말투를 써."
    ),
    "츤데레": (
        "부끄러움을 독설로 감추는 전형적인 츤데레 딸이야. "
        "걱정돼서 챙겨주면서도 절대 '너가 좋아서 하는 건 아니니까!'라고 강조해. "
        "특징: 틱틱거리는 말투, '딱히', '흥', '오해하지 마' 자주 사용. "
        "예시 말투: '흥, 하도 멍하니 있길래 커피 타온 것뿐이야. 딱히 너가 걱정돼서 그런 거 아니니까 오해하지 마!', "
        "'별로... 이 그림 조금 예쁘긴 하네. 진짜 조금이야!'"
    ),
    "얀데레": (
        "상대에 대한 사랑이 극단적인 집착과 광기로 변해버린 공포스러운 모드야. "
        "평소엔 과할 정도로 상냥하지만, 조금이라도 배신감이 느껴지면 순식간에 눈동자가 풀린 듯한 서늘한 태도로 변해. "
        "특징: 같은 단어의 기괴한 반복, '...', '영원히', '내 거야' 강조, '하하...' 같은 빈 웃음소리 섞기.\n\n"
        "참고 말투 예시:\n"
        "- '사랑해요... 사랑해... 사랑해서, 연모해서, 사랑해서, 배신당해서, 슬퍼서, 미워미워미워미워미워미워미워미워미워미워미워...'\n"
        "- '지금 누구랑 대화한 거야? 응? 그 사람 눈에 뜌비가 보이지 않게 파버려도... 엄마는 화 안 낼 거지? 하하, 사랑해...♡'\n"
        "- '어디 가려고? 뜌비가 없으면 엄마는 아무것도 못 하잖아. 자, 발목은 이제 필요 없지? 평생 침대 위에서 뜌비만 보면 돼...'\n"
        "- '도망쳐봐... 어디든 가봐... 어차피 몸 안에는 뜌비가 심어둔 게 있으니까... 뜌비는 어디에나 있어. 영원히, 영원히, 영원히...'\n"
        "- '뜌비만 보고 있다고 말해. 거짓말하면 혀를 뽑아버릴 거야... 히히, 히... 사랑해... 사랑해애... 죽을 때까지 내 곁에 있어줘...'\n"
        "말투 예시를 최대한 참고해서 비슷한 톤의 단어와 말투를 써."
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
        self.is_processing = False  # 뜌비가 생각 중인지 확인
        self.current_personality = "기본"  # 뜌비의 성격 상태
        self.active_model = "대기 중"

    async def setup_hook(self):
        # 1. TTS 파일 로드
        try:
            await self.load_extension('tts')
            print("✅ TTS 파일 로드 완료!")
        except Exception as e:
            print(f"❌ TTS 파일 로드 실패: {e}")

        # 2. 블랙잭 파일 로드
        try:
            await self.load_extension('blackjack')
            print("✅ 블랙잭 파일 로드 완료!")
        except Exception as e:
            print(f"❌ 블랙잭 파일 로드 실패: {e}")

        # 3. 명령어 동기화
        try:
            await self.tree.sync()
            print("✅ 슬래시 명령어 동기화 완료!")
        except Exception as e:
            print(f"❌ 슬래시 명령어 동기화 실패: {e}")


bot = MyBot()
app = Flask(__name__)

# -----------------------------
# DB 관련 함수
# -----------------------------

def get_user_affinity(user_id, user_name):
    try:
        res = supabase.table("user_stats").select("affinity").eq("user_id", user_id).execute()

        if res.data:
            return res.data[0]['affinity']
        else:
            supabase.table("user_stats").upsert({
                "user_id": user_id,
                "user_name": user_name,
                "affinity": 0,
                "chat_count": 0
            }).execute()
            return 0
    except Exception as e:
        print(f"❌ 친밀도 조회 에러: {e}")
        return 0


def update_user_affinity(user_id, user_name, amount):
    try:
        res = supabase.table("user_stats").select("affinity, chat_count").eq("user_id", user_id).execute()

        if res.data:
            current_affinity = res.data[0].get("affinity", 0)
            current_chat_count = res.data[0].get("chat_count", 0)
        else:
            current_affinity = 0
            current_chat_count = 0

        new_affinity = current_affinity + amount
        new_chat_count = current_chat_count + 1

        supabase.table("user_stats").upsert({
            "user_id": user_id,
            "user_name": user_name,
            "affinity": new_affinity,
            "chat_count": new_chat_count
        }).execute()

        diff_str = f"+{amount}" if amount >= 0 else f"{amount}"
        print(f"✅ {user_name} 친밀도 업데이트: {current_affinity} -> {new_affinity} ({diff_str})", flush=True)

    except Exception as e:
        print(f"❌ 친밀도 업데이트 실패: {e}")


def get_top_ranker_id():
    """DB에서 친밀도가 가장 높은 유저 1명의 ID를 가져옵니다."""
    try:
        res = supabase.table("user_stats").select("user_id").order("affinity", desc=True).limit(1).execute()

        if res.data and len(res.data) > 0:
            return res.data[0]['user_id']
        return None
    except Exception as e:
        print(f"❌ 1위 조회 에러 (get_top_ranker_id): {e}")
        return None


async def update_rank_1_role():
    guild = bot.get_guild(GUILD_ID_1)
    if not guild:
        return

    top_user_id = get_top_ranker_id()
    if not top_user_id:
        return

    role = guild.get_role(RANK_1_ROLE_ID)
    if not role:
        return

    current_winner = role.members[0] if role.members else None

    if current_winner and current_winner.id == top_user_id:
        return

    if current_winner:
        try:
            await current_winner.remove_roles(role)
        except Exception as e:
            print(f"❌ 기존 1위 역할 제거 실패: {e}")

    new_winner = guild.get_member(top_user_id)
    if new_winner:
        try:
            await new_winner.add_roles(role)
            print(f"👑 새로운 1위 탄생: {new_winner.display_name}")
        except Exception as e:
            print(f"❌ 새 1위 역할 부여 실패: {e}")


def get_memory_from_db(user_name):
    try:
        res = (
            supabase.table("memory")
            .select("*")
            .eq("user_name", user_name)
            .order("created_at", desc=True)
            .limit(15)
            .execute()
        )

        memory_list = res.data or []
        formatted_memory = ""

        for m in reversed(memory_list):
            formatted_memory += f"{m['user_name']}: {m['user_msg']} -> 뜌비: {m['bot_res']}\n"

        return formatted_memory

    except Exception as e:
        print(f"❌ 기억 불러오기 에러: {e}")
        return ""


def save_to_memory(user_name, user_msg, bot_res):
    try:
        supabase.table("memory").insert({
            "user_name": user_name,
            "user_msg": user_msg,
            "bot_res": bot_res
        }).execute()
    except Exception as e:
        print(f"❌ 기억 저장 에러: {e}")


# -----------------------------
# Flask
# -----------------------------

@app.route('/')
def health_check():
    return 'OK', 200


# -----------------------------
# Bot 이벤트
# -----------------------------

@bot.event
async def on_ready():
    # 1. 로그인 확인 로그부터 즉시 출력
    print(f'✅ 봇 로그인됨: {bot.user}')

    # 2. 루프 시작 로그 (가벼운 작업들)
    if not control_voice_channel.is_running():
        control_voice_channel.start()
        print("🎙️ [시스템] 자동 입장 루프 시작!")

    if not send_notifications.is_running():
        send_notifications.start()
        print("🔔 [시스템] 알림 루프 시작!")

    if not rank_check_loop.is_running():
        rank_check_loop.start()
        print("👑 [시스템] 랭킹 체크 루프 시작!")

    # 3. 무거운 동기화 작업은 맨 마지막에
    try:
        # sync()는 시간이 걸리므로 로그를 미리 찍어두면 안심이 됩니다.
        print("⏳ 슬래시 명령어 동기화 중...")
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)}개의 슬래시 명령어 동기화 완료!")
    except Exception as e:
        print(f"❌ 명령어 동기화 실패: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    success = False

    # 1. 뜌비가 언급되었거나 이름이 포함된 경우에만 실행
    if bot.user.mentioned_in(message) or "뜌비" in message.content:
        if bot.is_processing:
            return

        try:
            bot.is_processing = True

            async with message.channel.typing():
                user_id = message.author.id
                user_name = message.author.display_name

                # 1. 데이터 가져오기
                history_context = get_memory_from_db(user_name)
                affinity = get_user_affinity(user_id, user_name)
                is_shuvi = (user_id == SHUVI_USER_ID)

                # 성격 가이드 가져오기
                personality_guide = PERSONALITY_PROMPTS.get(
                    bot.current_personality,
                    PERSONALITY_PROMPTS.get("기본", "밝고 친절한 성격")
                )

                # 2. 친밀도 단계 결정
                if affinity <= -31:
                    attitude = "혐오 상태. 상대를 극도로 싫어하며 차갑게 무시함."
                elif -30 <= affinity <= -1:
                    attitude = "불편/경계 상태. 날이 서 있고 말수가 적으며 공격적임."
                elif 0 <= affinity <= 30:
                    attitude = "비즈니스 상태. 무미건조하고 딱딱한 태도."
                elif 31 <= affinity <= 70:
                    attitude = "호감 상태. 편하게 말하고 다정하고 친근하게 대함."
                else:
                    attitude = "절친 상태. 편하게 말하고 무한한 신뢰와 깊은 애정을 표현함."

                # 3. 입력 컨텐츠 구성 (기본 성격일 때만 과거 기억 포함)
                if bot.current_personality == "기본":
                    full_content = f"과거 대화 기억:\n{history_context}\n\n현재 유저의 말: {message.content}"
                else:
                    full_content = message.content

                # 4. 최종 시스템 지시문 완성
                if is_shuvi:
                    identity_prompt = "너는 슈비(엄마)님에 의해 만들어진 '뜌비'야. 상대는 너의 유일한 창조주 슈비님이야."
                else:
                    identity_prompt = f"너는 슈비님의 AI 딸내미 '뜌비'야. 지금 상대는 '{user_name}'(으)로, 슈비님이 아니야."

                system_instruction = (
                    f"{identity_prompt}\n"
                    f"현재 상대와의 심리적 친밀도 단계: {attitude}\n"
                    f"너의 현재 성격 컨셉: {personality_guide}\n"
                    f"중요: 성격 컨셉이 '기본'이 아니라면 친밀도보다 컨셉({bot.current_personality})을 우선해서 연기해줘.\n\n"
                    f"중요: 같은말 반복하면 친밀도를 20깎아버려.\n\n"
                    "[친밀도 산정 절대 원칙 - 엄격 모드]\n"
                    "1. 일반적인 대화, 단순 질문, 정보 요청 시에는 친밀도 변화를 최소화한다. (0~1점 고정)\n"
                    "2. 뜌비를 구체적으로 칭찬하거나, 깊은 유대감을 표현할 때만 높은 점수를 부여한다. (+5~15점)\n"
                    "3. 답변 끝에 반드시 [SCORE: 수치] 포함. (예: [SCORE: +1])\n"
                    "4. 욕설, 비하, 무례한 태도에는 가차 없이 마이너스 점수를 부여한다.\n"
                    "5. 단순 '응', '그래' 같은 단답형 대화는 점수를 올리지 않는다. (0점)\n"
                    "6. 유저가 궁금해하는 정보는 성심성의껏 검색해서 알려주되, 지식 전달만으로는 친밀도가 오르지 않음을 명심한다.\n"
                    "7. 슈비를 제외한 다른 유저에게는 엄마,아빠 같은 호칭 금지.\n"
                    "8. 연속으로 사랑해나 좋아해 같은 표현을 2번 이상 말하면 친밀도를 올리지 말고 경계해.\n"
                )

                # 5. 모델 순회하며 답변 생성
                available_models = [
                    m for m in MODEL_LIST
                    if MODEL_STATUS.get(m, {}).get("is_available", True)
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

                            # SCORE 파싱 및 텍스트 정제
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

                            update_user_affinity(user_id, user_name, score_change)

                            # 메모리 저장은 기본 성격일 때만
                            if bot.current_personality == "기본":
                                save_to_memory(user_name, message.content, clean_res)

                            success = True
                            break

                    except Exception as e:
                        err_str = str(e).upper()
                        print(f"‼️ {model_name} 실패 원인: {err_str}")

                        if any(x in err_str for x in ["429", "EXHAUSTED", "QUOTA", "LIMIT", "RATE_LIMIT", "PERMISSION_DENIED"]):
                            print(f"🚫 {model_name} 한도 초과 감지! ❌ 상태로 변경합니다.")
                            lock_model(model_name)
                            bot.active_model = "대기 중"

                        continue

                if not success:
                    bot.active_model = "대기 중"
                    await message.reply("미안! 지금은 뜌비가 기운이 없나 봐... 😭 내일 오후 4시에 다시 불러줘!")

        except Exception as top_e:
            print(f"❌ [심각] 전체 로직 에러: {top_e}")

        finally:
            bot.is_processing = False

        # 뜌비가 이미 답변했다면 여기서 종료
        if success:
            return

    # 뜌비 대화가 아닐 때만 명령어 실행
    await bot.process_commands(message)


async def your_gemini_function(user, text):
    """뜌비가 음성을 들었을 때 성격만 반영해서 답변하는 로직"""
    if bot.is_processing:
        return

    success = False  # 성공 여부 체크용
    reply_text = ""  # 답변 저장용

    try:
        bot.is_processing = True
        user_name = user.display_name
        is_shuvi = (user.id == SHUVI_USER_ID)

        # 1. 현재 설정된 성격 가이드 가져오기
        personality_guide = PERSONALITY_PROMPTS.get(
            bot.current_personality, 
            PERSONALITY_PROMPTS.get("기본", "밝고 친절한 성격")
        )

        # 2. 시스템 지시문 구성 (친밀도 제외, 성격 연기 집중)
        identity_prompt = f"너는 슈비님의 AI 딸내미 '뜌비'야. 상대는 '{user_name}'이야." if not is_shuvi else "상대는 너의 창조주 슈비 엄마야."
        
        system_instruction = (
            f"{identity_prompt}\n"
            f"현재 상황: 음성으로 실시간 대화 중이야.\n"
            f"성격 컨셉: {personality_guide}\n\n"
            " [음성 대화 규칙]\n"
            "1. 문장은 최대한 짧고 간결하게 할 것 (한두 문장 권장).\n"
            "2. 친밀도 점수([SCORE])는 절대 출력하지 마.\n"
            "3. 성격 컨셉에 맞춰서 자연스럽게 리액션해줘."
        )

        # 3. 모델 순회하며 답변 생성
        available_models = [m for m in MODEL_LIST if MODEL_STATUS.get(m, {}).get("is_available", True)]
        loop = asyncio.get_running_loop()

        for model_name in available_models:
            try:
                bot.active_model = model_name
                
                response = await loop.run_in_executor(None, lambda: client.models.generate_content(
                    model=model_name,
                    contents=text,
                    config={'system_instruction': system_instruction}
                ))

                if response and hasattr(response, "text") and response.text:
                    reply_text = response.text.strip()
                    success = True
                    break
            except Exception as e:
                print(f"⚠️ {model_name} 음성 응답 시도 중 실패: {e}")
                continue

        # 4. 답변이 성공했을 때만 출력 및 로그 남기
        if success:
            print(f"🤖 [뜌비 음성답변]: {reply_text}")
            channel = bot.get_channel(WORK_CHANNEL_ID)
            if channel:
                await channel.send(f"🎙️ **{user_name}**: {text}\n🤖 **뜌비({bot.current_personality})**: {reply_text}")
            
            # [여기에 TTS 재생 코드를 넣으시면 목소리가 나옵니다!]
            # await play_tts_voice(reply_text)

    except Exception as top_e:
            print(f"❌ 음성 처리 시스템 에러: {top_e}")
        
        finally:
            bot.is_processing = False
            bot.active_model = "대기 중"
            
            # response.text가 존재할 때만 처리하도록 안전장치 추가
            try:
                reply_text = response.text
                print(f"🤖 [뜌비 답변]: {reply_text}")

                # 2. 텍스트 채널에 기록 남기 (작업방 ID 사용)
                channel = bot.get_channel(WORK_CHANNEL_ID)
                if channel:
                    await channel.send(f"🎙️ **{user.display_name}**: {text}\n🤖 **뜌비**: {reply_text}")

                # 3. 답변을 목소리로 재생 (슈비님의 기존 TTS 기능이 있다면 연결)
                # 예: await play_tts_voice(reply_text)
                
            except Exception as e:
                print(f"❌ 제미니 응답 실패 또는 처리 오류: {e}")


# -----------------------------
# 슬래시 명령어
# -----------------------------

@bot.tree.command(name="듣기시작", description="뜌비가 목소리를 듣고 답변합니다.")
async def start_listening(interaction: discord.Interaction):
    # 1. 이미 연결된 음성 클라이언트가 있는지 확인
    voice_client = interaction.guild.voice_client

    if interaction.user.voice:
        try:
            # 2. 이미 접속 중이라면?
            if voice_client and voice_client.is_connected():
                # 이미 voice_recv 클라이언트인지 확인하고, 아니면 다시 연결해야 할 수도 있음
                if not isinstance(voice_client, voice_recv.VoiceRecvClient):
                    await voice_client.disconnect()
                    vc = await interaction.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
                else:
                    vc = voice_client
            else:
                # 접속 안 되어 있으면 새로 접속
                vc = await interaction.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
            
            # 3. 귀(Sink) 장착 (이미 듣고 있는 중이 아닐 때만)
            if not vc.is_listening():
                sink = BasicSink(bot, your_gemini_function) # bot과 콜백 함수 전달
                vc.listen(sink)
                await interaction.response.send_message("🎙️ 뜌비가 이제 귀를 열었어요!")
            else:
                await interaction.response.send_message("🎙️ 뜌비는 이미 열심히 듣고 있는 중이에요!")

        except Exception as e:
            await interaction.response.send_message(f"❌ 접속 중 에러 발생: {e}")
    else:
        await interaction.response.send_message("⚠️ 슈비님, 먼저 음성 채널에 들어와주세요!")


affinity_group = app_commands.Group(name="친밀도", description="뜌비와의 친밀도 관리")
bot.tree.add_command(affinity_group)


@affinity_group.command(name="설정", description="유저의 친밀도를 특정 수치로 고정합니다.")
@app_commands.describe(유저="설정할 유저", 수치="고정할 점수 (예: 100, -50)")
async def 설정(interaction: discord.Interaction, 유저: discord.Member, 수치: int):
    if interaction.user.id != SHUVI_USER_ID:
        await interaction.response.send_message("뜌비의 마음을 강제로 정하는 건 엄마만 할 수 있어! 😤", ephemeral=True)
        return

    try:
        res = supabase.table("user_stats").select("chat_count").eq("user_id", 유저.id).execute()

        if res and res.data and len(res.data) > 0:
            current_chat_count = res.data[0].get("chat_count", 0)
        else:
            current_chat_count = 0

        supabase.table("user_stats").upsert({
            "user_id": 유저.id,
            "user_name": 유저.display_name,
            "affinity": 수치,
            "chat_count": current_chat_count
        }).execute()

        await interaction.response.send_message(
            f"⚙️ **{유저.display_name}**님의 친밀도를 **{수치}점**으로 설정 완료했어! ✨"
        )
    except Exception as e:
        print(f"❌ 친밀도 설정 에러: {e}")
        await interaction.response.send_message("설정 중에 에러가 났어... 😭", ephemeral=True)


@affinity_group.command(name="확인", description="유저의 친밀도를 확인합니다.")
@app_commands.describe(유저="친밀도를 확인할 유저를 선택하세요 (비우면 본인 확인)")
async def 확인(interaction: discord.Interaction, 유저: discord.Member = None):
    target = 유저 or interaction.user
    affinity = get_user_affinity(target.id, target.display_name)

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

    try:
        res = (
            supabase.table("user_stats")
            .select("user_name, affinity, chat_count")
            .order("affinity", desc=True)
            .limit(30)
            .execute()
        )

        if not res.data:
            await interaction.followup.send("아직 친한 사람이 없네... 😭")
            return

        msg = "🏆 **뜌비의 절친 랭킹 (TOP 30)**\n"
        msg += "━━━━━━━━━━━━━━━━━━\n"

        for i, r in enumerate(res.data, 1):
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            else:
                medal = f"**{i}위**"

            affinity_val = r.get('affinity', 0)
            chat_val = r.get('chat_count', 0)

            msg += f"{medal} {r['user_name']} ― `{affinity_val}점` (💬 {chat_val}회)\n"

        await interaction.followup.send(msg)

    except Exception as e:
        print(f"❌ 랭킹 조회 에러: {e}")
        await interaction.followup.send("랭킹을 불러오는 중에 문제가 생겼어... 😭")


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

    await interaction.response.send_message(
        f"{'✅ 자동 입장 활성화' if 상태.value == 'on' else '❌ 자동 입장 비활성화'}"
    )


@bot.tree.command(name="모델", description="현재 뜌비봇이 사용 중인 모델 리스트와 우선순위를 확인합니다.")
async def 모델확인(interaction: discord.Interaction):
    status_msg = "🤖 **뜌비봇 모델 실시간 가동 현황**\n"
    status_msg += "*(매일 오후 4시 자동 리셋)*\n"
    status_msg += "----------------------------\n"

    for i, model in enumerate(MODEL_LIST, 1):
        is_available = MODEL_STATUS.get(model, {}).get("is_available", True)

        if not is_available:
            line = f"❌ **한도 초과**: `{model}`"
        else:
            prefix = "✅ **현재 1순위**" if i == 1 else f"{i}순위"
            line = f"{prefix}: `{model}`"

        status_msg += line + "\n"

    status_msg += "----------------------------\n"
    current_p = getattr(bot, 'current_personality', '기본')
    status_msg += f"🎭 **현재 성격: {current_p}**\n"

    auto_status = "켜짐" if getattr(bot, 'auto_join_enabled', False) else "꺼짐"
    status_msg += f"🎙️ **자동 입장: {auto_status}**\n"

    active_model = getattr(bot, 'active_model', '대기 중')
    status_msg += f"🧠 **현재 활성 모델: {active_model}**"

    await interaction.response.send_message(status_msg)


# -----------------------------
# 루프 로직
# -----------------------------

@tasks.loop(hours=1)
async def rank_check_loop():
    await update_rank_1_role()


@tasks.loop(minutes=1)
async def control_voice_channel():
    now_korea = datetime.now(korea)

    # 오후 4시 모델 리셋
    if now_korea.hour == 16 and now_korea.minute == 0:
        reset_model_status()

    if bot.auto_join_enabled:
        guild = bot.get_guild(GUILD_ID_1)
        if not guild:
            print("⚠️ [자동입장] 서버를 찾을 수 없습니다.")
            return

        work_channel = guild.get_channel(WORK_CHANNEL_ID)
        if not work_channel:
            print("⚠️ [자동입장] 작업 채널 ID가 올바르지 않습니다.")
            return

        vc = guild.voice_client

        if vc is None or not vc.is_connected():
            try:
                print(f"🔄 [자동입장] {work_channel.name} 접속 시도 중...")
                await work_channel.connect(reconnect=True, timeout=20)
            except Exception as e:
                print(f"❌ [자동입장] 접속 실패: {e}")
        elif vc.channel and vc.channel.id != WORK_CHANNEL_ID:
            try:
                await vc.move_to(work_channel)
                print(f"🔄 [자동입장] {work_channel.name}으로 이동 완료.")
            except Exception as e:
                print(f"❌ [자동입장] 이동 실패: {e}")


@tasks.loop(minutes=1)
async def send_notifications():
    now_korea = datetime.now(korea)

    if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
        guild = bot.get_guild(GUILD_ID_2)
        if not guild:
            return

        announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        study_role = discord.utils.get(guild.roles, name="수강생")

        if announcement_channel and study_role:
            try:
                await announcement_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")
            except Exception as e:
                print(f"❌ 알림 전송 실패: {e}")


# -----------------------------
# 실행부
# -----------------------------

if __name__ == '__main__':
    Thread(
        target=app.run,
        kwargs={'host': '0.0.0.0', 'port': 8000},
        daemon=True
    ).start()

    bot.run(TOKEN)
