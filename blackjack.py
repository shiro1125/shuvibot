import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os
from typing import Optional

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.decks = {}
        self.data_file = "blackjack_stats.json"
        self.stats = self.load_stats()

    def load_stats(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_stats(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=4)

    def update_stats(self, user_id, result):
        uid = str(user_id)
        if uid not in self.stats:
            self.stats[uid] = {"win": 0, "lose": 0, "draw": 0}
        
        if result == "win": self.stats[uid]["win"] += 1
        elif result == "lose": self.stats[uid]["lose"] += 1
        else: self.stats[uid]["draw"] += 1
        self.save_stats()

    def get_card_value(self, card):
        if card in ['J', 'Q', 'K']: return 10
        if card == 'A': return 11
        return int(card)

    def calculate_score(self, hand):
        score = sum(self.get_card_value(card) for card in hand)
        aces = hand.count('A')
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    # 그룹 명령어로 설정하여 /블랙잭 시작, /블랙잭 전적 형태로 분리
    blackjack_group = app_commands.Group(name="블랙잭", description="블랙잭 게임 관련 명령어")

    @blackjack_group.command(name="시작", description="뜌비랑 공정한 블랙잭 한 판!")
    async def start_game(self, interaction: discord.Interaction):
        user_name = interaction.user.display_name
        deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] * 4
        random.shuffle(deck)
        
        user_hand = [deck.pop(), deck.pop()]
        bot_hand = [deck.pop(), deck.pop()]
        
        self.decks[interaction.user.id] = {"deck": deck, "user": user_hand, "bot": bot_hand, "name": user_name}
        
        embed = discord.Embed(title="🃏 공정한 블랙잭", color=0x5865F2)
        embed.set_footer(text="⚠️ 이 게임은 뜌비의 친밀도 시스템에 영향을 받지 않습니다.")
        embed.add_field(name=f"👤 {user_name}님의 카드", value=f"{', '.join(user_hand)}\n(합계: **{self.calculate_score(user_hand)}**)", inline=True)
        embed.add_field(name="🤖 딜러(뜌비) 카드", value=f"{bot_hand[0]}, ❓", inline=True)
        
        view = BlackjackView(self, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @blackjack_group.command(name="전적", description="본인 또는 다른 유저의 전적을 확인합니다.")
    @app_commands.describe(유저="전적을 확인할 유저를 선택하세요 (비워두면 본인 전적)")
    async def show_stats(self, interaction: discord.Interaction, 유저: Optional[discord.Member] = None):
        target = 유저 or interaction.user
        uid = str(target.id)
        
        if uid not in self.stats:
            await interaction.response.send_message(f"아직 {target.display_name}님의 플레이 기록이 없어요!", ephemeral=True)
            return

        s = self.stats[uid]
        total = s["win"] + s["lose"] + s["draw"]
        win_rate = (s["win"] / total * 100) if total > 0 else 0
        
        embed = discord.Embed(title=f"📊 {target.display_name}님의 블랙잭 전적", color=0x00ffcc)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="총 경기 수", value=f"{total}전", inline=False)
        embed.add_field(name="기록", value=f"✅ {s['win']}승 | ❌ {s['lose']}패 | 🤝 {s['draw']}무", inline=True)
        embed.add_field(name="승률", value=f"📈 {win_rate:.1f}%", inline=True)
        
        await interaction.response.send_message(embed=embed)

# --- View 부분은 이전과 동일 (히트/스테이 로직) ---
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
            self.cog.update_stats(self.user_id, "lose")
            await self.end_game(interaction, f"💥 {data['name']}님 버스트! 패배하셨습니다.")
        else:
            embed = discord.Embed(title="🃏 블랙잭 진행 중", color=0x5865F2)
            embed.add_field(name=f"👤 {data['name']}님의 카드", value=f"{', '.join(data['user'])}\n(합계: **{score}**)", inline=True)
            embed.add_field(name="🤖 딜러(뜌비) 카드", value=f"{data['bot'][0]}, ❓", inline=True)
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="스테이", style=discord.ButtonStyle.secondary)
    async def stay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        data = self.cog.decks[self.user_id]
        user_score = self.cog.calculate_score(data['user'])
        bot_score = self.cog.calculate_score(data['bot'])
        while bot_score < 17:
            data['bot'].append(data['deck'].pop())
            bot_score = self.cog.calculate_score(data['bot'])
        if bot_score > 21 or user_score > bot_score:
            result_msg = "🎊 승리하셨습니다!"
            self.cog.update_stats(self.user_id, "win")
        elif user_score < bot_score:
            result_msg = "😭 패배하셨습니다."
            self.cog.update_stats(self.user_id, "lose")
        else:
            result_msg = "🤝 무승부입니다."
            self.cog.update_stats(self.user_id, "draw")
        await self.end_game(interaction, result_msg)

    async def end_game(self, interaction, result_text):
        data = self.cog.decks[self.user_id]
        embed = discord.Embed(title="🏁 게임 결과", description=f"**{result_text}**", color=0x2ecc71)
        embed.add_field(name=f"👤 {data['name']} 최종", value=f"{self.cog.calculate_score(data['user'])}점", inline=True)
        embed.add_field(name="🤖 뜌비 최종", value=f"{self.cog.calculate_score(data['bot'])}점", inline=True)
        await interaction.response.edit_message(embed=embed, view=None)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
