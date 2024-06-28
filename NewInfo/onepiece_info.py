import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot import __version__ as red_version
import sys

class OnePieceInfo(commands.Cog):
    """Provides a One Piece themed info command."""

    def __init__(self, bot: Red):
        self.bot = bot

    @commands.command()
    async def onepiece_info(self, ctx):
        """Shows One Piece themed information about the One Piece Community."""
        python_version = "{}.{}.{}".format(*sys.version_info[:3])
        dpy_version = discord.__version__
        ping = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)
        max_guilds = 20  # Assuming 20 is the max slots reserved for the bot

        title = "🏴‍☠️ One Piece Community 🌊"
        description = (
            "Ahoy, pirates! Welcome to our One Piece themed Discord server. "
            "I'm Sunny, the bot sailing these digital seas. I'm always on deck and ready to help whenever a nakama needs me. "
            "Now, let me tell you about my friend [Red](https://github.com/Cog-Creators/Red-DiscordBot/tree/V3/develop/redbot), the system that powers me."
        )
        embed = discord.Embed(title=title, description=description)
        embed.set_thumbnail(url="https://example.com/sunny_bot_avatar.png")
        embed.add_field(
            inline=False,
            name='Bot Information 🌞',
            value=(
                "I (Sunny 🌞) am an instance of Red-DiscordBot. If you want a bot like me "
                "(because I'm as SUPER as Franky!), you can create your own by following the "
                "[Red installation docs](https://docs.discord.red/en/stable/install_guides/index.html)."
            )
        )
        embed.add_field(
            inline=False,
            name='Useful Commands 🛠️',
            value='Use `!credits` and `!findcog` to view the other sources used in Sunny.'
        )
        embed.add_field(
            inline=False,
            name='Getting Sunny 🚢',
            value=(
                "You might be wondering how to get Sunny for your own server. Currently, Sunny is a private bot for this One Piece Community, "
                "but if you want to set sail with a bot like Sunny, you'll need to contact our Shipwright (server admin). Or better yet, build your own Red instance and customize it to be as SUPER as you want!"
            )
        )
        embed.add_field(
            inline=False,
            name='System Information 💻',
            value=(
                f"**Python Version: {python_version} 🐍\n"
                f"Discord.py Version: {dpy_version} 📚\n"
                f"Red Version: {red_version} 🔴\n"
                f"Ping: {ping}ms 🏴‍☠️**"
            )
        )
        embed.add_field(
            inline=False,
            name='Server Slots ⚓',
            value=f"**Currently in {guild_count} / {max_guilds} servers**"
        )
        
        await ctx.send(embed=embed)

    @commands.command()
    async def credits(self, ctx):
        """Shows the credits for Sunny and the server."""
        cog = self.bot.get_cog("Downloader")
        repos = cog._repo_manager.repos
        s_repos = sorted(repos, key=lambda r: str.lower(r.name))
        embed = discord.Embed(title='The Honorable CreditBoard 🏅', description=" ")
        embed.add_field(
            inline=False,
            name='Red-DiscordBot 🔴',
            value=(
                "Sunny is powered by Red, created by [Twentysix26](https://github.com/Twentysix26) and "
                "[improved by many awesome people.](https://github.com/Cog-Creators/Red-DiscordBot/graphs/contributors)"
            )
        )
        embed.add_field(
            inline=False,
            name='Emojis 😄',
            value="Most of the emojis used in this bot are taken from NQN, so the credits go to their respective owners."
        )
        embed.add_field(
            inline=False,
            name='Cogs and their creators (Thanks to those awesome people for their work!)',
            value=(
                "**[aaa3a-cogs](https://github.com/AAA3A-AAA3A/AAA3A-cogs): aaa3a\n"
                "[ad-cog](https://github.com/aikaterna/gobcog.git): aikaterna\n"
                "[adrian](https://github.com/designbyadrian/CogsByAdrian.git): thinkadrian \n"
                "[blizz-cogs](https://git.purplepanda.cc/blizz/blizz-cogs): blizzthewolf\n"
                "[crab-cogs](https://github.com/orchidalloy/crab-cogs): hollowstrawberry\n"
                "[flare-cogs](https://github.com/flaree/Flare-Cogs): flare (flare#0001)\n"
                "[fluffycogs](https://github.com/zephyrkul/FluffyCogs): Zephyrkul (Zephyrkul#1089)\n"
                "[jojocogs](https://github.com/Just-Jojo/JojoCogs): Jojo#7791\n"
                "[jumperplugins](https://github.com/Redjumpman/Jumper-Plugins): Redjumpman (Redjumpman#1337)\n"
                "[laggrons-dumb-cogs](https://github.com/retke/Laggrons-Dumb-Cogs): El Laggron\n"
                "[lui-cogs-v3](https://github.com/Injabie3/lui-cogs-v3): Injabie3#1660, sedruk, KaguneAstra#6000, TheDarkBot#1677, quachtridat・たつ#8232\n"
                "[maxcogs](https://github.com/ltzmax/maxcogs): MAX\n**"
            )
        )
        embed.add_field(
            inline=False,
            name=' ',
            value=(
                "**[ultcogs](https://github.com/AfterWorld/ultcogs): UltPanda\n"
                "[npc-cogs](https://github.com/npc203/npc-cogs): epic guy#0715\n"
                "[pcxcogs](https://github.com/PhasecoreX/PCXCogs): PhasecoreX (PhasecoreX#0635)\n"
                "[seina-cogs](https://github.com/japandotorg/Seina-Cogs/): inthedark.org\n"
                "[sravan](https://github.com/sravan1946/sravan-cogs): sravan\n"
                "[toxic-cogs](https://github.com/NeuroAssassin/Toxic-Cogs): Neuro Assassin\n"
                "[Trusty-cogs](https://github.com/TrustyJAID/Trusty-cogs/): TrustyJAID\n"
                "[vrt-cogs](https://github.com/vertyco/vrt-cogs): Vertyco\n"
                "[yamicogs](https://github.com/yamikaitou/YamiCogs): YamiKaitou#8975\n**"
            )
        )
        await ctx.send(embed=embed)

async def setup(bot):
    bot.add_cog(OnePieceInfo(bot))
