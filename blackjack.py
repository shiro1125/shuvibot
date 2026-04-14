import discord
from discord.ext import commands
from discord import app_commands
import random
import os
from typing import Optional
from supabase import create_client, Client

# Supabase 설정 (환경 변수 권장)
URL: str = os.getenv("SUPABASE_URL")
KEY: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.decks = {}

    def get_user_stats(self, user_id):
        # DB에서 유저 데이터 가져오기 (없으면 생성)
        uid = str(user_id)
        res = supabase.table("blackjack_stats").select("*").eq("user_id", uid).execute()
        
        if not res.data:
            new_data = {"user_id": uid, "win": 0, "lose": 0, "draw": 0, "total": 0, "affinity": 100}
            supabase.table("blackjack_stats").insert(new_data).execute()
            return new_data
        return res.data[0]

    def update_db(self, user_id, result, bet_amount=0):
        uid = str(user_id)
        current = self.get_user_stats(user_id)
        
        updates = {
            "total": current["total"] + 1,
            "affinity": current["affinity"]
        }
        
        if result == "win":
            updates["win"] = current["win"] + 1
            updates["affinity"] += bet_amount
        elif result == "lose":
            updates["lose"] = current["lose"] + 1
            updates["affinity"] -= bet_amount
        else:
            updates["draw"] = current["draw"] + 1
            # 무승부는 친밀도 변동 없음 (1배)

        supabase.table("blackjack_stats").update(updates).eq("user_id", uid).execute()

    def calculate_score(self, hand):
        score = sum((10 if c in ['J', 'Q', 'K'] else (11 if c == 'A' else int(c))) for c in hand)
        aces = hand.count('A')
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    blackjack_group = app_commands.Group(name="블랙잭", description="Supabase 연동 블랙잭 시스템")

    @blackjack_group.command(name="베팅", description="친밀도를 걸고 뜌비와 승부합니다!")
    async def betting_game(self, interaction: discord.Interaction, 수치: int):
        user_data = self.get_user_stats(interaction.user.id)
        
        if 수치 <= 0:
            return await interaction.response.send_message("0보다 큰 값을 베팅해줘!", ephemeral=True)
        if 수치 > user_data["affinity"]:
            return await interaction.response.send_message(f"보유 친밀도({user_data['affinity']})가 부족해!", ephemeral=True)

        deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] * 4
        random.shuffle(deck)
        user_hand, bot_hand = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]

        self.decks[interaction.user.id] = {
            "deck": deck, "user": user_hand, "bot": bot_hand, 
            "bet": 수치, "name": interaction.user.display_name
        }

        embed = discord.Embed(title="🎲 블랙잭 베팅 모드", description=f"**베팅 💖: {수치}**", color=0xFF69B4)
        embed.add_field(name=f"👤 {interaction.user.display_name}", value=f"합계: **{self.calculate_score(user_hand)}**")
        embed.add_field(name="🤖 뜌비", value=f"카드: {bot_hand[0]}, ❓")
        
        await interaction.response.send_message(embed=embed, view=BlackjackView(self, interaction.user.id))

    @blackjack_group.command(name="랭킹", description="승률 TOP 10 (10판 이상 플레이어)")
    async def show_ranking(self, interaction: discord.Interaction):
        # 10판 이상인 유저들 가져오기
        res = supabase.table("blackjack_stats").select("*").gte("total", 10).execute()
        players = res.data

        if not players:
            return await interaction.response.send_message("아직 랭킹에 등록된 유저가 없어!", ephemeral=True)

        # 승률 계산 후 정렬
        for p in players:
            p['rate'] = (p['win'] / p['total']) * 100
        
        players.sort(key=lambda x: x['rate'], reverse=True)
        top_10 = players[:10]

        embed = discord.Embed(title="🏆 블랙잭 승률 랭킹 (TOP 10)", color=0xF1C40F)
        desc = ""
        for i, p in enumerate(top_10, 1):
            member = interaction.guild.get_member(int(p['user_id']))
            name = member.display_name if member else "익명의 유저"
            desc += f"**{i}위. {name}** | `{p['rate']:.1f}%` ({p['win']}승/{p['total']}전)\n"
        
        embed.description = desc
        await interaction.response.send_message(embed=embed)

# --- View (버튼 로직) ---
class BlackjackView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="히트", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        data = self.cog.decks[self.user_id]
        data['user'].append(data['deck'].pop())
        score = self.cog.calculate_score(data['user'])
        
        if score > 21:
            self.cog.update_db(self.user_id, "lose", data["bet"])
            await self.end_game(interaction, "💥 버스트! 뜌비가 베팅금을 가져갈게.")
        else:
            # 중간 진행 임베드 갱신 로직 (생략)
            await interaction.response.edit_message(content="카드를 더 뽑았어!")

    @discord.ui.button(label="스테이", style=discord.ButtonStyle.secondary)
    async def stay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        data = self.cog.decks[self.user_id]
        u_score, b_score = self.cog.calculate_score(data['user']), self.cog.calculate_score(data['bot'])
        
        while b_score < 17:
            data['bot'].append(data['deck'].pop())
            b_score = self.cog.calculate_score(data['bot'])
            
        result = "win" if b_score > 21 or u_score > b_score else ("draw" if u_score == b_score else "lose")
        self.cog.update_db(self.user_id, result, data["bet"])
        
        msg = "🎊 승리! 친밀도 2배!" if result == "win" else ("🤝 무승부!" if result == "draw" else "😭 패배..")
        await self.end_game(interaction, msg)

    async def end_game(self, interaction, text):
        # 결과 화면 출력 로직 (생략)
        await interaction.response.edit_message(content=text, view=None)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
