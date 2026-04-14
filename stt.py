import discord
from discord.ext import voice_recv
import whisper
import os
import asyncio

# 1. AI 모델 준비 (Koyeb 사양에 맞춰 가장 가벼운 'tiny' 모델 사용)
# 처음 실행될 때만 모델을 다운로드합니다.
model = whisper.load_model("tiny")

class SpeechToText:
    def __init__(self, bot):
        self.bot = bot

    async def process_voice(self, user, data):
        """
        이 부분은 실제 음성 데이터를 처리하는 로직입니다.
        데이터를 임시 파일로 저장한 뒤 Whisper로 읽습니다.
        """
        # 임시 파일 경로
        filename = f"temp_voice_{user.id}.wav"
        
        try:
            # 2. Whisper로 음성 -> 텍스트 변환
            # fp16=False는 CPU만 있는 서버 환경에서 에러를 방지합니다.
            result = model.transcribe(filename, fp16=False, language='ko')
            text = result['text'].strip()
            
            if text:
                print(f"🎙️ [인식 성공] {user.display_name}: {text}")
                return text
        except Exception as e:
            print(f"❌ [STT 에러] {e}")
        finally:
            # 작업이 끝나면 임시 파일 삭제
            if os.path.exists(filename):
                os.remove(filename)
        return None

# 3. 봇에 추가할 '귀' 클래스 (Sink)
class BasicSink(voice_recv.AudioSink):
    def __init__(self, callback):
        self.callback = callback

    def want_opus(self):
        return False # PCM(가공하기 쉬운 데이터) 형태로 받음

    def write(self, user, data):
        # 여기서 사용자의 목소리가 들어오지만, 
        # 실시간 처리는 복잡하므로 특정 조건(말 끝남 등)을 체크하는 로직이 추가로 필요합니다.
        pass

    def cleanup(self):
        pass
