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
        """Shows One Piece themed information about the Grand Line Discord <:strawhat:1243924879045034075>."""
        python_version = "{}.{}.{}".format(*sys.version_info[:3])
        dpy_version = discord.__version__
        ping = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)

        title = "Grand Line Discord <:strawhat:1243924879045034075>"
        embed = discord.Embed(title=title, description="Ahoy, pirates! Welcome to our One Piece themed Discord server. I'm Sunny, the bot sailing these digital seas. I'm always on deck and ready to help whenever a nakama needs me. Now, let me tell you about my friend [Red](https://github.com/Cog-Creators/Red-DiscordBot/tree/V3/develop/redbot), the system that powers me.")
        embed.set_thumbnail(url="https://example.com/sunny_bot_avatar.png")
        embed.add_field(inline=False, name=' ', value='I (Sunny <:strawhat:1243924879045034075>) am an instance of Red-DiscordBot. If you want a bot like me (because I\'m as SUPER as Franky!), you can create your own by following the [Red installation docs](https://docs.discord.red/en/stable/install_guides/index.html).')
        embed.add_field(inline=False, name=' ', value='Use `!credits` and `!findcog` to view the other sources used in Sunny.')
        embed.add_field(inline=False, name=' ', value="You might be wondering how to get Sunny for your own server. Currently, Sunny is a private bot for this Grand Line, but if you want to set sail with a bot like Sunny, you'll need to contact our Shipwright (server admin). Or better yet, build your own Red instance and customize it to be as SUPER as you want!")
        embed.add_field(inline=False, name="", value=(f"**<:log_pose:1252942734738591776> Python Version: {python_version} \n<:den_den_mushi:1252942959855276143> discord.py: {dpy_version} \n<:sunny:1244503516039348234> Red version: {red_version} \n🏴‍☠️ Ping : {ping}ms\n**"))
        embed.add_field(inline=False, name=' ', value=f"**<:log_pose:1252942734738591776> Currently in {guild_count} servers**")
        
        # Adding emojis to fields for better visuals
        embed.add_field(inline=False, name=' ', value="**<:den_den_mushi:1252942959855276143> For more information, use `!credits` and `!findcog`.**")
        embed.add_field(inline=False, name=' ', value="**<:sunny:1244503516039348234> To get a bot like Sunny, visit the [Red installation docs](https://docs.discord.red/en/stable/install_guides/index.html).**")
        embed.add_field(inline=False, name=' ', value="**🏴‍☠️ Contact our Shipwright (server admin) for more info on Sunny's adventures!**")
        
        await ctx.send(embed=embed)

async def setup(bot):
    bot.add_cog(OnePieceInfo(bot))
