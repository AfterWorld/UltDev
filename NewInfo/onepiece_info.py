import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot import __version__ as red_version
import sys
import psutil
import platform
import asyncio

old_info = None
old_ping = None

class OnePieceInfo(commands.Cog):
    """Provides One Piece themed info and ping commands."""

    def __init__(self, bot: Red):
        self.bot = bot

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
        """Shows a battle between Aokiji and Akainu with ping information"""
        start = ctx.message.created_at
        message = await ctx.send("A fierce battle is about to begin on Punk Hazard...")
        
        # Animation frames
        battle_frames = [
            "Aokiji and Akainu face each other...",
            "Aokiji: 'I won't let you pass!' Akainu: 'Stand aside, or face absolute justice!'",
            "❄️ Aokiji prepares his ice powers!",
            "🌋 Akainu's fist turns to magma!",
            "❄️➡️➡️➡️🌋 Aokiji attacks! Ice Age!",
            "💨💨💨 Steam fills the air as ice meets magma!",
            "🌋➡️➡️➡️❄️ Akainu counterattacks! Great Eruption!",
            "💥💥💥 The attacks collide in a massive explosion!",
            "The smoke clears, revealing the outcome...",
        ]
        
        for frame in battle_frames:
            await asyncio.sleep(1)
            await message.edit(content=frame)
        
        end = discord.utils.utcnow()
        ping_time = (end - start).total_seconds() * 1000
        
        # Determine the winner based on ping time
        if ping_time < 100:
            winner = "Aokiji"
            outcome = "Aokiji's ice freezes even Akainu's magma!"
        elif ping_time < 200:
            winner = "Tie"
            outcome = "Neither admiral can overcome the other. It's a draw!"
        else:
            winner = "Akainu"
            outcome = "Akainu's magma melts through Aokiji's ice!"
        
        final_message = (
            f"**Battle Outcome:** {winner} {'wins' if winner != 'Tie' else ''}\n"
            f"{outcome}\n\n"
            f"⏱️ Battle duration: **{ping_time:.2f}ms**\n"
            f"🌡️ WebSocket latency: **{round(self.bot.latency * 1000, 2)}ms**\n\n"
            "The fight on Punk Hazard rages on, changing the very nature of the island!"
        )
        
        await message.edit(content=final_message)

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
