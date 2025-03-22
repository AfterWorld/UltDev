import asyncio
import logging
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union
from urllib.parse import quote, urljoin

import aiohttp
from bs4 import BeautifulSoup
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

log = logging.getLogger("red.mangatracker")

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
    
    async def make_request(self, endpoint, params=None, fallback_scrape=False):
        """Make a request to the MangaDex API with web scraping fallback"""
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
                    
                    # Try web scraping fallback if enabled
                    if fallback_scrape and endpoint.startswith("/manga"):
                        log.info("Trying web scraping fallback...")
                        return await self.scrape_fallback(endpoint, params)
                    
                    return None
        except Exception as e:
            log.error(f"Error making API request: {str(e)}")
            
            # Try web scraping fallback if enabled
            if fallback_scrape and endpoint.startswith("/manga"):
                log.info("Trying web scraping fallback after exception...")
                return await self.scrape_fallback(endpoint, params)
                
            return None
    
    async def scrape_fallback(self, endpoint, params=None):
        """Fallback to web scraping when API fails"""
        await self.ensure_session()
        
        # Convert API endpoint to web URL
        web_url = "https://mangadex.org"
        
        if endpoint.startswith("/manga"):
            manga_id = endpoint.split("/")[-1] if "/" in endpoint else ""
            if manga_id:
                web_url += f"/title/{manga_id}"
            elif params and "title" in params:
                web_url += f"/search?q={params['title']}"
            else:
                web_url += "/titles"
        
        log.info(f"Scraping from web URL: {web_url}")
        
        try:
            async with self.session.get(web_url) as response:
                if response.status != 200:
                    log.error(f"Web scraping failed with status {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Different parsing based on endpoint
                if endpoint.startswith("/manga/") and "/" in endpoint:
                    # Single manga page
                    return self.parse_manga_page(soup, endpoint.split("/")[-1])
                elif endpoint.startswith("/manga") or (params and "title" in params):
                    # Manga search results
                    return self.parse_search_results(soup, params.get("title", "") if params else "")
                
                return None
        except Exception as e:
            log.error(f"Error in web scraping fallback: {str(e)}")
            return None
    
    def parse_manga_page(self, soup, manga_id):
        """Parse a single manga page"""
        result = {"data": {
            "id": manga_id,
            "attributes": {},
            "relationships": []
        }}
        
        # Try to get the title
        title_elem = soup.select_one("h3.manga-title") or soup.select_one("h1") or soup.select_one(".title")
        if title_elem:
            result["data"]["attributes"]["title"] = {"en": title_elem.get_text(strip=True)}
        
        # Try to get description
        desc_elem = soup.select_one(".description") or soup.select_one(".synopsis")
        if desc_elem:
            result["data"]["attributes"]["description"] = {"en": desc_elem.get_text(strip=True)}
        
        # Try to get status
        status_elem = soup.select_one(".status")
        if status_elem:
            result["data"]["attributes"]["status"] = status_elem.get_text(strip=True).lower()
        
        # Try to get cover art
        cover_elem = soup.select_one(".cover img") or soup.select_one(".manga-poster img")
        if cover_elem and "src" in cover_elem.attrs:
            cover_url = cover_elem["src"]
            result["data"]["relationships"].append({
                "type": "cover_art",
                "attributes": {"fileName": cover_url.split("/")[-1]}
            })
        
        return result
    
    def parse_search_results(self, soup, search_query):
        """Parse search results page"""
        results = {"data": []}
        
        # Look for manga cards/items
        manga_items = soup.select(".manga-card") or soup.select(".manga-item") or soup.select(".grid-item")
        
        for item in manga_items:
            manga_id = ""
            # Try to extract ID from URL
            link_elem = item.select_one("a")
            if link_elem and "href" in link_elem.attrs:
                href = link_elem["href"]
                id_match = re.search(r'/title/([^/]+)', href)
                if id_match:
                    manga_id = id_match.group(1)
            
            # Get title
            title_elem = item.select_one(".manga-title") or item.select_one("h3") or link_elem
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
            
            # Get cover image
            cover_url = None
            img_elem = item.select_one("img")
            if img_elem and "src" in img_elem.attrs:
                cover_url = img_elem["src"]
            
            # Create manga entry
            manga_entry = {
                "id": manga_id,
                "attributes": {
                    "title": {"en": title},
                },
                "relationships": []
            }
            
            # Add cover art relationship if available
            if cover_url:
                manga_entry["relationships"].append({
                    "type": "cover_art",
                    "attributes": {"fileName": cover_url.split("/")[-1]}
                })
            
            results["data"].append(manga_entry)
        
        return results
    
    async def search_manga(self, title, limit=5, offset=0, fallback_scrape=False):
        """Search for manga by title with web scraping fallback"""
        params = {
            "title": title,
            "limit": limit,
            "offset": offset,
            "includes[]": ["cover_art", "author", "artist"],
            "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"]  # Include all ratings
        }
        
        response = await self.make_request("/manga", params, fallback_scrape=fallback_scrape)
        
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
                "cover_url": cover_url,
                "source": "mangadex"
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
            "attributes": attributes,
            "source": "mangadex"
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
                "url": f"https://mangadex.org/chapter/{chapter_id}",
                "source": "mangadex"
            })
        
        return chapters


class TCBScansAPI:
    """API wrapper for TCB Scans (web scraping based)"""
    
    def __init__(self):
        self.base_url = "https://tcbscans.com"
        self.session = None
    
    async def ensure_session(self):
        """Ensure an aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml",
                "Accept-Language": "en-US,en;q=0.9"
            })
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_webpage(self, url):
        """Fetch a webpage and return its HTML"""
        await self.ensure_session()
        
        try:
            log.info(f"Fetching TCB page: {url}")
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    log.error(f"Failed to get TCB page, status: {response.status} for URL: {url}")
                    return None
        except Exception as e:
            log.error(f"Error fetching TCB page: {str(e)}")
            return None
    
    async def search_manga(self, title):
        """Search for manga by title"""
        # TCB Scans doesn't have a search API, so we scrape from the projects page
        html = await self.get_webpage(f"{self.base_url}/projects")
        if not html:
            return []
        
        results = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for manga cards
        manga_cards = soup.select(".bg-card")
        
        title_lower = title.lower()
        for card in manga_cards:
            # Extract manga info
            manga_link = card.select_one("a")
            if not manga_link or not manga_link.get("href"):
                continue
                
            manga_url = manga_link.get("href")
            manga_id = manga_url.split("/")[-1] if "/" in manga_url else manga_url
            
            title_elem = card.select_one("h5") or card.select_one(".card-title")
            manga_title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
            
            # Only include if the title matches the search query
            if title_lower in manga_title.lower():
                # Get cover image
                cover_url = None
                img_elem = card.select_one("img")
                if img_elem and "src" in img_elem.attrs:
                    cover_url = img_elem["src"]
                    # Make sure URL is absolute
                    if not cover_url.startswith("http"):
                        cover_url = urljoin(self.base_url, cover_url)
                
                results.append({
                    "id": manga_id,
                    "title": manga_title,
                    "url": urljoin(self.base_url, manga_url),
                    "cover_url": cover_url,
                    "source": "tcbscans"
                })
        
        return results
    
    async def get_manga_details(self, manga_id):
        """Get detailed information about a manga using its URL or ID"""
        if manga_id.startswith("http"):
            url = manga_id  # It's already a full URL
        else:
            # Try to construct the URL from ID
            url = f"{self.base_url}/mangas/{manga_id}"
        
        html = await self.get_webpage(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract manga info
        title_elem = soup.select_one("h1") or soup.select_one(".manga-title")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
        
        # Get description
        desc_elem = soup.select_one(".description") or soup.select_one(".synopsis")
        description = desc_elem.get_text(strip=True) if desc_elem else "No description available."
        
        # Get cover image
        cover_url = None
        img_elem = soup.select_one(".manga-cover img") or soup.select_one(".manga-image img")
        if img_elem and "src" in img_elem.attrs:
            cover_url = img_elem["src"]
            # Make sure URL is absolute
            if not cover_url.startswith("http"):
                cover_url = urljoin(self.base_url, cover_url)
        
        return {
            "id": manga_id,
            "title": title,
            "description": description,
            "url": url,
            "cover_url": cover_url,
            "source": "tcbscans"
        }
    
    async def get_latest_chapters(self, manga_id):
        """Get the latest chapters for a manga"""
        manga_url = manga_id if manga_id.startswith("http") else f"{self.base_url}/mangas/{manga_id}"
        
        html = await self.get_webpage(manga_url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the chapters section
        chapters = []
        chapter_items = soup.select(".chapter-item") or soup.select(".chapters-list li")
        
        for item in chapter_items:
            # Extract chapter info
            link = item.select_one("a")
            if not link or not link.get("href"):
                continue
            
            chapter_url = link.get("href")
            chapter_id = chapter_url.split("/")[-1] if "/" in chapter_url else chapter_url
            
            # Extract chapter title/number
            title_text = link.get_text(strip=True)
            
            # Try to extract chapter number with regex
            chapter_num_match = re.search(r'Chapter\s+(\d+(?:\.\d+)?)', title_text, re.IGNORECASE)
            chapter_num = chapter_num_match.group(1) if chapter_num_match else "N/A"
            
            # Create readable chapter info
            chapter_info = title_text
            
            # Get the date if available
            date_elem = item.select_one(".release-date") or item.select_one(".date")
            date_text = date_elem.get_text(strip=True) if date_elem else ""
            
            chapters.append({
                "id": chapter_id,
                "chapter": chapter_num,
                "title": title_text,
                "chapter_info": chapter_info,
                "published_at": date_text,
                "url": urljoin(self.base_url, chapter_url),
                "source": "tcbscans"
            })
        
        # Sort chapters by number in descending order
        try:
            chapters.sort(key=lambda x: float(x["chapter"]) if x["chapter"] != "N/A" else 0, reverse=True)
        except (ValueError, TypeError):
            # If sorting fails, keep original order
            pass
        
        return chapters


class MangaTracker(commands.Cog):
    """Track manga releases from MangaDex and TCB Scans"""
    
    default_guild_settings = {
        "notification_channel": None,
    }
    
    default_global_settings = {
        "tracked_manga": {},
    }
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.mangadex_api = MangaDexAPI()
        self.tcbscans_api = TCBScansAPI()
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
        asyncio.create_task(self.mangadex_api.close_session())
        asyncio.create_task(self.tcbscans_api.close_session())
    
    def format_timestamp(self, dt):
        """Format a datetime object into a clean human-readable string"""
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except ValueError:
                return dt
                
        # Format: "March 22, 2025 at 6:38 PM UTC"
        return dt.strftime("%B %d, %Y at %I:%M %p %Z")
    
    @commands.group(name="manga")
    async def manga(self, ctx: commands.Context):
        """Manga tracking commands"""
        if ctx.invoked_subcommand is None:
            help_text = (
                "📚 **Manga Tracker**\n\n"
                "Available commands:\n"
                "`[p]manga search <title>` - Search for manga\n"
                "`[p]manga track <title>` - Track a manga for new chapter releases\n"
                "`[p]manga untrack <title>` - Stop tracking a manga\n"
                "`[p]manga list` - List all tracked manga\n"
                "`[p]manga setnotify [channel]` - Set the channel for notifications\n"
                "`[p]manga check` - Manually check for updates\n"
                "`[p]manga tcbsearch <title>` - Search for manga on TCB Scans"
            )
            await ctx.send(help_text.replace("[p]", ctx.clean_prefix))
    
    @manga.command(name="search")
    async def manga_search(self, ctx: commands.Context, *, query: str):
        """Search for manga on MangaDex by title"""
        async with ctx.typing():
            message = await ctx.send(f"🔍 Searching for: {query}...")
            results = await self.mangadex_api.search_manga(query, fallback_scrape=True)
            
            if not results or len(results) == 0:
                return await message.edit(content=f"❌ No results found for '{query}' on MangaDex")
            
            # Create pages for pagination
            pages = []
            
            # Split results into chunks of 3 per page (since each result has more info)
            chunks = [results[i:i + 3] for i in range(0, len(results), 3)]
            
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"MangaDex Results for '{query}'",
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
    
    @manga.command(name="tcbsearch")
    async def tcb_manga_search(self, ctx: commands.Context, *, query: str):
        """Search for manga on TCB Scans by title"""
        async with ctx.typing():
            message = await ctx.send(f"🔍 Searching for: {query} on TCB Scans...")
            results = await self.tcbscans_api.search_manga(query)
            
            if not results or len(results) == 0:
                return await message.edit(content=f"❌ No results found for '{query}' on TCB Scans")
            
            # Create pages for pagination
            pages = []
            
            # Split results into chunks of 3 per page
            chunks = [results[i:i + 3] for i in range(0, len(results), 3)]
            
            for i, chunk in enumerate(chunks):
                embed = discord.Embed(
                    title=f"TCB Scans Results for '{query}'",
                    color=await ctx.embed_color(),
                    timestamp=datetime.now()
                )
                
                for manga in chunk:
                    title = manga.get('title', 'Unknown Title')
                    manga_id = manga.get('id', 'Unknown ID')
                    url = manga.get('url', '#')
                    
                    value = f"**ID:** `{manga_id}`\n**URL:** [Read on TCB Scans]({url})"
                    
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
        """Track a manga for new chapter releases (searches both MangaDex and TCB Scans)"""
        async with ctx.typing():
            await ctx.send(f"🔍 Searching on both MangaDex and TCB Scans for: {title}...")
            
            # Search on both platforms
            mangadex_results = await self.mangadex_api.search_manga(title, fallback_scrape=True)
            tcb_results = await self.tcbscans_api.search_manga(title)
            
            if not mangadex_results and not tcb_results:
                return await ctx.send(f"❌ No results found for '{title}' on either MangaDex or TCB Scans")
            
            # Create a combined embed for selection
            embed = discord.Embed(
                title=f"Select a manga to track",
                description=f"Reply with the number of the manga you want to track:",
                color=await ctx.embed_color(),
                timestamp=datetime.now()
            )
            
            options = []
            count = 1
            
            # Add MangaDex results
            if mangadex_results:
                embed.add_field(name="📚 MangaDex Results", value="", inline=False)
                for manga in mangadex_results[:5]:  # Limit to first 5
                    options.append(manga)
                    embed.add_field(
                        name=f"{count}. {manga.get('title', 'Unknown Title')}",
                        value=f"Source: MangaDex",
                        inline=True
                    )
                    count += 1
            
            # Add TCB Scans results
            if tcb_results:
                embed.add_field(name="📚 TCB Scans Results", value="", inline=False)
                for manga in tcb_results[:5]:  # Limit to first 5
                    options.append(manga)
                    embed.add_field(
                        name=f"{count}. {manga.get('title', 'Unknown Title')}",
                        value=f"Source: TCB Scans",
                        inline=True
                    )
                    count += 1
            
            # Send embed and wait for response
            selection_message = await ctx.send(embed=embed)
            
            def check(msg):
                return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.isdigit()
            
            try:
                # Wait for user selection
                user_response = await self.bot.wait_for('message', check=check, timeout=60.0)
                selection = int(user_response.content)
                
                # Validate selection
                if selection < 1 or selection > len(options):
                    return await ctx.send(f"❌ Invalid selection. Please choose a number between 1 and {len(options)}.")
                
                # Get the selected manga
                selected_manga = options[selection - 1]
                source = selected_manga.get('source', 'unknown')
                manga_id = selected_manga.get('id', '')
                manga_title = selected_manga.get('title', 'Unknown Title')
                
                if source == 'mangadex':
                    # Get the latest chapter from MangaDex
                    chapters = await self.mangadex_api.get_latest_chapters(manga_id)
                    api = self.mangadex_api
                elif source == 'tcbscans':
                    # Get the latest chapter from TCB Scans
                    if 'url' in selected_manga:
                        chapters = await self.tcbscans_api.get_latest_chapters(selected_manga['url'])
                    else:
                        chapters = await self.tcbscans_api.get_latest_chapters(manga_id)
                    api = self.tcbscans_api
                else:
                    return await ctx.send(f"❌ Unknown source for manga: {manga_title}")
                
                if not chapters:
                    return await ctx.send(f"❌ Failed to get chapters for '{manga_title}'")
                
                latest_chapter = chapters[0] if chapters else None
                latest_chapter_num = latest_chapter.get('chapter', 'N/A') if latest_chapter else 'N/A'
                
                # Get current tracked manga
                tracked_manga = await self.config.tracked_manga()
                
                # Generate a unique key
                manga_key = f"{source}-{manga_id}"
                
                # Add to tracked manga
                tracked_manga[manga_key] = {
                    'title': manga_title,
                    'latest_chapter': latest_chapter_num,
                    'last_checked': self.format_timestamp(datetime.now(timezone.utc)),
                    'source': source,
                    'id': manga_id,
                    'url': selected_manga.get('url', '') if source == 'tcbscans' else ''
                }
                
                # Save to config
                await self.config.tracked_manga.set(tracked_manga)
                
                # Set notification channel if not already set
                if await self.config.guild(ctx.guild).notification_channel() is None:
                    await self.config.guild(ctx.guild).notification_channel.set(ctx.channel.id)
                
                await ctx.send(f"✅ Now tracking **{manga_title}** from **{source.upper()}**! Latest chapter: {latest_chapter_num}")
                
            except asyncio.TimeoutError:
                await ctx.send("❌ Selection timed out. Please try again.")
            
        except Exception as e:
            log.error(f"Error in manga track command: {str(e)}")
            await ctx.send(f"❌ An error occurred: {str(e)}")
    
    @manga.command(name="untrack")
    async def manga_untrack(self, ctx: commands.Context, *, title: str):
        """Stop tracking a manga"""
        # Find manga by title in tracked list
        manga_key_to_remove = None
        tracked_manga = await self.config.tracked_manga()
        
        for manga_key, manga_data in tracked_manga.items():
            if manga_data['title'].lower() == title.lower():
                manga_key_to_remove = manga_key
                break
        
        if manga_key_to_remove:
            removed_title = tracked_manga[manga_key_to_remove]['title']
            removed_source = tracked_manga[manga_key_to_remove].get('source', 'unknown').upper()
            del tracked_manga[manga_key_to_remove]
            await self.config.tracked_manga.set(tracked_manga)
            await ctx.send(f"✅ Stopped tracking **{removed_title}** from **{removed_source}**")
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
            
            for manga_key, manga_data in chunk:
                # Format the last_checked timestamp if it's not already formatted
                last_checked = manga_data['last_checked']
                if isinstance(last_checked, str) and ('+' in last_checked or 'T' in last_checked):
                    last_checked = self.format_timestamp(last_checked)
                
                source = manga_data.get('source', 'unknown').upper()
                
                embed.add_field(
                    name=f"{manga_data['title']} ({source})",
                    value=f"Latest Chapter: {manga_data['latest_chapter']}\n"
                          f"Last Checked: {last_checked}",
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
            
            for manga_key, manga_data in tracked_manga.items():
                try:
                    source = manga_data.get('source', 'mangadex')
                    manga_id = manga_data.get('id', '')
                    manga_url = manga_data.get('url', '')
                    
                    # Get chapters based on source
                    chapters = []
                    if source == 'mangadex':
                        chapters = await self.mangadex_api.get_latest_chapters(manga_id)
                    elif source == 'tcbscans':
                        if manga_url:
                            chapters = await self.tcbscans_api.get_latest_chapters(manga_url)
                        else:
                            chapters = await self.tcbscans_api.get_latest_chapters(manga_id)
                    
                    if not chapters:
                        log.error(f"Failed to get chapters for {manga_data['title']} from {source}")
                        continue
                    
                    latest_chapter = chapters[0] if chapters else None
                    if not latest_chapter:
                        continue
                    
                    latest_chapter_num = latest_chapter.get('chapter', 'N/A')
                    
                    # Update last checked timestamp
                    tracked_manga[manga_key]['last_checked'] = self.format_timestamp(datetime.now(timezone.utc))
                    updates_made = True
                    
                    # Check if there's a new chapter
                    try:
                        # Convert to float for comparison if possible
                        current = float(manga_data['latest_chapter']) if manga_data['latest_chapter'] != 'N/A' else 0
                        new = float(latest_chapter_num) if latest_chapter_num != 'N/A' else 0
                        
                        if new > current:
                            log.info(f"New chapter found for {manga_data['title']}: {latest_chapter_num} (current: {manga_data['latest_chapter']})")
                            
                            # Update the latest chapter number
                            tracked_manga[manga_key]['latest_chapter'] = latest_chapter_num
                            
                            # Add to updates found
                            updates_found.append({
                                'manga_key': manga_key,
                                'manga_title': manga_data['title'],
                                'previous_chapter': manga_data['latest_chapter'],
                                'new_chapter': latest_chapter_num,
                                'chapter_data': latest_chapter,
                                'source': source
                            })
                    except ValueError:
                        # Handle non-numeric chapter numbers
                        if latest_chapter_num != manga_data['latest_chapter']:
                            log.info(f"New chapter found for {manga_data['title']}: {latest_chapter_num} (current: {manga_data['latest_chapter']})")
                            
                            # Update the latest chapter number
                            tracked_manga[manga_key]['latest_chapter'] = latest_chapter_num
                            
                            # Add to updates found
                            updates_found.append({
                                'manga_key': manga_key,
                                'manga_title': manga_data['title'],
                                'previous_chapter': manga_data['latest_chapter'],
                                'new_chapter': latest_chapter_num,
                                'chapter_data': latest_chapter,
                                'source': source
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
                            source = update.get('source', 'unknown').upper()
                            chapter_url = chapter_data.get('url', '')
                            chapter_info = chapter_data.get('chapter_info', f"Chapter {update['new_chapter']}")
                            
                            embed = discord.Embed(
                                title=f"📢 New Chapter Alert: {update['manga_title']}",
                                description=f"**{chapter_info}** is now available on **{source}**!",
                                color=discord.Color.gold(),
                                url=chapter_url
                            )
                            
                            # Add previous chapter info
                            if update['previous_chapter'] != 'N/A':
                                embed.add_field(name="Previous Chapter", value=update['previous_chapter'], inline=True)
                            
                            # Add source info
                            embed.add_field(name="Source", value=source, inline=True)
                            
                            embed.set_footer(text="Manga Tracker")
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
    cog = MangaTracker(bot)
    await bot.add_cog(cog)
