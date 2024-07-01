import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import random
import asyncio
from openai import OpenAI
from datetime import datetime, timedelta
import json
import tiktoken

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
            "world_state": {"weather": "calm", "current_island": "Foosha Village"},
            "global_events": [],
        }
        default_member = {
            "character": {"name": "", "traits": [], "skills": {}},
            "crew": "",
            "experience": 0,
            "beris": 1000,
            "devil_fruit": "",
            "bounty": 0,
            "inventory": {},
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.client = None
        self.story_task = self.bot.loop.create_task(self.evolve_story())
        self.world_task = self.bot.loop.create_task(self.update_world())
        self.npc_task = self.bot.loop.create_task(self.npc_interactions())
        self.event_task = self.bot.loop.create_task(self.periodic_event())
        self.treasure_task = self.bot.loop.create_task(self.periodic_treasure_clue())
        self.token_reset_task = self.bot.loop.create_task(self.reset_daily_tokens())
        self.total_tokens_used = 0
        self.one_piece_characters = ["Monkey D. Luffy", "Roronoa Zoro", "Nami", "Usopp", "Sanji", "Tony Tony Chopper", "Nico Robin", "Franky", "Brook", "Jinbe"]
        self.devil_fruits = ["Gomu Gomu no Mi", "Mera Mera no Mi", "Hie Hie no Mi", "Gura Gura no Mi", "Ope Ope no Mi"]
        self.crews = ["Straw Hat Pirates", "Heart Pirates", "Red Hair Pirates", "Whitebeard Pirates", "Big Mom Pirates"]

    def cog_unload(self):
        self.story_task.cancel()
        self.world_task.cancel()
        self.npc_task.cancel()
        self.event_task.cancel()
        self.treasure_task.cancel()
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

        await self.process_message(message)

    async def process_message(self, message: discord.Message):
        user_data = await self.config.member(message.author).all()
        guild_data = await self.config.guild(message.guild).all()

        # Update user's experience and beris
        exp_gain = len(message.content.split()) // 2  # Simple exp gain based on message length
        beri_change = random.randint(-10, 20)  # Random beri change
        
        await self.config.member(message.author).experience.set(user_data['experience'] + exp_gain)
        await self.config.member(message.author).beris.set(user_data['beris'] + beri_change)

        # Check for character creation
        if not user_data['character']['name']:
            await self.create_character(message.author)
            user_data = await self.config.member(message.author).all()

        # Generate AI response
        context = f"Current storyline: {guild_data['current_storyline']}\n"
        context += f"World state: {json.dumps(guild_data['world_state'])}\n"
        context += f"User {message.author.display_name} ({user_data['character']['name']}) said: {message.content}\n"
        context += f"User traits: {', '.join(user_data['character']['traits'])}\n"
        context += f"User skills: {json.dumps(user_data['character']['skills'])}"

        response = await self.generate_ai_response(context)
        await message.channel.send(response)

        # Update storyline
        guild_data['current_storyline'] += f"\n{message.author.display_name}: {message.content}\nAI: {response}"
        await self.config.guild(message.guild).current_storyline.set(guild_data['current_storyline'])

        # Check for skill improvements
        await self.check_skill_improvement(message.author, message.content)

    async def create_character(self, user: discord.Member):
        traits = random.sample(["brave", "cunning", "loyal", "ambitious", "carefree"], 2)
        skills = {"strength": 1, "intelligence": 1, "charisma": 1}
        character = {
            "name": f"{user.display_name} the {traits[0].capitalize()}",
            "traits": traits,
            "skills": skills
        }
        await self.config.member(user).character.set(character)
        await self.config.member(user).crew.set(random.choice(self.crews))
        await self.config.member(user).devil_fruit.set(random.choice(self.devil_fruits))

    async def check_skill_improvement(self, user: discord.Member, message_content: str):
        skills = (await self.config.member(user).character())['skills']
        if "fight" in message_content.lower() or "battle" in message_content.lower():
            skills['strength'] += 1
        if "read" in message_content.lower() or "study" in message_content.lower():
            skills['intelligence'] += 1
        if "talk" in message_content.lower() or "negotiate" in message_content.lower():
            skills['charisma'] += 1
        await self.config.member(user).character.skills.set(skills)

    async def generate_ai_response(self, context: str):
        if not self.client:
            await self.initialize_client()
            if not self.client:
                return "The Den Den Mushi is out of order. Please try again later."

        guild = self.bot.guilds[0]
        guild_data = await self.config.guild(guild).all()
        
        if guild_data['daily_tokens_used'] >= guild_data['daily_token_limit']:
            return random.choice([
                "I'm a bit tired now. Let's chat later!",
                "The Den Den Mushi needs a break. Try again soon!",
                "Even pirates need to rest sometimes. I'll be back later!"
            ])

        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a One Piece themed AI assistant. Respond in character, incorporating One Piece themes and lore."},
                    {"role": "user", "content": context}
                ]
            )
            tokens_used = response.usage.total_tokens
            self.total_tokens_used += tokens_used
            await self.config.guild(guild).daily_tokens_used.set(guild_data['daily_tokens_used'] + tokens_used)
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def evolve_story(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(3600)  # Evolve story every hour
            for guild in self.bot.guilds:
                storyline = await self.config.guild(guild).current_storyline()
                new_development = await self.generate_ai_response(f"Evolve this One Piece storyline: {storyline}")
                await self.config.guild(guild).current_storyline.set(new_development)
                
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        await channel.send(f"**Story Update**\n{new_development}")

    async def update_world(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(1800)  # Update world every 30 minutes
            for guild in self.bot.guilds:
                world_state = await self.config.guild(guild).world_state()
                world_state['weather'] = random.choice(["calm", "stormy", "foggy", "sunny"])
                await self.config.guild(guild).world_state.set(world_state)
                
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        await channel.send(f"**World Update**\nThe weather has changed to {world_state['weather']}!")

    async def npc_interactions(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(5400)  # NPC interaction every 1.5 hours
            for guild in self.bot.guilds:
                npc = random.choice(["Shanks", "Buggy", "Rayleigh", "Garp"])
                interaction = await self.generate_ai_response(f"Generate a random interaction or quote from {npc} in the style of One Piece:")
                
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        await channel.send(f"**{npc} appears!**\n{interaction}")

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

    @commands.group(name="opaiadmin", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def opaiadmin(self, ctx):
        """Admin commands for OnePieceAI settings"""
        await ctx.send_help(ctx.command)

    @opaiadmin.command(name="settings")
    async def show_settings(self, ctx):
        """Display current OnePieceAI settings"""
        guild_data = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(title="OnePieceAI Settings", color=discord.Color.blue())
        
        embed.add_field(name="AI Status", value="Enabled" if guild_data['ai_enabled'] else "Disabled", inline=False)
        
        chat_channels = [ctx.guild.get_channel(channel_id).mention for channel_id in guild_data['chat_channels'] if ctx.guild.get_channel(channel_id)]
        embed.add_field(name="AI-enabled Channels", value=", ".join(chat_channels) if chat_channels else "None", inline=False)
        
        embed.add_field(name="Event Frequency", value=f"{guild_data['event_frequency']} seconds", inline=False)
        
        embed.add_field(name="Daily Token Limit", value=guild_data['daily_token_limit'], inline=True)
        embed.add_field(name="Tokens Used Today", value=guild_data['daily_tokens_used'], inline=True)
        
        last_reset = guild_data['last_token_reset']
        if last_reset:
            last_reset = datetime.fromisoformat(last_reset).strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            last_reset = "Never"
        embed.add_field(name="Last Token Reset", value=last_reset, inline=False)
        
        storyline = guild_data['current_storyline'][:1024]  # Discord embed field value limit
        embed.add_field(name="Current Storyline", value=storyline if storyline else "No active storyline", inline=False)
        
        clues = "\n".join(guild_data['treasure_clues'][-3:])  # Show last 3 clues
        embed.add_field(name="Recent Treasure Clues", value=clues if clues else "No recent clues", inline=False)
        
        embed.add_field(name="Current Weather", value=guild_data['world_state']['weather'], inline=True)
        embed.add_field(name="Current Island", value=guild_data['world_state']['current_island'], inline=True)
        
        await ctx.send(embed=embed)

    @opaiadmin.command(name="setdailylimit")
    async def set_daily_limit(self, ctx, limit: int):
        """Set the daily token usage limit"""
        await self.config.guild(ctx.guild).daily_token_limit.set(limit)
        await ctx.send(f"Daily token limit set to {limit}")

    @opaiadmin.command(name="resetusage")
    async def reset_usage(self, ctx):
        """Reset the daily token usage"""
        await self.config.guild(ctx.guild).daily_tokens_used.set(0)
        await self.config.guild(ctx.guild).last_token_reset.set(datetime.utcnow().isoformat())
        await ctx.send("Daily token usage has been reset.")

    @opaiadmin.command(name="toggleai")
    async def toggleai(self, ctx):
        """Toggle AI responses on/off"""
        current = await self.config.guild(ctx.guild).ai_enabled()
        await self.config.guild(ctx.guild).ai_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"AI responses have been {state}.")

    @opaiadmin.command(name="seteventfrequency")
    async def seteventfrequency(self, ctx, seconds: int):
        """Set the frequency of random events in seconds"""
        await self.config.guild(ctx.guild).event_frequency.set(seconds)
        await ctx.send(f"Event frequency set to every {seconds} seconds.")

    @opaiadmin.command(name="addchannel")
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
            encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
            estimated_cost = (self.total_tokens_used / 1000) * 0.002
            monthly_limit = 30000  # Adjust this based on your actual limit
            tokens_left = monthly_limit - self.total_tokens_used
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
            raise

async def setup(bot):
    cog = OnePieceAI(bot)
    await cog.initialize_client()
    await bot.add_cog(cog)
