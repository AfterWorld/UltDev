import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot import __version__ as red_version
import sys
import psutil
import platform
import asyncio
import time
import random

old_info = None
old_ping = None

class OnePieceInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {"aokiji_wins": 0, "akainu_wins": 0, "ties": 0}
        self.config.register_global(**default_global)

    def get_latency_description(self, latency):
        if latency < 50:
            return "As fast as Luffy's Gear 4th Snakeman!"
        elif latency < 100:
            return "Quick as Kizaru's light beams!"
        elif latency < 200:
            return "Steady as Whitebeard's earthquake punches!"
        else:
            return "Slower than Foxy's Noro Noro Beam..."

    def get_power_up(self, latency):
        if latency < 50:
            return "Ultimate Power-Up", 30
        elif latency < 100:
            return "Strong Power-Up", 20
        elif latency < 200:
            return "Moderate Power-Up", 10
        else:
            return "Weak Power-Up", 5
            
    def cog_unload(self):
        global old_info, old_ping
        if old_info:
            try:
                self.bot.remove_command("info")
            except:
                pass
            self.bot.add_command(old_info)
        if old_ping:
            try:
                self.bot.remove_command("ping")
            except:
                pass
            self.bot.add_command(old_ping)

    @commands.command()
    async def info(self, ctx):
        """Shows One Piece themed information about the One Piece Community."""
        python_version = "{}.{}.{}".format(*sys.version_info[:3])
        dpy_version = discord.__version__
        ping = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)
        max_guilds = 20  # Assuming 20 is the max slots reserved for the bot

        # Get system info
        cpu_usage = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        title = "One Piece Community"
        description = (
            "Ahoy, pirates! Welcome to our One Piece themed Discord server. "
            "I'm Sunny, the bot sailing these digital seas. I'm always on deck and ready to help whenever a nakama needs me. "
            "Now, let me tell you about my friend [Red](https://github.com/Cog-Creators/Red-DiscordBot/tree/V3/develop/redbot), the system that powers me."
        )
        embed = discord.Embed(title=title, description=description, color=discord.Color.gold())
        embed.set_thumbnail(url="https://example.com/sunny_bot_avatar.png")
        embed.add_field(
            inline=False,
            name='Bot Information',
            value=(
                "I (Sunny) am an instance of Red-DiscordBot. If you want a bot like me "
                "(because I'm as SUPER as Franky!), you can create your own by following the "
                "[Red installation docs](https://docs.discord.red/en/stable/install_guides/index.html)."
            )
        )
        embed.add_field(
            inline=False,
            name='Useful Commands',
            value='Use `!credits` and `!findcog` to view the other sources used in Sunny.'
        )
        embed.add_field(
            inline=False,
            name='Getting Sunny',
            value=(
                "You might be wondering how to get Sunny for your own server. Currently, Sunny is a private bot for this One Piece Community, "
                "but if you want to set sail with a bot like Sunny, you'll need to contact our Shipwright (server admin). Or better yet, build your own Red instance and customize it to be as SUPER as you want!"
            )
        )
        embed.add_field(
            inline=False,
            name='System Information',
            value=(
                f"Python Version: {python_version}\n"
                f"Discord.py Version: {dpy_version}\n"
                f"Red Version: {red_version}\n"
                f"Ping: {ping}ms\n"
                f"OS: {platform.system()} {platform.release()}\n"
                f"CPU Usage: {cpu_usage}%\n"
                f"Memory Usage: {memory.percent}%\n"
                f"Disk Usage: {disk.percent}%"
            )
        )
        embed.add_field(
            inline=False,
            name='Server Slots',
            value=f"Currently in {guild_count} / {max_guilds} servers"
        )
        
        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx):
        """Initiate an epic battle between Aokiji and Akainu!"""
        start = time.perf_counter()
        message = await ctx.send("The tension rises on Punk Hazard...")
        end = time.perf_counter()
        message_latency = (end - start) * 1000
        websocket_latency = round(self.bot.latency * 1000, 2)

        embed = discord.Embed(title="Battle on Punk Hazard: Aokiji vs Akainu", color=discord.Color.orange())
        embed.set_thumbnail(url="https://example.com/punk_hazard.jpg")

        aokiji_health = akainu_health = 100
        rounds = 3

        attacks = {
            "Aokiji": ["Ice Time", "Ice Block: Partisan", "Ice Age"],
            "Akainu": ["Great Eruption", "Meteor Volcano", "Hellhound"]
        }

        # Latency-based power-ups
        aokiji_power_up, aokiji_boost = self.get_power_up(websocket_latency)
        akainu_power_up, akainu_boost = self.get_power_up(message_latency)

        embed.add_field(name="Power-Ups", value=f"Aokiji: {aokiji_power_up} (+{aokiji_boost} damage)\nAkainu: {akainu_power_up} (+{akainu_boost} damage)", inline=False)

        for round in range(1, rounds + 1):
            embed.add_field(name=f"Round {round}", value="The battle rages on!", inline=False)
            
            aokiji_attack = random.choice(attacks["Aokiji"])
            akainu_attack = random.choice(attacks["Akainu"])
            
            aokiji_damage = random.randint(10, 30) + aokiji_boost
            akainu_damage = random.randint(10, 30) + akainu_boost

            akainu_health -= aokiji_damage
            aokiji_health -= akainu_damage

            embed.description = f"Aokiji uses {aokiji_attack}! ❄️➡️➡️➡️🌋\n"
            embed.description += f"Akainu counters with {akainu_attack}! 🌋➡️➡️➡️❄️\n\n"
            embed.description += f"Aokiji HP: {'█' * (aokiji_health // 10)}{aokiji_health}\n"
            embed.description += f"Akainu HP: {'█' * (akainu_health // 10)}{akainu_health}"

            await message.edit(embed=embed)
            await asyncio.sleep(2)

            # Easter egg: random character interruption (5% chance)
            if random.random() < 0.05:
                interrupting_characters = ["Garp", "Sengoku", "Blackbeard", "Shanks"]
                character = random.choice(interrupting_characters)
                embed.add_field(name="Unexpected Interruption!", value=f"Suddenly, {character} appears and temporarily halts the battle!", inline=False)
                await message.edit(embed=embed)
                await asyncio.sleep(2)

        if aokiji_health > akainu_health:
            winner = "Aokiji"
            outcome = "The azure admiral freezes his opponent solid!"
            await self.config.aokiji_wins.set(await self.config.aokiji_wins() + 1)
        elif akainu_health > aokiji_health:
            winner = "Akainu"
            outcome = "The crimson admiral's magma melts through all resistance!"
            await self.config.akainu_wins.set(await self.config.akainu_wins() + 1)
        else:
            winner = "Tie"
            outcome = "Both admirals stand at an impasse, neither willing to yield!"
            await self.config.ties.set(await self.config.ties() + 1)

        embed.add_field(name="Battle Outcome", value=f"{winner}: {outcome}", inline=False)
        
        # Themed latency descriptions
        embed.add_field(name="WebSocket Latency", value=f"{websocket_latency:.2f}ms\n{self.get_latency_description(websocket_latency)}", inline=True)
        embed.add_field(name="Message Latency", value=f"{message_latency:.2f}ms\n{self.get_latency_description(message_latency)}", inline=True)

        # Leaderboard
        stats = await self.config.all()
        embed.add_field(name="Battle Leaderboard", value=f"Aokiji Wins: {stats['aokiji_wins']}\nAkainu Wins: {stats['akainu_wins']}\nTies: {stats['ties']}", inline=False)

        # One Piece trivia
        trivia_questions = [
            "What is Aokiji's real name?",
            "What is Akainu's real name?",
            "What happened to Punk Hazard after their battle?",
            "What are Aokiji's and Akainu's Devil Fruit powers?",
            "Who became Fleet Admiral after this battle?",
            "What was the duration of Aokiji and Akainu's fight on Punk Hazard?",
            "What did Aokiji do after leaving the Marines?",
            "How did the battle on Punk Hazard affect the island's climate?",
        ]
        embed.add_field(name="One Piece Trivia", value=random.choice(trivia_questions), inline=False)

        await message.edit(embed=embed)
        
    @commands.command()
    async def credits(self, ctx):
        """Shows the credits for Sunny and the server."""
        cog = self.bot.get_cog("Downloader")
        if cog and hasattr(cog, '_repo_manager'):
            repos = cog._repo_manager.repos
            s_repos = sorted(repos, key=lambda r: str.lower(r.name))
        else:
            s_repos = []

        embed = discord.Embed(title='The Honorable CreditBoard', description="", color=discord.Color.blue())
        embed.add_field(
            inline=False,
            name='Red-DiscordBot',
            value=(
                "Sunny is powered by Red, created by [Twentysix26](https://github.com/Twentysix26) and "
                "[improved by many awesome people.](https://github.com/Cog-Creators/Red-DiscordBot/graphs/contributors)"
            )
        )

        cog_creators = [
            "**[aaa3a-cogs](https://github.com/AAA3A-AAA3A/AAA3A-cogs): aaa3a",
            "[ad-cog](https://github.com/aikaterna/gobcog.git): aikaterna",
            "[adrian](https://github.com/designbyadrian/CogsByAdrian.git): thinkadrian",
            "[blizz-cogs](https://git.purplepanda.cc/blizz/blizz-cogs): blizzthewolf",
            "[crab-cogs](https://github.com/orchidalloy/crab-cogs): hollowstrawberry",
            "[flare-cogs](https://github.com/flaree/Flare-Cogs): flare (flare#0001)",
            "[fluffycogs](https://github.com/zephyrkul/FluffyCogs): Zephyrkul (Zephyrkul#1089)",
            "[jojocogs](https://github.com/Just-Jojo/JojoCogs): Jojo#7791",
            "[jumperplugins](https://github.com/Redjumpman/Jumper-Plugins): Redjumpman (Redjumpman#1337)",
            "[laggrons-dumb-cogs](https://github.com/retke/Laggrons-Dumb-Cogs): El Laggron",
            "[lui-cogs-v3](https://github.com/Injabie3/lui-cogs-v3): Injabie3#1660, sedruk, KaguneAstra#6000, TheDarkBot#1677, quachtridat・たつ#8232",
            "[maxcogs](https://github.com/ltzmax/maxcogs): MAX",
            "[ultcogs](https://github.com/AfterWorld/ultcogs): UltPanda",
            "[npc-cogs](https://github.com/npc203/npc-cogs): epic guy#0715",
            "[pcxcogs](https://github.com/PhasecoreX/PCXCogs): PhasecoreX (PhasecoreX#0635)",
            "[seina-cogs](https://github.com/japandotorg/Seina-Cogs/): inthedark.org",
            "[sravan](https://github.com/sravan1946/sravan-cogs): sravan",
            "[toxic-cogs](https://github.com/NeuroAssassin/Toxic-Cogs): Neuro Assassin",
            "[Trusty-cogs](https://github.com/TrustyJAID/Trusty-cogs/): TrustyJAID",
            "[vrt-cogs](https://github.com/vertyco/vrt-cogs): Vertyco",
            "[yamicogs](https://github.com/yamikaitou/YamiCogs): YamiKaitou#8975**"
        ]

        # Split the cog creators list into two parts
        mid = len(cog_creators) // 2
        embed.add_field(
            inline=False,
            name='Cogs and their creators (Part 1)',
            value="\n".join(cog_creators[:mid])
        )
        embed.add_field(
            inline=False,
            name='Cogs and their creators (Part 2)',
            value="\n".join(cog_creators[mid:])
        )

        await ctx.send(embed=embed)

async def setup(bot):
    global old_info, old_ping
    old_info = bot.get_command("info")
    old_ping = bot.get_command("ping")
    if old_info:
        bot.remove_command(old_info.name)
    if old_ping:
        bot.remove_command(old_ping.name)

    cog = OnePieceInfo(bot)
    await bot.add_cog(cog)
