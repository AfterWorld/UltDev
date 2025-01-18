from redbot.core.bot import Red
from .mods import Moderation


async def setup(bot: Red):
    cog = Moderation(bot)
    await bot.add_cog(cog)
