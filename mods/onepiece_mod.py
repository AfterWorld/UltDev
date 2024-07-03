import discord
from redbot.core import commands, checks, modlog
from redbot.core.bot import Red
import asyncio
import re
import random

original_commands = {}

class OnePieceMod(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.log_channel_id = 1245208777003634698
        self.mute_role_id = 808869058476769312
        self.general_chat_id = 425068612542398476  # ID of the general chat channel
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
    @checks.admin_or_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, *, args: str = ""):
        """Silence a crew member with Sea Prism handcuffs. Usage: .mute @member [duration] [reason]"""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            await ctx.send("The Mute role doesn't exist! We need to craft some Sea Prism handcuffs first.")
            return

        duration = None
        reason = "Speaking out of turn during a crew meeting!"

        # Parse duration and reason
        duration_match = re.match(r'(\d+)([mhd])', args)
        if duration_match:
            duration = duration_match.group(0)
            reason = args[len(duration):].strip() or reason
        else:
            reason = args or reason

        try:
            # Store the user's current roles
            self.muted_users[member.id] = [role for role in member.roles if role != ctx.guild.default_role]

            # Remove all roles and add mute role
            await member.edit(roles=[])
            await member.add_roles(mute_role, reason=reason)
            
            await ctx.send(f"🔇 {member.name} has been silenced with Sea Prism handcuffs and stripped of all roles!")
            
            if duration:
                duration_seconds = self.parse_duration(duration)
                await self.log_action(ctx, member, f"Muted for {duration}", reason)
                await asyncio.sleep(duration_seconds)
                await self.unmute(ctx, member)
            else:
                await self.log_action(ctx, member, "Muted indefinitely", reason)

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
            # Remove mute role
            await member.remove_roles(mute_role, reason=reason)
            
            # Restore original roles
            if member.id in self.muted_users:
                await member.add_roles(*self.muted_users[member.id], reason="Restoring roles after unmute")
                del self.muted_users[member.id]
            
            await ctx.send(f"🔊 The Sea Prism effect has worn off. {member.name} can speak again and their roles have been restored!")
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

    def parse_duration(self, duration: str) -> int:
        """Parse duration string into seconds."""
        value = int(duration[:-1])
        unit = duration[-1]
        if unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        elif unit == 'd':
            return value * 86400
        else:
            return 0

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
