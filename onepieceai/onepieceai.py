import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import random
import asyncio
from openai import OpenAI
from datetime import datetime, timedelta
import tiktoken
import json

class OnePieceAI(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "chat_channels": [],
            "ai_enabled": True,
            "event_frequency": 3600,
            "current_storyline": "",
            "treasure_clues": [],
            "daily_token_limit": 50000,
            "daily_tokens_used": 0,
            "last_token_reset": None,
        }
        default_member = {
            "character_role": "",
            "experience": 0,
            "crew": "",
            "devil_fruit": "",
            "bounty": 0,
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.client = None
        self.event_task = self.bot.loop.create_task(self.periodic_event())
        self.treasure_task = self.bot.loop.create_task(self.periodic_treasure_clue())
        self.ambient_task = self.bot.loop.create_task(self.periodic_ambient())
        self.token_reset_task = self.bot.loop.create_task(self.reset_daily_tokens())
        self.total_tokens_used = 0
        self.one_piece_characters = ["Monkey D. Luffy", "Roronoa Zoro", "Nami", "Usopp", "Sanji", "Tony Tony Chopper", "Nico Robin", "Franky", "Brook", "Jinbe"]
        self.devil_fruits = ["Gomu Gomu no Mi", "Mera Mera no Mi", "Hie Hie no Mi", "Gura Gura no Mi", "Ope Ope no Mi"]
        self.crews = ["Straw Hat Pirates", "Heart Pirates", "Red Hair Pirates", "Whitebeard Pirates", "Big Mom Pirates"]

    def cog_unload(self):
        self.event_task.cancel()
        self.treasure_task.cancel()
        self.ambient_task.cancel()
        self.token_reset_task.cancel()

    async def initialize_client(self):
        api_key = (await self.bot.get_shared_api_tokens("openai")).get("api_key")
        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            print("OpenAI API key not found.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        chat_channels = await self.config.guild(message.guild).chat_channels()
        if message.channel.id not in chat_channels:
            return

        ai_enabled = await self.config.guild(message.guild).ai_enabled()
        if not ai_enabled:
            return

        user_data = await self.config.member(message.author).all()
        if not user_data['character_role']:
            user_data['character_role'] = random.choice(self.one_piece_characters)
            user_data['crew'] = random.choice(self.crews)
            user_data['devil_fruit'] = random.choice(self.devil_fruits)
            await self.config.member(message.author).set(user_data)

        bot_mentioned = self.bot.user in message.mentions
        if bot_mentioned:
            response = await self.get_response(message.content, user_data)
            await message.channel.send(response)

        await self.config.member(message.author).experience.set(user_data['experience'] + 1)
        await self.update_bounty(message.author)

    async def get_response(self, prompt: str, user_data: dict):
        guild = self.bot.guilds[0]
        guild_data = await self.config.guild(guild).all()
        
        if guild_data['daily_tokens_used'] >= guild_data['daily_token_limit']:
            return random.choice([
                "I'm a bit tired now. Let's chat later!",
                "The Den Den Mushi needs a break. Try again soon!",
                "Even pirates need to rest sometimes. I'll be back later!"
            ])

        if random.random() < 0.3:  # 30% chance of using a pre-written response
            return self.get_prewritten_response(user_data)

        response = await self.generate_ai_response(prompt, user_data)
        return response

    def get_prewritten_response(self, user_data: dict):
        responses = [
            f"Ahoy, {user_data['character_role']}! How's life aboard the {user_data['crew']}?",
            f"I heard your {user_data['devil_fruit']} powers are getting stronger!",
            "The Grand Line is full of mysteries. What adventure shall we embark on next?",
            f"Your bounty of {user_data['bounty']} Berries is impressive! Keep up the good work!",
            "I smell adventure on the horizon. Are you ready to set sail?",
        ]
        return random.choice(responses)

    async def generate_ai_response(self, prompt: str, user_data: dict):
        if not self.client:
            await self.initialize_client()
            if not self.client:
                return "I'm not feeling well at the moment. Please try again later."

        try:
            guild = self.bot.guilds[0]
            guild_data = await self.config.guild(guild).all()
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"You are a One Piece themed AI assistant. The user has the role of {user_data['character_role']}, is part of the {user_data['crew']}, and has the {user_data['devil_fruit']} power. Current storyline: {guild_data['current_storyline']}. Respond in character, incorporating One Piece themes and lore."},
                    {"role": "user", "content": prompt}
                ]
            )
            tokens_used = response.usage.total_tokens
            self.total_tokens_used += tokens_used
            await self.config.guild(guild).daily_tokens_used.set(guild_data['daily_tokens_used'] + tokens_used)
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def update_bounty(self, user: discord.Member):
        user_data = await self.config.member(user).all()
        new_bounty = user_data['experience'] * 1000  # Simple bounty calculation
        await self.config.member(user).bounty.set(new_bounty)

    async def periodic_event(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(await self.config.guild(self.bot.guilds[0]).event_frequency())
            for guild in self.bot.guilds:
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        event = self.generate_random_event()
                        await channel.send(event)

    def generate_random_event(self):
        events = [
            "A mysterious island has appeared on the horizon!",
            "A powerful storm is brewing in the New World!",
            "Rumors of a hidden treasure map are spreading!",
            "A rival pirate crew has been spotted nearby!",
            "The Marines have launched a surprise attack!"
        ]
        event = random.choice(events)
        return f"**One Piece World Event**\n\n{event}"

    async def periodic_treasure_clue(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(7200)  # Every 2 hours
            for guild in self.bot.guilds:
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        clue = self.generate_treasure_clue()
                        await channel.send(f"**Treasure Clue**\n\n{clue}")

    def generate_treasure_clue(self):
        clues = [
            "Where the sun sets twice, X marks the spot.",
            "In the shadow of the skull-shaped mountain, treasure awaits.",
            "When the three moons align, the path will be revealed.",
            "Beneath the roots of the oldest tree on Laugh Tale, riches lie.",
            "Where the sea kings slumber, gold and jewels glitter."
        ]
        return random.choice(clues)

    async def periodic_ambient(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(1800)  # Every 30 minutes
            for guild in self.bot.guilds:
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        ambient = self.get_ambient_snippet()
                        await channel.send(ambient)

    def get_ambient_snippet(self):
        snippets = [
            "A seagull lands on the crow's nest, carrying a message in its beak.",
            "The smell of Sanji's cooking wafts across the deck, making everyone's mouths water.",
            "Nami studies her maps intently, plotting the course to the next island.",
            "Zoro's snores can be heard from the crow's nest as he naps during his watch.",
            "Brook plays a melancholy tune on his violin, filling the air with sweet music."
        ]
        return random.choice(snippets)

    async def reset_daily_tokens(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.utcnow()
            tomorrow = now + timedelta(days=1)
            next_reset = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
            await asyncio.sleep((next_reset - now).total_seconds())
            for guild in self.bot.guilds:
                await self.config.guild(guild).daily_tokens_used.set(0)
                await self.config.guild(guild).last_token_reset.set(next_reset.isoformat())

    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def toggleai(self, ctx):
        """Toggle AI responses on/off"""
        current = await self.config.guild(ctx.guild).ai_enabled()
        await self.config.guild(ctx.guild).ai_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"AI responses have been {state}.")

    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def seteventfrequency(self, ctx, seconds: int):
        """Set the frequency of random events in seconds"""
        await self.config.guild(ctx.guild).event_frequency.set(seconds)
        await ctx.send(f"Event frequency set to every {seconds} seconds.")

    @commands.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def addchannel(self, ctx, channel: discord.TextChannel):
        """Add a channel for AI interactions and events"""
        async with self.config.guild(ctx.guild).chat_channels() as channels:
            if channel.id not in channels:
                channels.append(channel.id)
        await ctx.send(f"{channel.mention} added to AI-enabled channels.")

    @commands.command()
    @commands.is_owner()
    async def check_openai_usage(self, ctx):
        """Check estimated OpenAI API usage based on token count"""
        if not self.client:
            await ctx.send("OpenAI client is not initialized.")
            return

        try:
            # Get the encoding for gpt-3.5-turbo
            encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

            # Estimate cost (assuming $0.002 per 1K tokens for gpt-3.5-turbo)
            estimated_cost = (self.total_tokens_used / 1000) * 0.002

            # Example of how many tokens are left (assuming a monthly limit of 10 million tokens)
            monthly_limit = 30000  # Adjust this based on your actual limit
            tokens_left = monthly_limit - self.total_tokens_used

            # Create a sample message to show token usage
            sample_message = "This is a sample message to show token usage."
            sample_tokens = len(encoding.encode(sample_message))

            await ctx.send(f"Estimated usage since bot start:\n"
                           f"Total tokens used: {self.total_tokens_used:,}\n"
                           f"Estimated cost: ${estimated_cost:.2f}\n"
                           f"Estimated tokens left: {tokens_left:,}\n"
                           f"\nSample message: '{sample_message}'\n"
                           f"Token count: {sample_tokens}")

        except Exception as e:
            await ctx.send(f"Error checking usage: {str(e)}")
            raise  # This will print the full error traceback in the console

async def setup(bot):
    cog = OnePieceAI(bot)
    await cog.initialize_client()
    await bot.add_cog(cog)
