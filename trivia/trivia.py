import discord
from redbot.core import commands, Config
import aiohttp
import yaml
import random
import asyncio
from typing import List, Dict
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
            "scores": {},
            "total_scores": {},
            "games_played": 0,
            "questions_answered": 0
        }
        self.config.register_guild(**default_guild)
        self.trivia_active = False
        self.current_question = None
        self.current_answers = []
        self.current_hints = []
        self.trivia_channel = None
        self.task = None
        self.used_questions = set()

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
        if self.trivia_active:
            return await ctx.send("A trivia session is already running!")

        genres = await self.fetch_genres(ctx.guild)
        if genre not in genres:
            return await ctx.send(f"Invalid genre. Available genres: {', '.join(genres)}")

        await self.config.guild(ctx.guild).selected_genre.set(genre)
        self.trivia_active = True
        self.trivia_channel = ctx.channel
        self.used_questions.clear()
        
        # Increment games played counter
        async with self.config.guild(ctx.guild).games_played() as games:
            games += 1
            
        await ctx.send(f"Starting trivia for the **{genre}** genre. Get ready!")
        self.task = asyncio.create_task(self.run_trivia(ctx.guild))

    @trivia.command()
    async def stop(self, ctx):
        """Stop the current trivia session."""
        if self.trivia_active:
            self.trivia_active = False
            if self.task:
                self.task.cancel()
            await ctx.send("Trivia session stopped.")
            await self.show_scores(ctx.guild)
            await self.config.guild(ctx.guild).scores.set({})
        else:
            await ctx.send("No trivia session is currently running.")

    @trivia.command()
    async def stats(self, ctx):
        """Show trivia statistics."""
        guild = ctx.guild
        games_played = await self.config.guild(guild).games_played()
        questions_answered = await self.config.guild(guild).questions_answered()
        total_scores = await self.config.guild(guild).total_scores()
        
        # Calculate top scorer
        top_scorer_id = max(total_scores.items(), key=lambda x: x[1])[0] if total_scores else None
        top_scorer = await self.bot.fetch_user(int(top_scorer_id)) if top_scorer_id else None
        
        embed = discord.Embed(
            title="📊 Trivia Statistics",
            color=discord.Color.blue()
        )
        embed.add_field(name="Games Played", value=str(games_played), inline=True)
        embed.add_field(name="Questions Answered", value=str(questions_answered), inline=True)
        if top_scorer:
            embed.add_field(name="Top Scorer", value=f"{top_scorer.name}: {total_scores[top_scorer_id]}", inline=True)
        
        await ctx.send(embed=embed)

    @trivia.command()
    async def hint(self, ctx):
        """Get a hint for the current question."""
        if not self.trivia_active or not self.current_question:
            return await ctx.send("No trivia question is currently active.")
        
        if not self.current_hints:
            return await ctx.send("No hints available for this question!")
            
        hint = self.current_hints.pop(0) if self.current_hints else "No more hints available!"
        await ctx.send(f"**Hint:** {hint}")

    @trivia.command()
    async def scores(self, ctx):
        """Show current session scores."""
        await self.show_scores(ctx.guild)

    @trivia.command()
    async def leaderboard(self, ctx):
        """Show the all-time leaderboard."""
        await self.show_leaderboard(ctx.guild)

    async def show_scores(self, guild):
        """Display the current session scores."""
        scores = await self.config.guild(guild).scores()
        if not scores:
            await self.trivia_channel.send("No scores yet in this session!")
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

        await self.trivia_channel.send(embed=embed)

    async def show_leaderboard(self, guild):
        """Display the all-time leaderboard."""
        total_scores = await self.config.guild(guild).total_scores()
        if not total_scores:
            await self.trivia_channel.send("No scores recorded yet!")
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

        await self.trivia_channel.send(embed=embed)

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
        async with self.config.guild(guild).scores() as scores:
            if str(user_id) not in scores:
                scores[str(user_id)] = 0
            scores[str(user_id)] += points

        async with self.config.guild(guild).total_scores() as total_scores:
            if str(user_id) not in total_scores:
                total_scores[str(user_id)] = 0
            total_scores[str(user_id)] += points

    @commands.Cog.listener()
    async def on_message(self, message):
        """Check messages for trivia answers."""
        if (not self.trivia_active or 
            not self.current_question or 
            message.author.bot or 
            message.channel != self.trivia_channel):
            return

        answer = message.content.lower().strip()
        correct_answers = [ans.lower().strip() for ans in self.current_answers]

        if answer in correct_answers:
            points = 10
            await self.add_score(message.guild, message.author.id, points)
            
            # Increment questions answered counter
            async with self.config.guild(message.guild).questions_answered() as questions:
                questions += 1
            
            await message.add_reaction("✅")
            await self.trivia_channel.send(
                f"🎉 Correct, {message.author.mention}! (+{points} points)\nThe answer was: {self.current_answers[0]}"
            )
            
            self.current_question = None
            self.current_answers = []
            self.current_hints = []

    async def run_trivia(self, guild):
        """Main trivia loop."""
        try:
            channel = self.trivia_channel
            genre = await self.config.guild(guild).selected_genre()
            questions = await self.fetch_questions(guild, genre)

            if not questions:
                await channel.send(f"No questions found for the genre '{genre}'. Please check the file.")
                self.trivia_active = False
                return

            while self.trivia_active:
                available_questions = [q for q in questions if q["question"] not in self.used_questions]
                
                if not available_questions:
                    await channel.send("All questions have been used! Reshuffling question pool...")
                    self.used_questions.clear()
                    available_questions = questions

                question_data = random.choice(available_questions)
                self.current_question = question_data["question"]
                self.current_answers = question_data["answers"]
                self.current_hints = question_data.get("hints", []).copy()
                self.used_questions.add(self.current_question)
                main_answer = self.current_answers[0]

                await channel.send(
                    f"**Trivia Question:**\n{self.current_question}\n"
                    f"*Use `!trivia hint` for a hint!*"
                )
                
                for i in range(30, 0, -5):
                    if not self.trivia_active:
                        return
                    await asyncio.sleep(5)
                    if not self.current_question:
                        break

                    if i == 15:
                        partial_answer = self.get_partial_answer(main_answer, 0.33)
                        await channel.send(f"**15 seconds left!** The answer looks like: {partial_answer}")
                    elif i == 10:
                        partial_answer = self.get_partial_answer(main_answer, 0.66)
                        await channel.send(f"**10 seconds left!** The answer looks like: {partial_answer}")

                if self.current_question and self.trivia_active:
                    await channel.send(f"Time's up! The correct answer was: {main_answer}")
                    self.current_question = None
                    self.current_answers = []
                    self.current_hints = []

                await asyncio.sleep(5)

        except asyncio.CancelledError:
            self.current_question = None
            self.current_answers = []
            self.current_hints = []
            self.trivia_active = False
            return
        except Exception as e:
            log.error(f"Error in trivia loop: {str(e)}")
            await channel.send("An error occurred running the trivia game.")
            self.trivia_active = False

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
