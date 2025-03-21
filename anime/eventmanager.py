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
            
    async def check_airing_notifications(self, guild):
        """Check for anime episodes that have aired and notify"""
        settings = await self.config.guild(guild).all()
        events_data = settings.get("events", {})
        
        # Skip if notifications are disabled
        if not settings.get("notifications", {}).get("new_episodes", True):
            return
            
        # Get anime IDs to check
        anime_ids = events_data.get("airing_notifications", [])
        if not anime_ids:
            return
            
        # Check if enough time has passed since last check (at least 30 minutes)
        last_check = events_data.get("last_check", 0)
        if time.time() - last_check < 1800:
            return
            
        # Find forum category
        category_name = settings.get("forums_category_name", "Anime Forums")
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            return
            
        # Get current schedule from API
        try:
            current_day = datetime.now().weekday()
            # Map to Jikan's format (0 = Sunday, 6 = Saturday)
            jikan_day = (current_day + 1) % 7
            jikan_days = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
            
            schedule = await self.mal_api.get_anime_schedule(jikan_days[jikan_day])
            
            # No schedule data for today
            if not schedule:
                return
                
            # Get today's schedule
            today_schedule = schedule.get(jikan_days[jikan_day].capitalize(), [])
            
            # Filter to get only the anime we're tracking
            for anime in today_schedule:
                anime = anime_results[0]
            anime_id = anime.get("id") or anime.get("mal_id")
            anime_title = anime.get("title")
            
            if not anime_id:
                return await ctx.send("Could not find a valid anime ID.")
                
            # Remove from watching list
            removed = False
            async with self.config.guild(ctx.guild).events() as events:
                if "watching" in events and str(anime_id) in events["watching"]:
                    if user_id in events["watching"][str(anime_id)]:
                        events["watching"][str(anime_id)].remove(user_id)
                        removed = True
                        
                    # If no one is watching, remove from airing notifications
                    if not events["watching"][str(anime_id)] and "airing_notifications" in events:
                        if anime_id in events["airing_notifications"]:
                            events["airing_notifications"].remove(anime_id)
                    
            # Confirmation message
            if removed:
                await ctx.send(f"Removed from watching list: **{anime_title}**")
            else:
                await ctx.send(f"You were not watching **{anime_title}**.")
                
            return True
            
        except Exception as e:
            log.error(f"Error removing from watching list: {e}")
            await ctx.send(f"Error removing from watching list: {e}")
            return False
            
    async def show_upcoming_season(self, ctx):
        """Show information about the upcoming anime season"""
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        async with ctx.typing():
            try:
                # Get upcoming anime
                upcoming_anime = await self.mal_api.get_upcoming_anime(limit=15)
                
                if not upcoming_anime:
                    return await ctx.send("Could not fetch upcoming anime information.")
                    
                # Get current season info to determine next season
                current_season = await self.mal_api._make_jikan_request("seasons/now", {"limit": 1})
                if not current_season or "data" not in current_season or not current_season["data"]:
                    return await ctx.send("Could not determine current anime season.")
                    
                # Extract current season and year
                sample_anime = current_season["data"][0]
                current_year = int(sample_anime.get("year", datetime.now().year))
                current_season_name = sample_anime.get("season", "").lower()
                
                # Calculate next season
                seasons = ["winter", "spring", "summer", "fall"]
                current_idx = seasons.index(current_season_name) if current_season_name in seasons else 0
                next_idx = (current_idx + 1) % 4
                next_season = seasons[next_idx]
                next_year = current_year + 1 if next_idx == 0 else current_year
                
                # Create embed
                embed = discord.Embed(
                    title=f"Upcoming Anime: {next_season.capitalize()} {next_year}",
                    description=f"Here are some anime to look forward to in the upcoming season:",
                    color=discord.Color.gold()
                )
                
                # Add anime to embed
                for i, anime in enumerate(upcoming_anime[:10]):
                    # Format the description
                    synopsis = anime.get("synopsis", "No synopsis available.")
                    if synopsis and len(synopsis) > 100:
                        synopsis = synopsis[:97] + "..."
                        
                    # Format genres
                    genres = ", ".join(anime.get("genres", [])[:3])
                    genres_str = f"\nGenres: {genres}" if genres else ""
                    
                    # Format airing date
                    airing_start = anime.get("airing_start", "TBA")
                    if airing_start and airing_start != "TBA":
                        try:
                            airing_date = datetime.fromisoformat(airing_start.replace("Z", "+00:00"))
                            airing_start = airing_date.strftime("%B %d, %Y")
                        except:
                            pass
                    
                    # Add field
                    embed.add_field(
                        name=f"{i+1}. {anime.get('title')}",
                        value=f"Airing: {airing_start}\nEpisodes: {anime.get('episodes', 'TBA')}{genres_str}\n{synopsis}",
                        inline=False
                    )
                
                # Add thumbnail
                if upcoming_anime[0].get("image_url"):
                    embed.set_thumbnail(url=upcoming_anime[0]["image_url"])
                
                # Add footer
                embed.set_footer(text=f"Use `.seasonal` to create forum channels when the season starts!")
                
                # Send the embed
                await ctx.send(embed=embed)
                
                # Ask if they want to schedule a notification
                confirm_msg = await ctx.send(f"Would you like to schedule a notification when the {next_season.capitalize()} {next_year} season starts? (y/n)")
                
                # Wait for confirmation
                try:
                    pred = MessagePredicate.yes_or_no(ctx)
                    await self.bot.wait_for("message", check=pred, timeout=30)
                    if pred.result:
                        # Schedule notification
                        await self.schedule_season_notification(ctx, next_season, next_year)
                    else:
                        await ctx.send("Season notification not scheduled.")
                except asyncio.TimeoutError:
                    await ctx.send("No response received, notification not scheduled.")
                
                return True
                
            except Exception as e:
                log.error(f"Error showing upcoming season: {e}")
                await ctx.send(f"Error showing upcoming season: {e}")
                return False
                
    def _parse_time_string(self, time_str: str) -> Optional[datetime]:
        """Parse a time string into a datetime object"""
        try:
            time_str = time_str.lower().strip()
            now = datetime.now()
            
            # Handle relative times (e.g., "2h30m")
            if any(unit in time_str for unit in ["h", "m", "d", "w"]):
                total_seconds = 0
                
                # Extract days
                if "d" in time_str:
                    days_match = re.search(r'(\d+)d', time_str)
                    if days_match:
                        total_seconds += int(days_match.group(1)) * 86400
                
                # Extract weeks
                if "w" in time_str:
                    weeks_match = re.search(r'(\d+)w', time_str)
                    if weeks_match:
                        total_seconds += int(weeks_match.group(1)) * 604800
                
                # Extract hours
                if "h" in time_str:
                    hours_match = re.search(r'(\d+)h', time_str)
                    if hours_match:
                        total_seconds += int(hours_match.group(1)) * 3600
                
                # Extract minutes
                if "m" in time_str:
                    minutes_match = re.search(r'(\d+)m', time_str)
                    if minutes_match:
                        total_seconds += int(minutes_match.group(1)) * 60
                
                if total_seconds > 0:
                    return now + timedelta(seconds=total_seconds)
            
            # Handle "tomorrow" and common time formats
            if "tomorrow" in time_str:
                tomorrow = now + timedelta(days=1)
                time_part = time_str.replace("tomorrow", "").strip()
                
                if not time_part:
                    # Default to noon tomorrow if no time specified
                    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 12, 0)
                
                # Try to parse the time part
                if ":" in time_part:
                    # Format like "3:30pm"
                    time_match = re.search(r'(\d+):(\d+)\s*(am|pm)?', time_part)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2))
                        am_pm = time_match.group(3)
                        
                        if am_pm and am_pm.lower() == "pm" and hour < 12:
                            hour += 12
                        elif am_pm and am_pm.lower() == "am" and hour == 12:
                            hour = 0
                            
                        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute)
                else:
                    # Format like "3pm"
                    time_match = re.search(r'(\d+)\s*(am|pm)', time_part)
                    if time_match:
                        hour = int(time_match.group(1))
                        am_pm = time_match.group(2)
                        
                        if am_pm.lower() == "pm" and hour < 12:
                            hour += 12
                        elif am_pm.lower() == "am" and hour == 12:
                            hour = 0
                            
                        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, 0)
            
            # Handle specific date/time formats
            try:
                # Try parsing with datetime
                for fmt in ["%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y/%m/%d %H:%M"]:
                    try:
                        return datetime.strptime(time_str, fmt)
                    except ValueError:
                        continue
            except:
                pass
                
            # Could not parse the time string
            return None
            
        except Exception as e:
            log.error(f"Error parsing time string: {e}")
            return None
            
    async def get_watching_list(self, ctx, user_id=None):
        """Get the list of anime a user is watching"""
        if not user_id:
            user_id = ctx.author.id
            
        try:
            # Get watching data
            events_data = await self.config.guild(ctx.guild).events()
            watching_data = events_data.get("watching", {})
            
            # Find all anime IDs the user is watching
            watching_anime_ids = []
            for anime_id, watchers in watching_data.items():
                if user_id in watchers:
                    watching_anime_ids.append(anime_id)
                    
            if not watching_anime_ids:
                return await ctx.send("You are not watching any anime.")
                
            # Get anime details for each ID
            watching_anime = []
            for anime_id in watching_anime_ids:
                try:
                    anime_details = await self.mal_api.get_anime_details(int(anime_id))
                    if anime_details:
                        watching_anime.append(anime_details)
                except:
                    continue
                    
            if not watching_anime:
                return await ctx.send("Could not retrieve details for your watching list.")
                
            # Create embed
            embed = discord.Embed(
                title="Your Watching List",
                description=f"You're currently watching {len(watching_anime)} anime series.",
                color=discord.Color.blue()
            )
            
            # Add anime to embed
            for anime in watching_anime:
                status = ""
                if anime.get("airing"):
                    status = "🟢 Currently Airing"
                elif anime.get("status") == "Finished Airing":
                    status = "🔵 Finished Airing"
                else:
                    status = "⚪ Not Yet Aired"
                    
                value = f"{status}\nEpisodes: {anime.get('episodes', '?')}"
                if anime.get("url"):
                    value += f"\n[MyAnimeList]({anime.get('url')})"
                    
                embed.add_field(
                    name=anime.get("title"),
                    value=value,
                    inline=True
                )
                
            # Send the embed
            await ctx.send(embed=embed)
            
            return True
            
        except Exception as e:
            log.error(f"Error getting watching list: {e}")
            await ctx.send(f"Error retrieving watching list: {e}")
            return False
            
    async def list_scheduled_events(self, ctx):
        """List all scheduled events for the server"""
        try:
            # Get events data
            events_data = await self.config.guild(ctx.guild).events()
            scheduled_events = events_data.get("scheduled_events", {})
            
            if not scheduled_events:
                return await ctx.send("No events are currently scheduled.")
                
            # Create embed
            embed = discord.Embed(
                title="Scheduled Events",
                description=f"There are {len(scheduled_events)} events scheduled.",
                color=discord.Color.purple()
            )
            
            # Group events by type
            events_by_type = {}
            for event_id, event in scheduled_events.items():
                event_type = event.get("type", "unknown")
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)
                
            # Add events to embed by type
            for event_type, events in events_by_type.items():
                # Sort events by time
                events.sort(key=lambda e: e.get("time", 0))
                
                # Format events
                events_text = ""
                for event in events[:5]:  # Limit to 5 per type
                    event_time = event.get("time", 0)
                    time_str = format_relative_time(event_time)
                    
                    if event_type == "watchparty":
                        events_text += f"• **{event.get('title')}** Episode {event.get('episode', '?')} - {time_str}\n"
                    elif event_type == "season_start":
                        season = event.get("season", "").capitalize()
                        year = event.get("year", "")
                        events_text += f"• **{season} {year}** Season Start - {time_str}\n"
                    elif event_type == "anime_reminder":
                        events_text += f"• **{event.get('title', 'Anime Reminder')}** - {time_str}\n"
                    else:
                        events_text += f"• **Unknown Event** - {time_str}\n"
                        
                # Add field for this event type
                if events_text:
                    embed.add_field(
                        name=f"{event_type.capitalize()} Events",
                        value=events_text,
                        inline=False
                    )
                    
            # Add footer
            embed.set_footer(text="Use `.events cancel [event_id]` to cancel an event.")
            
            # Send the embed
            await ctx.send(embed=embed)
            
            return True
            
        except Exception as e:
            log.error(f"Error listing scheduled events: {e}")
            await ctx.send(f"Error listing scheduled events: {e}")
            return False
            
    async def cancel_event(self, ctx, event_id):
        """Cancel a scheduled event"""
        try:
            # Get events data
            async with self.config.guild(ctx.guild).events() as events:
                scheduled_events = events.get("scheduled_events", {})
                
                # Check if event exists
                if event_id not in scheduled_events:
                    return await ctx.send(f"Event with ID {event_id} not found.")
                    
                # Check permissions (admin or event creator)
                event = scheduled_events[event_id]
                created_by = event.get("created_by")
                
                if not await ctx.bot.is_admin(ctx.author) and ctx.author.id != created_by:
                    return await ctx.send("You don't have permission to cancel this event.")
                    
                # Cancel the event
                del scheduled_events[event_id]
                
            # Confirmation message
            await ctx.send(f"Event {event_id} has been cancelled.")
            
            return True
            
        except Exception as e:
            log.error(f"Error cancelling event: {e}")
            await ctx.send(f"Error cancelling event: {e}")
            return False
                    if anime_id in anime_ids:
                    # Find matching forum
                    anime_title = anime.get("title")
                    if not anime_title:
                        continue
                        
                    forum_channel = discord.utils.find(
                        lambda c: c.name.lower() == anime_title.lower().replace(" ", "-") and 
                                  isinstance(c, discord.ForumChannel) and
                                  c.category_id == category.id,
                        guild.channels
                    )
                    
                    if not forum_channel:
                        continue
                        
                    # Create an episode discussion thread
                    episode_num = self._estimate_current_episode(anime)
                    
                    # Check if we already have a thread for this episode
                    thread_name = f"Episode {episode_num} Discussion"
                    existing_thread = discord.utils.find(
                        lambda t: t.name.lower() == thread_name.lower() and t.parent_id == forum_channel.id,
                        guild.threads
                    )
                    
                    if existing_thread:
                        continue  # Skip if thread already exists
                        
                    # Create new thread
                    try:
                        # Find Discussion tag
                        discussion_tag = discord.utils.find(
                            lambda t: t.name == "Discussion", 
                            forum_channel.available_tags
                        )
                        
                        tags = [discussion_tag] if discussion_tag else []
                        
                        thread = await forum_channel.create_thread(
                            name=thread_name,
                            content=(
                                f"# Episode {episode_num} Discussion\n\n"
                                f"This thread is for discussing episode {episode_num} of **{anime_title}**.\n\n"
                                f"**Please keep spoilers about future episodes out of this thread!**\n\n"
                                f"Use Discord's spoiler tags `||like this||` for content from the episode that might be considered spoilers."
                            ),
                            applied_tags=tags
                        )
                        
                        # Ping users who are watching this anime
                        watchers = events_data.get("watching", {}).get(str(anime_id), [])
                        if watchers:
                            mentions = " ".join(f"<@{user_id}>" for user_id in watchers)
                            await thread.send(
                                f"New episode alert! {mentions}\n"
                                f"Episode {episode_num} of **{anime_title}** is now available!"
                            )
                            
                    except Exception as e:
                        log.error(f"Error creating episode thread: {e}")
                    
        except Exception as e:
            log.error(f"Error checking airing notifications: {e}")
            
    def _estimate_current_episode(self, anime_data):
        """Estimate the current episode number based on air date"""
        try:
            # Start with a default if we can't calculate
            if not anime_data.get("aired", {}).get("from"):
                return "New"
                
            # Parse the start date
            start_date_str = anime_data.get("aired", {}).get("from")
            start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            
            # Calculate weeks since start
            now = datetime.now(start_date.tzinfo)
            days_since_start = (now - start_date).days
            
            # Most anime air weekly, so estimate the episode number
            episode_number = (days_since_start // 7) + 1
            
            # Cap at total episodes if known
            total_episodes = anime_data.get("episodes")
            if total_episodes and episode_number > total_episodes:
                episode_number = total_episodes
                
            return episode_number
            
        except Exception:
            # If anything goes wrong, just return "New"
            return "New"
            
    async def check_scheduled_events(self, guild):
        """Check for and process scheduled events"""
        settings = await self.config.guild(guild).all()
        events_data = settings.get("events", {})
        
        # Get scheduled events
        scheduled_events = events_data.get("scheduled_events", {})
        if not scheduled_events:
            return
            
        # Current time
        current_time = time.time()
        
        # Find events that are due
        events_to_remove = []
        for event_id, event in scheduled_events.items():
            event_time = event.get("time", 0)
            
            if current_time >= event_time:
                # Process the event
                await self._process_event(guild, event)
                events_to_remove.append(event_id)
                
        # Remove processed events
        if events_to_remove:
            async with self.config.guild(guild).events() as events:
                for event_id in events_to_remove:
                    if event_id in events["scheduled_events"]:
                        del events["scheduled_events"][event_id]
                        
    async def _process_event(self, guild, event):
        """Process a single scheduled event"""
        event_type = event.get("type")
        
        if event_type == "watchparty":
            await self._process_watchparty_event(guild, event)
        elif event_type == "season_start":
            await self._process_season_start_event(guild, event)
        elif event_type == "anime_reminder":
            await self._process_anime_reminder_event(guild, event)
            
    async def _process_watchparty_event(self, guild, event):
        """Process a watch party event"""
        try:
            channel_id = event.get("channel_id")
            anime_id = event.get("anime_id")
            episode = event.get("episode", 1)
            title = event.get("title", "Anime Watch Party")
            
            channel = guild.get_channel(channel_id)
            if not channel:
                return
                
            # Get anime details if we have the ID
            anime_details = None
            if anime_id and self.mal_api:
                anime_details = await self.mal_api.get_anime_details(anime_id)
                
            # Create embed for the watch party
            embed = discord.Embed(
                title=f"🎬 Watch Party: {title}",
                description=f"The scheduled watch party is starting now!",
                color=discord.Color.purple()
            )
            
            if anime_details:
                embed.add_field(name="Anime", value=anime_details.get("title"), inline=True)
                embed.add_field(name="Episode", value=str(episode), inline=True)
                
                if anime_details.get("image_url"):
                    embed.set_thumbnail(url=anime_details["image_url"])
                    
            # Role mention if specified
            role_id = event.get("role_id")
            content = None
            if role_id:
                role = guild.get_role(role_id)
                if role:
                    content = f"{role.mention} The watch party is starting!"
                    
            # Send the notification
            await channel.send(content=content, embed=embed)
            
        except Exception as e:
            log.error(f"Error processing watch party event: {e}")
            
    async def _process_season_start_event(self, guild, event):
        """Process a new anime season start event"""
        try:
            channel_id = event.get("channel_id")
            season = event.get("season", "")
            year = event.get("year", datetime.now().year)
            
            channel = guild.get_channel(channel_id)
            if not channel:
                return
                
            # Get the seasonal anime
            seasonal_anime = []
            if self.mal_api:
                seasonal_anime = await self.mal_api.get_seasonal_anime(year, season, limit=20)
                
            if not seasonal_anime:
                await channel.send(f"The {season.capitalize()} {year} anime season is starting, but we couldn't fetch the anime list.")
                return
                
            # Create an embed with the season info
            embed = discord.Embed(
                title=f"🌸 {season.capitalize()} {year} Anime Season",
                description=f"The new anime season is starting! Here are some highlights:",
                color=discord.Color.gold()
            )
            
            # Add top anime as fields
            for i, anime in enumerate(seasonal_anime[:10]):  # Top 10
                embed.add_field(
                    name=f"{i+1}. {anime.get('title')}",
                    value=f"Episodes: {anime.get('episodes', '?')} | Score: {anime.get('score', 'N/A')}\n{anime.get('synopsis', '')[:100]}{'...' if anime.get('synopsis', '') and len(anime.get('synopsis', '')) > 100 else ''}",
                    inline=False
                )
                
            # Add a footer with a link to create forums
            embed.set_footer(text="Use `.seasonal` to create forum channels for this season's anime!")
            
            # Send the notification
            await channel.send(embed=embed)
            
        except Exception as e:
            log.error(f"Error processing season start event: {e}")
            
    async def _process_anime_reminder_event(self, guild, event):
        """Process an anime reminder event"""
        try:
            channel_id = event.get("channel_id")
            anime_id = event.get("anime_id")
            message = event.get("message", "Reminder for your anime!")
            
            channel = guild.get_channel(channel_id)
            if not channel or not anime_id:
                return
                
            # Get anime details
            anime_details = None
            if self.mal_api:
                anime_details = await self.mal_api.get_anime_details(anime_id)
                
            if not anime_details:
                await channel.send(message)
                return
                
            # Create an embed with the anime info
            embed = discord.Embed(
                title=f"📌 Anime Reminder: {anime_details.get('title')}",
                description=message,
                color=discord.Color.blue()
            )
            
            if anime_details.get("image_url"):
                embed.set_thumbnail(url=anime_details["image_url"])
                
            # Add anime details
            if anime_details.get("episodes"):
                embed.add_field(name="Episodes", value=str(anime_details["episodes"]), inline=True)
            if anime_details.get("score"):
                embed.add_field(name="Score", value=f"{anime_details['score']}/10", inline=True)
            if anime_details.get("status"):
                embed.add_field(name="Status", value=anime_details["status"], inline=True)
                
            # Add link to anime
            if anime_details.get("url"):
                embed.add_field(name="MyAnimeList", value=f"[View page]({anime_details['url']})", inline=False)
                
            # User mentions if specified
            user_ids = event.get("user_ids", [])
            content = None
            if user_ids:
                mentions = " ".join(f"<@{user_id}>" for user_id in user_ids)
                content = f"{mentions} Here's your anime reminder!"
                
            # Send the notification
            await channel.send(content=content, embed=embed)
            
        except Exception as e:
            log.error(f"Error processing anime reminder event: {e}")
            
    async def schedule_watchparty(self, ctx, anime_name, time_str, episode=1, role_id=None):
        """Schedule a watch party event"""
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        try:
            # Parse the time
            when = self._parse_time_string(time_str)
            if not when:
                return await ctx.send("Invalid time format. Please use a format like '2h30m' or 'tomorrow 8pm'.")
                
            # Search for the anime
            anime_results = await self.mal_api.search_anime(anime_name)
            if not anime_results:
                return await ctx.send(f"Could not find anime matching '{anime_name}'.")
                
            anime = anime_results[0]
            anime_id = anime.get("id") or anime.get("mal_id")
            anime_title = anime.get("title")
            
            # Create event data
            event_id = f"watchparty_{ctx.guild.id}_{anime_id}_{int(time.time())}"
            event_data = {
                "type": "watchparty",
                "anime_id": anime_id,
                "title": anime_title,
                "episode": episode,
                "time": when.timestamp(),
                "channel_id": ctx.channel.id,
                "created_by": ctx.author.id,
                "role_id": role_id
            }
            
            # Save to config
            async with self.config.guild(ctx.guild).events() as events:
                if "scheduled_events" not in events:
                    events["scheduled_events"] = {}
                    
                events["scheduled_events"][event_id] = event_data
                
            # Format time for confirmation message
            time_until = format_relative_time(when)
            
            # Confirmation message
            await ctx.send(
                f"Watch party scheduled for **{anime_title}** Episode {episode}!\n"
                f"The watch party will start {time_until}."
            )
            
            return True
            
        except Exception as e:
            log.error(f"Error scheduling watch party: {e}")
            await ctx.send(f"Error scheduling watch party: {e}")
            return False
            
    async def schedule_season_notification(self, ctx, season, year=None, channel_id=None):
        """Schedule a notification for the start of a new anime season"""
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        try:
            # Validate season
            valid_seasons = ["winter", "spring", "summer", "fall"]
            season = season.lower()
            if season not in valid_seasons:
                return await ctx.send(f"Invalid season. Please use one of: {', '.join(valid_seasons)}")
                
            # Use current year if not specified
            if not year:
                year = datetime.now().year
            else:
                year = int(year)
                
            # Use current channel if not specified
            if not channel_id:
                channel_id = ctx.channel.id
                
            # Determine start date for the season
            season_starts = {
                "winter": (year, 1, 1),   # January 1
                "spring": (year, 4, 1),   # April 1
                "summer": (year, 7, 1),   # July 1
                "fall": (year, 10, 1)     # October 1
            }
            
            start_date = datetime(*season_starts[season])
            
            # If the date is in the past, notify user
            now = datetime.now()
            if start_date < now:
                return await ctx.send(f"The {season} {year} season has already started.")
                
            # Create event data
            event_id = f"season_{ctx.guild.id}_{season}_{year}_{int(time.time())}"
            event_data = {
                "type": "season_start",
                "season": season,
                "year": year,
                "time": start_date.timestamp(),
                "channel_id": channel_id,
                "created_by": ctx.author.id
            }
            
            # Save to config
            async with self.config.guild(ctx.guild).events() as events:
                if "scheduled_events" not in events:
                    events["scheduled_events"] = {}
                    
                events["scheduled_events"][event_id] = event_data
                
            # Format time for confirmation message
            time_until = format_relative_time(start_date)
            
            # Confirmation message
            await ctx.send(
                f"Notification scheduled for the start of the **{season.capitalize()} {year}** anime season!\n"
                f"The notification will be sent {time_until}."
            )
            
            return True
            
        except Exception as e:
            log.error(f"Error scheduling season notification: {e}")
            await ctx.send(f"Error scheduling season notification: {e}")
            return False
    
    async def watch_anime(self, ctx, anime_name, user_id=None):
        """Add a user to the watching list for an anime"""
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        try:
            # Default to command author if no user specified
            if not user_id:
                user_id = ctx.author.id
                
            # Search for the anime
            anime_results = await self.mal_api.search_anime(anime_name)
            if not anime_results:
                return await ctx.send(f"Could not find anime matching '{anime_name}'.")
                
            anime = anime_results[0]
            anime_id = anime.get("id") or anime.get("mal_id")
            anime_title = anime.get("title")
            
            if not anime_id:
                return await ctx.send("Could not find a valid anime ID.")
                
            # Add to watching list
            async with self.config.guild(ctx.guild).events() as events:
                if "watching" not in events:
                    events["watching"] = {}
                    
                if str(anime_id) not in events["watching"]:
                    events["watching"][str(anime_id)] = []
                    
                if user_id not in events["watching"][str(anime_id)]:
                    events["watching"][str(anime_id)].append(user_id)
                    
                # Also add to airing notifications if it's currently airing
                if anime.get("airing") and "airing_notifications" not in events:
                    events["airing_notifications"] = []
                    
                if anime.get("airing") and anime_id not in events["airing_notifications"]:
                    events["airing_notifications"].append(anime_id)
                    
            # Confirmation message
            await ctx.send(
                f"Added to watching list: **{anime_title}**\n"
                f"You'll receive notifications for new episodes in the relevant forum channel."
            )
            
            return True
            
        except Exception as e:
            log.error(f"Error adding to watching list: {e}")
            await ctx.send(f"Error adding to watching list: {e}")
            return False
            
    async def unwatch_anime(self, ctx, anime_name, user_id=None):
        """Remove a user from the watching list for an anime"""
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        try:
            # Default to command author if no user specified
            if not user_id:
                user_id = ctx.author.id
                
            # Search for the anime
            anime_results = await self.mal_api.search_anime(anime_name)
            if not anime_results:
                return await ctx.send(f"Could not find anime matching '{anime_name}'.")
                
            anime = anime_results[0]
            anime_id = anime.get("id") or anime.get("mal_id")
            anime_title = anime.get("title")
            
            if not anime_id:
                return await ctx.send("Could not find a valid anime ID.")
                
            # Remove from watching list
            removed = False
            async with self.config.guild(ctx.guild).events() as events:
                if "watching" in events and str(anime_id) in events["watching"]:
                    if user_id in events["watching"][str(anime_id)]:
                        events["watching"][str(anime_id)].remove(user_id)
                        removed = True
                        
                    # If no one is watching, remove from airing notifications
                    if not events["watching"][str(anime_id)] and "airing_notifications" in events:
                        if anime_id in events["airing_notifications"]:
                            events["airing_notifications"].remove(anime_id)
                    
            # Confirmation message
            if removed:
                await ctx.send(f"Removed from watching list: **{anime_title}**")
            else:
                await ctx.send(f"You were not watching **{anime_title}**.")
                
            return True
            
        except Exception as e:
            log.error(f"Error removing from watching list: {e}")
            await ctx.send(f"Error removing from watching list: {e}")
            return False
            
    async def show_upcoming_season(self, ctx):
        """Show information about the upcoming anime season"""
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        async with ctx.typing():
            try:
                # Get upcoming anime
                upcoming_anime = await self.mal_api.get_upcoming_anime(limit=15)
                
                if not upcoming_anime:
                    return await ctx.send("Could not fetch upcoming anime information.")
                    
                # Get current season info to determine next season
                current_season = await self.mal_api._make_jikan_request("seasons/now", {"limit": 1})
                if not current_season or "data" not in current_season or not current_season["data"]:
                    return await ctx.send("Could not determine current anime season.")
                    
                # Extract current season and year
                sample_anime = current_season["data"][0]
                current_year = int(sample_anime.get("year", datetime.now().year))
                current_season_name = sample_anime.get("season", "").lower()
                
                # Calculate next season
                seasons = ["winter", "spring", "summer", "fall"]
                current_idx = seasons.index(current_season_name) if current_season_name in seasons else 0
                next_idx = (current_idx + 1) % 4
                next_season = seasons[next_idx]
                next_year = current_year + 1 if next_idx == 0 else current_year
                
                # Create embed
                embed = discord.Embed(
                    title=f"Upcoming Anime: {next_season.capitalize()} {next_year}",
                    description=f"Here are some anime to look forward to in the upcoming season:",
                    color=discord.Color.gold()
                )
                
                # Add anime to embed
                for i, anime in enumerate(upcoming_anime[:10]):
                    # Format the description
                    synopsis = anime.get("synopsis", "No synopsis available.")
                    if synopsis and len(synopsis) > 100:
                        synopsis = synopsis[:97] + "..."
                        
                    # Format genres
                    genres = ", ".join(anime.get("genres", [])[:3])
                    genres_str = f"\nGenres: {genres}" if genres else ""
                    
                    # Format airing date
                    airing_start = anime.get("airing_start", "TBA")
                    if airing_start and airing_start != "TBA":
                        try:
                            airing_date = datetime.fromisoformat(airing_start.replace("Z", "+00:00"))
                            airing_start = airing_date.strftime("%B %d, %Y")
                        except:
                            pass
                    
                    # Add field
                    embed.add_field(
                        name=f"{i+1}. {anime.get('title')}",
                        value=f"Airing: {airing_start}\nEpisodes: {anime.get('episodes', 'TBA')}{genres_str}\n{synopsis}",
                        inline=False
                    )
                
                # Add thumbnail
                if upcoming_anime[0].get("image_url"):
                    embed.set_thumbnail(url=upcoming_anime[0]["image_url"])
                
                # Add footer
                embed.set_footer(text=f"Use `.seasonal` to create forum channels when the season starts!")
                
                # Send the embed
                await ctx.send(embed=embed)
                
                # Ask if they want to schedule a notification
                confirm_msg = await ctx.send(f"Would you like to schedule a notification when the {next_season.capitalize()} {next_year} season starts? (y/n)")
                
                # Wait for confirmation
                try:
                    pred = MessagePredicate.yes_or_no(ctx)
                    await self.bot.wait_for("message", check=pred, timeout=30)
                    if pred.result:
                        # Schedule notification
                        await self.schedule_season_notification(ctx, next_season, next_year)
                    else:
                        await ctx.send("Season notification not scheduled.")
                except asyncio.TimeoutError:
                    await ctx.send("No response received, notification not scheduled.")
                
                return True
                
            except Exception as e:
                log.error(f"Error showing upcoming season: {e}")
                await ctx.send(f"Error showing upcoming season: {e}")
                return False
                
    def _parse_time_string(self, time_str: str) -> Optional[datetime]:
        """Parse a time string into a datetime object"""
        try:
            time_str = time_str.lower().strip()
            now = datetime.now()
            
            # Handle relative times (e.g., "2h30m")
            if any(unit in time_str for unit in ["h", "m", "d", "w"]):
                total_seconds = 0
                
                # Extract days
                if "d" in time_str:
                    days_match = re.search(r'(\d+)d', time_str)
                    if days_match:
                        total_seconds += int(days_match.group(1)) * 86400
                
                # Extract weeks
                if "w" in time_str:
                    weeks_match = re.search(r'(\d+)w', time_str)
                    if weeks_match:
                        total_seconds += int(weeks_match.group(1)) * 604800
                
                # Extract hours
                if "h" in time_str:
                    hours_match = re.search(r'(\d+)h', time_str)
                    if hours_match:
                        total_seconds += int(hours_match.group(1)) * 3600
                
                # Extract minutes
                if "m" in time_str:
                    minutes_match = re.search(r'(\d+)m', time_str)
                    if minutes_match:
                        total_seconds += int(minutes_match.group(1)) * 60
                
                if total_seconds > 0:
                    return now + timedelta(seconds=total_seconds)
            
            # Handle "tomorrow" and common time formats
            if "tomorrow" in time_str:
                tomorrow = now + timedelta(days=1)
                time_part = time_str.replace("tomorrow", "").strip()
                
                if not time_part:
                    # Default to noon tomorrow if no time specified
                    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 12, 0)
                
                # Try to parse the time part
                if ":" in time_part:
                    # Format like "3:30pm"
                    time_match = re.search(r'(\d+):(\d+)\s*(am|pm)?', time_part)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2))
                        am_pm = time_match.group(3)
                        
                        if am_pm and am_pm.lower() == "pm" and hour < 12:
                            hour += 12
                        elif am_pm and am_pm.lower() == "am" and hour == 12:
                            hour = 0
                            
                        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute)
                else:
                    # Format like "3pm"
                    time_match = re.search(r'(\d+)\s*(am|pm)', time_part)
                    if time_match:
                        hour = int(time_match.group(1))
                        am_pm = time_match.group(2)
                        
                        if am_pm.lower() == "pm" and hour < 12:
                            hour += 12
                        elif am_pm.lower() == "am" and hour == 12:
                            hour = 0
                            
                        return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, 0)
            
            # Handle specific date/time formats
            try:
                # Try parsing with datetime
                for fmt in ["%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y/%m/%d %H:%M"]:
                    try:
                        return datetime.strptime(time_str, fmt)
                    except ValueError:
                        continue
            except:
                pass
                
            # Could not parse the time string
            return None
            
        except Exception as e:
            log.error(f"Error parsing time string: {e}")
            return None
            
    async def get_watching_list(self, ctx, user_id=None):
        """Get the list of anime a user is watching"""
        if not user_id:
            user_id = ctx.author.id
            
        try:
            # Get watching data
            events_data = await self.config.guild(ctx.guild).events()
            watching_data = events_data.get("watching", {})
            
            # Find all anime IDs the user is watching
            watching_anime_ids = []
            for anime_id, watchers in watching_data.items():
                if user_id in watchers:
                    watching_anime_ids.append(anime_id)
                    
            if not watching_anime_ids:
                return await ctx.send("You are not watching any anime.")
                
            # Get anime details for each ID
            watching_anime = []
            for anime_id in watching_anime_ids:
                try:
                    anime_details = await self.mal_api.get_anime_details(int(anime_id))
                    if anime_details:
                        watching_anime.append(anime_details)
                except:
                    continue
                    
            if not watching_anime:
                return await ctx.send("Could not retrieve details for your watching list.")
                
            # Create embed
            embed = discord.Embed(
                title="Your Watching List",
                description=f"You're currently watching {len(watching_anime)} anime series.",
                color=discord.Color.blue()
            )
            
            # Add anime to embed
            for anime in watching_anime:
                status = ""
                if anime.get("airing"):
                    status = "🟢 Currently Airing"
                elif anime.get("status") == "Finished Airing":
                    status = "🔵 Finished Airing"
                else:
                    status = "⚪ Not Yet Aired"
                    
                value = f"{status}\nEpisodes: {anime.get('episodes', '?')}"
                if anime.get("url"):
                    value += f"\n[MyAnimeList]({anime.get('url')})"
                    
                embed.add_field(
                    name=anime.get("title"),
                    value=value,
                    inline=True
                )
                
            # Send the embed
            await ctx.send(embed=embed)
            
            return True
            
        except Exception as e:
            log.error(f"Error getting watching list: {e}")
            await ctx.send(f"Error retrieving watching list: {e}")
            return False
            
    async def list_scheduled_events(self, ctx):
        """List all scheduled events for the server"""
        try:
            # Get events data
            events_data = await self.config.guild(ctx.guild).events()
            scheduled_events = events_data.get("scheduled_events", {})
            
            if not scheduled_events:
                return await ctx.send("No events are currently scheduled.")
                
            # Create embed
            embed = discord.Embed(
                title="Scheduled Events",
                description=f"There are {len(scheduled_events)} events scheduled.",
                color=discord.Color.purple()
            )
            
            # Group events by type
            events_by_type = {}
            for event_id, event in scheduled_events.items():
                event_type = event.get("type", "unknown")
                if event_type not in events_by_type:
                    events_by_type[event_type] = []
                events_by_type[event_type].append(event)
                
            # Add events to embed by type
            for event_type, events in events_by_type.items():
                # Sort events by time
                events.sort(key=lambda e: e.get("time", 0))
                
                # Format events
                events_text = ""
                for event in events[:5]:  # Limit to 5 per type
                    event_time = event.get("time", 0)
                    time_str = format_relative_time(event_time)
                    
                    if event_type == "watchparty":
                        events_text += f"• **{event.get('title')}** Episode {event.get('episode', '?')} - {time_str}\n"
                    elif event_type == "season_start":
                        season = event.get("season", "").capitalize()
                        year = event.get("year", "")
                        events_text += f"• **{season} {year}** Season Start - {time_str}\n"
                    elif event_type == "anime_reminder":
                        events_text += f"• **{event.get('title', 'Anime Reminder')}** - {time_str}\n"
                    else:
                        events_text += f"• **Unknown Event** - {time_str}\n"
                        
                # Add field for this event type
                if events_text:
                    embed.add_field(
                        name=f"{event_type.capitalize()} Events",
                        value=events_text,
                        inline=False
                    )
                    
            # Add footer
            embed.set_footer(text="Use `.events cancel [event_id]` to cancel an event.")
            
            # Send the embed
            await ctx.send(embed=embed)
            
            return True
            
        except Exception as e:
            log.error(f"Error listing scheduled events: {e}")
            await ctx.send(f"Error listing scheduled events: {e}")
            return False
            
    async def cancel_event(self, ctx, event_id):
        """Cancel a scheduled event"""
        try:
            # Get events data
            async with self.config.guild(ctx.guild).events() as events:
                scheduled_events = events.get("scheduled_events", {})
                
                # Check if event exists
                if event_id not in scheduled_events:
                    return await ctx.send(f"Event with ID {event_id} not found.")
                    
                # Check permissions (admin or event creator)
                event = scheduled_events[event_id]
                created_by = event.get("created_by")
                
                if not await ctx.bot.is_admin(ctx.author) and ctx.author.id != created_by:
                    return await ctx.send("You don't have permission to cancel this event.")
                    
                # Cancel the event
                del scheduled_events[event_id]
                
            # Confirmation message
            await ctx.send(f"Event {event_id} has been cancelled.")
            
            return True
            
        except Exception as e:
            log.error(f"Error cancelling event: {e}")
            await ctx.send(f"Error cancelling event: {e}")
            return False
