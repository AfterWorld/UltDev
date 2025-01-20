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
        }
        self.config.register_guild(**default_guild)
        self.op_facts = [
            "The One Piece world has more than 500 devil fruits!",
            "Eiichiro Oda started writing One Piece in 1997.",
            "Luffy's favorite food is meat!",
            "The Going Merry was partly inspired by Viking ships!",
            "Oda originally planned One Piece to last five years!",
            "The longest arc in One Piece is the Dressrosa arc!",
            "Zoro's character is inspired by the real-life pirate François l'Olonnais!",
            "Sanji was originally going to be named 'Naruto'!",
            "The One Piece manga has sold over 480 million copies worldwide!",
            "The creator, Eiichiro Oda, rarely takes breaks from writing One Piece!",
            "The Straw Hat Pirates' ship, the Thousand Sunny, was designed by Franky!",
            "Nami's tattoo is a homage to her adoptive mother, Bell-mère!",
            "Robin's favorite food is sandwiches!",
            "Chopper is a reindeer who ate the Hito Hito no Mi, a Zoan-type Devil Fruit!",
            "Brook is a living skeleton who can use the power of the Yomi Yomi no Mi!",
            "Franky is a cyborg who built himself after being severely injured!",
            "Jinbe is a fish-man and a master of Fish-Man Karate!",
            "The One Piece anime has over 1000 episodes!",
            "The One Piece world is divided into four seas: East Blue, West Blue, North Blue, and South Blue!",
            "The Grand Line is known as the pirate's graveyard due to its dangerous conditions!",
            "The Revolutionary Army is led by Luffy's father, Monkey D. Dragon!",
            "The World Government is the main antagonist organization in One Piece!",
            "The Marines are the military sea force of the World Government!",
            "The Yonko are the four most powerful pirates in the world!",
            "The Shichibukai were a group of seven powerful pirates allied with the World Government!",
            "The One Piece treasure is said to be located at the end of the Grand Line, on an island called Raftel!",
            "The Will of D is a mysterious concept in the One Piece world!",
            "Haki is a mysterious power that allows the user to utilize their own spiritual energy for various purposes!",
            "The One Piece world has three types of Haki: Observation Haki, Armament Haki, and Conqueror's Haki!",
            "The One Piece manga holds the Guinness World Record for the most copies published for the same comic book series by a single author!"
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

        rules_channel = guild.get_channel(590972222366023718)
        roles_channel = guild.get_channel(597528644432166948)

        embed = discord.Embed(
            title=f"🏴‍☠️ Welcome to the {guild.name} Crew! 🏴‍☠️",
            description=f"Ahoy, {member.mention if member.mention else member.name}! You've just embarked on a grand adventure!",
            color=discord.Color.blue()
        )

        embed.set_thumbnail(url=member.display_avatar.url)

        if rules_channel and roles_channel:
            embed.add_field(
                name="📜 First Steps on Your Journey",
                value=f"Please check out the {rules_channel.mention} and {roles_channel.mention} channels.",
                inline=False
            )

        embed.add_field(
            name="💡 Did You Know?",
            value=random.choice(self.op_facts),
            inline=False
        )

        embed.add_field(
            name="🛠️ Role Assignment",
            value="Head over to the roles channel to assign yourself roles!",
            inline=False
        )

        embed.add_field(
            name="📢 Message from the Admins",
            value="Welcome to our server! We hope you have a great time here. If you have any questions, feel free to ask!",
            inline=False
        )

        embed.set_footer(text=f"You're our {guild.member_count}th crew member!")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            await guild.owner.send(f"I don't have permission to send messages in {channel.mention}")

async def setup(bot):
    await bot.add_cog(OPWelcome(bot))
