import discord
from discord.ext import voice_recv
import speech_recognition as sr
import asyncio
import time

# 음성 인식기 초기화
r = sr.Recognizer()


class BasicSink(voice_recv.AudioSink):
    """
    음성 패킷을 받아 버퍼에 저장하고 일정 시간 침묵이 감지되면
    Google SpeechRecognition을 통해 텍스트로 변환하여 콜백을 호출합니다.

    이 구현에는 자세한 로그가 포함되어 있어 디버깅 시 누가 말했고
    얼마나 많은 오디오 데이터가 수신되었는지, 언제 STT가 실행됐는지 등을
    콘솔에서 확인할 수 있습니다.
    """

    def __init__(self, bot, text_callback):
        super().__init__()
        self.bot = bot
        self.text_callback = text_callback
        self.audio_buffer = bytearray()
        self.last_speaking_time = 0
        self.is_processing = False
        self.current_user = None
        self.buffer_lock = asyncio.Lock()
        # Timestamp when the first packet of the current utterance was received.
        # Used to trigger STT even when there is continuous speech with no silence.
        self.first_packet_time = 0.0
        # Maximum duration (in seconds) to wait before forcing STT on the buffered audio.
        self.MAX_PROCESS_DELAY = 2.0

        # 설정값
        # 침묵 감지 임계값(초)
        # 음성 수신 환경에서 디스코드 패킷이 계속 들어오는 경우 침묵을 포착하기 어려워
        # STT가 실행되지 않는 문제가 있었으므로 임계값을 0.8초로 낮췄습니다.
        self.SILENCE_THRESHOLD = 0.8
        # 최소 버퍼 크기: 약 0.3초 분량의 PCM 데이터(48kHz * 2채널 * 16비트 * 0.3초)
        # 버퍼가 이 값 이상 모이면 STT를 수행하도록 하여 짧은 발화도 인식할 수 있게 했습니다.
        self.MIN_BUFFER_SIZE = int(48000 * 2 * 2 * 0.3)

    def wants_opus(self) -> bool:
        # PCM(생소리) 데이터를 받습니다.
        return False

    def write(self, user, data):
        """
        디스코드로부터 음성 패킷을 받는 부분입니다.
        여기서는 최대한 안전하게 버퍼만 쌓고, 실제 처리는 check_silence에서 합니다.
        """
        try:
            if not data or not getattr(data, "pcm", None):
                return

            pcm = data.pcm
            if not pcm:
                return

            # 로그: 오디오 패킷 수신
            try:
                print(
                    f"[STT] 오디오 패킷 수신: 사용자 {user.display_name} ({user.id}), 길이 {len(pcm)}",
                    flush=True,
                )
            except Exception:
                pass

            # write는 sync 함수라 직접 await 못 하므로 빠르게 버퍼 추가만 처리
            now = time.time()
            # 초기 발화 시각을 기록하여 연속 발화 시에도 일정 시간이 지나면 STT를 강제로 실행할 수 있도록 합니다.
            if self.first_packet_time == 0.0:
                self.first_packet_time = now
            self.audio_buffer.extend(pcm)
            self.last_speaking_time = now
            self.current_user = user

            # 이미 침묵 체크 중이 아니면 한 번만 실행
            if not self.is_processing:
                self.is_processing = True
                asyncio.run_coroutine_threadsafe(
                    self.check_silence(),
                    self.bot.loop
                )

        except Exception as e:
            print(f"⚠️ [STT] 패킷 처리 중 오류 발생: {e}", flush=True)

    async def check_silence(self):
        """침묵을 감지하고 텍스트 변환을 시작합니다."""
        try:
            while True:
                await asyncio.sleep(0.5)
                current_time = time.time()

                # 말 끝났고 버퍼가 충분할 때 처리
                # 두 조건 중 하나 충족 시 STT 실행:
                # 1) 침묵이 일정 시간 지속되고 버퍼가 충분할 때
                # 2) 첫 패킷 이후 최대 시간(MAX_PROCESS_DELAY)이 경과하고 버퍼가 충분할 때
                silence_cond = (
                    current_time - self.last_speaking_time > self.SILENCE_THRESHOLD
                    and len(self.audio_buffer) > self.MIN_BUFFER_SIZE
                )
                force_cond = (
                    self.first_packet_time != 0.0
                    and (current_time - self.first_packet_time > self.MAX_PROCESS_DELAY)
                    and len(self.audio_buffer) > self.MIN_BUFFER_SIZE
                )
                if silence_cond or force_cond:
                    async with self.buffer_lock:
                        audio_to_process = bytes(self.audio_buffer)
                        user = self.current_user
                        # 다음 발화를 위해 먼저 초기화
                        self.audio_buffer = bytearray()
                        self.current_user = None
                        # reset timestamps
                        self.first_packet_time = 0.0

                    # 로그: 침묵 감지 및 STT 시작
                    try:
                        if silence_cond:
                            # 침묵으로 인한 트리거
                            print(
                                f"[STT] 침묵 감지됨. 사용자 {getattr(user, 'display_name', '?')}의 음성 변환을 시작합니다.",
                                flush=True,
                            )
                        else:
                            # 시간 초과로 인한 강제 트리거
                            print(
                                f"[STT] 최대 대기시간 초과. 사용자 {getattr(user, 'display_name', '?')}의 음성 변환을 시작합니다.",
                                flush=True,
                            )
                    except Exception:
                        pass

                    try:
                        text = await transcribe_audio(audio_to_process)
                    except Exception as e:
                        print(f"⚠️ [STT] 변환 실패: {e}", flush=True)
                        text = None

                    if text and user:
                        try:
                            print(
                                f"[STT] 변환된 텍스트: 사용자 {user.display_name} ({user.id}) -> '{text}'",
                                flush=True,
                            )
                        except Exception:
                            pass
                        try:
                            await self.text_callback(user, text)
                        except Exception as e:
                            print(f"❌ [STT] text_callback 실행 실패: {e}", flush=True)

                    break

                # 너무 오래 데이터가 안 들어오면 버퍼 비우고 종료
                if current_time - self.last_speaking_time > 10:
                    async with self.buffer_lock:
                        self.audio_buffer = bytearray()
                        self.current_user = None
                    break

        except Exception as e:
            print(f"❌ [STT] check_silence 내부 오류: {e}", flush=True)

        finally:
            self.is_processing = False

    def cleanup(self):
        self.audio_buffer.clear()
        self.current_user = None
        self.is_processing = False


async def transcribe_audio(audio_bytes):
    """바이트 데이터를 텍스트로 변환하는 헬퍼 함수"""
    if not audio_bytes:
        return None

    # 너무 짧은 오디오는 무시
    if len(audio_bytes) < 16000:
        return None

    try:
        # 로그: STT 시작
        print(f"[STT] 음성 데이터 길이 {len(audio_bytes)} bytes. 음성을 텍스트로 변환합니다.", flush=True)

        # 디스코드 PCM: 48000Hz, 16-bit, 2채널
        audio_data = sr.AudioData(audio_bytes, 48000, 2)

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(
            None,
            lambda: r.recognize_google(audio_data, language="ko-KR")
        )
        return text

    except sr.UnknownValueError:
        # 소리는 들렸지만 무슨 말인지 모를 때
        return None

    except sr.RequestError as e:
        print(f"❌ [STT] Google STT 서비스 에러: {e}", flush=True)
        return None

    except Exception as e:
        print(f"❌ [STT] STT 변환 중 예상치 못한 에러: {e}", flush=True)
        return None
