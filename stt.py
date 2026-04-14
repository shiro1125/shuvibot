import discord
from discord.ext import voice_recv
import speech_recognition as sr
import io
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
        
        # 설정값
        self.SILENCE_THRESHOLD = 1.5  # 1.5초간 조용하면 말이 끝난 것으로 간주
        self.MIN_BUFFER_SIZE = 48000 * 2 * 2 * 0.5 # 최소 0.5초 이상의 데이터가 있을 때만 처리

    def wants_opus(self) -> bool:
        # PCM(생소리) 데이터를 받습니다.
        return False

    def write(self, user, data):
        # 유저별로 구분할 수도 있지만, 여기서는 들어오는 모든 음성을 합칩니다.
        # data.pcm은 bytes 형태입니다.
        if data.pcm:
            self.audio_buffer.extend(data.pcm)
            self.last_speaking_time = time.time()
            
            # 별도의 루프가 없다면 여기서 침묵 체크를 트리거합니다.
            if not self.is_processing:
                asyncio.run_coroutine_threadsafe(self.check_silence(user), self.bot.loop)

    async def check_silence(self, user):
        """침묵을 감지하고 텍스트 변환을 시작합니다."""
        self.is_processing = True
        
        while True:
            await asyncio.sleep(0.5)
            current_time = time.time()
            
            # 마지막 발화 후 일정 시간이 지났고, 버퍼에 데이터가 충분히 쌓였을 때
            if (current_time - self.last_speaking_time > self.SILENCE_THRESHOLD) and len(self.audio_buffer) > self.MIN_BUFFER_SIZE:
                
                # 버퍼 복사 후 초기화 (다음 발화를 위해)
                audio_to_process = bytes(self.audio_buffer)
                self.audio_buffer = bytearray()
                
                # STT 실행
                text = await transcribe_audio(audio_to_process)
                
                if text:
                    print(f"🎙️ [STT 인식 결과]: {text}")
                    # 메인 bot.py의 your_gemini_function 호출
                    await self.text_callback(user, text)
                
                break # 한 문장 처리 후 루프 종료 (다음 발화 시 다시 생성됨)
            
            # 데이터가 너무 오랫동안 안 들어오면 루프 종료
            if current_time - self.last_speaking_time > 10:
                self.audio_buffer = bytearray()
                break

        self.is_processing = False

    def cleanup(self):
        self.audio_buffer.clear()

async def transcribe_audio(audio_bytes):
    """바이트 데이터를 텍스트로 변환하는 헬퍼 함수"""
    # 디스코드 음성은 기본 48000Hz, 16-bit, 2채널(Stereo)입니다.
    audio_data = sr.AudioData(audio_bytes, 48000, 2)
    
    try:
        loop = asyncio.get_event_loop()
        # Google STT 사용 (무료 버전은 할당량 제한이 있을 수 있음)
        text = await loop.run_in_executor(None, lambda: r.recognize_google(audio_data, language='ko-KR'))
        return text
    except sr.UnknownValueError:
        # 소리는 들리지만 무슨 말인지 모를 때
        return None
    except sr.RequestError as e:
        print(f"❌ Google STT 서비스 에러: {e}")
        return None
    except Exception as e:
        print(f"❌ STT 변환 중 예상치 못한 에러: {e}")
        return None
