import discord
from discord.ext import commands
from discord import app_commands
import random

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.decks = {}

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

    @app_commands.command(name="블랙잭", description="뜌비랑 공정한 블랙잭 한 판!")
    async def blackjack(self, interaction: discord.Interaction):
        user_name = interaction.user.display_name
        
        # 덱 초기화 (호감도 영향 없음)
        deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] * 4
        random.shuffle(deck)
        
        user_hand = [deck.pop(), deck.pop()]
        bot_hand = [deck.pop(), deck.pop()]
        
        self.decks[interaction.user.id] = {
            "deck": deck, 
            "user": user_hand, 
            "bot": bot_hand, 
            "name": user_name
        }
        
        embed = discord.Embed(title="🃏 공정한 블랙잭", color=0x5865F2)
        embed.set_footer(text="이 게임은 뜌비의 호감도 시스템에 영향을 받지 않는 공정 모드입니다.")
        embed.add_field(name=f"👤 {user_name}님의 카드", value=f"{', '.join(user_hand)}\n(합계: **{self.calculate_score(user_hand)}**)", inline=True)
        embed.add_field(name="🤖 딜러(뜌비) 카드", value=f"{bot_hand[0]}, ❓", inline=True)
        
        view = BlackjackView(self, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

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
            await self.end_game(interaction, f"💥 {data['name']}님 버스트! 이번 판은 뜌비가 이겼네요.")
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
        
        # 딜러 규칙: 17점 미만 무조건 히트 (호감도와 상관없는 고정 확률)
        while bot_score < 17:
            data['bot'].append(data['deck'].pop())
            bot_score = self.cog.calculate_score(data['bot'])
            
        if bot_score > 21:
            result = f"🎊 뜌비 버스트! {data['name']}님이 승리하셨습니다!"
        elif user_score > bot_score:
            result = f"🏆 {data['name']}님 승리! ({user_score} 대 {bot_score})"
        elif user_score < bot_score:
            result = f"😭 뜌비 승리! ({bot_score} 대 {user_score})"
        else:
            result = "🤝 푸시(Push)! 무승부입니다."
            
        await self.end_game(interaction, result)

    async def end_game(self, interaction, result_text):
        data = self.cog.decks[self.user_id]
        embed = discord.Embed(title="🏁 게임 결과", description=f"**{result_text}**", color=0x2ecc71)
        embed.add_field(name=f"👤 {data['name']} 최종", value=f"{', '.join(data['user'])}\n(합계: {self.cog.calculate_score(data['user'])})", inline=True)
        embed.add_field(name="🤖 뜌비 최종", value=f"{', '.join(data['bot'])}\n(합계: {self.cog.calculate_score(data['bot'])})", inline=True)
        await interaction.response.edit_message(embed=embed, view=None)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
