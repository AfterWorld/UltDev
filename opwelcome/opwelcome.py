import discord
from redbot.core import commands, Config
import random

class OPWelcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "welcome_channel": None,
            "welcome_enabled": False,
            "rules_channel": None,
            "roles_channel": None,
        }
        self.config.register_guild(**default_guild)
        self.op_facts = [
            "The One Piece world has more than 500 devil fruits!",
            "Eiichiro Oda started writing One Piece in 1997.",
            "Luffy's favorite food is meat!",
            "The Going Merry was partly inspired by Viking ships.",
            "Oda originally planned One Piece to last five years.",
        ]

    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def welcome(self, ctx):
        """Manage welcome settings."""
        pass

    @welcome.command()
    async def channel(self, ctx, channel: discord.TextChannel):
        """Set the welcome channel."""
        await self.config.guild(ctx.guild).welcome_channel.set(channel.id)
        await ctx.send(f"Welcome channel set to {channel.mention}")

    @welcome.command()
    async def toggle(self, ctx):
        """Toggle the welcome message on or off."""
        current = await self.config.guild(ctx.guild).welcome_enabled()
        await self.config.guild(ctx.guild).welcome_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"Welcome message {state}.")

    @welcome.command()
    async def setchannels(self, ctx, rules: discord.TextChannel, roles: discord.TextChannel):
        """Set the rules and roles channels."""
        await self.config.guild(ctx.guild).rules_channel.set(rules.id)
        await self.config.guild(ctx.guild).roles_channel.set(roles.id)
        await ctx.send(f"Channels set: Rules: {rules.mention}, Roles: {roles.mention}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if not await self.config.guild(guild).welcome_enabled():
            return

        channel_id = await self.config.guild(guild).welcome_channel()
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        rules_channel = guild.get_channel(await self.config.guild(guild).rules_channel())
        roles_channel = guild.get_channel(await self.config.guild(guild).roles_channel())

        embed = discord.Embed(
            title=f"Welcome to the {guild.name} Crew!",
            description=f"Ahoy, {member.mention}! You've just embarked on a grand adventure!",
            color=discord.Color.blue()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        if rules_channel and roles_channel:
            embed.add_field(
                name="First Steps on Your Journey",
                value=(
                    f"1. Read the pirate code in {rules_channel.mention}\n"
                    f"2. Choose your role in {roles_channel.mention}"
                ),
                inline=False
            )

        embed.add_field(
            name="Did You Know?",
            value=random.choice(self.op_facts),
            inline=False
        )

        embed.set_footer(text=f"You're our {guild.member_count}th crew member!")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            await guild.owner.send(f"I don't have permission to send messages in {channel.mention}")

def setup(bot):
    bot.add_cog(OPWelcome(bot))
