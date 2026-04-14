import discord
from discord.ext import commands
from discord import app_commands
import random
import os
from typing import Optional
from supabase import create_client, Client

# Supabase 설정 (환경 변수에서 가져오기)
URL: str = os.getenv("SUPABASE_URL")
KEY: str = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.decks = {}

    def get_actual_affinity(self, user_id):
        """user_stats 테이블에서 실제 유저의 친밀도를 가져옵니다."""
        uid = str(user_id)
        try:
            res = supabase.table("user_stats").select("affinity").eq("user_id", uid).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]["affinity"]
            return 0
        except Exception as e:
            print(f"친밀도 가져오기 에러: {e}")
            return 0

    def get_blackjack_data(self, user_id, user_name):
        """blackjack_stats 테이블에서 전적 데이터를 가져오거나 생성합니다."""
        uid = str(user_id)
        try:
            res = supabase.table("blackjack_stats").select("*").eq("user_id", uid).execute()
            if not res.data:
                new_record = {
                    "user_id": uid, 
                    "user_name": user_name,
                    "win": 0, "lose": 0, "draw": 0, "total": 0
                }
                supabase.table("blackjack_stats").insert(new_record).execute()
                return new_record
            return res.data[0]
        except Exception as e:
            print(f"전적 데이터 조회 에러: {e}")
            return None

    def update_stats(self, user_id, user_name, result, bet_amount):
        """결과를 blackjack_stats(전적)와 user_stats(친밀도) 양쪽에 업데이트합니다."""
        uid = str(user_id)
        
        # 1. 블랙잭 전적 업데이트
        current_bj = self.get_blackjack_data(user_id, user_name)
        if current_bj:
            bj_updates = {
                "total": current_bj["total"] + 1,
                "user_name": user_name
            }
            if result == "win": bj_updates["win"] = current_bj["win"] + 1
            elif result == "lose": bj_updates["lose"] = current_bj["lose"] + 1
            else: bj_updates["draw"] = current_bj["draw"] + 1
            
            supabase.table("blackjack_stats").update(bj_updates).eq("user_id", uid).execute()

        # 2. user_stats 테이블의 친밀도 업데이트
        current_affinity = self.get_actual_affinity(user_id)
        new_affinity = current_affinity
        if result == "win": new_affinity += bet_amount
        elif result == "lose": new_affinity -= bet_amount
        
        supabase.table("user_stats").update({"affinity": new_affinity}).eq("user_id", uid).execute()

    def calculate_score(self, hand):
        score = sum((10 if c in ['J', 'Q', 'K'] else (11 if c == 'A' else int(c))) for c in hand)
        aces = hand.count('A')
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    blackjack_group = app_commands.Group(name="블랙잭", description="실제 친밀도 연동 블랙잭")

    @blackjack_group.command(name="베팅", description="친밀도를 걸고 뜌비와 승부합니다!")
    @app_commands.describe(수치="베팅할 친밀도 양을 입력하세요.")
    async def betting_game(self, interaction: discord.Interaction, 수치: int):
        actual_affinity = self.get_actual_affinity(interaction.user.id)
        user_name = interaction.user.display_name

        if 수치 <= 0:
            return await interaction.response.send_message("0보다 큰 값을 걸어줘 뜌비!", ephemeral=True)
        if 수치 > actual_affinity:
            return await interaction.response.send_message(f"보유하신 친밀도({actual_affinity})가 부족합니다!", ephemeral=True)

        deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] * 4
        random.shuffle(deck)
        user_hand, bot_hand = [deck.pop(), deck.pop()], [deck.pop(), deck.pop()]

        self.decks[interaction.user.id] = {
            "deck": deck, "user": user_hand, "bot": bot_hand, "bet": 수치, "name": user_name
        }

        embed = discord.Embed(title="🎲 블랙잭 베팅 모드", description=f"**베팅 💖: {수치}**\n(현재 보유 친밀도: {actual_affinity})", color=0xFF69B4)
        embed.add_field(name=f"👤 {user_name}", value=f"합계: **{self.calculate_score(user_hand)}**", inline=True)
        embed.add_field(name="🤖 뜌비", value=f"카드: {bot_hand[0]}, ❓", inline=True)
        
        view = BlackjackView(self, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @blackjack_group.command(name="랭킹", description="승률 TOP 10을 확인합니다 (10판 이상 플레이어)")
    async def show_ranking(self, interaction: discord.Interaction):
        res = supabase.table("blackjack_stats").select("*").gte("total", 10).execute()
        players = res.data
        if not players:
            return await interaction.response.send_message("아직 랭킹에 등록된 유저가 없어!", ephemeral=True)

        for p in players:
            p['rate'] = (p['win'] / p['total']) * 100
        
        players.sort(key=lambda x: x['rate'], reverse=True)
        
        embed = discord.Embed(title="🏆 블랙잭 승률 랭킹 (TOP 10)", color=0xF1C40F)
        desc = ""
        for i, p in enumerate(players[:10], 1):
            name = p.get('user_name') or f"익명({p['user_id'][:5]})"
            desc += f"**{i}위. {name}** | `{p['rate']:.1f}%` ({p['win']}승/{p['total']}전)\n"
        
        embed.description = desc
        await interaction.response.send_message(embed=embed)

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
            self.cog.update_stats(self.user_id, data['name'], "lose", data["bet"])
            await self.end_game(interaction, "💥 버스트! 뜌비가 베팅금을 가져갈게.")
        else:
            embed = discord.Embed(title="🃏 블랙잭 진행 중", description=f"**베팅 💖: {data['bet']}**", color=0x5865F2)
            embed.add_field(name=f"👤 {data['name']}", value=f"합계: **{score}**", inline=True)
            embed.add_field(name="🤖 뜌비", value=f"카드: {data['bot'][0]}, ❓", inline=True)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="스테이", style=discord.ButtonStyle.secondary)
    async def stay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        data = self.cog.decks[self.user_id]
        u_score = self.cog.calculate_score(data['user'])
        
        while self.cog.calculate_score(data['bot']) < 17:
            data['bot'].append(data['deck'].pop())
            
        b_score = self.cog.calculate_score(data['bot'])
        if b_score > 21 or u_score > b_score: result = "win"
        elif u_score < b_score: result = "lose"
        else: result = "draw"
        
        self.cog.update_stats(self.user_id, data['name'], result, data["bet"])
        
        msg = "🎊 승리! 친밀도 2배!" if result == "win" else ("🤝 무승부! 원금을 돌려줄게." if result == "draw" else "😭 패배.. 친밀도를 잃었어.")
        await self.end_game(interaction, msg)

    async def end_game(self, interaction, result_text):
        data = self.cog.decks[self.user_id]
        u_score = self.cog.calculate_score(data['user'])
        b_score = self.cog.calculate_score(data['bot'])
        
        color = 0x2ecc71 if "승리" in result_text else (0xe74c3c if "패배" in result_text or "버스트" in result_text else 0x95a5a6)
        
        embed = discord.Embed(title="🏁 게임 결과", description=f"**{result_text}**", color=color)
        embed.add_field(name=f"👤 {data['name']} (최종)", value=f"카드: {', '.join(data['user'])}\n합계: **{u_score}**", inline=True)
        embed.add_field(name="🤖 뜌비 (최종)", value=f"카드: {', '.join(data['bot'])}\n합계: **{b_score}**", inline=True)
        embed.set_footer(text="결과가 Supabase DB에 실시간 반영되었습니다.")
        
        await interaction.response.edit_message(embed=embed, view=None)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
