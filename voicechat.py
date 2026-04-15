import logging
import os
import asyncio

import discord
from discord.ext import commands
from discord import app_commands
from discord.ext import voice_recv

# -----------------------------------------------------------------------------
# This Cog provides a minimal and more stable voice‑to‑text functionality.
# It listens in a voice channel, converts speech to text using the existing
# `BasicSink` from stt.py and logs the transcribed text. The focus is on
# reliability: there is no AI response generation or TTS playback, and the
# implementation attempts to work around known issues in discord‑ext‑voice‑recv.
# -----------------------------------------------------------------------------

# Patch: Work around Opus corrupted stream errors in discord‑ext‑voice‑recv
#
# The discord‑ext‑voice‑recv library can throw `OpusError: corrupted stream`
# when handling incoming audio. These exceptions occur in a background thread
# and, if uncaught, stop the voice receive loop entirely. To increase
# robustness, we monkey‑patch the decoder to catch these errors and return
# empty audio so that corrupted packets are silently dropped instead of
# crashing the router.
try:
    import discord.ext.voice_recv.opus as _opus_module  # type: ignore
    import discord.opus as _discord_opus  # type: ignore
    _orig_decode = _opus_module.Decoder.decode

    def _safe_decode(self, data, fec=False):  # type: ignore
        try:
            return _orig_decode(self, data, fec)
        except _discord_opus.OpusError as oe:
            logging.warning(f"[VOICECHAT] Opus decode error: {oe}. Skipping packet")
            return b""

    _opus_module.Decoder.decode = _safe_decode  # type: ignore
    logging.info("[VOICECHAT] Patched Opus decoder to handle corrupted stream errors")
except Exception as e:
    logging.warning(f"[VOICECHAT] Failed to patch Opus decoder: {e}")

# Internal import: BasicSink for collecting audio and performing STT
from stt import BasicSink


class VoiceChatCog(commands.Cog):
    """
    Cog that listens for speech in a voice channel and logs the transcribed text.

    This command is controlled via a slash command `/듣기` with ON and OFF options.
    When turned ON, the bot joins the user's current voice channel using
    `VoiceRecvClient` and starts receiving audio via a `BasicSink`. When speech
    is transcribed, it is logged to the console using the logging module.
    No AI processing or TTS playback occurs in this minimal version.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.listening: bool = False
        self.vc: discord.VoiceClient | None = None
        self.sink: BasicSink | None = None

    @app_commands.command(name="듣기", description="음성 인식 로그를 활성화하거나 비활성화합니다.")
    @app_commands.choices(상태=[
        app_commands.Choice(name="ON", value="on"),
        app_commands.Choice(name="OFF", value="off")
    ])
    async def listen_control(self, interaction: discord.Interaction, 상태: app_commands.Choice[str]) -> None:
        """
        Slash command handler to start or stop listening for speech.

        When `상태` is "on", the bot joins the caller's voice channel (if not
        already connected) using VoiceRecvClient, begins receiving audio via
        BasicSink, and logs transcriptions. When `상태` is "off", the bot stops
        receiving audio and disconnects from the voice channel.
        """
        # Turn on speech listening
        if 상태.value == "on":
            # Already listening; do nothing
            if self.listening:
                await interaction.response.send_message("이미 음성 인식이 켜져 있습니다!", ephemeral=True)
                return
            # Ensure the user is in a voice channel
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.response.send_message("먼저 음성 채널에 들어가 주세요!", ephemeral=True)
                return
            channel = interaction.user.voice.channel
            try:
                # Disconnect existing non‑receiving voice client if necessary
                vc = interaction.guild.voice_client
                if vc and not isinstance(vc, voice_recv.VoiceRecvClient):
                    logging.info("[VOICECHAT] Disconnecting existing VoiceClient before starting listening")
                    try:
                        await vc.disconnect(force=True)
                    except Exception as disconnect_err:
                        logging.warning(f"[VOICECHAT] Error disconnecting existing VoiceClient: {disconnect_err}")
                    vc = None
                # Connect using VoiceRecvClient or reuse existing connection
                if not vc:
                    logging.info(f"[VOICECHAT] Connecting to channel '{channel.name}' as VoiceRecvClient")
                    self.vc = await channel.connect(cls=voice_recv.VoiceRecvClient)
                else:
                    self.vc = vc
                    if self.vc.channel != channel:
                        logging.info(f"[VOICECHAT] Moving VoiceRecvClient to channel '{channel.name}'")
                        await self.vc.move_to(channel)
                # Initialize sink and begin listening
                self.sink = BasicSink(self.bot, self.handle_speech)
                self.vc.listen(self.sink)
                self.listening = True
                logging.info("[VOICECHAT] Voice listening started")
                await interaction.response.send_message("🎧 음성 인식이 시작되었습니다.", ephemeral=True)
            except Exception as exc:
                self.listening = False
                self.vc = None
                self.sink = None
                logging.error(f"[VOICECHAT] Failed to start listening: {exc}")
                await interaction.response.send_message(f"❌ 음성 인식 시작 실패: {exc}", ephemeral=True)
        # Turn off speech listening
        else:
            # Not currently listening
            if not self.listening:
                await interaction.response.send_message("지금 음성 인식이 활성화되어 있지 않습니다.", ephemeral=True)
                return
            self.listening = False
            try:
                # Stop receiving audio
                if self.vc:
                    if hasattr(self.vc, "stop_listening"):
                        self.vc.stop_listening()
                    try:
                        await self.vc.disconnect(force=True)
                    except Exception as disconnect_err:
                        logging.warning(f"[VOICECHAT] Error disconnecting voice client: {disconnect_err}")
                # Clean up sink
                if self.sink:
                    try:
                        self.sink.cleanup()
                    except Exception:
                        pass
                logging.info("[VOICECHAT] Voice listening stopped")
                await interaction.response.send_message("🛑 음성 인식이 중지되었습니다.", ephemeral=True)
            finally:
                self.vc = None
                self.sink = None

    async def handle_speech(self, user: discord.Member, text: str) -> None:
        """
        Callback invoked by BasicSink whenever a phrase has been transcribed.

        Logs the speaker's display name and the recognized text. No further
        processing is done in this minimal implementation.
        """
        # Only handle events when listening is enabled
        if not self.listening:
            return
        try:
            logging.info(f"[STT] {user.display_name}: {text}")
        except Exception as exc:
            logging.error(f"[VOICECHAT] Error logging speech: {exc}")


async def setup(bot: commands.Bot) -> None:
    """
    Coroutine used by discord.py to set up the Cog.

    This function is invoked by `bot.load_extension` in bot.py. It simply adds
    the VoiceChatCog instance to the bot.
    """
    await bot.add_cog(VoiceChatCog(bot))
