import discord
from redbot.core import commands, Config
from datetime import datetime

class OPWelcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "welcome_channel": None,
            "welcome_enabled": False,
            "welcome_message": "Ahoy, {mention}! Welcome aboard the {guild} crew! 🏴‍☠️",
            "rules_channel": None,
            "roles_channel": None,
            "general_channel": None
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
        await ctx.send(f"Welcome channel set to {channel.mention}")

    @welcome.command()
    async def toggle(self, ctx):
        """Toggle the welcome message on or off."""
        current = await self.config.guild(ctx.guild).welcome_enabled()
        await self.config.guild(ctx.guild).welcome_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"Welcome message {state}.")

    @welcome.command()
    async def message(self, ctx, *, welcome_message: str = None):
        """Set a custom welcome message or reset to default if no message is provided."""
        default_message = "Ahoy, {mention}! Welcome aboard the {guild} crew! 🏴‍☠️"
        if not welcome_message:
            welcome_message = default_message
        await self.config.guild(ctx.guild).welcome_message.set(welcome_message)
        await ctx.send("Welcome message updated!")

    @welcome.command()
    async def setchannels(self, ctx, rules: discord.TextChannel, roles: discord.TextChannel, general: discord.TextChannel):
        """Set the rules, roles, and general channels."""
        await self.config.guild(ctx.guild).rules_channel.set(rules.id)
        await self.config.guild(ctx.guild).roles_channel.set(roles.id)
        await self.config.guild(ctx.guild).general_channel.set(general.id)
        await ctx.send(f"Channels set: Rules: {rules.mention}, Roles: {roles.mention}, General: {general.mention}")

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

        welcome_message = await self.config.guild(guild).welcome_message()
        rules_channel = guild.get_channel(await self.config.guild(guild).rules_channel())
        roles_channel = guild.get_channel(await self.config.guild(guild).roles_channel())
        general_channel = guild.get_channel(await self.config.guild(guild).general_channel())

        embed = discord.Embed(
            title="Welcome to the Crew!",
            description=welcome_message.format(mention=member.mention, guild=guild.name),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else None)

        if rules_channel and roles_channel and general_channel:
            embed.add_field(
                name="Getting Started",
                value=(
                    f"1. Read the rules in {rules_channel.mention}\n"
                    f"2. Get your roles in {roles_channel.mention}\n"
                    f"3. Join the conversation in {general_channel.mention}"
                ),
                inline=False
            )

        embed.set_footer(text=f"Member #{guild.member_count}")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            await guild.owner.send(f"I don't have permission to send messages in {channel.mention}")

def setup(bot):
    bot.add_cog(OPWelcome(bot))
