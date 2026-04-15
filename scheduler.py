import discord
from discord.ext import tasks
from datetime import datetime
import pytz

korea = pytz.timezone('Asia/Seoul')

# ID 설정 (관리 편의를 위해 여기에 모음)
GUILD_ID_1 = 1228372760212930652
GUILD_ID_2 = 1170313139225640972
STUDY_CHANNEL_ID = 1358176930725236968
WORK_CHANNEL_ID = 1296431232045027369
ANNOUNCEMENT_CHANNEL_ID = 1358394433665634454

def setup_scheduler(bot):
    @tasks.loop(minutes=1)
    async def study_and_voice_loop():
        now = datetime.now(korea)
        guild = bot.get_guild(GUILD_ID_1)
        if not guild: return

        # 스터디 채널 관리 (18:00 ~ 23:00)
        study_ch = guild.get_channel(STUDY_CHANNEL_ID)
        if study_ch:
            study_role = discord.utils.get(guild.roles, name="스터디")
            is_study_time = 18 <= now.hour <= 23
            await study_ch.set_permissions(guild.default_role, connect=False)
            await study_ch.set_permissions(study_role, connect=is_study_time)
            new_name = "🟢 스터디" if is_study_time else "🔴 스터디"
            if study_ch.name != new_name: await study_ch.edit(name=new_name)

        # 자동 입장 (수신 기능 없이 입장만)
        if bot.auto_join_enabled:
            work_ch = guild.get_channel(WORK_CHANNEL_ID)
            if work_ch and (not guild.voice_client or not guild.voice_client.is_connected()):
                try: await work_ch.connect(reconnect=True, timeout=20)
                except: pass

    @tasks.loop(minutes=1)
    async def class_notification_loop():
        now = datetime.now(korea)
        # 토요일 17:50 체크
        if now.weekday() == 5 and now.hour == 17 and now.minute == 50:
            guild = bot.get_guild(GUILD_ID_2)
            if not guild: return
            
            ann_ch = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            role = discord.utils.get(guild.roles, name="수강생")
            week_num = (now.day - 1) // 7 + 1
            
            if ann_ch and role:
                msg = "이번주는 휴강입니다." if week_num == 5 else f"{role.mention} 📢 수업 10분전 입니다!"
                await ann_ch.send(msg)

    # 루프 시작 함수들 반환
    return study_and_voice_loop, class_notification_loop
