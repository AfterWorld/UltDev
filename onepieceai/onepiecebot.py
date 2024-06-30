from redbot.core import commands, Config
from redbot.core.bot import Red
import discord
import random
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
import json

log = logging.getLogger("red.onepiecebot")

class OnePieceBot(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "chat_channels": [],
            "chatgpt_enabled": True,
            "last_conversation": None,
            "last_event": None,
        }
        default_member = {
            "crew": None,
            "personality": None,
            "experience": 0,
            "conversation_history": [],
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.session = aiohttp.ClientSession()
        self.crews = ["Straw Hat Pirates", "Heart Pirates", "Red Hair Pirates", "Whitebeard Pirates", "Marine"]
        self.personalities = ["brave", "cunning", "loyal", "ambitious", "carefree"]
        self.interjection_task = self.bot.loop.create_task(self.periodic_interjection())
        self.event_task = self.bot.loop.create_task(self.periodic_event())

    def cog_unload(self):
        self.interjection_task.cancel()
        self.event_task.cancel()
        asyncio.create_task(self.session.close())

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        chat_channels = await self.config.guild(message.guild).chat_channels()
        if message.channel.id not in chat_channels:
            return

        bot_mentioned = self.bot.user in message.mentions
        last_conversation = await self.config.guild(message.guild).last_conversation()
        recent_conversation = last_conversation and (datetime.now() - datetime.fromisoformat(last_conversation)).total_seconds() < 300

        if bot_mentioned or recent_conversation:
            await self.process_message(message)

    async def process_message(self, message: discord.Message):
        user_data = await self.config.member(message.author).all()
        
        if not user_data['crew']:
            await self.assign_random_crew(message.author)
            user_data['crew'] = await self.config.member(message.author).crew()

        if not user_data['personality']:
            await self.assign_random_personality(message.author)
            user_data['personality'] = await self.config.member(message.author).personality()

        # Update user experience
        await self.config.member(message.author).experience.set(user_data['experience'] + 1)

        # Prepare conversation history
        conversation_history = user_data['conversation_history'][-5:]  # Last 5 interactions
        conversation_history.append(f"User: {message.content}")

        context = (
            f"You are a One Piece themed AI assistant. "
            f"The user, {message.author.display_name}, is part of the {user_data['crew']} "
            f"and has a {user_data['personality']} personality. "
            f"Their experience level is {user_data['experience']}. "
            f"Respond in character, incorporating One Piece themes and the user's crew and personality. "
            f"Recent conversation: {json.dumps(conversation_history)}"
        )

        response = await self.generate_chatgpt_response(context, message.content)
        await message.channel.send(response)

        # Update conversation history
        conversation_history.append(f"AI: {response}")
        await self.config.member(message.author).conversation_history.set(conversation_history[-10:])  # Keep last 10 interactions

        # Update the last conversation time
        await self.config.guild(message.guild).last_conversation.set(datetime.now().isoformat())

    async def generate_chatgpt_response(self, context: str, message_content: str):
        api_key = await self.bot.get_shared_api_tokens("openai")
        if not api_key.get("api_key"):
            log.error("OpenAI API key not found.")
            return "Yohohoho! It seems my Den Den Mushi is out of order. I can't respond right now!"

        headers = {
            "Authorization": f"Bearer {api_key['api_key']}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": message_content}
            ]
        }

        async with self.session.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['choices'][0]['message']['content']
            else:
                log.error(f"Error from OpenAI API: {resp.status}")
                return "Ah, the Grand Line is interfering with our communication. Let's try again later!"

    async def assign_random_crew(self, member: discord.Member):
        crew = random.choice(self.crews)
        await self.config.member(member).crew.set(crew)

    async def assign_random_personality(self, member: discord.Member):
        personality = random.choice(self.personalities)
        await self.config.member(member).personality.set(personality)

    async def periodic_interjection(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(random.randint(3600, 7200))  # Random interval between 1-2 hours
            for guild in self.bot.guilds:
                channels = await self.config.guild(guild).chat_channels()
                if channels:
                    channel = self.bot.get_channel(random.choice(channels))
                    if channel:
                        interjection = await self.generate_interjection()
                        await channel.send(interjection)

    async def generate_interjection(self):
        interjections = [
            "Yohohoho! Did someone mention adventure?",
            "I smell treasure nearby! Who wants to go exploring?",
            "The sea is calling our names, crew! Any takers for a quick voyage?",
            "My Observation Haki is tingling. Something exciting is about to happen!",
            "Who's up for a round of 'Guess That Devil Fruit'?",
        ]
        return random.choice(interjections)

    async def periodic_event(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(86400)  # Daily events
            for guild in self.bot.guilds:
                channels = await self.config.guild(guild).chat_channels()
                if channels:
                    channel = self.bot.get_channel(random.choice(channels))
                    if channel:
                        event = await self.generate_event()
                        await channel.send(event)
                        await self.config.guild(guild).last_event.set(datetime.now().isoformat())

    async def generate_event(self):
        events = [
            "Breaking News: A mysterious island has appeared on the horizon! Who dares to explore it?",
            "Attention all pirates and marines! A Buster Call has been initiated in a nearby sector. Prepare for chaos!",
            "The Reverie is about to begin! Representatives from all kingdoms are gathering. What secrets will be revealed?",
            "A powerful storm is brewing in the New World. All ships are advised to seek shelter immediately!",
            "Rumors spread of a hidden poneglyph discovered in an ancient ruin. The race to find it begins now!",
        ]
        return f"**One Piece World Event**\n{random.choice(events)}\n\nHow will you respond to this event? Your actions may shape the future of the One Piece world!"

    @commands.command()
    async def setchannel(self, ctx, channel: discord.TextChannel):
        """Set a channel for One Piece bot conversations"""
        async with self.config.guild(ctx.guild).chat_channels() as channels:
            if channel.id not in channels:
                channels.append(channel.id)
        await ctx.send(f"I'll now converse in {channel.mention}! Just mention me or continue recent conversations to chat!")

    @commands.command()
    async def toggleai(self, ctx):
        """Toggle AI responses on/off"""
        current = await self.config.guild(ctx.guild).chatgpt_enabled()
        await self.config.guild(ctx.guild).chatgpt_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"AI responses have been {state}.")

    @commands.command()
    async def mycharacter(self, ctx):
        """View your One Piece character details"""
        user_data = await self.config.member(ctx.author).all()
        embed = discord.Embed(title=f"{ctx.author.display_name}'s One Piece Character", color=discord.Color.blue())
        embed.add_field(name="Crew", value=user_data['crew'], inline=False)
        embed.add_field(name="Personality", value=user_data['personality'].capitalize(), inline=False)
        embed.add_field(name="Experience", value=user_data['experience'], inline=False)
        await ctx.send(embed=embed)

async def setup(bot):
    cog = OnePieceBot(bot)
    await bot.add_cog(cog)
