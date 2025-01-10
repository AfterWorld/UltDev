import discord
from redbot.core import commands, Config
import random
import aiohttp
import asyncio
from typing import List, Tuple

class Trivia(commands.Cog):
    """A Trivia system with GitHub integration and natural interaction."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567891)
        default_guild = {
            "channel_id": None,  # Channel where trivia is hosted
            "leaderboard": {},  # Points per user
            "github_url": "https://raw.githubusercontent.com/AfterWorld/UltDev/main/trivia/questions/questions.txt",
        }
        self.config.register_guild(**default_guild)
        self.current_question = None  # Active question
        self.current_answers = []  # Correct answers
        self.trivia_active = False  # Trivia session status
        self.trivia_channel = None  # Channel object for trivia

    # ==============================
    # USER COMMANDS
    # ==============================
    @commands.group()
    @commands.guild_only()
    async def trivia(self, ctx):
        """User commands for trivia."""
        pass

    @trivia.command()
    async def start(self, ctx):
        """Start a trivia session."""
        if self.trivia_active:
            return await ctx.send("Trivia is already active!")
        
        self.trivia_active = True
        self.trivia_channel = ctx.channel
        await ctx.send("Starting trivia! Get ready to answer.")
        await self.run_trivia(ctx.guild)

    @trivia.command()
    async def stop(self, ctx):
        """Stop the trivia session."""
        if not self.trivia_active:
            return await ctx.send("No active trivia session to stop.")
        
        self.trivia_active = False
        self.current_question = None
        self.current_answers = []
        self.trivia_channel = None
        await ctx.send("Trivia session stopped!")

    @trivia.command()
    async def leaderboard(self, ctx):
        """View the trivia leaderboard."""
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if not leaderboard:
            return await ctx.send("No one has scored any points yet!")

        sorted_leaderboard = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
        embed = discord.Embed(title="Trivia Leaderboard", color=discord.Color.blue())
        for i, (user_id, points) in enumerate(sorted_leaderboard[:10], start=1):
            user = ctx.guild.get_member(user_id)
            username = user.display_name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"{i}. {username}", value=f"{points} points", inline=False)

        await ctx.send(embed=embed)

    # ==============================
    # BACKGROUND TASK
    # ==============================
    async def run_trivia(self, guild):
        """Main trivia loop."""
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id:
            channel_id = self.trivia_channel.id  # Default to the starting channel
        channel = guild.get_channel(channel_id)

        questions = await self.fetch_questions()
        while self.trivia_active:
            question, answers, hints = random.choice(questions)
            self.current_question = question
            self.current_answers = answers

            await channel.send(f"**Trivia Question:**\n{question}")
            await asyncio.sleep(15)

            if self.current_question:
                await channel.send(f"**Hint 1:** {hints[0]}")
            await asyncio.sleep(10)

            if self.current_question:
                await channel.send(f"**Hint 2:** {hints[1]}")
            await asyncio.sleep(5)

            if self.current_question:
                await channel.send(f"Time's up! The correct answer was: {', '.join(answers)}.")
                self.current_question = None
                self.current_answers = []

            await asyncio.sleep(10)  # Short pause before the next question

    # ==============================
    # EVENT LISTENER
    # ==============================
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for correct answers in the trivia channel."""
        if (
            not self.trivia_active or
            not self.current_question or
            message.channel != self.trivia_channel or
            message.author.bot
        ):
            return

        if message.content.lower() in [answer.lower() for answer in self.current_answers]:
            points = 10
            async with self.config.guild(message.guild).leaderboard() as leaderboard:
                leaderboard[message.author.id] = leaderboard.get(message.author.id, 0) + points

            self.current_question = None  # Clear current question
            self.current_answers = []
            await message.channel.send(f"Correct! {message.author.mention} earns {points} points!")

    # ==============================
    # GITHUB INTEGRATION
    # ==============================
    async def fetch_questions(self) -> List[Tuple[str, List[str], List[str]]]:
        """Fetch trivia questions from GitHub."""
        github_url = await self.config.guild(self.bot.guilds[0]).github_url()
        async with aiohttp.ClientSession() as session:
            async with session.get(github_url) as response:
                if response.status != 200:
                    raise ValueError("Failed to fetch trivia questions.")
                content = await response.text()

        questions = []
        for line in content.strip().split("\n"):
            if "| A:" in line and "| H:" in line:
                question, rest = line.split("| A:")
                answers, hints = rest.split("| H:")
                questions.append((
                    question.strip(),
                    [a.strip() for a in answers.split(",")],
                    [h.strip() for h in hints.split(",")]
                ))
        return questions
