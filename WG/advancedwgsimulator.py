import random
import asyncio
from redbot.core import commands, Config
import discord
from datetime import datetime, timedelta
from discord.ext import tasks

class AdvancedWorldGovernmentSimulator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        
        self.all_skills = [
            "diplomacy", "military", "economy", "intelligence", "science",
            "naval_tactics", "justice_enforcement", "espionage", "assassination",
            "devil_fruit_research", "weapon_development"
        ]
        
        self.mission_types = {
            "patrol": {"description": "Patrol a designated area", "duration": 4, "skill": "military"},
            "intel": {"description": "Gather intelligence on a target", "duration": 3, "skill": "intelligence"},
            "diplomacy": {"description": "Attend a diplomatic meeting", "duration": 2, "skill": "diplomacy"},
            "training": {"description": "Conduct a training exercise", "duration": 5, "skill": "military"},
            "resource": {"description": "Manage resource allocation", "duration": 1, "skill": "economy"}
        }
    
        self.positions = [
            "Recruit", "Junior Official", "Senior Official", "Department Head", 
            "Commodore", "Vice Admiral", "Admiral", "Fleet Admiral", "Gorosei Member", "Im-sama"
        ]
    
        self.faction_skills = {
            "Marines": ["naval_tactics", "justice_enforcement"],
            "Cipher Pol": ["espionage", "assassination"],
            "Science Division": ["devil_fruit_research", "weapon_development"]
        }
    
        self.devil_fruits = {
            "Logia": ["Mera Mera no Mi", "Goro Goro no Mi", "Hie Hie no Mi", "Magu Magu no Mi"],
            "Zoan": ["Ushi Ushi no Mi, Model: Giraffe", "Neko Neko no Mi, Model: Leopard", "Tori Tori no Mi, Model: Falcon"],
            "Paramecia": ["Gura Gura no Mi", "Ope Ope no Mi", "Bara Bara no Mi", "Gomu Gomu no Mi"]
        }
        
        self.devil_fruit = {
            "Mera Mera no Mi": {"type": "Logia", "description": "Allows the user to create, control, and transform into fire at will."},
            "Goro Goro no Mi": {"type": "Logia", "description": "Allows the user to create, control, and transform into electricity at will."},
            "Ope Ope no Mi": {"type": "Paramecia", "description": "Allows the user to create a sphere-like space or 'room', in which they can manipulate anything within it."},
            "Gura Gura no Mi": {"type": "Paramecia", "description": "Allows the user to create vibrations, or 'quakes'."},
            "Hito Hito no Mi, Model: Daibutsu": {"type": "Mythical Zoan", "description": "Allows the user to transform into a giant Buddha."}
        }

        self.faction_df_rules = {
            "Marines": {
                "Admiral": {"types": ["Logia"], "chance": 0.5},
                "Vice Admiral": {"types": ["Paramecia", "Zoan"], "chance": 0.3}
            },
            "Cipher Pol": {
                "Department Head": {"types": ["Zoan"], "chance": 0.4},
                "Senior Official": {"types": ["Paramecia"], "chance": 0.2}
            },
            "Science Division": {
                "Department Head": {"types": ["Paramecia"], "chance": 0.3},
                "Senior Official": {"types": ["Zoan"], "chance": 0.2}
            }
        }
        
        self.special_ops = {
            "Infiltration": {
                "description": "Infiltrate a target organization to gather intelligence.",
                "skills": ["espionage", "intelligence"],
                "difficulty": 7,
                "cooldown": timedelta(hours=12),
                "effects": {
                    "intelligence": lambda: random.randint(50, 200),
                    "revolutionary_threat": lambda: -random.randint(1, 5)
                }
            },
            "Sabotage": {
                "description": "Disrupt enemy operations through covert sabotage.",
                "skills": ["military", "intelligence"],
                "difficulty": 8,
                "cooldown": timedelta(hours=18),
                "effects": {
                    "piracy_level": lambda: -random.randint(3, 8),
                    "marine_strength": lambda: random.randint(1, 3)
                }
            },
            "Propaganda Campaign": {
                "description": "Launch a secret propaganda campaign to influence public opinion.",
                "skills": ["diplomacy", "intelligence"],
                "difficulty": 6,
                "cooldown": timedelta(hours=8),
                "effects": {
                    "civilian_approval": lambda: random.randint(2, 7),
                    "world_stability": lambda: random.randint(1, 3)
                }
            },
            "Asset Extraction": {
                "description": "Extract a valuable asset from enemy territory.",
                "skills": ["military", "espionage"],
                "difficulty": 9,
                "cooldown": timedelta(hours=24),
                "effects": {
                    "intelligence": lambda: random.randint(100, 300),
                    "marine_strength": lambda: random.randint(2, 5)
                }
            }
        }
        
        self.undercover_missions = {
            "Gather Intel": {
                "description": "Collect information on pirate activities.",
                "risk": 10,
                "reward": {"intelligence": 50},
                "exposure_increase": 5
            },
            "Sabotage Ship": {
                "description": "Damage a pirate ship to delay their operations.",
                "risk": 20,
                "reward": {"piracy_level": -3},
                "exposure_increase": 10
            },
            "Steal Treasure": {
                "description": "Steal valuable treasure for the World Government.",
                "risk": 30,
                "reward": {"budget": 10000},
                "exposure_increase": 15
            }
        }

        self.cp_training_modules = {
            "Stealth": {
                "description": "Train in the art of moving unseen.",
                "duration": timedelta(days=3),
                "skill_increase": {"espionage": 2}
            },
            "Interrogation": {
                "description": "Learn advanced interrogation techniques.",
                "duration": timedelta(days=4),
                "skill_increase": {"intelligence": 2}
            },
            "Combat": {
                "description": "Master close-quarters combat skills.",
                "duration": timedelta(days=5),
                "skill_increase": {"military": 2}
            }
        }
        
        self.mission_cooldowns = {}
        self.mission_cooldown_time = timedelta(hours=4)  # 4-hour cooldown
    
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
            "ongoing_special_ops": {},
            "current_year": 1500,
            "resources": {
                "budget": 1000000,
                "manpower": 100000,
                "intelligence": 500
            },
            "yonko": ["Kaido", "Big Mom", "Shanks", "Blackbeard"],
            "shichibukai": ["Dracule Mihawk", "Bartholomew Kuma", "Boa Hancock", "Crocodile", "Gecko Moria", "Jinbe", "Donquixote Doflamingo"],
            "current_crisis": None,
            "promotion_candidates": {},
            "factions": {
                "Marines": {
                    "strength": 100,
                    "reputation": 50,
                    "resources": {"ships": 100, "weapons": 1000}
                },
                "Cipher Pol": {
                    "strength": 50,
                    "reputation": 30,
                    "resources": {"agents": 50, "intel": 500}
                },
                "Science Division": {
                    "strength": 30,
                    "reputation": 40,
                    "resources": {"labs": 10, "research_points": 100}
                }
            },
            "faction_relations": {
                "Marines": {"Cipher Pol": 50, "Science Division": 50},
                "Cipher Pol": {"Marines": 50, "Science Division": 50},
                "Science Division": {"Marines": 50, "Cipher Pol": 50}
            }
        }
    
        default_user = {
            "position": None,
            "faction": None,
            "influence": 0,
            "allies": [],
            "enemies": [],
            "decisions": [],
            "completed_missions": [],
            "special_ops_cooldowns": {},
            "mission_history": [],
            "unlocked_missions": [],
            "unlocked_abilities": [],
            "is_undercover": False,
            "exposure_level": 0,
            "undercover_cooldown": None,
            "cp_trainees": [],
            "devil_fruit": None,
            "df_mastery": 0,
            "skills": {skill: 1 for skill in self.all_skills},
            "personal_resources": {
                "wealth": 1000,
                "connections": 10
            },
            "crisis_contributions": 0,
            "reputation": {
                "Marines": 50,
                "Cipher Pol": 50,
                "Science Division": 50,
                "Civilians": 50,
                "Pirates": 50,
                "Revolutionaries": 50
            }
        }
    
        self.config.register_guild(**default_guild)
        self.config.register_user(**default_user)
        
        self.world_events = [
            {
                "name": "Pirate Alliance Formation",
                "description": "A powerful alliance of pirate crews has formed in the New World.",
                "effects": {
                    "piracy_level": 15,
                    "marine_strength": -5,
                    "world_stability": -10
                },
                "duration": 7,  # days
                "special_missions": [
                    {
                        "name": "Disrupt Pirate Alliance",
                        "description": "Infiltrate and sabotage the newly formed pirate alliance.",
                        "required_skill": "espionage",
                        "difficulty": 9,
                        "rewards": {
                            "influence": 20,
                            "reputation": {"Pirates": -15, "Marines": 10},
                            "skill_increase": {"espionage": 1.0, "intelligence": 0.5}
                        }
                    }
                ]
            },
            {
                "name": "Revolutionary Army Uprising",
                "description": "The Revolutionary Army has incited major uprisings across multiple kingdoms.",
                "effects": {
                    "revolutionary_threat": 20,
                    "world_stability": -15,
                    "civilian_approval": -5
                },
                "duration": 10,  # days
                "special_missions": [
                    {
                        "name": "Quell Uprisings",
                        "description": "Lead a task force to suppress the uprisings and restore order.",
                        "required_skill": "military",
                        "difficulty": 10,
                        "rewards": {
                            "influence": 25,
                            "reputation": {"Revolutionaries": -20, "Civilians": -10, "Marines": 15},
                            "skill_increase": {"military": 1.2, "diplomacy": 0.6}
                        }
                    }
                ]
            },
            {
                "name": "Ancient Weapon Discovery",
                "description": "Rumors spread about the discovery of an Ancient Weapon's location.",
                "effects": {
                    "scientific_advancement": 10,
                    "world_stability": -5,
                    "piracy_level": 10
                },
                "duration": 14,  # days
                "special_missions": [
                    {
                        "name": "Secure Ancient Weapon",
                        "description": "Lead a covert operation to secure the Ancient Weapon before others can claim it.",
                        "required_skill": "intelligence",
                        "difficulty": 11,
                        "rewards": {
                            "influence": 30,
                            "reputation": {"Science Division": 20, "Pirates": -10},
                            "skill_increase": {"intelligence": 1.5, "science": 1.0}
                        }
                    }
                ]
            }
        ]
    
        self.faction_missions = {
            "Marines": [
                {
                    "name": "Basic Training",
                    "description": "Complete your basic Marine training.",
                    "required_skill": "military",
                    "difficulty": 3,
                    "prerequisites": {},
                    "rewards": {
                        "influence": 5,
                        "reputation": {"Marines": 5},
                        "skill_increase": {"military": 0.5},
                        "unlocks": {
                            "missions": ["Justice Enforcement Campaign"],
                            "abilities": ["Basic Combat Training"]
                        }
                    }
                },
                {
                    "name": "Justice Enforcement Campaign",
                    "description": "Organize a large-scale campaign to enforce justice in a lawless region.",
                    "required_skill": "justice_enforcement",
                    "difficulty": 7,
                    "prerequisites": {
                        "rank": "Commodore",
                        "skill_level": {"justice_enforcement": 3},
                        "completed_missions": ["Basic Training"]
                    },
                    "rewards": {
                        "influence": 12,
                        "reputation": {"Civilians": 8, "Pirates": -8},
                        "resource_changes": {"manpower": -2500, "budget": -40000},
                        "skill_increase": {"justice_enforcement": 0.7, "diplomacy": 0.3},
                        "unlocks": {
                            "missions": ["Buster Call Operation"],
                            "abilities": ["Advanced Justice Enforcement"]
                        }
                    }
                },
                {
                    "name": "Buster Call Operation",
                    "description": "Lead a Buster Call operation against a pirate-controlled island.",
                    "required_skill": "naval_tactics",
                    "difficulty": 8,
                    "prerequisites": {
                        "rank": "Vice Admiral",
                        "skill_level": {"naval_tactics": 5},
                        "completed_missions": ["Justice Enforcement Campaign"]
                    },
                    "rewards": {
                        "influence": 15,
                        "reputation": {"Pirates": -15, "Civilians": -10, "Marines": 10},
                        "resource_changes": {"manpower": -4000, "budget": -80000},
                        "skill_increase": {"naval_tactics": 0.8, "military": 0.4},
                        "unlocks": {
                            "abilities": ["Buster Call Authority"]
                        }
                    }
                }
            ],
            "Cipher Pol": [
                {
                    "name": "Basic Espionage",
                    "description": "Complete your basic Cipher Pol training.",
                    "required_skill": "espionage",
                    "difficulty": 3,
                    "prerequisites": {},
                    "rewards": {
                        "influence": 5,
                        "reputation": {"Cipher Pol": 5},
                        "skill_increase": {"espionage": 0.5},
                        "unlocks": {
                            "missions": ["Infiltrate Revolutionary Army"],
                            "abilities": ["Basic Stealth"]
                        }
                    }
                },
                {
                    "name": "Infiltrate Revolutionary Army",
                    "description": "Infiltrate a Revolutionary Army cell and gather critical intelligence.",
                    "required_skill": "espionage",
                    "difficulty": 9,
                    "prerequisites": {
                        "rank": "Senior Official",
                        "skill_level": {"espionage": 6},
                        "completed_missions": ["Basic Espionage"]
                    },
                    "rewards": {
                        "influence": 18,
                        "reputation": {"Revolutionaries": -18, "Pirates": -5},
                        "resource_changes": {"intelligence": 150, "budget": -70000},
                        "skill_increase": {"espionage": 0.9, "intelligence": 0.5},
                        "unlocks": {
                            "missions": ["Eliminate Threat"],
                            "abilities": ["Advanced Infiltration"]
                        }
                    }
                },
                {
                    "name": "Eliminate Threat",
                    "description": "Assassinate a high-profile target threatening World Government stability.",
                    "required_skill": "assassination",
                    "difficulty": 10,
                    "prerequisites": {
                        "rank": "Department Head",
                        "skill_level": {"assassination": 7},
                        "completed_missions": ["Infiltrate Revolutionary Army"]
                    },
                    "rewards": {
                        "influence": 20,
                        "reputation": {"Civilians": -12, "Pirates": -8},
                        "resource_changes": {"intelligence": 80, "budget": -100000},
                        "skill_increase": {"assassination": 1.0, "military": 0.4},
                        "unlocks": {
                            "abilities": ["Master Assassin"]
                        }
                    }
                }
            ],
            "Science Division": [
                {
                    "name": "Basic Research",
                    "description": "Conduct basic research for the World Government.",
                    "required_skill": "science",
                    "difficulty": 3,
                    "prerequisites": {},
                    "rewards": {
                        "influence": 5,
                        "reputation": {"Science Division": 5},
                        "skill_increase": {"science": 0.5},
                        "unlocks": {
                            "missions": ["Devil Fruit Experimentation"],
                            "abilities": ["Scientific Method"]
                        }
                    }
                },
                {
                    "name": "Devil Fruit Experimentation",
                    "description": "Conduct groundbreaking research on a newly discovered Devil Fruit.",
                    "required_skill": "devil_fruit_research",
                    "difficulty": 8,
                    "prerequisites": {
                        "rank": "Senior Official",
                        "skill_level": {"devil_fruit_research": 5},
                        "completed_missions": ["Basic Research"]
                    },
                    "rewards": {
                        "influence": 16,
                        "reputation": {"Marines": 8, "Cipher Pol": 5},
                        "resource_changes": {"budget": -120000, "scientific_advancement": 12},
                        "skill_increase": {"devil_fruit_research": 0.8, "science": 0.4},
                        "unlocks": {
                            "missions": ["Advanced Weapon Project"],
                            "abilities": ["Devil Fruit Analysis"]
                        }
                    }
                },
                {
                    "name": "Advanced Weapon Project",
                    "description": "Develop a cutting-edge weapon to combat powerful pirates and revolutionaries.",
                    "required_skill": "weapon_development",
                    "difficulty": 9,
                    "prerequisites": {
                        "rank": "Department Head",
                        "skill_level": {"weapon_development": 6},
                        "completed_missions": ["Devil Fruit Experimentation"]
                    },
                    "rewards": {
                        "influence": 18,
                        "reputation": {"Marines": 12, "Pirates": -8},
                        "resource_changes": {"budget": -150000, "scientific_advancement": 15},
                        "skill_increase": {"weapon_development": 0.9, "science": 0.5},
                        "unlocks": {
                            "abilities": ["Weapon Mastery"]
                        }
                    }
                }
            ]
        }
        
        self.resource_update.start()
        self.check_ongoing_activities.start()
        self.generate_news.start()
        self.check_daily_missions.start()
        self.crisis_check.start()
        self.promotion_cycle.start()
        self.current_world_event = None
        self.world_event_loop.start()  # Renamed from world_event_task to world_event_loop
        self.news_feed = []
        self.current_auction = None
        self.auction_schedule.start()
        self.max_news_items = 50  # Maximum number of news items to store
        
    def cog_unload(self):
        # Cancel all background tasks
        self.resource_update.cancel()
        self.check_daily_missions.cancel()
        self.auction_schedule.cancel()
        self.crisis_check.cancel()
        self.check_ongoing_activities.cancel()
        self.generate_news.cancel()
        self.promotion_cycle.cancel()
        self.world_event_loop.cancel()
        
    @tasks.loop(minutes=30)  # Run every 30 minutes
    async def check_ongoing_activities(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            wg_channel = self.bot.get_channel(guild_data['wg_channel'])
            if not wg_channel:
                continue

            # Check Cipher Pol training
            for member in guild.members:
                user_data = await self.config.user(member).all()
                if 'ongoing_training' in user_data:
                    for module, end_time in user_data['ongoing_training'].items():
                        if datetime.now() >= end_time:
                            await self.complete_cp_training(guild, member, module)
                            user_data['ongoing_training'].pop(module)
                            await self.config.user(member).set(user_data)

            # Check undercover missions
            for member in guild.members:
                user_data = await self.config.user(member).all()
                if user_data.get('is_undercover', False):
                    if user_data['exposure_level'] >= 100:
                        user_data['is_undercover'] = False
                        user_data['exposure_level'] = 0
                        user_data['undercover_cooldown'] = datetime.now() + timedelta(days=30)
                        await self.config.user(member).set(user_data)
                        await wg_channel.send(f"{member.mention}'s cover has been blown! They've been extracted and cannot go undercover again for 30 days.")

    @check_ongoing_activities.before_loop
    async def before_check_ongoing_activities(self):
        await self.bot.wait_until_ready()
        
    @tasks.loop(hours=24)
    async def world_event_loop(self):
        if self.current_world_event:
            self.current_world_event['duration'] -= 1
            if self.current_world_event['duration'] <= 0:
                await self.end_world_event()
        elif random.random() < 0.3:  # 30% chance of a new event each day
            await self.start_new_world_event()

    async def start_new_world_event(self):
        self.current_world_event = random.choice(self.world_events)
        for guild in self.bot.guilds:
            channel_id = await self.config.guild(guild).get_attr('wg_channel')()
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"**World Event: {self.current_world_event['name']}**\n{self.current_world_event['description']}")
        
        # Apply event effects
        for guild in self.bot.guilds:
            async with self.config.guild(guild).world_state() as world_state:
                for key, value in self.current_world_event['effects'].items():
                    if key in world_state:
                        world_state[key] = max(0, min(100, world_state[key] + value))

    async def end_world_event(self):
        for guild in self.bot.guilds:
            channel_id = await self.config.guild(guild).get_attr('wg_channel')()
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"The world event '{self.current_world_event['name']}' has ended.")
        
        # Revert event effects
        for guild in self.bot.guilds:
            async with self.config.guild(guild).world_state() as world_state:
                for key, value in self.current_world_event['effects'].items():
                    if key in world_state:
                        world_state[key] = max(0, min(100, world_state[key] - value))
        
        self.current_world_event = None
        
    @tasks.loop(hours=6)  # Generate news every 6 hours
    async def generate_news(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            if guild_data['wg_channel']:
                news_item = self.create_news_item(guild_data)
                self.news_feed.insert(0, news_item)
                if len(self.news_feed) > self.max_news_items:
                    self.news_feed.pop()
                
                # Notify players of breaking news
                if news_item['importance'] == 'high':
                    channel = self.bot.get_channel(guild_data['wg_channel'])
                    if channel:
                        await channel.send(f"🚨 Breaking News: {news_item['headline']}")

    def create_news_item(self, guild_data):
        world_state = guild_data['world_state']
        current_year = guild_data['current_year']
        
        news_topics = [
            {"condition": world_state['piracy_level'] > 70, "template": "Pirate activity reaches alarming levels in {region}!"},
            {"condition": world_state['revolutionary_threat'] > 60, "template": "Revolutionary Army gains support in {kingdom}"},
            {"condition": world_state['marine_strength'] < 40, "template": "Marine forces struggle to maintain order in {sea}"},
            {"condition": world_state['economy'] > 80, "template": "Economic boom in {kingdom} leads to increased World Government influence"},
            {"condition": world_state['scientific_advancement'] > 75, "template": "Breakthrough in {field} research announced by World Government scientists"},
            {"condition": True, "template": "Routine patrols in {sea} yield no significant findings"}
        ]
        
        applicable_topics = [topic for topic in news_topics if topic['condition']]
        chosen_topic = random.choice(applicable_topics)
        
        headline = chosen_topic['template'].format(
            region=random.choice(["North Blue", "East Blue", "West Blue", "South Blue", "Grand Line", "New World"]),
            kingdom=random.choice(["Alabasta", "Dressrosa", "Wano", "Germa Kingdom", "Fishman Island"]),
            sea=random.choice(["Calm Belt", "Paradise", "New World"]),
            field=random.choice(["Devil Fruit", "Weapons", "Medicine", "Navigation"])
        )
        
        return {
            "date": datetime.now(),
            "year": current_year,
            "headline": headline,
            "importance": "high" if chosen_topic['condition'] != True else "normal"
        }
        
    @tasks.loop(hours=168)  # Run weekly
    async def auction_schedule(self):
        await self.start_new_auction()

    @auction_schedule.before_loop
    async def before_auction_schedule(self):
        await self.bot.wait_until_ready()

    async def start_new_auction(self):
        if self.current_auction:
            await self.end_auction()

        devil_fruit = random.choice(list(self.devil_fruit.keys()))
        self.current_auction = {
            "devil_fruit": devil_fruit,
            "start_time": datetime.now(),
            "end_time": datetime.now() + timedelta(days=3),
            "current_bid": 50000,
            "current_bidder": None,
            "bids": []
        }

        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            channel = self.bot.get_channel(guild_data['wg_channel'])
            if channel:
                embed = discord.Embed(title="New Devil Fruit Auction!", color=discord.Color.gold())
                embed.add_field(name="Devil Fruit", value=devil_fruit, inline=False)
                embed.add_field(name="Type", value=self.devil_fruit[devil_fruit]["type"], inline=True)
                embed.add_field(name="Description", value=self.devil_fruit[devil_fruit]["description"], inline=False)
                embed.add_field(name="Starting Bid", value="50,000 Beri", inline=True)
                embed.add_field(name="Auction Ends", value=self.current_auction['end_time'].strftime("%Y-%m-%d %H:%M:%S"), inline=True)
                await channel.send(embed=embed)

    async def end_auction(self):
        if not self.current_auction:
            return

        winner = self.current_auction['current_bidder']
        if winner:
            user_data = await self.config.user(winner).all()
            user_data['devil_fruit'] = self.current_auction['devil_fruit']
            await self.config.user(winner).set(user_data)

            for guild in self.bot.guilds:
                guild_data = await self.config.guild(guild).all()
                channel = self.bot.get_channel(guild_data['wg_channel'])
                if channel:
                    await channel.send(f"The auction for {self.current_auction['devil_fruit']} has ended! {winner.mention} won with a bid of {self.current_auction['current_bid']} Beri.")
        else:
            for guild in self.bot.guilds:
                guild_data = await self.config.guild(guild).all()
                channel = self.bot.get_channel(guild_data['wg_channel'])
                if channel:
                    await channel.send(f"The auction for {self.current_auction['devil_fruit']} has ended with no bids.")

        self.current_auction = None
        
    @tasks.loop(hours=24)
    async def check_daily_missions(self):
        for guild in self.bot.guilds:
            guild_data = await self.config.guild(guild).all()
            if guild_data['wg_channel']:
                for user_id in guild_data['active_players']:
                    user_data = await self.config.user_from_id(user_id).all()
                    if 'daily_missions' in user_data:
                        user_data['daily_missions'] = {}
                        await self.config.user_from_id(user_id).set(user_data)

    @commands.command()
    async def daily_missions(self, ctx):
        """View your daily missions"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        if 'daily_missions' not in user_data or not user_data['daily_missions']:
            user_data['daily_missions'] = self.generate_daily_missions()
            await self.config.user(ctx.author).set(user_data)

        embed = discord.Embed(title="Your Daily Missions", color=discord.Color.blue())
        for mission_type, mission in user_data['daily_missions'].items():
            status = "Completed" if mission['completed'] else "Not Started"
            if mission['start_time']:
                start_time = datetime.fromisoformat(mission['start_time'])
                end_time = datetime.fromisoformat(mission['end_time'])
                time_left = end_time - datetime.now()
                if time_left > timedelta(0):
                    status = f"In Progress - {time_left.total_seconds() / 3600:.1f} hours left"
            embed.add_field(name=f"{mission_type.capitalize()} Mission", 
                            value=f"Description: {mission['description']}\nStatus: {status}", 
                            inline=False)

        await ctx.send(embed=embed)

    def generate_daily_missions(self):
        daily_missions = {}
        for _ in range(3):
            mission_type, mission_info = random.choice(list(self.mission_types.items()))
            daily_missions[mission_type] = {
                "description": mission_info["description"],
                "duration": mission_info["duration"],
                "skill": mission_info["skill"],
                "start_time": None,
                "end_time": None,
                "completed": False
            }
        return daily_missions

    @commands.command()
    async def start_mission(self, ctx, mission_type: str):
        """Start a daily mission"""
        if not await self.check_wg_channel(ctx):
            return
    
        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return
    
        if 'daily_missions' not in user_data or not user_data['daily_missions']:
            await ctx.send("You don't have any daily missions. Use `.daily_missions` to get your missions.")
            return
    
        if mission_type not in user_data['daily_missions']:
            await ctx.send(f"Invalid mission type. Choose from: {', '.join(user_data['daily_missions'].keys())}")
            return
    
        mission = user_data['daily_missions'][mission_type]
        if mission['completed']:
            await ctx.send("This mission is already completed.")
            return
    
        if mission['start_time']:
            start_time = datetime.fromisoformat(mission['start_time'])
            end_time = datetime.fromisoformat(mission['end_time'])
            time_left = end_time - datetime.now()
            if time_left > timedelta(0):
                await ctx.send(f"This mission is already in progress. It will end in {time_left.total_seconds() / 3600:.1f} hours.")
            else:
                await ctx.send("This mission has ended. Use `.complete_mission` to claim your rewards.")
            return
    
        mission['start_time'] = datetime.now().isoformat()
        mission['end_time'] = (datetime.now() + timedelta(hours=mission['duration'])).isoformat()
        await self.config.user(ctx.author).set(user_data)
    
        end_time = datetime.fromisoformat(mission['end_time'])
        await ctx.send(f"Mission '{mission_type}' started. It will end at {end_time.strftime('%Y-%m-%d %H:%M:%S')}.")
        
    @commands.command()
    async def complete_mission(self, ctx, mission_type: str):
        """Complete a daily mission and claim rewards"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        if 'daily_missions' not in user_data or not user_data['daily_missions']:
            await ctx.send("You don't have any daily missions. Use `.daily_missions` to get your missions.")
            return

        if mission_type not in user_data['daily_missions']:
            await ctx.send(f"Invalid mission type. Choose from: {', '.join(user_data['daily_missions'].keys())}")
            return

        mission = user_data['daily_missions'][mission_type]
        if mission['completed']:
            await ctx.send("This mission is already completed.")
            return

        if not mission['start_time']:
            await ctx.send("You haven't started this mission yet. Use `.start_mission` to begin.")
            return

        end_time = datetime.fromisoformat(mission['end_time'])
        time_left = end_time - datetime.now()
        if time_left > timedelta(0):
            await ctx.send(f"This mission is still in progress. It will end in {time_left.total_seconds() / 3600:.1f} hours.")
            return

        # Mission completed successfully
        mission['completed'] = True
        rewards = self.calculate_mission_rewards(mission)
        self.apply_mission_rewards(user_data, rewards)
        await self.config.user(ctx.author).set(user_data)

        embed = discord.Embed(title="Mission Completed", color=discord.Color.green())
        embed.add_field(name="Mission", value=mission['description'], inline=False)
        for reward_type, value in rewards.items():
            embed.add_field(name=reward_type.capitalize(), value=value, inline=True)

        await ctx.send(embed=embed)

    def calculate_mission_rewards(self, mission):
        base_reward = 50
        skill_increase = random.uniform(0.1, 0.5)
        influence_gain = random.randint(1, 5)

        return {
            "experience": base_reward * mission['duration'],
            f"{mission['skill']}_skill_increase": skill_increase,
            "influence": influence_gain
        }

    def apply_mission_rewards(self, user_data, rewards):
        user_data['experience'] = user_data.get('experience', 0) + rewards['experience']
        user_data['skills'][list(rewards.keys())[1].split('_')[0]] += rewards[list(rewards.keys())[1]]
        user_data['influence'] += rewards['influence']

    @commands.group(name="auction")
    async def auction(self, ctx):
        """Devil Fruit Auction commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `.help auction` to see available Devil Fruit Auction commands.")

    @auction.command(name="info")
    async def auction_info(self, ctx):
        """Get information about the current Devil Fruit auction"""
        if not self.current_auction:
            await ctx.send("There is no active Devil Fruit auction at the moment.")
            return

        embed = discord.Embed(title="Current Devil Fruit Auction", color=discord.Color.gold())
        embed.add_field(name="Devil Fruit", value=self.current_auction['devil_fruit'], inline=False)
        embed.add_field(name="Type", value=self.devil_fruit[self.current_auction['devil_fruit']]["type"], inline=True)
        embed.add_field(name="Description", value=self.devil_fruit[self.current_auction['devil_fruit']]["description"], inline=False)
        embed.add_field(name="Current Bid", value=f"{self.current_auction['current_bid']} Beri", inline=True)
        embed.add_field(name="Current Bidder", value=self.current_auction['current_bidder'].mention if self.current_auction['current_bidder'] else "No bids yet", inline=True)
        embed.add_field(name="Auction Ends", value=self.current_auction['end_time'].strftime("%Y-%m-%d %H:%M:%S"), inline=True)
        await ctx.send(embed=embed)

    @auction.command(name="bid")
    async def auction_bid(self, ctx, amount: int):
        """Place a bid on the current Devil Fruit auction"""
        if not self.current_auction:
            await ctx.send("There is no active Devil Fruit auction at the moment.")
            return

        if amount <= self.current_auction['current_bid']:
            await ctx.send(f"Your bid must be higher than the current bid of {self.current_auction['current_bid']} Beri.")
            return

        user_data = await self.config.user(ctx.author).all()
        if user_data['personal_resources']['wealth'] < amount:
            await ctx.send("You don't have enough Beri to place this bid.")
            return

        self.current_auction['current_bid'] = amount
        self.current_auction['current_bidder'] = ctx.author
        self.current_auction['bids'].append((ctx.author.id, amount))

        user_data['personal_resources']['wealth'] -= amount
        await self.config.user(ctx.author).set(user_data)

        await ctx.send(f"You have successfully bid {amount} Beri on the {self.current_auction['devil_fruit']}!")

        
    @commands.group(name="undercover")
    async def undercover(self, ctx):
        """Undercover Pirate Infiltration commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `.help undercover` to see available Undercover Pirate Infiltration commands.")

    @undercover.command(name="join")
    async def undercover_join(self, ctx):
        """Become an undercover agent within a pirate crew"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if user_data['is_undercover']:
            await ctx.send("You are already undercover!")
            return

        if user_data['undercover_cooldown'] and user_data['undercover_cooldown'] > datetime.now():
            time_left = user_data['undercover_cooldown'] - datetime.now()
            await ctx.send(f"You must wait {time_left.days} days and {time_left.seconds // 3600} hours before going undercover again.")
            return

        user_data['is_undercover'] = True
        user_data['exposure_level'] = 0
        await self.config.user(ctx.author).set(user_data)
        await ctx.send("You have successfully gone undercover within a pirate crew. Be careful not to blow your cover!")

    @undercover.command(name="mission")
    async def undercover_mission(self, ctx, *, mission_name: str):
        """Perform an undercover mission"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['is_undercover']:
            await ctx.send("You are not currently undercover. Use `.undercover join` to go undercover first.")
            return

        if mission_name not in self.undercover_missions:
            await ctx.send(f"Invalid mission. Choose from: {', '.join(self.undercover_missions.keys())}")
            return

        mission = self.undercover_missions[mission_name]
        exposure_chance = mission['risk'] + user_data['exposure_level']

        embed = discord.Embed(title=f"Undercover Mission: {mission_name}", color=discord.Color.red())
        embed.add_field(name="Description", value=mission['description'], inline=False)
        embed.add_field(name="Risk", value=f"{mission['risk']}%", inline=True)
        embed.add_field(name="Current Exposure", value=f"{user_data['exposure_level']}%", inline=True)
        embed.add_field(name="Chance of Being Exposed", value=f"{exposure_chance}%", inline=True)
        embed.add_field(name="Confirm", value="React with ✅ to start the mission or ❌ to cancel.", inline=False)

        message = await ctx.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                if random.random() * 100 < exposure_chance:
                    # Mission failed, cover blown
                    user_data['is_undercover'] = False
                    user_data['undercover_cooldown'] = datetime.now() + timedelta(days=30)
                    await self.config.user(ctx.author).set(user_data)
                    await ctx.send("Your cover has been blown! You've been extracted and cannot go undercover again for 30 days.")
                else:
                    # Mission successful
                    guild_data = await self.config.guild(ctx.guild).all()
                    for key, value in mission['reward'].items():
                        if key in guild_data['world_state']:
                            guild_data['world_state'][key] = max(0, min(100, guild_data['world_state'][key] + value))
                        elif key in guild_data['resources']:
                            guild_data['resources'][key] += value
                    await self.config.guild(ctx.guild).set(guild_data)

                    user_data['exposure_level'] += mission['exposure_increase']
                    await self.config.user(ctx.author).set(user_data)

                    await ctx.send(f"Mission successful! Reward: {', '.join([f'{k}: {v}' for k, v in mission['reward'].items()])}. Your exposure level has increased to {user_data['exposure_level']}%.")
            else:
                await ctx.send("Mission aborted.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. The mission was cancelled.")

    @undercover.command(name="extract")
    async def undercover_extract(self, ctx):
        """Extract yourself from undercover operation"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['is_undercover']:
            await ctx.send("You are not currently undercover.")
            return

        user_data['is_undercover'] = False
        user_data['exposure_level'] = 0
        user_data['undercover_cooldown'] = datetime.now() + timedelta(days=7)
        await self.config.user(ctx.author).set(user_data)
        await ctx.send("You have been successfully extracted from your undercover operation. You cannot go undercover again for 7 days.")

    @commands.group(name="cipherpoltraining")
    @commands.has_role("Cipher Pol")  # Ensure only Cipher Pol members can use these commands
    async def cipherpoltraining(self, ctx):
        """Cipher Pol Recruitment and Training commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `.help cipherpoltraining` to see available Cipher Pol Training commands.")

    @cipherpoltraining.command(name="recruit")
    async def cp_recruit(self, ctx, trainee: discord.Member):
        """Recruit a new Cipher Pol trainee"""
        if not await self.check_wg_channel(ctx):
            return

        trainer_data = await self.config.user(ctx.author).all()
        trainee_data = await self.config.user(trainee).all()

        if trainee.id in trainer_data['cp_trainees']:
            await ctx.send("This person is already your trainee.")
            return

        if len(trainer_data['cp_trainees']) >= 3:
            await ctx.send("You cannot train more than 3 recruits at a time.")
            return

        if trainee_data['faction'] != "Cipher Pol":
            await ctx.send("You can only recruit members of Cipher Pol.")
            return

        trainer_data['cp_trainees'].append(trainee.id)
        await self.config.user(ctx.author).set(trainer_data)
        await ctx.send(f"{trainee.display_name} has been recruited as your Cipher Pol trainee.")

    @cipherpoltraining.command(name="train")
    async def cp_train(self, ctx, trainee: discord.Member, *, module: str):
        """Start a training module for a Cipher Pol trainee"""
        if not await self.check_wg_channel(ctx):
            return

        trainer_data = await self.config.user(ctx.author).all()
        trainee_data = await self.config.user(trainee).all()

        if trainee.id not in trainer_data['cp_trainees']:
            await ctx.send("This person is not your trainee.")
            return

        if module not in self.cp_training_modules:
            await ctx.send(f"Invalid training module. Choose from: {', '.join(self.cp_training_modules.keys())}")
            return

        training = self.cp_training_modules[module]

        embed = discord.Embed(title=f"Cipher Pol Training: {module}", color=discord.Color.blue())
        embed.add_field(name="Description", value=training['description'], inline=False)
        embed.add_field(name="Duration", value=f"{training['duration'].days} days", inline=True)
        embed.add_field(name="Skill Increase", value=f"{next(iter(training['skill_increase'].keys()))}: +{next(iter(training['skill_increase'].values()))}", inline=True)
        embed.add_field(name="Confirm", value="React with ✅ to start the training or ❌ to cancel.", inline=False)

        message = await ctx.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                # Start the training
                end_time = datetime.now() + training['duration']
                trainee_data = await self.config.user(trainee).all()
                if 'ongoing_training' not in trainee_data:
                    trainee_data['ongoing_training'] = {}
                trainee_data['ongoing_training'][module] = end_time
                await self.config.user(trainee).set(trainee_data)
                
                await ctx.send(f"Training '{module}' has started for {trainee.display_name}. It will be completed in {training['duration'].days} days.")
            else:
                await ctx.send("Training cancelled.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. The training was cancelled.")


    async def complete_cp_training(self, guild, trainee, module):
        trainee_data = await self.config.user(trainee).all()
        training = self.cp_training_modules[module]

        # Apply skill increase
        for skill, increase in training['skill_increase'].items():
            trainee_data['skills'][skill] += increase

        await self.config.user(trainee).set(trainee_data)

        # Notify in the WG channel
        channel = self.bot.get_channel(await self.config.guild(guild).wg_channel())
        if channel:
            await channel.send(f"{trainee.mention} has completed the {module} training module. Their {next(iter(training['skill_increase'].keys()))} skill has increased by {next(iter(training['skill_increase'].values()))}.")
    
    @commands.group(name="news")
    async def news(self, ctx):
        """News commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `.help news` to see available news commands.")

    @news.command(name="latest")
    async def news_latest(self, ctx, count: int = 5):
        """View the latest news items"""
        if not await self.check_wg_channel(ctx):
            return
        
        count = min(count, len(self.news_feed))
        embed = discord.Embed(title="Latest World Government News", color=discord.Color.blue())
        
        for item in self.news_feed[:count]:
            embed.add_field(
                name=f"{item['year']} - {'🚨' if item['importance'] == 'high' else '📰'} {item['headline']}",
                value=f"Date: {item['date'].strftime('%Y-%m-%d %H:%M')}",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @news.command(name="search")
    async def news_search(self, ctx, *, keyword: str):
        """Search news items containing a specific keyword"""
        if not await self.check_wg_channel(ctx):
            return
        
        matching_news = [item for item in self.news_feed if keyword.lower() in item['headline'].lower()]
        
        if not matching_news:
            await ctx.send(f"No news items found containing '{keyword}'.")
            return
        
        embed = discord.Embed(title=f"News Search Results for '{keyword}'", color=discord.Color.green())
        
        for item in matching_news[:5]:  # Show up to 5 matching items
            embed.add_field(
                name=f"{item['year']} - {'🚨' if item['importance'] == 'high' else '📰'} {item['headline']}",
                value=f"Date: {item['date'].strftime('%Y-%m-%d %H:%M')}",
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    @commands.command()
    async def world_status(self, ctx):
        """Check the current world status and ongoing events"""
        if not await self.check_wg_channel(ctx):
            return

        world_state = await self.config.guild(ctx.guild).world_state()
        embed = discord.Embed(title="World Government Simulator - World Status", color=discord.Color.blue())
        
        for key, value in world_state.items():
            embed.add_field(name=key.replace("_", " ").title(), value=f"{value}/100", inline=True)
        
        if self.current_world_event:
            embed.add_field(name="Current World Event", value=f"{self.current_world_event['name']}\n{self.current_world_event['description']}", inline=False)
            embed.add_field(name="Event Duration", value=f"{self.current_world_event['duration']} days remaining", inline=False)
        else:
            embed.add_field(name="Current World Event", value="No active world event", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def special_mission(self, ctx):
        """Attempt a special mission related to the current world event"""
        if not await self.check_wg_channel(ctx):
            return

        if not self.current_world_event or not self.current_world_event['special_missions']:
            await ctx.send("There are no special missions available at this time.")
            return

        user_data = await self.config.user(ctx.author).all()
        mission = self.current_world_event['special_missions'][0]  # Assume one special mission per event for simplicity

        required_skill = mission['required_skill']
        skill_level = user_data['skills'].get(required_skill, 0)
        success_chance = min(90, max(10, (skill_level / mission['difficulty']) * 100))

        # Apply Devil Fruit bonus if applicable
        if user_data['devil_fruit']:
            df_bonus = user_data['df_mastery'] / 200  # Up to 50% bonus at max mastery
            success_chance = min(95, success_chance * (1 + df_bonus))

        embed = discord.Embed(title=f"Special Mission: {mission['name']}", color=discord.Color.gold())
        embed.add_field(name="Description", value=mission['description'], inline=False)
        embed.add_field(name="Required Skill", value=f"{required_skill.replace('_', ' ').title()}: {skill_level}", inline=True)
        embed.add_field(name="Difficulty", value=mission['difficulty'], inline=True)
        embed.add_field(name="Success Chance", value=f"{success_chance:.1f}%", inline=True)
        embed.add_field(name="Rewards", value="\n".join(f"{k}: {v}" for k, v in mission['rewards'].items() if k != 'skill_increase'), inline=False)
        
        message = await ctx.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                success = random.random() * 100 < success_chance
                if success:
                    await ctx.send(f"Congratulations! You successfully completed the special mission: {mission['name']}!")
                    await self.apply_mission_rewards(ctx, user_data, mission['rewards'])
                    
                    # Additional effects for completing a special mission
                    self.current_world_event['duration'] = max(0, self.current_world_event['duration'] - 2)  # Reduce event duration
                    
                    # Modify world state based on mission success
                    async with self.config.guild(ctx.guild).world_state() as world_state:
                        world_state['world_stability'] = min(100, world_state['world_stability'] + 5)
                        if 'piracy_level' in self.current_world_event['effects']:
                            world_state['piracy_level'] = max(0, world_state['piracy_level'] - 5)
                        if 'revolutionary_threat' in self.current_world_event['effects']:
                            world_state['revolutionary_threat'] = max(0, world_state['revolutionary_threat'] - 5)
                    
                    await ctx.send("Your success has had a positive impact on the world state!")
                else:
                    await ctx.send(f"Unfortunately, you failed to complete the special mission: {mission['name']}. The world event continues unabated.")
            else:
                await ctx.send("Mission aborted. The world event continues.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. The special mission opportunity has passed.")
            
    @commands.group(name="specialops")
    async def specialops(self, ctx):
        """Special Operations commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `.help specialops` to see available Special Operations commands.")

    @specialops.command(name="list")
    async def specialops_list(self, ctx):
        """List available special operations"""
        if not await self.check_wg_channel(ctx):
            return

        embed = discord.Embed(title="Available Special Operations", color=discord.Color.dark_gold())
        for op_name, op_info in self.special_ops.items():
            embed.add_field(name=op_name, value=f"Description: {op_info['description']}\nDifficulty: {op_info['difficulty']}/10\nRequired Skills: {', '.join(op_info['skills'])}", inline=False)

        await ctx.send(embed=embed)

    @specialops.command(name="start")
    async def specialops_start(self, ctx, *, operation_name: str):
        """Start a special operation"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        guild_data = await self.config.guild(ctx.guild).all()

        if operation_name not in self.special_ops:
            await ctx.send(f"Invalid operation. Use `.specialops list` to see available operations.")
            return

        operation = self.special_ops[operation_name]

        # Check cooldown
        if operation_name in user_data['special_ops_cooldowns']:
            cooldown_end = user_data['special_ops_cooldowns'][operation_name]
            if datetime.now() < cooldown_end:
                time_left = cooldown_end - datetime.now()
                await ctx.send(f"This operation is on cooldown. You can attempt it again in {time_left.total_seconds() / 3600:.1f} hours.")
                return

        # Calculate success chance
        skills_average = sum(user_data['skills'][skill] for skill in operation['skills']) / len(operation['skills'])
        success_chance = min(90, max(10, (skills_average / operation['difficulty']) * 100))

        embed = discord.Embed(title=f"Special Operation: {operation_name}", color=discord.Color.red())
        embed.add_field(name="Description", value=operation['description'], inline=False)
        embed.add_field(name="Difficulty", value=f"{operation['difficulty']}/10", inline=True)
        embed.add_field(name="Success Chance", value=f"{success_chance:.1f}%", inline=True)
        embed.add_field(name="Confirm", value="React with ✅ to start the operation or ❌ to cancel.", inline=False)

        message = await ctx.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                success = random.random() * 100 < success_chance
                if success:
                    await ctx.send(f"Operation {operation_name} successfully initiated. Results will be available in {operation['cooldown'].total_seconds() / 3600:.1f} hours.")
                    guild_data['ongoing_special_ops'][str(ctx.author.id)] = {
                        "operation": operation_name,
                        "start_time": datetime.now(),
                        "end_time": datetime.now() + operation['cooldown']
                    }
                    await self.config.guild(ctx.guild).set(guild_data)

                    # Set cooldown
                    user_data['special_ops_cooldowns'][operation_name] = datetime.now() + operation['cooldown']
                    await self.config.user(ctx.author).set(user_data)

                    # Schedule operation completion
                    await asyncio.sleep(operation['cooldown'].total_seconds())
                    await self.complete_special_operation(ctx.guild, ctx.author)
                else:
                    await ctx.send(f"The operation {operation_name} failed to initiate. Your cover was blown before the operation could begin.")
            else:
                await ctx.send("Operation cancelled.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. The operation was cancelled.")

    async def complete_special_operation(self, guild, user):
        guild_data = await self.config.guild(guild).all()
        user_data = await self.config.user(user).all()

        if str(user.id) not in guild_data['ongoing_special_ops']:
            return

        op_data = guild_data['ongoing_special_ops'].pop(str(user.id))
        operation = self.special_ops[op_data['operation']]

        # Apply effects
        effects = {}
        for key, effect_func in operation['effects'].items():
            effect_value = effect_func()
            if key in guild_data['world_state']:
                guild_data['world_state'][key] = max(0, min(100, guild_data['world_state'][key] + effect_value))
            elif key in guild_data['resources']:
                guild_data['resources'][key] += effect_value
            effects[key] = effect_value

        await self.config.guild(guild).set(guild_data)

        # Increase relevant skills
        for skill in operation['skills']:
            user_data['skills'][skill] += random.uniform(0.1, 0.3)
        await self.config.user(user).set(user_data)

        # Generate news item
        news_item = {
            "date": datetime.now(),
            "year": guild_data['current_year'],
            "headline": f"Covert operation affects {', '.join(effects.keys())}",
            "importance": "high"
        }
        self.news_feed.insert(0, news_item)
        if len(self.news_feed) > self.max_news_items:
            self.news_feed.pop()

        # Notify user
        channel = self.bot.get_channel(guild_data['wg_channel'])
        if channel:
            embed = discord.Embed(title=f"Special Operation Completed: {op_data['operation']}", color=discord.Color.green())
            for key, value in effects.items():
                embed.add_field(name=key.replace("_", " ").title(), value=f"{value:+d}", inline=True)
            await channel.send(content=f"{user.mention}, your operation is complete!", embed=embed)

    @specialops.command(name="status")
    async def specialops_status(self, ctx):
        """Check the status of your ongoing special operation"""
        if not await self.check_wg_channel(ctx):
            return

        guild_data = await self.config.guild(ctx.guild).all()
        user_op = guild_data['ongoing_special_ops'].get(str(ctx.author.id))

        if user_op:
            time_left = user_op['end_time'] - datetime.now()
            embed = discord.Embed(title="Ongoing Special Operation", color=discord.Color.blue())
            embed.add_field(name="Operation", value=user_op['operation'], inline=False)
            embed.add_field(name="Time Remaining", value=f"{time_left.total_seconds() / 3600:.1f} hours", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("You don't have any ongoing special operations.")


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
        
    @wg.command(name="check_df")
    async def wg_check_df(self, ctx):
        """Check your Devil Fruit status"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        if user_data['devil_fruit']:
            embed = discord.Embed(title="Your Devil Fruit", color=discord.Color.purple())
            embed.add_field(name="Fruit", value=user_data['devil_fruit'], inline=False)
            embed.add_field(name="Mastery", value=f"{user_data['df_mastery']}%", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("You don't have a Devil Fruit power yet.")

    async def check_for_devil_fruit(self, ctx, user_data):
        faction = user_data['faction']
        rank = user_data['position']
        
        if faction in self.faction_df_rules and rank in self.faction_df_rules[faction]:
            rule = self.faction_df_rules[faction][rank]
            if random.random() < rule['chance']:
                df_type = random.choice(rule['types'])
                devil_fruit = random.choice(self.devil_fruits[df_type])
                user_data['devil_fruit'] = devil_fruit
                user_data['df_mastery'] = 1
                await self.config.user(ctx.author).set(user_data)
                await ctx.send(f"Congratulations! You've obtained the {devil_fruit} Devil Fruit!")
                return True
        return False
    
    @wg.command(name="train_df")
    async def wg_train_df(self, ctx):
        """Train your Devil Fruit ability"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['devil_fruit']:
            await ctx.send("You don't have a Devil Fruit power to train!")
            return

        mastery_increase = random.randint(1, 5)
        user_data['df_mastery'] = min(100, user_data['df_mastery'] + mastery_increase)
        await self.config.user(ctx.author).set(user_data)
        await ctx.send(f"You've trained your {user_data['devil_fruit']} ability. Mastery increased by {mastery_increase}% to {user_data['df_mastery']}%")
        
    @wg.command(name="unlocks")
    async def wg_unlocks(self, ctx):
        """View your unlocked missions and abilities"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Unlocks", color=discord.Color.green())
        
        unlocked_missions = user_data['unlocked_missions']
        embed.add_field(name="Unlocked Missions", value="\n".join(unlocked_missions) if unlocked_missions else "None", inline=False)
        
        unlocked_abilities = user_data['unlocked_abilities']
        embed.add_field(name="Unlocked Abilities", value="\n".join(unlocked_abilities) if unlocked_abilities else "None", inline=False)

        await ctx.send(embed=embed)
        
    @wg.command(name="mission_history")
    async def wg_mission_history(self, ctx):
        """View your mission history"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        if not user_data['mission_history']:
            await ctx.send("You haven't completed any missions yet.")
            return

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Mission History", color=discord.Color.blue())
        for mission in user_data['mission_history'][-10:]:  # Show last 10 missions
            embed.add_field(
                name=f"{mission['name']} ({mission['date']})",
                value=f"Result: {'Success' if mission['success'] else 'Failure'}",
                inline=False
            )
        embed.set_footer(text=f"Total completed missions: {len(user_data['completed_missions'])}")

        await ctx.send(embed=embed)
        
    @wg.command(name="faction_missions")
    async def wg_faction_missions(self, ctx):
        """View available faction-specific missions"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        faction = user_data['faction']
        missions = self.faction_missions.get(faction, [])

        if not missions:
            await ctx.send(f"There are currently no missions available for {faction}.")
            return

        embed = discord.Embed(title=f"{faction} Missions", color=discord.Color.blue())
        for i, mission in enumerate(missions, 1):
            prerequisites_met = await self.check_mission_prerequisites(ctx.author, mission)
            status = "Available" if prerequisites_met else "Locked"
            cooldown = self.mission_cooldowns.get(f"{ctx.author.id}_{i}", None)
            if cooldown and cooldown > datetime.now():
                status = f"On cooldown until {cooldown.strftime('%Y-%m-%d %H:%M:%S')}"
            
            embed.add_field(
                name=f"{i}. {mission['name']} (Difficulty: {mission['difficulty']})",
                value=f"Description: {mission['description']}\nRequired Skill: {mission['required_skill']}\nStatus: {status}",
                inline=False
            )
            if not prerequisites_met:
                embed.add_field(
                    name="Prerequisites",
                    value=self.format_prerequisites(mission['prerequisites']),
                    inline=False
                )
        embed.set_footer(text="Use '.wg start_faction_mission <number>' to begin a mission.")

        await ctx.send(embed=embed)
    
    @wg.command(name="start_faction_mission")
    async def wg_start_faction_mission(self, ctx, mission_number: int):
        """Start a faction-specific mission"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        faction = user_data['faction']
        missions = self.faction_missions.get(faction, [])

        if not missions:
            await ctx.send(f"There are currently no missions available for {faction}.")
            return

        if mission_number < 1 or mission_number > len(missions):
            await ctx.send(f"Invalid mission number. Choose a number between 1 and {len(missions)}.")
            return

        cooldown_key = f"{ctx.author.id}_{mission_number}"
        if cooldown_key in self.mission_cooldowns and self.mission_cooldowns[cooldown_key] > datetime.now():
            time_left = self.mission_cooldowns[cooldown_key] - datetime.now()
            await ctx.send(f"This mission is on cooldown. You can attempt it again in {time_left.total_seconds() / 60:.1f} minutes.")
            return

        mission = missions[mission_number - 1]
        required_skill = mission['required_skill']
        skill_level = user_data['skills'][required_skill]
        success_chance = min(90, max(10, (skill_level / mission['difficulty']) * 100))

        # Modify success chance based on Devil Fruit
        if user_data['devil_fruit']:
            df_bonus = user_data['df_mastery'] / 200  # Up to 50% bonus at max mastery
            success_chance = min(95, success_chance * (1 + df_bonus))

        embed = discord.Embed(title=f"Mission: {mission['name']}", color=discord.Color.gold())
        embed.add_field(name="Description", value=mission['description'], inline=False)
        embed.add_field(name="Required Skill", value=f"{required_skill.replace('_', ' ').title()}: {skill_level}", inline=True)
        embed.add_field(name="Difficulty", value=mission['difficulty'], inline=True)
        embed.add_field(name="Success Chance", value=f"{success_chance:.1f}%", inline=True)
        embed.add_field(name="Rewards", value="\n".join(f"{k}: {v}" for k, v in mission['rewards'].items() if k not in ['reputation', 'skill_increase']), inline=False)
        
        message = await ctx.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                success = random.random() * 100 < success_chance
                if success:
                    await ctx.send(f"Congratulations! You successfully completed the mission: {mission['name']}!")
                    await self.apply_mission_rewards(ctx, user_data, mission['rewards'])
                    
                    # Update mission history and completed missions
                    user_data['mission_history'].append({
                        "name": mission['name'],
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "success": True
                    })
                    if mission['name'] not in user_data['completed_missions']:
                        user_data['completed_missions'].append(mission['name'])
                    
                    # Handle unlocks
                    unlocks = mission['rewards'].get('unlocks', {})
                    new_missions = unlocks.get('missions', [])
                    new_abilities = unlocks.get('abilities', [])
                    
                    user_data['unlocked_missions'].extend([m for m in new_missions if m not in user_data['unlocked_missions']])
                    user_data['unlocked_abilities'].extend([a for a in new_abilities if a not in user_data['unlocked_abilities']])
                    
                    if new_missions or new_abilities:
                        unlock_msg = "You've unlocked new content:\n"
                        if new_missions:
                            unlock_msg += f"Missions: {', '.join(new_missions)}\n"
                        if new_abilities:
                            unlock_msg += f"Abilities: {', '.join(new_abilities)}"
                        await ctx.send(unlock_msg)
                    
                    # Increase skills
                    for skill, increase in mission['rewards']['skill_increase'].items():
                        user_data['skills'][skill] += increase
                    
                    await self.config.user(ctx.author).set(user_data)
                    await ctx.send(f"Your skills have increased and the mission has been added to your history!")
                else:
                    await ctx.send(f"Unfortunately, you failed to complete the mission: {mission['name']}. Better luck next time!")
                    # Update mission history for failed missions too
                    user_data['mission_history'].append({
                        "name": mission['name'],
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "success": False
                    })
                    await self.config.user(ctx.author).set(user_data)
                
                # Set cooldown
                self.mission_cooldowns[cooldown_key] = datetime.now() + self.mission_cooldown_time
            else:
                await ctx.send("Mission aborted. You can try again later.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. The mission opportunity has passed.")
            
    async def apply_mission_rewards(self, ctx, user_data, rewards):
        guild_data = await self.config.guild(ctx.guild).all()
        
        user_data['influence'] += rewards.get('influence', 0)
        
        for group, value in rewards.get('reputation', {}).items():
            user_data['reputation'][group] = max(0, min(100, user_data['reputation'][group] + value))
        
        for resource, value in rewards.get('resource_changes', {}).items():
            guild_data['resources'][resource] = max(0, guild_data['resources'][resource] + value)
        
        await self.config.user(ctx.author).set(user_data)
        await self.config.guild(ctx.guild).set(guild_data)
        
        embed = discord.Embed(title="Mission Rewards", color=discord.Color.green())
        embed.add_field(name="Influence Gained", value=rewards.get('influence', 0), inline=False)
        if 'reputation' in rewards:
            embed.add_field(name="Reputation Changes", value="\n".join(f"{k}: {v:+d}" for k, v in rewards['reputation'].items()), inline=False)
        if 'resource_changes' in rewards:
            embed.add_field(name="Resource Changes", value="\n".join(f"{k}: {v:+d}" for k, v in rewards['resource_changes'].items()), inline=False)
        if 'skill_increase' in rewards:
            embed.add_field(name="Skill Increases", value="\n".join(f"{k.replace('_', ' ').title()}: +{v:.1f}" for k, v in rewards['skill_increase'].items()), inline=False)
        
        await ctx.send(embed=embed)
        
    async def check_mission_prerequisites(self, user, mission):
        user_data = await self.config.user(user).all()
        prerequisites = mission['prerequisites']

        # Check rank
        if 'rank' in prerequisites:
            if self.positions.index(user_data['position']) < self.positions.index(prerequisites['rank']):
                return False

        # Check skill levels
        if 'skill_level' in prerequisites:
            for skill, level in prerequisites['skill_level'].items():
                if user_data['skills'][skill] < level:
                    return False

        # Check completed missions
        if 'completed_missions' in prerequisites:
            if not all(mission in user_data['completed_missions'] for mission in prerequisites['completed_missions']):
                return False
            
        # Check if mission is unlocked
        if mission['name'] not in user_data['unlocked_missions'] and mission['name'] != "Basic Training":
            return False
        
        # Modify success chance based on Devil Fruit
        user_data = await self.config.user(ctx.author).all()
        if user_data['devil_fruit']:
            df_bonus = user_data['df_mastery'] / 200  # Up to 50% bonus at max mastery
            success_chance = min(95, success_chance * (1 + df_bonus))

        return True
            
    @wg.command(name="faction_relations")
    async def wg_faction_relations(self, ctx):
        """View the current relations between factions"""
        if not await self.check_wg_channel(ctx):
            return

        guild_data = await self.config.guild(ctx.guild).all()
        faction_relations = guild_data['faction_relations']

        embed = discord.Embed(title="Faction Relations", color=discord.Color.blue())
        for faction, relations in faction_relations.items():
            relations_str = "\n".join([f"{other_faction}: {relation}" for other_faction, relation in relations.items()])
            embed.add_field(name=faction, value=relations_str, inline=False)

        await ctx.send(embed=embed)

    @wg.command(name="join")
    async def wg_join(self, ctx, *, faction: str):
        """Join the World Government as a recruit in a specific faction"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if user_data['position']:
            await ctx.send(f"You are already a {user_data['position']} in the {user_data['faction']}!")
            return

        guild_data = await self.config.guild(ctx.guild).all()
        
        # Normalize faction input
        faction = faction.strip().title()
        
        if faction not in guild_data['factions']:
            await ctx.send(f"Invalid faction. Choose from: {', '.join(guild_data['factions'].keys())}")
            return

        user_data['position'] = "Recruit"
        user_data['faction'] = faction

        # Ensure all skills are initialized
        for skill in self.all_skills:
            if skill not in user_data['skills']:
                user_data['skills'][skill] = 1

        guild_data['active_players'][str(ctx.author.id)] = user_data
        await self.config.guild(ctx.guild).set(guild_data)
        await self.config.user(ctx.author).set(user_data)
        await ctx.send(f"Welcome to the World Government! You start as a Recruit in the {faction}. Work hard to climb the ranks.")

    @wg.command(name="skills")
    async def wg_skills(self, ctx):
        """View your current skills"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        embed = discord.Embed(title=f"{ctx.author.display_name}'s Skills", color=discord.Color.blue())
        
        # General skills
        general_skills = ["diplomacy", "military", "economy", "intelligence", "science"]
        embed.add_field(name="General Skills", value="\n".join(f"{skill.capitalize()}: {user_data['skills'][skill]}" for skill in general_skills), inline=False)
        
        # Faction-specific skills
        faction_skills = self.faction_skills[user_data['faction']]
        embed.add_field(name=f"{user_data['faction']} Skills", value="\n".join(f"{skill.replace('_', ' ').capitalize()}: {user_data['skills'][skill]}" for skill in faction_skills), inline=False)

        await ctx.send(embed=embed)

    @wg.command(name="train")
    async def wg_train(self, ctx, skill: str):
        """Train a specific skill"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        skill = skill.lower().replace(' ', '_')
        if skill not in user_data['skills']:
            await ctx.send(f"Invalid skill. Choose from: {', '.join(user_data['skills'].keys())}")
            return

        # Check if it's a faction-specific skill
        if skill in self.faction_skills[user_data['faction']]:
            increase = random.uniform(0.5, 1.5)
        else:
            increase = random.uniform(0.1, 0.5)

        user_data['skills'][skill] += increase
        await self.config.user(ctx.author).set(user_data)

        await ctx.send(f"You've trained your {skill.replace('_', ' ')} skill. It has increased by {increase:.2f} points.")

    @wg.command(name="faction")
    async def wg_faction(self, ctx):
        """View information about your faction"""
        if not await self.check_wg_channel(ctx):
            return
    
        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return
    
        guild_data = await self.config.guild(ctx.guild).all()
        faction_data = guild_data['factions'][user_data['faction']]
    
        embed = discord.Embed(title=f"{user_data['faction']} Information", color=discord.Color.blue())
        embed.add_field(name="Strength", value=faction_data['strength'], inline=True)
        embed.add_field(name="Reputation", value=faction_data['reputation'], inline=True)
        embed.add_field(name="Resources", value="\n".join(f"{k}: {v}" for k, v in faction_data['resources'].items()), inline=False)
        embed.add_field(name="Your Position", value=user_data['position'], inline=True)
        embed.add_field(name="Your Influence", value=user_data['influence'], inline=True)
    
        await ctx.send(embed=embed)

    @wg.command(name="wipe_data")
    @commands.admin()
    async def wg_wipe_data(self, ctx, user: discord.Member = None):
        """Wipe a user's World Government Simulator data. Admin only."""
        if user is None:
            user = ctx.author

        if not await self.check_wg_channel(ctx):
            return

        # Confirm action
        confirm_msg = await ctx.send(f"Are you sure you want to wipe {user.display_name}'s data? This action cannot be undone. React with ✅ to confirm or ❌ to cancel.")
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def check(reaction, reactor):
            return reactor == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id

        try:
            reaction, reactor = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                # Wipe user data
                await self.config.user(user).clear()
                
                # Remove user from active players in guild data
                async with self.config.guild(ctx.guild).active_players() as active_players:
                    active_players.pop(str(user.id), None)
                
                await ctx.send(f"{user.display_name}'s World Government Simulator data has been wiped.")
            else:
                await ctx.send("Data wipe cancelled.")
        except asyncio.TimeoutError:
            await ctx.send("No confirmation received. Data wipe cancelled.")

    @wg.command(name="reset_my_data")
    async def wg_reset_my_data(self, ctx):
        """Reset your own World Government Simulator data."""
        if not await self.check_wg_channel(ctx):
            return

        # Confirm action
        confirm_msg = await ctx.send("Are you sure you want to reset your World Government Simulator data? This action cannot be undone. React with ✅ to confirm or ❌ to cancel.")
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def check(reaction, reactor):
            return reactor == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id

        try:
            reaction, reactor = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                # Reset user data
                await self.config.user(ctx.author).clear()
                
                # Remove user from active players in guild data
                async with self.config.guild(ctx.guild).active_players() as active_players:
                    active_players.pop(str(ctx.author.id), None)
                
                await ctx.send("Your World Government Simulator data has been reset.")
            else:
                await ctx.send("Data reset cancelled.")
        except asyncio.TimeoutError:
            await ctx.send("No confirmation received. Data reset cancelled.")

    @wg.command(name="reputation")
    async def wg_reputation(self, ctx):
        """View your reputation with different groups"""
        if not await self.check_wg_channel(ctx):
            return
    
        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return
    
        embed = discord.Embed(title="Your Reputation", color=discord.Color.green())
        for group, rep in user_data['reputation'].items():
            embed.add_field(name=group, value=f"{rep}/100", inline=True)
    
        await ctx.send(embed=embed)

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
        """Make a political decision on current events"""
        if not await self.check_wg_channel(ctx):
            return

        guild_data = await self.config.guild(ctx.guild).all()
        user_data = guild_data['active_players'].get(str(ctx.author.id))
        if not user_data:
            await ctx.send("You haven't joined the World Government yet! Use `!wg join` to start.")
            return

        event = self.generate_event(user_data['position'], guild_data['world_state'])
        embed = discord.Embed(title="Political Decision", description=f"As a {user_data['position']}, you must decide:", color=discord.Color.gold())
        embed.add_field(name="Event", value=event['description'], inline=False)
        embed.add_field(name="Option A", value=event['option_a'], inline=True)
        embed.add_field(name="Option B", value=event['option_b'], inline=True)
        embed.add_field(name="How to Decide", value="React with 🅰️ for Option A or 🅱️ for Option B", inline=False)

        message = await ctx.send(embed=embed)
        await message.add_reaction("🅰️")
        await message.add_reaction("🅱️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["🅰️", "🅱️"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            choice = 'A' if str(reaction.emoji) == "🅰️" else 'B'
            
            consequences = self.calculate_event_consequences(event, choice, user_data, guild_data)
            user_data['decisions'].append({"event": event['description'], "choice": choice})
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

            result_embed = discord.Embed(title="Decision Results", color=discord.Color.blue())
            result_embed.add_field(name="Event", value=event['description'], inline=False)
            result_embed.add_field(name="Your Choice", value=f"Option {choice}: {event[f'option_{choice.lower()}']}", inline=False)
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

            # After a decision is made, potentially generate a news item
            if random.random() < 0.5:  # 50% chance to generate news from a decision
                decision_news = self.create_decision_news(event, choice, consequences)
                self.news_feed.insert(0, decision_news)
                if len(self.news_feed) > self.max_news_items:
                    self.news_feed.pop()
                
                await ctx.send(f"Your decision has made the news: {decision_news['headline']}")

            await self.check_for_promotion(ctx, user_data)

        except asyncio.TimeoutError:
            await ctx.send("You took too long to decide. The opportunity has passed.")

    def create_decision_news(self, event, choice, consequences):
        headline = f"World Government {'approves' if choice == 'A' else 'rejects'} {event['description'].lower()}"
        return {
            "date": datetime.now(),
            "year": self.config.guild(ctx.guild).current_year(),
            "headline": headline,
            "importance": "high" if abs(consequences['influence_change']) > 3 else "normal"
        }

    @wg.command(name="missions")
    async def wg_missions(self, ctx):
        """View available missions for your faction"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        faction = user_data['faction']
        missions = self.faction_missions.get(faction, [])

        if not missions:
            await ctx.send(f"There are currently no missions available for the {faction}.")
            return

        embed = discord.Embed(title=f"{faction} Missions", color=discord.Color.blue())
        for i, mission in enumerate(missions, 1):
            embed.add_field(
                name=f"{i}. {mission['name']} (Difficulty: {mission['difficulty']})",
                value=mission['description'],
                inline=False
            )
        embed.set_footer(text="Use '.wg start_mission <number>' to begin a mission.")

        await ctx.send(embed=embed)

    @wg.command(name="start_mission")
    async def wg_start_mission(self, ctx, mission_number: int):
        """Start a faction mission"""
        if not await self.check_wg_channel(ctx):
            return

        user_data = await self.config.user(ctx.author).all()
        if not user_data['faction']:
            await ctx.send("You haven't joined a faction yet! Use `.wg join <faction>` to join one.")
            return

        faction = user_data['faction']
        missions = self.faction_missions.get(faction, [])

        if not missions:
            await ctx.send(f"There are currently no missions available for the {faction}.")
            return

        if mission_number < 1 or mission_number > len(missions):
            await ctx.send(f"Invalid mission number. Choose a number between 1 and {len(missions)}.")
            return

        mission = missions[mission_number - 1]
        success_chance = min(90, max(10, (sum(user_data['skills'].values()) / mission['difficulty']) * 20))

        embed = discord.Embed(title=f"Mission: {mission['name']}", color=discord.Color.gold())
        embed.add_field(name="Description", value=mission['description'], inline=False)
        embed.add_field(name="Difficulty", value=mission['difficulty'], inline=True)
        embed.add_field(name="Success Chance", value=f"{success_chance}%", inline=True)
        embed.add_field(name="Rewards", value="\n".join(f"{k}: {v}" for k, v in mission['rewards'].items() if k != 'reputation'), inline=False)
        
        message = await ctx.send(embed=embed)
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            if str(reaction.emoji) == "✅":
                success = random.random() * 100 < success_chance
                if success:
                    await ctx.send(f"Congratulations! You successfully completed the mission: {mission['name']}!")
                    await self.apply_mission_rewards(ctx, user_data, mission['rewards'])
                else:
                    await ctx.send(f"Unfortunately, you failed to complete the mission: {mission['name']}. Better luck next time!")
            else:
                await ctx.send("Mission aborted. You can try again later.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. The mission opportunity has passed.")

    async def apply_mission_rewards(self, ctx, user_data, rewards):
        guild_data = await self.config.guild(ctx.guild).all()
        
        user_data['influence'] += rewards.get('influence', 0)
        
        for group, value in rewards.get('reputation', {}).items():
            user_data['reputation'][group] = max(0, min(100, user_data['reputation'][group] + value))
        
        if 'faction_strength' in rewards:
            guild_data['factions'][user_data['faction']]['strength'] += rewards['faction_strength']
        
        if 'faction_resources' in rewards:
            for resource, value in rewards['faction_resources'].items():
                guild_data['factions'][user_data['faction']]['resources'][resource] = guild_data['factions'][user_data['faction']]['resources'].get(resource, 0) + value
        
        if 'world_state_changes' in rewards:
            for state, value in rewards['world_state_changes'].items():
                guild_data['world_state'][state] = max(0, min(100, guild_data['world_state'][state] + value))
        
        await self.config.user(ctx.author).set(user_data)
        await self.config.guild(ctx.guild).set(guild_data)
        
        embed = discord.Embed(title="Mission Rewards", color=discord.Color.green())
        embed.add_field(name="Influence Gained", value=rewards.get('influence', 0), inline=False)
        if 'reputation' in rewards:
            embed.add_field(name="Reputation Changes", value="\n".join(f"{k}: {v:+d}" for k, v in rewards['reputation'].items()), inline=False)
        if 'faction_strength' in rewards:
            embed.add_field(name="Faction Strength Increase", value=rewards['faction_strength'], inline=False)
        if 'faction_resources' in rewards:
            embed.add_field(name="Faction Resources Gained", value="\n".join(f"{k}: {v}" for k, v in rewards['faction_resources'].items()), inline=False)
        if 'world_state_changes' in rewards:
            embed.add_field(name="World State Changes", value="\n".join(f"{k}: {v:+d}" for k, v in rewards['world_state_changes'].items()), inline=False)
        
        await ctx.send(embed=embed)

        
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

        user_data = await self.config.user(ctx.author).all()
        guild_data = await self.config.guild(ctx.guild).all()
        
        if not user_data['faction']:
            await ctx.send("You must be an active player to compete for promotion.")
            return

        if str(ctx.author.id) not in guild_data['promotion_candidates']:
            await ctx.send("You are not eligible for the current promotion cycle.")
            return

        # Include faction-specific skills in the task selection
        all_skills = ['diplomacy', 'military', 'economy', 'intelligence', 'science']
        faction_skills = self.faction_skills.get(user_data['faction'], [])
        task = random.choice(all_skills + faction_skills)
        
        await ctx.send(f"You've been assigned a {task.replace('_', ' ')} task. React with 👍 when you're ready to attempt it.")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == '👍'

        try:
            await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            success_chance = user_data['skills'][task] * 10

            # Apply Devil Fruit bonus if applicable
            if user_data['devil_fruit']:
                df_bonus = user_data['df_mastery'] / 200  # Up to 50% bonus at max mastery
                success_chance = min(95, success_chance * (1 + df_bonus))

            success = random.randint(1, 100) <= success_chance

            if success:
                guild_data['promotion_candidates'][str(ctx.author.id)] += 1
                await ctx.send(f"Task completed successfully! Your promotion score is now {guild_data['promotion_candidates'][str(ctx.author.id)]}.")
                
                # Check for Devil Fruit acquisition
                if await self.check_for_devil_fruit(ctx, user_data):
                    await ctx.send("Your successful performance has caught the attention of higher-ups!")
                
                # Increase the skill used
                skill_increase = random.uniform(0.1, 0.3)
                user_data['skills'][task] += skill_increase
                await ctx.send(f"Your {task.replace('_', ' ')} skill has increased by {skill_increase:.2f}!")
            else:
                await ctx.send("You were unable to complete the task successfully. Better luck next time!")

            await self.config.guild(ctx.guild).set(guild_data)
            await self.config.user(ctx.author).set(user_data)

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

    def generate_event(self, position, world_state):
        events = [
            {
                "description": "A powerful pirate crew has been spotted near a major trade route.",
                "option_a": "Increase Marine presence in the area",
                "option_b": "Negotiate with the pirates for safe passage",
                "required_position": "Commodore",
                "required_state": {}
            },
            {
                "description": "A kingdom is showing signs of joining the Revolutionary Army.",
                "option_a": "Send diplomats to strengthen ties",
                "option_b": "Increase surveillance and prepare for potential conflict",
                "required_position": "Vice Admiral",
                "required_state": {}
            },
            {
                "description": "A new type of Devil Fruit has been discovered.",
                "option_a": "Secure it for the World Government",
                "option_b": "Destroy it to prevent it from falling into the wrong hands",
                "required_position": "Admiral",
                "required_state": {}
            },
            {
                "description": "Increase Marine presence in the New World",
                "option_a": "Deploy additional Marine forces",
                "option_b": "Maintain current deployment levels",
                "required_position": "Vice Admiral",
                "required_state": {"piracy_level": 70}
            },
            {
                "description": "Negotiate with the Revolutionary Army",
                "option_a": "Open diplomatic channels",
                "option_b": "Refuse negotiations and prepare for conflict",
                "required_position": "Fleet Admiral",
                "required_state": {"revolutionary_threat": 80}
            },
            {
                "description": "Invest in scientific research for advanced weapons",
                "option_a": "Allocate significant funding to weapons research",
                "option_b": "Focus on other areas of scientific advancement",
                "required_position": "Department Head",
                "required_state": {"scientific_advancement": 40}
            },
            {
                "description": "Host a Reverie to address global issues",
                "option_a": "Organize a grand Reverie with all kingdom leaders",
                "option_b": "Address issues through smaller, regional meetings",
                "required_position": "Gorosei Member",
                "required_state": {"world_stability": 30}
            },
            {
                "description": "Implement stricter regulations on Devil Fruit users",
                "option_a": "Enforce new, stringent rules on Devil Fruit users",
                "option_b": "Maintain current regulations",
                "required_position": "Admiral",
                "required_state": {}
            },
            {
                "description": "Expand Cipher Pol operations in Paradise",
                "option_a": "Increase covert operations and intelligence gathering",
                "option_b": "Maintain current level of Cipher Pol activities",
                "required_position": "Fleet Admiral",
                "required_state": {"civilian_approval": 60}
            },
            {
                "description": "Allocate more resources to combating slavery",
                "option_a": "Launch a major anti-slavery campaign",
                "option_b": "Continue current efforts without additional resources",
                "required_position": "Vice Admiral",
                "required_state": {"civilian_approval": 40}
            },
            {
                "description": "Increase funding for Marine training programs",
                "option_a": "Expand and improve Marine training facilities",
                "option_b": "Maintain current training programs",
                "required_position": "Commodore",
                "required_state": {"marine_strength": 50}
            },
            {
                "description": "Propose a global tax increase to fund the World Government",
                "option_a": "Implement a new global tax structure",
                "option_b": "Find alternative funding methods",
                "required_position": "Gorosei Member",
                "required_state": {"economy": 70}
            },
            {
                "description": "Launch a propaganda campaign to improve the World Government's image",
                "option_a": "Initiate a widespread propaganda effort",
                "option_b": "Focus on concrete actions to improve public perception",
                "required_position": "Department Head",
                "required_state": {"civilian_approval": 30}
            }
        ]

        eligible_events = [
            e for e in events
            if self.positions.index(position) >= self.positions.index(e["required_position"])
            and all(world_state[k] >= v for k, v in e["required_state"].items())
        ]

        return random.choice(eligible_events) if eligible_events else {
            "description": "Handle routine administrative tasks",
            "option_a": "Focus on efficiency",
            "option_b": "Focus on thoroughness",
            "required_position": "Recruit",
            "required_state": {}
        }
        
    def calculate_event_consequences(self, event, choice, user_data, guild_data):
        consequences = {
        "influence_change": 0.0,
        "world_state_changes": {k: 0.0 for k in guild_data['world_state']},
        "resource_changes": {k: 0.0 for k in guild_data['resources']},
        "skill_changes": {k: 0.0 for k in user_data['skills']},
        "personal_resource_changes": {k: 0.0 for k in user_data['personal_resources']},
        "reputation_changes": {k: 0.0 for k in user_data['reputation']},
        "faction_changes": {
            faction: {"strength": 0.0, "reputation": 0.0, "resources": {}}
            for faction in guild_data['factions']
        },
        
        "faction_relation_changes": {
            faction: {other: 0 for other in guild_data['faction_relations'][faction]}
            for faction in guild_data['faction_relations']
        }
    }
        # Apply faction-specific skill bonuses
        faction = user_data['faction']
        if faction in self.faction_skills:
            for skill in self.faction_skills[faction]:
                skill_bonus = user_data['skills'].get(skill, 1) * 0.1
                for category in ['world_state_changes', 'resource_changes']:
                    for key in consequences[category]:
                        consequences[category][key] *= (1 + skill_bonus)

            return consequences
    
        event_effects = {
        "A powerful pirate crew has been spotted near a major trade route.": {
            "A": {
                "world_state_changes": {"piracy_level": -10.0, "marine_strength": 5.0, "civilian_approval": -2.0},
                "resource_changes": {"budget": -30000.0, "manpower": -2000.0},
                "skill_changes": {"military": 1.0}
            },
            "B": {
                "world_state_changes": {"piracy_level": 5.0, "economy": 3.0, "civilian_approval": 2.0},
                "resource_changes": {"budget": 10000.0},
                "skill_changes": {"diplomacy": 1.0}
            }
        },
        "A kingdom is showing signs of joining the Revolutionary Army.": {
            "A": {
                "world_state_changes": {"revolutionary_threat": -5.0, "world_stability": 3.0, "civilian_approval": 2.0},
                "resource_changes": {"budget": -20000.0},
                "skill_changes": {"diplomacy": 1.5}
            },
            "B": {
                "world_state_changes": {"revolutionary_threat": 5.0, "world_stability": -3.0, "marine_strength": 2.0},
                "resource_changes": {"intelligence": 100.0, "manpower": 1000.0},
                "skill_changes": {"military": 1.0, "intelligence": 0.5}
            }
        },
        "A new type of Devil Fruit has been discovered.": {
            "A": {
                "world_state_changes": {"scientific_advancement": 10.0, "marine_strength": 3.0},
                "resource_changes": {"budget": -50000.0},
                "skill_changes": {"intelligence": 1.5}
            },
            "B": {
                "world_state_changes": {"world_stability": 5.0, "civilian_approval": 3.0},
                "resource_changes": {"intelligence": 50.0},
                "skill_changes": {"diplomacy": 1.0}
            }
        },
        "A celestial dragon demands more protection during their visit to a kingdom.": {
            "A": {
                "world_state_changes": {"civilian_approval": -10.0, "world_stability": 5.0},
                "resource_changes": {"budget": -100000.0, "manpower": -5000.0},
                "skill_changes": {"diplomacy": 1.0, "military": 1.0}
            },
            "B": {
                "world_state_changes": {"civilian_approval": 5.0, "world_stability": -5.0},
                "resource_changes": {"budget": 20000.0},
                "skill_changes": {"diplomacy": 0.5}
            }
        },
        "A legendary weapon has been rumored to be hidden on a remote island.": {
            "A": {
                "world_state_changes": {"piracy_level": 10.0, "marine_strength": 5.0},
                "resource_changes": {"budget": -80000.0, "manpower": -3000.0},
                "skill_changes": {"intelligence": 2.0, "military": 1.0}
            },
            "B": {
                "world_state_changes": {"world_stability": -5.0, "revolutionary_threat": 5.0},
                "resource_changes": {"intelligence": 200.0},
                "skill_changes": {"intelligence": 1.5}
            }
        },
        "A prominent scientist offers to join the World Government's research division.": {
            "A": {
                "world_state_changes": {"scientific_advancement": 15.0, "economy": 5.0},
                "resource_changes": {"budget": -50000.0},
                "skill_changes": {"science": 2.0}
            },
            "B": {
                "world_state_changes": {"scientific_advancement": -5.0, "civilian_approval": 2.0},
                "resource_changes": {"budget": 10000.0},
                "skill_changes": {"economy": 0.5}
            }
        },
        "A major prison break has occurred at Impel Down.": {
            "A": {
                "world_state_changes": {"world_stability": -15.0, "piracy_level": 10.0, "marine_strength": 5.0},
                "resource_changes": {"budget": -200000.0, "manpower": -10000.0},
                "skill_changes": {"military": 2.0, "intelligence": 1.0}
            },
            "B": {
                "world_state_changes": {"world_stability": -5.0, "civilian_approval": -10.0},
                "resource_changes": {"intelligence": 100.0},
                "skill_changes": {"diplomacy": 1.0}
            }
        },
        "A new sea route has been discovered, potentially revolutionizing trade.": {
            "A": {
                "world_state_changes": {"economy": 10.0, "piracy_level": 5.0},
                "resource_changes": {"budget": 100000.0},
                "skill_changes": {"economy": 1.5}
            },
            "B": {
                "world_state_changes": {"economy": 5.0, "world_stability": 3.0},
                "resource_changes": {"budget": 50000.0, "intelligence": 50.0},
                "skill_changes": {"diplomacy": 1.0, "intelligence": 0.5}
            }
        },
        "A powerful Yonko is threatening to attack a World Government allied nation.": {
            "A": {
                "world_state_changes": {"world_stability": -10.0, "marine_strength": 10.0},
                "resource_changes": {"budget": -300000.0, "manpower": -15000.0},
                "skill_changes": {"military": 2.5, "diplomacy": 1.0}
            },
            "B": {
                "world_state_changes": {"world_stability": -5.0, "civilian_approval": -5.0},
                "resource_changes": {"budget": -50000.0, "intelligence": 150.0},
                "skill_changes": {"diplomacy": 2.0, "intelligence": 1.0}
            }
        }
    }
    
        if event['description'] in event_effects:
            effects = event_effects[event['description']][choice]
            for category, changes in effects.items():
                for key, value in changes.items():
                    consequences[category][key] += value
    
        # Adjust based on skills
        for category in ['world_state_changes', 'resource_changes']:
            for key in consequences[category]:
                skill_factor = user_data['skills'].get(key, 1) / 10
                consequences[category][key] *= (1 + skill_factor)
    
        # Personal resource changes
        consequences['personal_resource_changes']['wealth'] += random.randint(-100, 200)
        consequences['personal_resource_changes']['connections'] += random.randint(-2, 5)
    
        # Influence change
        consequences['influence_change'] = random.uniform(1.0, 5.0) if choice == 'A' else random.uniform(-2.0, 2.0)
    
        # Add faction-specific consequences
        faction = user_data['faction']
        if faction == "Marines":
            consequences['faction_changes'][faction]['strength'] += 2.0 if choice == 'A' else -1.0
            consequences['reputation_changes']['Civilians'] += 1.0 if choice == 'A' else -1.0
        elif faction == "Cipher Pol":
            consequences['faction_changes'][faction]['resources']['intel'] = 10 if choice == 'A' else -5
            consequences['reputation_changes']['Pirates'] -= 2.0 if choice == 'A' else 1.0
        elif faction == "Science Division":
            consequences['faction_changes'][faction]['resources']['research_points'] = 5 if choice == 'A' else -2
            consequences['world_state_changes']['scientific_advancement'] += 2.0 if choice == 'A' else -1.0
    
        for skill in self.faction_skills[faction]:
            skill_bonus = user_data['skills'][skill] * 0.1
            for category in ['world_state_changes', 'resource_changes']:
                for key in consequences[category]:
                    consequences[category][key] *= (1 + skill_bonus)

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
