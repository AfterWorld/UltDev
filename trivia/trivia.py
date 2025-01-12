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
            "scores": {}
        }
        self.config.register_guild(**default_guild)
        self.trivia_active = False
        self.current_question = None
        self.current_answers = []
        self.current_hints = []
        self.trivia_channel = None
        self.task = None  # Store the trivia task

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
        await ctx.send(f"Starting trivia for the **{genre}** genre. Get ready!")
        
        # Start the trivia task
        self.task = asyncio.create_task(self.run_trivia(ctx.guild))

    @trivia.command()
    async def stop(self, ctx):
        """Stop the current trivia session."""
        if self.trivia_active:
            self.trivia_active = False
            if self.task:
                self.task.cancel()
            await ctx.send("Trivia session stopped.")
            # Show final scores
            await self.show_scores(ctx.guild)
            # Reset scores
            await self.config.guild(ctx.guild).scores.set({})
        else:
            await ctx.send("No trivia session is currently running.")

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
        """Show current scores."""
        await self.show_scores(ctx.guild)

    async def show_scores(self, guild):
        """Display the current scores."""
        scores = await self.config.guild(guild).scores()
        if not scores:
            await self.trivia_channel.send("No scores yet!")
            return

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        score_list = "\n".join([f"{idx+1}. <@{player_id}>: {score}" 
                               for idx, (player_id, score) in enumerate(sorted_scores)])
        embed = discord.Embed(title="Trivia Scores", description=score_list, color=discord.Color.blue())
        await self.trivia_channel.send(embed=embed)

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

    async def add_score(self, guild, user_id: int, points: int):
        """Add points to a user's score."""
        async with self.config.guild(guild).scores() as scores:
            if str(user_id) not in scores:
                scores[str(user_id)] = 0
            scores[str(user_id)] += points

    @commands.Cog.listener()
    async def on_message(self, message):
        """Check messages for trivia answers."""
        if (not self.trivia_active or 
            not self.current_question or 
            message.author.bot or 
            message.channel != self.trivia_channel):
            return

        # Convert answer to lowercase for comparison
        answer = message.content.lower().strip()
        correct_answers = [ans.lower().strip() for ans in self.current_answers]

        if answer in correct_answers:
            # Award points (more points for faster answers)
            points = 10  # Base points
            await self.add_score(message.guild, message.author.id, points)
            
            await message.add_reaction("✅")
            await self.trivia_channel.send(
                f"🎉 Correct, {message.author.mention}! The answer was: {self.current_answers[0]}"
            )
            
            # Reset current question
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
                question_data = random.choice(questions)
                self.current_question = question_data["question"]
                self.current_answers = question_data["answers"]
                self.current_hints = question_data.get("hints", []).copy()
                main_answer = self.current_answers[0]

                await channel.send(f"**Trivia Question:**\n{self.current_question}\n*Use `!trivia hint` for a hint!*")
                
                for i in range(30, 0, -5):
                    if not self.trivia_active:  # Check if trivia was stopped
                        return
                    await asyncio.sleep(5)
                    if not self.current_question:  # Question was answered
                        break

                    if i == 15:
                        partial_answer = self.get_partial_answer(main_answer, 0.33)
                        await channel.send(f"**15 seconds left!** The answer looks like: {partial_answer}")
                    elif i == 10:
                        partial_answer = self.get_partial_answer(main_answer, 0.66)
                        await channel.send(f"**10 seconds left!** The answer looks like: {partial_answer}")

                if self.current_question and self.trivia_active:  # Time's up and trivia still active
                    await channel.send(f"Time's up! The correct answer was: {main_answer}")
                    self.current_question = None
                    self.current_answers = []
                    self.current_hints = []

                await asyncio.sleep(5)  # Pause before next question

        except asyncio.CancelledError:
            # Handle the cancellation gracefully
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
