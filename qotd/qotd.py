import discord
from redbot.core import commands, Config
import random
import aiohttp
import asyncio
import json
import base64
from datetime import datetime, timedelta

class QOTD(commands.Cog):
    """A Question of the Day system with themes, GitHub integration, restricted reactions, and user submissions."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        default_guild = {
            "channel_id": None,  # Where QOTD is posted
            "review_channel_id": None,  # Where admin reviews are done
            "theme": "general",  # Default theme
            "used_questions": {},  # Used questions for each theme
            "submissions": {},  # User submissions by theme
            "github_token": None,  # GitHub API token for writing to repo
            "user_cooldowns": {},  # Track user cooldowns for submitting questions
        }
        self.config.register_guild(**default_guild)
        self.github_base_url = "https://raw.githubusercontent.com/AfterWorld/UltDev/main/qotd/themes/"
        self.github_api_url = "https://api.github.com/repos/AfterWorld/UltDev/contents/qotd/themes/"
        self.qotd_started = False  # Tracks whether QOTD has begun
        self.allowed_reactions = ["👍", "👎"]  # Allowed reactions for admin review
        self.bg_task = self.bot.loop.create_task(self.qotd_task())

    async def red_delete_data_for_user(self, **kwargs):
        """Handle data deletion requests."""
        pass

    def cog_unload(self):
        """Cancel the background task when the cog is unloaded."""
        self.bg_task.cancel()

    # ==============================
    # AUTOMATIC QOTD POSTING
    # ==============================
    async def qotd_task(self):
        """Automatically post a QOTD every 12 hours."""
        await self.bot.wait_until_ready()
        while True:
            if self.qotd_started:  # Only run if QOTD has begun
                for guild in self.bot.guilds:
                    await self.post_random_qotd(guild)
            await asyncio.sleep(43200)  # Wait 12 hours

    async def post_random_qotd(self, guild):
        """Post a random QOTD from any theme in the configured channel for the guild."""
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id:
            return  # No channel set for this guild

        channel = guild.get_channel(channel_id)
        if not channel:
            return  # Channel not found

        themes = ["general", "onepiece", "anime"]
        random.shuffle(themes)  # Shuffle themes to pick randomly

        for theme in themes:
            questions, used_questions = await self.load_questions(guild, theme)
            if questions:
                question = random.choice(questions)
                embed = self.create_embed(question, theme)
                await channel.send(embed=embed)
                await self.mark_question_used(guild, theme, question)
                break
        else:
            await channel.send("No more questions available for any theme.")

    async def load_questions(self, guild, theme):
        """Load questions from GitHub for the specified theme."""
        url = f"{self.github_base_url}{theme}.txt"
        used_questions = await self.config.guild(guild).used_questions()
        used_questions = used_questions.get(theme, [])

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        print(f"Error: Could not fetch questions for theme '{theme}' from {url} (Status {response.status}).")
                        return [], used_questions
                    content = await response.text()
                    questions = [line.strip() for line in content.split("\n") if line.strip()]
        except Exception as e:
            print(f"Error fetching questions from GitHub: {e}")
            return [], used_questions

        # Exclude used questions
        questions = [q for q in questions if q not in used_questions]
        return questions, used_questions

    async def mark_question_used(self, guild, theme, question):
        """Mark a question as used for the specified theme."""
        used_questions = await self.config.guild(guild).used_questions()
        if theme not in used_questions:
            used_questions[theme] = []
        used_questions[theme].append(question)
        await self.config.guild(guild).used_questions.set(used_questions)

    # ==============================
    # EMBED CREATION
    # ==============================
    def create_embed(self, question, theme):
        """Create a themed embed for the QOTD."""
        themes = {
            "general": {
                "title": "🌟 General QOTD 🌟",
                "description": question,
                "color": discord.Color.blue(),
                "footer": "Think carefully and share your thoughts!",
            },
            "onepiece": {
                "title": "🏴‍☠️ One Piece QOTD 🏴‍☠️",
                "description": question,
                "color": discord.Color.orange(),
                "footer": "Set sail and answer like a pirate!",
            },
            "anime": {
                "title": "✨ Anime QOTD ✨",
                "description": question,
                "color": discord.Color.purple(),
                "footer": "Share your anime thoughts!",
            },
        }

        selected_theme = themes.get(theme, themes["general"])
        embed = discord.Embed(
            title=selected_theme["title"],
            description=selected_theme["description"],
            color=selected_theme["color"],
        )
        embed.set_footer(text=selected_theme["footer"])
        return embed

    # ==============================
    # COMMANDS
    # ==============================
    @commands.group()
    async def qotd(self, ctx):
        """Manage QOTD settings."""
        pass

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for QOTD posts."""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"QOTD channel set to {channel.mention}.")

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def setreviewchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for reviewing submitted questions."""
        await self.config.guild(ctx.guild).review_channel_id.set(channel.id)
        await ctx.send(f"Review channel set to {channel.mention}.")

    @qotd.command()
    async def submit(self, ctx, theme: str, *, question: str):
        """Submit a question for admin approval."""
        current_time = datetime.utcnow()
        cooldowns = await self.config.guild(ctx.guild).user_cooldowns()
        user_id = str(ctx.author.id)

        if user_id in cooldowns:
            last_submit_time = datetime.fromisoformat(cooldowns[user_id])
            if current_time < last_submit_time + timedelta(hours=2):
                remaining_time = last_submit_time + timedelta(hours=2) - current_time
                await ctx.send(f"You can submit another question in {remaining_time.seconds // 60} minutes.")
                return

        cooldowns[user_id] = current_time.isoformat()
        await self.config.guild(ctx.guild).user_cooldowns.set(cooldowns)

        submissions = await self.config.guild(ctx.guild).submissions()
        if theme not in submissions:
            submissions[theme] = []
        submissions[theme].append({"user": ctx.author.id, "question": question})
        await self.config.guild(ctx.guild).submissions.set(submissions)
        await ctx.send(f"Your question has been submitted for the `{theme}` theme.")

    @qotd.command()
    async def review(self, ctx, theme: str):
        """Review submitted questions for a theme."""
        submissions = await self.config.guild(ctx.guild).submissions()
        if theme not in submissions or not submissions[theme]:
            await ctx.send(f"No submissions for the `{theme}` theme.")
            return

        for submission in submissions[theme]:
            user_id = submission["user"]
            question = submission["question"]

            embed = discord.Embed(
                title=f"Review Submission for `{theme}`",
                description=question,
                color=discord.Color.gold(),
            )
            embed.set_footer(text="React with 👍 to approve or 👎 to deny.")

            message = await ctx.send(embed=embed)
            await message.add_reaction("👍")
            await message.add_reaction("👎")

            def check(reaction, user):
                return (
                    user == ctx.author
                    and str(reaction.emoji) in ["👍", "👎"]
                    and reaction.message.id == message.id
                )

            try:
                reaction, _ = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                if str(reaction.emoji) == "👍":
                    await self.add_question_to_github(ctx, theme, question)
                    await message.clear_reactions()
                    await ctx.send(f"The question has been added to the `{theme}` theme!")
                elif str(reaction.emoji) == "👎":
                    await message.clear_reactions()
                    reason_message = await ctx.send("Please provide a reason for rejecting this question.")

                    def message_check(m):
                        return m.author == ctx.author and m.channel == ctx.channel

                    try:
                        reason = await self.bot.wait_for("message", timeout=60.0, check=message_check)
                        user = self.bot.get_user(user_id)
                        if user:
                            await user.send(
                                f"Your question for the `{theme}` theme was denied by an admin.\nReason: {reason.content}"
                            )
                        await ctx.send("The user has been notified about the denial.")
                    except asyncio.TimeoutError:
                        await ctx.send("You didn't provide a reason in time. Skipping notification.")
            except asyncio.TimeoutError:
                await ctx.send("You didn't react in time. Moving to the next submission.")

        # Clear reviewed submissions
        submissions[theme] = []
        await self.config.guild(ctx.guild).submissions.set(submissions)

    @qotd.command()
    @commands.admin_or_permissions(manage_guild=True)
    async def begin(self, ctx):
        """Begin the QOTD posting every 12 hours."""
        self.qotd_started = True
        await ctx.send("QOTD posting has begun. A question will be posted every 12 hours.")

    async def add_question_to_github(self, ctx, theme, question):
        """Add a question to the GitHub .txt file."""
        token = await self.config.guild(ctx.guild).github_token()
        if not token:
            await ctx.send("GitHub API token is not set. Use `.qotd setapikey` to set it.")
            return

        url = f"{self.github_api_url}{theme}.txt"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

        async with aiohttp.ClientSession() as session:
            # Fetch the current file content and sha
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    await ctx.send(f"Error: Could not fetch the `{theme}` theme file.")
                    return
                file_data = await response.json()
                content = base64.b64decode(file_data["content"]).decode("utf-8")
                sha = file_data["sha"]
                current_questions = content.split("\n")

            # Check for duplicates
            if question in current_questions:
                await ctx.send(f"The question already exists in the `{theme}` theme.")
                return

            # Add the new question and encode content
            current_questions.append(question)
            updated_content = base64.b64encode("\n".join(current_questions).encode("utf-8")).decode("utf-8")

            # Push the updated file back to GitHub
            data = {
                "message": f"Add new question to {theme}",
                "content": updated_content,
                "sha": sha,
            }

            async with session.put(url, headers=headers, data=json.dumps(data)) as response:
                if response.status == 200:
                    await ctx.send(f"The question has been successfully added to `{theme}`.")
                else:
                    await ctx.send("Error: Could not update the GitHub repository.")

def setup(bot):
    bot.add_cog(QOTD(bot))
