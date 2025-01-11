import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import openai
import asyncio
import random
from datetime import datetime, timedelta


class AICharacter(commands.Cog):
    """Interact with fictional characters using OpenAI API."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        default_global = {
            "api_key": None,
            "character_profiles": {},  # Store dynamic character profiles
            "daily_token_limit": 50000,
            "daily_tokens_used": 0,
            "last_token_reset": None,
        }
        default_guild = {
            "ai_enabled": True,
            "chat_channels": [],
        }
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.token_reset_task = self.bot.loop.create_task(self.reset_daily_tokens())

    def cog_unload(self):
        """Unload background tasks when the cog is removed."""
        self.token_reset_task.cancel()

    # ==============================
    # COMMANDS
    # ==============================
    @commands.group(name="aiadmin", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def aiadmin(self, ctx: commands.Context):
        """Admin commands for AICharacter settings."""
        await ctx.send_help(ctx.command)

    @aiadmin.command(name="setapikey")
    async def set_api_key(self, ctx: commands.Context, api_key: str):
        """Set the OpenAI API key."""
        await self.config.api_key.set(api_key)
        await ctx.send("OpenAI API key has been set!")

    @aiadmin.command(name="toggleai")
    async def toggle_ai(self, ctx: commands.Context):
        """Toggle AI functionality on/off."""
        current = await self.config.guild(ctx.guild).ai_enabled()
        await self.config.guild(ctx.guild).ai_enabled.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"AI functionality has been {state}.")

    @aiadmin.command(name="setchannel")
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Enable AI in a specific channel."""
        async with self.config.guild(ctx.guild).chat_channels() as channels:
            if channel.id not in channels:
                channels.append(channel.id)
                await ctx.send(f"{channel.mention} has been added as an AI-enabled channel.")
            else:
                await ctx.send(f"{channel.mention} is already AI-enabled.")

    @aiadmin.command(name="removechannel")
    async def remove_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Disable AI in a specific channel."""
        async with self.config.guild(ctx.guild).chat_channels() as channels:
            if channel.id in channels:
                channels.remove(channel.id)
                await ctx.send(f"{channel.mention} has been removed from AI-enabled channels.")
            else:
                await ctx.send(f"{channel.mention} is not an AI-enabled channel.")

    @aiadmin.command(name="setdailylimit")
    async def set_daily_limit(self, ctx: commands.Context, limit: int):
        """Set the daily token usage limit."""
        await self.config.daily_token_limit.set(limit)
        await ctx.send(f"Daily token limit set to {limit}.")

    @commands.command(name="character")
    async def character(self, ctx: commands.Context, name: str, *, question: str):
        """Ask a question to a specific character."""
        api_key = await self.config.api_key()
        if not api_key:
            await ctx.send("OpenAI API key is not set. Use `[p]aiadmin setapikey` to configure it.")
            return

        openai.api_key = api_key
        profiles = await self.config.character_profiles()

        if name.lower() not in profiles:
            await ctx.send(f"Character `{name}` is not available. Use `[p]aiadmin listcharacters` to see available characters.")
            return

        prompt = (
            f"You are {profiles[name.lower()]}. Answer the following question as this character:\n\n"
            f"Question: {question}\n"
            f"Answer:"
        )

        try:
            response = openai.Completion.create(
                engine="text-davinci-003",
                prompt=prompt,
                max_tokens=200,
                temperature=0.7,
            )
            answer = response.choices[0].text.strip()
            await ctx.send(f"**{name.capitalize()} says:** {answer}")
        except Exception as e:
            await ctx.send(f"Error generating response: {e}")

    @commands.command(name="listcharacters")
    async def list_characters(self, ctx: commands.Context):
        """List all available characters."""
        profiles = await self.config.character_profiles()
        if not profiles:
            await ctx.send("No character profiles are available.")
        else:
            character_list = "\n".join(f"- {name.capitalize()}" for name in profiles.keys())
            await ctx.send(f"Available characters:\n{character_list}")

    @commands.command(name="addcharacter")
    @commands.is_owner()
    async def add_character(self, ctx: commands.Context, name: str, *, description: str):
        """Add a new character with a description."""
        profiles = await self.config.character_profiles()
        profiles[name.lower()] = description
        await self.config.character_profiles.set(profiles)
        await ctx.send(f"Character `{name}` has been added!")

    # ==============================
    # UTILITIES
    # ==============================
    async def reset_daily_tokens(self):
        """Reset the daily token usage limit."""
        await self.bot.wait_until_ready()
        while True:
            now = datetime.utcnow()
            next_reset = datetime(now.year, now.month, now.day) + timedelta(days=1)
            await asyncio.sleep((next_reset - now).total_seconds())

            await self.config.daily_tokens_used.set(0)
            await self.config.last_token_reset.set(next_reset.isoformat())


async def setup(bot: Red):
    cog = AICharacter(bot)
    await bot.add_cog(cog)
