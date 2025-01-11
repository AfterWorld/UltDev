import discord
from redbot.core import commands, Config
import openai

class AICharacter(commands.Cog):
    """Interact with fictional characters using OpenAI API."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210)
        default_global = {"api_key": None}
        self.config.register_global(**default_global)
        self.character_profiles = {
            "luffy": "Monkey D. Luffy, a cheerful, courageous, and determined pirate who wants to become the Pirate King. He is adventurous and loves his crew.",
            "zoro": "Roronoa Zoro, a skilled swordsman and loyal pirate. He is serious, focused, and determined to become the world's greatest swordsman.",
            "nami": "Nami, a clever and resourceful navigator. She is practical, intelligent, and values treasure but deeply cares for her friends.",
        }

    @commands.group()
    async def ai(self, ctx):
        """AI Character Interaction settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @ai.command()
    async def setapikey(self, ctx, api_key: str):
        """Set the OpenAI API key."""
        await self.config.api_key.set(api_key)
        await ctx.send("The OpenAI API key has been successfully set!")

    @commands.command()
    async def character(self, ctx, character: str, *, question: str):
        """Ask a fictional character a question."""
        api_key = await self.config.api_key()
        if not api_key:
            await ctx.send("The OpenAI API key is not set. Please set it using `[p]ai setapikey`.")
            return

        openai.api_key = api_key

        if character.lower() not in self.character_profiles:
            await ctx.send(f"I don't have a profile for {character}. Please choose a valid character.")
            return

        character_description = self.character_profiles[character.lower()]
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
            await ctx.send(f"**{character.capitalize()} says:** {answer}")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


def setup(bot):
    bot.add_cog(AICharacter(bot))
