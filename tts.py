import discord
from discord.ext import commands
from discord import app_commands
import edge_tts  # 1. 이거 추가
import os

class TTS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="말해", description="뜌비가 음성 채널에서 말을 합니다.")
    async def speak(self, interaction: discord.Interaction, 텍스트: str):
        if not interaction.user.voice:
            await interaction.response.send_message("⚠️ 먼저 음성 채널에 들어가 주세요!", ephemeral=True)
            return

        await interaction.response.defer()
        channel = interaction.user.voice.channel
        filename = f"voice_{interaction.user.id}.mp3"

        try:
            # 2. 이 부분이 gTTS 대신 edge-tts로 바뀌는 핵심이에요!
            # ko-KR-SunHiNeural은 아주 맑은 여성 목소리입니다.
            communicate = edge_tts.Communicate(텍스트, "ko-KR-SunHiNeural")
            await communicate.save(filename)

            vc = interaction.guild.voice_client
            if not vc:
                vc = await channel.connect()
            elif vc.channel != channel:
                await vc.move_to(channel)

            if vc.is_playing():
                vc.stop()

            # 3. 이전에 성공했던 ffmpeg 설정은 그대로 유지!
            source = discord.FFmpegPCMAudio(filename, executable="ffmpeg")
            
            vc.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
            await interaction.followup.send(f"📢 '{텍스트}'라고 말했어요!")

        except Exception as e:
            await interaction.followup.send(f"❌ 에러 발생: {e}")
            if os.path.exists(filename):
                os.remove(filename)

async def setup(bot):
    await bot.add_cog(TTS(bot))
