import discord
from redbot.core import commands, checks, modlog, Config
from redbot.core.utils.chat_formatting import pagify
from datetime import timedelta
import asyncio
import re

original_commands = {}

class OnePieceMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channel_id = 1245208777003634698
        self.mute_role_id = 808869058476769312
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "bounties": {},
            "raid_mode": False,
            "log_book": {},
            "timed_announcements": []
        }
        self.config.register_guild(**default_guild)

    def cog_unload(self):
        for cmd_name, cmd in original_commands.items():
            if self.bot.get_command(cmd_name):
                self.bot.remove_command(cmd_name)
            if cmd:
                self.bot.add_command(cmd)

    async def log_action(self, ctx, member: discord.Member, action: str, reason: str):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            log_message = f"- {member.name} (ID: {member.id})\n- {action}\n- Reason: {reason}"
            await log_channel.send(log_message)

    @commands.command()
    @checks.admin_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Disrespecting the captain's orders!"):
        """Kick a crew member off the ship."""
        try:
            await ctx.guild.kick(member, reason=reason)
            await ctx.send(f"🦵 {member.name} has been kicked off the ship! They'll have to find another crew.")
            await self.log_action(ctx, member, "Kicked", reason)
            
            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="kick",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been logged in the ship's records. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to kick that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to kick that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, days: int = 0, *, reason: str = "Mutiny against the crew!"):
        """Banish a pirate to Impel Down."""
        try:
            await ctx.guild.ban(member, reason=reason, delete_message_days=days)
            await ctx.send(f"⛓️ {member.name} has been banished to Impel Down for their crimes against the crew!")
            await self.log_action(ctx, member, "Banned", reason)
            
            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="ban",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The traitor's crimes have been recorded in the ship's log. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to banish that pirate!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to banish that pirate. The Marines must be jamming our signals!")

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    async def impeldown(self, ctx, member: discord.Member, days: int, *, reason: str = "Temporary imprisonment in Impel Down!"):
        """Temporarily banish a pirate to Impel Down."""
        try:
            await ctx.guild.ban(member, reason=reason)
            await ctx.send(f"⛓️ {member.name} has been imprisoned in Impel Down for {days} days!")
            await self.log_action(ctx, member, f"Temporarily Banned for {days} days", reason)
            
            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="tempban",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The sentence has been recorded in the World Government's records. Case number: {case.case_number}")

            # Schedule unban
            await asyncio.sleep(days * 86400)  # Convert days to seconds
            await ctx.guild.unban(member, reason="Impel Down sentence completed")
            await ctx.send(f"🔓 {member.name} has been released from Impel Down after serving their sentence!")
            await self.log_action(ctx, member, "Unbanned", "Impel Down sentence completed")

        except discord.Forbidden:
            await ctx.send("I don't have the authority to imprison that pirate!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to imprison that pirate. The Marines must be jamming our signals!")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, duration: str = None, *, reason: str = "Speaking out of turn during a crew meeting!"):
        """Silence a crew member with Sea Prism handcuffs."""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            await ctx.send("The Mute role doesn't exist! We need to craft some Sea Prism handcuffs first.")
            return

        try:
            # Remove all roles and add mute role
            await member.edit(roles=[mute_role])
            await ctx.send(f"🔇 {member.name} has been silenced with Sea Prism handcuffs!")
            
            if duration:
                try:
                    duration_seconds = int(duration) * 60  # Convert minutes to seconds
                except ValueError:
                    await ctx.send("Invalid duration. Please provide a number of minutes.")
                    return
                await self.log_action(ctx, member, f"Muted for {duration} minutes", reason)
                await asyncio.sleep(duration_seconds)
                await self.unmute(ctx, member)
            else:
                await self.log_action(ctx, member, "Muted", reason)

            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="mute",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been recorded in the ship's log. Case number: {case.case_number}")

        except discord.Forbidden:
            await ctx.send("I don't have the authority to use Sea Prism handcuffs on that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to silence that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "Sea Prism effect wore off"):
        """Remove Sea Prism handcuffs from a crew member."""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            await ctx.send("The Mute role doesn't exist! We can't remove non-existent Sea Prism handcuffs.")
            return

        if mute_role not in member.roles:
            await ctx.send(f"{member.name} is not muted. They're free to speak!")
            return

        try:
            await member.remove_roles(mute_role, reason=reason)
            await ctx.send(f"🔊 The Sea Prism effect has worn off. {member.name} can speak again!")
            await self.log_action(ctx, member, "Unmuted", reason)

            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="unmute",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been recorded in the ship's log. Case number: {case.case_number}")

        except discord.Forbidden:
            await ctx.send("I don't have the authority to remove Sea Prism handcuffs from that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to unmute that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def addbounty(self, ctx, member: discord.Member, amount: int):
        """Increase a pirate's bounty."""
        async with self.config.guild(ctx.guild).bounties() as bounties:
            current_bounty = bounties.get(str(member.id), 0)
            new_bounty = current_bounty + amount
            bounties[str(member.id)] = new_bounty

        await ctx.send(f"🏴‍☠️ {member.name}'s bounty has increased by {amount} Berries! Their total bounty is now {new_bounty} Berries!")

        if new_bounty >= 500:  # Example threshold
            await ctx.send(f"⚠️ {member.name}'s bounty has exceeded 500 Berries! The Marines are on high alert!")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def raidmode(self, ctx, state: bool):
        """Activate or deactivate Raid Mode to defend against pirate invasions."""
        await self.config.guild(ctx.guild).raid_mode.set(state)
        if state:
            await ctx.send("🚨 Raid Mode activated! All hands on deck! Prepare to repel invaders!")
            # Here you could add code to change channel permissions, etc.
        else:
            await ctx.send("✅ Raid Mode deactivated. Stand down, crew. The danger has passed.")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def logbook(self, ctx, member: discord.Member, *, entry: str):
        """Add an entry to a pirate's log book."""
        async with self.config.guild(ctx.guild).log_book() as log_book:
            if str(member.id) not in log_book:
                log_book[str(member.id)] = []
            log_book[str(member.id)].append(entry)

        await ctx.send(f"📖 An entry has been added to {member.name}'s log book.")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def promote(self, ctx, member: discord.Member, role: discord.Role):
        """Promote a crew member to a new position."""
        try:
            await member.add_roles(role)
            await ctx.send(f"🎉 Congratulations, {member.name}! You've been promoted to {role.name}!")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to promote crew members!")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def demote(self, ctx, member: discord.Member, role: discord.Role):
        """Demote a crew member from their position."""
        try:
            await member.remove_roles(role)
            await ctx.send(f"😔 {member.name} has been demoted from {role.name}. Better luck next time!")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to demote crew members!")

    @commands.command()
    @checks.admin_or_permissions(manage_channels=True)
    async def calmbelt(self, ctx, seconds: int):
        """Enable slow mode in a channel, simulating entering the Calm Belt."""
        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            await ctx.send(f"⚓ We've entered the Calm Belt! Messages can only be sent every {seconds} seconds.")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to adjust the channel settings!")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def redline(self, ctx):
        """Prevent new members from joining, simulating reaching the Red Line."""
        try:
            await ctx.guild.edit(verification_level=discord.VerificationLevel.highest)
            await ctx.send("🚫 We've reached the Red Line! No new crew members can join until we cross it.")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to change server settings!")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def bustercall(self, ctx, number: int):
        """Delete multiple messages at once, simulating a Buster Call operation."""
        deleted = await ctx.channel.purge(limit=number+1)  # +1 to include the command message
        await ctx.send(f"💥 Buster Call complete! {len(deleted)-1} messages have been annihilated.", delete_after=5)

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def seaking(self, ctx, *, banned_words):
        """Set up auto-moderation for specific words, themed as Sea Kings patrolling the waters."""
        banned_list = [word.strip() for word in banned_words.split(',')]
        await self.config.guild(ctx.guild).banned_words.set(banned_list)
        await ctx.send(f"🐉 Sea Kings are now patrolling for these words: {', '.join(banned_list)}")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def dendenmushi(self, ctx, time: str, *, message: str):
        """Schedule a timed announcement, themed as a Den Den Mushi broadcast."""
        try:
            hours, minutes = map(int, time.split(':'))
            if not (0 <= hours < 24 and 0 <= minutes < 60):
                raise ValueError
        except ValueError:
            await ctx.send("Invalid time format. Please use HH:MM.")
            return

        async with self.config.guild(ctx.guild).timed_announcements() as announcements:
            announcements.append({"time": time, "message": message})

        await ctx.send(f"📢 A Den Den Mushi broadcast has been scheduled for {time}.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Check for banned words (Sea Kings auto-moderation)
        banned_words = await self.config.guild(message.guild).banned_words()
        if any(word in message.content.lower() for word in banned_words):
            await message.delete@commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Check for banned words (Sea Kings auto-moderation)
        banned_words = await self.config.guild(message.guild).banned_words()
        if any(word in message.content.lower() for word in banned_words):
            await message.delete()
            await message.channel.send(f"{message.author.mention}, watch your language! The Sea Kings are patrolling these waters!", delete_after=10)

        # Check if raid mode is active
        raid_mode = await self.config.guild(message.guild).raid_mode()
        if raid_mode and message.author.joined_at is not None:
            if (discord.utils.utcnow() - message.author.joined_at).total_seconds() < 300:  # If member joined less than 5 minutes ago
                await message.delete()
                await message.author.send("Our ship is currently in Raid Mode. New crew members cannot send messages until the threat has passed.")

    async def check_timed_announcements(self):
        while self is self.bot.get_cog("OnePieceMod"):
            for guild in self.bot.guilds:
                announcements = await self.config.guild(guild).timed_announcements()
                current_time = discord.utils.utcnow().strftime("%H:%M")
                for announcement in announcements:
                    if announcement["time"] == current_time:
                        channel = guild.system_channel or guild.text_channels[0]
                        await channel.send(f"📢 Den Den Mushi Broadcast: {announcement['message']}")
            await asyncio.sleep(60)  # Check every minute

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def viewlogbook(self, ctx, member: discord.Member):
        """View the log book entries for a specific pirate."""
        log_book = await self.config.guild(ctx.guild).log_book()
        entries = log_book.get(str(member.id), [])
        if not entries:
            await ctx.send(f"📖 The log book for {member.name} is empty.")
        else:
            pages = []
            for i, entry in enumerate(entries, 1):
                pages.append(f"Entry {i}: {entry}")
            await self.send_pages(ctx, pages)

    async def send_pages(self, ctx, pages):
        """Helper function to send paginated content."""
        for page in pagify("\n".join(pages), delims=["\n"], page_length=1900):
            await ctx.send(f"```\n{page}\n```")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def viewbounties(self, ctx):
        """View the bounties of all pirates in the crew."""
        bounties = await self.config.guild(ctx.guild).bounties()
        if not bounties:
            await ctx.send("There are no bounties set for any pirates in this crew.")
            return

        sorted_bounties = sorted(bounties.items(), key=lambda x: x[1], reverse=True)
        pages = []
        for user_id, bounty in sorted_bounties:
            member = ctx.guild.get_member(int(user_id))
            if member:
                pages.append(f"{member.name}: {bounty} Berries")

        if pages:
            await ctx.send("🏴‍☠️ Current Bounties:")
            await self.send_pages(ctx, pages)
        else:
            await ctx.send("There are no active bounties for current crew members.")

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
    bot.loop.create_task(cog.check_timed_announcements())

async def teardown(bot):
    global original_commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
