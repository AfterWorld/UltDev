from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import random
import asyncio
import aiohttp
import logging
from collections import defaultdict
from datetime import datetime, timedelta

log = logging.getLogger("red.onepiecebot")

class OnePieceBot(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "trivia_channel": None,
            "conversation_channels": [],
            "trivia_frequency": 3600,  # Default: every hour
            "chatgpt_enabled": False,
            "chatgpt_daily_limit": 100,  # Default daily limit per user
        }
        default_member = {
            "belis": 0,
            "last_chatgpt_use": None,
            "chatgpt_uses_today": 0,
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.trivia_task = None
        self.session = aiohttp.ClientSession()
        self.chatgpt_cooldown = commands.CooldownMapping.from_cooldown(1, 30, commands.BucketType.user)
        self.user_trivia_scores = defaultdict(int)

    def cog_unload(self):
        if self.trivia_task:
            self.trivia_task.cancel()
        asyncio.create_task(self.session.close())

    async def initialize(self):
        self.trivia_task = self.bot.loop.create_task(self.trivia_loop())

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def opbot(self, ctx):
        """Configure One Piece Bot settings"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @opbot.command(name="setchannel")
    async def set_channel(self, ctx, channel_type: str, channel: discord.TextChannel):
        """Set channel for trivia or conversations"""
        if channel_type not in ["trivia", "conversation"]:
            return await ctx.send("Invalid channel type. Use 'trivia' or 'conversation'.")
        
        if channel_type == "trivia":
            await self.config.guild(ctx.guild).trivia_channel.set(channel.id)
            await ctx.send(f"Trivia channel set to {channel.mention}")
        else:
            async with self.config.guild(ctx.guild).conversation_channels() as channels:
                if channel.id not in channels:
                    channels.append(channel.id)
            await ctx.send(f"Added {channel.mention} to conversation channels")

    @opbot.command(name="setfrequency")
    async def set_frequency(self, ctx, seconds: int):
        """Set trivia frequency in seconds"""
        await self.config.guild(ctx.guild).trivia_frequency.set(seconds)
        await ctx.send(f"Trivia frequency set to every {seconds} seconds")

    @opbot.command(name="togglechatgpt")
    async def toggle_chatgpt(self, ctx):
        """Toggle ChatGPT integration"""
        current = await self.config.guild(ctx.guild).chatgpt_enabled()
        await self.config.guild(ctx.guild).chatgpt_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"ChatGPT integration has been {state}.")

    @opbot.command(name="setdailylimit")
    async def set_daily_limit(self, ctx, limit: int):
        """Set daily ChatGPT usage limit per user"""
        await self.config.guild(ctx.guild).chatgpt_daily_limit.set(limit)
        await ctx.send(f"Daily ChatGPT usage limit set to {limit} per user.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        channel_ids = await self.config.guild(message.guild).conversation_channels()
        if message.channel.id in channel_ids:
            chatgpt_enabled = await self.config.guild(message.guild).chatgpt_enabled()
            if chatgpt_enabled:
                bucket = self.chatgpt_cooldown.get_bucket(message)
                retry_after = bucket.update_rate_limit()
                if retry_after:
                    return await message.channel.send(f"Please wait {retry_after:.0f} seconds before using ChatGPT again.")
                
                daily_limit = await self.config.guild(message.guild).chatgpt_daily_limit()
                user_data = await self.config.member(message.author).all()
                
                if user_data["last_chatgpt_use"] is None or (datetime.now() - datetime.fromisoformat(user_data["last_chatgpt_use"])).days > 0:
                    await self.config.member(message.author).last_chatgpt_use.set(datetime.now().isoformat())
                    await self.config.member(message.author).chatgpt_uses_today.set(1)
                elif user_data["chatgpt_uses_today"] >= daily_limit:
                    return await message.channel.send("You've reached your daily ChatGPT usage limit. Please try again tomorrow.")
                else:
                    await self.config.member(message.author).chatgpt_uses_today.set(user_data["chatgpt_uses_today"] + 1)
                
                response = await self.generate_chatgpt_response(message.content)
            else:
                response = await self.generate_response(message.content)
            
            if response:
                await message.channel.send(response)

    async def generate_response(self, message_content: str):
        # Simple response generation (replace with more sophisticated logic if needed)
        responses = [
            "Yohohoho! That's interesting!",
            "Gomu Gomu no... response!",
            "Have you seen the One Piece yet?",
            "Nami-swan! Robin-chwan!",
            "SUUUUUPER!",
        ]
        return random.choice(responses)

    async def generate_chatgpt_response(self, message_content: str):
        api_key = await self.bot.get_shared_api_tokens("openai")
        if not api_key.get("api_key"):
            log.error("OpenAI API key not found.")
            return "Sorry, I can't respond right now. Ask an admin to set up the OpenAI API key."

        headers = {
            "Authorization": f"Bearer {api_key['api_key']}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "system", "content": "You are a One Piece themed AI assistant."},
                         {"role": "user", "content": message_content}]
        }

        async with self.session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['choices'][0]['message']['content']
            else:
                log.error(f"Error from OpenAI API: {resp.status}")
                return "Sorry, I couldn't generate a response. Please try again later."

    async def trivia_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for guild in self.bot.guilds:
                channel_id = await self.config.guild(guild).trivia_channel()
                if channel_id:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        question, answer = await self.get_random_trivia()
                        await channel.send(f"One Piece Trivia Time! {question}")
                        
                        def check(m):
                            return m.channel == channel and not m.author.bot

                        try:
                            guess = await self.bot.wait_for('message', timeout=30.0, check=check)
                            if guess.content.lower() == answer.lower():
                                self.user_trivia_scores[guess.author.id] += 1
                                belis_earned = random.randint(10, 50)
                                await self.award_belis(guess.author, belis_earned)
                                await channel.send(f"Correct, {guess.author.mention}! You've earned {belis_earned} Belis.")
                            else:
                                await channel.send(f"Time's up! The correct answer was: {answer}")
                        except asyncio.TimeoutError:
                            await channel.send(f"Time's up! The correct answer was: {answer}")

            frequency = await self.config.guild(guild).trivia_frequency()
            await asyncio.sleep(frequency)

    async def get_random_trivia(self):
        # In a real implementation, you might want to fetch this from a database or API
        trivia_list = [
            ("What is the name of Luffy's pirate crew?", "The Straw Hat Pirates"),
            ("Who is known as the 'Pirate Hunter'?", "Roronoa Zoro"),
            ("What is the name of the legendary treasure in One Piece?", "The One Piece"),
            ("What is the name of Luffy's signature attack?", "Gomu Gomu no"),
            ("Who is the cook of the Straw Hat Pirates?", "Sanji"),
        ]
        return random.choice(trivia_list)

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def belis(self, ctx):
        """Check your current Belis balance"""
        member = ctx.author
        belis = await self.config.member(member).belis()
        await ctx.send(f"{member.display_name}, you have {belis} Belis!")

    @commands.command()
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def leaderboard(self, ctx):
        """Display the trivia leaderboard"""
        sorted_scores = sorted(self.user_trivia_scores.items(), key=lambda x: x[1], reverse=True)
        leaderboard = []
        for i, (user_id, score) in enumerate(sorted_scores[:10], start=1):
            user = self.bot.get_user(user_id)
            if user:
                leaderboard.append(f"{i}. {user.name}: {score} points")
        
        if leaderboard:
            embed = discord.Embed(title="Trivia Leaderboard", color=discord.Color.gold())
            embed.description = "\n".join(leaderboard)
            await ctx.send(embed=embed)
        else:
            await ctx.send("No trivia scores recorded yet!")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def award_belis(self, ctx, member: discord.Member, amount: int):
        """Award Belis to a member"""
        async with self.config.member(member).belis() as belis:
            belis += amount
        await ctx.send(f"Awarded {amount} Belis to {member.display_name}!")

    @commands.command()
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def daily(self, ctx):
        """Claim your daily Belis reward"""
        member = ctx.author
        belis_reward = random.randint(50, 100)
        async with self.config.member(member).belis() as belis:
            belis += belis_reward
        await ctx.send(f"{member.display_name}, you've claimed your daily reward of {belis_reward} Belis!")

async def setup(bot):
    cog = OnePieceBot(bot)
    await bot.add_cog(cog)
    await cog.initialize()
