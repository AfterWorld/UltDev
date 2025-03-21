import asyncio
import discord
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify

from .mal_api import MyAnimeListAPI
from .cache_manager import CacheManager
from .utils import create_embed, chunked_send, format_relative_time

log = logging.getLogger("red.animeforum.forum_creator")

class ForumCreator:
    """Handles creation and management of anime forum channels"""
    
    def __init__(self, bot: Red, config: Config, cache: CacheManager):
        self.bot = bot
        self.config = config
        self.cache = cache
        self.mal_api = None  # Will be set by the main cog
        
    def set_mal_api(self, mal_api: MyAnimeListAPI):
        """Set the MAL API reference"""
        self.mal_api = mal_api
        
    async def create_anime_forum(self, ctx, name: str, anime_data: Dict = None):
        """Create a new anime forum channel"""
        settings = await self.config.guild(ctx.guild).all()
        
        async with ctx.typing():
            try:
                # Status message
                status_msg = await ctx.send(f"Creating forum for **{name}**... Gathering anime information...")
                
                # Find or create the forums category
                category_name = settings["forums_category_name"]
                category = discord.utils.get(ctx.guild.categories, name=category_name)
                
                if not category:
                    # Create the forums category if it doesn't exist
                    category = await ctx.guild.create_category(category_name)
                
                # Get anime info if enabled and not already provided
                if settings["use_mal_data"] and not anime_data and self.mal_api:
                    anime_data = await self.get_anime_info(name)
                    if anime_data:
                        await status_msg.edit(content=f"Creating forum for **{anime_data['title']}**... Setting up forum...")
                    
                # Create the forum
                forum_channel = await self.create_forum_channel(ctx.guild, name, category, anime_data)
                
                # Send completion message with anime thumbnail if available
                if anime_data and anime_data.get("image_url"):
                    embed = discord.Embed(
                        title=f"Forum Created: {anime_data['title']}",
                        url=forum_channel.jump_url,
                        description=f"A new anime forum has been created for {anime_data['title']}!",
                        color=discord.Color.blue()
                    )
                    embed.set_thumbnail(url=anime_data["image_url"])
                    
                    # Add anime details
                    if anime_data.get("episodes"):
                        embed.add_field(name="Episodes", value=anime_data.get("episodes", "Unknown"), inline=True)
                    if anime_data.get("score"):
                        embed.add_field(name="Score", value=f"{anime_data.get('score', 'N/A')}/10", inline=True)
                    if anime_data.get("genres"):
                        embed.add_field(name="Genres", value=", ".join(anime_data.get("genres", ["Unknown"])[:3]), inline=True)
                    
                    await status_msg.delete()
                    await ctx.send(embed=embed)
                else:
                    await status_msg.edit(content=f"Anime forum channel **{name}** has been created!")
                
                # Create initial threads if auto-thread creation is enabled
                if settings.get("auto_thread_create", False) and anime_data:
                    await self.create_initial_threads(forum_channel, anime_data)
                    
            except Exception as e:
                log.error(f"Error creating forum channel: {e}")
                await ctx.send(f"Error creating forum channel: {e}")
                
    async def create_seasonal_forums(self, ctx):
        """Create forum channels for current season anime"""
        settings = await self.config.guild(ctx.guild).all()
        
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        status_msg = await ctx.send("Gathering information about seasonal anime. This may take a moment...")
        
        try:
            # Find or create the forums category
            category_name = settings["forums_category_name"]
            category = discord.utils.get(ctx.guild.categories, name=category_name)
            
            if not category:
                # Create the category
                category = await ctx.guild.create_category(category_name)
                
            # Get current season anime from Jikan API
            try:
                seasonal_anime = await self.mal_api.get_seasonal_anime(limit=settings["rate_limits"]["max_bulk_create"])
                
                if not seasonal_anime:
                    await status_msg.edit(content="Error accessing anime API. Using fallback list.")
                    seasonal_anime = [
                        {"title": "Spy x Family"}, 
                        {"title": "Demon Slayer"}, 
                        {"title": "Jujutsu Kaisen"}, 
                        {"title": "My Hero Academia"}, 
                        {"title": "One Piece"}
                    ]
            except Exception as e:
                await status_msg.edit(content=f"Error accessing anime API: {e}. Using fallback list.")
                seasonal_anime = [
                    {"title": "Spy x Family"}, 
                    {"title": "Demon Slayer"}, 
                    {"title": "Jujutsu Kaisen"}, 
                    {"title": "My Hero Academia"}, 
                    {"title": "One Piece"}
                ]
            
            await status_msg.edit(content=f"Creating forums for {len(seasonal_anime)} seasonal anime...")
            
            created_forums = []
            existing_forums = []
            
            for index, anime in enumerate(seasonal_anime):
                # Update status periodically
                if index % 3 == 0:
                    await status_msg.edit(content=f"Creating forums for seasonal anime... ({index}/{len(seasonal_anime)})")
                
                # Check if forum already exists (case insensitive)
                title = anime.get("title", "Unknown")
                normalized_name = title.lower().replace(" ", "-")
                
                existing_channel = discord.utils.find(
                    lambda c: c.name.lower() == normalized_name,
                    ctx.guild.channels
                )
                
                if existing_channel:
                    existing_forums.append(title)
                    continue
                
                # Create the forum
                try:
                    await self.create_forum_channel(
                        ctx.guild, 
                        title, 
                        category, 
                        anime, 
                        is_seasonal=True
                    )
                    created_forums.append(title)
                    
                    # Sleep to avoid rate limits
                    await asyncio.sleep(settings["rate_limits"]["cooldown_seconds"])
                except Exception as e:
                    log.error(f"Error creating forum for {title}: {e}")
            
            # Final message
            message = []
            if created_forums:
                message.append(f"Created {len(created_forums)} seasonal anime forums!")
            if existing_forums:
                message.append(f"{len(existing_forums)} forums already existed.")
                
            await status_msg.edit(content="\n".join(message))
                
        except Exception as e:
            await status_msg.edit(content=f"Error creating seasonal anime forums: {e}")
            
    async def create_toptier_forums(self, ctx):
        """Create forum channels for top-rated anime"""
        settings = await self.config.guild(ctx.guild).all()
        
        if not self.mal_api:
            return await ctx.send("MAL API not initialized. Contact the bot owner.")
            
        status_msg = await ctx.send("Gathering information about top-rated anime. This may take a moment...")
        
        try:
            # Find or create the forums category
            category_name = settings["forums_category_name"]
            category = discord.utils.get(ctx.guild.categories, name=category_name)
            
            if not category:
                # Create the category
                category = await ctx.guild.create_category(category_name)
                
            # Get top anime from Jikan API
            try:
                top_anime = await self.mal_api.get_top_anime(limit=settings["rate_limits"]["max_bulk_create"])
                
                if not top_anime:
                    await status_msg.edit(content="Error accessing anime API. Using fallback list.")
                    top_anime = [
                        {"title": "Fullmetal Alchemist: Brotherhood"}, 
                        {"title": "Steins;Gate"}, 
                        {"title": "Hunter x Hunter"}, 
                        {"title": "Attack on Titan"}, 
                        {"title": "Gintama"}
                    ]
            except Exception as e:
                await status_msg.edit(content=f"Error accessing anime API: {e}. Using fallback list.")
                top_anime = [
                    {"title": "Fullmetal Alchemist: Brotherhood"}, 
                    {"title": "Steins;Gate"}, 
                    {"title": "Hunter x Hunter"}, 
                    {"title": "Attack on Titan"}, 
                    {"title": "Gintama"}
                ]
            
            await status_msg.edit(content=f"Creating forums for {len(top_anime)} top-rated anime...")
            
            created_forums = []
            existing_forums = []
            
            for index, anime in enumerate(top_anime):
                # Update status periodically
                if index % 3 == 0:
                    await status_msg.edit(content=f"Creating forums for top anime... ({index}/{len(top_anime)})")
                
                # Check if forum already exists
                title = anime.get("title", "Unknown")
                normalized_name = title.lower().replace(" ", "-")
                
                existing_channel = discord.utils.find(
                    lambda c: c.name.lower() == normalized_name,
                    ctx.guild.channels
                )
                
                if existing_channel:
                    existing_forums.append(title)
                    continue
                
                # Create the forum
                try:
                    await self.create_forum_channel(
                        ctx.guild, 
                        title, 
                        category, 
                        anime, 
                        is_top_rated=True
                    )
                    created_forums.append(title)
                    
                    # Sleep to avoid rate limits
                    await asyncio.sleep(settings["rate_limits"]["cooldown_seconds"])
                except Exception as e:
                    log.error(f"Error creating forum for {title}: {e}")
            
            # Final message
            message = []
            if created_forums:
                message.append(f"Created {len(created_forums)} top-rated anime forums!")
            if existing_forums:
                message.append(f"{len(existing_forums)} forums already existed.")
                
            await status_msg.edit(content="\n".join(message))
                
        except Exception as e:
            await status_msg.edit(content=f"Error creating top anime forums: {e}")
    
    async def get_anime_info(self, name: str) -> Optional[Dict]:
        """Fetch anime information from MyAnimeList via the API"""
        if not self.mal_api:
            return None
            
        try:
            # Search for the anime
            results = await self.mal_api.search_anime(name, limit=1)
            if not results:
                return None
                
            # Get detailed info
            anime_id = results[0].get("id") or results[0].get("mal_id")
            if not anime_id:
                return None
                
            return await self.mal_api.get_anime_details(anime_id)
                
        except Exception as e:
            log.error(f"Error getting anime info: {e}")
            return None
    
    async def create_forum_channel(self, guild, name: str, category=None, anime_data=None, is_seasonal=False, is_top_rated=False):
        """Create a forum channel with optimized settings"""
        settings = await self.config.guild(guild).all()
        
        # Prepare forum tags
        forum_tags = []
        
        # Add special tags based on type
        if is_seasonal:
            seasonal_tag = discord.ForumTag(name="Seasonal")
            forum_tags.append(seasonal_tag)
            
        if is_top_rated:
            top_rated_tag = discord.ForumTag(name="Top Rated")
            forum_tags.append(top_rated_tag)
        
        # Add default tags
        for tag_name in settings["default_tags"]:
            # Skip the tags we already added
            if (tag_name == "Seasonal" and is_seasonal) or (tag_name == "Top Rated" and is_top_rated):
                continue
            forum_tags.append(discord.ForumTag(name=tag_name))
            
        # Add genre tags if available
        if anime_data and anime_data.get("genres"):
            for genre in anime_data.get("genres", [])[:10]:  # Limit to 10 genres
                if genre not in settings["default_tags"]:
                    forum_tags.append(discord.ForumTag(name=genre))
        
        # Create guidelines for the forum
        if settings["default_post_guidelines"]:
            if anime_data:
                synopsis = anime_data.get("synopsis", "")
                if synopsis and len(synopsis) > 500:
                    synopsis = synopsis[:497] + "..."
                    
                guidelines = (
                    f"# {anime_data.get('title', name)}\n\n"
                    f"{synopsis}\n\n"
                    f"## Guidelines:\n"
                    f"- Be respectful to other fans\n"
                    f"- Mark spoilers appropriately\n"
                    f"- Keep discussions on-topic\n"
                    f"- Have fun discussing your favorite anime!\n\n"
                )
                
                if anime_data.get("url"):
                    guidelines += f"[MyAnimeList Page]({anime_data['url']})"
            else:
                guidelines = (
                    f"# Welcome to the {name} Forum!\n\n"
                    f"This is a place to discuss everything related to {name}.\n\n"
                    f"## Guidelines:\n"
                    f"- Be respectful to other fans\n"
                    f"- Mark spoilers appropriately\n"
                    f"- Keep discussions on-topic\n"
                    f"- Have fun discussing your favorite anime!"
                )
        else:
            guidelines = f"Discussion forum for {name}"
            
        # Create the forum channel
        forum_channel = await guild.create_forum(
            name=name,
            category=category,
            topic=guidelines[:1000],  # Discord's limit
            reason=f"Anime forum"
        )
        
        # Set the available tags
        await forum_channel.edit(available_tags=forum_tags)
        
        # Set suggested format if using MyAnimeList data
        if anime_data and settings["use_mal_data"]:
            # Create guidelines format that encourages structured discussions
            suggested_format = (
                f"**Topic**: \n\n"
                f"**Episodes Covered**: \n\n"
                f"**Discussion Points**: \n\n"
                f"**Rating**: /10\n\n"
                f"**Thoughts**: "
            )
            
            # No slowmode
            await forum_channel.edit(default_thread_slowmode_delay=0)
            
            # Set auto-archive to maximum
            await forum_channel.edit(default_auto_archive_duration=4320)  # 3 days in minutes
        
        return forum_channel
        
    async def create_initial_threads(self, forum_channel, anime_data):
        """Create initial threads in a newly created forum"""
        try:
            # Create general discussion thread
            await forum_channel.create_thread(
                name=f"General Discussion: {anime_data.get('title')}",
                content=(
                    f"Welcome to the general discussion thread for **{anime_data.get('title')}**!\n\n"
                    f"Use this thread for overall series discussion and impressions. Feel free to share your favorite moments, characters, and more!"
                ),
                applied_tags=[discord.utils.get(forum_channel.available_tags, name="Discussion")]
            )
            
            # Create recommendations thread
            await forum_channel.create_thread(
                name=f"Similar Anime Recommendations",
                content=(
                    f"If you enjoyed **{anime_data.get('title')}**, share your recommendations for similar anime here!\n\n"
                    f"When recommending, please explain why you think fans of this anime would enjoy your recommendation."
                ),
                applied_tags=[discord.utils.get(forum_channel.available_tags, name="Recommendation")]
            )
            
            # If it's currently airing, create episode discussion
            if anime_data.get("status") == "Currently Airing" or anime_data.get("airing"):
                await forum_channel.create_thread(
                    name=f"Latest Episode Discussion",
                    content=(
                        f"This thread is for discussing the most recent episode of **{anime_data.get('title')}**.\n\n"
                        f"Remember to use spoiler tags when discussing events from the episode!"
                    ),
                    applied_tags=[discord.utils.get(forum_channel.available_tags, name="Discussion")]
                )
                
        except Exception as e:
            log.error(f"Error creating initial threads: {e}")
    
    async def process_thread_message(self, message, parent_channel, settings):
        """Process a message sent in a forum thread"""
        # Auto-tag based on content
        content_lower = message.content.lower()
        keywords = {
            "spoiler": "Spoiler",
            "fanart": "Fanart", 
            "recommend": "Recommendation",
            "help": "Question",
            "news": "News",
            "meme": "Meme",
            "review": "Review"
        }
        
        current_tags = message.channel.applied_tags
        new_tags = list(current_tags)
        tag_added = False
        
        # Look for keywords to auto-tag
        for tag in parent_channel.available_tags:
            for keyword, tag_name in keywords.items():
                # Check if keyword is in message and tag not already applied
                if keyword in content_lower and tag.name == tag_name and tag not in new_tags:
                    new_tags.append(tag)
                    tag_added = True
        
        # Update tags if needed
        if tag_added and len(new_tags) > len(current_tags):
            try:
                await message.channel.edit(applied_tags=new_tags)
            except:
                pass
                
        # Handle spoiler detection if enabled
        if settings["moderation"].get("spoiler_detection", False):
            spoiler_keywords = ["spoiler", "spoilers", "just happened", "plot twist", "reveals", "ending"]
            has_spoiler_tag = any(tag.name == "Spoiler" for tag in current_tags)
            
            if not has_spoiler_tag and any(keyword in content_lower for keyword in spoiler_keywords):
                # Check if message contains proper spoiler formatting
                if not "||" in message.content:
                    # Add spoiler tag
                    if discord.utils.get(parent_channel.available_tags, name="Spoiler") not in new_tags:
                        spoiler_tag = discord.utils.get(parent_channel.available_tags, name="Spoiler")
                        if spoiler_tag:
                            new_tags.append(spoiler_tag)
                            await message.channel.edit(applied_tags=new_tags)
                            
                    # Remind about spoiler tags
                    try:
                        await message.reply(
                            "Your message may contain spoilers! Please use Discord's spoiler tags by wrapping text like this: `||spoiler text here||`",
                            delete_after=30
                        )
                    except:
                        pass
    
    async def process_new_thread(self, thread, settings):
        """Process a newly created thread"""
        try:
            # Find anime name from forum name
            anime_name = thread.parent.name.replace("-", " ").title()
            thread_name = thread.name
            
            # Create a welcoming message
            welcome_message = (
                f"Welcome to the discussion about **{thread_name}**!\n\n"
                f"Feel free to share your thoughts, theories, favorite moments, or questions about {anime_name}.\n\n"
                f"Remember to use tags to help others find your thread. Enjoy your discussion!"
            )
            
            # Add specific guidance based on thread tags
            if thread.applied_tags:
                tag_names = [tag.name for tag in thread.applied_tags]
                
                if "Review" in tag_names:
                    welcome_message += (
                        "\n\n**Review Guidelines:**\n"
                        "- Consider sharing your rating out of 10\n"
                        "- What aspects did you enjoy most?\n"
                        "- Any constructive criticism?\n"
                        "- Avoid major spoilers or use spoiler tags"
                    )
                elif "Question" in tag_names:
                    welcome_message += (
                        "\n\n**Asking Questions:**\n"
                        "- Be specific about what you're asking\n"
                        "- Mention which episode/chapter you're referring to\n"
                        "- Let others know if your question contains spoilers"
                    )
                elif "Recommendation" in tag_names:
                    welcome_message += (
                        "\n\n**Recommendation Tips:**\n"
                        "- Explain why you're recommending it\n"
                        "- Mention similar elements to this anime\n"
                        "- Consider noting content warnings if applicable"
                    )
            
            # Send the message
            await thread.send(welcome_message)
            
            # For seasonal anime, add episode reminder
            has_seasonal = any(tag.name == "Seasonal" for tag in thread.applied_tags)
            if has_seasonal and self.mal_api:
                anime_info = await self.get_anime_info(anime_name)
                if anime_info and anime_info.get("airing"):
                    # Get schedule info
                    next_episode_str = ""
                    if anime_info.get("broadcast", {}).get("day") and anime_info.get("broadcast", {}).get("time"):
                        next_episode_str = f"\n\nNew episodes air on {anime_info['broadcast']['day']} at {anime_info['broadcast']['time']} JST."
                        
                    await thread.send(
                        f"**Currently Airing Anime**\n"
                        f"This anime is currently airing with {anime_info.get('episodes', '?')} total episodes planned."
                        f"{next_episode_str}"
                    )
            
        except Exception as e:
            log.error(f"Error sending welcome message to new thread: {e}")
