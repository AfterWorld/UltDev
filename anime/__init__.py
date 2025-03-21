from redbot.core.bot import Red
from .animeforums import AnimeForumCreator


async def setup(bot: Red):
    cog = AnimeForumCreator(bot)
    await bot.add_cog(cog)
