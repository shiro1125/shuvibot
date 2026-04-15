# scheduler.py
import discord
from discord.ext import commands, tasks
from datetime import datetime
import pytz
import affinity_manager

korea = pytz.timezone('Asia/Seoul')

class SchedulerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.GUILD_ID_1 = 1228372760212930652
        self.GUILD_ID_2 = 1170313139225640972
        self.WORK_CHANNEL_ID = 1296431232045027369
        self.ANNOUNCEMENT_CHANNEL_ID = 1358394433665634454
        self.RANK_1_ROLE_ID = 1493551151323549767
        
        self.rank_check_loop.start()
        print("👑 [시스템] 랭킹 체크 루프 시작!")
        self.control_voice_channel.start()
        print("🎙️ [시스템] 자동 입장 루프 시작!")
        self.send_notifications.start()
        print("🔔 [시스템] 알림 루프 시작!")

    def cog_unload(self):
        self.rank_check_loop.cancel()
        self.control_voice_channel.cancel()
        self.send_notifications.cancel()

    @tasks.loop(hours=1)
    async def rank_check_loop(self):
        guild = self.bot.get_guild(self.GUILD_ID_1)
        if not guild: return

        top_user_id = affinity_manager.get_top_ranker_id()
        if not top_user_id: return

        role = guild.get_role(self.RANK_1_ROLE_ID)
        if not role: return

        current_winner = role.members[0] if role.members else None
        if current_winner and current_winner.id == top_user_id: return

        if current_winner:
            try:
                await current_winner.remove_roles(role)
            except Exception as e:
                print(f"❌ 기존 1위 역할 제거 실패: {e}")

        new_winner = guild.get_member(top_user_id)
        if new_winner:
            try:
                await new_winner.add_roles(role)
                print(f"👑 새로운 1위 탄생: {new_winner.display_name}")
            except Exception as e:
                print(f"❌ 새 1위 역할 부여 실패: {e}")

    @tasks.loop(minutes=1)
    async def control_voice_channel(self):
        now_korea = datetime.now(korea)

        if now_korea.hour == 16 and now_korea.minute == 0:
            self.bot.reset_model_status()
        
        if self.bot.auto_join_enabled:
            guild = self.bot.get_guild(self.GUILD_ID_1)
            if not guild:
                print("⚠️ [자동입장] 서버를 찾을 수 없습니다.")
                return
            work_channel = guild.get_channel(self.WORK_CHANNEL_ID)
            if not work_channel:
                print("⚠️ [자동입장] 작업 채널 ID가 올바르지 않습니다.")
                return
            
            vc = guild.voice_client
            if vc is None or not vc.is_connected():
                try:
                    print(f"🔄 [자동입장] {work_channel.name} 접속 시도 중...")
                    await work_channel.connect(reconnect=True, timeout=20)
                except Exception as e:
                    print(f"❌ [자동입장] 접속 실패: {e}")
            elif vc.channel and vc.channel.id != self.WORK_CHANNEL_ID:
                try:
                    await vc.move_to(work_channel)
                    print(f"🔄 [자동입장] {work_channel.name}으로 이동 완료.")
                except Exception as e:
                    print(f"❌ [자동입장] 이동 실패: {e}")

    @tasks.loop(minutes=1)
    async def send_notifications(self):
        now_korea = datetime.now(korea)
        if now_korea.weekday() == 5 and now_korea.hour == 17 and now_korea.minute == 50:
            guild = self.bot.get_guild(self.GUILD_ID_2)
            if not guild: return
            announcement_channel = guild.get_channel(self.ANNOUNCEMENT_CHANNEL_ID)
            study_role = discord.utils.get(guild.roles, name="수강생")
            if announcement_channel and study_role:
                try:
                    await announcement_channel.send(f"{study_role.mention} 📢 수업 10분전 입니다!")
                except Exception as e:
                    print(f"❌ 알림 전송 실패: {e}")

async def setup(bot):
    await bot.add_cog(SchedulerCog(bot))
