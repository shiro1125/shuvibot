import discord
from discord.ext import commands
from discord import app_commands
from gtts import gTTS
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
            # gTTS 파일 생성
            tts = gTTS(text=텍스트, lang='ko')
            tts.save(filename)

            # 음성 채널 연결 로직
            vc = interaction.guild.voice_client
            if not vc:
                vc = await channel.connect()
            elif vc.channel != channel:
                await vc.move_to(channel)

            if vc.is_playing():
                vc.stop()

           # 재생 및 파일 삭제 (이 부분을 수정합니다)
            # executable="/usr/bin/ffmpeg" 를 추가해서 경로를 직접 알려주는 거예요!
            source = discord.FFmpegPCMAudio(filename, executable="/usr/bin/ffmpeg")
            
            vc.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
            await interaction.followup.send(f"📢 '{텍스트}'라고 말했어요!")

        except Exception as e:
            await interaction.followup.send(f"❌ 에러 발생: {e}")
            if os.path.exists(filename):
                os.remove(filename)

async def setup(bot):
    await bot.add_cog(TTS(bot))
