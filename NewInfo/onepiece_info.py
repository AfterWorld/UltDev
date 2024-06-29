import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot import __version__ as red_version
import sys
import psutil
import platform
import asyncio
import random
from datetime import datetime

# Global variables for old commands
old_info = None
old_ping = None
old_serverinfo = None
old_userinfo = None

class OnePieceInfo(commands.Cog):
    """Provides One Piece themed info and ping commands."""

    def __init__(self, bot: Red):
        self.bot = bot

    def cog_unload(self):
        global old_info, old_ping, old_serverinfo, old_userinfo
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
        if old_serverinfo:
            try:
                self.bot.remove_command("serverinfo")
            except:
                pass
            self.bot.add_command(old_serverinfo)
        if old_userinfo:
            try:
                self.bot.remove_command("userinfo")
            except:
                pass
            self.bot.add_command(old_userinfo)

    @commands.command()
    async def info(self, ctx):
        """Shows One Piece themed information about the Thousand Sunny Bot."""
        python_version = "{}.{}.{}".format(*sys.version_info[:3])
        dpy_version = discord.__version__
        ping = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)
        max_guilds = 20  # Assuming 20 is the max slots reserved for the bot

        # Get system info
        cpu_usage = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Embed content
        embed = discord.Embed(
            title="🏴‍☠️ Welcome Aboard the Thousand Sunny! 🌞",
            description=(
                "Ahoy, brave pirates! I'm the Thousand Sunny, the dream ship crafted by the legendary shipwright Franky. "
                "I've sailed through digital Grand Lines to reach you, powered by the spirit of adventure and the technology of "
                "[Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot)!"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://example.com/thousand_sunny.png")

        # Add inline fields for Ship's Log and Ship's Specs side by side
        embed.add_field(
            name="🧭 **Ship's Log**",
            value=(
                f"**🏴‍☠️ Crew Members:** {ctx.guild.member_count}\n"
                f"**🌊 Sailing on:** {guild_count} / {max_guilds} seas\n"
                f"**⚓ Docked:** {ctx.guild.name}\n"
                f"**🐉 Captain:** {ctx.guild.owner.mention}"
            ),
            inline=True
        )

        embed.add_field(
            name="🔧 **Ship's Specs**",
            value=(
                f"**🐏 Ram:** {memory.percent}% occupied\n"
                f"**⚙️ Engine Load:** {cpu_usage}%\n"
                f"**🗺️ Chart Storage:** {disk.percent}% full\n"
                f"**🌡️ Ocean Temperature:** {ping}ms"
            ),
            inline=True
        )

        embed.add_field(
            name="\u200B",  # Empty field for spacing
            value="\u200B",
            inline=False
        )

        # Add fields for each rank with titles only
        embed.add_field(
            name="🏴‍☠️ **Pirate Crew**",
            value=(
                "----------------------------------------------------------------------------------\n"
                "⚔️ **Sun God Nika**: The Supreme Deity\n"
                "🛡️ **GodHand**: The Divine Protectors\n"
                "👑 **Gorosei**: The Elders of Wisdom\n"
                "⭐️ **Yonko**: The Emperors of the Sea\n"
                "⚓ **Warlords**: The Government Allies\n"
                "⚡ **Worst Generation**: The Rising Stars\n"
                "----------------------------------------------------------------------------------\n"
            ),
            inline=False
        )

        embed.add_field(
            name="\u200B",  # Empty field for spacing
            value="\u200B",
            inline=False
        )

        embed.add_field(
            name="🗝️ **Devil Fruit Powers**",
            value=(
                "🐍 **Python:** {}\n"
                "🤖 **Discord.py:** {}\n"
                "🔴 **Red-DiscordBot:** {}".format(python_version, dpy_version, red_version)
            ),
            inline=True
        )

        embed.add_field(
            name="🧭 **Navigation**",
            value=(
                "`[p]help`: View all commands\n"
                "`[p]info`: Display this ship's log\n"
                "`[p]ping`: Test the waters with Aokiji and Akainu"
            ),
            inline=True
        )

        embed.set_footer(text="Set sail for adventure with the Straw Hat Pirates!")
        
        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx):
        """Shows a battle between Aokiji and Akainu with ping information"""
        start = ctx.message.created_at
        embed = discord.Embed(title="Battle on Punk Hazard: Aokiji vs Akainu", color=discord.Color.orange())
        message = await ctx.send(embed=embed)
        
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
            "The smoke clears, revealing the outcome..."
        ]
        
        # Easter egg interruptions
        easter_eggs = [
            "Suddenly, Garp appears and knocks both admirals out!",
            "A wild Luffy appears, mistaking the battle for a meat-cooking contest!",
            "Buggy the Clown accidentally stumbles into the battlefield, somehow emerging unscathed!",
            "The battle is interrupted by Whitebeard's ghostly laughter echoing across Punk Hazard!",
            "Unexpected interference! The Thousand Sunny crashes into the island, scattering the combatants!"
        ]

        for frame in battle_frames:
            embed.description = frame
            await asyncio.sleep(1)
            
            # 5% chance for an Easter egg to occur
            if random.random() < 0.05:
                embed.add_field(name="Unexpected Interruption!", value=random.choice(easter_eggs), inline=False)
            
            await message.edit(embed=embed)
        
        end = discord.utils.utcnow()
        ping_time = (end - start).total_seconds() * 1000
        
        # Determine the winner based on ping time
        if ping_time < 100:
            winner = "Aokiji"
            outcome = "Aokiji's ice freezes even Akainu's magma!"
            color = discord.Color.blue()
        elif ping_time < 200:
            winner = "Tie"
            outcome = "Neither admiral can overcome the other. It's a draw!"
            color = discord.Color.purple()
        else:
            winner = "Akainu"
            outcome = "Akainu's magma melts through Aokiji's ice!"
            color = discord.Color.red()
        
        embed.color = color
        embed.add_field(name="Battle Outcome", value=f"**{winner}** {'wins' if winner != 'Tie' else ''}\n{outcome}", inline=False)
        embed.add_field(name="Battle Statistics", value=(
            f"⏱️ Battle duration: **{ping_time:.2f}ms**\n"
            f"🌡️ WebSocket latency: **{round(self.bot.latency * 1000, 2)}ms**"
        ), inline=False)
        embed.set_footer(text="The fight on Punk Hazard rages on, changing the very nature of the island!")
        
        await message.edit(embed=embed)

    @commands.command()
    async def serverinfo(self, ctx):
        """Display information about the current island (server)."""
        guild = ctx.guild
        
        if guild.member_count < 50:
            island_type = "Small island village"
        elif guild.member_count < 200:
            island_type = "Bustling port town"
        elif guild.member_count < 1000:
            island_type = "Grand Line island"
        else:
            island_type = "New World stronghold"

        bot_count = sum(1 for m in guild.members if m.bot)
        
        embed = discord.Embed(title=f"📍 Island Log: {guild.name}", color=discord.Color.blue())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else "https://example.com/default_island.png")
        
        embed.add_field(name="🏝️ Island Type", value=island_type, inline=False)
        embed.add_field(name="🏴‍☠️ Pirate Captain", value=guild.owner.mention, inline=True)
        embed.add_field(name="🗺️ Region", value=str(guild.region).title() if hasattr(guild, 'region') else "Unknown Seas", inline=True)
        embed.add_field(name="⚓ Founding Date", value=guild.created_at.strftime("%B %d, %Y"), inline=True)
        
        embed.add_field(name="👥 Population", value=f"{guild.member_count} inhabitants", inline=True)
        embed.add_field(name="🤖 Den Den Mushi", value=f"{bot_count} snails", inline=True)
        
        channel_info = (
            f"🗣️ Taverns (Text): {len(guild.text_channels)}\n"
            f"🎙️ Crow's Nests (Voice): {len(guild.voice_channels)}\n"
            f"📜 Announcements: {len(guild.categories)}"
        )
        embed.add_field(name="🏘️ Locations", value=channel_info, inline=False)
        
        role_info = (
            f"🎭 Total Roles: {len(guild.roles)}\n"
            f"👑 Highest Role: {guild.roles[-1].name}"
        )
        embed.add_field(name="🏅 Crew Positions", value=role_info, inline=False)
        
        embed.set_footer(text="May the winds of adventure guide your ship to this island!")
        
        await ctx.send(embed=embed)

    @commands.command()
    async def userinfo(self, ctx, member: discord.Member = None):
        """Display information about a crewmate (user)."""
        member = member or ctx.author
        
        days_on_server = (datetime.utcnow() - member.joined_at).days
        if days_on_server < 7:
            rank = "Cabin Boy"
        elif days_on_server < 30:
            rank = "Deckhand"
        elif days_on_server < 90:
            rank = "Quarter Master"
        elif days_on_server < 180:
            rank = "First Mate"
        else:
            rank = "Veteran Pirate"

        embed = discord.Embed(title=f"🏴‍☠️ Pirate Profile: {member.name}", color=member.color)
        embed.set_thumbnail(url=member.avatar.url)
        
        embed.add_field(name="🎭 Pirate Alias", value=member.display_name, inline=True)
        embed.add_field(name="🏅 Crew Rank", value=rank, inline=True)
        embed.add_field(name="🗺️ Joined Crew", value=member.joined_at.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="🌊 Sailed Discord Seas Since", value=member.created_at.strftime("%B %d, %Y"), inline=True)
        
        roles = [role.mention for role in reversed(member.roles) if role.name != "@everyone"]
        embed.add_field(name=f"🎨 Colors of Allegiance ({len(roles)})", value=" ".join(roles) if roles else "No colors", inline=False)
        
        pirate_status = f"{'🟢 On Deck' if member.status == discord.Status.online else '🔴 Below Deck'}"
        if member.is_on_mobile():
            pirate_status += " (via Den Den Mushi)"
        embed.add_field(name="⚓ Current Status", value=pirate_status, inline=False)
        
        if member.activity:
            if isinstance(member.activity, discord.Game):
                embed.add_field(name="🎮 Current Adventure", value=f"Playing {member.activity.name}", inline=False)
            elif isinstance(member.activity, discord.Streaming):
                embed.add_field(name="📡 Broadcasting Adventure", value=f"Streaming {member.activity.name}", inline=False)
        
        embed.set_footer(text="A true nakama, through calm seas and stormy weather!")
        
        await ctx.send(embed=embed)

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
            "[aaa3a-cogs](https://github.com/AAA3A-AAA3A/AAA3A-cogs): aaa3a",
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
            "[yamicogs](https://github.com/yamikaitou/YamiCogs): YamiKaitou#8975"
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
    global old_info, old_ping, old_serverinfo, old_userinfo
    old_info = bot.get_command("info")
    old_ping = bot.get_command("ping")
    old_serverinfo = bot.get_command("serverinfo")
    old_userinfo = bot.get_command("userinfo")
    
    if old_info:
        bot.remove_command(old_info.name)
    if old_ping:
        bot.remove_command(old_ping.name)
    if old_serverinfo:
        bot.remove_command(old_serverinfo.name)
    if old_userinfo:
        bot.remove_command(old_userinfo.name)

    cog = OnePieceInfo(bot)
    await bot.add_cog(cog)
