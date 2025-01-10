import discord
from redbot.core import commands, Config
import random
import aiohttp


class QOTD(commands.Cog):
    """A Question of the Day system with themes, GitHub integration, and reactions."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        default_guild = {
            "channel_id": None,  # Channel to post QOTD
            "theme": "general",  # Default theme
            "used_questions": {},  # Dict to track used questions by theme
            "submissions": {},  # User-submitted questions by theme
        }
        self.config.register_guild(**default_guild)
        self.github_base_url = "https://raw.githubusercontent.com/AfterWorld/UltDev/main/qotd/themes/"
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
            for guild in self.bot.guilds:
                await self.post_qotd(guild)
            await asyncio.sleep(43200)  # Wait 12 hours (43200 seconds)

    async def post_qotd(self, guild):
        """Post a QOTD in the configured channel for the guild."""
        channel_id = await self.config.guild(guild).channel_id()
        if not channel_id:
            return  # No channel set for this guild

        channel = guild.get_channel(channel_id)
        if not channel:
            return  # Channel not found

        theme = await self.config.guild(guild).theme()
        questions, used_questions = await self.load_questions(guild, theme)
        if not questions:
            await channel.send(f"No more questions available for the `{theme}` theme.")
            return

        question = random.choice(questions)
        embed = self.create_embed(question, theme)
        message = await channel.send(embed=embed)

        # Add reactions for engagement
        reactions = ["👍", "👎", "🤔"]
        for reaction in reactions:
            await message.add_reaction(reaction)

        await self.mark_question_used(guild, theme, question)

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
    # ADMIN COMMANDS
    # ==============================
    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def qotd(self, ctx):
        """Manage QOTD settings."""
        pass

    @qotd.command()
    async def setchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for QOTD."""
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"QOTD channel set to {channel.mention}.")

    @qotd.command()
    async def settheme(self, ctx, theme: str):
        """Set the theme for QOTD."""
        available_themes = ["general", "onepiece", "anime"]
        if theme not in available_themes:
            await ctx.send(f"Invalid theme. Available themes: {', '.join(available_themes)}")
            return

        await self.config.guild(ctx.guild).theme.set(theme)
        await ctx.send(f"QOTD theme set to `{theme}`.")

    @qotd.command()
    async def themes(self, ctx):
        """List all available themes for QOTD."""
        themes = ["general", "onepiece", "anime"]
        theme_list = "\n".join([f"- {theme}" for theme in themes])
        await ctx.send(f"Available themes:\n{theme_list}")

    # ==============================
    # USER SUBMISSIONS
    # ==============================
    @qotd.command()
    async def submit(self, ctx, theme: str, *, question: str):
        """Submit a question for approval."""
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

        review_list = "\n".join([f"- {q['question']} (Submitted by <@{q['user']}>)" for q in submissions[theme]])
        await ctx.send(f"Submitted questions for `{theme}`:\n{review_list}")


def setup(bot):
    bot.add_cog(QOTD(bot))
