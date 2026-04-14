import requests
import os

# 슈비님이 주신 정보
ELEVENLABS_API_KEY = "sk_e5bbe4c60535ec2ca035244927e7e28397ea49e756fdabcf"
VOICE_ID = "0tX0fDpY5yPAOO00erV7"

def generate_tts(text, output_path):
    """
    텍스트를 입력받아 ElevenLabs 목소리로 MP3를 생성합니다.
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2", # 한국어 최적화 모델
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75
        }
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return True
        else:
            print(f"❌ ElevenLabs 에러: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ TTS 생성 중 사고 발생: {e}")
        return False
