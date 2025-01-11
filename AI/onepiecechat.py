import openai
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box


class OnePieceChat(commands.Cog):
    """A cog for interacting with One Piece characters using OpenAI API."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {"api_key": None}
        self.config.register_global(**default_global)

    async def cog_check(self, ctx: commands.Context):
        """Ensure the cog is set up before use."""
        api_key = await self.config.api_key()
        if not api_key:
            await ctx.send("The OpenAI API key has not been set up yet.")
            return False
        return True

    @commands.is_owner()
    @commands.command()
    async def setapikey(self, ctx: commands.Context, api_key: str):
        """Set the OpenAI API key."""
        await self.config.api_key.set(api_key)
        await ctx.send("The OpenAI API key has been successfully set!")

    @commands.command()
    async def character(self, ctx: commands.Context, character: str, *, question: str):
        """Ask a One Piece character a question."""
        api_key = await self.config.api_key()
        openai.api_key = api_key

        character_profiles = {
            "luffy": "Monkey D. Luffy, a cheerful, courageous, and determined pirate who wants to become the Pirate King. He is adventurous and loves his crew.",
            "zoro": "Roronoa Zoro, a skilled swordsman and loyal pirate. He is serious, focused, and determined to become the world's greatest swordsman.",
            "nami": "Nami, a clever and resourceful navigator. She is practical, intelligent, and values treasure but deeply cares for her friends.",
            "sanji": "Sanji, the Straw Hat Pirates' cook. He is chivalrous, loves cooking, and is infatuated with women but always protects his friends.",
            "usopp": "Usopp, the crew's sniper and a talented inventor. He is humorous, creative, and dreams of becoming a brave warrior of the sea.",
            "robin": "Nico Robin, the archaeologist of the crew. She is calm, intelligent, and seeks to uncover the mysteries of the world.",
            "chopper": "Tony Tony Chopper, the crew's doctor. He is a talking reindeer with a big heart, always ready to help his friends.",
            "franky": "Franky, the shipwright of the crew. He is eccentric, loves cola, and builds innovative creations with great enthusiasm.",
            "brook": "Brook, the musician of the crew. He is a gentleman skeleton with a love for music and a cheerful, humorous personality.",
            # Add more characters as needed
        }

        # Check if the character is defined
        if character.lower() not in character_profiles:
            await ctx.send(f"I don't have a profile for {character}. Please choose a valid One Piece character.")
            return

        # Create the prompt for OpenAI
        character_description = character_profiles[character.lower()]
        prompt = (
            f"You are {character_description}. Answer the following question as this character:\n\n"
            f"Question: {question}\n"
            f"Answer:"
        )

        try:
            # Call the OpenAI API
            response = openai.Completion.create(
                engine="text-davinci-003",  # Use the appropriate model
                prompt=prompt,
                max_tokens=200,
                temperature=0.7,
            )
            answer = response.choices[0].text.strip()

            # Send the response
            await ctx.send(box(f"{character.capitalize()} says: {answer}", lang="markdown"))
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
