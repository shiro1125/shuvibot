import discord
from discord.ext import voice_recv
import speech_recognition as sr
import io

# 음성 인식기 초기화
r = sr.Recognizer()

class SpeechToText:
    def __init__(self, bot):
        self.bot = bot

    async def transcribe_audio(self, audio_data):
        # 48000Hz, 2채널(스테레오) PCM 데이터를 AudioData 객체로 변환
        audio = sr.AudioData(audio_data, 48000, 2)
        try:
            # 구글 엔진 사용 (한국어)
            text = r.recognize_google(audio, language='ko-KR')
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"❌ [STT 에러] 구글 서비스 연결 실패: {e}")
            return None

class BasicSink(voice_recv.AudioSink):
    def __init__(self, bot, text_callback):
        super().__init__() # 부모 클래스 초기화 추가
        self.bot = bot
        self.text_callback = text_callback
        self.stt = SpeechToText(bot)

    # ❗ 여기 함수 이름을 want_opus에서 wants_opus로 수정했습니다!
    def wants_opus(self) -> bool:
        return False

    def write(self, user, data):
        # 실시간 데이터 처리 로직 (필요시 추가)
        pass

    def cleanup(self):
        pass
