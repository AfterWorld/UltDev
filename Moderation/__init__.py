from redbot.core.bot import Red
from .moderation import Moderation


async def setup(bot: Red):
    """Load the Deathmatch cog."""
    cog = Moderation(bot)
    await bot.add_cog(cog)
