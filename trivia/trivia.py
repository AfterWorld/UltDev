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
        self.remaining_players = []  # List of players still in the game

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
        default_user = {
            "questions_answered": 0,
            "correct_answers": 0,
            "streak": 0,
            "highest_streak": 0,
            "points": 0,  # Total points for rank tracking
        }
        
        self.config.register_user(**default_user)
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
    async def start(self, ctx, genre: str, language: str = "english", mode: Optional[str] = None):
        """
        Start a trivia session in this channel.
    
        Arguments:
        - genre: The genre of trivia questions (e.g., onepiece, anime).
        - language: The language of the trivia questions (e.g., english, spanish).
        - mode (optional): The mode of the trivia game (speed, koth).
        """
        state = self.get_channel_state(ctx.channel)
    
        if state.active:
            await ctx.send("A trivia session is already running in this channel!")
            return
    
        genres = await self.fetch_genres(ctx.guild, language)
        if genre not in genres:
            await ctx.send(f"Invalid genre or language. Available genres for {language}: {', '.join(genres)}")
            return
    
        if mode not in (None, "speed", "koth"):
            await ctx.send("Invalid mode. Available modes: `speed`, `koth`.")
            return
    
        state.reset()
        state.active = True
        state.channel = ctx.channel
        state.mode = mode
        await self.config.guild(ctx.guild).selected_genre.set(genre)
        await self.config.guild(ctx.guild).selected_language.set(language)
        await self.config.guild(ctx.guild).last_active.set(discord.utils.utcnow().timestamp())
    
        games_played = await self.config.guild(ctx.guild).games_played()
        await self.config.guild(ctx.guild).games_played.set(games_played + 1)
    
        log.info(f"Starting trivia for genre '{genre}' in language '{language}', mode: '{mode or 'standard'}'")
        await ctx.send(f"Starting trivia for the **{genre}** genre in **{language}**. Mode: **{mode or 'standard'}**. Get ready!")
        state.task = asyncio.create_task(self.run_trivia(ctx.guild, ctx.channel))


    @trivia.command()
    async def stop(self, ctx):
        """Stop the trivia session in this channel."""
        state = self.get_channel_state(ctx.channel)
    
        if not state.active:
            await ctx.send("No trivia session is currently running in this channel.")
            return
    
        # Ensure session recap is displayed only once
        if state.task and not state.task.done():
            state.task.cancel()
    
        session_scores = await self.config.guild(ctx.guild).scores()
        await self.display_session_recap(ctx.guild, ctx.channel, session_scores)
    
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

    @trivia.command()
    async def stats(self, ctx, user: discord.Member = None):
        """
        Show trivia stats for a user.
        If no user is provided, show stats for the command invoker.
        """
        user = user or ctx.author
        stats = await self.config.user(user).all()
    
        total_questions = stats["questions_answered"]
        correct_answers = stats["correct_answers"]
        accuracy = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        streak = stats["streak"]
        highest_streak = stats["highest_streak"]
        points = stats["points"]
    
        # Calculate rank progress
        next_rank_points = 0
        current_rank = "Unranked"
        for points_required, rank_name in sorted(self.RANKS.items()):
            if points >= points_required:
                current_rank = rank_name
            else:
                next_rank_points = points_required
                break
        progress = f"{points}/{next_rank_points} points" if next_rank_points else "Max Rank Achieved"
    
        embed = discord.Embed(
            title=f"📊 Trivia Stats for {user.display_name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Questions Answered", value=str(total_questions), inline=True)
        embed.add_field(name="Correct Answers", value=str(correct_answers), inline=True)
        embed.add_field(name="Accuracy", value=f"{accuracy:.2f}%", inline=True)
        embed.add_field(name="Current Streak", value=str(streak), inline=True)
        embed.add_field(name="Highest Streak", value=str(highest_streak), inline=True)
        embed.add_field(name="Rank", value=current_rank, inline=True)
        embed.add_field(name="Rank Progress", value=progress, inline=True)
    
        await ctx.send(embed=embed)

    # --- Trivia Logic ---

    async def run_trivia(self, guild, channel):
        """Main trivia loop for a specific channel."""
        log.info(f"Starting trivia loop for guild: {guild.id}, channel: {channel.id}")
    
        state = self.get_channel_state(channel)
    
        # Prevent duplicate trivia tasks
        if state.task and not state.task.done():
            log.warning(f"Trivia loop already running in channel: {channel.id}.")
            return
    
        try:
            genre = await self.config.guild(guild).selected_genre()
            log.info(f"Selected genre: {genre}")
    
            questions = await self.fetch_questions(guild, genre)
            log.info(f"Fetched {len(questions)} questions for genre: {genre}")
    
            if not questions:
                await channel.send(f"No questions found for the genre '{genre}'.")
                state.reset()
                return
        
    async def _handle_question_round(self, channel, guild, state):
        """Handle a single question round."""
        try:
            if not state.question:
                log.warning("No active question found. Skipping round.")
                return
    
            log.info(f"Sending question: {state.question}")
            await channel.send(f"**Trivia Question:** {state.question}\nType your answer below!")
    
            for i in range(30, 0, -5):  # Countdown from 30 seconds
                if not state.active or not state.question:
                    return
    
                await asyncio.sleep(5)
    
                if state.question is None:  # Question was answered or canceled
                    break
    
                if i in (15, 10):  # Send hints at 15 and 10 seconds remaining
                    partial_answer = self.get_partial_answer(state.answers[0], 0.66 if i == 10 else 0.33)
                    log.info(f"Sending hint: {partial_answer}")
                    await channel.send(f"**{i} seconds left!** Hint: {partial_answer}")
    
            # If the question is still active after the time limit
            if state.question and state.active:
                await channel.send(f"Time's up! The correct answer was: {state.answers[0]}")
                log.info("Question timed out.")
    
            # Reset question state for the next round
            state.question = None
            state.answers = []
            state.hints = []
    
            if state.active:
                await asyncio.sleep(1)  # Small delay before the next question
        except Exception as e:
            log.error(f"Error in question round: {e}")

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
            language = await self.config.guild(guild).selected_language() or "english"
            url = f"{await self.config.guild(guild).github_url()}{language}/{genre}.yaml"
            log.info(f"Fetching questions from URL: {url}")
    
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch questions: {response.status}")
                        return []
    
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    questions = yaml.safe_load(content)
                    log.info(f"Successfully fetched {len(questions)} questions for genre '{genre}' in language '{language}'")
                    return questions
        except Exception as e:
            log.error(f"Error fetching questions for genre '{genre}': {e}")
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
        user_stats = await self.config.user(message.author).all()
    
        # Update questions answered
        await self.config.user(message.author).questions_answered.set(user_stats["questions_answered"] + 1)
    
        if message.content.lower().strip() in correct_answers:
            points = 10
    
            # Update correct answers
            await self.config.user(message.author).correct_answers.set(user_stats["correct_answers"] + 1)
    
            # Update streak
            new_streak = user_stats["streak"] + 1
            await self.config.user(message.author).streak.set(new_streak)
            if new_streak > user_stats["highest_streak"]:
                await self.config.user(message.author).highest_streak.set(new_streak)
    
            # Add points
            await self.add_score(message.guild, message.author.id, points)
            await self.config.user(message.author).points.set(user_stats["points"] + points)
    
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
        else:
            # Reset streak for incorrect answers
            await self.config.user(message.author).streak.set(0)


def setup(bot):
    bot.add_cog(Trivia(bot))
