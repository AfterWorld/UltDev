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

    import random

class OnePieceInfo(commands.Cog):
    # ... (previous methods remain unchanged)

    @commands.command()
    async def ping(self, ctx):
        """Shows a battle between Aokiji and Akainu, with the ping as the deciding factor!"""
        websocket_latency = round(self.bot.latency * 1000, 2)
        message = await ctx.send("A fierce battle is about to begin on Punk Hazard...")

        battle_frames = [
            "🌋 Akainu: 'I'll show you the power of absolute justice!' ❄️ Aokiji: 'Not if I freeze you first!'",
            "❄️ Aokiji unleashes his Ice Age! 🌋 Akainu counters with his Meteor Volcano!",
            "🌋❄️ The attacks collide, creating a massive steam cloud!",
            "💨💨💨 The steam clears, revealing the outcome...",
        ]

        for frame in battle_frames:
            await asyncio.sleep(1)
            await message.edit(content=frame)

        await asyncio.sleep(1)

        if websocket_latency < 100:
            winner = "Aokiji"
            outcome = (
                f"❄️ Aokiji's ice freezes Akainu's magma in **{websocket_latency}ms**!\n"
                "The bot's connection is as cool as Aokiji's ice powers!"
            )
        elif websocket_latency < 200:
            winner = "Tie"
            outcome = (
                f"🌫️ After **{websocket_latency}ms**, it's a draw! Punk Hazard is half frozen, half burning!\n"
                "The bot's connection is balanced, like the aftermath of their battle!"
            )
        else:
            winner = "Akainu"
            outcome = (
                f"🌋 Akainu's magma overpowers Aokiji's ice in **{websocket_latency}ms**!\n"
                "The bot's connection is as hot as Akainu's magma!"
            )

        final_message = (
            f"**Battle Outcome:** {winner} {'wins' if winner != 'Tie' else ''}\n\n"
            f"{outcome}\n\n"
            f"Websocket Latency: {websocket_latency}ms"
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
