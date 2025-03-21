import asyncio
import discord
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter, defaultdict

from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify, box
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .utils import create_embed

log = logging.getLogger("red.animeforum.analytics")

class AnalyticsManager:
    """Manages analytics for anime forum activity"""
    
    def __init__(self, bot: Red, config: Config):
        self.bot = bot
        self.config = config
        
        # Register additional configs
        self.config.register_guild(
            analytics_data={
                "forum_stats": {},  # Map of forum_id -> stats
                "user_stats": {},   # Map of user_id -> stats
                "thread_stats": {}, # Map of thread_id -> stats
                "leaderboard": {}   # Cached leaderboard data
            }
        )
        
        # Queue for batching analytics updates
        self.analytics_queue = defaultdict(list)  # guild_id -> list of updates
        self.queue_lock = asyncio.Lock()
        
    async def process_analytics_queue(self):
        """Background task to process batched analytics updates"""
        await self.bot.wait_until_ready()
        
        while self.bot.is_ready():
            try:
                # Process queues for each guild
                async with self.queue_lock:
                    guilds_to_process = list(self.analytics_queue.keys())
                    
                for guild_id in guilds_to_process:
                    # Get the guild's queue
                    async with self.queue_lock:
                        if guild_id not in self.analytics_queue:
                            continue
                            
                        # Get updates and clear the queue
                        updates = self.analytics_queue[guild_id].copy()
                        self.analytics_queue[guild_id].clear()
                        
                    # Skip empty queues
                    if not updates:
                        continue
                        
                    # Process the updates
                    await self._process_analytics_updates(guild_id, updates)
                    
            except Exception as e:
                log.error(f"Error processing analytics queue: {e}")
                
            # Wait before next processing (30 seconds)
            await asyncio.sleep(30)
            
    async def _process_analytics_updates(self, guild_id: int, updates: List[Dict]):
        """Process a batch of analytics updates for a guild"""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
                
            # Get current analytics data
            async with self.config.guild(guild).analytics_data() as analytics_data:
                # Initialize data structures if they don't exist
                if "forum_stats" not in analytics_data:
                    analytics_data["forum_stats"] = {}
                if "user_stats" not in analytics_data:
                    analytics_data["user_stats"] = {}
                if "thread_stats" not in analytics_data:
                    analytics_data["thread_stats"] = {}
                
                # Process each update
                for update in updates:
                    update_type = update.get("type")
                    
                    if update_type == "message":
                        await self._process_message_update(update, analytics_data)
                    elif update_type == "thread_create":
                        await self._process_thread_create_update(update, analytics_data)
                    elif update_type == "reaction":
                        await self._process_reaction_update(update, analytics_data)
                        
                # Recalculate leaderboard if needed
                if updates and "leaderboard" in analytics_data:
                    analytics_data["leaderboard"] = self._calculate_leaderboard(analytics_data)
                    
        except Exception as e:
            log.error(f"Error processing analytics updates: {e}")
    
    async def _process_message_update(self, update: Dict, analytics_data: Dict):
        """Process a message analytics update"""
        user_id = str(update.get("user_id"))
        thread_id = str(update.get("thread_id"))
        forum_id = str(update.get("forum_id"))
        content_length = update.get("content_length", 0)
        timestamp = update.get("timestamp", time.time())
        
        # Update user stats
        if user_id not in analytics_data["user_stats"]:
            analytics_data["user_stats"][user_id] = {
                "message_count": 0,
                "thread_count": 0,
                "total_content_length": 0,
                "last_active": 0,
                "reactions_given": 0,
                "reactions_received": 0,
                "forums_active": []
            }
            
        analytics_data["user_stats"][user_id]["message_count"] += 1
        analytics_data["user_stats"][user_id]["total_content_length"] += content_length
        analytics_data["user_stats"][user_id]["last_active"] = max(
            analytics_data["user_stats"][user_id]["last_active"],
            timestamp
        )
        
        # Add forum to active forums if not already there
        if forum_id not in analytics_data["user_stats"][user_id]["forums_active"]:
            analytics_data["user_stats"][user_id]["forums_active"].append(forum_id)
            
        # Update thread stats
        if thread_id not in analytics_data["thread_stats"]:
            analytics_data["thread_stats"][thread_id] = {
                "creator_id": update.get("thread_creator_id", "unknown"),
                "forum_id": forum_id,
                "message_count": 0,
                "participant_ids": [],
                "created_at": update.get("thread_created_at", timestamp),
                "last_active": timestamp,
                "view_count": 0
            }
            
        analytics_data["thread_stats"][thread_id]["message_count"] += 1
        analytics_data["thread_stats"][thread_id]["last_active"] = max(
            analytics_data["thread_stats"][thread_id]["last_active"],
            timestamp
        )
        
        # Add user to participants if not already there
        if user_id not in analytics_data["thread_stats"][thread_id]["participant_ids"]:
            analytics_data["thread_stats"][thread_id]["participant_ids"].append(user_id)
            
        # Update forum stats
        if forum_id not in analytics_data["forum_stats"]:
            analytics_data["forum_stats"][forum_id] = {
                "message_count": 0,
                "thread_count": 0,
                "participant_ids": [],
                "last_active": timestamp,
                "most_active_threads": []
            }
            
        analytics_data["forum_stats"][forum_id]["message_count"] += 1
        analytics_data["forum_stats"][forum_id]["last_active"] = max(
            analytics_data["forum_stats"][forum_id]["last_active"],
            timestamp
        )
        
        # Add user to participants if not already there
        if user_id not in analytics_data["forum_stats"][forum_id]["participant_ids"]:
            analytics_data["forum_stats"][forum_id]["participant_ids"].append(user_id)
            
        # Add thread to most active if not already there (up to 10)
        if thread_id not in analytics_data["forum_stats"][forum_id]["most_active_threads"]:
            if len(analytics_data["forum_stats"][forum_id]["most_active_threads"]) < 10:
                analytics_data["forum_stats"][forum_id]["most_active_threads"].append(thread_id)
                
    async def _process_thread_create_update(self, update: Dict, analytics_data: Dict):
        """Process a thread creation analytics update"""
        user_id = str(update.get("user_id"))
        thread_id = str(update.get("thread_id"))
        forum_id = str(update.get("forum_id"))
        timestamp = update.get("timestamp", time.time())
        
        # Update user stats
        if user_id not in analytics_data["user_stats"]:
            analytics_data["user_stats"][user_id] = {
                "message_count": 0,
                "thread_count": 0,
                "total_content_length": 0,
                "last_active": 0,
                "reactions_given": 0,
                "reactions_received": 0,
                "forums_active": []
            }
            
        analytics_data["user_stats"][user_id]["thread_count"] += 1
        analytics_data["user_stats"][user_id]["last_active"] = max(
            analytics_data["user_stats"][user_id]["last_active"],
            timestamp
        )
        
        # Add forum to active forums if not already there
        if forum_id not in analytics_data["user_stats"][user_id]["forums_active"]:
            analytics_data["user_stats"][user_id]["forums_active"].append(forum_id)
            
        # Create thread stats
        if thread_id not in analytics_data["thread_stats"]:
            analytics_data["thread_stats"][thread_id] = {
                "creator_id": user_id,
                "forum_id": forum_id,
                "message_count": 0,
                "participant_ids": [user_id],
                "created_at": timestamp,
                "last_active": timestamp,
                "view_count": 0
            }
            
        # Update forum stats
        if forum_id not in analytics_data["forum_stats"]:
            analytics_data["forum_stats"][forum_id] = {
                "message_count": 0,
                "thread_count": 0,
                "participant_ids": [],
                "last_active": timestamp,
                "most_active_threads": []
            }
            
        analytics_data["forum_stats"][forum_id]["thread_count"] += 1
        analytics_data["forum_stats"][forum_id]["last_active"] = max(
            analytics_data["forum_stats"][forum_id]["last_active"],
            timestamp
        )
        
        # Add user to participants if not already there
        if user_id not in analytics_data["forum_stats"][forum_id]["participant_ids"]:
            analytics_data["forum_stats"][forum_id]["participant_ids"].append(user_id)
            
    async def _process_reaction_update(self, update: Dict, analytics_data: Dict):
        """Process a reaction analytics update"""
        user_id = str(update.get("user_id"))
        target_user_id = str(update.get("target_user_id"))
        thread_id = str(update.get("thread_id"))
        timestamp = update.get("timestamp", time.time())
        
        # Update reaction giver stats
        if user_id not in analytics_data["user_stats"]:
            analytics_data["user_stats"][user_id] = {
                "message_count": 0,
                "thread_count": 0,
                "total_content_length": 0,
                "last_active": 0,
                "reactions_given": 0,
                "reactions_received": 0,
                "forums_active": []
            }
            
        analytics_data["user_stats"][user_id]["reactions_given"] += 1
        analytics_data["user_stats"][user_id]["last_active"] = max(
            analytics_data["user_stats"][user_id]["last_active"],
            timestamp
        )
        
        # Update reaction receiver stats
        if target_user_id not in analytics_data["user_stats"]:
            analytics_data["user_stats"][target_user_id] = {
                "message_count": 0,
                "thread_count": 0,
                "total_content_length": 0,
                "last_active": 0,
                "reactions_given": 0,
                "reactions_received": 0,
                "forums_active": []
            }
            
        analytics_data["user_stats"][target_user_id]["reactions_received"] += 1
        
    def _calculate_leaderboard(self, analytics_data: Dict) -> Dict:
        """Calculate leaderboard rankings from analytics data"""
        leaderboard = {
            "most_messages": [],
            "most_threads": [],
            "most_active_forums": [],
            "most_active_threads": []
        }
        
        # Most messages by user
        users_by_messages = sorted(
            analytics_data["user_stats"].items(),
            key=lambda x: x[1]["message_count"],
            reverse=True
        )
        leaderboard["most_messages"] = [
            {"user_id": user_id, "count": stats["message_count"]}
            for user_id, stats in users_by_messages[:10]
        ]
        
        # Most threads by user
        users_by_threads = sorted(
            analytics_data["user_stats"].items(),
            key=lambda x: x[1]["thread_count"],
            reverse=True
        )
        leaderboard["most_threads"] = [
            {"user_id": user_id, "count": stats["thread_count"]}
            for user_id, stats in users_by_threads[:10]
        ]
        
        # Most active forums
        forums_by_activity = sorted(
            analytics_data["forum_stats"].items(),
            key=lambda x: x[1]["message_count"],
            reverse=True
        )
        leaderboard["most_active_forums"] = [
            {"forum_id": forum_id, "count": stats["message_count"]}
            for forum_id, stats in forums_by_activity[:10]
        ]
        
        # Most active threads
        threads_by_activity = sorted(
            analytics_data["thread_stats"].items(),
            key=lambda x: x[1]["message_count"],
            reverse=True
        )
        leaderboard["most_active_threads"] = [
            {"thread_id": thread_id, "count": stats["message_count"]}
            for thread_id, stats in threads_by_activity[:10]
        ]
        
        return leaderboard
    
    def track_message(self, message):
        """Track a message for analytics"""
        # Skip if not in a thread or if author is a bot
        if not isinstance(message.channel, discord.Thread) or message.author.bot:
            return
            
        # Skip if parent is not a forum channel
        parent = message.channel.parent
        if not parent or not isinstance(parent, discord.ForumChannel):
            return
            
        # Create update data
        update = {
            "type": "message",
            "user_id": message.author.id,
            "thread_id": message.channel.id,
            "forum_id": parent.id,
            "content_length": len(message.content),
            "timestamp": message.created_at.timestamp(),
            "thread_creator_id": message.channel.owner_id,
            "thread_created_at": message.channel.created_at.timestamp()
        }
        
        # Add to queue
        asyncio.create_task(self._add_to_queue(message.guild.id, update))
    
    def track_thread_create(self, thread):
        """Track thread creation for analytics"""
        # Skip if parent is not a forum channel
        parent = thread.parent
        if not parent or not isinstance(parent, discord.ForumChannel):
            return
            
        # Create update data
        update = {
            "type": "thread_create",
            "user_id": thread.owner_id,
            "thread_id": thread.id,
            "forum_id": parent.id,
            "timestamp": thread.created_at.timestamp()
        }
        
        # Add to queue
        asyncio.create_task(self._add_to_queue(thread.guild.id, update))
    
    def track_reaction(self, reaction, user):
        """Track reaction for analytics"""
        # Skip if not in a thread or if user is a bot
        if not isinstance(reaction.message.channel, discord.Thread) or user.bot:
            return
            
        # Skip if parent is not a forum channel
        parent = reaction.message.channel.parent
        if not parent or not isinstance(parent, discord.ForumChannel):
            return
            
        # Create update data
        update = {
            "type": "reaction",
            "user_id": user.id,
            "target_user_id": reaction.message.author.id,
            "thread_id": reaction.message.channel.id,
            "forum_id": parent.id,
            "timestamp": time.time()
        }
        
        # Add to queue
        asyncio.create_task(self._add_to_queue(reaction.message.guild.id, update))
    
    async def _add_to_queue(self, guild_id, update):
        """Add an analytics update to the processing queue"""
        async with self.queue_lock:
            self.analytics_queue[guild_id].append(update)
    
    async def show_forum_stats(self, ctx, forum_name=None):
        """Show statistics for a forum or all forums"""
        settings = await self.config.guild(ctx.guild).all()
        analytics_data = settings.get("analytics_data", {})
        
        # Check if analytics are enabled
        if not settings.get("analytics", {}).get("enabled", False):
            return await ctx.send("Analytics are disabled for this server.")
            
        # Get forum channels
        anime_category_name = settings.get("forums_category_name", "Anime Forums")
        category = discord.utils.get(ctx.guild.categories, name=anime_category_name)
        
        if not category:
            return await ctx.send(f"Could not find the {anime_category_name} category.")
            
        forum_channels = [
            channel for channel in category.channels
            if isinstance(channel, discord.ForumChannel)
        ]
        
        if not forum_channels:
            return await ctx.send("No forum channels found.")
            
        # If forum name specified, show stats for that forum
        if forum_name:
            # Find the forum
            forum = discord.utils.find(
                lambda c: c.name.lower() == forum_name.lower().replace(" ", "-") or
                          c.name.lower() == forum_name.lower(),
                forum_channels
            )
            
            if not forum:
                return await ctx.send(f"Could not find forum '{forum_name}'.")
                
            # Show stats for this forum
            await self._show_single_forum_stats(ctx, forum, analytics_data)
        else:
            # Show overview of all forums
            await self._show_all_forums_stats(ctx, forum_channels, analytics_data)
            
    async def _show_single_forum_stats(self, ctx, forum, analytics_data):
        """Show detailed statistics for a single forum"""
        forum_id = str(forum.id)
        forum_stats = analytics_data.get("forum_stats", {}).get(forum_id, {})
        
        if not forum_stats:
            return await ctx.send(f"No statistics available for {forum.name}.")
            
        # Create embed
        embed = discord.Embed(
            title=f"Statistics for {forum.name}",
            description="Detailed forum activity statistics",
            color=discord.Color.blue()
        )
        
        # Add basic stats
        message_count = forum_stats.get("message_count", 0)
        thread_count = forum_stats.get("thread_count", 0)
        participant_count = len(forum_stats.get("participant_ids", []))
        
        embed.add_field(name="Total Messages", value=str(message_count), inline=True)
        embed.add_field(name="Total Threads", value=str(thread_count), inline=True)
        embed.add_field(name="Unique Participants", value=str(participant_count), inline=True)
        
        # Add last activity
        last_active = forum_stats.get("last_active", 0)
        if last_active:
            last_active_str = datetime.fromtimestamp(last_active).strftime("%Y-%m-%d %H:%M")
            embed.add_field(name="Last Activity", value=last_active_str, inline=True)
            
        # Add top threads
        most_active_threads = forum_stats.get("most_active_threads", [])
        if most_active_threads:
            thread_list = []
            for thread_id in most_active_threads:
                thread = ctx.guild.get_thread(int(thread_id))
                if thread:
                    thread_stats = analytics_data.get("thread_stats", {}).get(thread_id, {})
                    msg_count = thread_stats.get("message_count", 0)
                    thread_list.append(f"{thread.name}: {msg_count} messages")
                    
            if thread_list:
                embed.add_field(
                    name="Most Active Threads",
                    value="\n".join(thread_list[:5]),
                    inline=False
                )
                
        # Add top participants
        participant_ids = forum_stats.get("participant_ids", [])
        if participant_ids:
            participant_stats = []
            for user_id in participant_ids:
                user = ctx.guild.get_member(int(user_id))
                if user:
                    user_stats = analytics_data.get("user_stats", {}).get(user_id, {})
                    msg_count = user_stats.get("message_count", 0)
                    participant_stats.append((user, msg_count))
                    
            participant_stats.sort(key=lambda x: x[1], reverse=True)
            
            participant_list = [f"{user.display_name}: {count} messages" for user, count in participant_stats[:5]]
            if participant_list:
                embed.add_field(
                    name="Top Participants",
                    value="\n".join(participant_list),
                    inline=False
                )
                
        # Send the embed
        await ctx.send(embed=embed)
        
    async def _show_all_forums_stats(self, ctx, forum_channels, analytics_data):
        """Show overview statistics for all forums"""
        # Create embed
        embed = discord.Embed(
            title="Anime Forums Statistics",
            description="Overview of all forum activity",
            color=discord.Color.blue()
        )
        
        # Collect forum stats
        forum_stats_list = []
        for forum in forum_channels:
            forum_id = str(forum.id)
            stats = analytics_data.get("forum_stats", {}).get(forum_id, {})
            
            if stats:
                forum_stats_list.append({
                    "name": forum.name,
                    "id": forum_id,
                    "message_count": stats.get("message_count", 0),
                    "thread_count": stats.get("thread_count", 0),
                    "participant_count": len(stats.get("participant_ids", [])),
                    "last_active": stats.get("last_active", 0)
                })
                
        # Sort by activity
        forum_stats_list.sort(key=lambda x: x["message_count"], reverse=True)
        
        # Add total stats
        total_messages = sum(stats["message_count"] for stats in forum_stats_list)
        total_threads = sum(stats["thread_count"] for stats in forum_stats_list)
        
        embed.add_field(name="Total Forums", value=str(len(forum_channels)), inline=True)
        embed.add_field(name="Total Messages", value=str(total_messages), inline=True)
        embed.add_field(name="Total Threads", value=str(total_threads), inline=True)
        
        # Add top forums
        if forum_stats_list:
            top_forums = "\n".join(
                f"{stats['name']}: {stats['message_count']} messages, {stats['thread_count']} threads"
                for stats in forum_stats_list[:5]
            )
            embed.add_field(
                name="Most Active Forums",
                value=top_forums or "No forum activity recorded",
                inline=False
            )
            
        # Add most recent activity
        if forum_stats_list:
            recent_activity = sorted(forum_stats_list, key=lambda x: x["last_active"], reverse=True)
            recent_list = []
            
            for stats in recent_activity[:5]:
                if stats["last_active"]:
                    last_active_str = datetime.fromtimestamp(stats["last_active"]).strftime("%Y-%m-%d %H:%M")
                    recent_list.append(f"{stats['name']}: {last_active_str}")
                    
            if recent_list:
                embed.add_field(
                    name="Recent Activity",
                    value="\n".join(recent_list),
                    inline=False
                )
                
        # Send the embed
        await ctx.send(embed=embed)
        
        # Add note about detailed stats
        await ctx.send("Use `.stats [forum_name]` to view detailed statistics for a specific forum.")
