import discord
from redbot.core import commands, Config
import aiohttp
import yaml
import random
import asyncio
from typing import List, Optional
import logging
import base64
from datetime import datetime, timedelta

log = logging.getLogger("red.trivia")


class TriviaState:
    """Class to manage trivia game state."""

    def __init__(self, channel=None):
        self.active = False
        self.channel = channel  # Ensure channel is set during initialization
        self.question: Optional[str] = None
        self.answers: List[str] = []
        self.hints: List[str] = []
        self.task: Optional[asyncio.Task] = None
        self.used_questions: set = set()

    def reset(self, clear_channel=False):
        """Reset all state variables."""
        self.active = False
        self.question = None
        self.answers = []
        self.hints = []
        if clear_channel:
            self.channel = None  # Only reset the channel if explicitly requested
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = None
        self.used_questions.clear()


class Trivia(commands.Cog):
    """A trivia game with YAML-based questions."""

    # Difficulty points configuration
    difficulty_points = {"easy": 5, "medium": 10, "hard": 20}

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
        self.streaks = {}  # Dictionary to track user streaks
        default_guild = {
            "github_url": "https://api.github.com/repos/AfterWorld/UltDev/contents/trivia/questions/",
            "selected_genre": None,
            "selected_difficulty": None,  # Add this field for difficulty
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
    async def start(self, ctx, genre: str, difficulty: Optional[str] = None):
        """Start a trivia session in this channel. Players can optionally choose difficulty."""
        state = self.get_channel_state(ctx.channel)
    
        if state.active:
            await ctx.send("A trivia session is already running in this channel!")
            return
    
        genres = await self.fetch_genres(ctx.guild)
        if genre not in genres:
            await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")
            return
    
        if difficulty and difficulty not in ["easy", "medium", "hard"]:
            await ctx.send("Invalid difficulty. Choose from: easy, medium, hard.")
            return
    
        state.reset()  # Reset the trivia state
        state.active = True
        state.channel = ctx.channel  # Set the channel at the start
    
        await self.config.guild(ctx.guild).selected_genre.set(genre)
        await self.config.guild(ctx.guild).selected_difficulty.set(difficulty)
        await self.config.guild(ctx.guild).last_active.set(discord.utils.utcnow().timestamp())
    
        difficulty_message = f" with **{difficulty}** difficulty" if difficulty else " with dynamic difficulty"
        await ctx.send(f"Starting trivia for the **{genre}** genre{difficulty_message}. Get ready!")
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
    async def leaderboard(self, ctx):
        """Show the all-time trivia leaderboard."""
        try:
            total_scores = await self.config.guild(ctx.guild).total_scores()
            if not total_scores:
                await ctx.send("No scores recorded yet!")
                return
    
            # Sort scores in descending order and get the top 10 players
            sorted_scores = sorted(total_scores.items(), key=lambda x: x[1], reverse=True)
            top_players = sorted_scores[:10]
    
            embed = discord.Embed(
                title="🏆 All-Time Trivia Leaderboard 🏆",
                description="Top 10 Players",
                color=discord.Color.gold()
            )
    
            # Add medals for the top 3 positions
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
    
        except Exception as e:
            log.error(f"Error showing leaderboard: {e}")
            await ctx.send("An error occurred while showing the leaderboard.")

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
    async def daily(self, ctx):
        """Participate in the daily trivia challenge."""
        try:
            guild = ctx.guild
            user_id = str(ctx.author.id)
            daily_scores = await self.config.guild(guild).get_raw("daily_scores", default={})
    
            # Check if the user has already participated today
            today = datetime.utcnow().date()
            last_attempt = daily_scores.get(user_id, {}).get("date")
            if last_attempt and datetime.strptime(last_attempt, "%Y-%m-%d").date() == today:
                await ctx.send("You've already participated in today's daily challenge! Come back tomorrow.")
                return
    
            # Fetch a random category
            genres = await self.fetch_genres(guild)
            if not genres:
                await ctx.send("No trivia categories are available for the daily challenge.")
                return
            random_genre = random.choice(genres)
    
            # Fetch questions for the selected category
            questions = await self.fetch_questions(guild, random_genre)
            if not questions:
                await ctx.send(f"No questions found for today's challenge in the genre '{random_genre}'.")
                return
    
            # Select a random question
            question_data = random.choice(questions)
            question = question_data["question"]
            answers = question_data["answers"]
    
            # Send the question
            await ctx.send(
                f"🌟 **Daily Trivia Challenge** 🌟\n"
                f"Category: **{random_genre.title()}**\n\n"
                f"**Question:** {question}\n"
                f"Type your answer below!"
            )
    
            def check(m):
                return (
                    m.author == ctx.author
                    and m.channel == ctx.channel
                    and m.content.lower().strip() in [ans.lower().strip() for ans in answers]
                )
    
            try:
                # Wait for the user's response
                response = await self.bot.wait_for("message", check=check, timeout=30)
                await ctx.send(f"🎉 Correct, {ctx.author.mention}! You've earned **20 bonus points!**")
    
                # Add bonus points for the daily challenge
                async with self.config.guild(guild).get_raw("daily_scores", default={}) as scores:
                    scores[user_id] = {"date": today.strftime("%Y-%m-%d"), "points": 20}
    
                await self.add_score(guild, ctx.author.id, 20)
    
            except asyncio.TimeoutError:
                await ctx.send(f"⏰ Time's up! The correct answer was: **{answers[0]}**.")
    
        except Exception as e:
            log.error(f"Error in daily trivia: {e}")
            await ctx.send("An error occurred while starting the daily challenge. Please try again.")

    @trivia.command()
    @commands.admin()
    async def weeklyreset(self, ctx):
        """Reset the weekly trivia leaderboard."""
        try:
            guild = ctx.guild
            total_scores = await self.config.guild(guild).total_scores()
    
            if not total_scores:
                await ctx.send("No scores recorded this week to reset.")
                return
    
            # Determine the weekly champion
            sorted_scores = sorted(total_scores.items(), key=lambda x: x[1], reverse=True)
            top_user_id, top_score = sorted_scores[0]
            top_user = await self.bot.fetch_user(int(top_user_id))
    
            # Announce the champion
            await ctx.send(
                f"🏆 **Weekly Trivia Champion** 🏆\n"
                f"Congratulations to **{top_user.name}** with **{top_score} points!**\n"
                f"The leaderboard has been reset. Good luck next week!"
            )
    
            # Reset total scores
            await self.config.guild(guild).total_scores.set({})
        except Exception as e:
            log.error(f"Error in weekly reset: {e}")
            await ctx.send("An error occurred while resetting the leaderboard.")

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
                if not state.channel:
                    log.error("No channel set for the trivia session. Aborting.")
                    state.reset()
                    return
    
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
    
        except Exception as e:
            log.error(f"Error in trivia loop: {e}")
            state.reset()
        
    async def _handle_question_round(self, channel, guild, state):
        """Handle a single question round."""
        if not state.channel:
            log.error("State channel is None during a question round.")
            return
    
        if not state.question or not state.answers:
            await state.channel.send("Error: Invalid question or answers. Skipping...")
            return
    
        await state.channel.send(f"**Trivia Question:** {state.question}\nType your answer below!")
    
        def check_answer(message):
            return (
                message.channel == state.channel
                and message.author != self.bot.user
                and message.content.lower().strip() in [ans.lower().strip() for ans in state.answers]
            )
    
        try:
            response = await self.bot.wait_for("message", check=check_answer, timeout=30)
            points = 10  # Adjust as needed
            await self.add_score(guild, response.author.id, points)
            await response.add_reaction("✅")
            await state.channel.send(
                f"🎉 Correct, {response.author.mention}! (+{points} points)\n"
                f"The answer was: **{state.answers[0]}**"
            )
        except asyncio.TimeoutError:
            await state.channel.send(f"⏰ Time's up! The answer was: **{state.answers[0]}**.")
    
        # Reset state for the next question
        state.question = None
        state.answers = []
    
        def get_partial_answer(self, answer: str, reveal_percentage: float) -> str:
            """
            Returns a partially revealed answer string.
            
            :param answer: The correct answer to the question.
            :param reveal_percentage: The percentage of characters to reveal (0.0 to 1.0).
            :return: A string with some characters replaced by underscores.
            """
            if not answer:
                return ""
        
            # Convert the answer into a list of characters
            chars = list(answer)
            reveal_count = int(len(chars) * reveal_percentage)
        
            # Randomly choose indices to hide
            hidden_indices = random.sample(range(len(chars)), len(chars) - reveal_count)
        
            for i in hidden_indices:
                if chars[i].isalnum():  # Hide only alphanumeric characters
                    chars[i] = "_"
        
            return ''.join(chars)


    async def add_score(self, guild, user_id: int, points: int):
        """Add points to both current and total scores, with gamification."""
        try:
            async with self.config.guild(guild).scores() as scores:
                scores[str(user_id)] = scores.get(str(user_id), 0) + points

            async with self.config.guild(guild).total_scores() as total_scores:
                if str(user_id) not in total_scores:
                    total_scores[str(user_id)] = 0
                total_scores[str(user_id)] += points
                total_points = total_scores[str(user_id)]

            await self.check_achievements(guild, user_id, total_points)
        except Exception as e:
            log.error(f"Error adding score: {e}")
            raise

    async def check_achievements(self, guild, user_id: int, total_points: int):
        """Check if a user has achieved a new rank or milestone."""
        user = await self.bot.fetch_user(user_id)
        if not user:
            return

        rank = None
        for points, rank_name in sorted(self.RANKS.items(), reverse=True):
            if total_points >= points:
                rank = rank_name
                break

        if rank:
            badge = self.BADGES.get(rank, "")
            await self.channel_states[guild.id].channel.send(
                f"🎉 {user.mention} has achieved the rank of **{rank}**! {badge}\n"
                f"Total Points: {total_points}"
            )

        milestones = [10, 50, 100, 250, 500]
        if total_points in milestones:
            await self.channel_states[guild.id].channel.send(
                f"🏆 {user.mention} reached **{total_points} points**! Keep it up!"
            )

    async def display_session_recap(self, guild, channel, session_scores):
        """Display a recap of the trivia session."""
        if not session_scores:
            await channel.send("No one scored any points this session. Better luck next time!")
            return
    
        sorted_scores = sorted(session_scores.items(), key=lambda x: x[1], reverse=True)
        embed = discord.Embed(
            title="📊 Trivia Session Recap",
            color=discord.Color.blue(),
            description="Great job, everyone! Here's how the session went:"
        )
    
        for idx, (user_id, score) in enumerate(sorted_scores[:5]):  # Top 5 players
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
    
        # Fun ending message
        ending_messages = [
            "Thanks for playing! 🎉",
            "Want to improve your score? Play another round!",
            "Invite your friends to join next time!",
        ]
        embed.set_footer(text=random.choice(ending_messages))
    
        await channel.send(embed=embed)

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
        """Fetch questions for the selected genre and optional difficulty."""
        try:
            url = f"{await self.config.guild(guild).github_url()}{genre}.yaml"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    questions = yaml.safe_load(content)
    
                    # Get the selected difficulty
                    selected_difficulty = await self.config.guild(guild).selected_difficulty()
    
                    # If difficulty is specified, filter questions; otherwise, return all
                    if selected_difficulty:
                        questions = [q for q in questions if q.get("difficulty") == selected_difficulty]
    
                    return questions
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
    
        if not state.channel:
            log.error("State.channel is None during message processing.")
            return
    
        correct_answers = [ans.lower().strip() for ans in state.answers]
        user_answer = message.content.lower().strip()
    
        if user_answer in correct_answers:
            points = 10  # You can calculate points dynamically based on difficulty
            await self.add_score(message.guild, message.author.id, points)
            await message.add_reaction("✅")
            await state.channel.send(
                f"🎉 Correct, {message.author.mention}! (+{points} points)\n"
                f"The answer was: **{state.answers[0]}**"
            )
    
            state.question = None
            state.answers = []
            state.hints = []
            await asyncio.sleep(1)
            await self._handle_question_round(state.channel, message.guild, state)
        else:
            if not state.channel:
                log.error("State.channel is None when sending encouragement.")
                return
    
            encouraging_responses = [
                f"Not quite, {message.author.mention}, but keep trying!",
                "Close, but not the answer we're looking for!",
                "Good guess, but it's not correct. Try again!",
            ]
            await state.channel.send(random.choice(encouraging_responses))
            
def setup(bot):
    bot.add_cog(Trivia(bot))
