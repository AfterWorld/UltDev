from redbot.core.bot import Red

from .weeb import WeebCentral

async def setup(bot: Red):
    await bot.add_cog(WeebCentral(bot))
