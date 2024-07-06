import random
import asyncio
from redbot.core import commands, Config
import discord
from discord.ext import tasks
import datetime

class AdvancedWorldGovernmentSimulator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "wg_channel": None,
            "active_players": {},
            "world_state": {
                "piracy_level": 50,
                "revolutionary_threat": 50,
                "civilian_approval": 50,
                "marine_strength": 50,
                "world_stability": 50,
                "economy": 50,
                "scientific_advancement": 50
            },
            "ongoing_events": [],
            "current_year": 1500,
            "resources": {
                "budget": 1000000,
                "manpower": 100000,
                "intelligence": 500
            },
            "yonko": ["Kaido", "Big Mom", "Shanks", "Blackbeard"],
            "shichibukai": ["Dracule Mihawk", "Bartholomew Kuma", "Boa Hancock", "Crocodile", "Gecko Moria", "Jinbe", "Donquixote Doflamingo"],
            "current_crisis": None,
            "promotion_candidates": {}
        }
        default_user = {
            "position": None,
            "influence": 0,
            "allies": [],
            "enemies": [],
            "decisions": [],
            "skills": {
                "diplomacy": 1,
                "military": 1,
                "economy": 1,
                "intelligence": 1
            },
            "personal_resources": {
                "wealth": 1000,
                "connections": 10
            },
            "crisis_contributions": 0
        }
        self.config.register_guild(**default_guild)
        self.config.register_user(**default_user)
        
        self.positions = [
            "Recruit", "Junior Official", "Senior Official", "Department Head", 
            "Commodore", "Vice Admiral", "Admiral", "Fleet Admiral", "Gorosei Member", "Im-sama"
        ]
        
        self.world_events.start()
        self.resource_update.start()
        self.crisis_check.start()
        self.promotion_cycle.start()

    def cog_unload(self):
        self.world_events.cancel()
        self.resource_update.cancel()
        self.crisis_check.cancel()
        self.promotion_cycle.cancel()

    @commands.group()
    async def wg(self, ctx):
        """World Government Simulator commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `.help wg` to see available World Government Simulator commands.")

    @wg.command(name="setup")
    @commands.admin()
    async def wg_setup(self, ctx, channel: discord.TextChannel):
        """Set up the World Government Simulator channel"""
        await self.config.guild(ctx.guild).wg_channel.set(channel.id)
        await ctx.send(f"World Government Simulator channel set to {channel.mention}")

    @wg.command(name="join")
    async def wg_join(self, ctx):
        """Join the World Government as a recruit"""
        if not await self.check_wg_channel(ctx):
            return
    
        user_data = await self.config.user(ctx.author).all()
        if user_data['position']:
            await ctx.send(f"You are already a {user_data['position']} in the World Government!")
            return
    
        user_data['position'] = "Recruit"
        guild_data = await self.config.guild(ctx.guild).all()
        guild_data['active_players'][str(ctx.author.id)] = user_data
        await self.config.guild(ctx.guild).set(guild_data)
        await self.config.user(ctx.author).set(user_data)
        await ctx.send("Welcome to the World Government! You start as a Recruit. Work hard to climb the ranks.")

    @wg.command(name="status")
    async def wg_status(self, ctx):
        """Check your status and the current world state"""
        if not await self.check_wg_channel(ctx):
            return
    
        guild_data = await self.config.guild(ctx.guild).all()
        user_data = guild_data['active_players'].get(str(ctx.author.id))
        if not user_data:
            await ctx.send("You haven't joined the World Government yet! Use `.wg join` to start.")
            return
    
        embed = discord.Embed(title="World Government Status", color=discord.Color.blue())
        embed.add_field(name="Your Position", value=user_data['position'], inline=False)
        embed.add_field(name="Influence", value=user_data['influence'], inline=False)
        embed.add_field(name="Allies", value=", ".join(user_data['allies']) if user_data['allies'] else "None", inline=False)
        embed.add_field(name="Enemies", value=", ".join(user_data['enemies']) if user_data['enemies'] else "None", inline=False)

        embed.add_field(name="Skills", value="\n".join(f"{k.title()}: {v}" for k, v in user_data['skills'].items()), inline=False)
        embed.add_field(name="Personal Resources", value="\n".join(f"{k.title()}: {v}" for k, v in user_data['personal_resources'].items()), inline=False)

        embed.add_field(name="World State", value="\n".join(f"{k.replace('_', ' ').title()}: {v}%" for k, v in guild_data['world_state'].items()), inline=False)
        embed.add_field(name="Current Year", value=guild_data['current_year'], inline=False)
        embed.add_field(name="Global Resources", value="\n".join(f"{k.title()}: {v}" for k, v in guild_data['resources'].items()), inline=False)

        await ctx.send(embed=embed)

    @wg.command(name="decide")
    async def wg_decide(self, ctx):
        """Make a political decision"""
        if not await self.check_wg_channel(ctx):
            return
    
        guild_data = await self.config.guild(ctx.guild).all()
        user_data = guild_data['active_players'].get(str(ctx.author.id))
        if not user_data:
            await ctx.send("You haven't joined the World Government yet! Use `!wg join` to start.")
            return
    
        decision = self.generate_decision(user_data['position'], guild_data['world_state'])
        embed = discord.Embed(title="Political Decision", description=f"As a {user_data['position']}, you must decide:", color=discord.Color.gold())
        embed.add_field(name="Decision", value=decision['description'], inline=False)
        embed.add_field(name="Options", value="React with 👍 to approve or 👎 to reject", inline=False)
    
        message = await ctx.send(embed=embed)
        await message.add_reaction("👍")
        await message.add_reaction("👎")
    
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["👍", "👎"] and reaction.message.id == message.id
    
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            approve = str(reaction.emoji) == "👍"
            
            consequences = self.calculate_consequences(decision, approve, user_data, guild_data)
            user_data['decisions'].append({"decision": decision['description'], "approved": approve})
            user_data['influence'] += consequences['influence_change']
    
            for key, value in consequences['world_state_changes'].items():
                guild_data['world_state'][key] = max(0, min(100, guild_data['world_state'][key] + value))
    
            for key, value in consequences['resource_changes'].items():
                guild_data['resources'][key] += value
    
            for key, value in consequences['skill_changes'].items():
                user_data['skills'][key] = max(1, user_data['skills'][key] + value)
    
            for key, value in consequences['personal_resource_changes'].items():
                user_data['personal_resources'][key] += value
    
            guild_data['active_players'][str(ctx.author.id)] = user_data
            await self.config.guild(ctx.guild).set(guild_data)
    
            result_embed = discord.Embed(title="Decision Results", color=discord.Color.green() if approve else discord.Color.red())
            result_embed.add_field(name="Decision", value=f"{'Approved' if approve else 'Rejected'}: {decision['description']}", inline=False)
            result_embed.add_field(name="Influence Change", value=f"{consequences['influence_change']:+.1f}", inline=False)
            for key, value in consequences['world_state_changes'].items():
                result_embed.add_field(name=key.replace("_", " ").title(), value=f"{value:+.1f}%", inline=True)
            for key, value in consequences['resource_changes'].items():
                result_embed.add_field(name=f"Global {key.title()}", value=f"{value:+.1f}", inline=True)
            for key, value in consequences['skill_changes'].items():
                result_embed.add_field(name=f"{key.title()} Skill", value=f"{value:+.1f}", inline=True)
            for key, value in consequences['personal_resource_changes'].items():
                result_embed.add_field(name=f"Personal {key.title()}", value=f"{value:+.1f}", inline=True)
    
            await ctx.send(embed=result_embed)
    
            await self.check_for_promotion(ctx, user_data)
    
        except asyncio.TimeoutError:
            await ctx.send("You took too long to decide. The opportunity has passed.")
        
    @commands.command()
    async def yonko(self, ctx):
        """View the current Yonko"""
        if not await self.check_wg_channel(ctx):
            return
    
        guild_data = await self.config.guild(ctx.guild).all()
        yonko = guild_data['yonko']
        
        embed = discord.Embed(title="Current Yonko", color=discord.Color.red())
        for i, emperor in enumerate(yonko, 1):
            embed.add_field(name=f"Emperor {i}", value=emperor, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    async def shichibukai(self, ctx):
        """View and manage the Shichibukai"""
        if not await self.check_wg_channel(ctx):
            return

        guild_data = await self.config.guild(ctx.guild).all()
        user_data = guild_data['active_players'].get(str(ctx.author.id))
        
        if not user_data or self.positions.index(user_data['position']) < self.positions.index('Fleet Admiral'):
            await ctx.send("You don't have the authority to manage the Shichibukai.")
            return

        shichibukai = guild_data['shichibukai']
        
        embed = discord.Embed(title="Current Shichibukai", color=discord.Color.gold())
        for i, warlord in enumerate(shichibukai, 1):
            embed.add_field(name=f"Warlord {i}", value=warlord, inline=False)
        
        await ctx.send(embed=embed)
        
        await ctx.send("Do you want to add or remove a Shichibukai? (add/remove/no)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['add', 'remove', 'no']

        try:
            action = await self.bot.wait_for('message', timeout=30.0, check=check)
            if action.content.lower() == 'add':
                await ctx.send("Enter the name of the new Shichibukai:")
                new_warlord = await self.bot.wait_for('message', timeout=30.0, check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                guild_data['shichibukai'].append(new_warlord.content)
                await ctx.send(f"{new_warlord.content} has been added to the Shichibukai!")
            elif action.content.lower() == 'remove':
                await ctx.send("Enter the name of the Shichibukai to remove:")
                removed_warlord = await self.bot.wait_for('message', timeout=30.0, check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                if removed_warlord.content in guild_data['shichibukai']:
                    guild_data['shichibukai'].remove(removed_warlord.content)
                    await ctx.send(f"{removed_warlord.content} has been removed from the Shichibukai!")
                else:
                    await ctx.send("That person is not a current Shichibukai.")
            else:
                await ctx.send("No changes made to the Shichibukai.")
            
            await self.config.guild(ctx.guild).set(guild_data)
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. No changes made to the Shichibukai.")

    @commands.command()
    async def crisis(self, ctx):
        """View current crisis and contribute to its resolution"""
        if not await self.check_wg_channel(ctx):
            return

        guild_data = await self.config.guild(ctx.guild).all()
        user_data = guild_data['active_players'].get(str(ctx.author.id))
        
        if not user_data:
            await ctx.send("You must be an active player to participate in crisis resolution.")
            return

        current_crisis = guild_data['current_crisis']
        if not current_crisis:
            await ctx.send("There is no ongoing crisis at the moment.")
            return

        embed = discord.Embed(title="Current Crisis", description=current_crisis['description'], color=discord.Color.dark_red())
        embed.add_field(name="Required Actions", value=current_crisis['required_actions'], inline=False)
        
        time_left = current_crisis['time_limit'] - (datetime.datetime.now() - current_crisis['start_time']).total_seconds() / 3600
        embed.add_field(name="Time Remaining", value=f"{time_left:.1f} hours", inline=False)
        
        await ctx.send(embed=embed)
        
        await ctx.send("Do you want to contribute to resolving this crisis? (yes/no)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['yes', 'no']

        try:
            response = await self.bot.wait_for('message', timeout=30.0, check=check)
            if response.content.lower() == 'yes':
                contribution = self.calculate_crisis_contribution(user_data)
                current_crisis['participants'][str(ctx.author.id)] = contribution
                user_data['crisis_contributions'] += contribution
                guild_data['active_players'][str(ctx.author.id)] = user_data
                await self.config.guild(ctx.guild).set(guild_data)
                
                await ctx.send(f"You've contributed {contribution} points towards resolving this crisis!")
                
                if sum(current_crisis['participants'].values()) >= current_crisis['difficulty'] * 100:
                    await self.resolve_crisis(ctx.guild)
            else:
                await ctx.send("You've chosen not to contribute to this crisis.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. No contribution made to the crisis.")

    @commands.command()
    async def compete(self, ctx):
        """Compete in the current promotion cycle"""
        if not await self.check_wg_channel(ctx):
            return

        guild_data = await self.config.guild(ctx.guild).all()
        user_data = guild_data['active_players'].get(str(ctx.author.id))
        
        if not user_data:
            await ctx.send("You must be an active player to compete for promotion.")
            return

        if str(ctx.author.id) not in guild_data['promotion_candidates']:
            await ctx.send("You are not eligible for the current promotion cycle.")
            return

        task = random.choice(['diplomatic', 'military', 'economic', 'intelligence'])
        await ctx.send(f"You've been assigned a {task} task. React with 👍 when you're ready to attempt it.")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == '👍'

        try:
            await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            success_chance = user_data['skills'][task] * 10
            success = random.randint(1, 100) <= success_chance

            if success:
                guild_data['promotion_candidates'][str(ctx.author.id)] += 1
                await ctx.send(f"Task completed successfully! Your promotion score is now {guild_data['promotion_candidates'][str(ctx.author.id)]}.")
            else:
                await ctx.send("You were unable to complete the task successfully. Better luck next time!")

            await self.config.guild(ctx.guild).set(guild_data)

        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. The task opportunity has passed.")

    @commands.command()
    async def topboard(self, ctx):
        """View the leaderboard of World Government officials"""
        if not await self.check_wg_channel(ctx):
            return

        guild_data = await self.config.guild(ctx.guild).all()
        
        leaderboard = sorted(
            guild_data['active_players'].items(),
            key=lambda x: (self.positions.index(x[1]['position']), x[1]['influence']),
            reverse=True
        )

        embed = discord.Embed(title="World Government Leaderboard", color=discord.Color.gold())
        
        for i, (user_id, data) in enumerate(leaderboard[:10], 1):
            user = ctx.guild.get_member(int(user_id))
            if user:
                embed.add_field(
                    name=f"{i}. {user.name}",
                    value=f"Position: {data['position']}\nInfluence: {data['influence']}",
                    inline=False
                )

        await ctx.send(embed=embed)

    def generate_decision(self, position, world_state):
        decisions = [
            {
                "description": "Increase Marine presence in the New World",
                "required_position": "Vice Admiral",
                "required_state": {"piracy_level": 70}
            },
            {
                "description": "Negotiate with the Revolutionary Army",
                "required_position": "Fleet Admiral",
                "required_state": {"revolutionary_threat": 80}
            },
            {
                "description": "Invest in scientific research for advanced weapons",
                "required_position": "Department Head",
                "required_state": {"scientific_advancement": 40}
            },
            {
                "description": "Host a Reverie to address global issues",
                "required_position": "Gorosei Member",
                "required_state": {"world_stability": 30}
            },
            {
                "description": "Implement stricter regulations on Devil Fruit users",
                "required_position": "Admiral",
                "required_state": {}
            },
            {
                "description": "Expand Cipher Pol operations in Paradise",
                "required_position": "Fleet Admiral",
                "required_state": {"civilian_approval": 60}
            },
            {
                "description": "Allocate more resources to combating slavery",
                "required_position": "Vice Admiral",
                "required_state": {"civilian_approval": 40}
            },
            {
                "description": "Increase funding for Marine training programs",
                "required_position": "Commodore",
                "required_state": {"marine_strength": 50}
            },
            {
                "description": "Propose a global tax increase to fund the World Government",
                "required_position": "Gorosei Member",
                "required_state": {"economy": 70}
            },
            {
                "description": "Launch a propaganda campaign to improve the World Government's image",
                "required_position": "Department Head",
                "required_state": {"civilian_approval": 30}
            }
        ]

        eligible_decisions = [
            d for d in decisions
            if self.positions.index(position) >= self.positions.index(d["required_position"])
            and all(world_state[k] >= v for k, v in d["required_state"].items())
        ]

        return random.choice(eligible_decisions) if eligible_decisions else {"description": "Handle routine administrative tasks", "required_position": "Recruit", "required_state": {}}

    def calculate_consequences(self, decision, approve, user_data, guild_data):
        base_influence = 5.0 if approve else -2.0
        consequences = {
            "influence_change": base_influence + random.uniform(-2.0, 2.0),
            "world_state_changes": {k: 0.0 for k in guild_data['world_state']},
            "resource_changes": {k: 0.0 for k in guild_data['resources']},
            "skill_changes": {k: 0.0 for k in user_data['skills']},
            "personal_resource_changes": {k: 0.0 for k in user_data['personal_resources']}
        }

        decision_effects = {
            "Increase Marine presence in the New World": {
                "world_state_changes": {"piracy_level": -10, "marine_strength": 5, "civilian_approval": -5},
                "resource_changes": {"budget": -50000, "manpower": -5000},
                "skill_changes": {"military": 1}
            },
            "Negotiate with the Revolutionary Army": {
                "world_state_changes": {"revolutionary_threat": -15, "world_stability": 10, "civilian_approval": 5},
                "resource_changes": {"intelligence": 50},
                "skill_changes": {"diplomacy": 2}
            },
            "Invest in scientific research for advanced weapons": {
                "world_state_changes": {"scientific_advancement": 15, "marine_strength": 5},
                "resource_changes": {"budget": -100000},
                "skill_changes": {"intelligence": 1}
            },
            "Host a Reverie to address global issues": {
                "world_state_changes": {"world_stability": 20, "civilian_approval": 10},
                "resource_changes": {"budget": -200000},
                "skill_changes": {"diplomacy": 2}
            },
            "Implement stricter regulations on Devil Fruit users": {
                "world_state_changes": {"world_stability": 5, "civilian_approval": -10},
                "resource_changes": {"intelligence": 100},
                "skill_changes": {"military": 1}
            },
            "Expand Cipher Pol operations in Paradise": {
                "world_state_changes": {"revolutionary_threat": -5, "civilian_approval": -5},
                "resource_changes": {"budget": -50000, "intelligence": 200},
                "skill_changes": {"intelligence": 2}
            },
            "Allocate more resources to combating slavery": {
                "world_state_changes": {"civilian_approval": 15, "economy": -5},
                "resource_changes": {"budget": -100000, "manpower": -2000},
                "skill_changes": {"diplomacy": 1}
            },
            "Increase funding for Marine training programs": {
                "world_state_changes": {"marine_strength": 10},
                "resource_changes": {"budget": -75000, "manpower": 1000},
                "skill_changes": {"military": 1}
            },
            "Propose a global tax increase to fund the World Government": {
                "world_state_changes": {"civilian_approval": -15, "economy": 10},
                "resource_changes": {"budget": 300000},
                "skill_changes": {"economy": 2}
            },
            "Launch a propaganda campaign to improve the World Government's image": {
                "world_state_changes": {"civilian_approval": 10, "revolutionary_threat": -5},
                "resource_changes": {"budget": -50000},
                "skill_changes": {"diplomacy": 1}
            }
        }

        if decision['description'] in decision_effects:
            effects = decision_effects[decision['description']]
            for category, changes in effects.items():
                for key, value in changes.items():
                    consequences[category][key] += value if approve else -value

        # Adjust based on skills
        for category in ['world_state_changes', 'resource_changes']:
            for key in consequences[category]:
                skill_factor = user_data['skills'].get(key, 1) / 10
                consequences[category][key] *= (1 + skill_factor)

        # Personal resource changes
        consequences['personal_resource_changes']['wealth'] += random.randint(-100, 200)
        consequences['personal_resource_changes']['connections'] += random.randint(-2, 5)

        return consequences

    def calculate_crisis_contribution(self, user_data):
        base_contribution = sum(user_data['skills'].values()) * 5
        position_factor = self.positions.index(user_data['position']) + 1
        return base_contribution * position_factor

    @tasks.loop(hours=24)
    async def world_events(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            if guild_data['wg_channel']:
                channel = self.bot.get_channel(guild_data['wg_channel'])
                if channel:
                    event = self.generate_world_event(guild_data['world_state'])
                    guild_data['ongoing_events'].append(event)
                    guild_data['current_year'] += 1
                    await self.config.guild(guild).set(guild_data)
                    
                    embed = discord.Embed(title="World Event", description=event['description'], color=discord.Color.red())
                    for key, value in event['effects'].items():
                        embed.add_field(name=key.replace("_", " ").title(), value=f"{value:+d}%", inline=True)
                    
                    await channel.send(embed=embed)

    def generate_world_event(self, world_state):
        events = [
            {
                "description": "A powerful pirate crew has emerged in the New World!",
                "effects": {"piracy_level": 10, "marine_strength": -5}
            },
            {
                "description": "The Revolutionary Army has liberated a kingdom from tyrannical rule!",
                "effects": {"revolutionary_threat": 15, "civilian_approval": 5, "world_stability": -10}
            },
            {
                "description": "A new breakthrough in Devil Fruit research has been made!",
                "effects": {"scientific_advancement": 20, "economy": 5}
            },
            {
                "description": "A Celestial Dragon has been attacked by pirates!",
                "effects": {"world_stability": -15, "marine_strength": 5, "civilian_approval": 10}
            },
            {
                "description": "A devastating natural disaster has struck multiple islands!",
                "effects": {"economy": -10, "civilian_approval": -5, "world_stability": -5}
            }
        ]
        
        event = random.choice(events)
        for key in event['effects']:
            event['effects'][key] = max(-20, min(20, event['effects'][key] + random.randint(-5, 5)))
        
        return event

    @tasks.loop(hours=1)
    async def resource_update(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            if guild_data['wg_channel']:
                guild_data['resources']['budget'] += 10000
                guild_data['resources']['manpower'] += 100
                guild_data['resources']['intelligence'] += 5
                await self.config.guild(guild).set(guild_data)

    @tasks.loop(hours=24)
    async def crisis_check(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            if guild_data['wg_channel'] and not guild_data['current_crisis']:
                if random.random() < 0.2:  # 20% chance of a crisis each day
                    crisis = self.generate_crisis(guild_data)
                    guild_data['current_crisis'] = crisis
                    await self.config.guild(guild).set(guild_data)
                    
                    channel = self.bot.get_channel(guild_data['wg_channel'])
                    if channel:
                        embed = discord.Embed(title="Global Crisis!", description=crisis['description'], color=discord.Color.dark_red())
                        embed.add_field(name="Required Actions", value=crisis['required_actions'], inline=False)
                        embed.add_field(name="Time Limit", value=f"{crisis['time_limit']} hours", inline=False)
                        await channel.send(embed=embed)

    def generate_crisis(self, guild_data):
        crises = [
            {
                "description": "A Yonko alliance is threatening to overtake a major kingdom!",
                "required_actions": "Mobilize Marines, negotiate with kingdom, gather intelligence",
                "time_limit": 48,
                "difficulty": 8
            },
            {
                "description": "An Ancient Weapon has been awakened and is causing chaos!",
                "required_actions": "Research weapon weaknesses, evacuate civilians, coordinate military response",
                "time_limit": 72,
                "difficulty": 9
            },
            {
                "description": "Multiple high-security prisoners have escaped from Impel Down!",
                "required_actions": "Track escapees, reinforce prison security, alert Marine bases",
                "time_limit": 36,
                "difficulty": 7
            },
            {
                "description": "A Celestial Dragon has been kidnapped by revolutionaries!",
                "required_actions": "Negotiate with kidnappers, prepare rescue operation, manage public relations",
                "time_limit": 24,
                "difficulty": 6
            }
        ]
        
        crisis = random.choice(crises)
        crisis['start_time'] = datetime.datetime.now()
        crisis['participants'] = {}
        return crisis

    async def resolve_crisis(self, guild):
        guild_data = await self.config.guild(guild).all()
        crisis = guild_data['current_crisis']
        
        channel = self.bot.get_channel(guild_data['wg_channel'])
        if channel:
            embed = discord.Embed(title="Crisis Resolved!", description=f"The {crisis['description']} has been successfully resolved!", color=discord.Color.green())
            
            top_contributors = sorted(crisis['participants'].items(), key=lambda x: x[1], reverse=True)[:3]
            for i, (user_id, contribution) in enumerate(top_contributors, 1):
                user = guild.get_member(int(user_id))
                if user:
                    embed.add_field(name=f"Top Contributor #{i}", value=f"{user.name}: {contribution} points", inline=False)
            
            await channel.send(embed=embed)
        
        guild_data['current_crisis'] = None
        await self.config.guild(guild).set(guild_data)

    @tasks.loop(hours=168)  # Weekly
    async def promotion_cycle(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            if guild_data['wg_channel']:
                await self.start_promotion_cycle(guild)

    async def start_promotion_cycle(self, guild):
        guild_data = await self.config.guild(guild).all()
        channel = self.bot.get_channel(guild_data['wg_channel'])
        
        if not channel:
            return

        positions_with_openings = [pos for pos in self.positions[1:] if pos not in [p['position'] for p in guild_data['active_players'].values()]]
        
        if not positions_with_openings:
            await channel.send("There are currently no positions available for promotion.")
            return

        position = random.choice(positions_with_openings)
        eligible_candidates = [
            (user_id, data) for user_id, data in guild_data['active_players'].items()
            if self.positions.index(data['position']) == self.positions.index(position) - 1
        ]

        if not eligible_candidates:
            await channel.send(f"No eligible candidates for promotion to {position}.")
            return

        guild_data['promotion_candidates'] = {user_id: 0 for user_id, _ in eligible_candidates}
        await self.config.guild(guild).set(guild_data)

        embed = discord.Embed(title="Promotion Cycle", description=f"A position for {position} has opened up!", color=discord.Color.blue())
        embed.add_field(name="Eligible Candidates", value="\n".join([f"<@{user_id}>" for user_id, _ in eligible_candidates]), inline=False)
        embed.add_field(name="How to Participate", value="Use `.compete` to participate in the promotion cycle. The cycle will last for 7 days.", inline=False)
        
        await channel.send(embed=embed)

    @tasks.loop(hours=168)  # Weekly
    async def end_promotion_cycle(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            if guild_data['wg_channel'] and guild_data['promotion_candidates']:
                await self.conclude_promotion(guild)

    async def conclude_promotion(self, guild):
        guild_data = await self.config.guild(guild).all()
        channel = self.bot.get_channel(guild_data['wg_channel'])
        
        if not channel:
            return

        if not guild_data['promotion_candidates']:
            await channel.send("The promotion cycle has ended, but there were no participants.")
            return

        winner_id = max(guild_data['promotion_candidates'], key=guild_data['promotion_candidates'].get)
        winner_data = guild_data['active_players'][winner_id]
        new_position = self.positions[self.positions.index(winner_data['position']) + 1]

        winner_data['position'] = new_position
        guild_data['active_players'][winner_id] = winner_data

        embed = discord.Embed(title="Promotion Cycle Concluded", color=discord.Color.green())
        embed.add_field(name="Winner", value=f"<@{winner_id}>", inline=False)
        embed.add_field(name="New Position", value=new_position, inline=False)
        embed.add_field(name="Promotion Score", value=guild_data['promotion_candidates'][winner_id], inline=False)

        await channel.send(embed=embed)

        guild_data['promotion_candidates'] = {}
        await self.config.guild(guild).set(guild_data)

    async def check_for_promotion(self, ctx, user_data):
        current_position = user_data['position']
        current_index = self.positions.index(current_position)

        if user_data['influence'] >= (current_index + 1) * 50 and current_index < len(self.positions) - 1:
            new_position = self.positions[current_index + 1]
            user_data['position'] = new_position
            guild_data = await self.config.guild(ctx.guild).all()
            guild_data['active_players'][str(ctx.author.id)] = user_data
            await self.config.guild(ctx.guild).set(guild_data)
            await ctx.send(f"Congratulations! You've been promoted to {new_position}!")

    async def check_wg_channel(self, ctx):
        guild_data = await self.config.guild(ctx.guild).all()
        if not guild_data['wg_channel']:
            await ctx.send("The World Government Simulator channel has not been set up yet. An admin needs to use `.wg setup` first.")
            return False
        if ctx.channel.id != guild_data['wg_channel']:
            wg_channel = self.bot.get_channel(guild_data['wg_channel'])
            await ctx.send(f"This command can only be used in the designated World Government Simulator channel: {wg_channel.mention}")
            return False
        return True

def setup(bot):
    bot.add_cog(AdvancedWorldGovernmentSimulator(bot))
