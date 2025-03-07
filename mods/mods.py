from redbot.core import commands, Config
from discord import Embed, Member, TextChannel
from datetime import datetime, timedelta
import random
import discord
import asyncio

class Moderation(commands.Cog):
    """Custom moderation cog for Discord Redbot."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "log_channel": None,
            "mute_role": None,
            "warnings": {},
            "mutes": {},
            "kicks": {},
            "timeouts": {}
        }
        self.config.register_guild(**default_guild)
        self.kick_messages = [
            "You've been booted from the crew, {member}!",
            "Looks like {member} couldn't handle the Grand Line!",
            "{member} has been sent flying like Luffy's punch!",
        ]
        self.ban_messages = [
            "{member} has been banished from the Grand Line!",
            "No more adventures for {member}, they've been banished!",
            "{member} has been sent to Impel Down!",
        ]
        self.mute_messages = [
            "{member} has been silenced by the Sea Prism Stone!",
            "Shh! {member} has been quieted!",
            "{member} can't speak now, they've been quieted!",
        ]
        self.warn_messages = [
            "{member}, you've been cautioned! Watch out for the next one!",
            "Careful, {member}! You've received a caution!",
            "{member}, this is your caution! Don't make Zoro mad!",
        ]
        self.timeout_messages = [
            "{member} has been sent to the corner!",
            "{member} is in timeout!",
            "{member} has been put in the corner for a while!",
        ]

    @commands.command(name="boot")
    @commands.has_permissions(kick_members=True)
    async def custom_kick(self, ctx, member: Member, *, reason: str = None):
        """Kick a member from the server."""
        await member.kick(reason=reason)
        message = random.choice(self.kick_messages).format(member=member.mention)
        await ctx.send(message)
        await self.log_action(ctx, "Kick", member, reason)
        await self.increment_stat(ctx.guild.id, member.id, "kicks")

    @commands.command(name="banish")
    @commands.has_permissions(ban_members=True)
    async def custom_ban(self, ctx, member: Member, *, reason: str = None):
        """Ban a member from the server."""
        await member.ban(reason=reason)
        message = random.choice(self.ban_messages).format(member=member.mention)
        await ctx.send(message)
        await self.log_action(ctx, "Ban", member, reason)

    async def get_mute_role(self, ctx):
        """Get the mute role for the guild or create one if it doesn't exist."""
        # Check if we have a saved mute role ID
        mute_role_id = await self.config.guild(ctx.guild).mute_role()
        mute_role = None
        
        if mute_role_id:
            mute_role = ctx.guild.get_role(mute_role_id)
        
        # If we don't have a valid mute role, find one named "Muted"
        if not mute_role:
            mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        
        # If we still don't have a mute role, we'll need to create one
        if not mute_role:
            return None
            
        return mute_role
    
    @commands.command(name="setupmute")
    @commands.has_permissions(administrator=True)
    async def setup_mute_role(self, ctx, role: discord.Role = None):
        """Set up the muted role. If no role is provided, a new one will be created automatically."""
        # If a role was provided, use it
        if role:
            mute_role = role
            await self.config.guild(ctx.guild).mute_role.set(role.id)
            await ctx.send(f"Mute role set to {role.mention}")
        else:
            # Create a new role
            try:
                # Create role below the bot's highest role
                bot_member = ctx.guild.me
                bot_roles = bot_member.roles
                if len(bot_roles) > 1:
                    highest_bot_role = max([r for r in bot_roles if not r.is_default()], key=lambda r: r.position)
                    position = highest_bot_role.position - 1
                else:
                    position = 0
                
                # Create the role
                mute_role = await ctx.guild.create_role(name="Muted", reason="Setup for moderation")
                
                # Position it correctly
                positions = {mute_role: position}
                await ctx.guild.edit_role_positions(positions)
                
                # Save the role ID
                await self.config.guild(ctx.guild).mute_role.set(mute_role.id)
                
                await ctx.send(f"Created Muted role {mute_role.mention}")
            except Exception as e:
                await ctx.send(f"Failed to create mute role: {str(e)}")
                return
        
        # Set up permissions for all channels
        status_msg = await ctx.send("Setting up channel permissions for the mute role... This may take a moment.")
        
        try:
            for channel in ctx.guild.channels:
                await channel.set_permissions(mute_role, 
                                             send_messages=False, 
                                             speak=False, 
                                             add_reactions=False,
                                             create_public_threads=False,
                                             create_private_threads=False,
                                             send_messages_in_threads=False)
                
            await status_msg.edit(content=f"✅ Mute role setup complete! The role {mute_role.mention} has been configured for all channels.")
        except Exception as e:
            await status_msg.edit(content=f"⚠️ Partially completed mute role setup. Error: {str(e)}")
    
    @commands.command(name="quiet")
    @commands.has_permissions(manage_roles=True)
    async def custom_mute(self, ctx, member: Member, duration: int = 30, *, reason: str = None):
        """Mute a member for a specified duration (in minutes, default: 30)."""
        mute_role = await self.get_mute_role(ctx)
        
        if not mute_role:
            await ctx.send("No mute role found. Setting one up now...")
            await self.setup_mute_role(ctx)
            mute_role = await self.get_mute_role(ctx)
            
            if not mute_role:
                await ctx.send("Failed to set up a mute role. Please try setting it up manually with `setupmute`.")
                return
        
        # Apply mute role without removing other roles
        await member.add_roles(mute_role, reason=reason)
        
        message = random.choice(self.mute_messages).format(member=member.mention)
        await ctx.send(f"{message} for {duration} minutes.")
        await self.log_action(ctx, "Mute", member, reason)
        await self.increment_stat(ctx.guild.id, member.id, "mutes")
        
        # Start a background task to unmute the member after the specified duration
        self.bot.loop.create_task(self.unmute_after_delay(ctx, member, duration))

    async def unmute_after_delay(self, ctx, member: Member, duration: int):
        """Unmute a member after a specified delay."""
        await asyncio.sleep(duration * 60)
        
        # Get the configured mute role
        mute_role = await self.get_mute_role(ctx)
        
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role)
            await ctx.send(f"{member.mention} has been unmuted.")

    @commands.command(name="corner")
    @commands.has_permissions(manage_roles=True)
    async def custom_timeout(self, ctx, member: Member, duration: int = 30, *, reason: str = None):
        """Timeout a member for a specified duration (in minutes, default: 30)."""
        try:
            until = datetime.utcnow() + timedelta(minutes=duration)
            await member.timeout(until=until, reason=reason)
            message = random.choice(self.timeout_messages).format(member=member.mention)
            await ctx.send(f"{message} for {duration} minutes.")
            await self.log_action(ctx, "Timeout", member, reason)
            await self.increment_stat(ctx.guild.id, member.id, "timeouts")
        except Exception as e:
            await ctx.send(f"Failed to timeout {member.mention}: {str(e)}")

    @commands.command(name="caution")
    @commands.has_permissions(manage_roles=True)
    async def custom_warn(self, ctx, member: Member, *, reason: str = None):
        """Warn a member and automatically mute after 3 warnings."""
        guild_id = ctx.guild.id
        warnings = await self.config.guild(ctx.guild).warnings()
        if str(member.id) not in warnings:
            warnings[str(member.id)] = 0
        warnings[str(member.id)] += 1
        await self.config.guild(ctx.guild).warnings.set(warnings)

        level = warnings[str(member.id)]
        
        # If 3+ warnings, apply mute for 30 minutes
        if level >= 3:
            mute_role = await self.get_mute_role(ctx)
            
            if not mute_role:
                await ctx.send("No mute role found. Setting one up now...")
                await self.setup_mute_role(ctx)
                mute_role = await self.get_mute_role(ctx)
                
                if not mute_role:
                    await ctx.send("Failed to set up a mute role. Please try setting it up manually with `setupmute`.")
                    return
            
            await member.add_roles(mute_role, reason="Automatic mute due to 3 warnings")
            self.bot.loop.create_task(self.unmute_after_delay(ctx, member, 30))
            await ctx.send(f"{member.mention} has been automatically muted for 30 minutes due to reaching 3 warnings.")

        message = random.choice(self.warn_messages).format(member=member.mention)
        embed = Embed(title=f"Level {level} Caution", description="A member got a caution.", color=0xff0000)
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        embed.add_field(name="Reason", value=reason or "No reason provided")
        embed.add_field(name="Status", value=f"The member now has {level} caution(s)")
        embed.set_footer(text=datetime.now().strftime("%m/%d/%Y %I:%M %p"))

        log_channel_id = await self.config.guild(ctx.guild).log_channel()
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)
        await ctx.send(f"{message}", embed=embed)

    @commands.command(name="unquiet")
    @commands.has_permissions(manage_roles=True)
    async def custom_unmute(self, ctx, member: Member):
        """Unmute a member."""
        mute_role = await self.get_mute_role(ctx)
        
        if mute_role and mute_role in member.roles:
            await member.remove_roles(mute_role)
            await ctx.send(f"{member.mention} has been unmuted.")
            await self.log_action(ctx, "Unmute", member)
        else:
            await ctx.send(f"{member.mention} is not muted.")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setlogchannel(self, ctx, channel: TextChannel):
        """Set the log channel for moderation actions."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Log channel set to {channel.mention}")

    @commands.command()
    async def cautions(self, ctx, member: Member):
        """Show how many cautions/mutes a user has."""
        warnings = await self.config.guild(ctx.guild).warnings()
        mutes = await self.config.guild(ctx.guild).mutes()
        warning_count = warnings.get(str(member.id), 0)
        mute_count = mutes.get(str(member.id), 0)

        embed = Embed(title=f"{member.name}'s Cautions", color=0xff0000)
        embed.add_field(name="Warnings", value=warning_count)
        embed.add_field(name="Mutes", value=mute_count)
        embed.set_footer(text=datetime.now().strftime("%m/%d/%Y %I:%M %p"))

        await ctx.send(embed=embed)

    @commands.command()
    async def history(self, ctx, member: Member):
        """Show the history of mutes, warns, kicks, and timeouts for a user."""
        warnings = await self.config.guild(ctx.guild).warnings()
        mutes = await self.config.guild(ctx.guild).mutes()
        kicks = await self.config.guild(ctx.guild).kicks()
        timeouts = await self.config.guild(ctx.guild).timeouts()
        
        warning_count = warnings.get(str(member.id), 0)
        mute_count = mutes.get(str(member.id), 0)
        kick_count = kicks.get(str(member.id), 0)
        timeout_count = timeouts.get(str(member.id), 0)
        
        embed = Embed(title=f"{member.name}'s History", color=0x00ff00)
        embed.add_field(name="Warnings", value=warning_count)
        embed.add_field(name="Mutes", value=mute_count)
        embed.add_field(name="Kicks", value=kick_count)
        embed.add_field(name="Timeouts", value=timeout_count)
        await ctx.send(embed=embed)

    @commands.command(name="clearcautions")
    @commands.has_permissions(manage_roles=True)
    async def clear_warnings(self, ctx, member: Member):
        """Clear all warnings from a user."""
        warnings = await self.config.guild(ctx.guild).warnings()
        if str(member.id) in warnings:
            warnings[str(member.id)] = 0
            await self.config.guild(ctx.guild).warnings.set(warnings)
            await ctx.send(f"All warnings for {member.mention} have been cleared.")
        else:
            await ctx.send(f"{member.mention} has no warnings.")

    async def log_action(self, ctx, action: str, member: Member, reason: str = None):
        """Log moderation actions to the log channel."""
        embed = Embed(title=action, description=f"A member was {action.lower()}ed.", color=0xff0000)
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        embed.add_field(name="Reason", value=reason or "No reason provided")
        embed.set_footer(text=datetime.now().strftime("%m/%d/%Y %I:%M %p"))

        log_channel_id = await self.config.guild(ctx.guild).log_channel()
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)

    async def increment_stat(self, guild_id: int, member_id: int, stat: str):
        """Increment a specific stat for a member."""
        stats = await self.config.guild_from_id(guild_id).get_raw(stat, default={})
        if str(member_id) not in stats:
            stats[str(member_id)] = 0
        stats[str(member_id)] += 1
        await self.config.guild_from_id(guild_id).set_raw(stat, value=stats)

def setup(bot):
    bot.add_cog(Moderation(bot))
