import discord
from redbot.core import commands, checks, modlog
from redbot.core.utils.chat_formatting import box, pagify
from datetime import timedelta
import asyncio

class OnePieceMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.admin_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """Kick a crew member off the ship."""
        if not reason:
            reason = "Disrespecting the captain's orders!"

        try:
            await member.kick(reason=reason)
            await ctx.send(f"🦵 {member.name} has been kicked off the ship! They'll have to find another crew.")
            
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
            await member.ban(reason=reason, delete_message_days=days)
            await ctx.send(f"⛓️ {member.name} has been banished to Impel Down for their crimes against the crew!")
            
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
        except discord.Forbidden:
            await ctx.send("I don't have the authority to use Sea Prism handcuffs on that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to silence that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

def setup(bot):
    bot.add_cog(OnePieceMod(bot))
