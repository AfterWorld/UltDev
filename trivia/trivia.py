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
            # Trigger session recap after the trivia ends, before resetting the state
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
            await channel.send(f"Time's up! The correct answer was: {state.answers[0]}")
            state.question = None
            state.answers = []
            state.hints = []

        await asyncio.sleep(5)

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
    
        # Sort scores in descending order
        sorted_scores = sorted(session_scores.items(), key=lambda x: x[1], reverse=True)
    
        embed = discord.Embed(
            title="📊 Trivia Session Recap",
            color=discord.Color.blue(),
            description=f"Great job, everyone! Here's how the session went:"
        )
    
        # Add top players
        for idx, (user_id, score) in enumerate(sorted_scores[:5]):  # Show top 5 players
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
    
        # Add total questions answered
        questions_answered = await self.config.guild(guild).questions_answered()
        embed.add_field(name="Total Questions Answered", value=str(questions_answered), inline=False)
    
        # Congratulate the top scorer
        top_user_id, top_score = sorted_scores[0]
        try:
            top_user = await self.bot.fetch_user(int(top_user_id))
            top_user_name = top_user.name if top_user else "Unknown Player"
        except:
            top_user_name = "Unknown Player"
        embed.set_footer(text=f"🏆 Top Scorer: {top_user_name} with {top_score} points!")
    
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
