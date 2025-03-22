from redbot.core.bot import Red

from .weebcentral import WeebCentral

async def setup(bot: Red):
    await bot.add_cog(WeebCentral(bot))
