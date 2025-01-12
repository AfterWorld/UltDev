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
        self.channel_states = {}  # State per channel

    def get_channel_state(self, channel: discord.TextChannel):
        """Get or initialize the trivia state for a specific channel."""
        if channel.id not in self.channel_states:
            self.channel_states[channel.id] = TriviaState()
        return self.channel_states[channel.id]

    @commands.group()
    async def trivia(self, ctx):
        """Trivia commands."""
        pass

    @trivia.command()
    async def start(self, ctx, genre: str):
        """Start a trivia session in this channel."""
        state = self.get_channel_state(ctx.channel)

        if state.active:
            await ctx.send("A trivia session is already running in this channel!")
            return

        genres = await self.fetch_genres(ctx.guild)
        if genre not in genres:
            await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")
            return

        log.info(f"Starting trivia with genre: {genre} in channel: {ctx.channel.id}")
        state.reset()  # Ensure a clean state before starting
        state.active = True
        state.channel = ctx.channel
        await self.config.guild(ctx.guild).selected_genre.set(genre)
        await self.config.guild(ctx.guild).last_active.set(discord.utils.utcnow().timestamp())

        # Increment games played
        games_played = await self.config.guild(ctx.guild).games_played()
        await self.config.guild(ctx.guild).games_played.set(games_played + 1)

        await ctx.send(f"Starting trivia for the **{genre}** genre. Get ready!")
        state.task = asyncio.create_task(self.run_trivia(ctx.guild, ctx.channel))

    @trivia.command()
    async def stop(self, ctx):
        """Stop the trivia session in this channel."""
        state = self.get_channel_state(ctx.channel)

        if not state.active:
            await ctx.send("No trivia session is currently running in this channel.")
            return

        state.reset()
        await ctx.send("Trivia session stopped.")

    async def run_trivia(self, guild, channel):
        """Main trivia loop for a specific channel."""
        state = self.get_channel_state(channel)
        try:
            genre = await self.config.guild(guild).selected_genre()
            questions = await self.fetch_questions(guild, genre)

            if not questions:
                await channel.send(f"No questions found for the genre '{genre}'.")
                state.reset()
                return

            # Filter unused questions
            while state.active:
                available_questions = [q for q in questions if q["question"] not in state.used_questions]
                if not available_questions:
                    await channel.send("All questions have been used! Reshuffling the question pool...")
                    state.used_questions.clear()
                    available_questions = questions

                question_data = random.choice(available_questions)
                state.question = question_data["question"]
                state.answers = question_data["answers"]
                state.hints = question_data.get("hints", [])
                state.used_questions.add(state.question)

                await self._handle_question_round(channel, guild, state)

        except asyncio.CancelledError:
            log.info("Trivia task cancelled.")
        except Exception as e:
            log.error(f"Error in trivia loop: {e}")
        finally:
            state.reset()

    async def _handle_question_round(self, channel, guild, state):
        """Handle a single question round."""
        await channel.send(f"**Trivia Question:** {state.question}\nType your answer below!")

        for i in range(30, 0, -5):  # 30 seconds timer
            if not state.active:
                return
            await asyncio.sleep(5)
            if not state.question:
                break

            # Provide hints at 15 and 10 seconds
            if i in (15, 10):
                partial_answer = self.get_partial_answer(
                    state.answers[0],
                    0.66 if i == 10 else 0.33
                )
                await channel.send(f"**{i} seconds left!** Hint: {partial_answer}")

        if state.question and state.active:
            await channel.send(f"Time's up! The correct answer was: {state.answers[0]}")
            state.question = None
            state.answers = []
            state.hints = []

        await asyncio.sleep(5)

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

    async def add_score(self, guild, user_id: int, points: int):
        """Add points to both current and total scores."""
        async with self.config.guild(guild).scores() as scores:
            scores[str(user_id)] = scores.get(str(user_id), 0) + points
        async with self.config.guild(guild).total_scores() as total_scores:
            total_scores[str(user_id)] = total_scores.get(str(user_id), 0) + points

    @commands.Cog.listener()
    async def on_message(self, message):
        """Check messages for trivia answers."""
        if message.author.bot:
            return

        state = self.channel_states.get(message.channel.id)
        if not state or not state.active or not state.question:
            return

        correct_answers = [ans.lower().strip() for ans in state.answers]
        if message.content.lower().strip() in correct_answers:
            points = 10
            await self.add_score(message.guild, message.author.id, points)
            await message.add_reaction("✅")
            await state.channel.send(
                f"🎉 Correct, {message.author.mention}! (+{points} points)\n"
                f"The answer was: {state.answers[0]}"
            )
            state.question = None  # Clear the question for the next round
            
def setup(bot):
    bot.add_cog(Trivia(bot))
