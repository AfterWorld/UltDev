import discord
from redbot.core import commands, Config
import random
import aiohttp
import asyncio
import json
import base64
from typing import List, Tuple

import logging
log = logging.getLogger("red.trivia")


class Trivia(commands.Cog):
    """A Trivia cog with GitHub integration and genre-based questions."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543211, force_registration=True)
        default_guild = {
            "channel_id": None,  # Channel for trivia
            "github_url": "https://raw.githubusercontent.com/AfterWorld/UltDev/main/trivia/questions/",
            "github_token": None,  # GitHub API token
            "selected_genre": None,  # Active genre
            "leaderboard": {},  # Leaderboard data
        }
        self.config.register_guild(**default_guild)
        self.trivia_active = False
        self.current_question = None
        self.current_answers = []
        self.trivia_channel = None

    # ==============================
    # COMMANDS
    # ==============================
    @commands.group()
    @commands.guild_only()
    async def trivia(self, ctx):
        """Trivia commands."""
        pass

    @trivia.command()
    async def list(self, ctx):
        """List available trivia genres."""
        genres = await self.fetch_genres(ctx.guild)
        if not genres:
            return await ctx.send("No trivia genres are available.")
        await ctx.send(f"Available trivia genres: {', '.join(genres)}")

    @trivia.command()
    async def start(self, ctx, genre: str):
        """Start a trivia session with the selected genre."""
        genres = await self.fetch_genres(ctx.guild)
        if genre not in genres:
            return await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")

        await self.config.guild(ctx.guild).selected_genre.set(genre)
        self.trivia_active = True
        self.trivia_channel = ctx.channel
        await ctx.send(f"Starting trivia for the **{genre}** genre. Get ready!")
        await self.run_trivia(ctx.guild)

    @trivia.command()
    async def stop(self, ctx):
        """Stop the current trivia session."""
        if not self.trivia_active:
            return await ctx.send("No active trivia session to stop.")
        self.trivia_active = False
        self.current_question = None
        self.current_answers = []
        await ctx.send("Trivia session stopped.")

    @trivia.command()
    async def leaderboard(self, ctx):
        """View the trivia leaderboard."""
        leaderboard = await self.config.guild(ctx.guild).leaderboard()
        if not leaderboard:
            return await ctx.send("No one has scored any points yet!")

        sorted_lb = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
        embed = discord.Embed(title="Trivia Leaderboard", color=discord.Color.blue())
        for i, (user_id, points) in enumerate(sorted_lb[:10], start=1):
            user = ctx.guild.get_member(user_id)
            username = user.display_name if user else f"Unknown User ({user_id})"
            embed.add_field(name=f"{i}. {username}", value=f"{points} points", inline=False)

        await ctx.send(embed=embed)

    @trivia.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def settoken(self, ctx, token: str):
        """Set the GitHub API token for accessing private repositories."""
        await self.config.guild(ctx.guild).github_token.set(token)
        await ctx.send("GitHub API token has been saved.")

    # ==============================
    # TRIVIA GAME LOGIC
    # ==============================
    async def run_trivia(self, guild):
        """Main trivia loop."""
        channel = self.trivia_channel
        genre = await self.config.guild(guild).selected_genre()
        questions = await self.fetch_questions(guild, genre)

        while self.trivia_active:
            question, answers = random.choice(questions)
            self.current_question = question
            self.current_answers = answers

            await channel.send(f"**Trivia Question:**\n{question}")
            await asyncio.sleep(30)

            if self.current_question:  # Time's up
                await channel.send(f"Time's up! The correct answers were: {', '.join(answers)}.")
                self.current_question = None
                self.current_answers = []

            await asyncio.sleep(10)

    # ==============================
    # EVENT LISTENER
    # ==============================
    @commands.Cog.listener()
    async def on_message(self, message):
        """Check for correct answers."""
        if not self.trivia_active or not self.current_question or message.channel != self.trivia_channel or message.author.bot:
            return

        if message.content.lower() in [a.lower() for a in self.current_answers]:
            points = 10
            async with self.config.guild(message.guild).leaderboard() as leaderboard:
                leaderboard[message.author.id] = leaderboard.get(message.author.id, 0) + points

            self.current_question = None
            self.current_answers = []
            await message.channel.send(f"Correct! {message.author.mention} earns {points} points!")

    # ==============================
    # GITHUB INTEGRATION
    # ==============================
    sync def fetch_genres(self, guild) -> List[str]:
        """Fetch available genres from the GitHub folder using the GitHub API."""
        github_url = "https://api.github.com/repos/AfterWorld/UltDev/contents/trivia/questions"
        token = await self.config.guild(guild).github_token()
        headers = {"Authorization": f"token {token}"} if token else {}
    
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(github_url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch genres: {response.status} - {response.reason}")
                        return []
    
                    data = await response.json()
                    # Extract `.txt` filenames
                    return [item["name"].replace(".txt", "") for item in data if item["name"].endswith(".txt")]
        except Exception as e:
            log.exception("Error while fetching genres")
            return []

    async def fetch_questions(self, guild, genre: str) -> List[Tuple[str, List[str]]]:
        """Fetch questions for the selected genre from the GitHub API."""
        github_url = f"https://raw.githubusercontent.com/AfterWorld/UltDev/main/trivia/questions/{genre}.txt"
    
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(github_url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch questions for genre '{genre}': {response.status} - {response.reason}")
                        return []
    
                    content = await response.text()
    
            questions = []
            for line in content.strip().split("\n"):
                if ":" in line:
                    question, answers = line.split(":", 1)
                    answers = [a.strip() for a in answers.split("\n") if a.startswith("-")]
                    questions.append((question.strip(), answers))
            return questions
        except Exception as e:
            log.exception(f"Error while fetching questions for genre '{genre}'")
            return []

def setup(bot):
    bot.add_cog(Trivia(bot))
