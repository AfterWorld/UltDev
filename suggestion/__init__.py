from redbot.core.bot import Red
from .suggestion import Suggestions

async def setup(bot):
    await bot.add_cog(Suggestion(bot))
