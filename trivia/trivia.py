import discord
from redbot.core import commands, Config
import aiohttp
import yaml
import random
import asyncio
from typing import List, Dict, Optional
import logging
import base64
from contextlib import suppress

log = logging.getLogger("red.trivia")

class TriviaState:
    """Class to manage trivia game state"""
    def __init__(self):
        self.active = False
        self.question: Optional[str] = None
        self.answers: List[str] = []
        self.hints: List[str] = []
        self.channel: Optional[discord.TextChannel] = None
        self.task: Optional[asyncio.Task] = None
        self.used_questions: set = set()

    def reset(self):
        """Reset all state variables"""
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
        self._cleanup_task = None
        self._initialize_cleanup()

    def _initialize_cleanup(self):
        """Initialize the cleanup task for stale games"""
        async def cleanup_stale_games():
            while True:
                try:
                    await self._check_and_cleanup_stale_games()
                except Exception as e:
                    log.error(f"Error in cleanup task: {str(e)}")
                await asyncio.sleep(300)  # Check every 5 minutes

        self._cleanup_task = asyncio.create_task(cleanup_stale_games())

    async def _check_and_cleanup_stale_games(self):
        """Check for and cleanup stale trivia games"""
        if not self.state.active:
            return

        last_active = await self.config.guild(self.state.channel.guild).last_active()
        if last_active and (discord.utils.utcnow().timestamp() - last_active) > 1800:  # 30 minutes
            log.info("Resetting stale trivia state")
            await self.state.channel.send("Trivia game automatically stopped due to inactivity.")
            self.state.reset()

    @commands.group()
    async def trivia(self, ctx):
        """Trivia commands."""
        pass

    @trivia.command()
    async def list(self, ctx):
        """List available trivia genres."""
        try:
            genres = await self.fetch_genres(ctx.guild)
            if not genres:
                return await ctx.send("No trivia genres available.")
            await ctx.send(f"Available trivia genres: {', '.join(genres)}")
        except Exception as e:
            log.error(f"Error listing genres: {str(e)}")
            await ctx.send("An error occurred while fetching genres. Please try again.")

    @trivia.command()
    async def start(self, ctx, genre: str):
        """Start a trivia session with the selected genre."""
        try:
            if self.state.active:
                return await ctx.send("A trivia session is already running!")

            genres = await self.fetch_genres(ctx.guild)
            if not genres:
                return await ctx.send("Failed to fetch trivia genres. Please try again later.")

            log.info(f"Starting trivia with genre: {genre}")
            log.info(f"Available genres: {genres}")

            if genre not in genres:
                return await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")

            # Reset state before starting new game
            self.state.reset()
            
            await self.config.guild(ctx.guild).selected_genre.set(genre)
            await self.config.guild(ctx.guild).last_active.set(discord.utils.utcnow().timestamp())
            
            self.state.active = True
            self.state.channel = ctx.channel
            
            async with self.config.guild(ctx.guild).games_played() as games:
                games += 1
                
            await ctx.send(f"Starting trivia for the **{genre}** genre. Get ready!")
            self.state.task = asyncio.create_task(self.run_trivia(ctx.guild))
            
        except Exception as e:
            log.error(f"Error starting trivia: {str(e)}")
            await ctx.send("An error occurred while starting the trivia game. Please try again.")
            self.state.reset()

    @trivia.command()
    async def stop(self, ctx):
        """Stop the current trivia session."""
        try:
            if self.state.active:
                self.state.active = False
                if self.state.task:
                    self.state.task.cancel()
                await ctx.send("Trivia session stopped.")
                await self.show_scores(ctx.guild)
                await self.config.guild(ctx.guild).scores.set({})
                self.state.reset()
            else:
                await ctx.send("No trivia session is currently running.")
        except Exception as e:
            log.error(f"Error stopping trivia: {str(e)}")
            await ctx.send("An error occurred while stopping the game.")
            self.state.reset()

    @trivia.command()
    async def stats(self, ctx):
        """Show trivia statistics."""
        try:
            guild = ctx.guild
            games_played = await self.config.guild(guild).games_played()
            questions_answered = await self.config.guild(guild).questions_answered()
            total_scores = await self.config.guild(guild).total_scores()
            
            # Calculate top scorer
            top_scorer = None
            if total_scores:
                top_scorer_id = max(total_scores.items(), key=lambda x: x[1])[0]
                top_scorer = await self.bot.fetch_user(int(top_scorer_id))
            
            embed = discord.Embed(
                title="📊 Trivia Statistics",
                color=discord.Color.blue()
            )
            embed.add_field(name="Games Played", value=str(games_played), inline=True)
            embed.add_field(name="Questions Answered", value=str(questions_answered), inline=True)
            if top_scorer:
                embed.add_field(
                    name="Top Scorer",
                    value=f"{top_scorer.name}: {total_scores[str(top_scorer.id)]}",
                    inline=True
                )
            
            await ctx.send(embed=embed)
        except Exception as e:
            log.error(f"Error showing stats: {str(e)}")
            await ctx.send("An error occurred while fetching statistics.")

    @trivia.command()
    async def hint(self, ctx):
        """Get a hint for the current question."""
        try:
            if not self.state.active or not self.state.question:
                return await ctx.send("No trivia question is currently active.")
            
            if not self.state.hints:
                return await ctx.send("No hints available for this question!")
                
            hint = self.state.hints.pop(0) if self.state.hints else "No more hints available!"
            await ctx.send(f"**Hint:** {hint}")
        except Exception as e:
            log.error(f"Error giving hint: {str(e)}")
            await ctx.send("An error occurred while providing the hint.")

    @trivia.command()
    async def scores(self, ctx):
        """Show current session scores."""
        try:
            await self.show_scores(ctx.guild)
        except Exception as e:
            log.error(f"Error showing scores: {str(e)}")
            await ctx.send("An error occurred while showing scores.")

    @trivia.command()
    async def leaderboard(self, ctx):
        """Show the all-time leaderboard."""
        try:
            await self.show_leaderboard(ctx.guild)
        except Exception as e:
            log.error(f"Error showing leaderboard: {str(e)}")
            await ctx.send("An error occurred while showing the leaderboard.")

    async def show_scores(self, guild):
        """Display the current session scores."""
        scores = await self.config.guild(guild).scores()
        if not scores:
            await self.state.channel.send("No scores yet in this session!")
            return

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        embed = discord.Embed(
            title="📝 Current Session Scores",
            color=discord.Color.green()
        )
        
        for idx, (player_id, score) in enumerate(sorted_scores):
            try:
                player = await self.bot.fetch_user(int(player_id))
                player_name = player.name if player else "Unknown Player"
            except:
                player_name = "Unknown Player"
            embed.add_field(
                name=f"#{idx + 1}",
                value=f"{player_name}: {score}",
                inline=False
            )

        await self.state.channel.send(embed=embed)

    async def show_leaderboard(self, guild):
        """Display the all-time leaderboard."""
        total_scores = await self.config.guild(guild).total_scores()
        if not total_scores:
            await self.state.channel.send("No scores recorded yet!")
            return

        sorted_scores = sorted(total_scores.items(), key=lambda x: x[1], reverse=True)
        top_players = sorted_scores[:10]

        embed = discord.Embed(
            title="🏆 All-Time Trivia Leaderboard 🏆",
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

        await self.state.channel.send(embed=embed)

    def get_partial_answer(self, answer: str, reveal_percentage: float) -> str:
        """Returns a partially revealed answer."""
        if not answer:
            return ""
        chars = list(answer)
        reveal_count = int(len(chars) * reveal_percentage)
        hidden_indices = random.sample(range(len(chars)), len(chars) - reveal_count)
        for i in hidden_indices:
            if chars[i].isalnum():
                chars[i] = '_'
        return ''.join(chars)

    async def add_score(self, guild, user_id: int, points: int):
        """Add points to both current and total scores."""
        try:
            async with self.config.guild(guild).scores() as scores:
                if str(user_id) not in scores:
                    scores[str(user_id)] = 0
                scores[str(user_id)] += points

            async with self.config.guild(guild).total_scores() as total_scores:
                if str(user_id) not in total_scores:
                    total_scores[str(user_id)] = 0
                total_scores[str(user_id)] += points
        except Exception as e:
            log.error(f"Error adding score: {str(e)}")
            raise

    @commands.Cog.listener()
    async def on_message(self, message):
        """Check messages for trivia answers."""
        if (not self.state.active or 
            not self.state.question or 
            message.author.bot or 
            message.channel != self.state.channel):
            return

        try:
            answer = message.content.lower().strip()
            correct_answers = [ans.lower().strip() for ans in self.state.answers]

            if answer in correct_answers:
                points = 10
                await self.add_score(message.guild, message.author.id, points)
                
                async with self.config.guild(message.guild).questions_answered() as questions:
                    questions += 1
                
                await message.add_reaction("✅")
                await self.state.channel.send(
                    f"🎉 Correct, {message.author.mention}! (+{points} points)\n"
                    f"The answer was: {self.state.answers[0]}"
                )
                
                self.state.question = None
                self.state.answers = []
                self.state.hints = []
        except Exception as e:
            log.error(f"Error processing answer: {str(e)}")

    async def run_trivia(self, guild):
        """Main trivia loop with improved error handling."""
        try:
            genre = await self.config.guild(guild).selected_genre()
            questions = await self.fetch_questions(guild, genre)

            if not questions:
                await self.state.channel.send(f"No questions found for the genre '{genre}'. Please check the file.")
                self.state.reset()
                return

            while self.state.active:
                try:
                    await self.config.guild(guild).last_active.set(discord.utils.utcnow().timestamp())
                    
                    available_questions = [q for q in questions if q["question"] not in self.state.used_questions]
                    if not available_questions:
                        await self.state.channel.send("All questions have been used! Reshuffling question pool...")
                        self.state.used_questions.clear()
                        available_questions = questions

                    question_data = random.choice(available_questions)
                    self.state.question = question_data["question"]
                    self.state.answers = question_data["answers"]
                    self.state.hints = question_data.get("hints", []).copy()
                    self.state.used_questions.add(self.state.question)

                    await self._handle_question_round(guild)
                    
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.error(f"Error in trivia round: {str(e)}")
                    await self.state.channel.send("An error occurred during the trivia round. Starting next question...")
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            log.info("Trivia game cancelled")
            raise
        except Exception as e:
            log.error(f"Fatal error in trivia loop: {str(e)}")
            await self.state.channel.send("A fatal error occurred running the trivia game.")
        finally:
            self.state.reset()

    async def _handle_question_round(self, guild):
        """Handle a single question round"""
        await self.state.channel.send(
            f"**Trivia Question:**\n{self.state.question}\n"
            f"*Use `!trivia hint` for a hint!*")

        for i in range(30, 0, -5):
            if not self.state.active:
                return
            await asyncio.sleep(5)
            if not self.state.question:
                break

            if i in (15, 10):
                partial_answer = self.get_partial_answer(
                    self.state.answers[0], 
                    0.66 if i == 10 else 0.33
                )
                await self.state.channel.send(
                    f"**{i} seconds left!** The answer looks like: {partial_answer}"
                )

        if self.state.question and self.state.active:
            await self.state.channel.send(
                f"Time's up! The correct answer was: {self.state.answers[0]}"
            )
            self.state.question = None
            self.state.answers = []
            self.state.hints = []

        await asyncio.sleep(5)

    async def fetch_genres(self, guild) -> List[str]:
        """Fetch available genres."""
        try:
            github_url = await self.config.guild(guild).github_url()
            async with aiohttp.ClientSession() as session:
                async with session.get(github_url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch genres: {response.status} - {response.reason}")
                        return []
                    data = await response.json()
                    genres = [item["name"].replace(".yaml", "") 
                             for item in data 
                             if item["name"].endswith(".yaml")]
                    log.info(f"Successfully fetched genres: {genres}")
                    return genres
        except Exception as e:
            log.error(f"Error while fetching genres: {str(e)}")
            return []

    async def fetch_questions(self, guild, genre: str) -> List[dict]:
        """Fetch questions for the selected genre."""
        try:
            github_url = f"{await self.config.guild(guild).github_url()}{genre}.yaml"
            async with aiohttp.ClientSession() as session:
                async with session.get(github_url) as response:
                    if response.status != 200:
                        log.error(f"Failed to fetch questions for genre '{genre}': {response.status} - {response.reason}")
                        return []

                    data = await response.json()
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    questions = yaml.safe_load(content)
                    
                    # Validate question format
                    for question in questions:
                        if not isinstance(question, dict) or "question" not in question or "answers" not in question:
                            log.error(f"Invalid question format in {genre}.yaml")
                            return []
                        if not isinstance(question["answers"], list) or not question["answers"]:
                            log.error(f"Invalid answers format in {genre}.yaml")
                            return []
                    
                    return questions
        except Exception as e:
            log.error(f"Error while fetching questions for genre '{genre}': {str(e)}")
            return []

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self.state.reset()

def setup(bot):
    """Add the cog to the bot."""
    try:
        bot.add_cog(Trivia(bot))
        log.info("Trivia cog successfully loaded")
    except Exception as e:
        log.error(f"Error loading Trivia cog: {str(e)}")
