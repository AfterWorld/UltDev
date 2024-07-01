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
            "event_frequency": 3600,  # Default: one event per hour
            "current_storyline": "",
            "treasure_clues": [],
        }
        default_member = {
            "character_role": "",
            "experience": 0,
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.client = None
        self.event_task = self.bot.loop.create_task(self.periodic_event())
        self.treasure_task = self.bot.loop.create_task(self.periodic_treasure_clue())
        self.total_tokens_used = 0
        self.one_piece_characters = [
            "Monkey D. Luffy", "Roronoa Zoro", "Nami", "Usopp", "Sanji",
            "Tony Tony Chopper", "Nico Robin", "Franky", "Brook", "Jinbe"
        ]

    def cog_unload(self):
        self.event_task.cancel()
        self.treasure_task.cancel()

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

        # Assign a character role if the user doesn't have one
        user_data = await self.config.member(message.author).all()
        if not user_data['character_role']:
            user_data['character_role'] = random.choice(self.one_piece_characters)
            await self.config.member(message.author).character_role.set(user_data['character_role'])

        bot_mentioned = self.bot.user in message.mentions
        if bot_mentioned:
            response = await self.generate_ai_response(message.content, user_data['character_role'])
            await message.channel.send(response)

        # Update user experience
        await self.config.member(message.author).experience.set(user_data['experience'] + 1)

    async def generate_ai_response(self, prompt: str, user_character: str):
        if not self.client:
            await self.initialize_client()
            if not self.client:
                return "I'm not feeling well at the moment. Please try again later."

        try:
            current_storyline = await self.config.guild(self.bot.guilds[0]).current_storyline()
            treasure_clues = await self.config.guild(self.bot.guilds[0]).treasure_clues()

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"You are a One Piece themed AI assistant. The user you're talking to has the role of {user_character}. Current storyline: {current_storyline}. Recent treasure clues: {json.dumps(treasure_clues)}. Respond in character, incorporating One Piece themes, lore, the current storyline, and recent treasure clues. Acknowledge the user's character role."},
                    {"role": "user", "content": prompt}
                ]
            )
            self.total_tokens_used += response.usage.total_tokens
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def periodic_event(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(await self.config.guild(self.bot.guilds[0]).event_frequency())
            for guild in self.bot.guilds:
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        event = await self.generate_random_event()
                        await channel.send(event)

    async def generate_random_event(self):
        events = [
            "A mysterious island has appeared on the horizon!",
            "A powerful storm is brewing in the New World!",
            "Rumors of a hidden treasure map are spreading!",
            "A rival pirate crew has been spotted nearby!",
            "The Marines have launched a surprise attack!"
        ]
        event = random.choice(events)
        response = await self.generate_ai_response(f"Describe this One Piece world event in detail and update the current storyline: {event}", "Narrator")
        
        # Update the current storyline
        await self.config.guild(self.bot.guilds[0]).current_storyline.set(response)
        
        return f"**One Piece World Event**\n\n{response}"

    async def periodic_treasure_clue(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(7200)  # Every 2 hours
            for guild in self.bot.guilds:
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        clue = await self.generate_treasure_clue()
                        await channel.send(f"**Treasure Clue**\n\n{clue}")

    async def generate_treasure_clue(self):
        prompt = "Generate a cryptic clue about a hidden One Piece treasure. The clue should be challenging but solvable."
        clue = await self.generate_ai_response(prompt, "Mysterious Stranger")
        
        async with self.config.guild(self.bot.guilds[0]).treasure_clues() as clues:
            clues.append(clue)
            if len(clues) > 5:
                clues.pop(0)
        
        return clue

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