import discord
from discord.errors import Forbidden, HTTPException
from redbot.core import commands, checks, modlog, Config
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta
from redbot.core.utils.mod import get_audit_reason
from redbot.core.bot import Red
from datetime import timedelta, datetime, timezone
import asyncio
import re
import random
import pytz
import logging
from typing import Optional, List, Union, Dict

original_commands = {}

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
        self.mute_tasks = {}
        default_guild = {
            "general_channel_id": None,
            "main_server_id": None,
            "muted_users": {},
            "restricted_channels": {},
            "minimum_image_role_id": None,
            "warned_users": {},
            "mute_role": None,
            "notification_channel": None,
            "default_time": 0,
            "dm": False,
            "show_mod": False,
        }
        self.config.register_guild(**default_guild)
        self.mute_role_cache = {}
        self.log_channel_id = 1245208777003634698
        self.mute_role_id = 808869058476769312  # Pre-set mute role ID
        self.general_chat_id = 425068612542398476
        self.default_mute_time = timedelta(hours=24)  # Default mute time of 24 hours
        self.muted_users = {}  # Store muted users' roles
        self.reminder_task = None
        self.logger = logging.getLogger('red.onepiece_mod')
        self.logger.setLevel(logging.DEBUG)
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

    async def initialize(self):
        self.reminder_task = self.bot.loop.create_task(self.send_periodic_reminder())
        self.logger.info("Reminder task initialized")

    def cog_unload(self):
        if self.reminder_task:
            self.reminder_task.cancel()
        self.logger.info("Reminder task unloaded")

    async def is_allowed_by_hierarchy(
        self, guild: discord.Guild, mod: discord.Member, user: discord.Member
    ):
        is_special = mod == guild.owner or await self.bot.is_owner(mod)
        return mod.top_role > user.top_role or is_special

    async def _send_dm_notification(
        self,
        user: Union[discord.User, discord.Member],
        moderator: Union[discord.User, discord.Member],
        guild: discord.Guild,
        action: str,
        reason: Optional[str],
        duration: Optional[timedelta] = None
    ):
        if user.bot:
            return

        if not await self.config.guild(guild).dm():
            return

        show_mod = await self.config.guild(guild).show_mod()
        title = f"🏴‍☠️ {action} 🏴‍☠️"
        
        if duration:
            duration_str = humanize_timedelta(timedelta=duration)
            until = datetime.now(timezone.utc) + duration
            until_str = discord.utils.format_dt(until)

        moderator_str = str(moderator) if show_mod else "A mysterious pirate captain"

        if not reason:
            reason = "No reason provided, ye scurvy dog!"

        message = f"{title}\n\n"
        message += f"**Reason:** {reason}\n"
        if show_mod:
            message += f"**Enforcing Officer:** {moderator_str}\n"
        if duration:
            message += f"**Duration:** {duration_str}\n"
            message += f"**Until:** {until_str}\n"
        message += f"**Crew:** {guild.name}"

        try:
            await user.send(message)
        except discord.Forbidden:
            pass  # Cannot send DM to the user

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setgeneralchannel(self, ctx, channel: discord.TextChannel):
        """Set the general channel for reminders."""
        await self.config.guild(ctx.guild).general_channel_id.set(channel.id)
        await self.config.guild(ctx.guild).main_server_id.set(ctx.guild.id)
        await ctx.send(f"General channel set to {channel.mention} and this server set as the main server for reminders.")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def testreminder(self, ctx):
        """Test the reminder system by sending a random reminder."""
        main_server_id = await self.config.guild(ctx.guild).main_server_id()
        if ctx.guild.id != main_server_id:
            return await ctx.send("This command can only be used in the main server.")

        general_channel_id = await self.config.guild(ctx.guild).general_channel_id()
        if not general_channel_id:
            return await ctx.send("The general channel hasn't been set. Use `setgeneralchannel` first.")

        channel = ctx.guild.get_channel(general_channel_id)
        if not channel:
            return await ctx.send("The set general channel could not be found. Please set it again.")

        reminder = self.get_random_reminder()
        await channel.send(reminder)
        await ctx.send("Test reminder sent successfully!")

    async def send_periodic_reminder(self):
        await self.bot.wait_until_ready()
        self.logger.info("Starting periodic reminder task")
        
        while not self.bot.is_closed():
            try:
                main_server_id = await self.config.guild(self.bot.guilds[0]).main_server_id()
                if not main_server_id:
                    self.logger.warning("Main server ID not set. Skipping reminder.")
                    await asyncio.sleep(300)  # Wait 5 minutes before trying again
                    continue

                guild = self.bot.get_guild(main_server_id)
                if not guild:
                    self.logger.error(f"Main server with ID {main_server_id} not found.")
                    await asyncio.sleep(300)  # Wait 5 minutes before trying again
                    continue

                general_channel_id = await self.config.guild(guild).general_channel_id()
                if not general_channel_id:
                    self.logger.warning(f"No general channel set for main server {guild.name}")
                    await asyncio.sleep(300)  # Wait 5 minutes before trying again
                    continue

                channel = guild.get_channel(general_channel_id)
                if channel:
                    reminder = self.get_random_reminder()
                    await channel.send(reminder)
                    self.logger.info(f"Reminder sent to {guild.name}: {reminder[:30]}...")
                else:
                    self.logger.error(f"General channel not found in main server {guild.name}")

                # Fixed delay of 30 minutes
                delay = 30 * 60  # 30 minutes in seconds
                self.logger.debug(f"Waiting for {delay} seconds before next reminder")
                await asyncio.sleep(delay)
            
            except discord.errors.HTTPException as e:
                self.logger.error(f"HTTP error when sending reminder: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error in reminder task: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before trying again

    def get_random_reminder(self):
        reminder_messages = [
            "# 🏴‍☠️ __**Ahoy, me hearties!**__ 🏴‍☠️\n> Remember, loose lips sink ships!\n> **Keep them spoilers out of the general chat,\n> or ye'll be walkin' the plank!** 🦈",
            
            "# ⚓ __**Avast ye!**__ ⚓\n> The Pirate Code (server rules) be posted in <#rules>.\n> **Any landlubber caught ignorin' 'em will be keelhauled!** 🏴‍☠️",
            
            "# 🗺️ __**Arrr!**__ 🗺️\n> This here ship be a peaceful one.\n> **Leave yer controversial topics at the dock,\n> or face the wrath of the Sea Kings!** 🌊",
            
            "# 🍖 __**Oi!**__ 🍖\n> Just like Luffy respects his crew's privacy,\n> **respect yer fellow pirates' personal information.\n> Don't be sharin' what ain't yours to share!** 🤐",
            
            "# 🎭 __**Yo ho ho!**__ 🎭\n> Keep it family-friendly, ye scurvy dogs!\n> **We run a clean ship here, like the Thousand Sunny!** 🌟",
            
            "# 🌊 __**Sea Kings ahead!**__ 🌊\n> Watch yer language in the general waters.\n> **This ain't the Grand Line, so keep it mild!** 🧼",
            
            "# 🍊 __**Nami says:**__ 🍊\n> '**Don't spam the chat or I'll charge you\n> 100,000 berries per message!**' 💰",
            
            "# 📚 __**Robin's daily reminder:**__ 📚\n> Treat every crew member with respect,\n> regardless of their background.\n> **That's the way of the Straw Hat Pirates!** 🏴‍☠️",
            
            "# 🔧 __**Franky's SUPER reminder:**__ 🔧\n> Keep the server topics as organized as his workshop!\n> **Use the right channels for the right discussions!** 🛠️",
            
            "# 🍳 __**Sanji's kitchen notice:**__ 🍳\n> All are welcome in our crew, just like in the Baratie!\n> **Discrimination of any kind will not be tolerated!** 🥘",
            
            "# ⚔️ __**Zoro's warning:**__ ⚔️\n> Don't go starting fights in the chat.\n> **If ye have a problem, talk to a moderator\n> before ye get lost in a ban!** 🧭",
            
            "# 🩺 __**Chopper's advice:**__ 🩺\n> If someone's breaking the rules, don't play doctor yourself.\n> **Report it to the ship's officers (moderators)!** 🚨",
            
            "# 🎵 __**Brook's melody of wisdom:**__ 🎵\n> Yohohoho! Remember to give credit when sharing others' work,\n> **or you'll face a copyright strike!**\n> ...Ah, but I don't have eyes to see copyrights! Skull joke! 💀",
            
            "# 👑 __**Words from the Pirate King:**__ 👑\n> '**In this server, everyone's dreams are respected.\n> Don't mock or belittle others for their passions!**' 🌈"
        ]
        return random.choice(reminder_messages)


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
    @checks.mod_or_permissions(manage_messages=True)
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
        self.logger.debug(f"Creating warn embed for member: {member.id}")
        self.logger.debug(f"Member avatar: {member.avatar}")
        self.logger.debug(f"Member default avatar: {member.default_avatar}")

        embed = discord.Embed(
            title=f"⚠️ Warning Log for {member.display_name}",
            color=discord.Color.red(),
            timestamp=datetime.fromisoformat(warn_data['timestamp'])
        )
        
        if member.avatar:
            avatar_url = member.avatar.url
            self.logger.debug(f"Using custom avatar: {avatar_url}")
        else:
            avatar_url = member.default_avatar.url
            self.logger.debug(f"Using default avatar: {avatar_url}")
        
        embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(name="Warning Count", value=str(warn_data['count']), inline=False)
        embed.add_field(name="Reasons", value="\n".join(f"• {reason}" for reason in warn_data['reasons']), inline=False)
        moderator = member.guild.get_member(warn_data['moderator'])
        mod_name = moderator.display_name if moderator else "Unknown Moderator"
        embed.add_field(name="Last Updated By", value=mod_name, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        return embed

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
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
    @checks.mod_or_permissions(kick_members=True)
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
    @checks.mod_or_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Mutiny against the crew!"):
        """Banish a pirate to Impel Down and erase their messages."""
        try:
            # Ensure the bot has permission to ban
            if not ctx.guild.me.guild_permissions.ban_members:
                return await ctx.send("I don't have the authority to banish pirates to Impel Down!")
    
            # Check role hierarchy
            if ctx.author.top_role <= member.top_role or ctx.guild.me.top_role <= member.top_role:
                return await ctx.send("Ye can't banish a pirate of equal or higher rank!")
    
            # Ban the user
            await ctx.guild.ban(member, reason=reason, delete_message_days=7)
    
            # Select a random ban message
            ban_message, ban_gif = random.choice(self.ban_messages)
    
            # Create the ban text message
            ban_text = (
                f"⛓️ Pirate Banished to Impel Down! ⛓️\n\n"
                f"{member.name} has been locked away!\n\n"
                f"**Crimes**\n{reason}\n\n"
                f"**Warden's Note**\n{ban_message}"
            )
    
            # Send the ban message to the general chat or the current channel
            general_chat = self.bot.get_channel(self.general_chat_id)
            if general_chat:
                await general_chat.send(ban_text)
                await general_chat.send(ban_gif)
            else:
                await ctx.send("Couldn't find the general chat channel. Posting here instead:")
                await ctx.send(ban_text)
                await ctx.send(ban_gif)
    
            # Log the action
            await self.log_action(ctx, member, "Banished to Impel Down", reason, moderator=ctx.author)
    
            # Create a case in the modlog
            case = await modlog.create_case(
                self.bot, ctx.guild, ctx.message.created_at, action_type="ban",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The traitor's crimes have been recorded in the ship's log. Case number: {case.case_number}")
    
        except discord.Forbidden:
            await ctx.send("I don't have the authority to banish that pirate to Impel Down!")
        except discord.HTTPException as e:
            await ctx.send(f"There was an error while trying to banish that pirate. The Marines must be jamming our signals! Error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            self.logger.error(f"Error in ban command: {e}", exc_info=True)

    @staticmethod
    async def is_mod_or_admin(ctx):
        """Check if the user is a mod or admin."""
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author == ctx.guild.owner:
            return True
        if await ctx.bot.is_mod(ctx.author):
            return True
        return False
            
    @commands.command(usage="<users...> [time_and_reason]")
    @commands.guild_only()
    @commands.check(is_mod_or_admin)
    async def mute(
        self,
        ctx: commands.Context,
        users: commands.Greedy[discord.Member],
        *,
        time_and_reason: str = None
    ):
        """Banish crew members to the Void Century."""
        if not users:
            return await ctx.send_help()
        if ctx.me in users:
            return await ctx.send("You cannot banish the ship's Log Pose to the Void Century!")
        if ctx.author in users:
            return await ctx.send("You cannot banish yourself to the Void Century!")

        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("Blimey! The Void Century role has vanished like a mirage! Alert the captain!")

        async with ctx.typing():
            duration = None
            until = None
            reason = None
            if time_and_reason:
                converter = MuteTime()
                time_data = await converter.convert(ctx, time_and_reason)
                duration = time_data.get("duration")
                reason = time_data.get("reason")
                if duration:
                    until = ctx.message.created_at + duration
            
            if not duration:
                default_duration = await self.config.guild(ctx.guild).default_time()
                if default_duration:
                    duration = timedelta(seconds=default_duration)
                    until = ctx.message.created_at + duration

            time_str = f"for {humanize_timedelta(timedelta=duration)}" if duration else "indefinitely"

            success_list = []
            for user in users:
                result = await self.mute_user(ctx.guild, ctx.author, user, until, reason)
                if result["success"]:
                    success_list.append(user)
                    await modlog.create_case(
                        self.bot,
                        ctx.guild,
                        ctx.message.created_at,
                        "smute",
                        user,
                        ctx.author,
                        reason,
                        until=until,
                    )
                    await self._send_dm_notification(user, ctx.author, ctx.guild, "Banishment to the Void Century", reason, duration)
                    await self.log_action(ctx, user, f"Banished to Void Century {time_str}", reason, ctx.author)
                    
                    # Schedule auto-unmute
                    if duration:
                        self.schedule_unmute(ctx.guild, user, duration)
                else:
                    await ctx.send(f"I couldn't banish {user} to the Void Century: {result['reason']}")

        if success_list:
            pirate_messages = [
                f"Yarr! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been cast into the Void Century {time_str}!",
                f"Shiver me timbers! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} vanished into the mists of the Void Century {time_str}!",
                f"By Davy Jones' locker! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been marooned in the Void Century {time_str}!",
                f"Blimey! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been swallowed by the Void Century {time_str}!"
            ]
            await ctx.send(random.choice(pirate_messages))

    def schedule_unmute(self, guild: discord.Guild, user: discord.Member, duration: timedelta):
        async def unmute_later():
            await asyncio.sleep(duration.total_seconds())
            await self.unmute_user(guild, self.bot.user, user, "Automatic unmute: Void Century banishment has ended")
            # Remove the task from the mute_tasks dict
            if guild.id in self.mute_tasks and user.id in self.mute_tasks[guild.id]:
                del self.mute_tasks[guild.id][user.id]

        # Create a task for the delayed unmute
        task = asyncio.create_task(unmute_later())
        
        # Store the task so it can be cancelled if needed
        if guild.id not in self.mute_tasks:
            self.mute_tasks[guild.id] = {}
        self.mute_tasks[guild.id][user.id] = task

    async def mute_user(
        self,
        guild: discord.Guild,
        author: discord.Member,
        user: discord.Member,
        until: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Union[bool, str]]:
        """Handles banishing users to the Void Century"""
        ret = {"success": False, "reason": None}

        mute_role = guild.get_role(self.mute_role_id)
        if not mute_role:
            ret["reason"] = "The Void Century role is missing! Have ye checked the Grand Line?"
            return ret

        if mute_role in user.roles:
            ret["reason"] = f"{user.name} is already banished to the Void Century!"
            return ret

        try:
            # Store current roles
            current_roles = [role for role in user.roles if role != guild.default_role and role != mute_role]
            
            # Remove all roles except @everyone and add mute role
            await user.edit(roles=[mute_role], reason=reason)

            if guild.id not in self.mute_role_cache:
                self.mute_role_cache[guild.id] = {}
            self.mute_role_cache[guild.id][user.id] = {
                "author": author.id,
                "member": user.id,
                "until": until.timestamp() if until else None,
                "roles": [r.id for r in current_roles]
            }
            await self.config.guild(guild).muted_users.set(self.mute_role_cache[guild.id])
            ret["success"] = True
        except discord.Forbidden as e:
            ret["reason"] = f"The Sea Kings prevent me from assigning the Void Century role! Error: {e}"
        except discord.HTTPException as e:
            ret["reason"] = f"A mysterious force interferes with the mute! Error: {e}"
        except Exception as e:
            ret["reason"] = f"An unexpected tempest disrupts the mute! Error: {e}"
        return ret

    @commands.command()
    @commands.guild_only()
    @commands.check(is_mod_or_admin)
    async def unmute(
        self,
        ctx: commands.Context,
        users: commands.Greedy[discord.Member],
        *,
        reason: str = "Void Century banishment has ended"
    ):
        """Return crew members from the Void Century."""
        if not users:
            return await ctx.send_help()
        if ctx.me in users:
            return await ctx.send("Ye can't free the ship's Log Pose from the Void Century!")
        if ctx.author in users:
            return await ctx.send("Ye can't free yerself from the Void Century!")
    
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("Shiver me timbers! The Void Century role has vanished like a ghost ship!")
    
        async with ctx.typing():
            success_list = []
            for user in users:
                self.logger.info(f"Attempting to unmute user {user.id}")
                result = await self.unmute_user(ctx.guild, ctx.author, user, reason)
                if result["success"]:
                    success_list.append(user)
                    await modlog.create_case(
                        self.bot,
                        ctx.guild,
                        ctx.message.created_at,
                        "sunmute",
                        user,
                        ctx.author,
                        reason,
                        until=None,
                    )
                    await self._send_dm_notification(user, ctx.author, ctx.guild, "Return from the Void Century", reason)
                    await self.log_action(ctx, user, "Returned from the Void Century", reason, ctx.author)
                else:
                    await ctx.send(f"I couldn't return {user} from the Void Century: {result['reason']}")
        
        if success_list:
            await ctx.send(
                f"{humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} "
                f"returned from the Void Century and can speak again!"
            )
        else:
            await ctx.send("Arrr! No crew members were freed from the Void Century this time.")
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        async with self.config.guild(guild).muted_users() as muted_users:
            if str(member.id) in muted_users:
                mute_data = muted_users[str(member.id)]
                mute_role = guild.get_role(self.mute_role_id)
                
                if mute_role:
                    try:
                        await member.add_roles(mute_role, reason="Reapplying mute on rejoin")
                        until = datetime.fromisoformat(mute_data['until']) if mute_data['until'] else None
                        if until and until > datetime.now(timezone.utc):
                            await self.schedule_unmute(guild, member, until - datetime.now(timezone.utc))
                        self.logger.info(f"Reapplied mute to {member} upon rejoining {guild}")
                    except discord.Forbidden:
                        self.logger.error(f"Failed to reapply mute to {member} in {guild}: Missing Permissions")
                    except discord.HTTPException as e:
                        self.logger.error(f"Failed to reapply mute to {member} in {guild}: {e}")
                        
    async def unmute_user(
        self,
        guild: discord.Guild,
        author: discord.Member,
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> Dict[str, Union[bool, str]]:
        """Handles returning users from the Void Century"""
        ret = {"success": False, "reason": None}
    
        self.logger.info(f"Attempting to unmute user {user.id} in guild {guild.id}")
    
        mute_role = guild.get_role(self.mute_role_id)
        if not mute_role:
            self.logger.error(f"Mute role {self.mute_role_id} not found in guild {guild.id}")
            ret["reason"] = "The Void Century role has vanished like a mirage! Alert the captain!"
            return ret
    
        if mute_role not in user.roles:
            self.logger.info(f"User {user.id} doesn't have the mute role in guild {guild.id}")
            ret["reason"] = f"{user.name} isn't trapped in the Void Century. They're free as a seagull!"
            return ret
    
        try:
            self.logger.info(f"Removing mute role {mute_role.id} from user {user.id}")
            await user.remove_roles(mute_role, reason=reason)
            
            # Restore previous roles
            if guild.id in self.mute_role_cache and user.id in self.mute_role_cache[guild.id]:
                roles_to_add = [guild.get_role(r_id) for r_id in self.mute_role_cache[guild.id][user.id]["roles"] if guild.get_role(r_id)]
                self.logger.info(f"Restoring roles for user {user.id}: {[r.id for r in roles_to_add]}")
                await user.add_roles(*roles_to_add, reason="Restoring roles after unmute")
                
                # Safely remove the user's mute data from the cache
                self.mute_role_cache[guild.id].pop(user.id, None)
                await self.config.guild(guild).muted_users.set(self.mute_role_cache[guild.id])
            else:
                self.logger.warning(f"No mute cache found for user {user.id} in guild {guild.id}")
            
            ret["success"] = True
            self.logger.info(f"Successfully unmuted user {user.id} in guild {guild.id}")
            
            # Cancel any existing unmute task
            if guild.id in self.mute_tasks and user.id in self.mute_tasks[guild.id]:
                self.logger.info(f"Cancelling unmute task for user {user.id} in guild {guild.id}")
                self.mute_tasks[guild.id][user.id].cancel()
                del self.mute_tasks[guild.id][user.id]
            
        except discord.Forbidden as e:
            self.logger.error(f"Forbidden error when unmuting user {user.id} in guild {guild.id}: {e}")
            ret["reason"] = "The Sea Kings prevent me from removing the Void Century role!"
        except discord.HTTPException as e:
            self.logger.error(f"HTTP error when unmuting user {user.id} in guild {guild.id}: {e}")
            ret["reason"] = f"A mysterious force interferes with the unmute! Error: {e}"
        except Exception as e:
            self.logger.error(f"Unexpected error when unmuting user {user.id} in guild {guild.id}: {e}", exc_info=True)
            ret["reason"] = f"An unexpected tempest disrupts the unmute! Error: {e}"
        
        return ret

    async def _restore_roles(self, member: discord.Member, reason: str):
        """Helper method to restore roles for a user."""
        guild = member.guild
        if guild.id in self.mute_role_cache and member.id in self.mute_role_cache[guild.id]:
            roles_to_add = []
            for role_id in self.mute_role_cache[guild.id][member.id]["roles"]:
                role = guild.get_role(role_id)
                if role and role < guild.me.top_role and role not in member.roles:
                    roles_to_add.append(role)
            
            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason=f"Restoring roles after unmute: {reason}")
                    self.logger.info(f"Restored roles for {member} in {guild}: {', '.join(r.name for r in roles_to_add)}")
                except discord.Forbidden:
                    self.logger.error(f"Failed to restore roles for {member} in {guild}: Missing Permissions")
                except discord.HTTPException as e:
                    self.logger.error(f"Failed to restore roles for {member} in {guild}: {e}")
            
            del self.mute_role_cache[guild.id][member.id]
            await self.config.guild(guild).muted_users.set(self.mute_role_cache[guild.id])

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Event listener to catch manual mute role removals."""
        mute_role = before.guild.get_role(self.mute_role_id)
        if not mute_role:
            return

        if mute_role in before.roles and mute_role not in after.roles:
            # The mute role was manually removed
            await self._restore_roles(after, "Manual unmute detected")


    async def log_action(self, ctx, member: discord.Member, action: str, reason: str, moderator: discord.Member = None):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            log_message = (
                "🏴‍☠️ **Crew Log Entry** 🏴‍☠️\n\n"
                f"**Target Pirate:** {member.name} (ID: {member.id})\n"
                f"**Action Taken:** {action}\n"
                f"**Reason for Action:** {reason or 'No reason provided'}\n"
                f"**Enforcing Officer:** {moderator.name} (ID: {moderator.id})\n"
                f"**Incident Report:** [View Incident Details]({ctx.message.jump_url})\n\n"
                f"Logged at {ctx.message.created_at.strftime('%Y-%m-%d %H:%M:%S')} | One Piece Moderation"
            )
            await log_channel.send(log_message)
            
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
    global original_commands
    cog = OnePieceMod(bot)

    command_names = ["kick", "ban", "mute", "unmute"]
    for cmd_name in command_names:
        original_cmd = bot.get_command(cmd_name)
        if original_cmd:
            original_commands[cmd_name] = original_cmd
            bot.remove_command(cmd_name)

    await bot.add_cog(cog)
    await cog.initialize()

async def teardown(bot):
    global original_commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
