import discord
from discord.ext import tasks
from redbot.core import commands, Config
from datetime import datetime

class OPWelcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "welcome_channel": None,
            "welcome_enabled": False,
            "welcome_message": (
                "Ahoy, {mention}! Welcome aboard the {guild} crew! 🏴‍☠️\n\n"
                "You've just set sail on an incredible adventure in the world of One Piece! 🌊"
            ),
            "welcome_role": None
        }
        self.config.register_guild(**default_guild)

    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def welcome(self, ctx):
        """Manage welcome settings."""
        pass

    @welcome.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Set the welcome channel."""
        await self.config.guild(ctx.guild).welcome_channel.set(channel.id)
        await ctx.send(f"Welcome channel set to {channel.mention} 🌟")

    @welcome.command()
    async def toggle(self, ctx):
        """Toggle the welcome message on or off."""
        current = await self.config.guild(ctx.guild).welcome_enabled()
        await self.config.guild(ctx.guild).welcome_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"Welcome message {state}. 🟢" if state == "enabled" else f"Welcome message {state}. 🔴")

    @welcome.command()
    async def message(self, ctx, *, welcome_message: str = None):
        """Set a custom welcome message or reset to default if no message is provided."""
        default_message = (
            "Ahoy, {mention}! Welcome aboard the {guild} crew! 🏴‍☠️\n\n"
            "You've just set sail on an incredible adventure in the world of One Piece! 🌊"
        )
        if not welcome_message:
            welcome_message = default_message
            await self.config.guild(ctx.guild).welcome_message.set(default_message)
            await ctx.send("Welcome message has been reset to the default. 📝")
        else:
            await self.config.guild(ctx.guild).welcome_message.set(welcome_message)
            await ctx.send("Welcome message updated! 📝")

    @welcome.command()
    async def role(self, ctx, role: discord.Role):
        """Set a welcome role to be assigned to new members."""
        await self.config.guild(ctx.guild).welcome_role.set(role.id)
        await ctx.send(f"Welcome role set to {role.name} 🌟")

    @welcome.command()
    async def preview(self, ctx):
        """Preview the current welcome message."""
        welcome_message_template = await self.config.guild(ctx.guild).welcome_message()
        welcome_message = welcome_message_template.format(
            mention=ctx.author.mention,
            guild=ctx.guild.name
        )
        embed = discord.Embed(
            title="Ahoy, New Crew Member!",
            description=welcome_message,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_image(url="https://example.com/path/to/welcome/banner.png")  # Add a relevant welcome banner URL
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url)

        embed.add_field(
            name="About One Piece",
            value=(
                "One Piece is an epic tale of pirates, adventure, and the search for the ultimate treasure - the One Piece. "
                "Join Monkey D. Luffy and his diverse crew as they navigate treacherous seas, face powerful enemies, "
                "and uncover the mysteries of the Grand Line."
            ),
            inline=False
        )

        embed.add_field(
            name="Server Information",
            value=(
                "🏴‍☠️ **Crew Quarters (channels):**\n"
                "• <#425068612542398476> - General 💬\n"
                "• <#590972222366023718> - Rules 📜\n"
                "• <#597528644432166948> - Roles 🏷️"
            ),
            inline=False
        )

        embed.add_field(
            name="Adventure Awaits!",
            value=(
                "• Join battles with `.battle @opponent ⚔️`\n"
                "• Start team battles with `.teambattle @teammate vs @opponent1 @opponent2 ⚔️`\n"
                "• Check your profile with `.profile 📜`\n"
                "• Train your skills with `.train strength` (or defense/speed) 🏋️‍♂️\n"
                "• Explore islands with `.explore 🏝️`\n"
                "• Join crews with `.join_crew <crew_name> ⚓`\n"
                "• Eat Devil Fruits with `.eat_devil_fruit <fruit_name> 🍎`\n\n"
                "Set sail, make friends, and carve your legend in the world of One Piece! 🌟"
            ),
            inline=False
        )

        embed.set_footer(text=f"Member #{ctx.guild.member_count}")

        await ctx.send(embed=embed)

    @welcome.command()
    async def test(self, ctx):
        """Test the welcome message."""
        await self.on_member_join(ctx.author)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if not await self.config.guild(guild).welcome_enabled():
            return

        channel_id = await self.config.guild(guild).welcome_channel()
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        welcome_message_template = await self.config.guild(guild).welcome_message()
        welcome_message = welcome_message_template.format(
            mention=member.mention,
            guild=guild.name
        )

        embed = discord.Embed(
            title="Ahoy, New Crew Member!",
            description=welcome_message,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url="https://example.com/path/to/welcome/banner.png")  # Add a relevant welcome banner URL
        embed.set_author(name=guild.name, icon_url=guild.icon.url)

        embed.add_field(
            name="About One Piece",
            value=(
                "One Piece is an epic tale of pirates, adventure, and the search for the ultimate treasure - the One Piece. "
                "Join Monkey D. Luffy and his diverse crew as they navigate treacherous seas, face powerful enemies, "
                "and uncover the mysteries of the Grand Line."
            ),
            inline=False
        )

        embed.add_field(
            name="Server Information",
            value=(
                "🏴‍☠️ **Crew Quarters (channels):**\n"
                "• <#425068612542398476> - General 💬\n"
                "• <#590972222366023718> - Rules 📜\n"
                "• <#597528644432166948> - Roles 🏷️"
            ),
            inline=False
        )

        embed.add_field(
            name="Adventure Awaits!",
            value=(
                "• Join battles with `.battle @opponent ⚔️`\n"
                "• Start team battles with `.teambattle @teammate vs @opponent1 @opponent2 ⚔️`\n"
                "• Check your profile with `.profile 📜`\n"
                "• Train your skills with `.train strength` (or defense/speed) 🏋️‍♂️\n"
                "• Explore islands with `.explore 🏝️`\n"
                "• Join crews with `.join_crew <crew_name> ⚓`\n"
                "• Eat Devil Fruits with `.eat_devil_fruit <fruit_name> 🍎`\n\n"
                "Set sail, make friends, and carve your legend in the world of One Piece! 🌟"
            ),
            inline=False
        )

        embed.set_footer(text=f"Member #{guild.member_count}")

        try:
            await channel.send(embed=embed)
            welcome_role_id = await self.config.guild(guild).welcome_role()
            if welcome_role_id:
                welcome_role = guild.get_role(welcome_role_id)
                if welcome_role:
                    await member.add_roles(welcome_role)
        except discord.Forbidden:
            await guild.owner.send(f"I don't have permission to send messages in {channel.mention}")

def setup(bot):
    bot.add_cog(OPWelcome(bot))
