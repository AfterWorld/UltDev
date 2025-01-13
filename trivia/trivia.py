import discord
from redbot.core import commands, Config
import aiohttp
import yaml
import random
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging
import base64
from typing import List, Optional

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

    # Define ranks and their point thresholds
    RANKS = {
        10: "Novice",
        50: "Trivia Enthusiast",
        100: "Trivia Master",
        250: "Trivia Legend",
        500: "Trivia Champion",
    }
    BADGES = {
        "Novice": "🔰",
        "Trivia Enthusiast": "✨",
        "Trivia Master": "🌟",
        "Trivia Legend": "🏅",
        "Trivia Champion": "🏆",
    }
    GENRE_DESCRIPTIONS = {
        "onepiece": "Questions about the One Piece anime and manga universe.",
        "anime": "Test your knowledge about anime.",
        "music": "Guess music, or lyrics",
        "history": "How well do you know world history?",
        "general": "Trivia about anything",
    }

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543212, force_registration=True)
        default_guild = {
            "github_url": "https://api.github.com/repos/AfterWorld/UltDev/contents/trivia/questions/",
            "selected_genre": None,
            "scores": {},  # Current session scores
            "total_scores": {},  # All-time scores
            "daily_scores": {},  # Daily leaderboard
            "weekly_scores": {},  # Weekly leaderboard
            "games_played": 0,
            "questions_answered": 0,
            "last_active": None,
        }
        self.config.register_guild(**default_guild)
        self.channel_states = {}

        # Initialize the scheduler for resets
        self.scheduler = AsyncIOScheduler()
        self.scheduler.add_job(self.reset_daily_scores, "cron", hour=0, minute=0)
        self.scheduler.add_job(self.reset_weekly_scores, "cron", day_of_week="mon", hour=0, minute=0)
        self.scheduler.start()

    def get_channel_state(self, channel: discord.TextChannel):
        """Get or initialize the trivia state for a specific channel."""
        if channel.id not in self.channel_states:
            self.channel_states[channel.id] = TriviaState()
        return self.channel_states[channel.id]

    # --- Score Reset Methods ---

    async def reset_daily_scores(self):
        """Reset daily scores for all guilds."""
        all_guilds = await self.config.all_guilds()
        for guild_id in all_guilds:
            await self.config.guild_from_id(guild_id).daily_scores.set({})
        log.info("Daily scores have been reset.")

    async def reset_weekly_scores(self):
        """Reset weekly scores for all guilds."""
        all_guilds = await self.config.all_guilds()
        for guild_id in all_guilds:
            await self.config.guild_from_id(guild_id).weekly_scores.set({})
        log.info("Weekly scores have been reset.")

    async def display_session_recap(self, guild, channel, session_scores):
        """Display a recap of the trivia session."""
        if not session_scores:
            await channel.send("No one scored any points this session. Better luck next time!")
            return

        sorted_scores = sorted(session_scores.items(), key=lambda x: x[1], reverse=True)

        embed = discord.Embed(
            title="📊 Trivia Session Recap",
            color=discord.Color.blue(),
            description=f"Great job, everyone! Here's how the session went:"
        )

        for idx, (user_id, score) in enumerate(sorted_scores[:5]):
            try:
                user = await self.bot.fetch_user(int(user_id))
                player_name = user.name if user else "Unknown Player"
            except:
                player_name = "Unknown Player"
            position = ["🥇", "🥈", "🥉"][idx] if idx < 3 else f"#{idx + 1}"
            embed.add_field(
                name=f"{position}: {player_name}",
                value=f"Points: {score}",
                inline=False
            )

        questions_answered = await self.config.guild(guild).questions_answered()
        embed.add_field(name="Total Questions Answered", value=str(questions_answered), inline=False)

        top_user_id, top_score = sorted_scores[0]
        try:
            top_user = await self.bot.fetch_user(int(top_user_id))
            top_user_name = top_user.name if top_user else "Unknown Player"
        except:
            top_user_name = "Unknown Player"
        embed.set_footer(text=f"🏆 Top Scorer: {top_user_name} with {top_score} points!")

        await channel.send(embed=embed)

    def get_partial_answer(self, answer, reveal_ratio):
        """
        Generate a partial answer hint by revealing a portion of the characters.
        Example: "elephant" -> "e____a__" (33% revealed)
        """
        revealed_chars = int(len(answer) * reveal_ratio)
        hint = ''.join(c if idx < revealed_chars else '_' for idx, c in enumerate(answer))
        return hint

    # --- Trivia Commands ---

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
    
        # Display session recap
        session_scores = await self.config.guild(ctx.guild).scores()
        await self.display_session_recap(ctx.guild, ctx.channel, session_scores)
    
        # Reset state and scores
        state.reset()
        await self.config.guild(ctx.guild).scores.set({})
        await ctx.send("Trivia session stopped.")

    @trivia.command()
    async def leaderboard(self, ctx, scope: str = "all-time"):
        """
        Show the trivia leaderboard.
        Scope can be:
        - "all-time" (default)
        - "daily"
        - "weekly"
        """
        scores = {}
        if scope == "daily":
            scores = await self.config.guild(ctx.guild).daily_scores()
        elif scope == "weekly":
            scores = await self.config.guild(ctx.guild).weekly_scores()
        else:
            scores = await self.config.guild(ctx.guild).total_scores()

        if not scores:
            await ctx.send(f"No scores recorded yet for the {scope} leaderboard!")
            return

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_players = sorted_scores[:10]

        embed = discord.Embed(
            title=f"🏆 {scope.title()} Trivia Leaderboard 🏆",
            description="Top 10 Players",
            color=discord.Color.gold()
        )

        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        for idx, (player_id, score) in enumerate(top_players):
            medal = medals.get(idx, "")
            try:
                player = await self.bot.fetch_user(int(player_id))
                player_name = player.name if player else "Unknown Player"
            except:
                player_name = "Unknown Player"
            embed.add_field(
                name=f"{medal} #{idx + 1}",
                value=f"{player_name}: {score} points",
                inline=False
            )

        await ctx.send(embed=embed)

    @trivia.command()
    async def categories(self, ctx):
        """List all available trivia categories with descriptions."""
        try:
            # Fetch available genres
            genres = await self.fetch_genres(ctx.guild)
            if not genres:
                await ctx.send("No trivia categories are currently available.")
                return
    
            # Create an embed for the category list
            embed = discord.Embed(
                title="📚 Trivia Categories",
                description="Choose a category to play trivia!",
                color=discord.Color.green(),
            )
    
            # Add genres with descriptions
            for genre in genres:
                description = self.GENRE_DESCRIPTIONS.get(genre, "No description available.")
                embed.add_field(name=genre.title(), value=description, inline=False)
    
            await ctx.send(embed=embed)
    
        except Exception as e:
            log.error(f"Error fetching categories: {e}")
            await ctx.send("An error occurred while fetching categories.")

    @trivia.command()
    async def preview(self, ctx, genre: str):
        """Preview a few questions from a specific category."""
        try:
            genres = await self.fetch_genres(ctx.guild)
            if genre not in genres:
                await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")
                return
    
            questions = await self.fetch_questions(ctx.guild, genre)
            if not questions:
                await ctx.send(f"No questions available for the genre '{genre}'.")
                return
    
            # Select up to 3 random questions to preview
            preview_questions = random.sample(questions, min(3, len(questions)))
    
            embed = discord.Embed(
                title=f"🔍 Preview of {genre.title()} Questions",
                description="Here are a few sample questions:",
                color=discord.Color.blue(),
            )
            for idx, question in enumerate(preview_questions, start=1):
                embed.add_field(name=f"Question {idx}", value=question["question"], inline=False)
    
            await ctx.send(embed=embed)
    
        except Exception as e:
            log.error(f"Error previewing questions: {e}")
            await ctx.send("An error occurred while previewing questions.")

    # --- Trivia Logic ---

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
            await self.config.guild(guild).scores.set({})
        state.reset()

    async def _handle_question_round(self, channel, guild, state):
        """Handle a single question round with immediate progression."""
        await channel.send(f"**Trivia Question:** {state.question}\nType your answer below!")

        correct = False
        for i in range(30, 0, -5):
            if not state.active:
                return
            await asyncio.sleep(5)
            if correct:  # If someone answered correctly, skip the rest of the countdown.
                break

            if i in (15, 10):
                partial_answer = self.get_partial_answer(
                    state.answers[0],
                    0.66 if i == 10 else 0.33
                )
                await channel.send(f"**{i} seconds left!** Hint: {partial_answer}")

        if not correct and state.question and state.active:
            await channel.send(f"Time's up! The correct answer was: {state.answers[0]}")
            state.question = None
            state.answers = []
            state.hints = []

        if state.active:
            await asyncio.sleep(1)
            state.task = asyncio.create_task(self.run_trivia(guild, channel))

    

    # --- Fetching and Utility Methods ---

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

    async def add_score(self, guild, user_id: int, points: int, scope: str = "session"):
        """Add points to the specified score scope."""
        try:
            async with self.config.guild(guild).scores() as scores:
                scores[str(user_id)] = scores.get(str(user_id), 0) + points

            if scope == "daily":
                async with self.config.guild(guild).daily_scores() as daily_scores:
                    daily_scores[str(user_id)] = daily_scores.get(str(user_id), 0) + points
            elif scope == "weekly":
                async with self.config.guild(guild).weekly_scores() as weekly_scores:
                    weekly_scores[str(user_id)] = weekly_scores.get(str(user_id), 0) + points

            async with self.config.guild(guild).total_scores() as total_scores:
                if str(user_id) not in total_scores:
                    total_scores[str(user_id)] = 0
                total_scores[str(user_id)] += points
        except Exception as e:
            log.error(f"Error adding score: {e}")
            raise

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
            await self.add_score(message.guild, message.author.id, points, scope="daily")
            await message.add_reaction("✅")
            await state.channel.send(
                f"🎉 Correct, {message.author.mention}! (+{points} points)\n"
                f"The answer was: {state.answers[0]}"
            )
            state.question = None  # Clear the question for the next round
            state.answers = []  # Reset answers to avoid repetition

            # Trigger the next question immediately
            if state.active:
                state.task = asyncio.create_task(self.run_trivia(message.guild, state.channel))


def setup(bot):
    bot.add_cog(Trivia(bot))
