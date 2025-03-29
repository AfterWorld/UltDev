from redbot.core import commands, Config, checks
from discord import Embed, Member, TextChannel, Role
from datetime import datetime, timedelta
import discord
import asyncio
import time
from collections import deque
from typing import Optional

class Moderation(commands.Cog):
    """Enhanced moderation cog with point-based warning system."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        
        # Default guild settings
        default_guild = {
            "log_channel": None,
            "mute_role": None,
            "staff_role": None,  # Added staff role configuration
            "warning_expiry_days": 30,  # Default warning expiry time in days
            "action_thresholds": {
                # Format: "points": {"action": "action_type", "duration": duration_in_minutes, "reason": "reason"}
                "3": {"action": "mute", "duration": 30, "reason": "Exceeded 3 warning points"},
                "5": {"action": "timeout", "duration": 60, "reason": "Exceeded 5 warning points"},
                "10": {"action": "kick", "reason": "Exceeded 10 warning points"}
            },
            "members": {}  # Store member warnings and history here
        }
        
        # Add member_roles default for storing roles during mute
        default_member = {
            "original_roles": [],
            "muted_until": None
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        
        # Rate limiting protection
        self.rate_limit = {
            "message_queue": {},  # Per-channel message queue
            "command_cooldown": {},  # Per-guild command cooldown
            "global_cooldown": deque(maxlen=10),  # Global command timestamps
        }
        
        # Background task for expiring warnings
        self.warning_cleanup_task = self.bot.loop.create_task(self.check_expired_warnings())
        
        # Background task for unmuting users
        self.unmute_check_task = self.bot.loop.create_task(self.check_mutes())
    
    def cog_unload(self):
        """Called when the cog is unloaded."""
        self.warning_cleanup_task.cancel()
        self.unmute_check_task.cancel()

    # Add a custom check for staff members
    async def is_staff_or_admin(self, ctx):
        """Check if the user is staff, has manage_roles, or is admin/mod."""
        if ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_roles:
            return True
            
        # Check for staff role
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        if staff_role_id:
            staff_role = ctx.guild.get_role(staff_role_id)
            if staff_role and staff_role in ctx.author.roles:
                return True
                
        return False

    async def check_mutes(self):
        """Background task to check and remove expired mutes."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Check all guilds for muted members
                for guild in self.bot.guilds:
                    # Get the mute role
                    mute_role_id = await self.config.guild(guild).mute_role()
                    if not mute_role_id:
                        continue
                        
                    mute_role = guild.get_role(mute_role_id)
                    if not mute_role:
                        continue
                    
                    # Get all members and check their mute status
                    guild_data = await self.config.guild(guild).all()
                    members_data = guild_data.get("members", {})
                    current_time = datetime.utcnow().timestamp()
                    
                    for member_id, member_data in members_data.items():
                        # Skip if no mute end time
                        muted_until = member_data.get("muted_until")
                        if not muted_until:
                            continue
                            
                        # Check if mute has expired
                        if current_time > muted_until:
                            try:
                                # Get member
                                member = guild.get_member(int(member_id))
                                if not member:
                                    continue
                                
                                # Check if they still have the mute role
                                if mute_role in member.roles:
                                    # Restore original roles
                                    await self.restore_member_roles(guild, member)
                                    
                                    # Log unmute
                                    await self.log_action(
                                        guild, 
                                        "Auto-Unmute", 
                                        member, 
                                        self.bot.user, 
                                        "Temporary mute duration expired"
                                    )
                            except Exception as e:
                                print(f"Error during automatic unmute check: {e}")
            
            except Exception as e:
                print(f"Error in mute check task: {e}")
            
            # Check every minute
            await asyncio.sleep(60)

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
                                        await self.safe_send_message(log_channel, embed=embed)
                    
                    # Save updated data back to config
                    await self.config.guild(guild).members.set(members_data)
            
            except Exception as e:
                print(f"Error in warning expiry check: {e}")
            
            # Check every 6 hours
            await asyncio.sleep(21600)

    async def safe_send_message(self, channel, content=None, *, embed=None, file=None):
        """
        Rate-limited message sending to avoid hitting Discord's API limits.
        
        This function queues messages and sends them with a delay if too many
        messages are being sent to the same channel in a short period.
        """
        if not channel:
            return None
            
        channel_id = str(channel.id)
        
        # Initialize queue for this channel if it doesn't exist
        if channel_id not in self.rate_limit["message_queue"]:
            self.rate_limit["message_queue"][channel_id] = {
                "queue": [],
                "last_send": 0,
                "processing": False
            }
            
        # Add message to queue
        message_data = {"content": content, "embed": embed, "file": file}
        self.rate_limit["message_queue"][channel_id]["queue"].append(message_data)
        
        # Start processing queue if not already running
        if not self.rate_limit["message_queue"][channel_id]["processing"]:
            self.rate_limit["message_queue"][channel_id]["processing"] = True
            return await self.process_message_queue(channel)
            
        return None

    async def process_message_queue(self, channel):
        """Process the message queue for a channel with rate limiting."""
        channel_id = str(channel.id)
        queue_data = self.rate_limit["message_queue"][channel_id]
        
        try:
            while queue_data["queue"]:
                # Get the next message
                message_data = queue_data["queue"][0]
                
                # Check if we need to delay sending (rate limit prevention)
                current_time = time.time()
                time_since_last = current_time - queue_data["last_send"]
                
                # If less than 1 second since last message, wait
                if time_since_last < 1:
                    await asyncio.sleep(1 - time_since_last)
                
                # Send the message
                try:
                    await channel.send(
                        content=message_data["content"],
                        embed=message_data["embed"],
                        file=message_data["file"]
                    )
                    queue_data["last_send"] = time.time()
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limit hit
                        retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                        print(f"Rate limit hit, waiting {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        continue  # Try again without removing from queue
                    else:
                        print(f"Error sending message: {e}")
                
                # Remove sent message from queue
                queue_data["queue"].pop(0)
                
                # Small delay between messages
                await asyncio.sleep(0.5)
        
        except Exception as e:
            print(f"Error processing message queue: {e}")
        
        finally:
            # Mark queue as not processing
            queue_data["processing"] = False

    @commands.group(name="cautionset")
    @commands.admin_or_permissions(administrator=True)
    async def caution_settings(self, ctx):
        """Configure the warning system settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @caution_settings.command(name="staffrole")
    @commands.admin_or_permissions(administrator=True)
    async def set_staff_role(self, ctx, role: Optional[Role] = None):
        """Set the staff role that can use moderation commands."""
        if role is None:
            # If no role is provided, show the current staff role
            current_role_id = await self.config.guild(ctx.guild).staff_role()
            if current_role_id:
                current_role = ctx.guild.get_role(current_role_id)
                if current_role:
                    await ctx.send(f"Current staff role: {current_role.mention}")
                else:
                    await ctx.send("Staff role is set but could not be found (it may have been deleted)")
            else:
                await ctx.send("No staff role is currently set.")
            return
            
        await self.config.guild(ctx.guild).staff_role.set(role.id)
        await ctx.send(f"Staff role set to {role.mention}")

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
    @commands.check(is_staff_or_admin)
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
        await self.safe_send_message(ctx.channel, f"{member.mention} has been cautioned.", embed=embed)
        
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
                # Get the mute role
                mute_role_id = await self.config.guild(ctx.guild).mute_role()
                if not mute_role_id:
                    await self.safe_send_message(ctx.channel, "Mute role not found. Please set up a mute role with !setupmute")
                    return
                
                mute_role = ctx.guild.get_role(mute_role_id)
                if not mute_role:
                    await self.safe_send_message(ctx.channel, "Mute role not found. Please set up a mute role with !setupmute")
                    return
                
                # Store member's current roles (except @everyone)
                current_roles = [role.id for role in member.roles if not role.is_default()]
                
                # Store original roles to restore later
                await self.config.member(member).original_roles.set(current_roles)
                
                # Set muted_until time if duration provided
                if duration:
                    muted_until = datetime.utcnow() + timedelta(minutes=duration)
                    await self.config.member(member).muted_until.set(muted_until.timestamp())
                
                # Remove all roles and add mute role
                try:
                    # First remove all roles except @everyone
                    roles_to_remove = [role for role in member.roles if not role.is_default()]
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason=f"Applying mute: {reason}")
                    
                    # Then add the mute role 
                    await member.add_roles(mute_role, reason=reason)
                    
                    await self.safe_send_message(ctx.channel, f"{member.mention} has been muted for {duration} minutes due to: {reason}")
                except discord.Forbidden:
                    await self.safe_send_message(ctx.channel, "I don't have permission to manage roles for this member.")
                    return
                except Exception as e:
                    await self.safe_send_message(ctx.channel, f"Error applying mute: {str(e)}")
                    return
                
                # Log the mute action
                await self.log_action(ctx.guild, "Auto-Mute", member, self.bot.user, reason,
                                    extra_fields=[{"name": "Duration", "value": f"{duration} minutes"}])
                
                # Set up automatic unmute if duration provided
                if duration:
                    self.bot.loop.create_task(self.unmute_after_delay(ctx.guild, member, duration, reason))
            
            elif action == "timeout":
                until = datetime.utcnow() + timedelta(minutes=duration)
                await member.timeout(until=until, reason=reason)
                await self.safe_send_message(ctx.channel, f"{member.mention} has been timed out for {duration} minutes due to: {reason}")
                await self.log_action(ctx.guild, "Auto-Timeout", member, self.bot.user, reason,
                                    extra_fields=[{"name": "Duration", "value": f"{duration} minutes"}])
            
            elif action == "kick":
                await member.kick(reason=reason)
                await self.safe_send_message(ctx.channel, f"{member.mention} has been kicked due to: {reason}")
                await self.log_action(ctx.guild, "Auto-Kick", member, self.bot.user, reason)
            
            elif action == "ban":
                await member.ban(reason=reason)
                await self.safe_send_message(ctx.channel, f"{member.mention} has been banned due to: {reason}")
                await self.log_action(ctx.guild, "Auto-Ban", member, self.bot.user, reason)
                
        except Exception as e:
            await self.safe_send_message(ctx.channel, f"Failed to apply automatic {action}: {str(e)}")
            print(f"Error in apply_threshold_action: {e}")

    @commands.command(name="quiet")
    @commands.check(is_staff_or_admin)
    async def mute_member(self, ctx, member: Member, duration: int = 30, *, reason: str = None):
        """Mute a member for the specified duration (in minutes)."""
        try:
            # Get mute role
            mute_role_id = await self.config.guild(ctx.guild).mute_role()
            if not mute_role_id:
                return await ctx.send("Mute role not set up. Please use !setupmute first.")
            
            mute_role = ctx.guild.get_role(mute_role_id)
            if not mute_role:
                return await ctx.send("Mute role not found. Please use !setupmute to create a new one.")
            
            # Store member's current roles (except @everyone)
            current_roles = [role.id for role in member.roles if not role.is_default()]
            
            # Store original roles to restore later
            await self.config.member(member).original_roles.set(current_roles)
            
            # Set muted_until time
            muted_until = datetime.utcnow() + timedelta(minutes=duration)
            await self.config.member(member).muted_until.set(muted_until.timestamp())
            
            # First remove all roles except @everyone
            roles_to_remove = [role for role in member.roles if not role.is_default()]
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Manual mute: {reason}")
            
            # Then add the mute role
            await member.add_roles(mute_role, reason=f"Manual mute: {reason}")
            
            # Confirm and log
            await ctx.send(f"{member.mention} has been muted for {duration} minutes. Reason: {reason or 'No reason provided'}")
            
            # Log action
            await self.log_action(ctx.guild, "Mute", member, ctx.author, reason,
                                extra_fields=[{"name": "Duration", "value": f"{duration} minutes"}])
            
            # Schedule unmute
            self.bot.loop.create_task(self.unmute_after_delay(ctx.guild, member, duration, reason))
            
        except discord.Forbidden:
            await ctx.send("I don't have permission to manage roles for this member.")
        except Exception as e:
            await ctx.send(f"Error applying mute: {str(e)}")
            print(f"Error in mute_member command: {e}")

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
        await self.restore_member_roles(guild, member)

    async def restore_member_roles(self, guild, member):
        """Restore a member's roles after unmuting them."""
        try:
            # Get the mute role
            mute_role = await self.get_mute_role(guild)
            
            # Get original roles
            original_role_ids = await self.config.member(member).original_roles()
            
            # First remove mute role if they have it
            if mute_role and mute_role in member.roles:
                await member.remove_roles(mute_role, reason="Unmuting member")
            
            # Restore original roles
            if original_role_ids:
                roles_to_restore = []
                for role_id in original_role_ids:
                    role = guild.get_role(role_id)
                    if role and role != mute_role:
                        roles_to_restore.append(role)
                
                if roles_to_restore:
                    await member.add_roles(*roles_to_restore, reason="Restoring roles after unmute")
            
            # Clear stored data
            await self.config.member(member).original_roles.set([])
            await self.config.member(member).muted_until.set(None)
            
            # Log the unmute action
            log_channel_id = await self.config.guild(guild).log_channel()
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    await self.safe_send_message(log_channel, f"{member.mention} has been unmuted.")
            
        except Exception as e:
            print(f"Error restoring member roles: {e}")
            # Try to get a channel to send the error
            log_channel_id = await self.config.guild(guild).log_channel()
            if log_channel_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel:
                    await self.safe_send_message(log_channel, f"Error unmuting {member.mention}: {str(e)}")

    @commands.command(name="unquiet")
    @commands.check(is_staff_or_admin)
    async def custom_unmute(self, ctx, member: Member):
        """Unmute a member."""
        mute_role = await self.get_mute_role(ctx.guild)
        
        if mute_role and mute_role in member.roles:
            await self.restore_member_roles(ctx.guild, member)
            await ctx.send(f"{member.mention} has been unmuted.")
            await self.log_action(ctx.guild, "Unmute", member, ctx.author)
        else:
            await ctx.send(f"{member.mention} is not muted.")

    @commands.command(name="cautions")
    async def list_warnings(self, ctx, member: Member = None):
        """
        List all active warnings for a member.
        Members can check themselves, staff can check other members.
        """
        if member is None:
            member = ctx.author
        
        # Check permissions if checking someone else
        if member != ctx.author:
            # Check if user has staff role or management permissions
            is_staff = await self.is_staff_or_admin(ctx)
            if not is_staff:
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
    @commands.check(is_staff_or_admin)
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
    @commands.check(is_staff_or_admin)
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
