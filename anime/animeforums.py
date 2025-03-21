import asyncio
import discord
import json
import logging
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Any

import aiohttp
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
from redbot.core.utils.predicates import MessagePredicate

log = logging.getLogger("red.animeforum")

# Import additional modules
from .mal_api import MyAnimeListAPI
from .forum_creator import ForumCreator
from .cache_manager import CacheManager
from .event_manager import EventManager
from .analytics import AnalyticsManager
from .utils import create_embed, chunked_send, check_permissions


class AnimeForumCog(commands.Cog):
    """
    A comprehensive cog for creating and managing anime forum channels with MyAnimeList integration.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8675309, force_registration=True)
        
        # Default settings
        default_guild = {
            "forum_command_prefix": ".",
            "forums_category_name": "Anime Forums",
            "mention_message": "Hello there! If you want to discuss anime, please use one of our forum channels or create a new one with `.forum [anime name]`!",
            "default_tags": ["Discussion", "Question", "Recommendation", "Review", "Spoiler", "Fanart", "News", "Meme", "Seasonal", "Top Rated"],
            "auto_topic": True,
            "use_mal_data": True,
            "default_post_guidelines": True,
            "auto_thread_create": False,
            "moderation": {
                "spoiler_detection": True,
                "content_filter": False,
                "auto_organize": True
            },
            "analytics": {
                "enabled": True,
                "track_activity": True,
                "leaderboard_enabled": True
            },
            "mal_client_id": None,
            "notifications": {
                "new_episodes": True,
                "new_seasons": True
            },
            "rate_limits": {
                "max_forums_per_minute": 5,
                "max_bulk_create": 15,
                "cooldown_seconds": 2
            }
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_global(mal_client_id=None)
        
        # Initialize components
        self.session = aiohttp.ClientSession()
        self.cache = CacheManager(expiry=3600, max_size=500)
        self.mal_api = MyAnimeListAPI(self.session, self.cache)
        self.forum_creator = ForumCreator(bot, self.config, self.cache)
        self.event_manager = EventManager(bot, self.config, self.mal_api, self.cache)
        self.analytics = AnalyticsManager(bot, self.config)
        
        # Track rate limits
        self.command_timestamps = {}
        
        # Start background tasks
        self.bg_tasks = []
        self.start_background_tasks()
        
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Cancel background tasks
        for task in self.bg_tasks:
            task.cancel()
            
        # Close sessions
        asyncio.create_task(self.session.close())
        
    def start_background_tasks(self):
        """Start all background tasks for this cog"""
        self.bg_tasks.append(self.bot.loop.create_task(self.event_manager.schedule_checker()))
        self.bg_tasks.append(self.bot.loop.create_task(self.analytics.process_analytics_queue()))
        
    async def check_rate_limit(self, ctx, command_type="regular") -> Tuple[bool, str]:
        """Check if a command exceeds rate limits"""
        # Get guild settings for rate limits
        settings = await self.config.guild(ctx.guild).rate_limits()
        
        # Determine limits based on command type
        if command_type == "bulk":
            max_per_minute = settings["max_bulk_create"]
        else:
            max_per_minute = settings["max_forums_per_minute"]
            
        cooldown = settings["cooldown_seconds"]
        
        # Get the guild's command history
        guild_id = ctx.guild.id
        if guild_id not in self.command_timestamps:
            self.command_timestamps[guild_id] = []
        
        # Clean up old timestamps
        current_time = time.time()
        self.command_timestamps[guild_id] = [
            t for t in self.command_timestamps[guild_id] 
            if current_time - t < 60
        ]
        
        # Check if we've hit the rate limit
        if len(self.command_timestamps[guild_id]) >= max_per_minute:
            remaining = 60 - (current_time - self.command_timestamps[guild_id][0])
            return False, f"Rate limit reached. Please try again in {remaining:.1f} seconds."
        
        # Check if we need to apply cooldown
        if self.command_timestamps[guild_id] and current_time - self.command_timestamps[guild_id][-1] < cooldown:
            return False, f"Please wait {cooldown - (current_time - self.command_timestamps[guild_id][-1]):.1f} seconds between commands."
        
        # Add timestamp and allow command
        self.command_timestamps[guild_id].append(current_time)
        return True, ""

    @commands.group()
    @commands.guild_only()
    async def animecog(self, ctx):
        """Main command group for AnimeForumCog"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
            
    @animecog.command(name="version")
    async def show_version(self, ctx):
        """Show version information for the cog"""
        embed = discord.Embed(
            title="Anime Forum Cog",
            description="Ultimate Anime Forum Creator for Discord",
            color=discord.Color.blue()
        )
        embed.add_field(name="Version", value="1.0.0", inline=True)
        embed.add_field(name="Author", value="Claude", inline=True)
        embed.add_field(name="Commands", value="`.forum`, `.seasonal`, `.toptier`", inline=False)
        embed.add_field(name="Config", value="`.animeset` for configuration", inline=False)
        await ctx.send(embed=embed)

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def animeset(self, ctx):
        """Configure the Anime Forum Creator cog"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @animeset.command(name="prefix")
    async def set_prefix(self, ctx, prefix: str):
        """Set the prefix for forum commands (default '.')"""
        await self.config.guild(ctx.guild).forum_command_prefix.set(prefix)
        await ctx.send(f"Forum command prefix set to: {prefix}")

    @animeset.command(name="category")
    async def set_category(self, ctx, *, category_name: str):
        """Set the category name for anime forums"""
        await self.config.guild(ctx.guild).forums_category_name.set(category_name)
        await ctx.send(f"Anime forums category name set to: {category_name}")

    @animeset.command(name="mentionmsg")
    async def set_mention_message(self, ctx, *, message: str):
        """Set the message sent when the bot is mentioned"""
        await self.config.guild(ctx.guild).mention_message.set(message)
        await ctx.send("Mention message has been updated.")
        
    @animeset.command(name="addtag")
    async def add_default_tag(self, ctx, *, tag_name: str):
        """Add a tag to the default forum tags"""
        async with self.config.guild(ctx.guild).default_tags() as tags:
            if tag_name in tags:
                await ctx.send(f"Tag '{tag_name}' already exists.")
                return
            tags.append(tag_name)
        await ctx.send(f"Added '{tag_name}' to default forum tags.")
        
    @animeset.command(name="removetag")
    async def remove_default_tag(self, ctx, *, tag_name: str):
        """Remove a tag from the default forum tags"""
        async with self.config.guild(ctx.guild).default_tags() as tags:
            if tag_name not in tags:
                await ctx.send(f"Tag '{tag_name}' doesn't exist.")
                return
            tags.remove(tag_name)
        await ctx.send(f"Removed '{tag_name}' from default forum tags.")
    
    @animeset.command(name="malclientid")
    async def set_mal_client_id(self, ctx, client_id: str = None):
        """Set MyAnimeList API client ID (leave empty to reset)"""
        # Reset if no client ID provided
        if client_id is None:
            await self.config.guild(ctx.guild).mal_client_id.set(None)
            await ctx.send("MyAnimeList client ID has been reset.")
            return
            
        # Test the client ID
        self.mal_api.set_client_id(client_id)
        try:
            test_result = await self.mal_api.search_anime("test", limit=1)
            if test_result:
                await self.config.guild(ctx.guild).mal_client_id.set(client_id)
                await ctx.send("MyAnimeList client ID has been set and tested successfully.")
            else:
                await ctx.send("Error: Could not validate MyAnimeList client ID.")
        except Exception as e:
            await ctx.send(f"Error testing MyAnimeList client ID: {e}")
    
    @animeset.command(name="togglemoderation")
    async def toggle_moderation_feature(self, ctx, feature: str):
        """Toggle moderation features (spoiler_detection, content_filter, auto_organize)"""
        async with self.config.guild(ctx.guild).moderation() as moderation:
            if feature not in moderation:
                await ctx.send(f"Unknown feature '{feature}'. Available features: {', '.join(moderation.keys())}")
                return
                
            moderation[feature] = not moderation[feature]
            state = "enabled" if moderation[feature] else "disabled"
            
        await ctx.send(f"Moderation feature '{feature}' has been {state}.")
        
    @animeset.command(name="toggleanalytics")
    async def toggle_analytics_feature(self, ctx, feature: str):
        """Toggle analytics features (enabled, track_activity, leaderboard_enabled)"""
        async with self.config.guild(ctx.guild).analytics() as analytics:
            if feature not in analytics:
                await ctx.send(f"Unknown feature '{feature}'. Available features: {', '.join(analytics.keys())}")
                return
                
            analytics[feature] = not analytics[feature]
            state = "enabled" if analytics[feature] else "disabled"
            
        await ctx.send(f"Analytics feature '{feature}' has been {state}.")
    
    @animeset.command(name="settings")
    async def show_settings(self, ctx):
        """Show current anime forum settings"""
        settings = await self.config.guild(ctx.guild).all()
        
        # Format the settings in a readable way
        pages = []
        
        # Basic settings
        basic_settings = (
            "**Basic Settings:**\n"
            f"Forum Command Prefix: `{settings['forum_command_prefix']}`\n"
            f"Forums Category: `{settings['forums_category_name']}`\n"
            f"Use MAL Data: `{settings['use_mal_data']}`\n"
            f"Auto Topic: `{settings['auto_topic']}`\n"
            f"Default Post Guidelines: `{settings['default_post_guidelines']}`\n"
            f"Auto Thread Create: `{settings['auto_thread_create']}`\n"
        )
        pages.append(basic_settings)
        
        # Default tags
        tags_str = ", ".join(settings['default_tags'])
        tags_settings = f"**Default Tags:**\n{tags_str}"
        pages.append(tags_settings)
        
        # Moderation settings
        mod_settings = "**Moderation Settings:**\n"
        for key, value in settings['moderation'].items():
            mod_settings += f"{key}: `{value}`\n"
        pages.append(mod_settings)
        
        # Analytics settings
        analytics_settings = "**Analytics Settings:**\n"
        for key, value in settings['analytics'].items():
            analytics_settings += f"{key}: `{value}`\n"
        pages.append(analytics_settings)
        
        # Notification settings
        notification_settings = "**Notification Settings:**\n"
        for key, value in settings['notifications'].items():
            notification_settings += f"{key}: `{value}`\n"
        pages.append(notification_settings)
        
        # Rate limit settings
        rate_limit_settings = "**Rate Limit Settings:**\n"
        for key, value in settings['rate_limits'].items():
            rate_limit_settings += f"{key}: `{value}`\n"
        pages.append(rate_limit_settings)
        
        # Send paginated settings
        for page in pages:
            await ctx.send(page)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    async def forum(self, ctx, *, name: str):
        """Create a new anime forum channel in the configured category"""
        # Check permissions
        if not await check_permissions(ctx):
            return await ctx.send("You don't have permission to create forums.")
            
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
            
        # Forward to forum creator
        await self.forum_creator.create_anime_forum(ctx, name)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    async def seasonal(self, ctx):
        """Create forum channels for current season anime"""
        # Check permissions
        if not await check_permissions(ctx):
            return await ctx.send("You don't have permission to create forums.")
            
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx, "bulk")
        if not can_proceed:
            return await ctx.send(message)
            
        # Forward to forum creator
        await self.forum_creator.create_seasonal_forums(ctx)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    async def toptier(self, ctx):
        """Create forum channels for top-rated anime"""
        # Check permissions
        if not await check_permissions(ctx):
            return await ctx.send("You don't have permission to create forums.")
            
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx, "bulk")
        if not can_proceed:
            return await ctx.send(message)
            
        # Forward to forum creator
        await self.forum_creator.create_toptier_forums(ctx)
        
    @commands.command()
    @commands.guild_only()
    async def anime(self, ctx, *, name: str):
        """Search for anime information from MyAnimeList"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
            
        async with ctx.typing():
            try:
                # Search for the anime
                result = await self.mal_api.search_anime(name)
                if not result:
                    return await ctx.send(f"Could not find anime matching '{name}'.")
                    
                # Get detailed anime info
                anime = await self.mal_api.get_anime_details(result[0]["id"])
                if not anime:
                    return await ctx.send("Error retrieving anime details.")
                
                # Create embed with anime info
                embed = create_embed(anime)
                
                # Send the embed
                await ctx.send(embed=embed)
                
                # Ask if they want to create a forum for this anime
                confirm_msg = await ctx.send(f"Would you like to create a forum for **{anime['title']}**? (y/n)")
                
                # Wait for confirmation
                try:
                    pred = MessagePredicate.yes_or_no(ctx)
                    await self.bot.wait_for("message", check=pred, timeout=30)
                    if pred.result:
                        # Create the forum
                        await self.forum_creator.create_anime_forum(ctx, anime["title"], anime_data=anime)
                    else:
                        await ctx.send("Forum creation cancelled.")
                except asyncio.TimeoutError:
                    await ctx.send("No response received, forum creation cancelled.")
                    
            except Exception as e:
                log.error(f"Error in anime command: {e}")
                await ctx.send(f"An error occurred while searching for anime: {e}")
                
    @commands.command()
    @commands.guild_only()
    async def watchlist(self, ctx, action: str = "show", *, anime_name: str = None):
        """Manage your personal anime watchlist"""
        # This will be implemented in the watchlist_manager.py module
        await ctx.send("This feature is coming soon!")
        
    @commands.command()
    @commands.guild_only()
    async def schedule(self, ctx, action: str = "show", *, anime_name: str = None):
        """View or manage upcoming anime episode schedule"""
        # This will be implemented in the event_manager.py module
        await ctx.send("This feature is coming soon!")
        
    @commands.command()
    @commands.guild_only()
    async def upcoming(self, ctx):
        """Show upcoming anime for next season"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
            
        await self.event_manager.show_upcoming_season(ctx)
                
    @commands.command()
    @commands.guild_only()
    async def stats(self, ctx, *, forum_name: str = None):
        """Show activity statistics for anime forums"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
            
        await self.analytics.show_forum_stats(ctx, forum_name)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle messages in forum channels"""
        if message.author.bot or not message.guild:
            return
            
        # Get settings for this guild
        settings = await self.config.guild(message.guild).all()
        
        # Handle bot mention
        if self.bot.user in message.mentions and not message.mention_everyone:
            await message.channel.send(settings["mention_message"])
            
        # Process message for analytics
        if settings["analytics"]["enabled"] and settings["analytics"]["track_activity"]:
            self.analytics.track_message(message)
            
        # Handle forum thread interaction
        if isinstance(message.channel, discord.Thread) and message.channel.parent:
            parent_channel = message.channel.parent
            
            # Check if parent is a forum channel
            if isinstance(parent_channel, discord.ForumChannel):
                # Process message for forum-specific features
                await self.forum_creator.process_thread_message(message, parent_channel, settings)

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        """Enhance new threads in anime forums"""
        # Only process if thread parent is a forum channel
        if not isinstance(thread.parent, discord.ForumChannel):
            return
            
        # Get settings for this guild
        settings = await self.config.guild(thread.guild).all()
        
        # Check if in anime category
        anime_category_name = settings["forums_category_name"]
        category_name = thread.parent.category.name if thread.parent.category else None
        
        if not category_name or category_name != anime_category_name:
            return
            
        # Process the new thread
        await self.forum_creator.process_new_thread(thread, settings)
        
        # Track for analytics
        if settings["analytics"]["enabled"] and settings["analytics"]["track_activity"]:
            self.analytics.track_thread_create(thread)


async def setup(bot):
    """Set up the AnimeForumCog with all required modules"""
    # The module loading is handled with relative imports so order doesn't matter
    cog = AnimeForumCog(bot)
    await bot.add_cog(cog)
