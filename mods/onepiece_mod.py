import discord
from redbot.core import commands, checks, modlog, Config
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta
from redbot.core.utils.mod import get_audit_reason
from redbot.core.bot import Red
from datetime import timedelta, datetime, timezone
import asyncio
import re
import random
import pytz
from typing import Optional  # Add this line

original_commands = {}
original_permissions_command = None

class MuteTime(commands.Converter):
    async def convert(self, ctx, argument):
        matches = re.match(r"(\d+)\s*(m(?:in(?:ute)?s?)?|h(?:ours?)?|d(?:ays?)?|w(?:eeks?)?)?$", argument.lower())
        if matches:
            time = int(matches.group(1))
            unit = matches.group(2) or 'm'
            if unit.startswith('m'):
                return {"duration": timedelta(minutes=time), "reason": None}
            elif unit.startswith('h'):
                return {"duration": timedelta(hours=time), "reason": None}
            elif unit.startswith('d'):
                return {"duration": timedelta(days=time), "reason": None}
            elif unit.startswith('w'):
                return {"duration": timedelta(weeks=time), "reason": None}
        return {"duration": None, "reason": argument}

class OnePieceMod(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "muted_users": {},
            "restricted_channels": {},
            "minimum_image_role_id": None,
            "warned_users": {}
        }
        self.config.register_guild(**default_guild)
        self.log_channel_id = 1245208777003634698
        self.mute_role_id = 808869058476769312  # Pre-set mute role ID
        self.general_chat_id = 425068612542398476
        self.default_mute_time = timedelta(hours=24)  # Default mute time of 24 hours
        self.muted_users = {}  # Store muted users' roles
        self.ban_messages = [
            ("Looks like you're taking a trip to Impel Down!", "https://tenor.com/view/one-piece-magellan-magellan-one-piece-impel-down-gif-24849283"),
            ("You've been hit by Nami's Clima-Tact!", "https://tenor.com/view/nami-sanji-slap-one-piece-anime-gif-19985101"),
            ("Zoro got lost again, and somehow you got banned!", "https://tenor.com/view/onepiece-zoro-gif-20413728"),
            ("You've been Gum-Gum Banned!", "https://tenor.com/view/luffy-punch-onepiece-gif-11908462"),
            ("Sanji's kicking you out of the crew!", "https://tenor.com/view/sanji-one-piece-angry-flame-gif-5738862"),
            ("You've been caught in Trafalgar Law's ROOM!", "https://tenor.com/view/room-law-trafalgar-law-shambles-big-mom-gif-26718981"),
            ("Blackbeard's darkness has swallowed you!", "https://tenor.com/view/one-piece-anime-blackbeard-marshall-d-teach-gif-19895866"),
            ("You've been frozen by Aokiji's Ice Age!", "https://tenor.com/view/one-piece-kuzan-aokoji-freeze-charlotte-cracker-gif-15455402913382101990"),
            ("Buggy's Chop-Chop Fruit sent you flying!", "https://tenor.com/view/bara-bara-no-mi-bara-bara-no-mi-o-grande-one-piece-rp-gif-22513624"),
            ("Big Mom's Soul-Soul Fruit has taken your lifespan... and your server access!", "https://tenor.com/view/%E5%A4%A7%E5%AA%BDauntie-aunt-granny-grandmom-gif-12576437")
        ]

    async def log_action(self, ctx, member: discord.Member, action: str, reason: str, moderator: discord.Member = None, jump_url: str = None, image_url: str = None):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            log_message = (
                "🏴‍☠️ **Crew Log Entry** 🏴‍☠️\n\n"
                f"**Target Pirate:** {member.name} (ID: {member.id})\n"
                f"**Action Taken:** {action}\n"
                f"**Reason for Action:** {reason}\n"
            )
            if moderator:
                log_message += f"**Enforcing Officer:** {moderator.name} (ID: {moderator.id})\n"
            if jump_url:
                log_message += f"**Incident Report:** [View Incident Details]({jump_url})\n"
            if image_url:
                log_message += f"**Evidence:** [View Image]({image_url})\n"
            
            log_message += f"\nLogged at {ctx.message.created_at.strftime('%Y-%m-%d %H:%M:%S')} | One Piece Moderation"
            
            await log_channel.send(log_message)

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Warn a crew member for breaking the Pirate Code."""
        if member.bot:
            return await ctx.send("Ye can't warn a bot, ye scurvy dog!")

        if member == ctx.author:
            return await ctx.send("Ye can't warn yerself, ye barnacle-brained buffoon!")

        current_time = datetime.utcnow()
        async with self.config.guild(ctx.guild).warned_users() as warned_users:
            user_warns = warned_users.get(str(member.id), {})
            
            if user_warns and current_time - datetime.fromisoformat(user_warns['timestamp']) < timedelta(hours=24):
                # Update existing warning
                user_warns['count'] += 1
                user_warns['reasons'].append(reason)
                user_warns['timestamp'] = current_time.isoformat()
            else:
                # Create new warning
                user_warns = {
                    'count': 1,
                    'reasons': [reason],
                    'moderator': ctx.author.id,
                    'timestamp': current_time.isoformat()
                }
            
            warned_users[str(member.id)] = user_warns

        warn_count = user_warns['count']
        
        pirate_warnings = [
            f"Ahoy, {member.mention}! Ye've been given a black spot for breakin' the Pirate Code!",
            f"Shiver me timbers, {member.mention}! Ye've earned yerself a mark on the captain's log!",
            f"Blimey, {member.mention}! Ye've been caught red-handed violatin' our crew's code!",
            f"Arrr, {member.mention}! The Pirate Court has found ye guilty of misbehavior!",
            f"Avast ye, {member.mention}! Ye've been branded with the mark of the mutineer!"
        ]

        if warn_count == 1:
            warning_message = random.choice(pirate_warnings)
        else:
            warning_message = f"Aye, {member.mention}! Ye've been warned {warn_count} times in the last 24 hours! Keep this up, and ye'll be swabbin' the decks in Impel Down!"

        await ctx.send(warning_message)

        # Update or create the log message
        await self.update_warn_log(ctx.guild, member, user_warns)

        if warn_count >= 5:
            recommendation = f"⚠️ {member.mention} has received 5 or more warnings in 24 hours. Consider muting them for 30 minutes using the following command:\n`[p]mute {member.mention} 30m Multiple infractions of the Pirate Code`"
            await ctx.send(recommendation)

    async def update_warn_log(self, guild, member, warn_data):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            return  # Log channel not found

        # Check if there's an existing log message for this user's current warning period
        async for message in log_channel.history(limit=100):
            if message.author == self.bot.user and message.embeds:
                embed = message.embeds[0]
                if embed.title and embed.title.startswith(f"⚠️ Warning Log for {member.display_name}"):
                    # Update existing log message
                    new_embed = self.create_warn_embed(member, warn_data)
                    await message.edit(embed=new_embed)
                    return

        # If no existing message found, create a new one
        new_embed = self.create_warn_embed(member, warn_data)
        await log_channel.send(embed=new_embed)

    def create_warn_embed(self, member, warn_data):
        embed = discord.Embed(
            title=f"⚠️ Warning Log for {member.display_name}",
            color=discord.Color.red(),
            timestamp=datetime.fromisoformat(warn_data['timestamp'])
        )
        embed.set_thumbnail(url=member.avatar.url)
        embed.add_field(name="Warning Count", value=str(warn_data['count']), inline=False)
        embed.add_field(name="Reasons", value="\n".join(f"• {reason}" for reason in warn_data['reasons']), inline=False)
        moderator = member.guild.get_member(warn_data['moderator'])
        mod_name = moderator.display_name if moderator else "Unknown Moderator"
        embed.add_field(name="Last Updated By", value=mod_name, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        return embed

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member):
        """Check a crew member's recent warnings."""
        async with self.config.guild(ctx.guild).warned_users() as warned_users:
            user_warns = warned_users.get(str(member.id), {})

        if not user_warns:
            return await ctx.send(f"{member.mention} has a clean record, sailin' smooth seas!")

        current_time = datetime.utcnow()
        if current_time - datetime.fromisoformat(user_warns['timestamp']) >= timedelta(hours=24):
            return await ctx.send(f"{member.mention} has no warnings in the last 24 hours. They've straightened their course!")

        embed = self.create_warn_embed(member, user_warns)
        await ctx.send(embed=embed)

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def clearwarnings(self, ctx, member: discord.Member):
        """Clear all warnings for a crew member."""
        async with self.config.guild(ctx.guild).warned_users() as warned_users:
            if str(member.id) in warned_users:
                del warned_users[str(member.id)]
                await ctx.send(f"Yarr! All warnings for {member.mention} have been wiped clean. Their slate be as clear as the horizon!")
            else:
                await ctx.send(f"{member.mention} had no warnings to clear. They be sailin' with a clean record already!")

        # Update the log to reflect cleared warnings
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            async for message in log_channel.history(limit=100):
                if message.author == self.bot.user and message.embeds:
                    embed = message.embeds[0]
                    if embed.title and embed.title.startswith(f"⚠️ Warning Log for {member.display_name}"):
                        await message.delete()
                        break
        
    @commands.command()
    @checks.admin_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Disrespecting the captain's orders!"):
        """Force a crew member to walk the plank."""
        try:
            await ctx.guild.kick(member, reason=reason)
            await ctx.send(f"🦈 {member.name} has walked the plank! They'll have to find another crew or swim with the Sea Kings.")
            await self.log_action(ctx, member, "Forced to Walk the Plank", reason, moderator=ctx.author)
            
            case = await modlog.create_case(
                self.bot, ctx.guild, ctx.message.created_at, action_type="kick",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been recorded in the ship's log. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to make that crew member walk the plank!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to make that crew member walk the plank. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Mutiny against the crew!"):
        """Banish a pirate to Impel Down and erase their messages."""
        try:
            # Delete all messages from the user across all channels
            for channel in ctx.guild.text_channels:
                def check(message):
                    return message.author == member
    
                await channel.purge(limit=None, check=check)
    
            # Ban the user
            await ctx.guild.ban(member, reason=reason, delete_message_days=7)
    
            ban_message, ban_gif = random.choice(self.ban_messages)
            
            embed = discord.Embed(title="⛓️ Pirate Banished to Impel Down! ⛓️", description=f"{member.name} has been locked away!", color=0xff0000)
            embed.add_field(name="Crimes", value=reason, inline=False)
            embed.add_field(name="Warden's Note", value=ban_message, inline=False)
            embed.set_image(url=ban_gif)
            
            general_chat = self.bot.get_channel(self.general_chat_id)
            if general_chat:
                await general_chat.send(embed=embed)
            else:
                await ctx.send("Couldn't find the general chat channel. Posting here instead:", embed=embed)
            
            await self.log_action(ctx, member, "Banished to Impel Down (all messages deleted)", reason, moderator=ctx.author)
            
            case = await modlog.create_case(
                self.bot, ctx.guild, ctx.message.created_at, action_type="ban",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The traitor's crimes have been recorded in the ship's log. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to banish that pirate to Impel Down!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to banish that pirate. The Marines must be jamming our signals!")
            
    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def mute(
        self,
        ctx: commands.Context,
        users: commands.Greedy[discord.Member],
        *,
        time_and_reason: str = None
    ):
        """Banish crew members to the Void Century.

        <users...> is a space separated list of usernames, ID's, or mentions.
        [time_and_reason] is the time to mute for and/or the reason.
        Time can be specified as a number followed by m(inutes), h(ours), d(ays), or w(eeks).
        If no time is specified, the banishment will be indefinite.

        You can also attach an image as evidence for the mute.

        Examples:
        `[p]mute @member1 @member2 10m Disrupting crew meeting`
        `[p]mute @member1 1d Stealing food from the galley`
        `[p]mute @member1 Insubordination` (indefinite banishment)
        `[p]mute @member1` (indefinite banishment with no reason)
        """
        if not users:
            return await ctx.send_help()
        if ctx.me in users:
            return await ctx.send("You cannot banish the ship's Log Pose to the Void Century!")
        if ctx.author in users:
            return await ctx.send("You cannot banish yourself to the Void Century!")

        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("The Void Century role hasn't been established yet!")

        duration = None
        reason = "No reason provided"

        if time_and_reason:
            time_match = re.match(r"(\d+)\s*(m(?:in(?:ute)?s?)?|h(?:ours?)?|d(?:ays?)?|w(?:eeks?)?)", time_and_reason)
            if time_match:
                time_val = int(time_match.group(1))
                time_unit = time_match.group(2)[0].lower()
                if time_unit == 'm':
                    duration = timedelta(minutes=time_val)
                elif time_unit == 'h':
                    duration = timedelta(hours=time_val)
                elif time_unit == 'd':
                    duration = timedelta(days=time_val)
                elif time_unit == 'w':
                    duration = timedelta(weeks=time_val)
                reason = time_and_reason[time_match.end():].strip() or reason
            else:
                reason = time_and_reason

        # Check for image attachment
        image_url = None
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                image_url = attachment.url

        async with ctx.typing():
            author = ctx.message.author
            guild = ctx.guild
            audit_reason = get_audit_reason(author, reason)
            success_list = []
            
            async with self.config.guild(ctx.guild).muted_users() as muted_users:
                for user in users:
                    try:
                        # Store the user's current roles
                        self.muted_users[user.id] = [role for role in user.roles if role != ctx.guild.default_role]
                        
                        # Remove all roles and add mute role
                        await user.edit(roles=[])
                        await user.add_roles(mute_role, reason=audit_reason)
                        
                        success_list.append(user)
                        
                        # Store mute information
                        muted_users[str(user.id)] = {
                            "moderator": ctx.author.id,
                            "reason": reason,
                            "timestamp": ctx.message.created_at.isoformat(),
                            "duration": duration.total_seconds() if duration else None,
                            "jump_url": ctx.message.jump_url
                        }
                        
                        await modlog.create_case(
                            self.bot,
                            guild,
                            ctx.message.created_at,
                            "smute",
                            user,
                            author,
                            reason,
                            until=ctx.message.created_at + duration if duration else None,
                        )
                        
                        time_str = f" for {humanize_timedelta(timedelta=duration)}" if duration else " indefinitely"
                        await self.log_action(ctx, user, f"Banished to Void Century{time_str}", reason, moderator=ctx.author, jump_url=ctx.message.jump_url, image_url=image_url)
                        
                        # Schedule unmute if duration is set
                        if duration:
                            self.bot.loop.create_task(self.schedule_unmute(ctx.guild, user, duration))
                    except discord.Forbidden:
                        await ctx.send(f"I don't have the authority to banish {user.name} to the Void Century!")
                    except discord.HTTPException:
                        await ctx.send(f"There was an error trying to banish {user.name}. The currents of time must be interfering with our Log Pose!")

        if success_list:
            if len(success_list) == 1:
                msg = f"{success_list[0].name} has been banished to the Void Century{time_str}."
            else:
                msg = f"{humanize_list([f'`{u.name}`' for u in success_list])} have been banished to the Void Century{time_str}."
            await ctx.send(msg)

    async def schedule_unmute(self, guild: discord.Guild, user: discord.Member, duration: timedelta):
        """Schedule an unmute operation."""
        await asyncio.sleep(duration.total_seconds())
        
        # Check if the user is still muted
        mute_role = guild.get_role(self.mute_role_id)
        if mute_role and mute_role in user.roles:
            # Create a mock context for the unmute command
            channel = self.bot.get_channel(self.general_chat_id) or guild.text_channels[0]
            mock_message = await channel.send(f"Scheduled unmute for {user.mention}")
            ctx = await self.bot.get_context(mock_message)
            await ctx.message.delete()  # Delete the mock message
            
            await self.unmute(ctx, user, reason="Scheduled unmute: Void Century banishment has ended")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def unmute(self, ctx: commands.Context, user: discord.Member, *, reason: str = "Void Century banishment has ended"):
        """Return a crew member from the Void Century."""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("The Void Century role doesn't exist!")

        if mute_role not in user.roles:
            return await ctx.send(f"{user.name} is not banished to the Void Century. They're free to speak!")

        try:
            # Remove mute role
            await user.remove_roles(mute_role, reason=reason)
            
            # Restore original roles
            await self._restore_roles(user, reason)
            
            async with self.config.guild(ctx.guild).muted_users() as muted_users:
                muted_users.pop(str(user.id), None)
            
            message = f"🕰️ {user.name} has returned from the Void Century and can speak again! Their roles have been restored."
            await ctx.send(message)
            
            # Log the unmute action
            await self.log_action(ctx, user, "Returned from Void Century", reason, moderator=ctx.author)
            
        except discord.Forbidden:
            await ctx.send(f"I don't have the authority to return {user.name} from the Void Century!")
        except discord.HTTPException:
            await ctx.send(f"There was an error trying to return {user.name} from the Void Century. The currents of time must be interfering with our Log Pose!")

    async def _restore_roles(self, user: discord.Member, reason: str):
        """Helper method to restore roles for a user."""
        if user.id in self.muted_users:
            roles_to_add = [role for role in self.muted_users[user.id] if role not in user.roles and role < user.guild.me.top_role]
            if roles_to_add:
                await user.add_roles(*roles_to_add, reason=f"Restoring roles after unmute: {reason}")
            self.muted_users.pop(user.id, None)

    @commands.command()
    @checks.admin_or_permissions(manage_channels=True)
    async def restrict(self, ctx, channel: discord.TextChannel, role: discord.Role):
        """Restrict a channel to users with a specific role."""
        async with self.config.guild(ctx.guild).restricted_channels() as restricted:
            restricted[str(channel.id)] = role.id

        await channel.set_permissions(ctx.guild.default_role, send_messages=False, add_reactions=False)
        await channel.set_permissions(role, send_messages=True, add_reactions=True)

        await ctx.send(f"🔒 The {channel.mention} has been restricted to members with the {role.name} role or higher.")

    @commands.command()
    @checks.admin_or_permissions(manage_channels=True)
    async def unrestrict(self, ctx, channel: discord.TextChannel):
        """Remove restrictions from a channel."""
        async with self.config.guild(ctx.guild).restricted_channels() as restricted:
            if str(channel.id) in restricted:
                del restricted[str(channel.id)]

        await channel.set_permissions(ctx.guild.default_role, send_messages=None, add_reactions=None)
        await ctx.send(f"🔓 The restrictions on {channel.mention} have been removed.")

    @commands.group(name="permissions")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def new_permissions(self, ctx):
        """Manage permissions for cogs and commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @new_permissions.command(name="add")
    async def add_permission(self, ctx, cog_or_command: str, *channels: discord.TextChannel):
        """Allow a cog or command to be used in specific channels."""
        if not channels:
            return await ctx.send("Ye need to specify at least one channel, ye scurvy dog!")
        for channel in channels:
            await self._set_permission(ctx, cog_or_command, channel.id, True)
    
    @new_permissions.command(name="deny")
    async def deny_permission(self, ctx, cog_or_command: str, *channels: discord.TextChannel):
        """Deny a cog or command from being used in specific channels."""
        if not channels:
            return await ctx.send("Ye need to specify at least one channel, ye landlubber!")
        for channel in channels:
            await self._set_permission(ctx, cog_or_command, channel.id, False)
    
    @new_permissions.command(name="reset")
    async def reset_permission(self, ctx, cog_or_command: str):
        """Reset permissions for a cog or command."""
        await self._set_permission(ctx, cog_or_command, None, None)
    
    @new_permissions.command(name="list")
    async def list_permissions(self, ctx):
        """List all current permissions."""
        guild_data = await self.config.guild(ctx.guild).all()
        permissions = guild_data.get("permissions", {})
        
        if not permissions:
            return await ctx.send("There be no permissions set, ye empty-headed animal food trough wiper!")
    
        embed = discord.Embed(title="🏴‍☠️ Permissions Map 🗺️", color=discord.Color.blue())
        
        for cog_or_command, perm_data in permissions.items():
            allowed_channels = []
            denied_channels = []
            if isinstance(perm_data, dict):
                for channel_id, allowed in perm_data.items():
                    if channel_id not in ('channel', 'allowed'):
                        try:
                            channel = ctx.guild.get_channel(int(channel_id))
                            if channel:
                                if allowed:
                                    allowed_channels.append(channel.mention)
                                else:
                                    denied_channels.append(channel.mention)
                        except ValueError:
                            # If channel_id is not a valid integer, skip it
                            continue
            
            value = ""
            if allowed_channels:
                value += f"Allowed in: {', '.join(allowed_channels)}\n"
            if denied_channels:
                value += f"Denied in: {', '.join(denied_channels)}\n"
            
            if value:
                embed.add_field(name=cog_or_command, value=value, inline=False)
            else:
                embed.add_field(name=cog_or_command, value="No channel-specific permissions set", inline=False)
    
        await ctx.send(embed=embed)

    async def _set_permission(self, ctx, cog_or_command: str, channel_id: Optional[int], allowed: Optional[bool]):
        async with self.config.guild(ctx.guild).all() as guild_data:
            guild_data.setdefault("permissions", {})
            if channel_id is None and allowed is None:
                guild_data["permissions"].pop(cog_or_command, None)
                await ctx.send(f"🏴‍☠️ Permissions reset for {cog_or_command}. It's free to sail all seas now!")
            else:
                guild_data["permissions"].setdefault(cog_or_command, {})
                guild_data["permissions"][cog_or_command][str(channel_id)] = allowed
                action = "allowed to dock in" if allowed else "banned from"
                channel = ctx.guild.get_channel(channel_id)
                await ctx.send(f"🏴‍☠️ The {cog_or_command} ship is now {action} the waters of {channel.mention}!")
                
    @commands.Cog.listener()
    async def on_command(self, ctx):
        if ctx.guild is None:
            return
    
        is_allowed = await self.check_permissions(ctx, ctx.command.qualified_name)
    
        if not is_allowed:
            await ctx.send("🏴‍☠️ Shiver me timbers! Ye can't use that command in these waters, ye scurvy dog!")
            return await ctx.message.delete()
                    
    @commands.Cog.listener()
    async def on_command(self, ctx):
        if ctx.guild is None:
            return
    
        cog_name = ctx.command.cog.__class__.__name__ if ctx.command.cog else "No Cog"
        guild_data = await self.config.guild(ctx.guild).all()
        permissions = guild_data.get("permissions", {})
    
        for item in [ctx.command.qualified_name, cog_name]:
            if item in permissions:
                channel_perms = permissions[item]
                if str(ctx.channel.id) in channel_perms:
                    if not channel_perms[str(ctx.channel.id)]:
                        await ctx.send("🏴‍☠️ Shiver me timbers! This command be not allowed in these waters.")
                        return await ctx.message.delete()
                elif any(channel_perms.values()):  # If there are any allowed channels
                    allowed_channels = [ctx.guild.get_channel(int(c)) for c, a in channel_perms.items() if a]
                    allowed_channels = [c.mention for c in allowed_channels if c]
                    await ctx.send(f"🏴‍☠️ Avast ye! This command can only be used in the waters of: {', '.join(allowed_channels)}.")
                    return await ctx.message.delete()
                    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
    
        # Check if the user is new (less than 24 hours in the server)
        utc_now = datetime.now(pytz.utc)
        joined_at_utc = message.author.joined_at.replace(tzinfo=pytz.utc)
        is_new_user = (utc_now - joined_at_utc) < timedelta(hours=24)
    
        if is_new_user:
            # First check for obvious URLs
            contains_url = self.contains_url(message.content)

            if contains_url:
                await self.delete_and_warn(message, "new_user_link")
                return

            # If no obvious URL, wait a short time and check for embeds
            await asyncio.sleep(1)  # Wait for Discord to process potential embeds

            # Fetch the message again to check for embeds
            try:
                updated_message = await message.channel.fetch_message(message.id)
                if updated_message.embeds:
                    await self.delete_and_warn(updated_message, "new_user_link")
                    return
            except discord.NotFound:
                # Message was deleted, no action needed
                pass

        # Get the minimum image role
        minimum_image_role_id = await self.config.guild(message.guild).minimum_image_role_id()
        if minimum_image_role_id is None:
            return  # If no minimum role is set, don't apply any restrictions

        minimum_image_role = message.guild.get_role(minimum_image_role_id)
        if minimum_image_role is None:
            return  # If the role doesn't exist anymore, don't apply any restrictions

        # Check if the user has the minimum role or higher
        has_permission = any(role >= minimum_image_role for role in message.author.roles)

        # Filter images and GIFs for users without the minimum role or higher
        if not has_permission:
            contains_gif = re.search(r'\b(?:gif|giphy)\b', message.content, re.IGNORECASE)
            has_attachments = len(message.attachments) > 0
            if contains_gif or has_attachments or message.embeds:
                await self.delete_and_warn(message, "low_rank_image", minimum_image_role)
                return

        # Check if the channel is restricted
        restricted_channels = await self.config.guild(message.guild).restricted_channels()
        if str(message.channel.id) in restricted_channels:
            required_role_id = restricted_channels[str(message.channel.id)]
            required_role = message.guild.get_role(required_role_id)
            if required_role and not any(role >= required_role for role in message.author.roles):
                await self.delete_and_warn(message, "restricted_channel", required_role)
                return

    def contains_url(self, text):
        url_regex = re.compile(
            r'(?i)\b((?:https?://|www\d{0,3}[.]|discord[.]gg|discordapp[.]com|discord[.]com|t[.]me|twitch[.]tv|picarto[.]tv|youtube[.]com|youtu[.]be|facebook[.]com|fb[.]com|instagram[.]com|instagr[.]am|twitter[.]com|x[.]com|tumblr[.]com|reddit[.]com|reddit[.]it|linkedin[.]com|linkd[.]in|snapchat[.]com|snap[.]com|whatsapp[.]com|whatsapp[.]net|weibo[.]com|qq[.]com|qzone[.]qq[.]com|tiktok[.]com|douyin[.]com|bilibili[.]com|b23[.]tv|vk[.]com|ok[.]ru)\S*)\b')
        return re.search(url_regex, text) is not None

    async def delete_and_warn(self, message, message_type, role=None):
        await message.delete()
        await self.send_themed_message(message.channel, message.author, message_type, role)

    async def send_themed_message(self, channel, user, message_type, role=None):
        messages = {
            "new_user_link": [
                f"Avast ye, {user.mention}! New crew members can't be sharing treasure maps (links) until they've proven their sea legs for 24 hours!",
                f"Shiver me timbers, {user.mention}! Ye can't be posting mysterious scrolls (links) 'til ye've sailed with us for a full day!",
                f"Blimey, {user.mention}! No sharing secret routes (links) 'til ye've been part of the crew for 24 hours! Them's the rules of the sea!"
            ],
            "low_rank_image": [
                f"Arr, {user.mention}! Yer bounty's not high enough to be sharing wanted posters (images) yet! Ye need to reach a higher rank first!",
                f"Hold yer seahorses, {user.mention}! Only pirates of higher rank can show off their loot (images). Keep plunderin' and level up!",
                f"Yo ho ho, {user.mention}! Ye need to rank up to unfurl yer map (share images). Hoist yer Jolly Roger higher!"
            ],
            "restricted_channel": [
                f"Gaaar! {user.mention}, this be a restricted part of the ship. Only crew members of a certain rank can enter these waters!",
                f"Avast, {user.mention}! This channel be for certain ranked crew members only. Swab the poop deck and come back when ye've earned yer stripes!",
                f"Blimey, {user.mention}! This be the captain's quarters (restricted channel). Ye'll be keel-hauled if ye try to enter without permission!"
            ]
        }
    
        themed_message = random.choice(messages[message_type])
        
        if role is not None:
            themed_message = themed_message.replace("higher rank", f"the rank of {role.name} or higher")
            themed_message = themed_message.replace("certain rank", f"ranked {role.name} or higher")
        
        await channel.send(themed_message, delete_after=15)

            
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Event listener to catch manual mute role removals."""
        mute_role = before.guild.get_role(self.mute_role_id)
        if not mute_role:
            return

        if mute_role in before.roles and mute_role not in after.roles:
            # The mute role was manually removed
            await self._restore_roles(after, "Manual unmute detected")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def send_server_rules(self, ctx, channel: discord.TextChannel = None):
        """Send the full server rules and information to the specified channel."""
        if channel is None:
            channel = ctx.channel

        rules = """
# 🏴‍☠️ Grand Line Pirates' Code of Conduct 🏴‍☠️

Ahoy, fellow pirates! Welcome aboard the Grand Line Discord Server. Before ye set sail on this grand adventure, make sure to familiarize yourself with our code of conduct and Discord's Terms of Service. Remember, even pirates have rules to follow!

## 📜 Discord Terms of Service

All crew members must adhere to Discord's Terms of Service. Here are some key points:

- 🔞 You must be at least 13 years old to use Discord
- 🚫 No harassment, hate speech, or extreme political content
- 🔒 Respect others' privacy and intellectual property
- 🛡️ Don't share or promote harmful content or illegal activities
- 🤖 Don't use self-bots or user-bots

For the full terms, visit: [Discord Terms of Service](https://discord.com/\u200Bterms)

## 🏴‍☠️ Server Rules (Applies to all crew members, from cabin boys to Yonko)

1. 🤝 Respect yer fellow pirates. Swearing be allowed, but mind yer tongue and respect others' boundaries.
2. 🤐 Sensitive topics such as politics, religion, or personal matters are off-limits. Keep 'em in Davy Jones' locker!
3. 🌈 No discriminatin' against race, religion, or background. We be a diverse crew, savvy?
4. 🔇 No spammin' outside the designated areas. Don't make us walk ye off the plank!
5. 📢 Advertisin' other pirate crews (Discord servers) without permission is mutiny. Ye've been warned!
6. 🤫 Keep manga spoilers in the appropriate channels. Don't ruin the adventure for others!
7. 💡 Respect others' ideas and theories. Ask permission and give credit where it's due.
8. 📖 Read the channel topics before postin'. They contain valuable treasure maps of information!
9. 🔞 No NSFW content. Keep it family-friendly, ye scurvy dogs!
10. 👨‍⚖️ The Moderators and Admins have the final say in disputes. Respect their authority or face the consequences!
"""

        rules_part2 = """
## ⚓ Consequences for Breakin' the Code

1. ⚠️ First offense: Ye'll get a warnin' shot across the bow
2. 🔇 Second offense: Ye'll be thrown in the brig (muted)
3. 🏝️ Third offense: Ye'll be marooned (banned)

## 👑 Crew Hierarchy

- 👑 Pirate King: Server Owner
- ⭐️ Yonko: High-ranking Administrators
- ⚓️ Admirals: Senior Moderators
- 💎 Legends: Trusted friends and partners
- 👑 Shichibukai: Novice Moderators
"""

        rules_part3 = """
## 🌊 Choose Your Sea

Join one of the five seas from One Piece:
- ⭕ Grand Line 
- 🔵 East Blue 
- ⚪ West Blue 
- ⚫ North Blue 
- 🔴 South Blue 

Select your sea in the designated channel to participate in sea tournaments!

## 🏴‍☠️ Join a Pirate Crew

Enlist in one of our fearsome pirate crews:
- 🕷️ Phantom Troupe
- 🦊 Foxy Pirates
- 🐉 Revolutionary Army

Each crew has 4 ranks: Cabin Boy, First Mate, Commander, and Right Hand

## 📈 Pirate Ranking System


Now, hoist the colors and set sail for adventure! If ye have any questions, consult yer Log Pose (ping a moderator). May the winds be ever in yer favor! ⛵🌊🏝️
"""

        chunks = [rules, rules_part2, rules_part3]

        try:
            for chunk in chunks:
                await channel.send(chunk)
            await ctx.send(f"Full server rules and information sent to {channel.mention}!")
        except discord.Forbidden:
            await ctx.send("I don't have permission to send messages in that channel!")
        except discord.HTTPException:
            await ctx.send("There was an error sending the rules. Please try again later.")
            
async def setup(bot):
    global original_commands, original_permissions_command
    cog = OnePieceMod(bot)

    command_names = ["kick", "ban", "mute", "unmute"]
    for cmd_name in command_names:
        original_cmd = bot.get_command(cmd_name)
        if original_cmd:
            original_commands[cmd_name] = original_cmd
            bot.remove_command(cmd_name)

    # Store and remove the original permissions command
    original_permissions_command = bot.get_command("permissions")
    if original_permissions_command:
        bot.remove_command("permissions")

    await bot.add_cog(cog)

async def teardown(bot):
    global original_commands, original_permissions_command
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()

    # Restore the original permissions command
    if original_permissions_command:
        bot.add_command(original_permissions_command)
    original_permissions_command = None
