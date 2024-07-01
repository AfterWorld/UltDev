import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import random
import asyncio
from openai import OpenAI
from datetime import datetime, timedelta
import json

class Tournament:
    def __init__(self, name, start_date, end_date, event_type):
        self.name = name
        self.start_date = start_date
        self.end_date = end_date
        self.event_type = event_type
        self.participants = []
        self.scores = {}

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
            "formality_preference": 0.5,
            "resources": {
                "food": 100,
                "wood": 50,
                "gold": 20,
                "special_items": []
            },
            "reputation": {
                "Marines": 0,
                "Pirates": 0,
                "Revolutionaries": 0
            }
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
        self.tournament_task = self.bot.loop.create_task(self.run_tournaments())
        self.feature_reminder_task = self.bot.loop.create_task(self.send_feature_reminder())
        self.total_tokens_used = 0
        self.current_event = None
        self.event_response_lock = asyncio.Lock()
        self.current_tournament = None
        self.storyline = "A new adventure begins in the world of One Piece..."
        self.roles = {
            0: "Cabin Boy",
            100: "Deckhand",
            500: "First Mate",
            1000: "Captain",
            2000: "Yonko"
        }
        self.islands = ["Alabasta", "Water 7", "Thriller Bark", "Sabaody Archipelago", "Fishman Island"]

    def cog_unload(self):
        self.story_task.cancel()
        self.world_task.cancel()
        self.npc_task.cancel()
        self.event_task.cancel()
        self.token_reset_task.cancel()
        self.discussion_task.cancel()
        self.tournament_task.cancel()
        self.feature_reminder_task.cancel()

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

        if self.bot.user in message.mentions:
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

        # Generate AI response
        context = self.build_context(message, user_data, guild_data)
        response = await self.generate_ai_response(context)

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
        await self.config.member(user).crew.set(random.choice(["Straw Hat Pirates", "Heart Pirates", "Red Hair Pirates", "Whitebeard Pirates", "Big Mom Pirates"]))
        await self.config.member(user).devil_fruit.set(random.choice(["Gomu Gomu no Mi", "Mera Mera no Mi", "Hie Hie no Mi", "Gura Gura no Mi", "Ope Ope no Mi"]))

    async def update_user_role(self, member: discord.Member, xp: int):
        async with self.config.member(member).all() as user_data:
            user_data['experience'] = user_data.get('experience', 0) + xp
            current_xp = user_data['experience']

            for required_xp, role_name in sorted(self.roles.items(), reverse=True):
                if current_xp >= required_xp:
                    role = discord.utils.get(member.guild.roles, name=role_name)
                    if role and role not in member.roles:
                        await member.add_roles(role)
                        await member.guild.system_channel.send(f"Congratulations, {member.mention}! You've earned the role of {role_name}!")
                    break

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
                    {"role": "system", "content": "You are a One Piece themed AI assistant. Respond in character, incorporating One Piece themes and lore. Include the user's character in your response and advance the story based on their actions."},
                    {"role": "user", "content": context}
                ]
            )
            tokens_used = response.usage.total_tokens
            self.total_tokens_used += tokens_used
            await self.config.guild(guild).daily_tokens_used.set(guild_data['daily_tokens_used'] + tokens_used)
            return response.choices[0].message.content
        except Exception as e:
            return f"Error generating response: {str(e)}"

    async def check_skill_improvement(self, user: discord.Member, message_content: str):
        async with self.config.member(user).character() as character:
            if "fight" in message_content.lower() or "battle" in message_content.lower():
                character['skills']['strength'] = min(100, character['skills']['strength'] + 1)
            if "read" in message_content.lower() or "study" in message_content.lower():
                character['skills']['intelligence'] = min(100, character['skills']['intelligence'] + 1)
            if "talk" in message_content.lower() or "negotiate" in message_content.lower():
                character['skills']['charisma'] = min(100, character['skills']['charisma'] + 1)

    @commands.command()
    async def profile(self, ctx):
        """Display your One Piece profile"""
        user_data = await self.config.member(ctx.author).all()
        current_xp = user_data.get('experience', 0)
        current_role = "Swabbie"
        for required_xp, role_name in sorted(self.roles.items(), reverse=True):
            if current_xp >= required_xp:
                current_role = role_name
                break

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Pirate Profile", color=discord.Color.blue())
        embed.add_field(name="Role", value=current_role, inline=False)
        embed.add_field(name="Experience", value=current_xp, inline=False)
        embed.add_field(name="Crew", value=user_data.get('crew', 'None'), inline=False)
        embed.add_field(name="Devil Fruit", value=user_data.get('devil_fruit', 'None'), inline=False)
        embed.add_field(name="Skills", value="\n".join([f"{k.capitalize()}: {v}" for k, v in user_data['character']['skills'].items()]), inline=False)
        embed.add_field(name="Bounty", value=f"{user_data['bounty']:,} Beris", inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot or reaction.message.author != self.bot.user:
            return

        xp_rewards = {
            "⚔️": ("combat", 10),
            "🧠": ("intelligence", 10),
            "🏃": ("speed", 10),
            "🍳": ("cooking", 10)
        }

        if str(reaction.emoji) in xp_rewards:
            skill, xp = xp_rewards[str(reaction.emoji)]
            await self.update_user_skill(user, skill, xp)
            await reaction.message.channel.send(f"{user.mention} gained {xp} {skill} XP!")

    async def update_user_skill(self, user: discord.User, skill: str, xp: int):
        async with self.config.member(user).all() as user_data:
            user_data.setdefault('skills', {})
            user_data['skills'][skill] = user_data['skills'].get(skill, 0) + xp

    @commands.command()
    async def resources(self, ctx):
        """Display your current resources"""
        user_data = await self.config.member(ctx.author).all()
        resources = user_data['resources']

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Resources", color=discord.Color.green())
        for resource, amount in resources.items():
            if resource != "special_items":
                embed.add_field(name=resource.capitalize(), value=amount, inline=True)
        
        if resources['special_items']:
            embed.add_field(name="Special Items", value=", ".join(resources['special_items']), inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def trade(self, ctx, member: discord.Member, give_resource: str, give_amount: int, receive_resource: str, receive_amount: int):
        """Trade resources with another user"""
        if member == ctx.author:
            return await ctx.send("You can't trade with yourself!")

        async with self.config.member(ctx.author).all() as user_data, self.config.member(member).all() as target_data:
            if give_resource not in user_data['resources'] or receive_resource not in target_data['resources']:
                return await ctx.send("Invalid resource type.")

            if user_data['resources'][give_resource] < give_amount or target_data['resources'][receive_resource] < receive_amount:
                return await ctx.send("One of you doesn't have enough resources for this trade.")

            user_data['resources'][give_resource] -= give_amount
            user_data['resources'][receive_resource] += receive_amount
            target_data['resources'][give_resource] += give_amount
            target_data['resources'][receive_resource] -= receive_amount

        await ctx.send(f"Trade successful! {ctx.author.mention} gave {give_amount} {give_resource} and received {receive_amount} {receive_resource} from {member.mention}.")

    @commands.command()
    async def reputation(self, ctx):
        """Display your reputation with different factions"""
        user_data = await self.config.member(ctx.author).all()
        rep = user_data['reputation']

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Reputation", color=discord.Color.purple())
        for faction, value in rep.items():
            embed.add_field(name=faction, value=value, inline=True)
        
        await ctx.send(embed=embed)

    async def update_reputation(self, user: discord.Member, faction: str, amount: int):
        async with self.config.member(user).all() as user_data:
            user_data['reputation'][faction] = max(-100, min(100, user_data['reputation'][faction] + amount))

    async def run_tournaments(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            if self.current_tournament is None:
                await self.start_new_tournament()
            elif datetime.now() > self.current_tournament.end_date:
                await self.end_tournament()
            await asyncio.sleep(3600)  # Check every hour

    async def start_new_tournament(self):
        tournament_types = ["Combat", "Cooking", "Navigation"]
        name = f"Grand Line {random.choice(tournament_types)} Tournament"
        start_date = datetime.now()
        end_date = start_date + timedelta(days=7)
        self.current_tournament = Tournament(name, start_date, end_date, random.choice(tournament_types))

        for guild in self.bot.guilds:
            for channel_id in await self.config.guild(guild).chat_channels():
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"**New Tournament Started!**\n{name}\nType `.join_tournament` to participate!")

    @commands.command()
    async def join_tournament(self, ctx):
        """Join the current tournament"""
        if self.current_tournament is None:
            return await ctx.send("There is no active tournament right now.")
        if ctx.author.id in self.current_tournament.participants:
            return await ctx.send("You're already participating in this tournament!")
        self.current_tournament.participants.append(ctx.author.id)
        self.current_tournament.scores[ctx.author.id] = 0
        await ctx.send(f"You've joined the {self.current_tournament.name}!")

    async def end_tournament(self):
        if not self.current_tournament:
            return

        winner_id = max(self.current_tournament.scores, key=self.current_tournament.scores.get)
        winner = self.bot.get_user(winner_id)

        for guild in self.bot.guilds:
            for channel_id in await self.config.guild(guild).chat_channels():
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"**Tournament Ended!**\n{self.current_tournament.name}\nWinner: {winner.mention}")

        # Award the winner
        await self.update_user_role(winner, 100)  # Big XP boost
        special_role = await self.create_special_role(winner.guild, f"{self.current_tournament.event_type} Champion")
        await winner.add_roles(special_role)

        self.current_tournament = None

    async def create_special_role(self, guild, role_name):
        role = await guild.create_role(name=role_name, color=discord.Color.gold())
        return role

    @commands.command()
    async def story(self, ctx):
        """Start a new interactive story arc"""
        user_data = await self.config.member(ctx.author).all()
        character_name = user_data['character']['name']
        story_prompt = f"Start a new One Piece adventure featuring {character_name}:"
        story_start = await self.generate_ai_response(story_prompt)
        
        message = await ctx.send(f"**New Adventure Begins**\n\n{story_start}\n\nHow do you want to proceed? React with:\n🏴‍☠️ - Act like a pirate\n⚖️ - Follow the law\n🕵️ - Investigate further")
        
        for emoji in ['🏴‍☠️', '⚖️', '🕵️']:
            await message.add_reaction(emoji)

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ['🏴‍☠️', '⚖️', '🕵️'] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("The adventure fades as you hesitate to act...")
        else:
            choice = {
                '🏴‍☠️': 'act like a pirate',
                '⚖️': 'follow the law',
                '🕵️': 'investigate further'
            }[str(reaction.emoji)]
            
            next_part = await self.generate_ai_response(f"Continue the One Piece story where {character_name} decides to {choice}:\n\n{story_start}")
            await ctx.send(f"**The Adventure Continues**\n\n{next_part}")
            self.storyline += f"\n\n{story_start}\n{next_part}"

    @commands.command()
    async def treasure_hunt(self, ctx):
        """Start a treasure hunting minigame"""
        grid_size = 5
        treasure_x, treasure_y = random.randint(0, grid_size-1), random.randint(0, grid_size-1)
        attempts = 3

        await ctx.send(f"A treasure has been hidden in a {grid_size}x{grid_size} grid! You have {attempts} attempts to find it.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        while attempts > 0:
            await ctx.send(f"Enter your guess as 'x y' (e.g., '2 3'). Attempts left: {attempts}")
            try:
                msg = await self.bot.wait_for('message', timeout=30.0, check=check)
                guess_x, guess_y = map(int, msg.content.split())
                
                if guess_x == treasure_x and guess_y == treasure_y:
                    await ctx.send("Congratulations! You found the treasure!")
                    await self.award_treasure(ctx.author)
                    return
                else:
                    attempts -= 1
                    if attempts > 0:
                        hint = self.get_treasure_hint(guess_x, guess_y, treasure_x, treasure_y)
                        await ctx.send(f"Not quite! {hint}")
                    else:
                        await ctx.send(f"Sorry, you're out of attempts. The treasure was at ({treasure_x}, {treasure_y}).")
            except (ValueError, IndexError):
                await ctx.send("Invalid input. Please enter two numbers separated by a space.")
            except asyncio.TimeoutError:
                await ctx.send("Time's up! The treasure remains hidden.")
                return

    def get_treasure_hint(self, guess_x, guess_y, treasure_x, treasure_y):
        if abs(guess_x - treasure_x) <= 1 and abs(guess_y - treasure_y) <= 1:
            return "You're very close!"
        elif guess_x == treasure_x:
            return "You've got the right X coordinate!"
        elif guess_y == treasure_y:
            return "You've got the right Y coordinate!"
        elif guess_x < treasure_x:
            return "The treasure is to the east."
        elif guess_x > treasure_x:
            return "The treasure is to the west."
        elif guess_y < treasure_y:
            return "The treasure is to the north."
        else:
            return "The treasure is to the south."

    async def award_treasure(self, user: discord.Member):
        treasure_items = ["Golden Den Den Mushi", "Ancient Poneglyph Rubbing", "Rare Devil Fruit"]
        treasure = random.choice(treasure_items)
        async with self.config.member(user).all() as user_data:
            user_data['resources']['special_items'].append(treasure)
            user_data['beris'] += 1000
        await self.update_user_role(user, 50)
        await self.update_reputation(user, "Pirates", 10)
        await user.send(f"You've been awarded a {treasure} and 1000 Beris for finding the treasure!")

    async def send_feature_reminder(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(1800)  # 30 minutes
            for guild in self.bot.guilds:
                chat_channels = await self.config.guild(guild).chat_channels()
                if chat_channels:
                    channel = self.bot.get_channel(random.choice(chat_channels))
                    if channel:
                        embed = discord.Embed(title="One Piece AI Bot Features", color=discord.Color.blue())
                        embed.add_field(name="Story", value="Start a new adventure with `.story`", inline=False)
                        embed.add_field(name="Treasure Hunt", value="Search for treasure with `.treasure_hunt`", inline=False)
                        embed.add_field(name="Profile", value="View your character profile with `.profile`", inline=False)
                        embed.add_field(name="Resources", value="Check your resources with `.resources`", inline=False)
                        embed.add_field(name="Reputation", value="View your faction reputation with `.reputation`", inline=False)
                        embed.add_field(name="Tournament", value="Join ongoing tournaments with `.join_tournament`", inline=False)
                        embed.add_field(name="Trade", value="Trade resources with `.trade`", inline=False)
                        await channel.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def check_openai_usage(self, ctx):
        """Check estimated OpenAI API usage based on token count"""
        if not self.client:
            await ctx.send("OpenAI client is not initialized.")
            return

        try:
            estimated_cost = (self.total_tokens_used / 1000) * 0.002
            guild_data = await self.config.guild(ctx.guild).all()
            daily_tokens_used = guild_data['daily_tokens_used']
            daily_limit = guild_data['daily_token_limit']

            await ctx.send(f"Estimated usage since bot start:\n"
                           f"Total tokens used: {self.total_tokens_used:,}\n"
                           f"Estimated cost: ${estimated_cost:.2f}\n"
                           f"Daily tokens used: {daily_tokens_used:,}/{daily_limit:,}")

        except Exception as e:
            await ctx.send(f"Error checking usage: {str(e)}")

async def setup(bot):
    await bot.add_cog(OnePieceAI(bot))
