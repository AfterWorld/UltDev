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
            "world_state": {"marine_influence": 50, "pirate_influence": 50},
            "active_crews": {},
        }
        default_member = {
            "crew": None,
            "personality": None,
            "experience": 0,
            "conversation_history": [],
            "items": [],
            "achievements": [],
            "adventure_cooldown": None,
            "current_crew": None,
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.session = aiohttp.ClientSession()
        self.crews = ["Straw Hat Pirates", "Heart Pirates", "Red Hair Pirates", "Whitebeard Pirates", "Marine"]
        self.personalities = ["brave", "cunning", "loyal", "ambitious", "carefree"]
        self.interjection_task = self.bot.loop.create_task(self.periodic_interjection())
        self.event_task = self.bot.loop.create_task(self.periodic_event())
        self.world_event_task = self.bot.loop.create_task(self.check_world_events())

    def cog_unload(self):
        self.interjection_task.cancel()
        self.event_task.cancel()
        self.world_event_task.cancel()
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
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def adventure(self, ctx):
        """Embark on a One Piece adventure!"""
        user_data = await self.config.member(ctx.author).all()
        
        if user_data['adventure_cooldown'] and datetime.now() < datetime.fromisoformat(user_data['adventure_cooldown']):
            time_left = datetime.fromisoformat(user_data['adventure_cooldown']) - datetime.now()
            return await ctx.send(f"You're still recovering from your last adventure. Try again in {time_left.seconds // 60} minutes.")

        adventure = await self.generate_adventure(ctx.author, user_data)
        
        embed = discord.Embed(title="One Piece Adventure", description=adventure['description'], color=discord.Color.blue())
        embed.add_field(name="Challenge", value=adventure['challenge'], inline=False)
        embed.add_field(name="Reward", value=adventure['reward'], inline=False)
        
        message = await ctx.send(embed=embed)
        await message.add_reaction("⚔️")  # Combat
        await message.add_reaction("🗣️")  # Diplomacy
        await message.add_reaction("🏃")  # Escape
        await message.add_reaction("👥")  # Team up (if in a crew)

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⚔️", "🗣️", "🏃", "👥"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("Adventure timed out. Try again later!")

        if str(reaction.emoji) == "👥" and user_data['current_crew']:
            result = await self.start_group_adventure(ctx, user_data, adventure)
        else:
            result = await self.resolve_adventure(ctx.author, user_data, adventure, str(reaction.emoji))
        
        await ctx.send(embed=result)

        # Set cooldown
        await self.config.member(ctx.author).adventure_cooldown.set((datetime.now() + timedelta(hours=1)).isoformat())

    async def generate_adventure(self, user: discord.Member, user_data: dict):
        adventures = [
            {
                "description": "You've stumbled upon a Marine outpost!",
                "challenge": "Will you fight the Marines, try to sneak past, or attempt to negotiate?",
                "reward": "Valuable intelligence and a chance to influence the world.",
                "difficulty": 3,
            },
            {
                "description": "A rival pirate crew is attacking a nearby island!",
                "challenge": "Will you engage in ship-to-ship combat, try to out-maneuver them, or attempt to form an alliance?",
                "reward": "Increased reputation and potential new crew members.",
                "difficulty": 4,
            },
            {
                "description": "You've discovered a hidden cave that might contain a Poneglyph!",
                "challenge": "Will you brave the dangerous traps, try to decipher the ancient writings, or look for an alternative entrance?",
                "reward": "Ancient knowledge and a rare artifact.",
                "difficulty": 5,
            },
            {
                "description": "A powerful storm is approaching, and a small village needs evacuation!",
                "challenge": "Will you use your ship to evacuate the villagers, try to redirect the storm, or fortify the village?",
                "reward": "Gratitude of the villagers and potential allies.",
                "difficulty": 4,
            },
            {
                "description": "You've received intel about a secret World Government facility!",
                "challenge": "Will you infiltrate the facility, gather outside intelligence, or spread disinformation?",
                "reward": "Top-secret information and advanced technology.",
                "difficulty": 6,
            },
        ]
        
        adventure = random.choice(adventures)
        return adventure

    async def resolve_adventure(self, user: discord.Member, user_data: dict, adventure: dict, choice: str):
        success_chance = (user_data['experience'] / 100) - adventure['difficulty'] + random.random()
        success = success_chance > 0.5

        embed = discord.Embed(title="Adventure Result", color=discord.Color.green() if success else discord.Color.red())

        if choice == "⚔️":  # Combat
            if success:
                embed.description = f"Your combat skills prevail! {adventure['reward']}"
                await self.add_item(user, "Combat Medal")
                await self.adjust_world_state(user_data['crew'], 5)
            else:
                embed.description = "Despite your best efforts, you were overwhelmed. Retreat and recover!"

        elif choice == "🗣️":  # Diplomacy
            if success:
                embed.description = f"Your silver tongue saves the day! {adventure['reward']}"
                await self.add_item(user, "Diplomatic Badge")
                await self.adjust_world_state(user_data['crew'], 3)
            else:
                embed.description = "Your words fall on deaf ears. Make a hasty retreat!"

        else:  # Escape
            if success:
                embed.description = "You make a daring escape, living to fight another day!"
            else:
                embed.description = "Your escape is foiled! Prepare for conflict!"

        # Update user experience
        new_exp = user_data['experience'] + (5 if success else 1)
        await self.config.member(user).experience.set(new_exp)
        embed.add_field(name="Experience Gained", value=f"{5 if success else 1} points")

        return embed

    @commands.group()
    async def crew(self, ctx):
        """Crew management commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @crew.command(name="create")
    async def create_crew(self, ctx, *, crew_name: str):
        """Create a new crew"""
        guild_data = await self.config.guild(ctx.guild).all()
        if ctx.author.id in guild_data['active_crews']:
            return await ctx.send("You're already in a crew. Leave your current crew first.")

        new_crew = {
            "name": crew_name,
            "captain": ctx.author.id,
            "members": [ctx.author.id],
            "level": 1,
            "experience": 0,
        }

        async with self.config.guild(ctx.guild).active_crews() as crews:
            crews[ctx.author.id] = new_crew

        await self.config.member(ctx.author).current_crew.set(ctx.author.id)
        await ctx.send(f"Crew '{crew_name}' has been created with you as the captain!")

    @crew.command(name="join")
    async def join_crew(self, ctx, captain: discord.Member):
        """Join an existing crew"""
        guild_data = await self.config.guild(ctx.guild).all()
        if ctx.author.id in guild_data['active_crews']:
            return await ctx.send("You're already in a crew. Leave your current crew first.")

        if captain.id not in guild_data['active_crews']:
            return await ctx.send("That user is not a captain of any crew.")

        async with self.config.guild(ctx.guild).active_crews() as crews:
            crews[captain.id]["members"].append(ctx.author.id)

        await self.config.member(ctx.author).current_crew.set(captain.id)
        await ctx.send(f"You've joined {captain.display_name}'s crew!")

    @crew.command(name="leave")
    async def leave_crew(self, ctx):
        """Leave your current crew"""
        user_data = await self.config.member(ctx.author).all()
        if not user_data['current_crew']:
            return await ctx.send("You're not in a crew.")

        async with self.config.guild(ctx.guild).active_crews() as crews:
            crew = crews[user_data['current_crew']]
            crew["members"].remove(ctx.author.id)
            if crew["captain"] == ctx.author.id:
                if crew["members"]:
                    new_captain = crew["members"][0]
                    crew["captain"] = new_captain
                    await ctx.send(f"You've left the crew. {self.bot.get_user(new_captain).display_name} is the new captain.")
                else:
                    del crews[user_data['current_crew']]
                    await ctx.send("You've disbanded the crew as you were the last member.")
            else:
                await ctx.send("You've left the crew.")

        await self.config.member(ctx.author).current_crew.set(None)

    async def start_group_adventure(self, ctx, user_data: dict, adventure: dict):
        crew_id = user_data['current_crew']
        guild_data = await self.config.guild(ctx.guild).all()
        crew = guild_data['active_crews'][crew_id]

        # Notify crew members
        for member_id in crew['members']:
            if member_id != ctx.author.id:
                member = ctx.guild.get_member(member_id)
                if member:
                    await member.send(f"{ctx.author.display_name} has started a group adventure! React with 👍 to join!")

        # Wait for responses
        participants = [ctx.author]
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 60:  # Wait for 1 minute
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add",
                    timeout=60.0,
                    check=lambda r, u: str(r.emoji) == "👍" and u.id in crew['members'] and u not in participants
                )
                participants.append(user)
                await ctx.send(f"{user.display_name} has joined the adventure!")
            except asyncio.TimeoutError:
                break

        # Resolve group adventure
        success_chance = sum(self.config.member(p).experience() for p in participants) / (100 * len(participants)) - adventure['difficulty'] + random.random()
        success = success_chance > 0.5

        embed = discord.Embed(title="Group Adventure Result", color=discord.Color.green() if success else discord.Color.red())
        
        if success:
            embed.description = f"Your crew's combined efforts lead to victory! {adventure['reward']}"
            for participant in participants:
                await self.add_item(participant, "Crew Victory Token")
            await self.adjust_world_state(user_data['crew'], 5 * len(participants))
        else:
            embed.description = "Despite your crew's best efforts, you were unable to overcome the challenge. Retreat and recover!"

        # Update crew experience
        async with self.config.guild(ctx.guild).active_crews() as crews:
            crews[crew_id]["experience"] += 10 if success else 2
            if crews[crew_id]["experience"] >= crews[crew_id]["level"] * 100:
                crews[crew_id]["level"] += 1
                crews[crew_id]["experience"] = 0
                embed.add_field(name="Crew Levelup!", value=f"Your crew is now level {crews[crew_id]['level']}!")

        # Update individual experience
        for participant in participants:
            user_data = await self.config.member(participant).all()
            new_exp = user_data['experience'] + (5 if success else 1)
            await self.config.member(participant).experience.set(new_exp)

        embed.add_field(name="Participants", value=", ".join(p.display_name for p in participants), inline=False)
        embed.add_field(name="Experience Gained", value=f"{5 if success else 1} points each")

        return embed

    @commands.command()
    async def craft(self, ctx, *, item_name: str):
        """Craft an item using materials in your inventory"""
        user_data = await self.config.member(ctx.author).all()
        
        recipes = {
            "Log Pose": {"materials": ["Iron Ingot", "Glass Orb"], "result": "Log Pose"},
            "Clima-Tact": {"materials": ["Metal Pipe", "Weather Orb", "Dials"], "result": "Clima-Tact"},
            "Adam Wood Plank": {"materials": ["Adam Wood", "Carpenter Tools"], "result": "Adam Wood Plank"},
        }

        if item_name not in recipes:
            return await ctx.send(f"No recipe found for {item_name}. Available recipes: {', '.join(recipes.keys())}")

        recipe = recipes[item_name]
        user_inventory = user_data['items']

        # Check if user has all required materials
        for material in recipe['materials']:
            if material not in user_inventory:
                return await ctx.send(f"You're missing {material} to craft {item_name}.")

        # Remove materials from inventory
        async with self.config.member(ctx.author).items() as items:
            for material in recipe['materials']:
                items.remove(material)
            items.append(recipe['result'])

        await ctx.send(f"You've successfully crafted {item_name}!")

    async def check_world_events(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(3600)  # Check every hour
            for guild in self.bot.guilds:
                world_state = await self.config.guild(guild).world_state()
                if world_state['marine_influence'] >= 75:
                    await self.trigger_world_event(guild, "marine_dominance")
                elif world_state['pirate_influence'] >= 75:
                    await self.trigger_world_event(guild, "pirate_dominance")

    async def trigger_world_event(self, guild, event_type):
        channels = await self.config.guild(guild).chat_channels()
        if not channels:
            return

        channel = self.bot.get_channel(random.choice(channels))
        if not channel:
            return

        if event_type == "marine_dominance":
            await channel.send("**World Event: Marine Dominance**\nThe Marines have gained significant control over the seas! Pirates are being hunted down relentlessly. Will you join the fight against tyranny or help maintain order?")
        elif event_type == "pirate_dominance":
            await channel.send("**World Event: Age of Pirates**\nPirates are running rampant across the world! The World Government is struggling to maintain control. Will you join the chaos or help restore balance?")

    async def add_item(self, user: discord.Member, item: str):
        async with self.config.member(user).items() as items:
            items.append(item)

    async def adjust_world_state(self, crew: str, amount: int):
        async with self.config.guild(self.bot.guilds[0]).world_state() as world_state:
            if crew == "Marine":
                world_state["marine_influence"] = min(100, world_state["marine_influence"] + amount)
                world_state["pirate_influence"] = max(0, world_state["pirate_influence"] - amount)
            else:
                world_state["pirate_influence"] = min(100, world_state["pirate_influence"] + amount)
                world_state["marine_influence"] = max(0, world_state["marine_influence"] - amount)

    @commands.command()
    async def inventory(self, ctx):
        """Display your inventory and achievements"""
        user_data = await self.config.member(ctx.author).all()
        
        embed = discord.Embed(title=f"{ctx.author.display_name}'s Inventory", color=discord.Color.gold())
        embed.add_field(name="Items", value=", ".join(user_data['items']) if user_data['items'] else "No items", inline=False)
        embed.add_field(name="Achievements", value=", ".join(user_data['achievements']) if user_data['achievements'] else "No achievements", inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def worldstate(self, ctx):
        """Check the current state of the One Piece world"""
        world_state = await self.config.guild(ctx.guild).world_state()
        
        embed = discord.Embed(title="One Piece World State", color=discord.Color.blue())
        embed.add_field(name="Marine Influence", value=f"{world_state['marine_influence']}%", inline=True)
        embed.add_field(name="Pirate Influence", value=f"{world_state['pirate_influence']}%", inline=True)
        
        await ctx.send(embed=embed)

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

async def setup(bot):
    cog = OnePieceBot(bot)
    await bot.add_cog(cog)
