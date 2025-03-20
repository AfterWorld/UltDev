"""
Prune cog for Red Discord Bot - Optimized version
Allows moderators to prune, nuke, and log messages efficiently.
"""
import asyncio
from redbot.core.bot import Red
from .prune import Prune

__red_end_user_data_statement__ = (
    "This cog stores deleted message contents for moderation logs. "
    "This data can be removed by server administrators using the pruneset command."
)

async def setup(bot: Red):
    """Load the Prune cog."""
    cog = Prune(bot)
    await bot.add_cog(cog)
    await cog.initialize()
