from redbot.core.bot import Red
from .skadosh import Skadosh

__red_end_user_data_statement__ = "This cog temporarily stores message deletion logs from users. The logs are uploaded to mclo.gs and only URLs are stored in memory."

async def setup(bot: Red):
    cog = Skadosh(bot)
    await bot.add_cog(cog)
