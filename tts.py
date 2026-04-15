import discord
from discord.ext import commands
from discord import app_commands
import requests  # edge_tts 대신 requests를 사용합니다
import os

class TTS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 슈비님이 발급받은 정보 (보안을 위해 환경변수로 옮길 수 있습니다)
        self.api_key = "sk_e5bbe4c60535ec2ca035244927e7e28397ea49e756fdabcf"
        self.voice_id = "0tX0fDpY5yPAOO00erV7"

    @app_commands.command(name="말해", description="슈비님이 만든 목소리로 뜌비가 말을 합니다.")
    async def speak(self, interaction: discord.Interaction, 텍스트: str):
        if not interaction.user.voice:
            await interaction.response.send_message("⚠️ 먼저 음성 채널에 들어가 주세요!", ephemeral=True)
            return

        await interaction.response.defer()
        channel = interaction.user.voice.channel
        filename = f"voice_{interaction.user.id}.mp3"

        try:
            # 1. ElevenLabs API 호출 부분
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
            else:
                raise Exception(f"API 오류 (상태 코드: {response.status_code})")

            # 2. 음성 채널 접속 및 재생
            vc = interaction.guild.voice_client
            if not vc:
                vc = await channel.connect()
            elif vc.channel != channel:
                await vc.move_to(channel)

            if vc.is_playing():
                vc.stop()

            source = discord.FFmpegPCMAudio(filename)
            vc.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
            await interaction.followup.send(f"🎤 **뜌비:** {텍스트}")

        except Exception as e:
            await interaction.followup.send(f"❌ 에러 발생: {e}")
            if os.path.exists(filename):
                os.remove(filename)

async def setup(bot):
    await bot.add_cog(TTS(bot))
