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
