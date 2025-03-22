import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Union

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

log = logging.getLogger("red.weebcentral")

class WeebCentralAPI:
    """API wrapper for WeebCentral"""
    
    def __init__(self, base_url="https://www.weebcentral.com/api"):
        self.base_url = base_url
        self.session = None
    
    async def ensure_session(self):
        """Ensure an aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def search_manga(self, query: str) -> Optional[List[Dict]]:
        """Search for manga by name"""
        await self.ensure_session()
        
        try:
            # The exact endpoint may differ - adjust as needed based on the actual API
            url = f"{self.base_url}/search"
            params = {"q": query}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    log.error(f"Search failed with status {response.status}")
                    return None
        except Exception as e:
            log.error(f"Error searching for manga: {str(e)}")
            return None
    
    async def get_manga_details(self, manga_id: str) -> Optional[Dict]:
        """Get detailed information about a manga"""
        await self.ensure_session()
        
        try:
            # The exact endpoint may differ - adjust as needed
            url = f"{self.base_url}/manga/{manga_id}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    log.error(f"Failed to get manga details, status: {response.status}")
                    return None
        except Exception as e:
            log.error(f"Error getting manga details: {str(e)}")
            return None
    
    async def get_latest_chapters(self, manga_id: str) -> Optional[List[Dict]]:
        """Get the latest chapters for a manga"""
        await self.ensure_session()
        
        try:
            # The exact endpoint may differ - adjust as needed
            url = f"{self.base_url}/manga/{manga_id}/chapters"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    log.error(f"Failed to get chapters, status: {response.status}")
                    return None
        except Exception as e:
            log.error(f"Error getting manga chapters: {str(e)}")
            return None


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
                "`[p]manga setnotify [channel]` - Set the channel for notifications"
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
                    # Fields may differ based on the actual API response
                    manga_id = manga.get('id', 'Unknown ID')
                    title = manga.get('title', 'Unknown Title')
                    chapters = manga.get('chapters', 'Unknown')
                    
                    embed.add_field(
                        name=f"{title}",
                        value=f"ID: `{manga_id}`\nChapters: {chapters}",
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
                return await ctx.send(f"ℹ️ Found multiple results for '{title}'. Please be more specific or use the ID from search results.")
            
            manga = results[0]
            manga_id = manga.get('id')
            manga_title = manga.get('title')
            
            # Get the latest chapter
            chapters = await self.api.get_latest_chapters(manga_id)
            
            if not chapters:
                return await ctx.send(f"❌ Failed to get chapters for '{manga_title}'")
            
            latest_chapter = chapters[0] if chapters else None
            latest_chapter_num = latest_chapter.get('chapter_number', '0') if latest_chapter else '0'
            
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
    
    async def check_for_updates(self):
        """Background task to check for manga updates"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready() and not self.bot.is_closed():
            try:
                log.info("Checking for manga updates...")
                
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
                        
                        latest_chapter_num = latest_chapter.get('chapter_number', '0')
                        
                        # Update last checked timestamp
                        tracked_manga[manga_id]['last_checked'] = datetime.now().isoformat()
                        updates_made = True
                        
                        # Check if there's a new chapter
                        if latest_chapter_num > manga_data['latest_chapter']:
                            log.info(f"New chapter found for {manga_data['title']}: {latest_chapter_num}")
                            
                            # Update the latest chapter number
                            tracked_manga[manga_id]['latest_chapter'] = latest_chapter_num
                            
                            # Send notifications to all guilds
                            for guild in self.bot.guilds:
                                try:
                                    channel_id = await self.config.guild(guild).notification_channel()
                                    if channel_id:
                                        channel = guild.get_channel(channel_id)
                                        if channel:
                                            chapter_url = latest_chapter.get('url', '')
                                            
                                            embed = discord.Embed(
                                                title=f"📢 New Chapter Alert: {manga_data['title']}",
                                                description=f"Chapter {latest_chapter_num} is now available!",
                                                color=discord.Color.gold(),
                                                url=chapter_url or f"https://www.weebcentral.com/series/{manga_id}"
                                            )
                                            
                                            embed.set_footer(text="WeebCentral Manga Tracker")
                                            await channel.send(embed=embed)
                                except Exception as e:
                                    log.error(f"Error sending notification to guild {guild.id}: {str(e)}")
                        
                    except Exception as e:
                        log.error(f"Error checking updates for {manga_data['title']}: {str(e)}")
                    
                    # Add a small delay between requests to avoid rate limiting
                    await asyncio.sleep(1)
                
                # Save updated data if changes were made
                if updates_made:
                    await self.config.tracked_manga.set(tracked_manga)
                
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
