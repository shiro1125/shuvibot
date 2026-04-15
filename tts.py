import discord
from discord.ext import commands
from discord import app_commands
import requests
import os


class TTS(commands.Cog):
    """
    텍스트를 받아 ElevenLabs API를 통해 음성으로 변환하고 재생하는 Cog입니다.
    자세한 로그를 통해 API 호출과 재생 과정을 확인할 수 있습니다.
    """

    def __init__(self, bot):
        self.bot = bot
        # API 키와 voice_id는 보안을 위해 환경변수에서 읽는 것이 좋습니다.
        # 여기서는 예시 값으로 하드코딩되어 있으며 필요시 .env를 통해 관리하세요.
        self.api_key = "sk_e5bbe4c60535ec2ca035244927e7e28397ea49e756fdabcf"
        self.voice_id = "0tX0fDpY5yPAOO00erV7"

    @app_commands.command(name="말해", description="슈비님이 만든 목소리로 뜌비가 말을 합니다.")
    async def speak(self, interaction: discord.Interaction, 텍스트: str):
        """
        텍스트를 입력받아 ElevenLabs API로 음성 파일을 생성한 뒤
        현재 사용자가 있는 음성 채널에서 재생합니다. 과정 중 상세 로그를 출력합니다.
        """
        if not interaction.user.voice:
            await interaction.response.send_message("⚠️ 먼저 음성 채널에 들어가 주세요!", ephemeral=True)
            return

        await interaction.response.defer()
        channel = interaction.user.voice.channel
        filename = f"voice_{interaction.user.id}.mp3"

        try:
            # 1. ElevenLabs API 호출 부분
            print(f"[TTS] ElevenLabs API 호출 시작. 텍스트: '{텍스트}'", flush=True)
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
            headers = {
                "xi-api-key": self.api_key,
                "Content-Type": "application/json"
            }
            data = {
                "text": 텍스트,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.75
                }
            }

            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"[TTS] 음성 파일 저장 완료: {filename}", flush=True)
            else:
                raise Exception(f"API 오류 (상태 코드: {response.status_code})")

            # 2. 음성 채널 접속 및 재생
            vc = interaction.guild.voice_client
            if not vc:
                print("[TTS] 음성 채널에 연결되지 않아 새로 연결합니다.", flush=True)
                vc = await channel.connect()
            elif vc.channel != channel:
                print("[TTS] 다른 채널에 연결되어 있어 이동합니다.", flush=True)
                await vc.move_to(channel)

            if vc.is_playing():
                print("[TTS] 기존 재생을 중지합니다.", flush=True)
                vc.stop()

            # ffmpeg 경로는 환경에 따라 조정이 필요할 수 있습니다. 기본값 사용.
            source = discord.FFmpegPCMAudio(filename)
            vc.play(
                source,
                after=lambda e: os.remove(filename) if os.path.exists(filename) else None
            )
            print("[TTS] 음성 재생을 시작합니다.", flush=True)
            await interaction.followup.send(f"🎤 **뜌비:** {텍스트}")

        except Exception as e:
            await interaction.followup.send(f"❌ 에러 발생: {e}")
            print(f"❌ [TTS] 에러 발생: {e}", flush=True)
            if os.path.exists(filename):
                os.remove(filename)


async def setup(bot):
    await bot.add_cog(TTS(bot))
