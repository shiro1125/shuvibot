import discord
from discord.ext import commands
from discord import app_commands
from discord.ext import voice_recv
import asyncio
import os

# 내부 모듈 임포트
from stt import BasicSink
import tts_module
import affinity_manager
import personality
from google import genai


def _create_client():
    """
    genai.Client 인스턴스를 생성합니다. bot.py와 동일한 설정을 적용해
    기존 모델 리스트를 사용하여 음성 채팅에서도 일관된 응답을 생성합니다.
    """
    api_key = os.getenv('GEMINI_API_KEY')
    # api_version은 bot.py에서와 동일하게 지정합니다.
    return genai.Client(api_key=api_key, http_options={'api_version': 'v1beta'})


class VoiceChatCog(commands.Cog):
    """
    음성 채널에서 사용자의 음성을 실시간으로 듣고 텍스트로 변환(STT)한 후
    AI 모델을 통해 응답을 생성하고, 이를 다시 음성으로 출력(TTS)하는 기능을 담당합니다.

    /듣기 ON 명령으로 활성화되고 /듣기 OFF 명령으로 비활성화됩니다.
    기본 봇 기능과 충돌하지 않도록, 비동기 상태 플래그를 사용하여 동시에 하나의
    응답만 처리하도록 합니다.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.listening: bool = False
        self.vc: discord.VoiceClient | None = None
        self.sink: BasicSink | None = None
        # genai 클라이언트는 생성 비용이 크므로 Cog 초기화 시 생성해 둡니다.
        self.genai_client = _create_client()

    @app_commands.command(name="듣기", description="음성 인식 및 응답 기능을 켜거나 끕니다.")
    @app_commands.guilds(1228372760212930652)  # 특정 길드에서 슬래시 명령어를 즉시 등록합니다.
    @app_commands.choices(상태=[
        app_commands.Choice(name="ON", value="on"),
        app_commands.Choice(name="OFF", value="off")
    ])
    async def listen_control(self, interaction: discord.Interaction, 상태: app_commands.Choice[str]):
        """
        슬래시 명령어로 음성 기능을 제어합니다.
        - ON: 현재 사용자가 참여한 음성 채널에 봇이 입장하고, 음성을 수신하여 AI 응답을 음성으로 재생합니다.
        - OFF: 현재 음성 수신을 중단하고, 등록된 싱크를 정리합니다.
        """
        # ON 처리
        if 상태.value == "on":
            # 이미 활성화 상태면 다시 켜지 않음
            if self.listening:
                await interaction.response.send_message("이미 음성 인식이 활성화되어 있어요!", ephemeral=True)
                return
            # 음성 채널에 참가하지 않은 경우 안내
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.response.send_message("⚠️ 먼저 음성 채널에 들어가 주세요!", ephemeral=True)
                return
            channel = interaction.user.voice.channel
            try:
                # 현재 길드에 접속된 VoiceClient 확인
                vc = interaction.guild.voice_client
                # 기존에 일반 VoiceClient로 연결된 경우 강제 종료 후 새로 연결합니다.
                if vc and not isinstance(vc, voice_recv.VoiceRecvClient):
                    try:
                        # force=True로 강제 종료하여 연결이 완전히 끊어지도록 합니다.
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
                    vc = None

                if not vc:
                    # 연결되어 있지 않거나 이전 연결을 끊은 경우 새로 VoiceRecvClient로 접속
                    self.vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
                else:
                    # 이미 VoiceRecvClient로 연결되어 있으면 그대로 사용하고 채널만 이동
                    self.vc = vc
                    if self.vc.channel != channel:
                        await self.vc.move_to(channel)
                # BasicSink를 생성하고 콜백 등록
                self.sink = BasicSink(self.bot, self.handle_speech)
                self.vc.listen(self.sink)
                self.listening = True
                await interaction.response.send_message("🎧 음성 인식이 활성화되었습니다.", ephemeral=True)
            except Exception as e:
                # 실패 시 플래그 및 리소스 초기화
                self.listening = False
                self.vc = None
                self.sink = None
                await interaction.response.send_message(f"❌ 음성 인식 활성화 실패: {e}", ephemeral=True)
        # OFF 처리
        else:
            # 비활성화 플래그를 먼저 설정하여 콜백 실행을 차단
            self.listening = False
            # 음성 수신 중지 및 싱크 정리
            vc = interaction.guild.voice_client
            if vc:
                try:
                    # VoiceRecvClient이면 stop_listening 사용
                    if hasattr(vc, "stop_listening"):
                        vc.stop_listening()
                    else:
                        vc.stop()
                except Exception:
                    pass
            if self.sink:
                try:
                    self.sink.cleanup()
                except Exception:
                    pass
            self.sink = None
            self.vc = None
            await interaction.response.send_message("🛑 음성 인식이 비활성화되었습니다.", ephemeral=True)

    async def handle_speech(self, user: discord.Member, text: str):
        """
        STT 모듈에서 텍스트가 생성되면 호출되는 콜백입니다.
        사용자 발화에 대해 AI 응답을 생성하고, TTS로 음성 재생을 수행합니다.
        """
        # 음성 시스템이 비활성화됐거나 다른 작업 중이면 무시
        if not self.listening or self.bot.is_processing:
            return
        try:
            self.bot.is_processing = True
            user_id = user.id
            user_name = user.display_name
            # 과거 대화 및 친밀도 정보 조회
            history_context = affinity_manager.get_memory_from_db(user_name)
            affinity = affinity_manager.get_user_affinity(user_id, user_name)
            is_shuvi = (user_id == 440517859140173835)
            personality_guide = personality.get_personality_guide(self.bot.current_personality)
            attitude = affinity_manager.get_attitude_guide(affinity)
            # 콘텐츠 구성: 기본 성격이면 과거 대화 포함
            if self.bot.current_personality == "기본":
                full_content = f"과거 대화 기억:\n{history_context}\n\n현재 유저의 말: {text}"
            else:
                full_content = text
            system_instruction = personality.make_system_instruction(
                is_shuvi, user_name, self.bot.current_personality, attitude, personality_guide
            )
            # 사용 가능한 모델 추려서 순차 시도
            available_models = [m for m in self.bot.model_list if self.bot.model_status.get(m, {}).get("is_available", True)]
            loop = asyncio.get_running_loop()
            response_text = None
            for model_name in available_models:
                try:
                    self.bot.active_model = model_name
                    # gemma 계열일 경우 프롬프트 형식 다르게 구성
                    if "gemma" in model_name.lower():
                        prompt = f"[시스템 지침]\n{system_instruction}\n\n유저 메시지: {full_content}"
                        response = await loop.run_in_executor(
                            None,
                            lambda: self.genai_client.models.generate_content(
                                model=model_name,
                                contents=prompt
                            )
                        )
                    else:
                        response = await loop.run_in_executor(
                            None,
                            lambda: self.genai_client.models.generate_content(
                                model=model_name,
                                contents=full_content,
                                config={'system_instruction': system_instruction}
                            )
                        )
                    if response and getattr(response, "text", None):
                        full_text = response.text
                        clean_res = full_text
                        score_change = 0
                        # 점수 파싱
                        if "[SCORE:" in full_text:
                            try:
                                parts = full_text.split("[SCORE:")
                                clean_res = parts[0].strip()
                                score_val_str = parts[1].split("]")[0].strip()
                                raw_score = int(score_val_str.replace("+", ""))
                                score_change = max(-20, min(20, raw_score))
                            except Exception:
                                clean_res = full_text
                                score_change = 0
                        response_text = clean_res
                        # 친밀도 업데이트 및 메모리 저장
                        affinity_manager.update_user_affinity(user_id, user_name, score_change)
                        if self.bot.current_personality == "기본":
                            affinity_manager.save_to_memory(user_name, text, clean_res)
                        break
                except Exception as e:
                    err_str = str(e).upper()
                    # 한도 초과 관련 에러 감지 시 모델 잠금
                    if any(x in err_str for x in ["429", "EXHAUSTED", "QUOTA", "LIMIT", "RATE_LIMIT", "PERMISSION_DENIED"]):
                        self.bot.lock_model(model_name)
                        self.bot.active_model = "대기 중"
                    continue
            # 응답 텍스트가 생성되면 TTS 재생
            if response_text and self.vc and self.vc.is_connected():
                filename = f"tts_{user_id}.mp3"
                success = tts_module.generate_tts(response_text, filename)
                if success:
                    try:
                        if self.vc.is_playing():
                            self.vc.stop()
                        source = discord.FFmpegPCMAudio(filename)
                        def _after_play(error: Exception | None):
                            # 재생 후 임시 파일 삭제
                            try:
                                if os.path.exists(filename):
                                    os.remove(filename)
                            except Exception:
                                pass
                        self.vc.play(source, after=lambda e: _after_play(e))
                    except Exception as e:
                        print(f"❌ [음성 시스템] 음성 재생 실패: {e}")
                else:
                    print("❌ [TTS] 음성 파일 생성 실패")
        except Exception as e:
            # 콜백 내 예상치 못한 오류 로깅
            print(f"❌ [음성 시스템] 콜백 오류: {e}")
        finally:
            self.bot.is_processing = False


async def setup(bot: commands.Bot):
    """
    Cog를 비동기로 로드합니다. bot.py의 setup_hook에서 이 모듈을 불러와
    슬래시 명령어가 동기화될 수 있도록 합니다.
    """
    await bot.add_cog(VoiceChatCog(bot))
