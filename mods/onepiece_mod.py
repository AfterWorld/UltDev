import discord
from redbot.core import commands, checks, modlog, Config
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta
from redbot.core.utils.mod import get_audit_reason
from redbot.core.bot import Red
from datetime import timedelta, datetime
import asyncio
import re
import random

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
                self.bot, ctx.guild, ctx.message.created_at, action_type="kick",
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
    async def ban(self, ctx, member: discord.Member, delete_days: int = 1, delete_all: bool = False, *, reason: str = "Mutiny against the crew!"):
        """
        Banish a pirate to Impel Down.
        
        Use delete_all=True to delete all messages from the user across the server.
        delete_days determines how many days worth of messages to delete if delete_all is False.
        """
        try:
            if delete_all:
                # Delete all messages from the user across all channels
                for channel in ctx.guild.text_channels:
                    def check(message):
                        return message.author == member

                    await channel.purge(limit=None, check=check)
                await ctx.send(f"🧹 All messages from {member.name} have been swept from the deck!")
            else:
                # Use the standard delete_message_days parameter
                await ctx.guild.ban(member, reason=reason, delete_message_days=delete_days)

            # Select a random ban message and GIF
            ban_message, ban_gif = random.choice(self.ban_messages)
            
            embed = discord.Embed(title="⛓️ Pirate Banished! ⛓️", description=f"{member.name} has been banished to Impel Down!", color=0xff0000)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Ban Message", value=ban_message, inline=False)
            embed.set_image(url=ban_gif)
            
            # Send the ban message to the general chat
            general_chat = self.bot.get_channel(self.general_chat_id)
            if general_chat:
                await general_chat.send(embed=embed)
            else:
                await ctx.send("Couldn't find the general chat channel. Posting here instead:", embed=embed)
            
            await self.log_action(ctx, member, f"Banned (messages deleted: {'all' if delete_all else f'{delete_days} days'})", reason)
            
            case = await modlog.create_case(
                self.bot, ctx.guild, ctx.message.created_at, action_type="ban",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The traitor's crimes have been recorded in the ship's log. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to banish that pirate!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to banish that pirate. The Marines must be jamming our signals!")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def mute(
        self,
        ctx: commands.Context,
        users: commands.Greedy[discord.Member],
        time_and_reason: MuteTime,
        *,
        reason: str = None
    ):
        """Silence crew members with Sea Prism handcuffs.

        <users...> is a space separated list of usernames, ID's, or mentions.
        [time_and_reason] is the time to mute for and/or the reason.
        Time can be specified as a number followed by m(inutes), h(ours), d(ays), or w(eeks).
        If no time unit is given, minutes will be assumed.
        If no time is specified, the mute will last for 24 hours.

        Examples:
        `[p]mute @member1 @member2 10m Disrupting crew meeting`
        `[p]mute @member1 1d Stealing food from the galley`
        `[p]mute @member1 Insubordination`
        """
        if not users:
            return await ctx.send_help()
        if ctx.me in users:
            return await ctx.send("You cannot silence the ship's Den Den Mushi!")
        if ctx.author in users:
            return await ctx.send("You cannot silence yourself with Sea Prism handcuffs!")

        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("The Sea Prism handcuffs (mute role) haven't been crafted yet!")

        duration = time_and_reason["duration"] or self.default_mute_time
        reason = reason or time_and_reason["reason"] or "No reason provided"
        until = ctx.message.created_at + duration
        time_str = f" for {humanize_timedelta(timedelta=duration)}"

        async with ctx.typing():
            author = ctx.message.author
            guild = ctx.guild
            audit_reason = get_audit_reason(author, reason)
            success_list = []
            for user in users:
                try:
                    # Store the user's current roles
                    self.muted_users[user.id] = [role for role in user.roles if role != ctx.guild.default_role]
                    
                    # Remove all roles and add mute role
                    await user.edit(roles=[])
                    await user.add_roles(mute_role, reason=audit_reason)
                    
                    success_list.append(user)
                    await modlog.create_case(
                        self.bot,
                        guild,
                        ctx.message.created_at,
                        "smute",
                        user,
                        author,
                        reason,
                        until=until,
                    )
                    await self.log_action(ctx, user, f"Muted{time_str}", reason)
                    
                    # Schedule unmute
                    self.bot.loop.create_task(self.schedule_unmute(user, duration))
                except discord.Forbidden:
                    await ctx.send(f"I don't have the authority to silence {user.name}!")
                except discord.HTTPException:
                    await ctx.send(f"There was an error trying to silence {user.name}. The Sea Kings must be interfering with our Den Den Mushi!")

        if success_list:
            if len(success_list) == 1:
                msg = f"{success_list[0].name} has been silenced with Sea Prism handcuffs{time_str}."
            else:
                msg = f"{humanize_list([f'`{u.name}`' for u in success_list])} have been silenced with Sea Prism handcuffs{time_str}."
            await ctx.send(msg)

    async def schedule_unmute(self, user: discord.Member, duration: timedelta):
        """Schedule an unmute operation."""
        await asyncio.sleep(duration.total_seconds())
        await self.unmute(await self.bot.get_context(await self.bot.get_message(user.guild, user.id)), user)

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def unmute(self, ctx: commands.Context, user: discord.Member, *, reason: str = "Sea Prism effect wore off"):
        """Remove Sea Prism handcuffs from a crew member."""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("The Sea Prism handcuffs (mute role) don't exist!")

        if mute_role not in user.roles:
            return await ctx.send(f"{user.name} is not silenced. They're free to speak!")

        try:
            # Remove mute role
            await user.remove_roles(mute_role, reason=reason)
            
            # Restore original roles
            await self._restore_roles(user, reason)
            
            await ctx.send(f"🔊 The Sea Prism effect has worn off. {user.name} can speak again and their roles have been restored!")
            
        except discord.Forbidden:
            await ctx.send(f"I don't have the authority to remove Sea Prism handcuffs from {user.name}!")
        except discord.HTTPException:
            await ctx.send(f"There was an error trying to un-silence {user.name}. The Sea Kings must be interfering with our Den Den Mushi!")

    async def _restore_roles(self, user: discord.Member, reason: str):
        """Helper method to restore roles for a user."""
        if user.id in self.muted_users:
            roles_to_add = [role for role in self.muted_users[user.id] if role not in user.roles and role < user.guild.me.top_role]
            if roles_to_add:
                await user.add_roles(*roles_to_add, reason=f"Restoring roles after unmute: {reason}")
            del self.muted_users[user.id]

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
    async def send_staff_announcement(self, ctx, channel: discord.TextChannel = None):
        """Send the staff announcement about updated moderation commands to the specified channel."""
        if channel is None:
            channel = ctx.channel

        announcement = (
            "🚨 **Attention All Crew Members <@700014289418977341> !** 🏴‍☠️\n\n"
            "Captain's orders! We've upgraded our ship's systems to better maintain order and discipline among our crew. "
            "Here are the new and improved moderation commands:\n\n"
            "1. **Muting** (Sea Prism Handcuffs):\n"
            "   - Command: `.mute <user(s)> [duration] [reason]`\n"
            "   - Duration can be specified in minutes (m), hours (h), days (d), or weeks (w).\n"
            "   - If no duration is given, the default is 24 hours.\n"
            "   - Example: `.mute @LuffyFan123 2h Excessive shouting about becoming Pirate King`\n\n"
            "2. **Kicking** (Walking the Plank):\n"
            "   - Command: `.kick <user> [reason]`\n"
            "   - Example: `.kick @ZoroStan456 Sleeping on watch duty again`\n\n"
            "3. **Banning** (Banishment to Impel Down):\n"
            "   - Command: `.ban <user> [delete_days] [reason]`\n"
            "   - `delete_days` specifies how many days of messages to delete (default is 1).\n"
            "   - Example: `.ban @SanjiSimp789 7 Harassing female crew members`\n\n"
            "4. **Unmuting** (Removing Sea Prism Handcuffs):\n"
            "   - Command: `.unmute <user> [reason]`\n"
            "   - Example: `.unmute @ChopperLover101 Has learned their lesson about proper medical practices`\n\n"
            "Remember, with great power comes great responsibility. Use these commands wisely and fairly. "
            "We're not the World Government, after all!\n\n"
            "If you have any questions about these new features, please consult with your division commander "
            "or send a message in a bottle to the tech support Den Den Mushi.\n\n"
            "Stay vigilant and keep our seas safe!\n\n"
            "- Your Friendly Neighborhood Sunny Go Support System 🌞"
        )

        try:
            await channel.send(announcement)
            await ctx.send(f"Staff announcement sent to {channel.mention}!")
        except discord.Forbidden:
            await ctx.send("I don't have permission to send messages in that channel!")
        except discord.HTTPException:
            await ctx.send("There was an error sending the announcement. Please try again later.")
            
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
