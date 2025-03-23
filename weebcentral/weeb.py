import asyncio
import logging
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union
from urllib.parse import quote, urljoin
from collections import defaultdict

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
    
    async def get_latest_releases(self, limit=10):
        """Get the latest releases from MangaDex"""
        params = {
            "limit": limit,
            "order[publishAt]": "desc",
            "contentRating[]": ["safe", "suggestive", "erotica", "pornographic"],
            "includes[]": ["manga", "scanlation_group"]
        }
        
        response = await self.make_request("/chapter", params)
        
        if not response or "data" not in response:
            return []
        
        # Format the results
        releases = []
        for chapter in response["data"]:
            chapter_id = chapter["id"]
            attributes = chapter["attributes"]
            
            # Get manga title
            manga_title = "Unknown Manga"
            manga_id = None
            for relationship in chapter.get("relationships", []):
                if relationship["type"] == "manga":
                    manga_id = relationship["id"]
                    if "attributes" in relationship and "title" in relationship["attributes"]:
                        titles = relationship["attributes"]["title"]
                        # Try to get English title, fallback to first available
                        manga_title = (titles.get("en") or 
                                    titles.get("jp") or 
                                    titles.get("ja") or 
                                    next(iter(titles.values())) if titles else "Unknown Manga")
            
            # Get chapter number
            chapter_num = attributes.get("chapter", "N/A")
            if chapter_num == "":
                chapter_num = "N/A"
            
            # Get published date
            published_at = attributes.get("publishAt", "")
            
            # Create timestamp for sorting
            try:
                if published_at:
                    release_time = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                else:
                    release_time = datetime.now(timezone.utc)
                
                release_timestamp = release_time.timestamp()
            except ValueError:
                release_timestamp = datetime.now(timezone.utc).timestamp()
            
            # Add to releases list
            releases.append({
                'manga_title': manga_title,
                'chapter_num': chapter_num,
                'url': f"https://mangadex.org/chapter/{chapter_id}",
                'source': 'mangadex',
                'released_at': self.format_timestamp(release_time) if hasattr(self, 'format_timestamp') else str(release_time),
                'release_timestamp': release_timestamp
            })
        
        return releases


class TCBScansAPI:
    """API wrapper for TCB Scans (web scraping based)"""
    
    def __init__(self):
        self.base_url = "https://tcbscans.com"
        self.session = None
        self.project_list = []  # Cache for available manga
    
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
    
    async def get_available_manga(self, force_refresh=False):
        """Get a list of all available manga on TCB Scans"""
        if not force_refresh and self.project_list:
            return self.project_list
        
        # Get the projects page
        html = await self.get_webpage(f"{self.base_url}/projects")
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        self.project_list = []
        
        # Look for manga cards/items in different potential layouts
        manga_items = (
            soup.select(".bg-card") or 
            soup.select(".manga-card") or 
            soup.select(".grid-item") or
            soup.select(".project-card") or
            soup.select("a[href^='/mangas/']")
        )
        
        log.info(f"Found {len(manga_items)} manga items on TCB Scans projects page")
        
        for item in manga_items:
            try:
                # Extract manga info
                manga_link = item.select_one("a") if not item.name == 'a' else item
                if not manga_link or not manga_link.get("href"):
                    continue
                    
                manga_url = manga_link.get("href")
                # Make sure it's a full URL
                if not manga_url.startswith("http"):
                    manga_url = urljoin(self.base_url, manga_url)
                    
                manga_id = manga_url.split("/")[-1] if "/" in manga_url else manga_url
                
                # Get title from different possible elements
                title_elem = (
                    item.select_one("h5") or 
                    item.select_one(".card-title") or 
                    item.select_one(".manga-title") or
                    item.select_one(".title") or
                    manga_link
                )
                manga_title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
                
                # Get cover image
                cover_url = None
                img_elem = item.select_one("img")
                if img_elem and "src" in img_elem.attrs:
                    cover_url = img_elem["src"]
                    # Make sure URL is absolute
                    if not cover_url.startswith("http"):
                        cover_url = urljoin(self.base_url, cover_url)
                
                # Add to results list
                self.project_list.append({
                    "id": manga_id,
                    "title": manga_title,
                    "url": manga_url,
                    "cover_url": cover_url,
                    "source": "tcbscans"
                })
            except Exception as e:
                log.error(f"Error parsing manga item: {str(e)}")
        
        # Add direct URLs for popular manga that TCB Scans is known to translate
        # Even if we couldn't find them on the projects page
        known_titles = [
            # Core TCB Scans manga
            {"title": "One Piece", "id": "one-piece", "url": f"{self.base_url}/mangas/1/one-piece"},
            {"title": "My Hero Academia", "id": "my-hero-academia", "url": f"{self.base_url}/mangas/2/my-hero-academia"},
            {"title": "Jujutsu Kaisen", "id": "jujutsu-kaisen", "url": f"{self.base_url}/mangas/3/jujutsu-kaisen"},
            {"title": "Black Clover", "id": "black-clover", "url": f"{self.base_url}/mangas/4/black-clover"},
            {"title": "Chainsaw Man", "id": "chainsaw-man", "url": f"{self.base_url}/mangas/5/chainsaw-man"},
            {"title": "Dragon Ball Super", "id": "dragon-ball-super", "url": f"{self.base_url}/mangas/6/dragon-ball-super"},
            {"title": "Hunter X Hunter", "id": "hunter-x-hunter", "url": f"{self.base_url}/mangas/7/hunter-x-hunter"},
            
            # Additional popular manga
            {"title": "One Punch Man", "id": "one-punch-man", "url": f"{self.base_url}/mangas/8/one-punch-man"},
            {"title": "Boruto", "id": "boruto", "url": f"{self.base_url}/mangas/9/boruto"},
            {"title": "Demon Slayer", "id": "demon-slayer", "url": f"{self.base_url}/mangas/10/demon-slayer"},
            {"title": "Attack on Titan", "id": "attack-on-titan", "url": f"{self.base_url}/mangas/11/attack-on-titan"},
            {"title": "Tokyo Ghoul", "id": "tokyo-ghoul", "url": f"{self.base_url}/mangas/12/tokyo-ghoul"},
            {"title": "Naruto", "id": "naruto", "url": f"{self.base_url}/mangas/13/naruto"},
            {"title": "Bleach", "id": "bleach", "url": f"{self.base_url}/mangas/14/bleach"},
            {"title": "Dr. Stone", "id": "dr-stone", "url": f"{self.base_url}/mangas/15/dr-stone"},
            {"title": "The Promised Neverland", "id": "the-promised-neverland", "url": f"{self.base_url}/mangas/16/the-promised-neverland"},
            {"title": "Haikyuu", "id": "haikyuu", "url": f"{self.base_url}/mangas/17/haikyuu"},
            
            # Aliases/abbreviations
            {"title": "OPM", "id": "one-punch-man", "url": f"{self.base_url}/mangas/8/one-punch-man"},
            {"title": "MHA", "id": "my-hero-academia", "url": f"{self.base_url}/mangas/2/my-hero-academia"},
            {"title": "JJK", "id": "jujutsu-kaisen", "url": f"{self.base_url}/mangas/3/jujutsu-kaisen"},
            {"title": "CSM", "id": "chainsaw-man", "url": f"{self.base_url}/mangas/5/chainsaw-man"},
            {"title": "DBS", "id": "dragon-ball-super", "url": f"{self.base_url}/mangas/6/dragon-ball-super"},
            {"title": "HxH", "id": "hunter-x-hunter", "url": f"{self.base_url}/mangas/7/hunter-x-hunter"},
            {"title": "AOT", "id": "attack-on-titan", "url": f"{self.base_url}/mangas/11/attack-on-titan"}
        ]
        
        # Add known manga if not already in list
        for manga in known_titles:
            if not any(m["title"].lower() == manga["title"].lower() for m in self.project_list):
                manga["source"] = "tcbscans"
                self.project_list.append(manga)
        
        return self.project_list
    
    async def search_manga(self, title):
        """Search for manga by title"""
        # Get all available manga first
        all_manga = await self.get_available_manga()
        
        if not all_manga:
            return []
        
        # Normalize the search query
        title_lower = title.lower()
        title_words = title_lower.split()
        
        # Perform the search with different matching strategies
        exact_matches = []
        partial_matches = []
        word_matches = []
        
        for manga in all_manga:
            manga_title = manga["title"].lower()
            
            # Exact match
            if title_lower == manga_title:
                exact_matches.append(manga)
                continue
                
            # Partial match (title is contained in manga title)
            if title_lower in manga_title:
                partial_matches.append(manga)
                continue
                
            # Word match (all words in title appear in manga title)
            if all(word in manga_title for word in title_words):
                word_matches.append(manga)
                continue
        
        # Combine results in order of relevance
        results = exact_matches + partial_matches + word_matches
        
        # If we have abbreviations like "OPM" for "One Punch Man", try to handle them
        if not results and len(title) <= 5:
            # Could be an abbreviation, try matching initials
            for manga in all_manga:
                manga_title = manga["title"]
                # Get initials (first letter of each word)
                initials = ''.join(word[0].lower() for word in manga_title.split() if word)
                if title_lower == initials:
                    results.append(manga)
        
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
        title_elem = soup.select_one("h1") or soup.select_one("h2") or soup.select_one(".manga-title")
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Title"
        
        # Get description
        desc_elem = soup.select_one(".description") or soup.select_one(".synopsis")
        description = desc_elem.get_text(strip=True) if desc_elem else "No description available."
        
        # Get cover image
        cover_url = None
        img_elem = soup.select_one(".manga-cover img") or soup.select_one(".manga-image img") or soup.select_one("img")
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
        chapter_items = (
            soup.select(".chapter-item") or 
            soup.select(".chapters-list li") or
            soup.select("a[href^='/chapters/']") or
            soup.select("a[href*='/chapter/']")
        )
        
        for item in chapter_items:
            try:
                # Extract chapter info
                link = item if item.name == 'a' else item.select_one("a")
                if not link or not link.get("href"):
                    continue
                
                chapter_url = link.get("href")
                # Make sure URL is absolute
                if not chapter_url.startswith("http"):
                    chapter_url = urljoin(self.base_url, chapter_url)
                    
                chapter_id = chapter_url.split("/")[-1] if "/" in chapter_url else chapter_url
                
                # Extract chapter title/number
                title_text = link.get_text(strip=True)
                
                # Try to extract chapter number with regex
                chapter_num_match = re.search(r'Chapter\s+(\d+(?:\.\d+)?)', title_text, re.IGNORECASE)
                if chapter_num_match:
                    chapter_num = chapter_num_match.group(1)
                else:
                    # Try alternate formats (e.g., "#123")
                    alt_match = re.search(r'#(\d+(?:\.\d+)?)', title_text)
                    chapter_num = alt_match.group(1) if alt_match else "N/A"
                
                # Create readable chapter info
                chapter_info = title_text
                
                # Get the date if available
                date_elem = item.select_one(".release-date") or item.select_one(".date")
                date_text = date_elem.get_text(strip=True) if date_elem else ""
                
                # Try to parse date if available
                release_time = None
                if date_text:
                    try:
                        # Handle common date formats
                        if re.match(r'\d{4}-\d{2}-\d{2}', date_text):
                            # ISO format
                            release_time = datetime.fromisoformat(date_text)
                        elif re.match(r'\d{2}/\d{2}/\d{4}', date_text):
                            # MM/DD/YYYY format
                            release_time = datetime.strptime(date_text, '%m/%d/%Y')
                        elif re.match(r'\w+ \d{1,2}, \d{4}', date_text):
                            # Month Day, Year format
                            release_time = datetime.strptime(date_text, '%B %d, %Y')
                        # Add other date formats as needed
                    except ValueError:
                        pass
                
                # Default to current time if parsing failed
                if not release_time:
                    release_time = datetime.now(timezone.utc)
                
                chapters.append({
                    "id": chapter_id,
                    "chapter": chapter_num,
                    "title": title_text,
                    "chapter_info": chapter_info,
                    "published_at": date_text,
                    "published_datetime": release_time,
                    "url": chapter_url,
                    "source": "tcbscans"
                })
            except Exception as e:
                log.error(f"Error parsing chapter item: {str(e)}")
        
        # Sort chapters by number in descending order
        try:
            chapters.sort(key=lambda x: float(x["chapter"]) if x["chapter"] != "N/A" else 0, reverse=True)
        except (ValueError, TypeError):
            # If sorting fails, keep original order
            pass
        
        return chapters
    
    async def get_latest_releases(self, limit=10):
        """Get the latest releases from TCB Scans"""
        # TCB Scans usually lists latest releases on their home page
        html = await self.get_webpage(self.base_url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find the latest releases section
        releases = []
        release_items = (
            soup.select(".latest-release") or
            soup.select(".new-chapters-list li") or
            soup.select(".home-chapter-item") or
            soup.select("a[href*='/chapter/']")
        )
        
        log.info(f"Found {len(release_items)} release items on TCB Scans home page")
        
        for item in release_items[:limit]:  # Limit to requested number
            try:
                # Extract chapter info
                link = item if item.name == 'a' else item.select_one("a")
                if not link or not link.get("href"):
                    continue
                
                chapter_url = link.get("href")
                # Make sure URL is absolute
                if not chapter_url.startswith("http"):
                    chapter_url = urljoin(self.base_url, chapter_url)
                
                # Extract title text
                title_text = link.get_text(strip=True)
                
                # Try to separate manga title from chapter
                manga_title = "Unknown Manga"
                chapter_num = "N/A"
                
                # Look for patterns like "Manga Title - Chapter X" or "Manga Title Chapter X"
                title_match = re.search(r'^(.+?)(?:\s*[-:]\s*|\s+)Chapter\s+(\d+(?:\.\d+)?)', title_text, re.IGNORECASE)
                if title_match:
                    manga_title = title_match.group(1).strip()
                    chapter_num = title_match.group(2)
                else:
                    # Try alternate format with hash (e.g., "Manga Title #123")
                    alt_match = re.search(r'^(.+?)\s+#(\d+(?:\.\d+)?)', title_text)
                    if alt_match:
                        manga_title = alt_match.group(1).strip()
                        chapter_num = alt_match.group(2)
                
                # Get release date if available
                date_elem = item.select_one(".release-date") or item.select_one(".date")
                date_text = date_elem.get_text(strip=True) if date_elem else ""
                
                # Try to parse date
                release_time = datetime.now(timezone.utc)
                if date_text:
                    try:
                        # Handle relative dates like "2 days ago"
                        if "ago" in date_text.lower():
                            days_match = re.search(r'(\d+)\s*days?\s*ago', date_text, re.IGNORECASE)
                            hours_match = re.search(r'(\d+)\s*hours?\s*ago', date_text, re.IGNORECASE)
                            mins_match = re.search(r'(\d+)\s*mins?\s*ago', date_text, re.IGNORECASE)
                            
                            if days_match:
                                release_time = datetime.now(timezone.utc) - timedelta(days=int(days_match.group(1)))
                            elif hours_match:
                                release_time = datetime.now(timezone.utc) - timedelta(hours=int(hours_match.group(1)))
                            elif mins_match:
                                release_time = datetime.now(timezone.utc) - timedelta(minutes=int(mins_match.group(1)))
                            elif "today" in date_text.lower():
                                release_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                            elif "yesterday" in date_text.lower():
                                release_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                        # Try standard date formats
                        elif re.match(r'\d{4}-\d{2}-\d{2}', date_text):
                            release_time = datetime.fromisoformat(date_text)
                        elif re.match(r'\d{2}/\d{2}/\d{4}', date_text):
                            release_time = datetime.strptime(date_text, '%m/%d/%Y')
                    except ValueError:
                        # If parsing fails, keep current time
                        pass
                
                release_timestamp = release_time.timestamp()
                
                releases.append({
                    'manga_title': manga_title,
                    'chapter_num': chapter_num,
                    'url': chapter_url,
                    'source': 'tcbscans',
                    'released_at': date_text or "Recent",
                    'release_timestamp': release_timestamp
                })
            except Exception as e:
                log.error(f"Error parsing release item: {str(e)}")
        
        return releases


class ReleasePattern:
    """Class to analyze and predict manga release patterns"""
    
    def __init__(self, title, history=None):
        self.title = title
        self.history = history or []  # List of timestamp tuples (chapter_num, release_time)
        self.day_counts = defaultdict(int)  # Count of releases by day of week
        self.weekday_pattern = None  # Most common release day
        self.weekday_confidence = 0.0  # Confidence in the pattern
        self.avg_interval = None  # Average days between releases
        self.next_expected = None  # Next expected release date
        self.updated_at = datetime.now(timezone.utc)
    
    def add_release(self, chapter_num, release_time):
        """Add a release to the history"""
        if isinstance(release_time, str):
            try:
                release_time = datetime.fromisoformat(release_time.replace('Z', '+00:00'))
            except ValueError:
                # If we can't parse, use current time
                release_time = datetime.now(timezone.utc)
        
        self.history.append((chapter_num, release_time))
        self.history.sort(key=lambda x: float(x[0]) if x[0] != "N/A" else 0)
        self.updated_at = datetime.now(timezone.utc)
        self._analyze_pattern()
    
    def _analyze_pattern(self):
        """Analyze the release pattern"""
        if len(self.history) < 2:
            # Not enough data to determine pattern
            return
        
        # Count releases by day of week
        self.day_counts = defaultdict(int)
        for _, release_time in self.history:
            weekday = release_time.weekday()
            self.day_counts[weekday] += 1
        
        # Determine most common release day
        if self.day_counts:
            total_releases = sum(self.day_counts.values())
            most_common_day = max(self.day_counts.items(), key=lambda x: x[1])
            self.weekday_pattern = most_common_day[0]
            self.weekday_confidence = most_common_day[1] / total_releases
        
        # Calculate average interval between releases
        intervals = []
        for i in range(1, len(self.history)):
            try:
                prev_time = self.history[i-1][1]
                curr_time = self.history[i][1]
                interval = (curr_time - prev_time).days
                if 0 < interval < 90:  # Ignore negative or very long intervals
                    intervals.append(interval)
            except (TypeError, ValueError):
                continue
        
        if intervals:
            self.avg_interval = sum(intervals) / len(intervals)
            
            # Predict next release
            if self.history and self.avg_interval:
                last_release = self.history[-1][1]
                if self.weekday_pattern is not None and self.weekday_confidence > 0.5:
                    # If we have a strong day pattern, predict next occurrence of that day
                    days_until_next = (self.weekday_pattern - last_release.weekday()) % 7
                    if days_until_next == 0:
                        days_until_next = 7  # Next week
                    self.next_expected = last_release + timedelta(days=days_until_next)
                else:
                    # Otherwise use average interval
                    self.next_expected = last_release + timedelta(days=round(self.avg_interval))
    
    def get_check_frequency(self):
        """Determine how frequently to check for updates"""
        if not self.avg_interval:
            return "standard"  # Default to standard if we don't have enough data
        
        # If we're within 1 day of expected release, check frequently
        if self.next_expected:
            time_until_next = self.next_expected - datetime.now(timezone.utc)
            if 0 <= time_until_next.total_seconds() <= 86400:  # Within 24 hours
                return "frequent"
        
        # Use average interval to determine general frequency
        if self.avg_interval <= 7:
            return "standard"  # Weekly or more frequent manga
        elif 7 < self.avg_interval <= 14:
            return "standard"  # Bi-weekly manga
        else:
            return "slow"  # Monthly or slower manga
    
    def to_dict(self):
        """Convert to dictionary for storage"""
        return {
            "title": self.title,
            "history": [(chapter, release_time.isoformat()) for chapter, release_time in self.history],
            "weekday_pattern": self.weekday_pattern,
            "weekday_confidence": self.weekday_confidence,
            "avg_interval": self.avg_interval,
            "next_expected": self.next_expected.isoformat() if self.next_expected else None,
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create from dictionary"""
        pattern = cls(data["title"])
        
        # Convert history strings back to datetime objects
        history = []
        for chapter, time_str in data.get("history", []):
            try:
                release_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                history.append((chapter, release_time))
            except ValueError:
                continue
        
        pattern.history = history
        pattern.weekday_pattern = data.get("weekday_pattern")
        pattern.weekday_confidence = data.get("weekday_confidence", 0.0)
        pattern.avg_interval = data.get("avg_interval")
        
        if data.get("next_expected"):
            try:
                pattern.next_expected = datetime.fromisoformat(data["next_expected"].replace('Z', '+00:00'))
            except ValueError:
                pattern.next_expected = None
        
        if data.get("updated_at"):
            try:
                pattern.updated_at = datetime.fromisoformat(data["updated_at"].replace('Z', '+00:00'))
            except ValueError:
                pattern.updated_at = datetime.now(timezone.utc)
        
        return pattern


class MangaTracker(commands.Cog):
    """Track manga releases from MangaDex and TCB Scans with adaptive learning"""
    
    default_guild_settings = {
        "notification_channel": None,
    }
    
    default_global_settings = {
        "tracked_manga": {},
        "release_patterns": {},
        "frequency_overrides": {},
        "latest_releases": {},
        "last_releases_check": None
    }
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.mangadex_api = MangaDexAPI()
        self.tcbscans_api = TCBScansAPI()
        self.config = Config.get_conf(self, identifier=9879845123, force_registration=True)
        
        # Register default settings
        self.config.register_guild(**self.default_guild_settings)
        self.config.register_global(**self.default_global_settings)
        
        # In-memory cache of release patterns
        self.patterns = {}
        
        # Task timers for different update frequencies
        self.frequent_check_task = None  # Every 1 hour
        self.standard_check_task = None  # Every 6 hours
        self.slow_check_task = None      # Every 24 hours
        self.releases_check_task = None  # Every 2 hours
        
        # Start the background tasks
        self.setup_tasks()
    
    def setup_tasks(self):
        """Set up all background tasks"""
        self.frequent_check_task = self.bot.loop.create_task(self.check_frequent_updates())
        self.standard_check_task = self.bot.loop.create_task(self.check_standard_updates())
        self.slow_check_task = self.bot.loop.create_task(self.check_slow_updates())
        self.releases_check_task = self.bot.loop.create_task(self.check_latest_releases())
    
    async def initialize(self):
        """Load saved data into memory"""
        # Load release patterns
        saved_patterns = await self.config.release_patterns()
        for manga_key, pattern_data in saved_patterns.items():
            self.patterns[manga_key] = ReleasePattern.from_dict(pattern_data)
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self.frequent_check_task:
            self.frequent_check_task.cancel()
        if self.standard_check_task:
            self.standard_check_task.cancel()
        if self.slow_check_task:
            self.slow_check_task.cancel()
        if self.releases_check_task:
            self.releases_check_task.cancel()
        
        # Close API sessions
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
    
    def format_relative_time(self, dt):
        """Format a datetime as a relative time (e.g., "2 days ago")"""
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except ValueError:
                return "Unknown time"
        
        now = datetime.now(timezone.utc)
        delta = now - dt
        
        if delta.days < 0:
            return "in the future"
        elif delta.days == 0:
            hours = delta.seconds // 3600
            if hours == 0:
                minutes = delta.seconds // 60
                if minutes == 0:
                    return "just now"
                elif minutes == 1:
                    return "1 minute ago"
                else:
                    return f"{minutes} minutes ago"
            elif hours == 1:
                return "1 hour ago"
            else:
                return f"{hours} hours ago"
        elif delta.days == 1:
            return "yesterday"
        elif delta.days < 7:
            return f"{delta.days} days ago"
        elif delta.days < 30:
            weeks = delta.days // 7
            if weeks == 1:
                return "1 week ago"
            else:
                return f"{weeks} weeks ago"
        elif delta.days < 365:
            months = delta.days // 30
            if months == 1:
                return "1 month ago"
            else:
                return f"{months} months ago"
        else:
            years = delta.days // 365
            if years == 1:
                return "1 year ago"
            else:
                return f"{years} years ago"
    
    def get_next_release_estimate(self, manga_key):
        """Get a human-readable estimate of the next release"""
        if manga_key not in self.patterns:
            return "Unknown"
        
        pattern = self.patterns[manga_key]
        if not pattern.next_expected:
            return "Unknown"
        
        now = datetime.now(timezone.utc)
        if pattern.next_expected < now:
            # Expected date is in the past
            if pattern.avg_interval:
                # Calculate new expected date based on average interval
                days_since = (now - pattern.next_expected).days
                cycles = max(1, days_since // pattern.avg_interval + 1)
                new_expected = pattern.next_expected + timedelta(days=cycles * pattern.avg_interval)
                return f"Possibly {self.format_relative_time(new_expected)} (overdue)"
            return "Overdue"
        
        days_until = (pattern.next_expected - now).days
        weekday_name = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][pattern.next_expected.weekday()]
        
        if days_until == 0:
            return f"Expected today ({weekday_name})"
        elif days_until == 1:
            return f"Expected tomorrow ({weekday_name})"
        elif days_until < 7:
            return f"Expected in {days_until} days ({weekday_name})"
        else:
            return f"Expected on {pattern.next_expected.strftime('%B %d')} ({weekday_name})"
    
    def get_pattern_summary(self, manga_key):
        """Get a human-readable summary of the release pattern"""
        if manga_key not in self.patterns:
            return "No pattern data available"
        
        pattern = self.patterns[manga_key]
        if not pattern.avg_interval:
            return "Not enough data to determine pattern"
        
        weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        summary = []
        
        # Format average interval
        if pattern.avg_interval < 7:
            interval_text = f"Multiple times per week (every {pattern.avg_interval:.1f} days)"
        elif 7 <= pattern.avg_interval < 10:
            interval_text = "Weekly"
        elif 10 <= pattern.avg_interval < 18:
            interval_text = "Bi-weekly"
        elif 18 <= pattern.avg_interval < 40:
            interval_text = "Monthly"
        else:
            interval_text = f"Every {pattern.avg_interval:.1f} days"
        summary.append(interval_text)
        
        # Add day pattern if confidence is high enough
        if pattern.weekday_pattern is not None and pattern.weekday_confidence >= 0.5:
            day_name = weekday_names[pattern.weekday_pattern]
            confidence = int(pattern.weekday_confidence * 100)
            summary.append(f"Usually on {day_name}s ({confidence}% confidence)")
        
        # Add next expected
        if pattern.next_expected:
            summary.append(self.get_next_release_estimate(manga_key))
        
        return " • ".join(summary)
    
    async def update_release_pattern(self, manga_key, manga_data, chapter_data=None):
        """Update the release pattern for a manga"""
        title = manga_data['title']
        
        # Create or retrieve pattern
        if manga_key not in self.patterns:
            self.patterns[manga_key] = ReleasePattern(title)
        
        pattern = self.patterns[manga_key]
        
        # Add the latest chapter to the pattern if provided
        if chapter_data:
            chapter_num = chapter_data.get('chapter', 'N/A')
            
            # Get release time
            if 'published_datetime' in chapter_data:
                release_time = chapter_data['published_datetime']
            elif 'published_at' in chapter_data:
                # Try to parse the date string
                try:
                    release_time = datetime.fromisoformat(chapter_data['published_at'].replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    # If we can't parse, use current time
                    release_time = datetime.now(timezone.utc)
            else:
                release_time = datetime.now(timezone.utc)
            
            pattern.add_release(chapter_num, release_time)
        
        # Save the updated pattern
        patterns_dict = await self.config.release_patterns()
        patterns_dict[manga_key] = pattern.to_dict()
        await self.config.release_patterns.set(patterns_dict)
    
    def determine_check_frequency(self, manga_key, manga_data):
        """Determine how frequently to check this manga for updates"""
        # Check for manual override
        frequency_overrides = self.config.frequency_overrides()
        if manga_key in frequency_overrides:
            return frequency_overrides[manga_key]
        
        # Check release pattern
        if manga_key in self.patterns:
            return self.patterns[manga_key].get_check_frequency()
        
        # Default frequency based on source
        source = manga_data.get('source', 'unknown')
        if source == 'mangadex':
            return "standard"
        elif source == 'tcbscans':
            return "frequent"  # TCB Scans releases are typically more time-sensitive
        
        return "standard"
    
    @commands.group(name="manga")
    async def manga(self, ctx: commands.Context):
        """Manga tracking commands"""
        if ctx.invoked_subcommand is None:
            help_text = (
                "📚 **Manga Tracker**\n\n"
                "Available commands:\n"
                "`[p]manga search <title>` - Search for manga on MangaDex\n"
                "`[p]manga tcbsearch <title>` - Search for manga on TCB Scans\n"
                "`[p]manga track <title>` - Track a manga for new chapter releases\n"
                "`[p]manga untrack <title>` - Stop tracking a manga\n"
                "`[p]manga list` - List all tracked manga\n"
                "`[p]manga info <title>` - Show detailed info for a tracked manga\n"
                "`[p]manga pattern <title>` - Show release pattern for a manga\n"
                "`[p]manga setfreq <title> <frequency>` - Set update frequency override\n"
                "`[p]manga setnotify [channel]` - Set the channel for notifications\n"
                "`[p]manga check` - Manually check for updates\n"
                "`[p]manga newreleases` - Show the latest manga releases\n"
                "`[p]manga refresh` - Refresh cached manga data"
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
        try:
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
                    
                    # Initialize release pattern
                    await self.update_release_pattern(manga_key, tracked_manga[manga_key], latest_chapter)
                    
                    # Save to config
                    await self.config.tracked_manga.set(tracked_manga)
                    
                    # Set notification channel if not already set
                    if await self.config.guild(ctx.guild).notification_channel() is None:
                        await self.config.guild(ctx.guild).notification_channel.set(ctx.channel.id)
                    
                    pattern_text = f"\n\nI'll learn the release pattern over time to predict when new chapters will come out."
                    await ctx.send(f"✅ Now tracking **{manga_title}** from **{source.upper()}**! Latest chapter: {latest_chapter_num}{pattern_text}")
                    
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
            
            # Also remove from release patterns
            patterns = await self.config.release_patterns()
            if manga_key_to_remove in patterns:
                del patterns[manga_key_to_remove]
                await self.config.release_patterns.set(patterns)
                if manga_key_to_remove in self.patterns:
                    del self.patterns[manga_key_to_remove]
            
            # Also remove from frequency overrides
            overrides = await self.config.frequency_overrides()
            if manga_key_to_remove in overrides:
                del overrides[manga_key_to_remove]
                await self.config.frequency_overrides.set(overrides)
            
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
                last_checked = manga_data.get('last_checked', 'Unknown')
                if isinstance(last_checked, str) and ('+' in last_checked or 'T' in last_checked):
                    last_checked = self.format_timestamp(last_checked)
                
                source = manga_data.get('source', 'unknown').upper()
                latest_chapter = manga_data.get('latest_chapter', 'N/A')
                
                # Get pattern info
                pattern_info = "No pattern data yet"
                if manga_key in self.patterns:
                    pattern_info = self.get_pattern_summary(manga_key)
                
                embed.add_field(
                    name=f"{manga_data['title']} ({source})",
                    value=f"Latest Chapter: {latest_chapter}\n"
                          f"Last Checked: {self.format_relative_time(last_checked) if isinstance(last_checked, datetime) else last_checked}\n"
                          f"Pattern: {pattern_info}",
                    inline=False
                )
            
            embed.set_footer(text=f"Page {i+1}/{len(chunks)}")
            pages.append(embed)
        
        # If only one page, just send it
        if len(pages) == 1:
            return await ctx.send(embed=pages[0])
        
        # Otherwise use paginated menu
        await menu(ctx, pages, DEFAULT_CONTROLS)
    
    @manga.command(name="info")
    async def manga_info(self, ctx: commands.Context, *, title: str):
        """Show detailed info for a tracked manga"""
        tracked_manga = await self.config.tracked_manga()
        
        # Find manga by title
        manga_key = None
        manga_data = None
        
        for key, data in tracked_manga.items():
            if data['title'].lower() == title.lower():
                manga_key = key
                manga_data = data
                break
        
        if not manga_data:
            return await ctx.send(f"❌ No tracked manga found with title '{title}'")
        
        # Get source-specific API
        source = manga_data.get('source', 'unknown')
        manga_id = manga_data.get('id', '')
        manga_url = manga_data.get('url', '')
        
        # Get detailed info
        detailed_info = None
        
        if source == 'mangadex':
            detailed_info = await self.mangadex_api.get_manga_details(manga_id)
        elif source == 'tcbscans':
            if manga_url:
                detailed_info = await self.tcbscans_api.get_manga_details(manga_url)
            else:
                detailed_info = await self.tcbscans_api.get_manga_details(manga_id)
        
        if not detailed_info:
            return await ctx.send(f"❌ Failed to get detailed info for '{title}'")
        
        # Create embed
        embed = discord.Embed(
            title=detailed_info.get('title', manga_data['title']),
            description=detailed_info.get('description', 'No description available.'),
            color=await ctx.embed_color(),
            timestamp=datetime.now()
        )
        
        # Add status
        status = detailed_info.get('status', 'Unknown').capitalize()
        embed.add_field(name="Status", value=status, inline=True)
        
        # Add source
        embed.add_field(name="Source", value=source.upper(), inline=True)
        
        # Add latest chapter
        latest_chapter = manga_data.get('latest_chapter', 'N/A')
        embed.add_field(name="Latest Chapter", value=latest_chapter, inline=True)
        
        # Add last checked
        last_checked = manga_data.get('last_checked', 'Unknown')
        if isinstance(last_checked, str) and ('+' in last_checked or 'T' in last_checked):
            last_checked = self.format_timestamp(last_checked)
        embed.add_field(
            name="Last Checked", 
            value=self.format_relative_time(last_checked) if isinstance(last_checked, datetime) else last_checked, 
            inline=True
        )
        
        # Add release pattern info
        if manga_key in self.patterns:
            pattern = self.patterns[manga_key]
            
            if pattern.avg_interval:
                embed.add_field(
                    name="Average Release Interval",
                    value=f"{pattern.avg_interval:.1f} days",
                    inline=True
                )
            
            if pattern.weekday_pattern is not None and pattern.weekday_confidence >= 0.5:
                weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                day_name = weekday_names[pattern.weekday_pattern]
                confidence = int(pattern.weekday_confidence * 100)
                embed.add_field(
                    name="Release Day Pattern",
                    value=f"{day_name}s ({confidence}% confidence)",
                    inline=True
                )
            
            if pattern.next_expected:
                embed.add_field(
                    name="Next Chapter Estimate",
                    value=self.get_next_release_estimate(manga_key),
                    inline=True
                )
                
            if pattern.history and len(pattern.history) >= 2:
                # Add last few chapter releases
                last_releases = pattern.history[-3:]  # Last 3 releases
                releases_text = "\n".join([
                    f"Ch. {ch_num}: {self.format_timestamp(release_time)}" 
                    for ch_num, release_time in reversed(last_releases)
                ])
                embed.add_field(
                    name="Recent Releases",
                    value=releases_text,
                    inline=False
                )
        
        # Set thumbnail to cover if available
        if detailed_info.get('cover_url'):
            embed.set_thumbnail(url=detailed_info['cover_url'])
        
        # Add link to read
        if source == 'mangadex':
            embed.url = f"https://mangadex.org/title/{manga_id}"
        elif source == 'tcbscans' and manga_url:
            embed.url = manga_url
        
        await ctx.send(embed=embed)
    
    @manga.command(name="pattern")
    async def manga_pattern(self, ctx: commands.Context, *, title: str):
        """Show release pattern information for a tracked manga"""
        tracked_manga = await self.config.tracked_manga()
        
        # Find manga by title
        manga_key = None
        manga_data = None
        
        for key, data in tracked_manga.items():
            if data['title'].lower() == title.lower():
                manga_key = key
                manga_data = data
                break
        
        if not manga_data:
            return await ctx.send(f"❌ No tracked manga found with title '{title}'")
        
        if manga_key not in self.patterns:
            return await ctx.send(f"❌ No release pattern data available for '{title}' yet. This will be collected over time as new chapters are released.")
        
        pattern = self.patterns[manga_key]
        
        if not pattern.history or len(pattern.history) < 2:
            return await ctx.send(f"❌ Not enough release data for '{title}' yet. Need at least 2 releases to analyze patterns.")
        
        # Create embed
        embed = discord.Embed(
            title=f"Release Pattern for {manga_data['title']}",
            color=await ctx.embed_color(),
            timestamp=datetime.now()
        )
        
        # Add basic pattern info
        if pattern.avg_interval:
            embed.add_field(
                name="Average Release Interval",
                value=f"{pattern.avg_interval:.1f} days",
                inline=True
            )
        
        # Add release day pattern
        weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        weekday_distribution = []
        
        for day, count in sorted(pattern.day_counts.items()):
            day_name = weekday_names[day]
            percentage = int((count / sum(pattern.day_counts.values())) * 100)
            weekday_distribution.append(f"{day_name}: {count} ({percentage}%)")
        
        if weekday_distribution:
            embed.add_field(
                name="Release Day Distribution",
                value="\n".join(weekday_distribution),
                inline=True
            )
        
        # Add next expected release
        if pattern.next_expected:
            embed.add_field(
                name="Next Chapter Estimate",
                value=self.get_next_release_estimate(manga_key),
                inline=True
            )
        
        # Add release history
        history_text = ""
        for ch_num, release_time in reversed(pattern.history):
            history_text += f"Ch. {ch_num}: {self.format_timestamp(release_time)}\n"
        
        if len(history_text) > 1024:  # Discord embed field value limit
            history_text = history_text[:1000] + "...(more)"
        
        embed.add_field(
            name="Release History",
            value=history_text or "No history available",
            inline=False
        )
        
        # Add confidence info
        confidence_text = ""
        if pattern.weekday_pattern is not None:
            day_name = weekday_names[pattern.weekday_pattern]
            confidence = int(pattern.weekday_confidence * 100)
            confidence_text += f"• {confidence}% confident that releases happen on {day_name}s\n"
        
        if pattern.avg_interval:
            interval_type = ""
            if pattern.avg_interval < 7:
                interval_type = "Multiple times per week"
            elif 7 <= pattern.avg_interval < 10:
                interval_type = "Weekly"
            elif 10 <= pattern.avg_interval < 18:
                interval_type = "Bi-weekly"
            elif 18 <= pattern.avg_interval < 40:
                interval_type = "Monthly"
            else:
                interval_type = f"Every {pattern.avg_interval:.1f} days"
                
            confidence_text += f"• Release frequency pattern: {interval_type}\n"
        
        if confidence_text:
            embed.add_field(
                name="Pattern Analysis",
                value=confidence_text,
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @manga.command(name="setfreq")
    async def set_frequency(self, ctx: commands.Context, title: str, frequency: str):
        """Set update frequency override for a manga
        
        Frequency options: frequent, standard, slow
        - frequent: Check every hour
        - standard: Check every 6 hours
        - slow: Check once a day
        """
        if frequency not in ["frequent", "standard", "slow"]:
            return await ctx.send("❌ Invalid frequency. Options are: frequent, standard, slow")
        
        tracked_manga = await self.config.tracked_manga()
        
        # Find manga by title
        manga_key = None
        for key, data in tracked_manga.items():
            if data['title'].lower() == title.lower():
                manga_key = key
                break
        
        if not manga_key:
            return await ctx.send(f"❌ No tracked manga found with title '{title}'")
        
        # Update frequency override
        overrides = await self.config.frequency_overrides()
        overrides[manga_key] = frequency
        await self.config.frequency_overrides.set(overrides)
        
        await ctx.send(f"✅ Set check frequency for '{title}' to {frequency}")
    
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
    
    @manga.command(name="newreleases")
    async def new_releases(self, ctx: commands.Context):
        """Show the latest manga releases from tracked sources"""
        latest_releases = await self.config.latest_releases()
        last_check = await self.config.last_releases_check()
        
        if not latest_releases:
            await ctx.send("❌ No recent releases found. Checking now...")
            await self._collect_latest_releases()
            latest_releases = await self.config.latest_releases()
            
            if not latest_releases:
                return await ctx.send("❌ No recent releases found.")
        
        # Create pages for pagination
        pages = []
        
        # Process and sort releases
        releases_list = []
        for source, source_releases in latest_releases.items():
            for release in source_releases:
                releases_list.append(release)
        
        # Sort by timestamp (most recent first)
        releases_list.sort(key=lambda x: x.get('release_timestamp', 0), reverse=True)
        
        # Group by source for presentation
        releases_by_source = defaultdict(list)
        for release in releases_list:
            source = release.get('source', 'unknown')
            releases_by_source[source].append(release)
        
        # Create embeds by source
        for source, source_releases in releases_by_source.items():
            embed = discord.Embed(
                title=f"Latest Releases from {source.upper()}",
                description=f"Last updated: {self.format_relative_time(last_check) if last_check else 'Unknown'}",
                color=await ctx.embed_color(),
                timestamp=datetime.now()
            )
            
            # Add releases (limited to 10 per source)
            for release in source_releases[:10]:
                manga_title = release.get('manga_title', 'Unknown Manga')
                chapter_num = release.get('chapter_num', 'N/A')
                url = release.get('url', '#')
                released_at = release.get('released_at', 'Unknown')
                
                if isinstance(released_at, datetime):
                    released_at = self.format_relative_time(released_at)
                
                value = f"[Read Chapter]({url})\nReleased: {released_at}"
                
                embed.add_field(
                    name=f"{manga_title} - Chapter {chapter_num}",
                    value=value,
                    inline=False
                )
            
            pages.append(embed)
        
        # If only one page, just send it
        if len(pages) == 1:
            return await ctx.send(embed=pages[0])
        
        # Otherwise use paginated menu
        await menu(ctx, pages, DEFAULT_CONTROLS)
    
    @manga.command(name="refresh")
    async def refresh_data(self, ctx: commands.Context):
        """Refresh cached manga data and release patterns"""
        await ctx.send("♻️ Refreshing manga data...")
        
        # Reload release patterns
        await self.initialize()
        
        # Refresh latest releases
        await self._collect_latest_releases()
        
        await ctx.send("✅ Data refreshed! Release patterns and latest chapters have been updated.")
    
    async def _check_for_updates(self, guild=None, frequency_tier=None):
        """Check for updates and return a list of updates found
        
        If frequency_tier is provided, only check manga in that tier.
        """
        updates_found = []
        
        try:
            # Get tracked manga
            tracked_manga = await self.config.tracked_manga()
            updates_made = False
            
            for manga_key, manga_data in tracked_manga.items():
                try:
                    # Skip if not in the requested frequency tier
                    if frequency_tier:
                        check_frequency = self.determine_check_frequency(manga_key, manga_data)
                        if check_frequency != frequency_tier:
                            continue
                    
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
                            
                            # Update release pattern
                            await self.update_release_pattern(manga_key, manga_data, latest_chapter)
                            
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
                            
                            # Update release pattern
                            await self.update_release_pattern(manga_key, manga_data, latest_chapter)
                            
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
                            
                            # Add release pattern info if available
                            manga_key = update.get('manga_key')
                            if manga_key in self.patterns and self.patterns[manga_key].next_expected:
                                next_estimate = self.get_next_release_estimate(manga_key)
                                embed.add_field(name="Next Chapter Estimate", value=next_estimate, inline=True)
                            
                            # Add source info
                            embed.add_field(name="Source", value=source, inline=True)
                            
                            embed.set_footer(text="Manga Tracker")
                            await channel.send(embed=embed)
                except Exception as e:
                    log.error(f"Error sending notification to guild {guild.id}: {str(e)}")
    
    async def _collect_latest_releases(self):
        """Collect the latest releases from all sources"""
        latest_releases = {}
        
        try:
            # Get releases from MangaDex
            mangadex_releases = await self.mangadex_api.get_latest_releases(limit=20)
            latest_releases['mangadex'] = mangadex_releases
            
            # Get releases from TCB Scans
            tcb_releases = await self.tcbscans_api.get_latest_releases(limit=20)
            latest_releases['tcbscans'] = tcb_releases
            
            # Save to config
            await self.config.latest_releases.set(latest_releases)
            await self.config.last_releases_check.set(datetime.now(timezone.utc).isoformat())
            
            log.info(f"Collected latest releases: {len(mangadex_releases)} from MangaDex, {len(tcb_releases)} from TCB Scans")
            
        except Exception as e:
            log.error(f"Error collecting latest releases: {str(e)}")
    
    async def check_frequent_updates(self):
        """Check for updates for manga in the 'frequent' tier (every hour)"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready() and not self.bot.is_closed():
            try:
                log.info("Checking frequently-updated manga...")
                await self._check_for_updates(frequency_tier="frequent")
                
                # Wait for 1 hour before checking again
                await asyncio.sleep(3600)  # 1 hour in seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in frequent update check task: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying if an error occurs
    
    async def check_standard_updates(self):
        """Check for updates for manga in the 'standard' tier (every 6 hours)"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready() and not self.bot.is_closed():
            try:
                log.info("Checking standard-frequency manga...")
                await self._check_for_updates(frequency_tier="standard")
                
                # Wait for 6 hours before checking again
                await asyncio.sleep(21600)  # 6 hours in seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in standard update check task: {str(e)}")
                await asyncio.sleep(600)  # Wait 10 minutes before retrying if an error occurs
    
    async def check_slow_updates(self):
        """Check for updates for manga in the 'slow' tier (every 24 hours)"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready() and not self.bot.is_closed():
            try:
                log.info("Checking slow-frequency manga...")
                await self._check_for_updates(frequency_tier="slow")
                
                # Wait for 24 hours before checking again
                await asyncio.sleep(86400)  # 24 hours in seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in slow update check task: {str(e)}")
                await asyncio.sleep(1800)  # Wait 30 minutes before retrying if an error occurs
    
    async def check_latest_releases(self):
        """Check for latest releases from all sources (every 2 hours)"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready() and not self.bot.is_closed():
            try:
                log.info("Collecting latest releases from all sources...")
                await self._collect_latest_releases()
                
                # Wait for 2 hours before checking again
                await asyncio.sleep(7200)  # 2 hours in seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in latest releases check task: {str(e)}")
                await asyncio.sleep(900)  # Wait 15 minutes before retrying if an error occurs


async def setup(bot: Red):
    """Add the cog to the bot"""
    cog = MangaTracker(bot)
    await bot.add_cog(cog)
    
    # Initialize the cog (load patterns and data)
    await cog.initialize()
