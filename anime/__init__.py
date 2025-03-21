import asyncio
import discord
import re
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from redbot.core import commands
from redbot.core.bot import Red

# Import all the modules
from .animeforums import AnimeForumCog

__version__ = "1.0.0"

log = logging.getLogger("red.animeforum")

# This is required by Red for initialization
async def setup(bot: Red):
    """Add the cog to the bot."""
    
    # Log the start of initialization
    log.info("Initializing AnimeForumCog...")
    
    try:
        # Allow event registration before the cog is added
        cog = AnimeForumCog(bot)
        
        # Connect all the components
        cog.forum_creator.set_mal_api(cog.mal_api)
        
        # Initialize any background tasks
        
        # Add the cog to the bot
        await bot.add_cog(cog)
        
        log.info("AnimeForumCog initialized successfully")
        
    except Exception as e:
        log.error(f"Error during AnimeForumCog initialization: {e}")
        raise e
