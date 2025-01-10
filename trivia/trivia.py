import discord
from discord.ext import tasks
from redbot.core import commands, Config, checks
from typing import Optional, List, Tuple
import aiohttp
import random
import asyncio
from datetime import datetime

class Trivia(commands.Cog):
    """A Trivia Cog with QOTD, leaderboards, and more!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        default_guild = {
            "questions": {},  # Questions from the GitHub repository
            "leaderboard": {},  # User points
            "current_question": None,  # Current question being asked
            "current_hints": None,  # Hints for the current question
        }
        self.config.register_guild(**default_guild)

        self.trivia_task = None
        self.fetch_questions_task.start()

    def cog_unload(self):
        if self.trivia_task:
            self.trivia_task.cancel()
        self.fetch_questions_task.cancel()

    async def fetch_github_questions(self) -> dict:
        """Fetch questions from a GitHub file."""
        github_url = "https://raw.githubusercontent.com/yourusername/yourrepo/main/questions.txt"
        async with aiohttp.ClientSession() as session:
            async with session.get(github_url) as response:
                if response.status != 200:
                    raise ValueError("Failed to fetch questions from GitHub.")
                content = await response.text()

        questions = {}
        for line in content.strip().split("\n"):
            if line.startswith("Q:") and "| A:" in line:
                question, answers = line.split("| A:")
                question = question[2:].strip()
                answers = [a.strip() for a in answers.split(",")]
                if question and answers:
                    questions[question] = answers
        return questions

    @tasks.loop(hours=1)
    async def fetch_questions_task(self):
        """Fetch and update questions from GitHub every hour."""
        for guild in self.bot.guilds:
            try:
                questions = await self.fetch_github_questions()
                async with self.config.guild(guild).questions() as questions_dict:
                    questions_dict.update(questions)
            except Exception as e:
                print(f"Failed to update questions for guild {guild.id}: {e}")

    @commands.group()
    @commands.guild_only()
    async def trivia(self, ctx):
        """Trivia commands."""
        pass

    @trivia.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def start(self, ctx):
        """Start a trivia game."""
        if self.trivia_task:
            return await ctx.send("Trivia is already running!")

        self.trivia_task = self.bot.loop.create_task(self.run_trivia(ctx))

    @trivia.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def stop(self, ctx):
        """Stop the trivia game."""
        if self.trivia_task:
            self.trivia_task.cancel()
            self.trivia_task = None
            await ctx.send("Trivia game stopped!")
        else:
            await ctx.send("No trivia game is currently running.")

    async def run_trivia(self, ctx):
        """Main trivia game loop."""
        while True:
            questions = await self.config.guild(ctx.guild).questions()
            if not questions:
                await ctx.send("No questions available. Please update the GitHub file.")
                return

            question, answers = random.choice(list(questions.items()))
            hints = [answer[:len(answer) // 2] for answer in answers]

            await ctx.send(f"**Trivia Time!**\n\n{question}")
            await self.config.guild(ctx.guild).current_question.set({"question": question, "answers": answers})
            await self.config.guild(ctx.guild).current_hints.set(hints)

            answered = False

            for i in range(30, 0, -5):  # Countdown in steps of 5 seconds
                if i in {15, 10, 5}:
                    hint = random.choice(hints)
                    await ctx.send(f"Hint: {hint}")
                await asyncio.sleep(5)

                current_data = await self.config.guild(ctx.guild).current_question()
                if not current_data:  # Someone already answered correctly
                    answered = True
                    break

            if not answered:
                await ctx.send(f"Time's up! The correct answer was: {', '.join(answers)}.")

            await self.config.guild(ctx.guild).current_question.clear()
            await self.config.guild(ctx.guild).current_hints.clear()
            await asyncio.sleep(5)  # Short delay before next question

    @trivia.command()
    async def answer(self, ctx, *, answer: str):
        """Answer the current trivia question."""
        current_data = await self.config.guild(ctx.guild).current_question()
        if not current_data:
            return await ctx.send("There is no active trivia question!")

        question = current_data["question"]
        correct_answers = current_data["answers"]

        if answer.lower() in [a.lower() for a in correct_answers]:
            points = 10
            async with self.config.guild(ctx.guild).leaderboard() as leaderboard:
                leaderboard[ctx.author.id] = leaderboard.get(ctx.author.id, 0) + points

            await ctx.send(f"Correct! You earned {points} points.")
            await self.config.guild(ctx.guild).current_question.clear()  # Stop the timer
        else:
            await ctx.send("Incorrect! Try again.")

    @trivia.command()
    async def leaderboard(self, ctx):
        """Display the trivia leaderboard."""
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if not leaderboard:
            return await ctx.send("No one has earned any points yet!")

        sorted_leaderboard = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
        top_ten = sorted_leaderboard[:10]

        embed = discord.Embed(title="Trivia Leaderboard", color=discord.Color.blue())
        for i, (user_id, points) in enumerate(top_ten, start=1):
            user = ctx.guild.get_member(user_id)
            username = user.display_name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"{i}. {username}", value=f"{points} points", inline=False)

        await ctx.send(embed=embed)
