import discord
from redbot.core import commands, Config
import aiohttp
import yaml
import random
import asyncio
from typing import List, Tuple
import logging
import base64

log = logging.getLogger("red.trivia")

class Trivia(commands.Cog):
    """A trivia game with YAML-based questions."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543212, force_registration=True)
        default_guild = {
            "github_url": "https://api.github.com/repos/AfterWorld/UltDev/contents/trivia/questions/",
            "selected_genre": None,
        }
        self.config.register_guild(**default_guild)
        self.trivia_active = False
        self.current_question = None
        self.current_answers = []
        self.current_hints = []
        self.trivia_channel = None

    @commands.group()
    async def trivia(self, ctx):
        """Trivia commands."""
        pass

    @trivia.command()
    async def list(self, ctx):
        """List available trivia genres."""
        genres = await self.fetch_genres(ctx.guild)
        if not genres:
            return await ctx.send("No trivia genres available.")
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
        if self.trivia_active:
            self.trivia_active = False
            await ctx.send("Trivia session stopped.")
        else:
            await ctx.send("No trivia session is currently running.")

    @trivia.command()
    async def hint(self, ctx):
        """Get a hint for the current question."""
        if not self.trivia_active or not self.current_question:
            return await ctx.send("No trivia question is currently active.")
        
        if not self.current_hints:
            return await ctx.send("No hints available for this question.")
            
        hint = self.current_hints.pop(0) if self.current_hints else "No more hints available!"
        await ctx.send(f"**Hint:** {hint}")

    def get_partial_answer(self, answer: str, reveal_percentage: float) -> str:
        """Returns a partially revealed answer."""
        if not answer:
            return ""
        chars = list(answer)
        reveal_count = int(len(chars) * reveal_percentage)
        for i in range(len(chars) - reveal_count):
            if chars[i].isalnum():
                chars[i] = '_'
        return ''.join(chars)

    async def run_trivia(self, guild):
        """Main trivia loop."""
        channel = self.trivia_channel
        genre = await self.config.guild(guild).selected_genre()
        questions = await self.fetch_questions(guild, genre)

        if not questions:
            await channel.send(f"No questions found for the genre '{genre}'. Please check the file.")
            self.trivia_active = False
            return

        while self.trivia_active:
            question_data = random.choice(questions)
            self.current_question = question_data["question"]
            self.current_answers = question_data["answers"]
            self.current_hints = question_data.get("hints", []).copy()  # Make a copy of hints
            main_answer = self.current_answers[0]  # Use first answer as main answer for reveals

            await channel.send(f"**Trivia Question:**\n{self.current_question}\n*Use `!trivia hint` for a hint!*")
            
            for i in range(30, 0, -5):  # Countdown
                await asyncio.sleep(5)
                if not self.current_question:  # Stop if answered
                    break

                if i == 15:  # At 15 seconds, reveal 33% of the answer
                    partial_answer = self.get_partial_answer(main_answer, 0.33)
                    await channel.send(f"**15 seconds left!** The answer looks like: {partial_answer}")
                elif i == 10:  # At 10 seconds, reveal 66% of the answer
                    partial_answer = self.get_partial_answer(main_answer, 0.66)
                    await channel.send(f"**10 seconds left!** The answer looks like: {partial_answer}")

            if self.current_question:  # Time's up
                await channel.send(f"Time's up! The correct answer was: {main_answer}")
                self.current_question = None
                self.current_answers = []
                self.current_hints = []

            await asyncio.sleep(5)  # Pause before next question

    async def fetch_genres(self, guild) -> List[str]:
        """Fetch available genres."""
        github_url = f"{await self.config.guild(guild).github_url()}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(github_url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch genres: {response.status} - {response.reason}")
                        return []
                    data = await response.json()
                    return [item["name"].replace(".yaml", "") for item in data if item["name"].endswith(".yaml")]
        except Exception as e:
            log.error(f"Error while fetching genres: {str(e)}")
            return []

    async def fetch_questions(self, guild, genre: str) -> List[dict]:
        """Fetch questions for the selected genre."""
        github_url = f"{await self.config.guild(guild).github_url()}{genre}.yaml"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(github_url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch questions for genre '{genre}': {response.status} - {response.reason}")
                        return []

                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    return yaml.safe_load(content)
        except Exception as e:
            log.error(f"Error while fetching questions for genre '{genre}': {str(e)}")
            return []

def setup(bot):
    bot.add_cog(Trivia(bot))
