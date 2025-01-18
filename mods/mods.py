from redbot.core import commands, Config
from discord.ext import commands as discord_commands
from discord import Embed, Member, TextChannel
from datetime import datetime, timedelta
import random

class Moderation(commands.Cog):
    """Custom moderation cog for Discord Redbot."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "log_channel": None,
            "warnings": {}
        }
        self.config.register_guild(**default_guild)
        self.kick_messages = [
            "You've been kicked out of the crew, {member}!",
            "Looks like {member} couldn't handle the Grand Line!",
            "{member} has been sent flying like Luffy's punch!",
        ]
        self.ban_messages = [
            "{member} has been banned from the Grand Line!",
            "No more adventures for {member}, they've been banned!",
            "{member} has been sent to Impel Down!",
        ]
        self.mute_messages = [
            "{member} has been silenced by the Sea Prism Stone!",
            "Shh! {member} has been muted!",
            "{member} can't speak now, they've been muted!",
        ]
        self.warn_messages = [
            "{member}, you've been warned! Watch out for the next one!",
            "Careful, {member}! You've received a warning!",
            "{member}, this is your warning! Don't make Zoro mad!",
        ]

    @commands.command(name="boot")
    @commands.has_permissions(kick_members=True)
    async def custom_kick(self, ctx, member: Member, *, reason: str = None):
        """Kick a member from the server."""
        await member.kick(reason=reason)
        message = random.choice(self.kick_messages).format(member=member.mention)
        await ctx.send(message)
        await self.log_action(ctx, "Kick", member, reason)

    @commands.command(name="banish")
    @commands.has_permissions(ban_members=True)
    async def custom_ban(self, ctx, member: Member, *, reason: str = None):
        """Ban a member from the server."""
        await member.ban(reason=reason)
        message = random.choice(self.ban_messages).format(member=member.mention)
        await ctx.send(message)
        await self.log_action(ctx, "Ban", member, reason)

    @commands.command(name="silence")
    @commands.has_permissions(manage_roles=True)
    async def custom_mute(self, ctx, member: Member, duration: int, *, reason: str = None):
        """Mute a member for a specified duration (in minutes)."""
        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            mute_role = await ctx.guild.create_role(name="Muted")
            for channel in ctx.guild.channels:
                await channel.set_permissions(mute_role, speak=False, send_messages=False)
        await member.add_roles(mute_role, reason=reason)
        message = random.choice(self.mute_messages).format(member=member.mention)
        await ctx.send(f"{message} for {duration} minutes.")
        await self.log_action(ctx, "Mute", member, reason)
        await self.bot.wait_for("timeout", timeout=duration * 60)
        await member.remove_roles(mute_role)
        await ctx.send(f"{member.mention} has been unmuted.")

    @commands.command(name="timeout")
    @commands.has_permissions(manage_roles=True)
    async def custom_timeout(self, ctx, member: Member, duration: int, *, reason: str = None):
        """Timeout a member for a specified duration (in minutes)."""
        await member.timeout(duration=timedelta(minutes=duration), reason=reason)
        await ctx.send(f"{member.mention} has been timed out for {duration} minutes.")
        await self.log_action(ctx, "Timeout", member, reason)

    @commands.command(name="caution")
    @commands.has_permissions(manage_roles=True)
    async def custom_warn(self, ctx, member: Member, *, reason: str = None):
        """Warn a member and escalate warnings."""
        guild_id = ctx.guild.id
        warnings = await self.config.guild(ctx.guild).warnings()
        if str(member.id) not in warnings:
            warnings[str(member.id)] = 0
        warnings[str(member.id)] += 1
        await self.config.guild(ctx.guild).warnings.set(warnings)

        level = warnings[str(member.id)]
        if level >= 3:
            await self.custom_mute(ctx, member, duration=10, reason="Automatic mute due to 3 warnings")
            level = 3

        message = random.choice(self.warn_messages).format(member=member.mention)
        embed = Embed(title=f"Level {level} Warning", description="A member got a warning.", color=0xff0000)
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Status", value=f"The member now has {level} warnings ({level} warns)")
        embed.set_footer(text=datetime.now().strftime("%m/%d/%Y %I:%M %p"))

        log_channel_id = await self.config.guild(ctx.guild).log_channel()
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)
        await ctx.send(f"{message}\n", embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setlogchannel(self, ctx, channel: TextChannel):
        """Set the log channel for moderation actions."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Log channel set to {channel.mention}")

    async def log_action(self, ctx, action: str, member: Member, reason: str = None):
        """Log moderation actions to the log channel."""
        embed = Embed(title=action, description=f"A member was {action.lower()}ed.", color=0xff0000)
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=datetime.now().strftime("%m/%d/%Y %I:%M %p"))

        log_channel_id = await self.config.guild(ctx.guild).log_channel()
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)

def setup(bot):
    bot.add_cog(Moderation(bot))
