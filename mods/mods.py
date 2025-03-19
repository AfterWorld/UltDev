from redbot.core import commands, Config
from discord import Embed, Member, TextChannel
from datetime import datetime, timedelta
import discord
import asyncio

class Moderation(commands.Cog):
    """Enhanced moderation cog with point-based warning system."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        
        # Default guild settings
        default_guild = {
            "log_channel": None,
            "mute_role": None,
            "warning_expiry_days": 30,  # Default warning expiry time in days
            "action_thresholds": {
                # Format: "points": {"action": "action_type", "duration": duration_in_minutes, "reason": "reason"}
                "3": {"action": "mute", "duration": 30, "reason": "Exceeded 3 warning points"},
                "5": {"action": "timeout", "duration": 60, "reason": "Exceeded 5 warning points"},
                "10": {"action": "kick", "reason": "Exceeded 10 warning points"}
            },
            "members": {}  # Store member warnings and history here
        }
        
        self.config.register_guild(**default_guild)
        
        # Background task for expiring warnings
        self.warning_cleanup_task = self.bot.loop.create_task(self.check_expired_warnings())
    
    def cog_unload(self):
        """Called when the cog is unloaded."""
        self.warning_cleanup_task.cancel()

    async def check_expired_warnings(self):
        """Background task to check and remove expired warnings."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Iterate through all guilds
                for guild in self.bot.guilds:
                    guild_data = await self.config.guild(guild).all()
                    expiry_days = guild_data["warning_expiry_days"]
                    members_data = guild_data.get("members", {})
                    current_time = datetime.utcnow().timestamp()
                    
                    # Check each member's warnings
                    for member_id, member_data in members_data.items():
                        warnings = member_data.get("warnings", [])
                        updated_warnings = []
                        
                        for warning in warnings:
                            issue_time = warning.get("timestamp", 0)
                            expiry_time = issue_time + (expiry_days * 86400)  # Convert days to seconds
                            
                            # Keep warning if not expired
                            if current_time < expiry_time:
                                updated_warnings.append(warning)
                        
                        # Update if warnings were removed
                        if len(warnings) != len(updated_warnings):
                            members_data[member_id]["warnings"] = updated_warnings
                            # Recalculate total points
                            total_points = sum(w.get("points", 1) for w in updated_warnings)
                            members_data[member_id]["total_points"] = total_points
                            
                            # Log that warnings were cleared due to expiry
                            log_channel_id = guild_data.get("log_channel")
                            if log_channel_id:
                                log_channel = self.bot.get_channel(log_channel_id)
                                if log_channel:
                                    member = guild.get_member(int(member_id))
                                    if member:
                                        embed = Embed(
                                            title="Warnings Expired",
                                            description=f"Some warnings for {member.mention} have expired.",
                                            color=0x00ff00
                                        )
                                        embed.add_field(name="Current Points", value=str(total_points))
                                        embed.set_footer(text=datetime.utcnow().strftime("%m/%d/%Y %I:%M %p"))
                                        await log_channel.send(embed=embed)
                    
                    # Save updated data back to config
                    await self.config.guild(guild).members.set(members_data)
            
            except Exception as e:
                print(f"Error in warning expiry check: {e}")
            
            # Check every 6 hours
            await asyncio.sleep(21600)

    @commands.group(name="cautionset")
    @commands.admin_or_permissions(administrator=True)
    async def caution_settings(self, ctx):
        """Configure the warning system settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @caution_settings.command(name="expiry")
    async def set_warning_expiry(self, ctx, days: int):
        """Set how many days until warnings expire automatically."""
        if days < 1:
            return await ctx.send("Expiry time must be at least 1 day.")
        
        await self.config.guild(ctx.guild).warning_expiry_days.set(days)
        await ctx.send(f"Warnings will now expire after {days} days.")

    @caution_settings.command(name="setthreshold")
    async def set_action_threshold(self, ctx, points: int, action: str, duration: int = None, *, reason: str = None):
        """
        Set an automatic action to trigger at a specific warning threshold.
        
        Actions: mute, timeout, kick, ban
        Duration (in minutes) is required for mute and timeout actions.
        """
        valid_actions = ["mute", "timeout", "kick", "ban"]
        if action.lower() not in valid_actions:
            return await ctx.send(f"Invalid action. Choose from: {', '.join(valid_actions)}")
        
        if action.lower() in ["mute", "timeout"] and duration is None:
            return await ctx.send(f"Duration (in minutes) is required for {action} action.")
        
        thresholds = await self.config.guild(ctx.guild).action_thresholds()
        
        # Create new threshold entry
        new_threshold = {"action": action.lower()}
        
        if duration:
            new_threshold["duration"] = duration
            
        if reason:
            new_threshold["reason"] = reason
        else:
            new_threshold["reason"] = f"Exceeded {points} warning points"
        
        # Save the new threshold
        thresholds[str(points)] = new_threshold
        await self.config.guild(ctx.guild).action_thresholds.set(thresholds)
        
        # Confirmation message
        confirmation = f"When a member reaches {points} warning points, they will be {action.lower()}ed"
        if duration:
            confirmation += f" for {duration} minutes"
        confirmation += f" with reason: {new_threshold['reason']}"
        
        await ctx.send(confirmation)

    @caution_settings.command(name="removethreshold")
    async def remove_action_threshold(self, ctx, points: int):
        """Remove an automatic action threshold."""
        thresholds = await self.config.guild(ctx.guild).action_thresholds()
        
        if str(points) in thresholds:
            del thresholds[str(points)]
            await self.config.guild(ctx.guild).action_thresholds.set(thresholds)
            await ctx.send(f"Removed action threshold for {points} warning points.")
        else:
            await ctx.send(f"No action threshold set for {points} warning points.")

    @caution_settings.command(name="showthresholds")
    async def show_action_thresholds(self, ctx):
        """Show all configured automatic action thresholds."""
        thresholds = await self.config.guild(ctx.guild).action_thresholds()
        
        if not thresholds:
            return await ctx.send("No action thresholds are configured.")
        
        embed = Embed(title="Warning Action Thresholds", color=0x00ff00)
        
        # Sort thresholds by point value
        sorted_thresholds = sorted(thresholds.items(), key=lambda x: int(x[0]))
        
        for points, data in sorted_thresholds:
            action = data["action"]
            duration = data.get("duration", "N/A")
            reason = data.get("reason", f"Exceeded {points} warning points")
            
            value = f"Action: {action.capitalize()}\n"
            if action in ["mute", "timeout"]:
                value += f"Duration: {duration} minutes\n"
            value += f"Reason: {reason}"
            
            embed.add_field(name=f"{points} Warning Points", value=value, inline=False)
        
        await ctx.send(embed=embed)

    @caution_settings.command(name="setlogchannel")
    async def set_log_channel(self, ctx, channel: TextChannel = None):
        """Set the channel where moderation actions will be logged."""
        if channel is None:
            channel = ctx.channel
            
        await self.config.guild(ctx.guild).log_channel.set(channel.id)
        await ctx.send(f"Log channel set to {channel.mention}")

    @commands.command(name="caution")
    @commands.has_permissions(manage_roles=True)
    async def warn_member(self, ctx, member: Member, points: int = 1, *, reason: str = None):
        """
        Issue a caution/warning to a member with optional point value.
        Default is 1 point if not specified.
        """
        if points < 1:
            return await ctx.send("Warning points must be at least 1.")
        
        # Get current member data
        guild_data = await self.config.guild(ctx.guild).all()
        members_data = guild_data.get("members", {})
        
        # Initialize member data if not exists
        member_id = str(member.id)
        if member_id not in members_data:
            members_data[member_id] = {
                "warnings": [],
                "total_points": 0
            }
        
        # Create warning entry
        warning = {
            "points": points,
            "reason": reason or "No reason provided",
            "moderator_id": ctx.author.id,
            "timestamp": datetime.utcnow().timestamp(),
            "expiry": (datetime.utcnow() + timedelta(days=guild_data["warning_expiry_days"])).timestamp()
        }
        
        # Add warning and update total points
        members_data[member_id]["warnings"].append(warning)
        members_data[member_id]["total_points"] = sum(w.get("points", 1) for w in members_data[member_id]["warnings"])
        total_points = members_data[member_id]["total_points"]
        
        # Save updated data
        await self.config.guild(ctx.guild).members.set(members_data)
        
        # Create warning embed
        embed = Embed(title=f"Warning Issued", color=0xff9900)
        embed.add_field(name="Member", value=member.mention)
        embed.add_field(name="Moderator", value=ctx.author.mention)
        embed.add_field(name="Points", value=str(points))
        embed.add_field(name="Total Points", value=str(total_points))
        embed.add_field(name="Reason", value=warning["reason"], inline=False)
        embed.add_field(name="Expires", value=f"<t:{int(warning['expiry'])}:R>", inline=False)
        embed.set_footer(text=datetime.utcnow().strftime("%m/%d/%Y %I:%M %p"))
        
        # Send warning in channel and log
        await ctx.send(f"{member.mention} has been cautioned.", embed=embed)
        
        # Log the warning
        await self.log_action(ctx.guild, "Warning", member, ctx.author, warning["reason"], 
                             extra_fields=[
                                 {"name": "Points", "value": str(points)},
                                 {"name": "Total Points", "value": str(total_points)}
                             ])
        
        # Check if any action thresholds were reached
        thresholds = guild_data.get("action_thresholds", {})
        
        # Get thresholds that match or are lower than current points, then get highest
        matching_thresholds = []
        for threshold_points, action_data in thresholds.items():
            if int(threshold_points) <= total_points:
                matching_thresholds.append((int(threshold_points), action_data))
        
        if matching_thresholds:
            # Sort by threshold value (descending) to get highest matching threshold
            matching_thresholds.sort(key=lambda x: x[0], reverse=True)
            threshold_points, action_data = matching_thresholds[0]
            
            # Check if this threshold has already been applied (to prevent repeated actions)
            if not self.has_action_been_applied(members_data[member_id], threshold_points):
                # Mark this threshold as applied
                if "applied_thresholds" not in members_data[member_id]:
                    members_data[member_id]["applied_thresholds"] = []
                members_data[member_id]["applied_thresholds"].append(threshold_points)
                await self.config.guild(ctx.guild).members.set(members_data)
                
                # Apply the action
                await self.apply_threshold_action(ctx, member, action_data)

    def has_action_been_applied(self, member_data, threshold_points):
        """Check if an action threshold has already been applied to prevent repeated actions."""
        applied_thresholds = member_data.get("applied_thresholds", [])
        return threshold_points in applied_thresholds

    async def apply_threshold_action(self, ctx, member, action_data):
        """Apply an automatic action based on crossed threshold."""
        action = action_data["action"]
        reason = action_data.get("reason", "Warning threshold exceeded")
        duration = action_data.get("duration")
        
        try:
            if action == "mute":
                # Find or create mute role
                mute_role = await self.get_mute_role(ctx.guild)
                if not mute_role:
                    await ctx.send("Mute role not found. Please set up a mute role.")
                    return
                
                await member.add_roles(mute_role, reason=reason)
                await ctx.send(f"{member.mention} has been muted due to: {reason}")
                
                if duration:
                    # Schedule unmute
                    self.bot.loop.create_task(self.unmute_after_delay(ctx.guild, member, duration, reason))
            
            elif action == "timeout":
                until = datetime.utcnow() + timedelta(minutes=duration)
                await member.timeout(until=until, reason=reason)
                await ctx.send(f"{member.mention} has been timed out for {duration} minutes due to: {reason}")
            
            elif action == "kick":
                await member.kick(reason=reason)
                await ctx.send(f"{member.mention} has been kicked due to: {reason}")
            
            elif action == "ban":
                await member.ban(reason=reason)
                await ctx.send(f"{member.mention} has been banned due to: {reason}")
            
            # Log the automated action
            await self.log_action(ctx.guild, f"Auto-{action.capitalize()}", member, self.bot.user, reason,
                                 extra_fields=[{"name": "Duration", "value": f"{duration} minutes"} if duration else None])
                
        except Exception as e:
            await ctx.send(f"Failed to apply automatic {action}: {str(e)}")

    async def get_mute_role(self, guild):
        """Get the mute role for the guild or create one if it doesn't exist."""
        # Check if we have a saved mute role ID
        mute_role_id = await self.config.guild(guild).mute_role()
        mute_role = None
        
        if mute_role_id:
            mute_role = guild.get_role(mute_role_id)
        
        if not mute_role:
            mute_role = discord.utils.get(guild.roles, name="Muted")
        
        return mute_role

    @commands.command(name="setupmute")
    @commands.has_permissions(administrator=True)
    async def setup_mute_role(self, ctx):
        """Set up the muted role for the server."""
        try:
            # Create a new role
            mute_role = await ctx.guild.create_role(name="Muted", reason="Setup for moderation")
            
            # Position the role
            bot_member = ctx.guild.me
            bot_roles = bot_member.roles
            if len(bot_roles) > 1:
                highest_bot_role = max([r for r in bot_roles if not r.is_default()], key=lambda r: r.position)
                position = highest_bot_role.position - 1
                
                # Set role position
                positions = {mute_role: position}
                await ctx.guild.edit_role_positions(positions)
            
            # Save the role ID
            await self.config.guild(ctx.guild).mute_role.set(mute_role.id)
            
            # Set up permissions for all channels
            status_msg = await ctx.send("Setting up permissions for the mute role... This may take a moment.")
            
            # First set permissions for all categories
            for category in ctx.guild.categories:
                await category.set_permissions(mute_role, 
                                           send_messages=False, 
                                           speak=False, 
                                           add_reactions=False,
                                           create_public_threads=False,
                                           create_private_threads=False,
                                           send_messages_in_threads=False)
            
            # Then handle any channels that don't have a category
            for channel in [c for c in ctx.guild.channels if c.category is None]:
                await channel.set_permissions(mute_role, 
                                           send_messages=False, 
                                           speak=False, 
                                           add_reactions=False,
                                           create_public_threads=False,
                                           create_private_threads=False,
                                           send_messages_in_threads=False)
            
            await status_msg.edit(content=f"✅ Mute role setup complete! The role {mute_role.mention} has been configured.")
            
        except Exception as e:
            await ctx.send(f"Failed to set up mute role: {str(e)}")

    async def unmute_after_delay(self, guild, member, duration, reason):
        """Unmute a member after a specified delay."""
        await asyncio.sleep(duration * 60)
        
        # Get the mute role
        mute_role = await self.get_mute_role(guild)
        
        if mute_role and mute_role in member.roles:
            try:
                await member.remove_roles(mute_role, reason=f"Temporary mute expired: {reason}")
                
                # Get log channel
                log_channel_id = await self.config.guild(guild).log_channel()
                if log_channel_id:
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel:
                        embed = Embed(title="Auto-Unmute", color=0x00ff00)
                        embed.add_field(name="Member", value=member.mention)
                        embed.add_field(name="Reason", value="Temporary mute duration expired")
                        embed.set_footer(text=datetime.utcnow().strftime("%m/%d/%Y %I:%M %p"))
                        await log_channel.send(embed=embed)
            except Exception as e:
                print(f"Error unmuting member {member.id}: {e}")

    @commands.command(name="cautions")
    async def list_warnings(self, ctx, member: Member = None):
        """
        List all active warnings for a member.
        Moderators can check other members. Members can check themselves.
        """
        if member is None:
            member = ctx.author
        
        # Check permissions if checking someone else
        if member != ctx.author and not ctx.author.guild_permissions.manage_roles:
            return await ctx.send("You don't have permission to view other members' warnings.")
        
        # Get member data
        guild_data = await self.config.guild(ctx.guild).all()
        members_data = guild_data.get("members", {})
        member_data = members_data.get(str(member.id), {"warnings": [], "total_points": 0})
        
        warnings = member_data.get("warnings", [])
        
        if not warnings:
            return await ctx.send(f"{member.mention} has no active warnings.")
        
        # Create embed
        embed = Embed(title=f"Warnings for {member.display_name}", color=0xff9900)
        embed.add_field(name="Total Points", value=str(member_data.get("total_points", 0)))
        
        # List all warnings
        for i, warning in enumerate(warnings, start=1):
            moderator = ctx.guild.get_member(warning.get("moderator_id"))
            moderator_mention = moderator.mention if moderator else "Unknown Moderator"
            
            # Format timestamp for display
            timestamp = warning.get("timestamp", 0)
            issued_time = f"<t:{int(timestamp)}:R>"
            
            # Format expiry timestamp
            expiry = warning.get("expiry", 0)
            expiry_time = f"<t:{int(expiry)}:R>"
            
            # Build warning details
            value = f"**Points:** {warning.get('points', 1)}\n"
            value += f"**Reason:** {warning.get('reason', 'No reason provided')}\n"
            value += f"**Moderator:** {moderator_mention}\n"
            value += f"**Issued:** {issued_time}\n"
            value += f"**Expires:** {expiry_time}"
            
            embed.add_field(name=f"Warning #{i}", value=value, inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name="clearcautions")
    @commands.has_permissions(manage_roles=True)
    async def clear_warnings(self, ctx, member: Member):
        """Clear all warnings from a member."""
        # Get member data
        guild_data = await self.config.guild(ctx.guild).all()
        members_data = guild_data.get("members", {})
        
        member_id = str(member.id)
        if member_id in members_data and members_data[member_id].get("warnings"):
            # Clear warnings and points
            members_data[member_id]["warnings"] = []
            members_data[member_id]["total_points"] = 0
            
            # Clear applied thresholds too
            if "applied_thresholds" in members_data[member_id]:
                members_data[member_id]["applied_thresholds"] = []
            
            # Save data
            await self.config.guild(ctx.guild).members.set(members_data)
            
            # Confirm and log
            await ctx.send(f"All warnings for {member.mention} have been cleared.")
            await self.log_action(ctx.guild, "Clear Warnings", member, ctx.author, "Manual clearing of all warnings")
        else:
            await ctx.send(f"{member.mention} has no warnings to clear.")

    @commands.command(name="removecaution")
    @commands.has_permissions(manage_roles=True)
    async def remove_warning(self, ctx, member: Member, warning_index: int):
        """Remove a specific warning from a member by index (use 'cautions' to see indexes)."""
        if warning_index < 1:
            return await ctx.send("Warning index must be 1 or higher.")
        
        # Get member data
        guild_data = await self.config.guild(ctx.guild).all()
        members_data = guild_data.get("members", {})
        
        member_id = str(member.id)
        if member_id not in members_data or not members_data[member_id].get("warnings"):
            return await ctx.send(f"{member.mention} has no warnings.")
        
        warnings = members_data[member_id]["warnings"]
        
        if warning_index > len(warnings):
            return await ctx.send(f"Invalid warning index. {member.mention} only has {len(warnings)} warnings.")
        
        # Remove warning (adjust for 0-based index)
        removed_warning = warnings.pop(warning_index - 1)
        
        # Recalculate total points
        members_data[member_id]["total_points"] = sum(w.get("points", 1) for w in warnings)
        
        # Save data
        await self.config.guild(ctx.guild).members.set(members_data)
        
        # Confirm and log
        await ctx.send(f"Warning #{warning_index} for {member.mention} has been removed.")
        await self.log_action(
            ctx.guild, 
            "Remove Warning", 
            member, 
            ctx.author, 
            f"Manually removed warning #{warning_index}",
            extra_fields=[
                {"name": "Warning Points", "value": str(removed_warning.get("points", 1))},
                {"name": "Warning Reason", "value": removed_warning.get("reason", "No reason provided")},
                {"name": "New Total Points", "value": str(members_data[member_id]["total_points"])}
            ]
        )

    async def log_action(self, guild, action, target, moderator, reason=None, extra_fields=None):
        """Log moderation actions to the log channel."""
        log_channel_id = await self.config.guild(guild).log_channel()
        if not log_channel_id:
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
        
        embed = Embed(title=action, description=f"A moderation action has been taken.", color=0xff0000)
        embed.add_field(name="Member", value=target.mention)
        embed.add_field(name="Moderator", value=moderator.mention)
        
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        
        # Add any extra fields
        if extra_fields:
            for field in extra_fields:
                if field and field.get("name") and field.get("value"):
                    embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", True))
        
        embed.set_footer(text=datetime.utcnow().strftime("%m/%d/%Y %I:%M %p"))
        await log_channel.send(embed=embed)

def setup(bot):
    bot.add_cog(Moderation(bot))
