import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot import __version__ as red_version
import sys
import psutil
import platform
import asyncio
import random
from datetime import datetime, timezone
import textwrap

# Global dictionary to store original commands
original_commands = {}

class OnePieceInfo(commands.Cog):
    """Provides One Piece themed info and ping commands."""

    def __init__(self, bot: Red):
        self.bot = bot

    def cog_unload(self):
        # Restore original commands
        for cmd_name, cmd in original_commands.items():
            if self.bot.get_command(cmd_name):
                self.bot.remove_command(cmd_name)
            if cmd:
                self.bot.add_command(cmd)

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

        embed.add_field(
            name="🧭 Ship's Log",
            value=(
                f"**🏴‍☠️ Crew Members:** {ctx.guild.member_count}\n"
                f"**🌊 Sailing on:** {guild_count} / {max_guilds} seas\n"
                f"**⚓ Docked:** {ctx.guild.name}\n"
                f"**🐉 Captain:** {ctx.guild.owner.mention}"
            ),
            inline=True
        )

        embed.add_field(
            name="🔧 Ship's Specs",
            value=(
                f"**🐏 Ram:** {memory.percent}% occupied\n"
                f"**⚙️ Engine Load:** {cpu_usage}%\n"
                f"**🗺️ Chart Storage:** {disk.percent}% full\n"
                f"**🌡️ Ocean Temperature:** {ping}ms"
            ),
            inline=True
        )

        embed.add_field(name="\u200B", value="\u200B", inline=False)

        embed.add_field(
            name="🏴‍☠️ Pirate Crew",
            value=(
                "⚔️ **Sun God Nika**: The Supreme Deity\n"
                "🛡️ **GodHand**: The Divine Protectors\n"
                "👑 **Gorosei**: The Elders of Wisdom\n"
                "⭐️ **Yonko**: The Emperors of the Sea\n"
                "⚓ **Warlords**: The Government Allies\n"
                "⚡ **Worst Generation**: The Rising Stars"
            ),
            inline=False
        )

        embed.add_field(name="\u200B", value="\u200B", inline=False)

        embed.add_field(
            name="🗝️ Devil Fruit Powers",
            value=(
                f"🐍 **Python:** {python_version}\n"
                f"🤖 **Discord.py:** {dpy_version}\n"
                f"🔴 **Red-DiscordBot:** {red_version}"
            ),
            inline=True
        )

        embed.add_field(
            name="🧭 Navigation",
            value=(
                "`[p]help`: View all commands\n"
                "`[p]info`: Display this ship's log\n"
                "`[p]ping`: Aokiji and Akainu Battle\n"
                "`[p]serverinfo`: Display the ships info\n"
                "`[p]userinfo`: For the pirates info"
            ),
            inline=True
        )

        embed.set_footer(text="Set sail for adventure with the Straw Hat Pirates!")
        
        await ctx.send(embed=embed)

    @commands.command(name="islands")
    @commands.is_owner()
    async def list_islands(self, ctx: commands.Context):
        """List all the islands (servers) the Straw Hat Pirates have visited."""
        guilds = sorted(self.bot.guilds, key=lambda s: s.name.lower())
        
        # Create pages of islands with One Piece theming
        island_pages = []
        for i in range(0, len(guilds), 10):
            page_guilds = guilds[i:i+10]
            embed = discord.Embed(
                title="🏴‍☠️ Grand Line Island Log 🌊", 
                description="A record of every island visited by the Thousand Sunny",
                color=discord.Color.blue()
            )
            
            for guild in page_guilds:
                # Determine island type based on member count
                if guild.member_count < 50:
                    island_emoji = "🏝️"
                elif guild.member_count < 200:
                    island_emoji = "🏙️"
                elif guild.member_count < 1000:
                    island_emoji = "🌴"
                else:
                    island_emoji = "🌋"
                
                embed.add_field(
                    name=f"{island_emoji} {guild.name}", 
                    value=f"ID: `{guild.id}`\nCrew Size: {guild.member_count} pirates", 
                    inline=False
                )
            
            island_pages.append(embed)
        
        # Create a menu for navigating island pages
        await menus.menu(ctx, island_pages, menus.DEFAULT_CONTROLS)

    @commands.command(name="islandinfo")
    @commands.is_owner()
    async def island_details(self, ctx, guild_id: int = None):
        """Explore the details of a specific island (server)."""
        # If no guild_id provided, use current guild
        if guild_id is None:
            guild = ctx.guild
        else:
            guild = self.bot.get_guild(guild_id)
        
        if not guild:
            return await ctx.send("🏴‍☠️ Unable to find that island in the Log Pose!")

        # Calculate online members
        online_members = len([m for m in guild.members if m.status != discord.Status.offline])
        
        # Determine island rank
        if guild.member_count < 50:
            island_rank = "East Blue Village"
        elif guild.member_count < 200:
            island_rank = "Grand Line Port"
        elif guild.member_count < 1000:
            island_rank = "New World Island"
        else:
            island_rank = "Yonko Territory"

        # Create an embed with detailed island information
        embed = discord.Embed(
            title=f"🏴‍☠️ Island Expedition Report: {guild.name}",
            description="Detailed intelligence on a discovered territory",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else "https://example.com/default_map.png")

        embed.add_field(name="🌊 Island Designation", value=guild.name, inline=False)
        embed.add_field(name="🧭 Island ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="👑 Island Captain", value=guild.owner.mention, inline=True)
        embed.add_field(name="🏆 Island Rank", value=island_rank, inline=True)

        embed.add_field(name="👥 Crew Composition", value=(
            f"Total Pirates: {guild.member_count}\n"
            f"Active Pirates: {online_members}\n"
            f"Den Den Mushi (Bots): {len([m for m in guild.members if m.bot])}"
        ), inline=False)

        embed.add_field(name="🏛️ Island Infrastructure", value=(
            f"Text Taverns: {len([c for c in guild.channels if isinstance(c, discord.TextChannel)])}\n"
            f"Voice Crow's Nests: {len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])}\n"
            f"Crew Positions: {len(guild.roles)}"
        ), inline=False)

        embed.add_field(name="📅 Island Discovery", value=guild.created_at.strftime("%B %d, %Y"), inline=True)

        # Add epic One Piece quotes to footer
        quotes = [
            "Every island has a story waiting to be discovered!",
            "The sea is vast. Each island holds its own adventure!",
            "Not all treasure is silver and gold...",
        ]
        embed.set_footer(text=random.choice(quotes))

        # Add reactions for additional actions
        message = await ctx.send(embed=embed)
        
        # Add confirmation reactions for owner actions
        if ctx.author.id == self.bot.owner_id:
            await message.add_reaction("🏴")  # Leave server
            await message.add_reaction("🔍")  # More details

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["🏴", "🔍"] and reaction.message.id == message.id

            try:
                reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                
                if str(reaction.emoji) == "🏴":
                    # Confirmation for leaving server
                    confirm_msg = await ctx.send("⚠️ Are you sure you want to abandon this island? React with ✅ to confirm.")
                    await confirm_msg.add_reaction("✅")
                    
                    def confirm_check(reaction, user):
                        return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id
                    
                    try:
                        await self.bot.wait_for('reaction_add', timeout=30.0, check=confirm_check)
                        await guild.leave()
                        await ctx.send(f"🏴‍☠️ Successfully left the island: {guild.name}")
                    except asyncio.TimeoutError:
                        await confirm_msg.delete()
                        await ctx.send("Island departure cancelled.")
                
                elif str(reaction.emoji) == "🔍":
                    # More detailed information
                    more_info = (
                        f"**Extended Island Log:**\n"
                        f"Emojis: {len(guild.emojis)}\n"
                        f"Stickers: {len(guild.stickers)}\n"
                        f"Verification Level: {guild.verification_level}\n"
                        f"Explicit Content Filter: {guild.explicit_content_filter}"
                    )
                    await ctx.send(more_info)

            except asyncio.TimeoutError:
                pass

    @commands.command()
    async def ping(self, ctx):
        """Shows a battle between Aokiji and Akainu with ping information"""
        start = ctx.message.created_at
        embed = discord.Embed(title="Battle on Punk Hazard: Aokiji vs Akainu", color=discord.Color.orange())
        message = await ctx.send(embed=embed)
        
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
            
            if random.random() < 0.05:
                embed.add_field(name="Unexpected Interruption!", value=random.choice(easter_eggs), inline=False)
            
            await message.edit(embed=embed)
        
        end = discord.utils.utcnow()
        ping_time = (end - start).total_seconds() * 1000
        
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
        
        # Determine island type and features
        if guild.member_count < 50:
            island_type = "🏝️ East Blue Village"
        elif guild.member_count < 200:
            island_type = "🏙️ Grand Line Port"
        elif guild.member_count < 1000:
            island_type = "🌴 New World Island"
        else:
            island_type = "🌋 Yonko Territory"

        island_features = []
        if "COMMUNITY" in guild.features:
            island_features.append("🏴‍☠️ Pirate Haven")
        if "ANIMATED_ICON" in guild.features:
            island_features.append("🎭 Thriller Bark Illusions")
        if "BANNER" in guild.features:
            island_features.append("🚩 Jolly Roger Flying")
        if "DISCOVERABLE" in guild.features:
            island_features.append("🗺️ Log Pose Attraction")
        if "INVITE_SPLASH" in guild.features:
            island_features.append("🌊 Aqua Laguna Defenses")
        if "PUBLIC" in guild.features:
            island_features.append("📯 Buster Call Target")
        if "VANITY_URL" in guild.features:
            island_features.append("🧭 Eternal Pose")
        
        embed = discord.Embed(title=f"📍 Island Log: {guild.name}", color=discord.Color.blue())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else "https://example.com/default_island.png")
        
        embed.add_field(name="🏝️ Island Type", value=island_type, inline=True)
        embed.add_field(name="🏴‍☠️ Pirate Captain", value=guild.owner.mention, inline=True)
        embed.add_field(name="⚓ Founding Date", value=guild.created_at.strftime("%B %d, %Y"), inline=True)
        
        embed.add_field(name="👥 Population", value=f"Total: {guild.member_count}\nPirates: {len([m for m in guild.members if not m.bot])}\nDen Den Mushi: {len([m for m in guild.members if m.bot])}", inline=True)
        embed.add_field(name="🏘️ Locations", value=f"Taverns (Text): {len(guild.text_channels)}\nCrow's Nests (Voice): {len(guild.voice_channels)}\nDistricts (Categories): {len(guild.categories)}", inline=True)
        embed.add_field(name="🏅 Crew Positions", value=f"Total Roles: {len(guild.roles)}\nHighest Role: {guild.roles[-1].name}", inline=True)
        
        if island_features:
            embed.add_field(name="🌟 Island Features", value="\n".join(island_features), inline=False)
        
        embed.set_footer(text="May the winds of adventure guide your ship to this island!")
        
        await ctx.send(embed=embed)

    @commands.command()
    async def userinfo(self, ctx, *, user: discord.Member = None):
        """Display user info (themed as a Vivre Card)."""
        user = user or ctx.author
        
        # Calculate account age using offset-aware datetimes
        now = datetime.now(timezone.utc)
        account_age = (now - user.created_at).days

        # Get roles, excluding @everyone
        roles = [role.name for role in user.roles if role.name != "@everyone"]
        
        # Determine user's highest role (crew position)
        highest_role = user.top_role.name if len(user.roles) > 1 else "Cabin Boy/Girl"

        # One Piece themed status
        op_status = {
            discord.Status.online: "On an Adventure",
            discord.Status.idle: "Taking a Nap",
            discord.Status.dnd: "In a Fierce Battle",
            discord.Status.offline: "Lost at Sea"
        }

        embed = discord.Embed(title=f"Vivre Card of {user.name}", color=user.color)
        embed.set_thumbnail(url=user.display_avatar.url)
        
        embed.add_field(name="🏴‍☠️ Pirate Name", value=user.name, inline=True)
        embed.add_field(name="🔢 Pirate ID", value=user.discriminator, inline=True)
        embed.add_field(name="⚓ Joined Crew", value=user.joined_at.strftime("%d %b %Y"), inline=True)
        
        embed.add_field(name="🎂 Pirate Age", value=f"{account_age} days", inline=True)
        embed.add_field(name="🧭 Current Status", value=op_status.get(user.status, "Unknown"), inline=True)
        embed.add_field(name="🏅 Highest Position", value=highest_role, inline=True)
        
        if roles:
            embed.add_field(name="🎭 Crew Positions", value=", ".join(roles) if len(roles) < 10 else f"{len(roles)} positions", inline=False)
        
        # Add a random One Piece quote
        quotes = [
            "The sea is vast. Someday, without fail, your nakama will appear!",
            "Only those who have suffered long can see the light within the shadows.",
            "If you don't take risks, you can't create a future!",
            "When do you think people die? When they are shot in the heart with a pistol? No. When they are ravaged by an uncurable disease? No. When they drink a soup made from poisonous mushrooms? No! It's when they are forgotten!",
            "I don't want to conquer anything. I just think the guy with the most freedom in this whole ocean... that's the Pirate King!"
        ]
        embed.set_footer(text=random.choice(quotes))

        await ctx.send(embed=embed)

async def setup(bot: Red):
    global original_commands
    cog = OnePieceInfo(bot)

    # Store and replace original commands
    command_names = ["info", "serverinfo", "userinfo", "ping"]
    for cmd_name in command_names:
        original_cmd = bot.get_command(cmd_name)
        if original_cmd:
            original_commands[cmd_name] = original_cmd
            bot.remove_command(cmd_name)

    await bot.add_cog(cog)

async def teardown(bot: Red):
    global original_commands
    # Restore original commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
