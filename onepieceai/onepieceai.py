import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import random
import asyncio
from openai import OpenAI
from datetime import datetime, timedelta
import json
import tiktoken
from textblob import TextBlob
import emoji

class OnePieceAI(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "chat_channels": [],
            "ai_enabled": True,
            "event_frequency": 3600,
            "daily_token_limit": 50000,
            "daily_tokens_used": 0,
            "last_token_reset": None,
            "world_state": {"weather": "calm", "current_island": "Foosha Village", "current_arc": "East Blue Saga"},
            "global_events": [],
            "conversation_context": {},
            "discussion_topics": []
        }
        default_member = {
            "character": {"name": "", "traits": [], "skills": {}},
            "crew": "",
            "experience": 0,
            "beris": 1000,
            "devil_fruit": "",
            "bounty": 0,
            "inventory": {},
            "personality_profile": {},
            "conversation_history": [],
            "emotional_state": "neutral",
            "formality_preference": 0.5  # 0 is very informal, 1 is very formal
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.client = None
        self.story_task = self.bot.loop.create_task(self.evolve_story())
        self.world_task = self.bot.loop.create_task(self.update_world())
        self.npc_task = self.bot.loop.create_task(self.npc_interactions())
        self.event_task = self.bot.loop.create_task(self.periodic_event())
        self.token_reset_task = self.bot.loop.create_task(self.reset_daily_tokens())
        self.discussion_task = self.bot.loop.create_task(self.generate_discussion_topics())
        self.total_tokens_used = 0
        self.one_piece_characters = ["Monkey D. Luffy", "Roronoa Zoro", "Nami", "Usopp", "Sanji", "Tony Tony Chopper", "Nico Robin", "Franky", "Brook", "Jinbe"]
        self.devil_fruits = ["Gomu Gomu no Mi", "Mera Mera no Mi", "Hie Hie no Mi", "Gura Gura no Mi", "Ope Ope no Mi"]
        self.crews = ["Straw Hat Pirates", "Heart Pirates", "Red Hair Pirates", "Whitebeard Pirates", "Big Mom Pirates"]
        self.one_piece_emojis = {
            "pirate": "🏴‍☠️", "ship": "⛵", "island": "🏝️", "treasure": "💰", "fight": "⚔️",
            "devil_fruit": "🍎", "sea": "🌊", "log_pose": "🧭", "wanted_poster": "📜"
        }
        self.current_event = None
        self.storyline = "The adventure begins in the East Blue..."

    def cog_unload(self):
        self.story_task.cancel()
        self.world_task.cancel()
        self.npc_task.cancel()
        self.event_task.cancel()
        self.token_reset_task.cancel()
        self.discussion_task.cancel()

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
        exp_gain = len(message.content.split()) // 2
        beri_change = random.randint(-10, 20)
        
        await self.config.member(message.author).experience.set(user_data['experience'] + exp_gain)
        await self.config.member(message.author).beris.set(user_data['beris'] + beri_change)

        # Check for character creation
        if not user_data['character']['name']:
            await self.create_character(message.author)
            user_data = await self.config.member(message.author).all()

        # Update conversation context
        conversation_context = guild_data['conversation_context']
        if message.channel.id not in conversation_context:
            conversation_context[message.channel.id] = []
        conversation_context[message.channel.id].append({
            "user": message.author.display_name,
            "message": message.content,
            "timestamp": message.created_at.isoformat()
        })
        conversation_context[message.channel.id] = conversation_context[message.channel.id][-10:]  # Keep last 10 messages
        await self.config.guild(message.guild).conversation_context.set(conversation_context)

        # Update user's conversation history
        user_data['conversation_history'].append(message.content)
        user_data['conversation_history'] = user_data['conversation_history'][-20:]  # Keep last 20 messages
        await self.config.member(message.author).conversation_history.set(user_data['conversation_history'])

        # Perform sentiment analysis
        sentiment = TextBlob(message.content).sentiment.polarity
        if sentiment > 0.3:
            emotional_state = "positive"
        elif sentiment < -0.3:
            emotional_state = "negative"
        else:
            emotional_state = "neutral"
        await self.config.member(message.author).emotional_state.set(emotional_state)

        # Update user's personality profile
        await self.update_personality_profile(message.author, message.content)

        # Generate AI response
        context = self.build_context(message, user_data, guild_data)
        response = await self.generate_ai_response(context)

        # Post-process the response
        response = self.post_process_response(response, user_data, guild_data)

        await message.channel.send(response)

        # Update storyline
        self.storyline += f"\n{message.author.display_name}: {message.content}\nAI: {response}"

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

    async def update_personality_profile(self, user: discord.Member, message: str):
        async with self.config.member(user).personality_profile() as profile:
            words = message.lower().split()
            for word in words:
                if word not in profile:
                    profile[word] = 0
                profile[word] += 1

    def build_context(self, message: discord.Message, user_data: dict, guild_data: dict):
        context = f"Current storyline: {self.storyline}\n"
        context += f"World state: {json.dumps(guild_data['world_state'])}\n"
        context += f"User {message.author.display_name} ({user_data['character']['name']}) said: {message.content}\n"
        context += f"User traits: {', '.join(user_data['character']['traits'])}\n"
        context += f"User skills: {json.dumps(user_data['character']['skills'])}\n"
        context += f"User's recent messages: {json.dumps(user_data['conversation_history'][-5:])}\n"
        context += f"User's emotional state: {user_data['emotional_state']}\n"
        context += f"User's formality preference: {user_data['formality_preference']}\n"
        context += f"Recent conversation: {json.dumps(guild_data['conversation_context'].get(message.channel.id, []))}\n"
        return context

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

    def post_process_response(self, response: str, user_data: dict, guild_data: dict):
        # Adjust formality
        if user_data['formality_preference'] < 0.3:
            response = response.lower().replace(".", "").replace(",", "")
        elif user_data['formality_preference'] > 0.7:
            response = response.capitalize() + "."

        # Add One Piece emojis
        for word, emoji_code in self.one_piece_emojis.items():
            if word in response.lower():
                response += f" {emoji_code}"

        # Mimic character voice if in character
        if "character_voice" in user_data and random.random() < 0.3:
            response = self.apply_character_voice(response, user_data['character_voice'])

        return response

    def apply_character_voice(self, response: str, character: str):
        if character == "Luffy":
            response += " Shishishi!"
        elif character == "Zoro":
            response = response.replace("left", "right").replace("right", "left")
        elif character == "Sanji":
            if "woman" in response.lower() or "lady" in response.lower():
                response += " Mellorine~!"
        # Add more character voices as needed
        return response

    async def generate_random_event(self):
        events = [
            "A mysterious island has appeared on the horizon!",
            "A powerful storm is brewing in the New World!",
            "Rumors of a hidden treasure map are spreading!",
            "A rival pirate crew has been spotted nearby!",
            "The Marines have launched a surprise attack!"
        ]
        event = random.choice(events)
        self.current_event = event
        return f"**One Piece World Event**\n\n{event}\n\nHow do you respond? (Use the `[p]respond` command)"

    @commands.command()
    async def respond(self, ctx, *, response: str):
        """Respond to the current world event"""
        if not self.current_event:
            await ctx.send("There is no active world event to respond to.")
            return

        # Generate AI response based on the user's response to the event
        prompt = f"Event: {self.current_event}\nUser response: {response}\nGenerate a narrative of how this response affects the event and the overall storyline:"
        result = await self.generate_ai_response(prompt)

        # Update the storyline with the event and response
        self.storyline += f"\n\nEvent: {self.current_event}\nResponse: {response}\nOutcome: {result}"

        # Clear the current event
        self.current_event = None

        await ctx.send(f"Your response: {response}\n\nOutcome: {result}")

        # Trigger a story update
        await self.evolve_story()

    async def evolve_story(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            if not self.current_event:  # Only evolve story if there's no active event
                prompt = f"Current storyline: {self.storyline}\n\nGenerate the next development in this One Piece adventure:"
                new_development = await self.generate_ai_response(prompt)
                self.storyline += f"\n\nNew Development: {new_development}"

                # Send the new development to all AI-enabled channels
                for guild in self.bot.guilds:
                    chat_channels = await self.config.guild(guild).chat_channels()
                    for channel_id in chat_channels:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(f"**Story Update**\n{new_development}")

            await asyncio.sleep(3600)  # Wait for an hour before the next story evolution

    @commands.command()
    async def storyline(self, ctx):
        """Display the current storyline"""
        await ctx.send(f"**Current One Piece Adventure Storyline**\n\n{self.storyline}")

    async def periodic_event(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(await self.config.guild(self.bot.guilds[0]).event_frequency())
            if not self.current_event:  # Only generate a new event if there's no active event
                for guild in self.bot.guilds:
                    chat_channels = await self.config.guild(guild).chat_channels()
                    if chat_channels:
                        channel = self.bot.get_channel(random.choice(chat_channels))
                        if channel:
                            event = await self.generate_random_event()
                            await channel.send(event)

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

    async def generate_discussion_topics(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(14400)  # Generate new topics every 4 hours
            for guild in self.bot.guilds:
                topic = await self.generate_ai_response("Generate a thought-provoking discussion topic about One Piece lore, theories, or character motivations.")
                async with self.config.guild(guild).discussion_topics() as topics:
                    topics.append(topic)
                    if len(topics) > 5:
                        topics.pop(0)

    @commands.command()
    async def discuss(self, ctx):
        """Start a discussion about a One Piece topic"""
        topics = await self.config.guild(ctx.guild).discussion_topics()
        if not topics:
            topic = await self.generate_ai_response("Generate a thought-provoking discussion topic about One Piece lore, theories, or character motivations.")
        else:
            topic = topics.pop(0)
        await ctx.send(f"Let's discuss this One Piece topic:\n\n{topic}")

    @commands.command()
    async def roleplay(self, ctx, character: str):
        """Start roleplaying as a One Piece character"""
        if character.lower() in [c.lower() for c in self.one_piece_characters]:
            await self.config.member(ctx.author).character_voice.set(character)
            await ctx.send(f"You are now roleplaying as {character}! The AI will interact with you accordingly.")
        else:
            await ctx.send(f"{character} is not a recognized One Piece character. Please choose from: {', '.join(self.one_piece_characters)}")

    @commands.command()
    async def joke(self, ctx):
        """Tell a One Piece themed joke"""
        joke = await self.generate_ai_response("Tell a One Piece themed joke or pun.")
        await ctx.send(joke)

    async def check_skill_improvement(self, user: discord.Member, message_content: str):
        async with self.config.member(user).character() as character:
            if "fight" in message_content.lower() or "battle" in message_content.lower():
                character['skills']['strength'] = min(100, character['skills']['strength'] + 1)
            if "read" in message_content.lower() or "study" in message_content.lower():
                character['skills']['intelligence'] = min(100, character['skills']['intelligence'] + 1)
            if "talk" in message_content.lower() or "negotiate" in message_content.lower():
                character['skills']['charisma'] = min(100, character['skills']['charisma'] + 1)

    @commands.command()
    async def profile(self, ctx, member: discord.Member = None):
        """Display your or another member's One Piece profile"""
        target = member or ctx.author
        user_data = await self.config.member(target).all()
        
        embed = discord.Embed(title=f"{target.display_name}'s One Piece Profile", color=discord.Color.blue())
        embed.add_field(name="Character", value=user_data['character']['name'], inline=False)
        embed.add_field(name="Crew", value=user_data['crew'], inline=True)
        embed.add_field(name="Devil Fruit", value=user_data['devil_fruit'] or "None", inline=True)
        embed.add_field(name="Bounty", value=f"{user_data['bounty']:,} Beris", inline=True)
        embed.add_field(name="Skills", value="\n".join([f"{k.capitalize()}: {v}" for k, v in user_data['character']['skills'].items()]), inline=False)
        embed.add_field(name="Traits", value=", ".join(user_data['character']['traits']), inline=False)
        
        await ctx.send(embed=embed)

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
            else:
                await ctx.send(f"{channel.mention} is already an AI-enabled channel.")

    @opaiadmin.command(name="removechannel")
    async def removechannel(self, ctx, channel: discord.TextChannel):
        """Remove a channel from AI interactions and events"""
        async with self.config.guild(ctx.guild).chat_channels() as channels:
            if channel.id in channels:
                channels.remove(channel.id)
                await ctx.send(f"{channel.mention} removed from AI-enabled channels.")
            else:
                await ctx.send(f"{channel.mention} is not an AI-enabled channel.")

    @opaiadmin.command(name="listchannels")
    async def listchannels(self, ctx):
        """List all AI-enabled channels"""
        channels = await self.config.guild(ctx.guild).chat_channels()
        if channels:
            channel_mentions = [ctx.guild.get_channel(channel_id).mention for channel_id in channels if ctx.guild.get_channel(channel_id)]
            await ctx.send(f"AI-enabled channels: {', '.join(channel_mentions)}")
        else:
            await ctx.send("There are no AI-enabled channels.")

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
    await bot.add_cog(OnePieceAI(bot))
