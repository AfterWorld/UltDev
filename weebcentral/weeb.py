import asyncio
import logging
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

log = logging.getLogger("red.mangadex")

class MangaDexAPI:
    """API wrapper for MangaDex"""
    
    def __init__(self):
        self.base_url = "https://api.mangadex.org"
        self.session = None
        self.rate_limit_reset = 0
        self.rate_limit_remaining = 0
    
    async def ensure_session(self):
        """Ensure an aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                "User-Agent": "Discord Bot/1.0 (MangaDex Tracker)"
            })
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def handle_rate_limits(self):
        """Handle API rate limits"""
        now = datetime.now().timestamp()
        if self.rate_limit_reset > now and self.rate_limit_remaining <= 0:
            sleep_time = self.rate_limit_reset - now + 0.5  # Add a small buffer
            if sleep_time > 0:
                log.info(f"Rate limited, sleeping for {sleep_time} seconds")
                await asyncio.sleep(sleep_time)
    
    async def make_request(self, endpoint, params=None):
        """Make a request to the MangaDex API"""
        await self.ensure_session()
        await self.handle_rate_limits()
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with self.session.get(url, params=params) as response:
                # Update rate limit info
                if "X-RateLimit-Remaining" in response.headers:
                    self.rate_limit_remaining = int(response.headers["X-RateLimit-Remaining"])
                if "X-RateLimit-Reset" in response.headers:
                    self.rate_limit_reset = int(response.headers["X-RateLimit-Reset"])
                
                # Check for rate limiting response
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After", 5)
                    log.warning(f"Rate limited, retrying after {retry_after} seconds")
                    await asyncio.sleep(int(retry_after))
                    return await self.make_request(endpoint, params)
                
                # Return the response
                if response.status == 200:
                    return await response.json()
                else:
                    log.error(f"API request failed with status {response.status}: {url}")
                    return None
        except Exception as e:
            log.error(f"Error making API request: {str(e)}")
            return None
    
    async def search_manga(self, title, limit=5, offset=0):
        """Search for manga by title"""
        params = {
            "title": title,
            "limit": limit,
            "offset": offset,
            "includes[]": ["cover_art", "author", "artist"],
            "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"]  # Include all ratings
        }
        
        response = await self.make_request("/manga", params)
        
        if not response or "data" not in response:
            return []
        
        # Format the results
        results = []
        for manga in response["data"]:
            manga_id = manga["id"]
            attributes = manga["attributes"]
            
            # Get title
            title = ""
            if "title" in attributes:
                title_dict = attributes["title"]
                # Try to get English title, fallback to first available
                title = (title_dict.get("en") or 
                        title_dict.get("jp") or 
                        title_dict.get("ja") or 
                        next(iter(title_dict.values())) if title_dict else "Unknown Title")
            
            # Get cover art
            cover_url = None
            for relationship in manga.get("relationships", []):
                if relationship["type"] == "cover_art":
                    if "attributes" in relationship and "fileName" in relationship["attributes"]:
                        filename = relationship["attributes"]["fileName"]
                        cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{filename}"
            
            results.append({
                "id": manga_id,
                "title": title,
                "description": attributes.get("description", {}).get("en", "No description available."),
                "status": attributes.get("status", "unknown"),
                "cover_url": cover_url
            })
        
        return results
    
    async def get_manga_details(self, manga_id):
        """Get detailed information about a manga"""
        params = {
            "includes[]": ["cover_art", "author", "artist"]
        }
        
        response = await self.make_request(f"/manga/{manga_id}", params)
        
        if not response or "data" not in response:
            return None
        
        manga = response["data"]
        attributes = manga["attributes"]
        
        # Get title
        title = ""
        if "title" in attributes:
            title_dict = attributes["title"]
            # Try to get English title, fallback to first available
            title = (title_dict.get("en") or 
                    title_dict.get("jp") or 
                    title_dict.get("ja") or 
                    next(iter(title_dict.values())) if title_dict else "Unknown Title")
        
        # Get cover art
        cover_url = None
        for relationship in manga.get("relationships", []):
            if relationship["type"] == "cover_art":
                if "attributes" in relationship and "fileName" in relationship["attributes"]:
                    filename = relationship["attributes"]["fileName"]
                    cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{filename}"
        
        return {
            "id": manga_id,
            "title": title,
            "description": attributes.get("description", {}).get("en", "No description available."),
            "status": attributes.get("status", "unknown"),
            "cover_url": cover_url,
            "attributes": attributes
        }
    
    async def get_latest_chapters(self, manga_id, limit=1):
        """Get the latest chapters for a manga"""
        params = {
            "manga": manga_id,
            "limit": limit,
            "order[chapter]": "desc",
            "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"],  # Include all ratings
            "includes[]": ["scanlation_group"]
        }
        
        response = await self.make_request("/chapter", params)
        
        if not response or "data" not in response:
            return []
        
        # Format the results
        chapters = []
        for chapter in response["data"]:
            chapter_id = chapter["id"]
            attributes = chapter["attributes"]
            
            # Get scanlation group
            group_name = "Unknown Group"
            for relationship in chapter.get("relationships", []):
                if relationship["type"] == "scanlation_group":
                    if "attributes" in relationship and "name" in relationship["attributes"]:
                        group_name = relationship["attributes"]["name"]
            
            # Get chapter number
            chapter_num = attributes.get("chapter", "N/A")
            if chapter_num == "":
                chapter_num = "N/A"
            
            # Get title
            title = attributes.get("title", "")
            if not title:
                title = f"Chapter {chapter_num}"
            
            # Create readable chapter info
            chapter_info = f"Chapter {chapter_num}"
            if title and title != f"Chapter {chapter_num}":
                chapter_info += f": {title}"
            
            chapters.append({
                "id": chapter_id,
                "chapter": chapter_num,
                "title": title,
                "chapter_info": chapter_info,
                "volume": attributes.get("volume", "N/A"),
                "group": group_name,
                "published_at": attributes.get("publishAt", ""),
                "url": f"https://mangadex.org/chapter/{chapter_id}"
            })
        
        return chapters


class MangaDexTracker(commands.Cog):
    """Track manga releases from MangaDex"""
    
    default_guild_settings = {
        "notification_channel": None,
    }
    
    default_global_settings = {
        "tracked_manga": {},
    }
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.api = MangaDexAPI()
        self.config = Config.get_conf(self, identifier=9879845123, force_registration=True)
        
        # Register default settings
        self.config.register_guild(**self.default_guild_settings)
        self.config.register_global(**self.default_global_settings)
        
        # Start the background task
        self.check_for_updates_task = self.bot.loop.create_task(self.check_for_updates())
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self.check_for_updates_task:
            self.check_for_updates_task.cancel()
        asyncio.create_task(self.api.close_session())
    
    @commands.group(name="manga")
    async def manga(self, ctx: commands.Context):
        """Manga tracking commands"""
        if ctx.invoked_subcommand is None:
            help_text = (
                "📚 **MangaDex Tracker**\n\n"
                "Available commands:\n"
                "`[p]manga search <title>` - Search for manga\n"
                "`[p]manga track <title>` - Track a manga for new chapter releases\n"
                "`[p]manga untrack <title>` - Stop tracking a manga\n"
                "`[p]manga list` - List all tracked manga\n"
                "`[p]manga setnotify [channel]` - Set the channel for notifications\n"
                "`[p]manga check` - Manually check for updates"
            )
            await ctx.send(help_text.replace("[p]", ctx.clean_prefix))
    
    @manga.command(name="search")
    async def manga_search(self, ctx: commands.Context, *, query: str):
        """Search for manga by title"""
        async with ctx.typing():
            message = await ctx.send(f"🔍 Searching for: {query}...")
            results = await self.api.search_manga(query)
            
            if not results or len(results) == 0:
                return await message.edit(content=f"❌ No results found for '{query}'")
            
            # Create pages for pagination
            pages = []
            
            # Split results into chunks of 3 per page (since each result has more info)
            chunks = [results[i:i + 3] for i in range(0, len(results), 3)]
            
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"Search Results for '{query}'",
                    color=await ctx.embed_color(),
                    timestamp=datetime.now()
                )
                
                for manga in chunk:
                    title = manga.get('title', 'Unknown Title')
                    manga_id = manga.get('id', 'Unknown ID')
                    status = manga.get('status', 'Unknown').capitalize()
                    description = manga.get('description', 'No description available.')
                    
                    # Truncate description if too long
                    if len(description) > 200:
                        description = description[:200] + "..."
                    
                    value = f"**ID:** `{manga_id}`\n**Status:** {status}\n\n{description}"
                    
                    embed.add_field(
                        name=f"{title}",
                        value=value,
                        inline=False
                    )
                    
                    # Set thumbnail to the cover of the first manga
                    if i == 0 and manga == chunk[0] and manga.get('cover_url'):
                        embed.set_thumbnail(url=manga.get('cover_url'))
                
                embed.set_footer(text=f"Page {i+1}/{len(chunks)} • Found {len(results)} results")
                pages.append(embed)
            
            # Send paginated results
            await message.delete()
            await menu(ctx, pages, DEFAULT_CONTROLS)
    
    @manga.command(name="track")
    async def manga_track(self, ctx: commands.Context, *, title: str):
        """Track a manga for new chapter releases"""
        async with ctx.typing():
            # Search for the manga first
            results = await self.api.search_manga(title)
            
            if not results or len(results) == 0:
                return await ctx.send(f"❌ No results found for '{title}'")
            
            # If multiple results, ask user to be more specific or provide an ID
            if len(results) > 1:
                # Try to find an exact match
                exact_match = None
                for manga in results:
                    if manga.get('title', '').lower() == title.lower():
                        exact_match = manga
                        break
                
                if not exact_match:
                    return await ctx.send(f"ℹ️ Found multiple results for '{title}'. Please be more specific or use the ID from search results.")
                else:
                    manga = exact_match
            else:
                manga = results[0]
            
            manga_id = manga.get('id')
            manga_title = manga.get('title')
            
            # Get the latest chapter
            chapters = await self.api.get_latest_chapters(manga_id)
            
            if not chapters:
                return await ctx.send(f"❌ Failed to get chapters for '{manga_title}'")
            
            latest_chapter = chapters[0] if chapters else None
            latest_chapter_num = latest_chapter.get('chapter', 'N/A') if latest_chapter else 'N/A'
            
            # Get current tracked manga
            tracked_manga = await self.config.tracked_manga()
            
            # Add to tracked manga
            tracked_manga[manga_id] = {
                'title': manga_title,
                'latest_chapter': latest_chapter_num,
                'last_checked': datetime.now(timezone.utc).isoformat()
            }
            
            # Save to config
            await self.config.tracked_manga.set(tracked_manga)
            
            # Set notification channel if not already set
            if await self.config.guild(ctx.guild).notification_channel() is None:
                await self.config.guild(ctx.guild).notification_channel.set(ctx.channel.id)
            
            await ctx.send(f"✅ Now tracking **{manga_title}**! Latest chapter: {latest_chapter_num}")
    
    @manga.command(name="untrack")
    async def manga_untrack(self, ctx: commands.Context, *, title: str):
        """Stop tracking a manga"""
        # Find manga by title in tracked list
        manga_id_to_remove = None
        tracked_manga = await self.config.tracked_manga()
        
        for manga_id, manga_data in tracked_manga.items():
            if manga_data['title'].lower() == title.lower():
                manga_id_to_remove = manga_id
                break
        
        if manga_id_to_remove:
            removed_title = tracked_manga[manga_id_to_remove]['title']
            del tracked_manga[manga_id_to_remove]
            await self.config.tracked_manga.set(tracked_manga)
            await ctx.send(f"✅ Stopped tracking **{removed_title}**")
        else:
            await ctx.send(f"❌ No tracked manga found with title '{title}'")
    
    @manga.command(name="list")
    async def manga_list(self, ctx: commands.Context):
        """List all tracked manga"""
        tracked_manga = await self.config.tracked_manga()
        
        if not tracked_manga:
            return await ctx.send("❌ No manga currently being tracked")
        
        # Create pages for pagination
        pages = []
        
        # Split manga into chunks of 5 per page
        manga_items = list(tracked_manga.items())
        chunks = [manga_items[i:i + 5] for i in range(0, len(manga_items), 5)]
        
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title="📚 Tracked Manga",
                description=f"Currently tracking {len(tracked_manga)} manga",
                color=await ctx.embed_color(),
                timestamp=datetime.now()
            )
            
            for manga_id, manga_data in chunk:
                embed.add_field(
                    name=manga_data['title'],
                    value=f"Latest Chapter: {manga_data['latest_chapter']}\n"
                          f"Last Checked: {manga_data['last_checked']}",
                    inline=False
                )
            
            embed.set_footer(text=f"Page {i+1}/{len(chunks)}")
            pages.append(embed)
        
        # If only one page, just send it
        if len(pages) == 1:
            return await ctx.send(embed=pages[0])
        
        # Otherwise use paginated menu
        await menu(ctx, pages, DEFAULT_CONTROLS)
    
    @manga.command(name="setnotify")
    async def set_notification_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel for notifications
        
        If no channel is provided, uses the current channel.
        """
        channel = channel or ctx.channel
        
        # Check permissions
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send(f"❌ I don't have permission to send messages in {channel.mention}")
        
        await self.config.guild(ctx.guild).notification_channel.set(channel.id)
        await ctx.send(f"✅ Notifications for this server will be sent to {channel.mention}")
    
    @manga.command(name="check")
    async def manual_check(self, ctx: commands.Context):
        """Manually check for updates"""
        async with ctx.typing():
            await ctx.send("🔍 Manually checking for updates...")
            updates = await self._check_for_updates(ctx.guild)
            
            if updates:
                await ctx.send(f"✅ Found {len(updates)} updates!")
            else:
                await ctx.send("ℹ️ No new chapters found.")
    
    async def _check_for_updates(self, guild=None):
        """Check for updates and return a list of updates found"""
        updates_found = []
        
        try:
            # Get tracked manga
            tracked_manga = await self.config.tracked_manga()
            updates_made = False
            
            for manga_id, manga_data in tracked_manga.items():
                try:
                    # Get latest chapters
                    chapters = await self.api.get_latest_chapters(manga_id)
                    
                    if not chapters:
                        log.error(f"Failed to get chapters for {manga_data['title']}")
                        continue
                    
                    latest_chapter = chapters[0] if chapters else None
                    if not latest_chapter:
                        continue
                    
                    latest_chapter_num = latest_chapter.get('chapter', 'N/A')
                    
                    # Update last checked timestamp
                    tracked_manga[manga_id]['last_checked'] = datetime.now(timezone.utc).isoformat()
                    updates_made = True
                    
                    # Check if there's a new chapter
                    try:
                        # Convert to float for comparison if possible
                        current = float(manga_data['latest_chapter']) if manga_data['latest_chapter'] != 'N/A' else 0
                        new = float(latest_chapter_num) if latest_chapter_num != 'N/A' else 0
                        
                        if new > current:
                            log.info(f"New chapter found for {manga_data['title']}: {latest_chapter_num} (current: {manga_data['latest_chapter']})")
                            
                            # Update the latest chapter number
                            tracked_manga[manga_id]['latest_chapter'] = latest_chapter_num
                            
                            # Add to updates found
                            updates_found.append({
                                'manga_id': manga_id,
                                'manga_title': manga_data['title'],
                                'previous_chapter': manga_data['latest_chapter'],
                                'new_chapter': latest_chapter_num,
                                'chapter_data': latest_chapter
                            })
                    except ValueError:
                        # Handle non-numeric chapter numbers
                        if latest_chapter_num != manga_data['latest_chapter']:
                            log.info(f"New chapter found for {manga_data['title']}: {latest_chapter_num} (current: {manga_data['latest_chapter']})")
                            
                            # Update the latest chapter number
                            tracked_manga[manga_id]['latest_chapter'] = latest_chapter_num
                            
                            # Add to updates found
                            updates_found.append({
                                'manga_id': manga_id,
                                'manga_title': manga_data['title'],
                                'previous_chapter': manga_data['latest_chapter'],
                                'new_chapter': latest_chapter_num,
                                'chapter_data': latest_chapter
                            })
                    
                except Exception as e:
                    log.error(f"Error checking updates for {manga_data['title']}: {str(e)}")
                
                # Add a small delay between requests to avoid rate limiting
                await asyncio.sleep(1)
            
            # Save updated data if changes were made
            if updates_made:
                await self.config.tracked_manga.set(tracked_manga)
            
            # Send notifications if updates were found and a guild was specified
            if updates_found and guild:
                await self._send_notifications(updates_found, [guild])
            
            return updates_found
            
        except Exception as e:
            log.error(f"Error in update check: {str(e)}")
            return []
    
    async def _send_notifications(self, updates, guilds=None):
        """Send notifications for updates to specified guilds"""
        guilds = guilds or self.bot.guilds
        
        for update in updates:
            for guild in guilds:
                try:
                    channel_id = await self.config.guild(guild).notification_channel()
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            chapter_data = update.get('chapter_data', {})
                            chapter_url = chapter_data.get('url', '')
                            chapter_info = chapter_data.get('chapter_info', f"Chapter {update['new_chapter']}")
                            group = chapter_data.get('group', 'Unknown Group')
                            
                            embed = discord.Embed(
                                title=f"📢 New Chapter Alert: {update['manga_title']}",
                                description=f"**{chapter_info}** is now available!",
                                color=discord.Color.gold(),
                                url=chapter_url
                            )
                            
                            embed.add_field(name="Scanlation Group", value=group, inline=True)
                            
                            # Add previous chapter info
                            if update['previous_chapter'] != 'N/A':
                                embed.add_field(name="Previous Chapter", value=update['previous_chapter'], inline=True)
                            
                            embed.set_footer(text="MangaDex Tracker")
                            await channel.send(embed=embed)
                except Exception as e:
                    log.error(f"Error sending notification to guild {guild.id}: {str(e)}")
    
    async def check_for_updates(self):
        """Background task to check for manga updates"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready() and not self.bot.is_closed():
            try:
                log.info("Checking for manga updates...")
                await self._check_for_updates()
                
                # Wait for 30 minutes before checking again
                await asyncio.sleep(1800)  # 30 minutes in seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in update check task: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying if an error occurs


async def setup(bot: Red):
    """Add the cog to the bot"""
    cog = MangaDexTracker(bot)
    await bot.add_cog(cog)
