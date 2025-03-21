import discord
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

log = logging.getLogger("red.animeforum.utils")

async def check_permissions(ctx) -> bool:
    """Check if user has permission to create forums"""
    # Admin
    if await ctx.bot.is_admin(ctx.author):
        return True
        
    # Manage Channels permission
    if ctx.author.guild_permissions.manage_channels:
        return True
        
    # No permissions
    return False

async def chunked_send(ctx, content, chunk_size=1950, code_block=False):
    """Send a message in chunks to avoid hitting the Discord character limit"""
    if not content:
        return
        
    chunks = []
    current_chunk = ""
    
    for line in content.splitlines(True):  # keepends=True
        if len(current_chunk) + len(line) > chunk_size:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line
            
    if current_chunk:
        chunks.append(current_chunk)
        
    for chunk in chunks:
        if code_block:
            await ctx.send(f"```\n{chunk}\n```")
        else:
            await ctx.send(chunk)

def create_embed(anime_data) -> discord.Embed:
    """Create a nicely formatted embed for anime data"""
    embed = discord.Embed(
        title=anime_data.get("title", "Unknown Anime"),
        description=anime_data.get("synopsis", "No synopsis available"),
        color=discord.Color.blue()
    )
    
    # Set thumbnail if available
    if anime_data.get("image_url"):
        embed.set_thumbnail(url=anime_data["image_url"])
        
    # Add anime details
    if anime_data.get("title_english") and anime_data["title_english"] != anime_data["title"]:
        embed.add_field(name="English Title", value=anime_data["title_english"], inline=True)
        
    if anime_data.get("episodes"):
        embed.add_field(name="Episodes", value=str(anime_data["episodes"]), inline=True)
        
    if anime_data.get("score"):
        embed.add_field(name="Score", value=f"{anime_data['score']}/10", inline=True)
        
    if anime_data.get("status"):
        embed.add_field(name="Status", value=anime_data["status"], inline=True)
        
    if anime_data.get("type"):
        embed.add_field(name="Type", value=anime_data["type"], inline=True)
        
    if anime_data.get("aired") and anime_data["aired"].get("from"):
        air_date = anime_data["aired"]["from"]
        if isinstance(air_date, str):
            air_date = air_date.split("T")[0]  # Remove time component if needed
        embed.add_field(name="Aired", value=air_date, inline=True)
        
    if anime_data.get("genres"):
        genres = ", ".join(anime_data["genres"][:5])  # Limit to 5 genres
        embed.add_field(name="Genres", value=genres, inline=False)
        
    if anime_data.get("studios"):
        studios = ", ".join(anime_data["studios"][:3])  # Limit to 3 studios
        embed.add_field(name="Studios", value=studios, inline=False)
        
    # Add MAL link if available
    if anime_data.get("url"):
        embed.add_field(name="MyAnimeList", value=f"[View page]({anime_data['url']})", inline=False)
        
    return embed

def format_relative_time(when) -> str:
    """Format a datetime as a relative time string (e.g., 'in 2 hours')"""
    now = datetime.now()
    
    if isinstance(when, (int, float)):
        when = datetime.fromtimestamp(when)
        
    delta = when - now
    
    # Handle past dates
    if delta.total_seconds() < 0:
        delta = abs(delta)
        
        if delta.days > 365:
            years = delta.days // 365
            return f"{years} year{'s' if years != 1 else ''} ago"
        elif delta.days > 30:
            months = delta.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        elif delta.days > 0:
            return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "just now"
            
    # Handle future dates
    if delta.days > 365:
        years = delta.days // 365
        return f"in {years} year{'s' if years != 1 else ''}"
    elif delta.days > 30:
        months = delta.days // 30
        return f"in {months} month{'s' if months != 1 else ''}"
    elif delta.days > 0:
        return f"in {delta.days} day{'s' if delta.days != 1 else ''}"
    elif delta.seconds >= 3600:
        hours = delta.seconds // 3600
        return f"in {hours} hour{'s' if hours != 1 else ''}"
    elif delta.seconds >= 60:
        minutes = delta.seconds // 60
        return f"in {minutes} minute{'s' if minutes != 1 else ''}"
    else:
        return "right now"

def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a filename"""
    # Replace spaces with hyphens
    name = re.sub(r'\s+', '-', name)
    
    # Remove any non-alphanumeric characters except hyphens and underscores
    name = re.sub(r'[^\w\-]', '', name)
    
    # Ensure name is not too long
    if len(name) > 100:
        name = name[:100]
        
    return name.lower()

def extract_episode_number(title: str) -> Optional[int]:
    """Extract episode number from a title string"""
    # Common patterns for episode numbers
    patterns = [
        r'episode\s+(\d+)',  # "Episode 10"
        r'ep\s*(\d+)',       # "Ep 10" or "EP10"
        r'#\s*(\d+)',        # "#10"
        r'\s(\d+)$',         # "Title 10"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title.lower())
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue
                
    return None

def parse_mal_date(date_str: str) -> Optional[datetime]:
    """Parse a date string from MyAnimeList"""
    if not date_str or date_str == "?" or date_str.lower() == "unknown":
        return None
        
    # Try multiple formats
    formats = [
        '%Y-%m-%d',  # ISO format: 2023-01-15
        '%Y-%m-%dT%H:%M:%S%z',  # ISO with time: 2023-01-15T12:30:00+00:00
        '%b %d, %Y',  # Jan 15, 2023
        '%B %d, %Y',  # January 15, 2023
        '%d %b %Y',   # 15 Jan 2023
        '%d %B %Y',   # 15 January 2023
        '%Y'          # Just the year: 2023
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
            
    # If all formats fail, try to extract just the year
    year_match = re.search(r'\b(19|20)\d{2}\b', date_str)
    if year_match:
        try:
            return datetime(int(year_match.group(0)), 1, 1)
        except ValueError:
            pass
            
    return None

def calculate_anime_seasons(year: int, month: int) -> Tuple[str, int]:
    """
    Calculate which anime season a date belongs to
    
    Returns:
    --------
    Tuple[str, int]: (season name, year)
    """
    if 1 <= month <= 3:
        return "winter", year
    elif 4 <= month <= 6:
        return "spring", year
    elif 7 <= month <= 9:
        return "summer", year
    else:  # 10-12
        return "fall", year

def convert_to_discord_timestamp(dt, format_code="f"):
    """
    Convert a datetime to a Discord timestamp
    
    Format codes:
    - t: Short time (e.g., 9:30 PM)
    - T: Long time (e.g., 9:30:00 PM)
    - d: Short date (e.g., 01/15/2023)
    - D: Long date (e.g., January 15, 2023)
    - f: Short date/time (e.g., January 15, 2023 9:30 PM)
    - F: Long date/time (e.g., Sunday, January 15, 2023 9:30 PM)
    - R: Relative time (e.g., 2 days ago)
    """
    if isinstance(dt, datetime):
        timestamp = int(dt.timestamp())
    else:
        timestamp = int(dt)
        
    return f"<t:{timestamp}:{format_code}>"
