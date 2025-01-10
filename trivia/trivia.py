import discord
from redbot.core import commands, Config
import aiohttp
import random
import asyncio
import logging
from typing import List, Tuple

log = logging.getLogger("red.trivia")

class Trivia(commands.Cog):
    """A Trivia system with GitHub integration and custom quizzes."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567891)
        default_guild = {
            "channel_id": None,  # Channel where trivia is hosted
            "leaderboard": {},  # Points per user
            "github_url": "https://raw.githubusercontent.com/AfterWorld/UltDev/main/trivia/questions/",  # Base folder
            "selected_file": None,  # Selected quiz file
            "github_token": None,  # Optional GitHub token for private repositories
        }
        self.github_api_url = "https://api.github.com/repos/AfterWorld/UltDev/contents/trivia/questions/"
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

    @trivia.command(name="list")
    async def list_quizzes(self, ctx):
        """List available trivia quizzes."""
        quizzes = await self.fetch_quiz_files(ctx.guild)
        if not quizzes:
            return await ctx.send("No trivia quizzes are currently available.")
        await ctx.send(f"Available quizzes: {', '.join(quizzes)}")

    @trivia.command(name="start")
    async def start_trivia(self, ctx, quiz_name: str):
        """Start a trivia session with the selected quiz."""
        quizzes = await self.fetch_quiz_files(ctx.guild)
        if quiz_name not in quizzes:
            return await ctx.send(f"Invalid quiz name. Use `.trivia list` to see available quizzes.")

        await self.config.guild(ctx.guild).selected_file.set(quiz_name)
        self.trivia_active = True
        self.trivia_channel = ctx.channel
        await ctx.send(f"Starting trivia quiz: **{quiz_name}**! Get ready to answer.")
        await self.run_trivia(ctx.guild)

    @trivia.command(name="stop")
    async def stop_trivia(self, ctx):
        """Stop the active trivia session."""
        if not self.trivia_active:
            return await ctx.send("No active trivia session to stop.")
        
        self.trivia_active = False
        self.current_question = None
        self.current_answers = []
        self.trivia_channel = None
        await ctx.send("Trivia session stopped!")

    @trivia.command(name="leaderboard")
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

    @commands.admin_or_permissions(manage_guild=True)
    @trivia.command(name="settoken")
    async def set_github_token(self, ctx, token: str):
        """Set the GitHub API token for accessing private repositories."""
        await self.config.guild(ctx.guild).github_token.set(token)
        await ctx.send("GitHub API token has been saved.")
    
    # ==============================
    # BACKGROUND TASK
    # ==============================
    async def run_trivia(self, guild):
        """Main trivia loop."""
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id:
            channel_id = self.trivia_channel.id  # Default to the starting channel
        channel = guild.get_channel(channel_id)

        questions = await self.fetch_questions(guild)
        while self.trivia_active:
            question, answers = random.choice(questions)
            self.current_question = question
            self.current_answers = answers

            await channel.send(f"**Trivia Question:**\n{question}")
            for i in range(30, 0, -5):  # Countdown with 5-second intervals
                await asyncio.sleep(5)
                if not self.current_question:
                    break
                if i == 15:
                    await channel.send("**Hint:** First letter of the answer: " + ", ".join([a[0] for a in answers]))

            if self.current_question:  # Time's up
                await channel.send(f"Time's up! The correct answer was: {', '.join(answers)}.")
                self.current_question = None
                self.current_answers = []

            await asyncio.sleep(5)  # Short pause before next question

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
    async def fetch_quiz_files(self, guild) -> List[str]:
        """Fetch available quiz files from the GitHub folder."""
        github_url = await self.config.guild(guild).github_url()
        token = await self.config.guild(guild).github_token()
        headers = {"Authorization": f"token {token}"} if token else {}
    
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(github_url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch quizzes: {response.status} - {response.reason}")
                        return []
                    content = await response.text()
                    return [line.strip().replace(".txt", "") for line in content.split("\n") if line.endswith(".txt")]
            except Exception as e:
                log.exception("Error while fetching quiz files")
                return []
    
        async def fetch_questions(self, guild) -> List[Tuple[str, List[str]]]:
            """Fetch trivia questions for the selected quiz."""
            selected_file = await self.config.guild(guild).selected_file()
            github_url = f"{await self.config.guild(guild).github_url()}{selected_file}.txt"
            token = await self.config.guild(guild).github_token()
            headers = {"Authorization": f"token {token}"} if token else {}
        
            async with aiohttp.ClientSession(headers=headers) as session:
                try:
                    async with session.get(github_url) as response:
                        if response.status != 200:
                            log.error(f"Failed to fetch questions for quiz '{selected_file}': {response.status} - {response.reason}")
                            return []
                        content = await response.text()
        
                    questions = []
                    for line in content.strip().split("\n"):
                        if ":" in line and line.startswith("-"):
                            question, answers = line.split(":", 1)
                            answers = [ans.strip() for ans in answers.strip().split("\n") if ans.startswith("-")]
                            questions.append((question.strip(), answers))
                    return questions
                except Exception as e:
                    log.exception("Error while fetching questions")
                    return []


def setup(bot):
    bot.add_cog(Trivia(bot))
