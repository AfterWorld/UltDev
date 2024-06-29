import discord
from redbot.core import commands, checks, modlog
from redbot.core.utils.chat_formatting import box
import asyncio

# Store the original commands
original_commands = {}

class OnePieceMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channel_id = 1245208777003634698

    def cog_unload(self):
        # Restore original commands
        for cmd_name, cmd in original_commands.items():
            if self.bot.get_command(cmd_name):
                self.bot.remove_command(cmd_name)
            if cmd:
                self.bot.add_command(cmd)

    async def log_action(self, ctx, member: discord.Member, action: str, reason: str):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            log_message = f"- {member.name} (ID: {member.id})\n- {action}\n- Reason: {reason}"
            await log_channel.send(box(log_message))

    @commands.command()
    @checks.admin_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """Kick a crew member off the ship."""
        if not reason:
            reason = "Disrespecting the captain's orders!"

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
    async def ban(self, ctx, member: discord.Member, days: int = 0, *, reason: str = None):
        """Banish a pirate to Impel Down."""
        if not reason:
            reason = "Mutiny against the crew!"

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
    @checks.admin_or_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, duration: int = 0, *, reason: str = None):
        """Silence a crew member with Sea Prism handcuffs."""
        if not reason:
            reason = "Speaking out of turn during a crew meeting!"

        mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not mute_role:
            await ctx.send("The 'Muted' role doesn't exist! We need to craft some Sea Prism handcuffs first.")
            return

        try:
            await member.add_roles(mute_role, reason=reason)
            await ctx.send(f"🔇 {member.name} has been silenced with Sea Prism handcuffs!")
            await self.log_action(ctx, member, f"Muted for {duration} minutes" if duration > 0 else "Muted", reason)
            
            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="mute",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been recorded in the ship's log. Case number: {case.case_number}")

            if duration > 0:
                await ctx.send(f"The Sea Prism effect will wear off in {duration} minutes.")
                await asyncio.sleep(duration * 60)
                await member.remove_roles(mute_role, reason="Sea Prism effect wore off")
                await ctx.send(f"🔊 The Sea Prism effect has worn off. {member.name} can speak again!")
                await self.log_action(ctx, member, "Unmuted", "Sea Prism effect wore off")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to use Sea Prism handcuffs on that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to silence that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

async def setup(bot):
    global original_commands
    cog = OnePieceMod(bot)

    # Store and replace original commands
    command_names = ["kick", "ban", "mute"]
    for cmd_name in command_names:
        original_cmd = bot.get_command(cmd_name)
        if original_cmd:
            original_commands[cmd_name] = original_cmd
            bot.remove_command(cmd_name)

    await bot.add_cog(cog)

async def teardown(bot):
    global original_commands
    # Restore original commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
