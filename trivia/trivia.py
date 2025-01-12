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
        self.channel = None  # Clear the channel reference
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = None
        self.used_questions.clear()


class Trivia(commands.Cog):
    """A trivia game with YAML-based questions."""

    GENRE_DESCRIPTIONS = {
        "onepiece": "Questions about the One Piece anime and manga universe.",
        "science": "Test your knowledge about science and discoveries.",
        "movies": "Guess movies, characters, and actors!",
        "history": "How well do you know world history?",
        "sports": "Trivia about famous sports and athletes.",
    }

    TIMEOUT_MESSAGES = {
        "onepiece": [
            "⏰ Time's up! Even Luffy couldn't guess that one. The answer was: **{answer}**.",
            "You're out of time! Guess the One Piece isn't yours today. The answer was: **{answer}**.",
        ],
        "science": [
            "⏰ Time's up! Even Einstein would've needed more time. The answer was: **{answer}**.",
            "Oops, you're out of time! Better study the laws of the universe. The answer was: **{answer}**.",
        ],
        "movies": [
            "⏰ Time's up! That was a blockbuster miss. The answer was: **{answer}**.",
            "The credits rolled, and you're out of time! The answer was: **{answer}**.",
        ],
        "history": [
            "⏰ Time's up! This moment in history was lost to you. The answer was: **{answer}**.",
            "You're out of time! Better brush up on your history books. The answer was: **{answer}**.",
        ],
        "sports": [
            "⏰ Time's up! That was a foul on your part. The answer was: **{answer}**.",
            "You're out of time! Maybe try hitting the trivia gym. The answer was: **{answer}**.",
        ],
    }

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
            "last_active": None,
        }
        self.config.register_guild(**default_guild)
        self.channel_states = {}

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
    async def start(self, ctx, genre: str = None):
        """Start a trivia session in this channel."""
        state = self.get_channel_state(ctx.channel)

        if state.active:
            await ctx.send("A trivia session is already running in this channel!")
            return

        # Fetch available genres
        genres = await self.fetch_genres(ctx.guild)
        if not genres:
            await ctx.send("No trivia categories are currently available.")
            return

        # Show genres if no genre is provided
        if genre is None:
            embed = discord.Embed(
                title="📚 Available Trivia Categories",
                description="Use `.trivia start <genre>` to start a game!",
                color=discord.Color.green(),
            )
            for genre_name in genres:
                description = self.GENRE_DESCRIPTIONS.get(genre_name, "No description available.")
                embed.add_field(name=genre_name.title(), value=description, inline=False)
            await ctx.send(embed=embed)
            return

        # Validate selected genre
        if genre not in genres:
            await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")
            return

        log.info(f"Starting trivia with genre: {genre} in channel: {ctx.channel.id}")
        state.reset()  # Ensure a clean state before starting
        state.active = True
        state.channel = ctx.channel  # Set the channel where the game is running
        await self.config.guild(ctx.guild).selected_genre.set(genre)
        await self.config.guild(ctx.guild).last_active.set(discord.utils.utcnow().timestamp())

        games_played = await self.config.guild(ctx.guild).games_played()
        await self.config.guild(ctx.guild).games_played.set(games_played + 1)

        await ctx.send(f"Starting trivia for the **{genre}** genre. Get ready!")
        state.task = asyncio.create_task(self.run_trivia(ctx.guild, ctx.channel))

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
            session_scores = await self.config.guild(guild).scores()
            await self.display_session_recap(guild, channel, session_scores)
            await self.config.guild(guild).scores.set({})  # Clear session scores
            state.reset()

    async def _handle_question_round(self, channel, guild, state):
        """Handle a single question round."""
        await channel.send(f"**Trivia Question:** {state.question}\nType your answer below!")

        for i in range(30, 0, -5):
            if not state.active:
                return
            await asyncio.sleep(5)
            if not state.question:
                break

            if i in (15, 10):
                partial_answer = self.get_partial_answer(
                    state.answers[0],
                    0.66 if i == 10 else 0.33
                )
                await channel.send(f"**{i} seconds left!** Hint: {partial_answer}")

        if state.question and state.active:
            genre = await self.config.guild(guild).selected_genre()
            themed_messages = self.TIMEOUT_MESSAGES.get(genre, [
                "⏰ Time's up! The answer was: **{answer}**."
            ])
            timeout_message = random.choice(themed_messages).format(answer=state.answers[0])

            await channel.send(timeout_message)
            state.question = None
            state.answers = []
            state.hints = []

        await asyncio.sleep(5)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Check messages for trivia answers."""
        if message.author.bot:
            return

        state = self.channel_states.get(message.channel.id)
        if not state or not state.active or not state.question:
            return

        correct_answers = [ans.lower().strip() for ans in state.answers]
        user_answer = message.content.lower().strip()

        if user_answer in correct_answers:
            points = 10
            await self.add_score(message.guild, message.author.id, points)
            await message.add_reaction("✅")
            await state.channel.send(
                f"🎉 Correct, {message.author.mention}! (+{points} points)\n"
                f"The answer was: **{state.answers[0]}**"
            )
            state.question = None  # Clear the question for the next round
            else:
            await message.add_reaction("❌")
            encouraging_responses = [
                f"Not quite, {message.author.mention}, but keep trying!",
                "Close, but not the answer we're looking for!",
                "Good guess, but it's not correct. Try again!",
            ]
            await state.channel.send(random.choice(encouraging_responses))
               
def setup(bot):
    bot.add_cog(Trivia(bot))
