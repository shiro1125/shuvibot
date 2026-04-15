import requests
import os

# ElevenLabs API 정보 (필요시 .env로 이동)
ELEVENLABS_API_KEY = "sk_e5bbe4c60535ec2ca035244927e7e28397ea49e756fdabcf"
VOICE_ID = "0tX0fDpY5yPAOO00erV7"

def generate_tts(text, output_path):
    """
    텍스트를 입력받아 ElevenLabs 목소리로 MP3를 생성합니다.
    생성 과정과 결과를 로그로 출력합니다.
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",  # 한국어 최적화 모델
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75
        }
    }

    try:
        print(f"[TTS_MODULE] 음성 생성 요청: '{text}'", flush=True)
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            print(f"[TTS_MODULE] 음성 파일 저장 완료: {output_path}", flush=True)
            return True
        else:
            print(f"❌ [TTS_MODULE] ElevenLabs 에러: {response.status_code}", flush=True)
            return False
    except Exception as e:
        print(f"❌ [TTS_MODULE] TTS 생성 중 사고 발생: {e}", flush=True)
        return False
