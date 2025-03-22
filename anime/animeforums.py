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
from .malapi import MyAnimeListAPI
from .forumcreator import ForumCreator
from .cachemanager import CacheManager
from .eventmanager import EventManager
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
            "watchlists": {},
            "watchparties": [],
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

    async def _get_user_watchlist(self, guild_id, user_id):
        """Get a user's watchlist from the database"""
        async with self.config.guild_from_id(guild_id).watchlists() as watchlists:
            if str(user_id) not in watchlists:
                watchlists[str(user_id)] = []
            return watchlists[str(user_id)]

    async def _add_to_watchlist(self, guild_id, user_id, anime_data):
        """Add an anime to a user's watchlist"""
        # Simplified anime data to store
        anime_entry = {
            "id": anime_data.get("id"),
            "title": anime_data.get("title"),
            "image_url": anime_data.get("image_url"),
            "episodes": anime_data.get("episodes"),
            "status": anime_data.get("status"),
            "added_on": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
        
        async with self.config.guild_from_id(guild_id).watchlists() as watchlists:
            if str(user_id) not in watchlists:
                watchlists[str(user_id)] = []
                
            # Check if already in watchlist
            for existing in watchlists[str(user_id)]:
                if existing.get("id") == anime_entry["id"]:
                    return False  # Already exists
                    
            # Add to watchlist
            watchlists[str(user_id)].append(anime_entry)
            return True
    
    async def _remove_from_watchlist(self, guild_id, user_id, anime_id):
        """Remove an anime from a user's watchlist"""
        async with self.config.guild_from_id(guild_id).watchlists() as watchlists:
            if str(user_id) not in watchlists:
                return False
                
            # Find and remove the anime
            for i, anime in enumerate(watchlists[str(user_id)]):
                if anime.get("id") == anime_id:
                    watchlists[str(user_id)].pop(i)
                    return True
                    
            return False  # Not found

    async def _get_watchparties(self, guild_id):
        """Get all scheduled watch parties for a guild"""
        async with self.config.guild_from_id(guild_id).watchparties() as watchparties:
            return watchparties
    
    async def _add_watchparty(self, guild_id, anime_data, date, time, host_id, channel_id=None, description=None):
        """Add a new watch party to the schedule"""
        # Create watchparty entry
        watchparty = {
            "id": str(int(datetime.now().timestamp())),  # Unique ID based on timestamp
            "anime_id": anime_data.get("id"),
            "anime_title": anime_data.get("title"),
            "image_url": anime_data.get("image_url"),
            "date": date,
            "time": time,
            "host_id": host_id,
            "channel_id": channel_id,
            "description": description,
            "participants": [host_id],  # Host is automatically a participant
            "created_at": datetime.now().isoformat()
        }
        
        async with self.config.guild_from_id(guild_id).watchparties() as watchparties:
            watchparties.append(watchparty)
            
        return watchparty
    
    async def _remove_watchparty(self, guild_id, watchparty_id):
        """Remove a watch party from the schedule"""
        async with self.config.guild_from_id(guild_id).watchparties() as watchparties:
            for i, party in enumerate(watchparties):
                if party.get("id") == watchparty_id:
                    watchparties.pop(i)
                    return True
        return False
    
    async def _join_watchparty(self, guild_id, watchparty_id, user_id):
        """Add a user to a watch party's participants"""
        async with self.config.guild_from_id(guild_id).watchparties() as watchparties:
            for party in watchparties:
                if party.get("id") == watchparty_id:
                    if user_id not in party["participants"]:
                        party["participants"].append(user_id)
                        return True
                    return False  # Already a participant
        return False  # Party not found
    
    async def _leave_watchparty(self, guild_id, watchparty_id, user_id):
        """Remove a user from a watch party's participants"""
        async with self.config.guild_from_id(guild_id).watchparties() as watchparties:
            for party in watchparties:
                if party.get("id") == watchparty_id:
                    if user_id in party["participants"]:
                        party["participants"].remove(user_id)
                        return True
                    return False  # Not a participant
        return False  # Party not found

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
        embed.add_field(name="Author", value="UltPanda", inline=True)
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
        """Search for anime information from MyAnimeList
        
        You can search by name or by ID (prefix with 'id:')
        Example: .anime Solo Leveling
                 .anime id:40028
        """
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
            
        async with ctx.typing():
            try:
                # Check if searching by ID
                if name.lower().startswith('id:'):
                    try:
                        # Extract the ID and get anime details directly
                        anime_id = int(name[3:].strip())
                        anime = await self.mal_api.get_anime_details(anime_id)
                        if not anime:
                            return await ctx.send(f"Could not find anime with ID {anime_id}.")
                    except ValueError:
                        return await ctx.send("Invalid ID format. Use 'id:12345' where 12345 is the anime ID.")
                else:
                    # Search by name
                    result = await self.mal_api.search_anime(name)
                    
                    if not result:
                        return await ctx.send(f"Could not find anime matching '{name}'.")
                    
                    # Get the first anime result and extract the ID
                    first_result = result[0]
                    anime_id = None
                    
                    # Check which key contains the ID (could be 'id' or 'mal_id')
                    if 'id' in first_result:
                        anime_id = first_result['id']
                    elif 'mal_id' in first_result:
                        anime_id = first_result['mal_id']
                    else:
                        # Show available keys for debugging
                        keys = ", ".join(first_result.keys())
                        log.error(f"Could not find ID in anime result. Available keys: {keys}")
                        return await ctx.send("Error: Could not process anime data.")
                    
                    # Get detailed anime info using the correct ID
                    anime = await self.mal_api.get_anime_details(anime_id)
                    if not anime:
                        return await ctx.send("Error retrieving anime details.")
                
                # Show a selection list for name searches with multiple results
                if not name.lower().startswith('id:') and len(result) > 1:
                    # Create a list of anime options
                    options = []
                    for i, anime_option in enumerate(result[:5], 1):  # Limit to top 5
                        title = anime_option.get('title', 'Unknown')
                        anime_type = anime_option.get('type', 'Unknown')
                        year = ''
                        
                        # Get year from aired.from if available
                        if 'aired' in anime_option and anime_option['aired'] and 'from' in anime_option['aired']:
                            aired_from = anime_option['aired']['from']
                            if aired_from:
                                # Extract year from date string
                                if isinstance(aired_from, str) and len(aired_from) >= 4:
                                    year = f" ({aired_from[:4]})"
                        
                        options.append(f"**{i}.** {title} - {anime_type}{year} [ID: {anime_option.get('id') or anime_option.get('mal_id')}]")
                    
                    options_msg = "**Multiple results found. Reply with the number you want:**\n" + "\n".join(options)
                    await ctx.send(options_msg)
                    
                    # Wait for user selection
                    try:
                        def check(m):
                            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= len(result[:5])
                        
                        selection_msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                        selection = int(selection_msg.content)
                        
                        # Get the selected anime
                        selected = result[selection-1]
                        anime_id = selected.get('id') or selected.get('mal_id')
                        anime = await self.mal_api.get_anime_details(anime_id)
                        if not anime:
                            return await ctx.send("Error retrieving anime details.")
                    
                    except asyncio.TimeoutError:
                        return await ctx.send("Selection timed out. Please try again.")
                    except (ValueError, IndexError):
                        return await ctx.send("Invalid selection. Please try again.")
                
                # Create embed with anime info
                embed = create_embed(anime)
                
                # Add ID to the embed for reference
                embed.add_field(name="MyAnimeList ID", value=str(anime['id']), inline=True)
                
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
                log.error(f"Error in anime command: {e}", exc_info=True)
                await ctx.send(f"An error occurred while searching for anime: {str(e)}")

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def watchparty(self, ctx):
        """Manage anime watch parties
        
        Use subcommands to create, join, leave, or list watch parties:
        - .watchparty create
        - .watchparty join [id]
        - .watchparty leave [id]
        - .watchparty list
        - .watchparty info [id]
        - .watchparty cancel [id]
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
            
            # Show upcoming watch parties as a convenience
            watchparties = await self._get_watchparties(ctx.guild.id)
            
            if watchparties:
                # Sort by date/time
                watchparties.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
                
                # Show the next 3 upcoming watch parties
                upcoming = [party for party in watchparties if self._is_upcoming(party)][:3]
                
                if upcoming:
                    embed = discord.Embed(
                        title="Upcoming Watch Parties",
                        description="Here are the next few scheduled watch parties:",
                        color=discord.Color.blue()
                    )
                    
                    for party in upcoming:
                        participants = len(party.get("participants", []))
                        embed.add_field(
                            name=f"{party.get('anime_title')} - {party.get('date')} at {party.get('time')}",
                            value=f"ID: {party.get('id')}\nHost: <@{party.get('host_id')}>\nParticipants: {participants}\nUse `.watchparty info {party.get('id')}` for details",
                            inline=False
                        )
                    
                    await ctx.send(embed=embed)
    
    @watchparty.command(name="create")
    async def watchparty_create(self, ctx):
        """Create a new anime watch party"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        # Interactive creation process
        try:
            # Step 1: Ask for anime
            await ctx.send("What anime would you like to watch? (Enter name or 'id:12345')")
            
            def check_author(m):
                return m.author == ctx.author and m.channel == ctx.channel
            
            anime_msg = await self.bot.wait_for("message", check=check_author, timeout=60.0)
            anime_name = anime_msg.content
            
            # Handle direct ID input
            if anime_name.lower().startswith('id:'):
                try:
                    anime_id = int(anime_name[3:].strip())
                    anime = await self.mal_api.get_anime_details(anime_id)
                    if not anime:
                        return await ctx.send(f"Could not find anime with ID {anime_id}.")
                except ValueError:
                    return await ctx.send("Invalid ID format. Use 'id:12345' where 12345 is the anime ID.")
            else:
                # Search for the anime
                result = await self.mal_api.search_anime(anime_name)
                
                if not result:
                    return await ctx.send(f"Could not find anime matching '{anime_name}'.")
                
                # If multiple results, ask user to select one
                if len(result) > 1:
                    # Create a list of anime options
                    options = []
                    for i, anime_option in enumerate(result[:5], 1):  # Limit to top 5
                        title = anime_option.get('title', 'Unknown')
                        anime_type = anime_option.get('type', 'Unknown')
                        options.append(f"**{i}.** {title} - {anime_type}")
                    
                    options_msg = "**Multiple results found. Reply with the number you want:**\n" + "\n".join(options)
                    await ctx.send(options_msg)
                    
                    # Wait for user selection
                    try:
                        selection_msg = await self.bot.wait_for("message", check=check_author, timeout=30.0)
                        selection = int(selection_msg.content)
                        
                        if selection < 1 or selection > len(result[:5]):
                            return await ctx.send("Invalid selection. Please try again.")
                        
                        # Get the selected anime
                        selected = result[selection-1]
                        anime_id = selected.get('id') or selected.get('mal_id')
                        anime = await self.mal_api.get_anime_details(anime_id)
                    except asyncio.TimeoutError:
                        return await ctx.send("Selection timed out. Please try again.")
                    except ValueError:
                        return await ctx.send("Invalid selection. Please try again.")
                else:
                    # Use the first result
                    anime_id = result[0].get('id') or result[0].get('mal_id')
                    anime = await self.mal_api.get_anime_details(anime_id)
            
            if not anime:
                return await ctx.send("Error retrieving anime details.")
            
            # Step 2: Ask for date
            await ctx.send("When will this watch party be held? (Enter date in YYYY-MM-DD format)")
            date_msg = await self.bot.wait_for("message", check=check_author, timeout=60.0)
            date_str = date_msg.content
            
            # Validate date format
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                date_str = date_obj.strftime("%Y-%m-%d")  # Normalize format
            except ValueError:
                return await ctx.send("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-04-06)")
            
            # Step 3: Ask for time
            await ctx.send("What time will it start? (Use 24-hour format HH:MM, e.g. 18:30)")
            time_msg = await self.bot.wait_for("message", check=check_author, timeout=60.0)
            time_str = time_msg.content
            
            # Validate time format
            try:
                time_obj = datetime.strptime(time_str, "%H:%M")
                time_str = time_obj.strftime("%H:%M")  # Normalize format
            except ValueError:
                return await ctx.send("Invalid time format. Please use HH:MM in 24-hour format (e.g., 18:30)")
            
            # Step 4: Ask for description/notes
            await ctx.send("Any additional notes or details? (Enter 'none' to skip)")
            desc_msg = await self.bot.wait_for("message", check=check_author, timeout=60.0)
            description = None if desc_msg.content.lower() == "none" else desc_msg.content
            
            # Step 5: Create the watch party
            watchparty = await self._add_watchparty(
                ctx.guild.id,
                anime,
                date_str,
                time_str,
                ctx.author.id,
                ctx.channel.id,
                description
            )
            
            # Step 6: Confirm and display info
            embed = discord.Embed(
                title=f"Watch Party: {anime['title']}",
                description=f"A new watch party has been scheduled!",
                color=discord.Color.green()
            )
            
            embed.add_field(name="Date", value=date_str, inline=True)
            embed.add_field(name="Time", value=time_str, inline=True)
            embed.add_field(name="Host", value=ctx.author.mention, inline=True)
            
            if description:
                embed.add_field(name="Notes", value=description, inline=False)
                
            embed.add_field(name="Join", value=f"Use `.watchparty join {watchparty['id']}` to join this watch party", inline=False)
            
            if anime.get("image_url"):
                embed.set_thumbnail(url=anime["image_url"])
                
            await ctx.send(embed=embed)
            
            # Optional: Create a reminder/announce in the channel
            announcement = f"📺 **ANIME WATCH PARTY SCHEDULED!** 📺\n\n{ctx.author.mention} is hosting a watch party for **{anime['title']}** on **{date_str}** at **{time_str}**.\n\nUse `.watchparty join {watchparty['id']}` to join!"
            await ctx.send(announcement)
            
        except asyncio.TimeoutError:
            await ctx.send("Watch party creation timed out. Please try again.")
        except Exception as e:
            log.error(f"Error creating watch party: {e}", exc_info=True)
            await ctx.send(f"An error occurred while creating the watch party: {str(e)}")
    
    @watchparty.command(name="list")
    async def watchparty_list(self, ctx):
        """List all upcoming watch parties"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        try:
            # Get all watch parties
            watchparties = await self._get_watchparties(ctx.guild.id)
            
            if not watchparties:
                return await ctx.send("No watch parties scheduled. Create one with `.watchparty create`!")
            
            # Sort by date/time
            watchparties.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
            
            # Filter to only show upcoming parties
            upcoming = [party for party in watchparties if self._is_upcoming(party)]
            
            if not upcoming:
                return await ctx.send("No upcoming watch parties scheduled. Create one with `.watchparty create`!")
            
            # Create pages of 5 parties each
            pages = []
            for i in range(0, len(upcoming), 5):
                embed = discord.Embed(
                    title="Upcoming Anime Watch Parties",
                    description=f"Showing {i+1}-{min(i+5, len(upcoming))} of {len(upcoming)} upcoming watch parties",
                    color=discord.Color.blue()
                )
                
                for party in upcoming[i:i+5]:
                    participants = len(party.get("participants", []))
                    host = ctx.guild.get_member(party.get("host_id"))
                    host_name = host.display_name if host else "Unknown Host"
                    
                    embed.add_field(
                        name=f"{party.get('anime_title')}",
                        value=f"**Date:** {party.get('date')} at {party.get('time')}\n**Host:** {host_name}\n**Participants:** {participants}\n**ID:** {party.get('id')}",
                        inline=False
                    )
                
                embed.set_footer(text=f"Page {i//5 + 1}/{(len(upcoming)+4)//5} • Use .watchparty info [id] for details")
                pages.append(embed)
            
            # Show the pages
            if not pages:
                return await ctx.send("No upcoming watch parties found.")
            
            if len(pages) == 1:
                # Only one page, send it directly
                await ctx.send(embed=pages[0])
            else:
                # Multiple pages, use a menu
                msg = await ctx.send(embed=pages[0])
                
                # Add reactions for navigation
                await msg.add_reaction("⬅️")
                await msg.add_reaction("➡️")
                
                # Current page index
                current_page = 0
                
                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == msg.id
                
                # Wait for reactions
                while True:
                    try:
                        reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                        
                        if str(reaction.emoji) == "➡️" and current_page < len(pages) - 1:
                            current_page += 1
                            await msg.edit(embed=pages[current_page])
                        elif str(reaction.emoji) == "⬅️" and current_page > 0:
                            current_page -= 1
                            await msg.edit(embed=pages[current_page])
                        
                        # Remove the reaction
                        await msg.remove_reaction(reaction, user)
                        
                    except asyncio.TimeoutError:
                        # Stop listening for reactions
                        break
                    except Exception as e:
                        log.error(f"Error in watchparty list pagination: {e}")
                        break
        
        except Exception as e:
            log.error(f"Error listing watch parties: {e}", exc_info=True)
            await ctx.send(f"An error occurred while listing watch parties: {str(e)}")
    
    @watchparty.command(name="join")
    async def watchparty_join(self, ctx, watchparty_id: str):
        """Join a watch party"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        try:
            # Add user to participants
            success = await self._join_watchparty(ctx.guild.id, watchparty_id, ctx.author.id)
            
            if success:
                # Get updated party info
                watchparties = await self._get_watchparties(ctx.guild.id)
                party = next((p for p in watchparties if p.get("id") == watchparty_id), None)
                
                if party:
                    await ctx.send(f"{ctx.author.mention} has joined the watch party for **{party.get('anime_title')}** on {party.get('date')} at {party.get('time')}!")
                else:
                    await ctx.send(f"{ctx.author.mention} has joined the watch party!")
            else:
                await ctx.send(f"Could not join the watch party. Either the party doesn't exist or you're already a participant.")
        
        except Exception as e:
            log.error(f"Error joining watch party: {e}", exc_info=True)
            await ctx.send(f"An error occurred while joining the watch party: {str(e)}")
    
    @watchparty.command(name="leave")
    async def watchparty_leave(self, ctx, watchparty_id: str):
        """Leave a watch party"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        try:
            # Remove user from participants
            success = await self._leave_watchparty(ctx.guild.id, watchparty_id, ctx.author.id)
            
            if success:
                # Get updated party info
                watchparties = await self._get_watchparties(ctx.guild.id)
                party = next((p for p in watchparties if p.get("id") == watchparty_id), None)
                
                if party:
                    await ctx.send(f"{ctx.author.mention} has left the watch party for **{party.get('anime_title')}** on {party.get('date')} at {party.get('time')}.")
                else:
                    await ctx.send(f"{ctx.author.mention} has left the watch party.")
            else:
                await ctx.send(f"Could not leave the watch party. Either the party doesn't exist or you're not a participant.")
        
        except Exception as e:
            log.error(f"Error leaving watch party: {e}", exc_info=True)
            await ctx.send(f"An error occurred while leaving the watch party: {str(e)}")
    
    @watchparty.command(name="info")
    async def watchparty_info(self, ctx, watchparty_id: str):
        """Get detailed information about a watch party"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        try:
            # Find the watch party
            watchparties = await self._get_watchparties(ctx.guild.id)
            party = next((p for p in watchparties if p.get("id") == watchparty_id), None)
            
            if not party:
                return await ctx.send(f"Watch party with ID {watchparty_id} not found.")
            
            # Create an embed with detailed info
            embed = discord.Embed(
                title=f"Watch Party: {party.get('anime_title')}",
                description=f"Scheduled for {party.get('date')} at {party.get('time')}",
                color=discord.Color.blue()
            )
            
            # Host information
            host_id = party.get("host_id")
            host = ctx.guild.get_member(host_id)
            host_name = host.display_name if host else f"User ID: {host_id}"
            embed.add_field(name="Host", value=host.mention if host else host_name, inline=True)
            
            # Date and time
            embed.add_field(name="Date", value=party.get("date"), inline=True)
            embed.add_field(name="Time", value=party.get("time"), inline=True)
            
            # Description/notes
            if party.get("description"):
                embed.add_field(name="Notes", value=party.get("description"), inline=False)
            
            # Participants
            participants = party.get("participants", [])
            participant_list = []
            
            for user_id in participants[:15]:  # Limit to 15 to avoid hitting embed limits
                user = ctx.guild.get_member(user_id)
                if user:
                    participant_list.append(user.mention)
                else:
                    participant_list.append(f"User ID: {user_id}")
            
            if participant_list:
                embed.add_field(
                    name=f"Participants ({len(participants)})",
                    value="\n".join(participant_list) + (f"\n... and {len(participants) - 15} more" if len(participants) > 15 else ""),
                    inline=False
                )
            else:
                embed.add_field(name="Participants (0)", value="No participants yet", inline=False)
            
            # ID for reference
            embed.add_field(name="Party ID", value=party.get("id"), inline=False)
            
            # Add anime image if available
            if party.get("image_url"):
                embed.set_thumbnail(url=party.get("image_url"))
            
            # Add actions
            actions = f"Join: `.watchparty join {party.get('id')}`\nLeave: `.watchparty leave {party.get('id')}`"
            if ctx.author.id == host_id:
                actions += f"\nCancel: `.watchparty cancel {party.get('id')}`"
                
            embed.add_field(name="Actions", value=actions, inline=False)
            
            await ctx.send(embed=embed)
        
        except Exception as e:
            log.error(f"Error showing watch party info: {e}", exc_info=True)
            await ctx.send(f"An error occurred while getting watch party info: {str(e)}")
    
    @watchparty.command(name="cancel")
    async def watchparty_cancel(self, ctx, watchparty_id: str):
        """Cancel a watch party (host only)"""
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        try:
            # Find the watch party
            watchparties = await self._get_watchparties(ctx.guild.id)
            party = next((p for p in watchparties if p.get("id") == watchparty_id), None)
            
            if not party:
                return await ctx.send(f"Watch party with ID {watchparty_id} not found.")
            
            # Check if user is the host
            if party.get("host_id") != ctx.author.id and not ctx.author.guild_permissions.administrator:
                return await ctx.send("Only the host or an administrator can cancel this watch party.")
            
            # Confirm cancellation
            confirm_msg = await ctx.send(f"Are you sure you want to cancel the watch party for **{party.get('anime_title')}**? (yes/no)")
            
            # Wait for confirmation
            try:
                pred = MessagePredicate.yes_or_no(ctx)
                await self.bot.wait_for("message", check=pred, timeout=30)
                if not pred.result:
                    return await ctx.send("Cancellation aborted.")
            except asyncio.TimeoutError:
                return await ctx.send("No response received, cancellation aborted.")
            
            # Remove the watch party
            success = await self._remove_watchparty(ctx.guild.id, watchparty_id)
            
            if success:
                # Notify about cancellation
                await ctx.send(f"The watch party for **{party.get('anime_title')}** on {party.get('date')} at {party.get('time')} has been cancelled.")
                
                # If party had participants, send a notification in the original channel
                if len(party.get("participants", [])) > 1 and party.get("channel_id"):
                    try:
                        channel = ctx.guild.get_channel(party.get("channel_id"))
                        if channel:
                            participants = [f"<@{user_id}>" for user_id in party.get("participants", []) if user_id != ctx.author.id]
                            if participants:
                                notification = f"⚠️ **WATCH PARTY CANCELLED** ⚠️\n\nAttention {', '.join(participants[:10])}{'... and others' if len(participants) > 10 else ''}: The watch party for **{party.get('anime_title')}** on {party.get('date')} at {party.get('time')} has been cancelled by the host."
                                await channel.send(notification)
                    except Exception as e:
                        log.error(f"Error sending cancellation notification: {e}")
            else:
                await ctx.send("Error cancelling the watch party.")
        
        except Exception as e:
            log.error(f"Error cancelling watch party: {e}", exc_info=True)
            await ctx.send(f"An error occurred while cancelling the watch party: {str(e)}")
    
    # Helper methods
    def _is_upcoming(self, party):
        """Check if a watch party is in the future"""
        try:
            party_date = datetime.strptime(f"{party.get('date')} {party.get('time')}", "%Y-%m-%d %H:%M")
            return party_date > datetime.now()
        except (ValueError, TypeError):
            # If date parsing fails, assume it's upcoming
            return True
    
    # Reminder system (add to background tasks)
    async def _watchparty_reminder_checker(self):
        """Background task to send reminders for upcoming watch parties"""
        await self.bot.wait_until_ready()
        
        while True:
            try:
                # Check each guild
                all_guilds = await self.config.all_guilds()
                
                for guild_id, guild_data in all_guilds.items():
                    if "watchparties" not in guild_data:
                        continue
                        
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue
                        
                    # Get all upcoming watch parties
                    watchparties = guild_data["watchparties"]
                    for party in watchparties:
                        try:
                            # Parse date and time
                            party_datetime = datetime.strptime(f"{party.get('date')} {party.get('time')}", "%Y-%m-%d %H:%M")
                            now = datetime.now()
                            
                            # Calculate time until party
                            time_until = party_datetime - now
                            
                            # Send reminder at 24 hours, 1 hour, and 10 minutes before
                            if 0 < time_until.total_seconds() <= 600:  # 10 minutes
                                await self._send_watchparty_reminder(guild, party, "10 minutes")
                            elif 3590 < time_until.total_seconds() <= 3660:  # ~1 hour
                                await self._send_watchparty_reminder(guild, party, "1 hour")
                            elif 86340 < time_until.total_seconds() <= 86460:  # ~24 hours
                                await self._send_watchparty_reminder(guild, party, "24 hours")
                        except Exception as e:
                            log.error(f"Error processing watch party reminder: {e}")
                            
                # Check every minute
                await asyncio.sleep(60)
                
            except Exception as e:
                log.error(f"Error in watch party reminder checker: {e}")
                await asyncio.sleep(60)
    
    async def _send_watchparty_reminder(self, guild, party, time_text):
        """Send a reminder about an upcoming watch party"""
        # Get the channel
        channel_id = party.get("channel_id")
        if not channel_id:
            return
            
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        
        # Create mention list of participants
        participants = []
        for user_id in party.get("participants", []):
            user = guild.get_member(user_id)
            if user:
                participants.append(user.mention)
        
        if not participants:
            return
        
        # Create the reminder message
        reminder = f"⏰ **WATCH PARTY REMINDER** ⏰\n\nAttention {', '.join(participants[:15])}{'... and others' if len(participants) > 15 else ''}!\n\nThe watch party for **{party.get('anime_title')}** is starting in **{time_text}**!\n\nDate: {party.get('date')}\nTime: {party.get('time')}"
        
        if party.get("description"):
            reminder += f"\n\nNotes: {party.get('description')}"
        
        # Add a unique ID to avoid sending duplicate reminders
        reminder_id = f"{party.get('id')}_{time_text.replace(' ', '_')}"
        
        # Check if this reminder has already been sent
        async with self.config.guild(guild).sent_reminders() as sent_reminders:
            if reminder_id in sent_reminders:
                return
            
            # Send the reminder
            try:
                await channel.send(reminder)
                
                # Mark as sent
                sent_reminders[reminder_id] = datetime.now().isoformat()
                
                # Clean up old reminder markers (over 48 hours)
                now = datetime.now()
                for rid in list(sent_reminders.keys()):
                    try:
                        sent_time = datetime.fromisoformat(sent_reminders[rid])
                        if (now - sent_time).total_seconds() > 172800:  # 48 hours
                            del sent_reminders[rid]
                    except (ValueError, KeyError):
                        continue
                        
            except Exception as e:
                log.error(f"Error sending watch party reminder: {e}")
                
    @commands.command()
    @commands.guild_only()
    async def watchlist(self, ctx, action: str = "show", *, anime_name: str = None):
        """Manage your personal anime watchlist
        
        Actions:
        - show: Display your watchlist (default)
        - add [anime_name]: Add an anime to your watchlist
        - remove [anime_name/id]: Remove an anime from your watchlist
        - clear: Clear your entire watchlist
        
        Examples:
        .watchlist show
        .watchlist add Solo Leveling
        .watchlist remove One Piece
        .watchlist remove id:21
        .watchlist clear
        """
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
            
        # Get user's watchlist
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        
        # Normalize action
        action = action.lower()
        
        try:
            if action == "show":
                # Display the user's watchlist
                watchlist = await self._get_user_watchlist(guild_id, user_id)
                
                if not watchlist:
                    return await ctx.send("Your watchlist is empty. Add anime with `.watchlist add [anime_name]`")
                
                # Create an embed to display the watchlist
                embed = discord.Embed(
                    title=f"{ctx.author.display_name}'s Anime Watchlist",
                    description=f"You have {len(watchlist)} anime in your watchlist",
                    color=discord.Color.blue()
                )
                
                # Add anime to the embed
                for i, anime in enumerate(watchlist[:15], 1):  # Limit to 15 entries
                    title = anime.get("title", "Unknown")
                    status = anime.get("status", "Unknown")
                    episodes = anime.get("episodes", "?")
                    
                    embed.add_field(
                        name=f"{i}. {title}",
                        value=f"Status: {status}\nEpisodes: {episodes}\nID: {anime.get('id')}\nAdded: {anime.get('added_on', 'Unknown')[:10]}",
                        inline=(i % 2 == 0)  # Alternate inline to create two columns
                    )
                
                # Add a footer with info if watchlist is longer than 15
                if len(watchlist) > 15:
                    embed.set_footer(text=f"Showing 15 of {len(watchlist)} anime. Use `.watchlist remove [name/id]` to manage your list.")
                
                # Send the embed
                await ctx.send(embed=embed)
                
            elif action == "add":
                # Check if anime name is provided
                if not anime_name:
                    return await ctx.send("Please provide an anime name to add to your watchlist.")
                
                # Search for the anime
                result = await self.mal_api.search_anime(anime_name)
                
                if not result:
                    return await ctx.send(f"Could not find anime matching '{anime_name}'.")
                
                # If multiple results, ask user to select one
                if len(result) > 1:
                    # Create a list of anime options
                    options = []
                    for i, anime_option in enumerate(result[:5], 1):  # Limit to top 5
                        title = anime_option.get('title', 'Unknown')
                        anime_type = anime_option.get('type', 'Unknown')
                        options.append(f"**{i}.** {title} - {anime_type}")
                    
                    options_msg = "**Multiple results found. Reply with the number you want to add:**\n" + "\n".join(options)
                    await ctx.send(options_msg)
                    
                    # Wait for user selection
                    try:
                        def check(m):
                            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= len(result[:5])
                        
                        selection_msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                        selection = int(selection_msg.content)
                        
                        # Get the selected anime
                        selected = result[selection-1]
                        anime_id = selected.get('id') or selected.get('mal_id')
                    except asyncio.TimeoutError:
                        return await ctx.send("Selection timed out. Please try again.")
                    except (ValueError, IndexError):
                        return await ctx.send("Invalid selection. Please try again.")
                else:
                    # Use the first result
                    anime_id = result[0].get('id') or result[0].get('mal_id')
                
                # Get detailed anime info
                anime = await self.mal_api.get_anime_details(anime_id)
                if not anime:
                    return await ctx.send("Error retrieving anime details.")
                
                # Add to watchlist
                success = await self._add_to_watchlist(guild_id, user_id, anime)
                
                if success:
                    await ctx.send(f"Added **{anime['title']}** to your watchlist!")
                else:
                    await ctx.send(f"**{anime['title']}** is already in your watchlist.")
                
            elif action == "remove":
                # Check if anime name/id is provided
                if not anime_name:
                    return await ctx.send("Please provide an anime name or ID to remove from your watchlist.")
                
                # Get current watchlist
                watchlist = await self._get_user_watchlist(guild_id, user_id)
                
                if not watchlist:
                    return await ctx.send("Your watchlist is empty.")
                
                # Check if removing by ID
                if anime_name.lower().startswith('id:'):
                    try:
                        anime_id = int(anime_name[3:].strip())
                        success = await self._remove_from_watchlist(guild_id, user_id, anime_id)
                        
                        if success:
                            return await ctx.send(f"Removed anime with ID **{anime_id}** from your watchlist.")
                        else:
                            return await ctx.send(f"Anime with ID **{anime_id}** not found in your watchlist.")
                    except ValueError:
                        return await ctx.send("Invalid ID format. Use 'id:12345' where 12345 is the anime ID.")
                
                # Search watchlist for matching anime name
                matches = []
                for i, anime in enumerate(watchlist):
                    if anime_name.lower() in anime.get("title", "").lower():
                        matches.append((i, anime))
                
                if not matches:
                    return await ctx.send(f"No anime matching '{anime_name}' found in your watchlist.")
                
                if len(matches) == 1:
                    # Only one match, remove it directly
                    idx, anime = matches[0]
                    success = await self._remove_from_watchlist(guild_id, user_id, anime.get("id"))
                    
                    if success:
                        await ctx.send(f"Removed **{anime.get('title')}** from your watchlist.")
                    else:
                        await ctx.send("Error removing anime from your watchlist.")
                else:
                    # Multiple matches, ask user to select
                    options = []
                    for i, (idx, anime) in enumerate(matches[:5], 1):
                        title = anime.get("title", "Unknown")
                        options.append(f"**{i}.** {title}")
                    
                    options_msg = "**Multiple matches found. Reply with the number you want to remove:**\n" + "\n".join(options)
                    await ctx.send(options_msg)
                    
                    # Wait for user selection
                    try:
                        def check(m):
                            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit() and 1 <= int(m.content) <= len(matches[:5])
                        
                        selection_msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                        selection = int(selection_msg.content)
                        
                        # Get the selected anime
                        idx, anime = matches[selection-1]
                        success = await self._remove_from_watchlist(guild_id, user_id, anime.get("id"))
                        
                        if success:
                            await ctx.send(f"Removed **{anime.get('title')}** from your watchlist.")
                        else:
                            await ctx.send("Error removing anime from your watchlist.")
                    except asyncio.TimeoutError:
                        await ctx.send("Selection timed out. Please try again.")
                    except (ValueError, IndexError):
                        await ctx.send("Invalid selection. Please try again.")
            
            elif action == "clear":
                # Clear the entire watchlist
                # First, ask for confirmation
                confirm_msg = await ctx.send("Are you sure you want to clear your entire watchlist? (yes/no)")
                
                # Wait for confirmation
                try:
                    pred = MessagePredicate.yes_or_no(ctx)
                    await self.bot.wait_for("message", check=pred, timeout=30)
                    if pred.result:
                        # Clear the watchlist
                        async with self.config.guild_from_id(guild_id).watchlists() as watchlists:
                            watchlists[str(user_id)] = []
                        await ctx.send("Your watchlist has been cleared.")
                    else:
                        await ctx.send("Operation cancelled.")
                except asyncio.TimeoutError:
                    await ctx.send("No response received, operation cancelled.")
            
            else:
                # Unknown action
                await ctx.send(f"Unknown action '{action}'. Use 'show', 'add', 'remove', or 'clear'.")
                
        except Exception as e:
            log.error(f"Error in watchlist command: {e}", exc_info=True)
            await ctx.send(f"An error occurred while managing your watchlist: {str(e)}")
        
    @commands.command()
    @commands.guild_only()
    async def schedule(self, ctx, day: str = None, *, anime_name: str = None):
        """View anime episode schedule
        
        Parameters:
        - day: Optional day of the week to filter (e.g., monday, tuesday)
        - anime_name: Optional anime name to search for
        
        Examples:
        .schedule                 - Show all anime for the week
        .schedule monday          - Show anime airing on Monday
        .schedule today           - Show anime airing today
        .schedule all one piece   - Search for One Piece in the full schedule
        .schedule monday spy      - Search for "spy" in Monday's schedule
        """
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        async with ctx.typing():
            try:
                # Handle the case where anime_name is provided but day is not
                if day and anime_name is None and day.lower() not in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today", "tomorrow", "all"]:
                    anime_name = day
                    day = "all"
                
                # Convert "today" to the actual day of the week
                if day and day.lower() == "today":
                    today = datetime.now().strftime("%A").lower()
                    day = today
                
                # Convert "tomorrow" to the actual day of the week
                if day and day.lower() == "tomorrow":
                    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%A").lower()
                    day = tomorrow
                
                # Get the anime schedule
                if day and day.lower() != "all":
                    schedule_data = await self.mal_api.get_anime_schedule(day.lower())
                else:
                    schedule_data = await self.mal_api.get_anime_schedule()
                
                if not schedule_data:
                    return await ctx.send("Failed to retrieve anime schedule data.")
                
                # Create pages for each day or filter by search term
                pages = []
                
                for weekday, anime_list in schedule_data.items():
                    # Skip if filtering by day and this isn't the right day
                    if day and day.lower() != "all" and weekday.lower() != day.lower():
                        continue
                    
                    # Filter by anime name if provided
                    filtered_list = anime_list
                    if anime_name:
                        filtered_list = [anime for anime in anime_list if anime_name.lower() in anime.get("title", "").lower()]
                        
                        # Skip this day if no matches after filtering
                        if not filtered_list:
                            continue
                    
                    # Create an embed for this day
                    embed = discord.Embed(
                        title=f"Anime Schedule - {weekday}",
                        description=f"Anime airing on {weekday}" + (f" matching '{anime_name}'" if anime_name else ""),
                        color=discord.Color.blue()
                    )
                    
                    # Add anime to the embed
                    for i, anime in enumerate(filtered_list[:15], 1):  # Limit to 15 entries
                        title = anime.get("title", "Unknown")
                        time = anime.get("time", "Unknown time")
                        episodes = anime.get("episodes", "?")
                        score = anime.get("score", "N/A")
                        
                        embed.add_field(
                            name=f"{i}. {title}",
                            value=f"Time: {time}\nEpisodes: {episodes}\nScore: {score}\n[MAL Link]({anime.get('url', '#')})",
                            inline=(i % 2 == 0)  # Alternate inline to create two columns
                        )
                    
                    # Add a footer with info
                    embed.set_footer(text=f"Found {len(filtered_list)} anime for {weekday}" + 
                                        (" matching search" if anime_name else "") + 
                                        (f". Showing 15 of {len(filtered_list)}." if len(filtered_list) > 15 else "."))
                    
                    # Add this embed to pages
                    pages.append(embed)
                
                # Check if we have any results
                if not pages:
                    if anime_name:
                        return await ctx.send(f"No anime matching '{anime_name}' found in the schedule" +
                                            (f" for {day}" if day and day.lower() != "all" else "") + ".")
                    else:
                        return await ctx.send("No schedule data available" +
                                            (f" for {day}" if day and day.lower() != "all" else "") + ".")
                
                # Send the embeds
                if len(pages) == 1:
                    # Only one page, send it directly
                    await ctx.send(embed=pages[0])
                else:
                    # Multiple pages, use a menu
                    msg = await ctx.send(embed=pages[0])
                    
                    # Add reactions for navigation
                    if len(pages) > 1:
                        await msg.add_reaction("⬅️")
                        await msg.add_reaction("➡️")
                    
                    # Current page index
                    current_page = 0
                    
                    def check(reaction, user):
                        return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == msg.id
                    
                    # Wait for reactions
                    while True:
                        try:
                            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
                            
                            if str(reaction.emoji) == "➡️" and current_page < len(pages) - 1:
                                current_page += 1
                                await msg.edit(embed=pages[current_page])
                            elif str(reaction.emoji) == "⬅️" and current_page > 0:
                                current_page -= 1
                                await msg.edit(embed=pages[current_page])
                            
                            # Remove the reaction
                            await msg.remove_reaction(reaction, user)
                            
                        except asyncio.TimeoutError:
                            # Stop listening for reactions
                            break
                        except Exception as e:
                            log.error(f"Error in schedule pagination: {e}")
                            break
                
            except Exception as e:
                log.error(f"Error in schedule command: {e}", exc_info=True)
                await ctx.send(f"An error occurred while retrieving the schedule: {str(e)}")
        
    @commands.command()
    @commands.guild_only()
    async def upcoming(self, ctx, *, query: str = None):
        """Show upcoming anime for next season
        
        Optionally filter results by providing a search query
        Example: .upcoming one piece
        """
        # Check rate limits
        can_proceed, message = await self.check_rate_limit(ctx)
        if not can_proceed:
            return await ctx.send(message)
        
        async with ctx.typing():
            try:
                # Get upcoming anime, optionally filtered by query
                upcoming_anime = await self.mal_api.get_upcoming_anime(15, query)
                
                if not upcoming_anime:
                    if query:
                        return await ctx.send(f"No upcoming anime found matching '{query}'.")
                    else:
                        return await ctx.send("No upcoming anime information available.")
                
                # Create an embed to display the results
                embed = discord.Embed(
                    title=f"Upcoming Anime{' - ' + query if query else ''}",
                    description="Anime scheduled for the next season",
                    color=discord.Color.blue()
                )
                
                # Add anime to the embed
                for i, anime in enumerate(upcoming_anime[:10], 1):  # Limit to 10 entries
                    title = anime.get("title", "Unknown")
                    airing_start = anime.get("airing_start", "TBA")
                    if airing_start and isinstance(airing_start, str) and len(airing_start) >= 10:
                        airing_start = airing_start[:10]  # Only show the date part
                    
                    episodes = anime.get("episodes", "?")
                    anime_type = anime.get("type", "TV")
                    
                    embed.add_field(
                        name=f"{i}. {title}",
                        value=f"Type: {anime_type}\nEpisodes: {episodes}\nStart Date: {airing_start}\n[MAL Link]({anime.get('url', '#')})",
                        inline=False
                    )
                
                # Add a footer with info
                embed.set_footer(text=f"Found {len(upcoming_anime)} upcoming anime. Showing top 10.")
                
                # Send the embed
                await ctx.send(embed=embed)
                
            except Exception as e:
                log.error(f"Error showing upcoming season: {e}", exc_info=True)
                await ctx.send(f"Error showing upcoming season: {str(e)}")
                
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
        if message.author.bot or not message.guild:
            return
            
        # Skip mention response in specific channels
        excluded_channels = [425068612542398476]  # Replace with your general channel IDs
        if message.channel.id in excluded_channels:
            return
            
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
