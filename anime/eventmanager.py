import asyncio
import discord
import logging
import json
import time
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.utils.predicates import MessagePredicate

from .malapi import MyAnimeListAPI
from .cachemanager import CacheManager
from .utils import create_embed, format_relative_time

log = logging.getLogger("red.animeforum.event_manager")

class EventManager:
    """Manages scheduled events and notifications for anime"""
    
    def __init__(self, bot: Red, config: Config, mal_api: MyAnimeListAPI, cache: CacheManager):
        self.bot = bot
        self.config = config
        self.mal_api = mal_api
        self.cache = cache
        
        # Register additional configs
        self.config.register_guild(
            events={
                "watching": {},  # Map of anime_id -> list of user IDs
                "scheduled_events": {},  # Map of event_id -> event_data
                "airing_notifications": [],  # List of anime_ids to notify about
                "last_check": 0  # Timestamp of last schedule check
            }
        )
        
        # Map day names to numbers (0 = Monday, 6 = Sunday) - with alternate forms
        self.weekday_map = {
            "monday": 0, "mon": 0, "m": 0,
            "tuesday": 1, "tue": 1, "tu": 1, "t": 1,
            "wednesday": 2, "wed": 2, "w": 2,
            "thursday": 3, "thu": 3, "th": 3,
            "friday": 4, "fri": 4, "f": 4,
            "saturday": 5, "sat": 5, "sa": 5,
            "sunday": 6, "sun": 6, "su": 6
        }

 async def schedule_checker(self):
        """Background task to check for scheduled events and notifications"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready():
            try:
                # Only check every 15 minutes to avoid API spam
                current_time = time.time()
                
                # Process airing notifications
                for guild in self.bot.guilds:
                    await self.check_airing_notifications(guild)
                
                # Process scheduled events
                for guild in self.bot.guilds:
                    await self.check_scheduled_events(guild)
                
                # Update last check time
                for guild in self.bot.guilds:
                    async with self.config.guild(guild).events() as events:
                        events["last_check"] = current_time
                        
            except Exception as e:
                log.error(f"Error in schedule checker: {e}")
                
            # Wait before next check (15 minutes)
            await asyncio.sleep(900)
