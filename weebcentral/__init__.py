from redbot.core.bot import Red

from .weeb import MangaTracker

async def setup(bot: Red):
    await bot.add_cog(MangaTracker(bot))
