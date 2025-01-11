import discord
from redbot.core import commands, Config
import openai


class AICharacter(commands.Cog):
    """Interact with fictional characters using OpenAI API."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        default_global = {"api_key": None, "character_profiles": {}}
        self.config.register_global(**default_global)

    async def red_delete_data_for_user(self, **kwargs):
        """Handle data deletion requests (not applicable here)."""
        pass

    # ==============================
    # COMMANDS
    # ==============================
    @commands.group()
    async def ai(self, ctx):
        """AI Character Interaction settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ai.command()
    @commands.is_owner()
    async def setapikey(self, ctx, api_key: str):
        """Set the OpenAI API key."""
        await self.config.api_key.set(api_key)
        await ctx.send("The OpenAI API key has been successfully set!")

    @ai.command()
    @commands.is_owner()
    async def addcharacter(self, ctx, name: str, *, description: str):
        """Add a character profile."""
        profiles = await self.config.character_profiles()
        profiles[name.lower()] = description
        await self.config.character_profiles.set(profiles)
        await ctx.send(f"Character `{name}` has been added!")

    @ai.command()
    @commands.is_owner()
    async def listcharacters(self, ctx):
        """List all available character profiles."""
        profiles = await self.config.character_profiles()
        if not profiles:
            await ctx.send("No character profiles have been added yet.")
            return
        character_list = "\n".join(f"- {name}" for name in profiles.keys())
        await ctx.send(f"Available characters:\n{character_list}")

    @commands.command()
    async def character(self, ctx, name: str, *, question: str):
        """Ask a fictional character a question."""
        api_key = await self.config.api_key()
        if not api_key:
            await ctx.send("The OpenAI API key is not set. Please set it using `[p]ai setapikey`.")
            return

        openai.api_key = api_key
        profiles = await self.config.character_profiles()

        if name.lower() not in profiles:
            await ctx.send(f"Character `{name}` is not available. Use `[p]ai listcharacters` to see available characters.")
            return

        character_description = profiles[name.lower()]
        prompt = (
            f"You are {character_description}. Answer the following question as this character:\n\n"
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
            await ctx.send(f"An error occurred: {e}")

    # ==============================
    # UTILITIES
    # ==============================
    async def get_character_description(self, name: str) -> str:
        """Fetch a character's description."""
        profiles = await self.config.character_profiles()
        return profiles.get(name.lower(), None)


def setup(bot):
    bot.add_cog(AICharacter(bot))
