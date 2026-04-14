import discord
from discord.ext import voice_recv
import speech_recognition as sr
import asyncio
import time

# 음성 인식기 초기화
r = sr.Recognizer()


class BasicSink(voice_recv.AudioSink):
    def __init__(self, bot, text_callback):
        super().__init__()
        self.bot = bot
        self.text_callback = text_callback
        self.audio_buffer = bytearray()
        self.last_speaking_time = 0
        self.is_processing = False
        self.current_user = None
        self.buffer_lock = asyncio.Lock()

        # 설정값
        self.SILENCE_THRESHOLD = 1.5  # 1.5초간 조용하면 말이 끝난 것으로 간주
        self.MIN_BUFFER_SIZE = int(48000 * 2 * 2 * 0.5)  # 최소 0.5초 이상 데이터일 때만 처리

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

            # write는 sync 함수라 직접 await 못 하므로 빠르게 버퍼 추가만 처리
            self.audio_buffer.extend(pcm)
            self.last_speaking_time = time.time()
            self.current_user = user

            # 이미 침묵 체크 중이 아니면 한 번만 실행
            if not self.is_processing:
                self.is_processing = True
                asyncio.run_coroutine_threadsafe(
                    self.check_silence(),
                    self.bot.loop
                )

        except Exception as e:
            print(f"⚠️ [음성 시스템] 패킷 처리 중 오류 발생: {e}", flush=True)

    async def check_silence(self):
        """침묵을 감지하고 텍스트 변환을 시작합니다."""
        try:
            while True:
                await asyncio.sleep(0.5)
                current_time = time.time()

                # 말 끝났고 버퍼가 충분할 때 처리
                if (
                    current_time - self.last_speaking_time > self.SILENCE_THRESHOLD
                    and len(self.audio_buffer) > self.MIN_BUFFER_SIZE
                ):
                    async with self.buffer_lock:
                        audio_to_process = bytes(self.audio_buffer)
                        user = self.current_user

                        # 다음 발화를 위해 먼저 초기화
                        self.audio_buffer = bytearray()
                        self.current_user = None

                    try:
                        text = await transcribe_audio(audio_to_process)
                    except Exception as e:
                        print(f"⚠️ [STT] 변환 실패: {e}", flush=True)
                        text = None

                    if text and user:
                        print(f"🎙️ [STT 인식 결과]: {text}", flush=True)

                        try:
                            await self.text_callback(user, text)
                        except Exception as e:
                            print(f"❌ [음성 시스템] text_callback 실행 실패: {e}", flush=True)

                    break

                # 너무 오래 데이터가 안 들어오면 버퍼 비우고 종료
                if current_time - self.last_speaking_time > 10:
                    async with self.buffer_lock:
                        self.audio_buffer = bytearray()
                        self.current_user = None
                    break

        except Exception as e:
            print(f"❌ [음성 시스템] check_silence 내부 오류: {e}", flush=True)

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
        print(f"❌ Google STT 서비스 에러: {e}", flush=True)
        return None

    except Exception as e:
        print(f"❌ STT 변환 중 예상치 못한 에러: {e}", flush=True)
        return None
