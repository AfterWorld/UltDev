from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import discord
import random
import asyncio

class OnePieceBot(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "trivia_channel": None,
            "conversation_channels": [],
            "trivia_frequency": 3600,  # Default: every hour
        }
        default_member = {
            "belis": 0,
        }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)
        self.trivia_task = self.bot.loop.create_task(self.trivia_loop())

    def cog_unload(self):
        self.trivia_task.cancel()

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setopbot(self, ctx, setting: str, *, value: str):
        """Configure One Piece Bot settings"""
        guild = ctx.guild
        if setting == "trivia_channel":
            channel = await commands.TextChannelConverter().convert(ctx, value)
            await self.config.guild(guild).trivia_channel.set(channel.id)
            await ctx.send(f"Trivia channel set to {channel.mention}")
        elif setting == "add_conversation_channel":
            channel = await commands.TextChannelConverter().convert(ctx, value)
            async with self.config.guild(guild).conversation_channels() as channels:
                if channel.id not in channels:
                    channels.append(channel.id)
            await ctx.send(f"Added {channel.mention} to conversation channels")
        elif setting == "trivia_frequency":
            frequency = int(value)
            await self.config.guild(guild).trivia_frequency.set(frequency)
            await ctx.send(f"Trivia frequency set to every {frequency} seconds")
        else:
            await ctx.send("Invalid setting. Available settings: trivia_channel, add_conversation_channel, trivia_frequency")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild = message.guild
        if not guild:
            return

        channel_ids = await self.config.guild(guild).conversation_channels()
        if message.channel.id in channel_ids:
            # Process the message and generate a response
            response = await self.generate_response(message.content)
            if response:
                await message.channel.send(response)

    async def generate_response(self, message_content: str):
        # This is where you'd integrate with an AI model to generate responses
        # For this example, we'll use a simple randomized response
        responses = [
            "Yohohoho! That's interesting!",
            "Gomu Gomu no... response!",
            "Have you seen the One Piece yet?",
            "Nami-swan! Robin-chwan!",
            "SUUUUUPER!",
        ]
        return random.choice(responses)

    async def trivia_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            for guild in self.bot.guilds:
                channel_id = await self.config.guild(guild).trivia_channel()
                if channel_id:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        question, answer = self.get_random_trivia()
                        await channel.send(f"One Piece Trivia Time! {question}")
                        await asyncio.sleep(30)  # Wait for 30 seconds before revealing the answer
                        await channel.send(f"The answer is: {answer}")

            frequency = await self.config.guild(guild).trivia_frequency()
            await asyncio.sleep(frequency)

    def get_random_trivia(self):
        # This is where you'd implement your trivia system
        # For this example, we'll use a simple list
        trivia_list = [
            ("What is the name of Luffy's pirate crew?", "The Straw Hat Pirates"),
            ("Who is known as the 'Pirate Hunter'?", "Roronoa Zoro"),
            ("What is the name of the legendary treasure in One Piece?", "The One Piece"),
        ]
        return random.choice(trivia_list)

    @commands.command()
    async def belis(self, ctx):
        """Check your current Belis balance"""
        member = ctx.author
        belis = await self.config.member(member).belis()
        await ctx.send(f"{member.display_name}, you have {belis} Belis!")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def award_belis(self, ctx, member: discord.Member, amount: int):
        """Award Belis to a member"""
        async with self.config.member(member).belis() as belis:
            belis += amount
        await ctx.send(f"Awarded {amount} Belis to {member.display_name}!")

def setup(bot):
    bot.add_cog(OnePieceBot(bot))
