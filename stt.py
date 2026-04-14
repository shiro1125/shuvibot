import discord
from discord.ext import voice_recv
import speech_recognition as sr
import io
import asyncio

# 음성 인식기 초기화
r = sr.Recognizer()

class BasicSink(voice_recv.AudioSink):
    def __init__(self, bot, text_callback):
        super().__init__()
        self.bot = bot
        self.text_callback = text_callback
        self.audio_buffer = io.BytesIO()
        self._task = None

    def wants_opus(self) -> bool:
        # 생소리(PCM)를 받아서 처리합니다.
        return False

    def write(self, user, data):
        # 들어오는 음성 패킷을 버퍼에 기록
        self.audio_buffer.write(data.pcm)
        
        # 데이터가 일정량 모이면 인식을 시도하도록 확장 가능
        # 현재는 연결 확인을 위해 로그만 남깁니다.

    def cleanup(self):
        self.audio_buffer.close()

async def transcribe_audio(audio_bytes):
    """바이트 데이터를 텍스트로 변환하는 헬퍼 함수"""
    # 48000Hz, 2채널(스테레오) PCM 기준
    audio = sr.AudioData(audio_bytes, 48000, 2)
    try:
        # 루프를 차단하지 않기 위해 별도 스레드에서 실행하는 것이 좋음
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, lambda: r.recognize_google(audio, language='ko-KR'))
        return text
    except:
        return None
