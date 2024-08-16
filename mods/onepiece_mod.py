import discord
from discord.ext import commands, tasks
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

class OnePieceMod(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "muted_users": {},
            "banned_words": [],
            "banned_word_strikes": {},
            "mute_role": None,
            "mod_log_channel": None,
            "general_channel": None,
        }
        self.config.register_guild(**default_guild)
        self.reminder_task = None
        self.start_tasks()
        self.mute_tasks = {}
        self.check_mutes.start()
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
            ("Big Mom's Soul-Soul Fruit has taken your lifespan... and your server access!", "https://tenor.com/view/%E5%A4%A7%E5%AA%BDauntie-aunt-granny-grandmom-gif-12576437"),
            ("Silence… Kidd Fan :LuffyTRUTH:","https://tenor.com/view/shanks-one-piece-divine-departure-kamusari-kid-gif-2484508146019442683")
        ]

    def cog_unload(self):
        self.check_mutes.cancel()
        global original_commands
        for cmd_name, cmd in original_commands.items():
            if self.bot.get_command(cmd_name):
                self.bot.remove_command(cmd_name)
            if cmd:
                self.bot.add_command(cmd)
        original_commands.clear()
        
    def start_tasks(self):
        self.reminder_task = self.bot.loop.create_task(self.send_periodic_reminder())

    def cog_unload(self):
        if self.reminder_task:
            self.reminder_task.cancel()

    @staticmethod
    def parse_duration(duration_str: str) -> timedelta:
        """Parse a duration string into a timedelta object."""
        match = re.match(r"(\d+)([smhd])", duration_str.lower())
        if not match:
            raise ValueError("Invalid duration format. Use a number followed by s, m, h, or d.")
        
        amount, unit = match.groups()
        amount = int(amount)
        
        if unit == 's':
            return timedelta(seconds=amount)
        elif unit == 'm':
            return timedelta(minutes=amount)
        elif unit == 'h':
            return timedelta(hours=amount)
        elif unit == 'd':
            return timedelta(days=amount)

    @tasks.loop(minutes=5)
    async def check_mutes(self):
        for guild in self.bot.guilds:
            muted_users = await self.config.guild(guild).muted_users()
            for user_id, mute_data in list(muted_users.items()):
                if mute_data["until"] and datetime.fromisoformat(mute_data["until"]) <= datetime.now(timezone.utc):
                    user = guild.get_member(int(user_id))
                    if user:
                        await self.unmute_user(guild, user, "Automatic unmute: mute duration expired")

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

            async with self.config.guild(guild).muted_users() as muted_users:
                muted_users[str(user.id)] = {
                    "author": author.id,
                    "member": user.id,
                    "until": until.isoformat() if until else None,
                    "roles": [r.id for r in current_roles]
                }

            ret["success"] = True
        except discord.Forbidden as e:
            ret["reason"] = f"The Sea Kings prevent me from assigning the Void Century role! Error: {e}"
        except discord.HTTPException as e:
            ret["reason"] = f"A mysterious force interferes with the mute! Error: {e}"
        except Exception as e:
            ret["reason"] = f"An unexpected tempest disrupts the mute! Error: {e}"
        return ret

    async def unmute_user(
        self,
        guild: discord.Guild,
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> Dict[str, Union[bool, str]]:
        """Handles returning users from the Void Century"""
        ret = {"success": False, "reason": None}

        mute_role = guild.get_role(self.mute_role_id)
        if not mute_role:
            ret["reason"] = "The Void Century role has vanished like a mirage! Alert the captain!"
            return ret

        if mute_role not in user.roles:
            ret["reason"] = f"{user.name} isn't trapped in the Void Century. They're free as a seagull!"
            return ret

        try:
            await user.remove_roles(mute_role, reason=reason)
            
            async with self.config.guild(guild).muted_users() as muted_users:
                if str(user.id) in muted_users:
                    roles_to_add = []
                    for role_id in muted_users[str(user.id)]["roles"]:
                        role = guild.get_role(role_id)
                        if role and role < guild.me.top_role and role not in user.roles:
                            roles_to_add.append(role)
                    
                    if roles_to_add:
                        await user.add_roles(*roles_to_add, reason="Restoring roles after unmute")
                    
                    del muted_users[str(user.id)]

            ret["success"] = True
        except discord.Forbidden as e:
            ret["reason"] = f"The Sea Kings prevent me from removing the Void Century role! Error: {e}"
        except discord.HTTPException as e:
            ret["reason"] = f"A mysterious force interferes with the unmute! Error: {e}"
        except Exception as e:
            ret["reason"] = f"An unexpected tempest disrupts the unmute! Error: {e}"
        return ret

    async def schedule_unmute(self, guild: discord.Guild, user: discord.Member, duration: timedelta):
        async def unmute_later():
            await asyncio.sleep(duration.total_seconds())
            await self.unmute_user(guild, user, "Automatic unmute: mute duration expired")

        task = asyncio.create_task(unmute_later())
        if guild.id not in self.mute_tasks:
            self.mute_tasks[guild.id] = {}
        self.mute_tasks[guild.id][user.id] = task
        
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setreminderchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for periodic reminders."""
        await self.config.guild(ctx.guild).general_channel.set(channel.id)
        await ctx.send(f"Reminder channel set to {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def sendreminder(self, ctx):
        """Manually send a reminder to the set channel."""
        channel_id = await self.config.guild(ctx.guild).general_channel()
        channel = ctx.guild.get_channel(channel_id)
        if channel:
            reminder = self.get_random_reminder()
            await channel.send(reminder)
            await ctx.send("Reminder sent!")
        else:
            await ctx.send("Reminder channel not set or not found.")

    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, duration: str = None, *, reason: str = None):
        """Mute a user, optionally for a specified duration."""
        if duration:
            try:
                duration = self.parse_duration(duration)
            except ValueError as e:
                return await ctx.send(str(e))
        
        success, error_message = await self.mute_user(ctx.guild, member, ctx.author, duration, reason)
        if success:
            duration_str = f" for {humanize_timedelta(timedelta=duration)}" if duration else ""
            await ctx.send(f"{member.mention} has been muted{duration_str}.")
            await self.send_mod_log(ctx.guild, "mute", member, ctx.author, reason, duration)
            await self.send_themed_message(ctx.channel, member, "mute", duration_str)
        else:
            await ctx.send(f"Failed to mute {member.mention}: {error_message}")
            
    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = None):
        """Unmute a muted user."""
        success, error_message = await self.unmute_user(ctx.guild, member, reason)
        if success:
            await ctx.send(f"{member.mention} has been unmuted.")
            await self.send_mod_log(ctx.guild, "unmute", member, ctx.author, reason)
            await self.send_themed_message(ctx.channel, member, "unmute")
        else:
            await ctx.send(f"Failed to unmute {member.mention}: {error_message}")

    @commands.command()
    @checks.mod_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """Kick a user from the server."""
        try:
            await member.kick(reason=reason)
            await ctx.send(f"{member.mention} has been kicked from the server.")
            await self.send_mod_log(ctx.guild, "kick", member, ctx.author, reason)
            await self.send_themed_message(ctx.channel, member, "kick")
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick that user.")
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to kick the user.")

    @commands.command()
    @checks.mod_or_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, delete_days: int = 0, *, reason: str = None):
        """Ban a user from the server."""
        try:
            await member.ban(reason=reason, delete_message_days=delete_days)
            
            ban_message, ban_gif = random.choice(self.ban_messages)
            ban_text = (
                f"⛓️ Pirate Banished to Impel Down! ⛓️\n\n"
                f"{member.name} has been locked away!\n\n"
                f"**Crimes**\n{reason or 'No reason provided'}\n\n"
                f"**Warden's Note**\n{ban_message}"
            )
            
            await ctx.send(ban_text)
            await ctx.send(ban_gif)
            
            await self.send_mod_log(ctx.guild, "ban", member, ctx.author, reason)
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban that user.")
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to ban the user.")

    async def send_mod_log(self, guild: discord.Guild, action: str, target: discord.Member, moderator: discord.Member, reason: str = None, duration: timedelta = None):
        log_channel_id = await self.config.guild(guild).mod_log_channel()
        if not log_channel_id:
            return

        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return

        action_str = f"{action.capitalize()}"
        if duration:
            action_str += f" for {humanize_timedelta(timedelta=duration)}"

        log_message = (
            "🏴‍☠️ **Crew Log Entry** 🏴‍☠️\n\n"
            f"**Target Pirate:** {target.name} (ID: {target.id})\n"
            f"**Action Taken:** {action_str}\n"
            f"**Reason for Action:** {reason or 'No reason provided'}\n"
            f"**Enforcing Officer:** {moderator.name} (ID: {moderator.id})\n"
            f"**Incident Report:** [View Incident Details]({moderator.jump_url})\n\n"
            f"Logged at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} | One Piece Moderation"
        )

        await log_channel.send(log_message)

    async def send_themed_message(self, channel: discord.TextChannel, user: discord.Member, action: str, duration: str = ""):
        messages = {
            "mute": [
                f"Yohohoho! {user.mention} has been sent to the Void Century{duration}! Even I, as a skeleton, can hear better than them now!",
                f"Gomu Gomu no Silence! {user.mention}'s voice has been stretched into the distance{duration}!",
                f"{user.mention} has been caught by Bartolomeo's Barrier{duration}! Not even sound can escape!"
            ],
            "unmute": [
                f"Break through! {user.mention} has escaped the Void Century and can speak again!",
                f"{user.mention}'s voice has returned from its grand adventure! Did you bring back any treasure?",
                f"The Sea Kings have granted {user.mention} their voice back! Use it wisely, or they might change their minds!"
            ],
            "kick": [
                f"{user.mention} has been sent flying by Luffy's Gomu Gomu no Bazooka! They're blasting off again!",
                f"Sanji's Diable Jambe just kicked {user.mention} clean off the ship! Hope they can swim!",
                f"{user.mention} got lost following Zoro and ended up kicked from the server! Typical Zoro..."
            ],
            "ban": [
                f"{user.mention} has been banished to Impel Down! Not even Buggy could escape this ban!",
                f"Akainu's Absolute Justice has been served! {user.mention} is hereby banned from this pirate crew!",
                f"{user.mention} has been caught in Blackbeard's darkness and swallowed by a ban! Zehahaha!"
            ]
        }
        
        await channel.send(random.choice(messages[action]))

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setmuterole(self, ctx, role: discord.Role):
        """Set the mute role for the server."""
        await self.config.guild(ctx.guild).mute_role.set(role.id)
        await ctx.send(f"Mute role has been set to {role.name}")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setmodlogchannel(self, ctx, channel: discord.TextChannel):
        """Set the mod log channel for the server."""
        await self.config.guild(ctx.guild).mod_log_channel.set(channel.id)
        await ctx.send(f"Mod log channel has been set to {channel.mention}")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setgeneralchannel(self, ctx, channel: discord.TextChannel):
        """Set the general channel for the server."""
        await self.config.guild(ctx.guild).general_channel.set(channel.id)
        await ctx.send(f"General channel has been set to {channel.mention}")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def addbannedword(self, ctx, word: str):
        """Add a word to the banned words list."""
        async with self.config.guild(ctx.guild).banned_words() as banned_words:
            if word.lower() not in banned_words:
                banned_words.append(word.lower())
                await ctx.send(f"Added '{word}' to the banned words list.")
            else:
                await ctx.send(f"'{word}' is already in the banned words list.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def removebannedword(self, ctx, word: str):
        """Remove a word from the banned words list."""
        async with self.config.guild(ctx.guild).banned_words() as banned_words:
            if word.lower() in banned_words:
                banned_words.remove(word.lower())
                await ctx.send(f"Removed '{word}' from the banned words list.")
            else:
                await ctx.send(f"'{word}' is not in the banned words list.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def listbannedwords(self, ctx):
        """List all banned words."""
        banned_words = await self.config.guild(ctx.guild).banned_words()
        if banned_words:
            words_list = ", ".join(banned_words)
            await ctx.author.send(f"Banned words: {words_list}")
            await ctx.send("I've sent you a DM with the list of banned words.")
        else:
            await ctx.send("There are no banned words.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        banned_words = await self.config.guild(message.guild).banned_words()
        if any(word in message.content.lower() for word in banned_words):
            await message.delete()
            await self.handle_banned_word(message)

    async def handle_banned_word(self, message):
        async with self.config.guild(message.guild).banned_word_strikes() as strikes:
            strikes[str(message.author.id)] = strikes.get(str(message.author.id), 0) + 1
            strike_count = strikes[str(message.author.id)]

        warning = random.choice([
            f"Oi oi, {message.author.mention}! Even Luffy wouldn't approve of that language! The Pirate King's dream is about freedom, not disrespect!",
            f"Yohohoho! {message.author.mention}, that word is more forbidden than the Poneglyphs! As a skeleton, I have no ears to hear such things... but I'm all bones! Skull joke!",
            f"Oi, {message.author.mention}! Sanji says a true pirate's Black Leg style is about kicking ass, not using crass words!",
            f"Huh?! {message.author.mention}, are you trying to make Chopper cry with that language? He's a reindeer, not a swear-deer!",
            f"Oi oi oi! {message.author.mention}, Zoro got lost and ended up here, and even he knows that word is more dangerous than Mihawk's sword!",
            f"Nami says if you use that word again, {message.author.mention}, she'll raise your debt by 100,000 berries! And trust me, she WILL collect!"
        ])

        await message.channel.send(warning, delete_after=10)

        if strike_count == 3:
            duration = timedelta(minutes=10)
            success, _ = await self.mute_user(message.guild, message.author, self.bot.user, duration, "Repeated use of banned words")
            if success:
                await message.channel.send(f"{message.author.mention} has been muted for 10 minutes due to repeated use of banned words.")
        elif strike_count == 5:
            duration = timedelta(hours=1)
            success, _ = await self.mute_user(message.guild, message.author, self.bot.user, duration, "Excessive use of banned words")
            if success:
                await message.channel.send(f"{message.author.mention} has been muted for 1 hour due to excessive use of banned words.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def resetbannedwordstrikes(self, ctx, member: discord.Member):
        """Reset the banned word strike count for a user."""
        async with self.config.guild(ctx.guild).banned_word_strikes() as strikes:
            if str(member.id) in strikes:
                del strikes[str(member.id)]
                await ctx.send(f"Reset banned word strikes for {member.mention}.")
            else:
                await ctx.send(f"{member.mention} has no banned word strikes.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def checkbannedwordstrikes(self, ctx, member: discord.Member):
        """Check the banned word strike count for a user."""
        strikes = await self.config.guild(ctx.guild).banned_word_strikes()
        strike_count = strikes.get(str(member.id), 0)
        await ctx.send(f"{member.mention} has {strike_count} banned word strike(s).")

    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def tempmute(self, ctx, member: discord.Member, duration: str, *, reason: str = None):
        """Temporarily mute a user."""
        try:
            duration = self.parse_duration(duration)
        except ValueError as e:
            return await ctx.send(str(e))

        success, error_message = await self.mute_user(ctx.guild, member, ctx.author, duration, reason)
        if success:
            await ctx.send(f"{member.mention} has been temporarily muted for {humanize_timedelta(timedelta=duration)}.")
            await self.send_mod_log(ctx.guild, "tempmute", member, ctx.author, reason, duration)
            await self.send_themed_message(ctx.channel, member, "mute", f" for {humanize_timedelta(timedelta=duration)}")
        else:
            await ctx.send(f"Failed to mute {member.mention}: {error_message}")

    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def mutecheck(self, ctx, member: discord.Member):
        """Check the remaining mute time for a user."""
        muted_users = await self.config.guild(ctx.guild).muted_users()
        mute_data = muted_users.get(str(member.id))

        if not mute_data:
            return await ctx.send(f"{member.mention} is not muted.")

        if mute_data["until"]:
            until = datetime.fromisoformat(mute_data["until"])
            now = datetime.now(timezone.utc)
            if until > now:
                remaining = until - now
                await ctx.send(f"{member.mention} is muted for {humanize_timedelta(timedelta=remaining)} more.")
            else:
                await ctx.send(f"{member.mention}'s mute has expired. They should be unmuted soon.")
        else:
            await ctx.send(f"{member.mention} is muted indefinitely.")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def mutedrole(self, ctx):
        """Show the current muted role."""
        mute_role_id = await self.config.guild(ctx.guild).mute_role()
        if mute_role_id:
            mute_role = ctx.guild.get_role(mute_role_id)
            if mute_role:
                await ctx.send(f"The current muted role is: {mute_role.name}")
            else:
                await ctx.send("The muted role is set, but I couldn't find it in the server. It may have been deleted.")
        else:
            await ctx.send("No muted role has been set for this server.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Re-apply mute if a muted user rejoins."""
        muted_users = await self.config.guild(member.guild).muted_users()
        mute_data = muted_users.get(str(member.id))

        if mute_data:
            mute_role_id = await self.config.guild(member.guild).mute_role()
            if mute_role_id:
                mute_role = member.guild.get_role(mute_role_id)
                if mute_role:
                    await member.add_roles(mute_role, reason="Re-applying mute on rejoin")
                    await self.send_mod_log(member.guild, "mute", member, self.bot.user, "Re-applied mute on rejoin")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def clearmutes(self, ctx):
        """Clear all mutes in the server."""
        mute_role_id = await self.config.guild(ctx.guild).mute_role()
        if not mute_role_id:
            return await ctx.send("No mute role set for this server.")

        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            return await ctx.send("Mute role not found in the server.")

        count = 0
        async with ctx.typing():
            for member in ctx.guild.members:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role, reason="Mass mute clearance")
                    count += 1

            await self.config.guild(ctx.guild).muted_users.set({})

        await ctx.send(f"Cleared mutes for {count} member(s).")
        await self.send_mod_log(ctx.guild, "clearmutes", None, ctx.author, f"Cleared mutes for {count} member(s)")

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

async def teardown(bot):
    global original_commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
