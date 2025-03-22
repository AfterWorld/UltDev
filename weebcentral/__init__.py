from redbot.core.bot import Red

from .weeb import MangaDexTracker

async def setup(bot: Red):
    await bot.add_cog(MangaDexTracker(bot))
