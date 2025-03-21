import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Union
import aiohttp
import json
import random

from .cache_manager import CacheManager

log = logging.getLogger("red.animeforum.mal_api")

class MyAnimeListAPI:
    """Handles interaction with MyAnimeList API"""
    
    def __init__(self, session: aiohttp.ClientSession, cache: CacheManager):
        self.session = session
        self.cache = cache
        self.client_id = None
        self.base_url = "https://api.myanimelist.net/v2"
        self.jikan_url = "https://api.jikan.moe/v4"
        self.rate_limit_lock = asyncio.Lock()
        self.rate_limit_remaining = 60
        self.rate_limit_reset = 0
        
    def set_client_id(self, client_id: str):
        """Set the MyAnimeList API client ID"""
        self.client_id = client_id
        
    async def _handle_rate_limit(self, api_type: str = "jikan"):
        """Handle rate limiting for API calls"""
        async with self.rate_limit_lock:
            current_time = time.time()
            
            # Different rate limits for different APIs
            if api_type == "mal":
                # MAL API has very generous limits, so we're conservative
                await asyncio.sleep(0.5)
                return
                
            # For Jikan API, we need to be more careful (60 requests per minute)
            if self.rate_limit_remaining <= 1:
                # Calculate how long to wait for reset
                wait_time = max(0, self.rate_limit_reset - current_time)
                if wait_time > 0:
                    log.info(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                    await asyncio.sleep(wait_time + 1)  # Add a buffer second
                    self.rate_limit_remaining = 60
                    self.rate_limit_reset = time.time() + 60
                    
            # Decrement remaining and add jitter to prevent thundering herd
            self.rate_limit_remaining -= 1
            await asyncio.sleep(random.uniform(0.1, 0.3))
    
    async def _make_jikan_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a request to Jikan API with rate limiting"""
        cache_key = f"jikan:{endpoint}:{json.dumps(params or {})}"
        
        # Check cache first
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data
            
        # Handle rate limiting
        await self._handle_rate_limit("jikan")
        
        try:
            url = f"{self.jikan_url}/{endpoint}"
            async with self.session.get(url, params=params) as resp:
                # Update rate limit info
                self.rate_limit_remaining = int(resp.headers.get("X-RateLimit-Remaining", self.rate_limit_remaining))
                reset_time = int(resp.headers.get("X-RateLimit-Reset", 0))
                if reset_time:
                    self.rate_limit_reset = reset_time
                
                if resp.status != 200:
                    log.error(f"Jikan API error: {resp.status} for {url}")
                    return None
                    
                data = await resp.json()
                
                # Cache the response
                self.cache.set(cache_key, data)
                return data
                
        except Exception as e:
            log.error(f"Error making Jikan API request: {e}")
            return None
    
    async def _make_mal_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a request to official MAL API with rate limiting"""
        if not self.client_id:
            log.warning("MAL API client ID not set, falling back to Jikan")
            return None
            
        cache_key = f"mal:{endpoint}:{json.dumps(params or {})}"
        
        # Check cache first
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data
            
        # Handle rate limiting
        await self._handle_rate_limit("mal")
        
        try:
            url = f"{self.base_url}/{endpoint}"
            headers = {"X-MAL-CLIENT-ID": self.client_id}
            
            async with self.session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    log.error(f"MAL API error: {resp.status} for {url}")
                    return None
                    
                data = await resp.json()
                
                # Cache the response
                self.cache.set(cache_key, data)
                return data
                
        except Exception as e:
            log.error(f"Error making MAL API request: {e}")
            return None
    
    async def search_anime(self, query: str, limit: int = 5) -> List[Dict]:
        """Search for anime by name"""
        # Try official API first if client ID is set
        if self.client_id:
            params = {
                "q": query,
                "limit": limit,
                "fields": "id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,popularity,num_episodes,media_type,status"
            }
            
            result = await self._make_mal_request("anime", params)
            if result and "data" in result:
                return [item["node"] for item in result["data"]]
                
        # Fall back to Jikan API
        params = {"q": query, "limit": limit}
        result = await self._make_jikan_request("anime", params)
        
        if result and "data" in result:
            return result["data"]
        return []
    
    async def get_anime_details(self, anime_id: int) -> Optional[Dict]:
        """Get detailed information about an anime"""
        # Try official API first if client ID is set
        if self.client_id:
            params = {
                "fields": "id,title,main_picture,alternative_titles,start_date,end_date,synopsis,mean,rank,popularity,num_episodes,media_type,status,genres,studios,related_anime,recommendations,background,pictures,statistics"
            }
            
            result = await self._make_mal_request(f"anime/{anime_id}", params)
            if result:
                # Format the response to be more consistent
                return {
                    "id": result.get("id"),
                    "title": result.get("title"),
                    "title_english": result.get("alternative_titles", {}).get("en"),
                    "title_japanese": result.get("alternative_titles", {}).get("ja"),
                    "synopsis": result.get("synopsis"),
                    "episodes": result.get("num_episodes"),
                    "score": result.get("mean"),
                    "rank": result.get("rank"),
                    "popularity": result.get("popularity"),
                    "image_url": result.get("main_picture", {}).get("large") or result.get("main_picture", {}).get("medium"),
                    "type": result.get("media_type"),
                    "status": result.get("status"),
                    "genres": [genre["name"] for genre in result.get("genres", [])],
                    "studios": [studio["name"] for studio in result.get("studios", [])],
                    "airing": result.get("status") == "currently_airing",
                    "aired": {
                        "from": result.get("start_date"),
                        "to": result.get("end_date")
                    },
                    "background": result.get("background"),
                    "url": f"https://myanimelist.net/anime/{anime_id}"
                }
                
        # Fall back to Jikan API
        result = await self._make_jikan_request(f"anime/{anime_id}/full")
        
        if result and "data" in result:
            data = result["data"]
            # Clean and standardize the data
            return {
                "id": data.get("mal_id"),
                "title": data.get("title"),
                "title_english": data.get("title_english"),
                "title_japanese": data.get("title_japanese"),
                "synopsis": data.get("synopsis"),
                "episodes": data.get("episodes"),
                "score": data.get("score"),
                "rank": data.get("rank"),
                "popularity": data.get("popularity"),
                "image_url": data.get("images", {}).get("jpg", {}).get("large_image_url"),
                "type": data.get("type"),
                "status": data.get("status"),
                "genres": [genre["name"] for genre in data.get("genres", [])],
                "studios": [studio["name"] for studio in data.get("studios", [])],
                "airing": data.get("airing", False),
                "aired": data.get("aired", {}),
                "background": data.get("background"),
                "url": data.get("url")
            }
            
        return None
        
    async def get_seasonal_anime(self, year: int = None, season: str = None, limit: int = 15) -> List[Dict]:
        """Get seasonal anime, defaults to current season"""
        if year and season:
            endpoint = f"seasons/{year}/{season}"
        else:
            endpoint = "seasons/now"
            
        params = {"limit": limit}
        result = await self._make_jikan_request(endpoint, params)
        
        if result and "data" in result:
            # Format the results consistently
            anime_list = []
            for item in result["data"][:limit]:
                anime_list.append({
                    "id": item.get("mal_id"),
                    "title": item.get("title"),
                    "synopsis": item.get("synopsis"),
                    "episodes": item.get("episodes"),
                    "score": item.get("score"),
                    "image_url": item.get("images", {}).get("jpg", {}).get("image_url"),
                    "airing_start": item.get("aired", {}).get("from"),
                    "type": item.get("type"),
                    "genres": [genre["name"] for genre in item.get("genres", [])],
                    "url": item.get("url")
                })
            return anime_list
        return []
        
    async def get_top_anime(self, limit: int = 15, filter_type: str = "all") -> List[Dict]:
        """Get top-rated anime"""
        params = {"limit": limit, "type": filter_type}
        result = await self._make_jikan_request("top/anime", params)
        
        if result and "data" in result:
            # Format the results consistently
            anime_list = []
            for item in result["data"][:limit]:
                anime_list.append({
                    "id": item.get("mal_id"),
                    "title": item.get("title"),
                    "synopsis": item.get("synopsis"),
                    "episodes": item.get("episodes"),
                    "score": item.get("score"),
                    "image_url": item.get("images", {}).get("jpg", {}).get("image_url"),
                    "type": item.get("type"),
                    "genres": [genre["name"] for genre in item.get("genres", [])],
                    "url": item.get("url")
                })
            return anime_list
        return []
        
    async def get_anime_schedule(self, weekday: str = None) -> Dict[str, List[Dict]]:
        """Get anime airing schedule, optionally filtered by weekday"""
        if weekday:
            endpoint = f"schedules/{weekday.lower()}"
        else:
            endpoint = "schedules"
            
        result = await self._make_jikan_request(endpoint)
        
        if result and "data" in result:
            # Group by weekday
            schedule = {}
            for item in result["data"]:
                weekday = item.get("broadcast", {}).get("day", "Unknown")
                if weekday not in schedule:
                    schedule[weekday] = []
                    
                schedule[weekday].append({
                    "id": item.get("mal_id"),
                    "title": item.get("title"),
                    "episodes": item.get("episodes"),
                    "score": item.get("score"),
                    "image_url": item.get("images", {}).get("jpg", {}).get("image_url"),
                    "time": item.get("broadcast", {}).get("time"),
                    "url": item.get("url")
                })
            return schedule
        return {}
        
    async def get_upcoming_anime(self, limit: int = 15) -> List[Dict]:
        """Get upcoming anime for next season"""
        # Get current season info to determine next season
        current_season = await self._make_jikan_request("seasons/now", {"limit": 1})
        if not current_season or "data" not in current_season or not current_season["data"]:
            return []
            
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
        
        # Get next season anime
        return await self.get_seasonal_anime(next_year, next_season, limit)
        
    async def get_recommendations(self, anime_id: int, limit: int = 10) -> List[Dict]:
        """Get anime recommendations based on a specific anime"""
        result = await self._make_jikan_request(f"anime/{anime_id}/recommendations")
        
        if result and "data" in result:
            recommendations = []
            for item in result["data"][:limit]:
                entry = item.get("entry", {})
                recommendations.append({
                    "id": entry.get("mal_id"),
                    "title": entry.get("title"),
                    "image_url": entry.get("images", {}).get("jpg", {}).get("image_url"),
                    "url": entry.get("url")
                })
            return recommendations
        return []
