import discord
from discord.ext import voice_recv
import speech_recognition as sr # 가벼운 라이브러리로 변경
import io
import os
import asyncio

# 음성 인식기 초기화
r = sr.Recognizer()

class SpeechToText:
    def __init__(self, bot):
        self.bot = bot

    async def transcribe_audio(self, audio_data):
        """
        수집된 음성 데이터를 텍스트로 변환합니다.
        """
        # 1. 받은 음성 데이터를 AI가 읽을 수 있는 형태로 변환
        audio = sr.AudioData(audio_data, 48000, 2)
        
        try:
            # 2. 구글 음성 인식 엔진 사용 (용량 차지 없음!)
            # language='ko-KR' 설정으로 한국어를 인식합니다.
            text = r.recognize_google(audio, language='ko-KR')
            return text
        except sr.UnknownValueError:
            # 목소리가 너무 작거나 이해할 수 없을 때
            return None
        except sr.RequestError as e:
            print(f"❌ [STT 에러] 구글 서비스 연결 실패: {e}")
            return None

class BasicSink(voice_recv.AudioSink):
    def __init__(self, bot, text_callback):
        self.bot = bot
        self.text_callback = text_callback
        self.stt = SpeechToText(bot)

    def want_opus(self):
        return False # 가공하기 쉬운 PCM 데이터로 받기

    def write(self, user, data):
        # 실시간으로 데이터가 들어오는 곳입니다.
        # 여기서는 간단한 구조만 보여드리며, 
        # 실제로는 일정 시간(무음)을 체크해 문장을 완성하는 로직이 필요합니다.
        pass

    def cleanup(self):
        pass
