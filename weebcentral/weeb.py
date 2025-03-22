import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from urllib.parse import quote

import aiohttp
import discord
from bs4 import BeautifulSoup
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

log = logging.getLogger("red.weebcentral")

class WeebCentralAPI:
    """API wrapper for WeebCentral"""
    
    def __init__(self, base_url="https://weebcentral.com"):
        self.base_url = base_url.rstrip("/")
        self.session = None
        self.directory = None  # Cache the directory
    
    async def ensure_session(self):
        """Ensure an aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Referer": self.base_url
            })
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_directory(self, force_refresh=False):
        """Get the full manga directory"""
        if self.directory is not None and not force_refresh:
            return self.directory
        
        await self.ensure_session()
        
        try:
            # First, try to get the directory from the search page
            async with self.session.get(f"{self.base_url}/search") as response:
                if response.status != 200:
                    log.error(f"Failed to get directory, status: {response.status}")
                    return []
                
                html = await response.text()
                
                # Try to find the directory in a JavaScript variable
                directory_match = re.search(r'vm\.Directory\s*=\s*(\[.*?\]);', html, re.DOTALL)
                if directory_match:
                    try:
                        directory_json = directory_match.group(1)
                        self.directory = json.loads(directory_json)
                        return self.directory
                    except json.JSONDecodeError as e:
                        log.error(f"Failed to parse directory JSON: {e}")
                
                # If we couldn't find the directory in JavaScript, try to scrape it from HTML
                soup = BeautifulSoup(html, 'html.parser')
                manga_items = []
                
                # Look for manga listings on the page
                manga_elements = soup.select('.manga-item') or soup.select('.grid-item')
                for element in manga_elements:
                    a_tag = element.find('a')
                    if a_tag and 'href' in a_tag.attrs:
                        link = a_tag['href']
                        title = a_tag.get_text(strip=True) or a_tag.get('title', '')
                        
                        # Extract manga ID from link
                        id_match = re.search(r'/series/([^/]+)', link)
                        manga_id = id_match.group(1) if id_match else ''
                        
                        if manga_id and title:
                            manga_items.append({
                                'i': manga_id,
                                's': title,
                                'a': []  # Empty array for aliases
                            })
                
                self.directory = manga_items
                return manga_items
                
        except Exception as e:
            log.error(f"Error getting manga directory: {str(e)}")
            return []
    
    async def search_manga(self, query: str) -> List[Dict]:
        """Search for manga by name"""
        await self.ensure_session()
        
        try:
            # Get the full directory
            directory = await self.get_directory()
            if not directory:
                return []
            
            # Normalize the query
            query_lower = query.lower()
            
            # Search in the directory
            results = []
            for manga in directory:
                title = manga.get('s', '')
                if query_lower in title.lower():
                    results.append({
                        'id': manga.get('i', ''),
                        'title': title,
                        'alt_titles': manga.get('a', [])
                    })
                else:
                    # Also search in alternative titles
                    for alt in manga.get('a', []):
                        if query_lower in alt.lower():
                            results.append({
                                'id': manga.get('i', ''),
                                'title': title,
                                'alt_titles': manga.get('a', [])
                            })
                            break
            
            # If we still don't have results, try a direct search
            if not results:
                search_url = f"{self.base_url}/search?q={quote(query)}"
                async with self.session.get(search_url) as response:
                    if response.status != 200:
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Look for manga listings
                    manga_elements = soup.select('.manga-item') or soup.select('.grid-item')
                    for element in manga_elements:
                        a_tag = element.find('a')
                        if a_tag and 'href' in a_tag.attrs:
                            link = a_tag['href']
                            title = a_tag.get_text(strip=True) or a_tag.get('title', '')
                            
                            # Extract manga ID from link
                            id_match = re.search(r'/series/([^/]+)', link)
                            manga_id = id_match.group(1) if id_match else ''
                            
                            if manga_id and title:
                                results.append({
                                    'id': manga_id,
                                    'title': title,
                                    'alt_titles': []
                                })
            
            return results
            
        except Exception as e:
            log.error(f"Error searching for manga: {str(e)}")
            return []
    
    async def get_manga_details(self, manga_id: str) -> Optional[Dict]:
        """Get detailed information about a manga"""
        await self.ensure_session()
        
        try:
            manga_url = f"{self.base_url}/series/{manga_id}"
            
            async with self.session.get(manga_url) as response:
                if response.status != 200:
                    log.error(f"Failed to get manga details, status: {response.status}")
                    return None
                
                html = await response.text()
                
                # Try to extract manga details from JavaScript variables
                chapters_match = re.search(r'vm\.Chapters\s*=\s*(\[.*?\]);', html, re.DOTALL)
                
                if not chapters_match:
                    # If we can't find the chapters variable, try BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    title_element = soup.select_one('.series-title') or soup.select_one('h1')
                    title = title_element.get_text(strip=True) if title_element else ''
                    
                    chapters = []
                    chapter_elements = soup.select('.chapter-item') or soup.select('.chapter-list-item')
                    for element in chapter_elements:
                        a_tag = element.find('a')
                        if a_tag and 'href' in a_tag.attrs:
                            link = a_tag['href']
                            chapter_text = a_tag.get_text(strip=True)
                            
                            # Extract chapter number
                            chapter_num_match = re.search(r'Chapter\s+(\d+(\.\d+)?)', chapter_text)
                            chapter_num = chapter_num_match.group(1) if chapter_num_match else ''
                            
                            # Extract chapter ID from link
                            id_match = re.search(r'/chapters/([^/]+)', link)
                            chapter_id = id_match.group(1) if id_match else ''
                            
                            if chapter_id and chapter_num:
                                date_element = element.select_one('.chapter-date')
                                date_text = date_element.get_text(strip=True) if date_element else ''
                                
                                chapters.append({
                                    'id': chapter_id,
                                    'chapter_number': float(chapter_num),
                                    'title': chapter_text,
                                    'date': date_text,
                                    'url': link
                                })
                    
                    return {
                        'id': manga_id,
                        'title': title,
                        'chapters': sorted(chapters, key=lambda x: x['chapter_number'], reverse=True)
                    }
                else:
                    # Parse chapters from JavaScript
                    try:
                        chapters_json = chapters_match.group(1)
                        chapters_data = json.loads(chapters_json)
                        
                        # Get title from the page
                        soup = BeautifulSoup(html, 'html.parser')
                        title_element = soup.select_one('.series-title') or soup.select_one('h1')
                        title = title_element.get_text(strip=True) if title_element else ''
                        
                        # Process chapters
                        chapters = []
                        for chapter in chapters_data:
                            chapter_id = chapter.get('id', '') or chapter.get('ChapterID', '') or chapter.get('i', '')
                            chapter_num = chapter.get('Chapter', '') or chapter.get('ChapterNumber', '') or chapter.get('n', '')
                            
                            if not chapter_id or not chapter_num:
                                continue
                            
                            # Convert chapter number to float
                            try:
                                chapter_num = float(chapter_num)
                            except ValueError:
                                continue
                            
                            chapter_title = chapter.get('ChapterName', '') or f"Chapter {chapter_num}"
                            date_str = chapter.get('Date', '') or chapter.get('ReleaseDate', '') or ''
                            
                            chapters.append({
                                'id': chapter_id,
                                'chapter_number': chapter_num,
                                'title': chapter_title,
                                'date': date_str,
                                'url': f"{self.base_url}/chapters/{chapter_id}"
                            })
                        
                        return {
                            'id': manga_id,
                            'title': title,
                            'chapters': sorted(chapters, key=lambda x: x['chapter_number'], reverse=True)
                        }
                    except json.JSONDecodeError as e:
                        log.error(f"Failed to parse chapters JSON: {e}")
                        return None
                    
        except Exception as e:
            log.error(f"Error getting manga details: {str(e)}")
            return None
    
    async def get_latest_chapters(self, manga_id: str) -> List[Dict]:
        """Get the latest chapters for a manga"""
        manga_details = await self.get_manga_details(manga_id)
        if manga_details:
            return manga_details.get('chapters', [])
        return []


class WeebCentral(commands.Cog):
    """Track manga releases from WeebCentral"""
    
    default_guild_settings = {
        "notification_channel": None,
    }
    
    default_global_settings = {
        "tracked_manga": {},
    }
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.api = WeebCentralAPI()
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
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
                "📚 **WeebCentral Manga Tracker**\n\n"
                "Available commands:\n"
                "`[p]manga search <title>` - Search for manga\n"
                "`[p]manga track <title>` - Track a manga for new chapter releases\n"
                "`[p]manga untrack <title>` - Stop tracking a manga\n"
                "`[p]manga list` - List all tracked manga\n"
                "`[p]manga setnotify [channel]` - Set the channel for notifications\n"
                "`[p]manga refresh` - Force refresh the manga directory\n"
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
            
            # Split results into chunks of 5 per page
            chunks = [results[i:i + 5] for i in range(0, len(results), 5)]
            
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"Search Results for '{query}'",
                    color=await ctx.embed_color(),
                    timestamp=datetime.now()
                )
                
                for manga in chunk:
                    manga_id = manga.get('id', 'Unknown ID')
                    title = manga.get('title', 'Unknown Title')
                    alt_titles = manga.get('alt_titles', [])
                    
                    value = f"ID: `{manga_id}`\n"
                    if alt_titles and len(alt_titles) > 0:
                        value += f"Alternate Titles: {', '.join(alt_titles[:3])}\n"
                    
                    embed.add_field(
                        name=f"{title}",
                        value=value,
                        inline=False
                    )
                
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
            latest_chapter_num = latest_chapter.get('chapter_number', 0) if latest_chapter else 0
            
            # Convert to string if it's a number
            if isinstance(latest_chapter_num, (int, float)):
                latest_chapter_num = str(latest_chapter_num)
            
            # Get current tracked manga
            tracked_manga = await self.config.tracked_manga()
            
            # Add to tracked manga
            tracked_manga[manga_id] = {
                'title': manga_title,
                'latest_chapter': latest_chapter_num,
                'last_checked': datetime.now().isoformat()
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
    
    @manga.command(name="refresh")
    async def refresh_directory(self, ctx: commands.Context):
        """Force refresh the manga directory"""
        async with ctx.typing():
            await ctx.send("🔄 Refreshing manga directory...")
            directory = await self.api.get_directory(force_refresh=True)
            await ctx.send(f"✅ Refreshed manga directory. Found {len(directory)} manga.")
    
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
                    
                    latest_chapter_num = latest_chapter.get('chapter_number', 0)
                    
                    # Convert to string if it's a number
                    if isinstance(latest_chapter_num, (int, float)):
                        latest_chapter_num = str(latest_chapter_num)
                    
                    # Update last checked timestamp
                    tracked_manga[manga_id]['last_checked'] = datetime.now().isoformat()
                    updates_made = True
                    
                    # Check if there's a new chapter
                    try:
                        current = float(manga_data['latest_chapter'])
                        new = float(latest_chapter_num)
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
                        log.error(f"Error comparing chapter numbers for {manga_data['title']}: {manga_data['latest_chapter']} vs {latest_chapter_num}")
                    
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
                            manga_id = update.get('manga_id', '')
                            
                            embed = discord.Embed(
                                title=f"📢 New Chapter Alert: {update['manga_title']}",
                                description=f"Chapter {update['new_chapter']} is now available!",
                                color=discord.Color.gold(),
                                url=chapter_url or f"{self.api.base_url}/series/{manga_id}"
                            )
                            
                            embed.set_footer(text="WeebCentral Manga Tracker")
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
                
                # Wait for 1 hour before checking again
                await asyncio.sleep(3600)  # 1 hour in seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in update check task: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying if an error occurs


async def setup(bot: Red):
    """Add the cog to the bot"""
    cog = WeebCentral(bot)
    await bot.add_cog(cog)
