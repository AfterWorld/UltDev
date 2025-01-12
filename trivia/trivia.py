import discord
from redbot.core import commands, Config
import aiohttp
import yaml
import random
import asyncio
from typing import List, Optional
import logging
import base64

log = logging.getLogger("red.trivia")

class TriviaState:
    """Class to manage trivia game state."""
    def __init__(self):
        self.active = False
        self.question: Optional[str] = None
        self.answers: List[str] = []
        self.hints: List[str] = []
        self.channel: Optional[discord.TextChannel] = None
        self.task: Optional[asyncio.Task] = None
        self.used_questions: set = set()

    def reset(self):
        """Reset all state variables."""
        self.active = False
        self.question = None
        self.answers = []
        self.hints = []
        self.channel = None
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = None
        self.used_questions.clear()

class Trivia(commands.Cog):
    """A trivia game with YAML-based questions."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543212, force_registration=True)
        default_guild = {
            "github_url": "https://api.github.com/repos/AfterWorld/UltDev/contents/trivia/questions/",
            "selected_genre": None,
            "scores": {},
            "total_scores": {},
            "games_played": 0,
            "questions_answered": 0,
            "last_active": None
        }
        self.config.register_guild(**default_guild)
        self.state = TriviaState()
        self._cleanup_task = asyncio.create_task(self._cleanup_stale_games())

    async def _cleanup_stale_games(self):
        """Clean up stale games."""
        while True:
            try:
                if self.state.active and self.state.channel:
                    last_active = await self.config.guild(self.state.channel.guild).last_active()
                    if last_active and (discord.utils.utcnow().timestamp() - last_active) > 1800:
                        log.info("Resetting stale trivia state due to inactivity.")
                        await self.state.channel.send("Trivia game automatically stopped due to inactivity.")
                        self.state.reset()
            except Exception as e:
                log.error(f"Error in cleanup task: {e}")
            await asyncio.sleep(300)

    @commands.group()
    async def trivia(self, ctx):
        """Trivia commands."""
        pass

    @trivia.command()
    async def start(self, ctx, genre: str):
        """Start a trivia session with the selected genre."""
        try:
            if self.state.active:
                await ctx.send("A trivia session is already running!")
                return
    
            genres = await self.fetch_genres(ctx.guild)
            if genre not in genres:
                await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")
                return
    
            log.info(f"Starting trivia with genre: {genre}")
            self.state.reset()  # Ensure a clean state before starting
            self.state.active = True
            self.state.channel = ctx.channel
            await self.config.guild(ctx.guild).selected_genre.set(genre)
            await self.config.guild(ctx.guild).last_active.set(discord.utils.utcnow().timestamp())
    
            # Increment games played
            games_played = await self.config.guild(ctx.guild).games_played()
            await self.config.guild(ctx.guild).games_played.set(games_played + 1)
    
            await ctx.send(f"Starting trivia for the **{genre}** genre. Get ready!")
            self.state.task = asyncio.create_task(self.run_trivia(ctx.guild))
    
        except Exception as e:
            log.error(f"Error starting trivia: {e}")
            await ctx.send("An error occurred while starting the trivia game.")
            self.state.reset()


    @trivia.command()
    async def stop(self, ctx):
        """Stop the current trivia session."""
        if not self.state.active:
            await ctx.send("No trivia session is currently running.")
            return
        self.state.reset()
        await ctx.send("Trivia session stopped.")

    async def run_trivia(self, guild):
        """Main trivia loop."""
        try:
            genre = await self.config.guild(guild).selected_genre()
            questions = await self.fetch_questions(guild, genre)
            if not questions:
                await self.state.channel.send(f"No questions found for the genre '{genre}'.")
                self.state.reset()
                return

            while self.state.active:
                question_data = random.choice(questions)
                self.state.question = question_data["question"]
                self.state.answers = question_data["answers"]
                self.state.hints = question_data.get("hints", [])
                await self._ask_question()
                await asyncio.sleep(5)

        except asyncio.CancelledError:
            log.info("Trivia task cancelled.")
        except Exception as e:
            log.error(f"Error in trivia loop: {e}")
        finally:
            self.state.reset()

    async def _ask_question(self):
        """Send the question to the channel."""
        await self.state.channel.send(f"**Trivia Question:** {self.state.question}")

    async def fetch_genres(self, guild) -> List[str]:
        """Fetch available genres."""
        try:
            url = await self.config.guild(guild).github_url()
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    return [item["name"].replace(".yaml", "") for item in data if item["name"].endswith(".yaml")]
        except Exception as e:
            log.error(f"Error fetching genres: {e}")
            return []

    async def fetch_questions(self, guild, genre: str) -> List[dict]:
        """Fetch questions for the selected genre."""
        try:
            url = f"{await self.config.guild(guild).github_url()}{genre}.yaml"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    return yaml.safe_load(content)
        except Exception as e:
            log.error(f"Error fetching questions: {e}")
            return []

def setup(bot):
    bot.add_cog(Trivia(bot))
