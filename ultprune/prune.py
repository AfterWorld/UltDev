import discord
import aiohttp
import asyncio
import datetime
import time
import logging
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box
from typing import Optional, List, Dict, Any, Tuple, Union, Set
from collections import defaultdict, OrderedDict
from dataclasses import dataclass
from enum import Enum

# Constants
class Constants:
    MAX_BULK_PURGE_AMOUNT = 100
    MAX_TARGETED_PRUNE_AMOUNT = 1000
    MAX_BATCH_SIZE = 100
    RATE_LIMIT_DELAY = 0.5
    OLD_MESSAGE_DELAY = 0.5
    MAX_LOG_ENTRIES = 25000
    CACHE_TTL = 86400  # 24 hours
    CACHE_MAX_SIZE = 100
    MAX_RETRIES = 3
    API_TIMEOUT = 10
    CONCURRENT_CHANNELS = 5
    SEARCH_LIMIT_MULTIPLIER = 3
    REASONABLE_SEARCH_LIMIT = 500

class LockdownLevel(Enum):
    STAFF = "staff"
    LEVEL_1 = "1"
    LEVEL_5 = "5"
    LEVEL_10 = "10"
    LEVEL_15 = "15"
    LEVEL_20 = "20"
    LEVEL_25 = "25"
    LEVEL_30 = "30"
    LEVEL_35 = "35"
    LEVEL_40 = "40"
    LEVEL_45 = "45"
    LEVEL_50 = "50"
    LEVEL_55 = "55"
    LEVEL_65 = "65"
    LEVEL_70 = "70"
    WORST_GENERATION = "wg"

@dataclass
class PruneStats:
    """Statistics for prune operations."""
    total_deleted: int = 0
    channels_affected: int = 0
    errors_encountered: int = 0
    processing_time: float = 0.0

@dataclass
class LogEntry:
    """Structured log entry for deleted messages."""
    user_id: int
    user_name: str
    content: str
    timestamp: str
    channel_id: int
    channel_name: str
    message_id: int

class TTLCache(OrderedDict):
    """Time-based LRU cache with automatic expiration of items."""
    
    def __init__(self, ttl: int = Constants.CACHE_TTL, max_size: int = Constants.CACHE_MAX_SIZE, *args, **kwargs):
        """Initialize the TTL cache.
        
        Args:
            ttl: Time to live in seconds
            max_size: Maximum number of items in cache
        """
        self.ttl = ttl
        self.max_size = max_size
        super().__init__(*args, **kwargs)
    
    def __setitem__(self, key, value):
        """Set an item with timestamp."""
        self._clean_expired()
        
        super().__setitem__(key, {
            'data': value,
            'timestamp': time.time()
        })
        
        if len(self) > self.max_size:
            self.popitem(last=False)
    
    def __getitem__(self, key):
        """Get an item, return None if expired."""
        item = super().__getitem__(key)
        
        if time.time() - item['timestamp'] > self.ttl:
            del self[key]
            raise KeyError(key)
            
        return item['data']
    
    def get(self, key, default=None):
        """Get an item with a default value if not found or expired."""
        try:
            return self[key]
        except KeyError:
            return default
    
    def _clean_expired(self):
        """Remove all expired entries."""
        now = time.time()
        expired_keys = [
            k for k, v in list(self.items()) 
            if now - v['timestamp'] > self.ttl
        ]
        for k in expired_keys:
            del self[k]

class ChannelProtectionManager:
    """Manages protected channels configuration."""
    
    def __init__(self, config):
        self.config = config
        
    async def get_protected_channels(self, guild: discord.Guild) -> List[int]:
        """Get protected channel IDs for a guild."""
        custom_protected = await self.config.guild(guild).protected_channels()
        if custom_protected:
            return custom_protected
        return self._get_default_protected_channels()
    
    def _get_default_protected_channels(self) -> List[int]:
        """Get default protected channels - should be configured per server."""
        return []
    
    async def add_protected_channel(self, guild: discord.Guild, channel_id: int):
        """Add a channel to protected list."""
        async with self.config.guild(guild).protected_channels() as protected:
            if channel_id not in protected:
                protected.append(channel_id)
    
    async def remove_protected_channel(self, guild: discord.Guild, channel_id: int):
        """Remove a channel from protected list."""
        async with self.config.guild(guild).protected_channels() as protected:
            if channel_id in protected:
                protected.remove(channel_id)

class RoleManager:
    """Manages role configurations for lockdown system."""
    
    def __init__(self):
        # Default role mappings - should be configurable per server
        self.default_level_roles = {
            LockdownLevel.LEVEL_1: 644731031701684226,
            LockdownLevel.LEVEL_5: 644731127738662922,
            LockdownLevel.LEVEL_10: 644731476977516544,
            LockdownLevel.LEVEL_15: 644731543415291911,
            LockdownLevel.LEVEL_20: 644731600382328843,
            LockdownLevel.LEVEL_25: 644731635509755906,
            LockdownLevel.LEVEL_30: 644731658444079124,
            LockdownLevel.LEVEL_35: 644731682343223317,
            LockdownLevel.LEVEL_40: 644731722415472650,
            LockdownLevel.LEVEL_45: 655587092738342942,
            LockdownLevel.LEVEL_50: 655587094030450689,
            LockdownLevel.LEVEL_55: 655587098144800769,
            LockdownLevel.LEVEL_65: 655587096529993738,
            LockdownLevel.LEVEL_70: 655587099579514919,
            LockdownLevel.WORST_GENERATION: 800825522653233195,
            LockdownLevel.STAFF: 700014289418977341
        }
    
    async def get_role_id(self, guild: discord.Guild, level: LockdownLevel, config) -> Optional[int]:
        """Get role ID for a lockdown level."""
        # Try to get custom role mapping first
        custom_roles = await config.guild(guild).custom_level_roles()
        if level.value in custom_roles:
            return custom_roles[level.value]
        
        # Fall back to default
        return self.default_level_roles.get(level)
    
    async def set_custom_role(self, guild: discord.Guild, level: LockdownLevel, role_id: int, config):
        """Set custom role for a level."""
        async with config.guild(guild).custom_level_roles() as custom_roles:
            custom_roles[level.value] = role_id

class MessageProcessor:
    """Handles message deletion operations."""
    
    @staticmethod
    async def delete_messages_in_batches(channel: discord.TextChannel, 
                                       messages: List[discord.Message]) -> PruneStats:
        """Delete messages in efficient batches respecting Discord's API limits."""
        if not messages:
            return PruneStats()
        
        start_time = time.time()
        stats = PruneStats()
        
        # Sort messages by ID (effectively by timestamp)
        messages.sort(key=lambda m: m.id)
        
        # Separate messages by age
        two_weeks_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
        recent_messages = [msg for msg in messages if msg.created_at > two_weeks_ago]
        old_messages = [msg for msg in messages if msg.created_at <= two_weeks_ago]
        
        # Bulk delete recent messages
        if recent_messages:
            batches = [recent_messages[i:i + Constants.MAX_BATCH_SIZE] 
                      for i in range(0, len(recent_messages), Constants.MAX_BATCH_SIZE)]
            
            for batch in batches:
                try:
                    await channel.delete_messages(batch)
                    stats.total_deleted += len(batch)
                    
                    if len(batches) > 1:
                        await asyncio.sleep(Constants.RATE_LIMIT_DELAY)
                        
                except Exception as e:
                    logging.warning(f"Bulk delete failed in {channel.name}: {e}")
                    stats.errors_encountered += 1
                    # Fallback to individual deletion
                    for msg in batch:
                        try:
                            await msg.delete()
                            stats.total_deleted += 1
                            await asyncio.sleep(Constants.OLD_MESSAGE_DELAY)
                        except Exception:
                            stats.errors_encountered += 1
        
        # Delete old messages individually
        if old_messages:
            for msg in old_messages:
                try:
                    await msg.delete()
                    stats.total_deleted += 1
                    await asyncio.sleep(Constants.OLD_MESSAGE_DELAY)
                except Exception:
                    stats.errors_encountered += 1
        
        stats.processing_time = time.time() - start_time
        stats.channels_affected = 1
        return stats

class LogManager:
    """Manages logging operations."""
    
    def __init__(self, session_factory, config):
        self.session_factory = session_factory
        self.config = config
        self.logs_api_url = "https://api.mclo.gs/1/log"
    
    async def upload_to_logs_service(self, content: str, title: str = "Prune logs") -> str:
        """Upload content to mclo.gs and return the URL."""
        content_with_title = f"# {title}\n\n{content}"
        
        session = await self.session_factory()
        if not session:
            return "Error: No HTTP session available"
        
        for attempt in range(Constants.MAX_RETRIES):
            try:
                data = {'content': content_with_title}
                async with session.post(self.logs_api_url, data=data, 
                                      timeout=Constants.API_TIMEOUT) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get('success'):
                            return response_data['url']
                        else:
                            error = response_data.get('error', 'Unknown error')
                            if attempt == Constants.MAX_RETRIES - 1:
                                return f"Upload error: {error}"
                    else:
                        if attempt == Constants.MAX_RETRIES - 1:
                            return f"Failed to upload: {response.status}"
            except Exception as e:
                if attempt == Constants.MAX_RETRIES - 1:
                    return f"Error uploading log: {str(e)}"
            
            if attempt < Constants.MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
        
        return "Failed to upload log after multiple attempts"
    
    @staticmethod
    def format_log_entries(log_entries: List[LogEntry]) -> str:
        """Format log entries for upload."""
        return "\n".join([
            f"[{entry.timestamp}] #{entry.channel_name}: {entry.user_name}: {entry.content}"
            for entry in log_entries
        ])
    
    async def store_log_entries(self, guild_id: int, log_entries: List[LogEntry], cache: TTLCache):
        """Store log entries in cache and database."""
        # Group by channel
        by_channel = defaultdict(list)
        for entry in log_entries:
            by_channel[entry.channel_id].append(entry)
        
        for channel_id, entries in by_channel.items():
            cache_key = f"{guild_id}:{channel_id}"
            
            # Store in memory cache
            if cache_key not in cache:
                cache[cache_key] = []
            cache[cache_key].extend([entry.__dict__ for entry in entries])
            
            # Store in database
            async with self.config.guild_from_id(guild_id).log_refs() as log_refs:
                channel_key = str(channel_id)
                if channel_key not in log_refs:
                    log_refs[channel_key] = []
                
                log_refs[channel_key].extend([entry.__dict__ for entry in entries])
                
                # Keep only recent entries
                if len(log_refs[channel_key]) > Constants.CACHE_MAX_SIZE:
                    log_refs[channel_key] = log_refs[channel_key][-Constants.CACHE_MAX_SIZE:]

class Prune(commands.Cog):
    """A cog for pruning and nuking messages with log uploads to mclo.gs."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1303050205)
        
        # Updated default guild configuration
        default_guild = {
            "staff_channel": None,
            "staff_role": None,
            "log_refs": {},
            "silenced_role": None,
            "lockdown_status": False,
            "lockdown_level": None,
            "protected_channels": [],  # Now empty by default
            "channel_permissions": {},
            "custom_level_roles": {},  # Custom role mappings
            "max_bulk_purge": Constants.MAX_BULK_PURGE_AMOUNT,
            "max_targeted_prune": Constants.MAX_TARGETED_PRUNE_AMOUNT,
            "auto_delete_confirmations": True,
            "log_retention_days": 7
        }
        self.config.register_guild(**default_guild)
        
        # Initialize managers
        self.deleted_logs = TTLCache()
        self.session = None
        self.deletion_tasks = {}
        self.cooldowns = {}
        
        self.protection_manager = ChannelProtectionManager(self.config)
        self.role_manager = RoleManager()
        self.log_manager = LogManager(self._get_session, self.config)
        self.message_processor = MessageProcessor()

    async def _get_session(self):
        """Get HTTP session, initializing if needed."""
        if not self.session:
            await self.initialize()
        return self.session

    async def initialize(self):
        """Initialize the aiohttp session."""
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Clean up the aiohttp session on unload."""
        if self.session:
            await self.session.close()
            
        for task in self.deletion_tasks.values():
            if not task.done():
                task.cancel()

    def _validate_amount(self, amount: int, max_amount: int, operation: str) -> bool:
        """Validate message amount for operations."""
        if amount <= 0:
            return False
        if amount > max_amount:
            return False
        return True

    async def send_to_staff_channel(self, ctx: commands.Context, user: discord.Member, 
                                  channels: List[discord.TextChannel], stats: PruneStats, 
                                  log_url: str, command_type: str = "Prune"):
        """Send notification to the staff channel if configured."""
        staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        
        if not staff_channel_id:
            return
            
        staff_channel = ctx.guild.get_channel(staff_channel_id)
        if not staff_channel:
            return
            
        # Create detailed message for staff
        staff_message = f"**{command_type} Action Log**\n"
        staff_message += f"• Moderator: {ctx.author.mention} ({ctx.author.name})\n"
        staff_message += f"• Target: {user.mention} ({user.name})\n"
        
        if len(channels) == 1:
            staff_message += f"• Channel: {channels[0].mention}\n"
        else:
            staff_message += f"• Channels: {len(channels)} channels\n"
            
        staff_message += f"• Messages Deleted: {stats.total_deleted}\n"
        if stats.errors_encountered > 0:
            staff_message += f"• Errors: {stats.errors_encountered}\n"
        staff_message += f"• Processing Time: {stats.processing_time:.2f}s\n"
        staff_message += f"• Log URL: {log_url}\n"
        
        # Add role mention if configured
        if staff_role_id:
            role = ctx.guild.get_role(staff_role_id)
            if role:
                staff_message = f"{role.mention}\n" + staff_message
        
        await staff_channel.send(staff_message)

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(2, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def prune(self, ctx: commands.Context, amount_or_user: Union[int, discord.Member], 
                    amount_if_user: Optional[int] = None, 
                    channel: Optional[discord.TextChannel] = None, 
                    *, keyword: Optional[str] = None):
        """
        Delete messages from a channel.
        
        Examples:
        - `.prune 15` - Delete the last 15 messages in the current channel
        - `.prune @user 100` - Delete the last 100 messages from a specific user
        - `.prune @user 200 #channel` - Delete the last 200 messages from a user in a specific channel
        - `.prune @user 15 #channel keyword` - Delete messages containing the keyword
        """
        # Check if it's a Member object (user mention or user object)
        if isinstance(amount_or_user, discord.Member):
            if amount_if_user is None:
                await ctx.send("Please specify the number of messages to delete.\nUsage: `.prune @user 100`")
                return
            await self.targeted_prune(ctx, amount_or_user, amount_if_user, channel, keyword)
        # Check if it's an integer that could be a reasonable message count (not a user ID)
        elif isinstance(amount_or_user, int) and amount_or_user <= 10000:
            # This is likely a message count for bulk purge
            await self.simple_purge(ctx, amount_or_user)
        else:
            # Large integers are likely user IDs that failed to convert to Member
            await ctx.send("Invalid parameters. Use `.prune 15` for bulk deletion or `.prune @user 100` for targeted deletion.\n"
                          "Make sure to mention the user properly with @ or use their current username.")

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.max_concurrency(2, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def pruneuser(self, ctx: commands.Context, user: discord.Member, amount: int, 
                       channel: Optional[discord.TextChannel] = None, *, keyword: Optional[str] = None):
        """
        Delete messages from a specific user (alternative command with clearer syntax).
        
        Examples:
        - `.pruneuser @user 100` - Delete 100 messages from user
        - `.pruneuser @user 50 #channel` - Delete 50 messages from user in specific channel
        - `.pruneuser @user 25 #channel keyword` - Delete messages containing keyword
        """
        await self.targeted_prune(ctx, user, amount, channel, keyword)

    async def simple_purge(self, ctx: commands.Context, amount: int):
        """Delete a specific number of recent messages in a channel."""
        max_bulk = await self.config.guild(ctx.guild).max_bulk_purge()
        
        if not self._validate_amount(amount, max_bulk, "bulk purge"):
            return await ctx.send(f"Amount must be between 1 and {max_bulk} for bulk purge operations.")
            
        async with ctx.typing():
            messages_to_delete = []
            
            async for message in ctx.channel.history(limit=amount+1):
                if message.id != ctx.message.id:
                    messages_to_delete.append(message)
                    if len(messages_to_delete) >= amount:
                        break
                        
            if not messages_to_delete:
                return await ctx.send("No messages found to delete.")
            
            # Create log entries
            log_entries = [
                LogEntry(
                    user_id=msg.author.id,
                    user_name=msg.author.name,
                    content=msg.content,
                    timestamp=msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    channel_id=msg.channel.id,
                    channel_name=msg.channel.name,
                    message_id=msg.id
                )
                for msg in messages_to_delete
            ]
            
            # Upload to mclo.gs
            formatted_logs = self.log_manager.format_log_entries(log_entries)
            log_title = f"Channel Purge - {ctx.channel.name}"
            log_url = await self.log_manager.upload_to_logs_service(formatted_logs, log_title)
            
            # Delete messages
            stats = await self.message_processor.delete_messages_in_batches(ctx.channel, messages_to_delete)
            
            # Store logs
            await self.log_manager.store_log_entries(ctx.guild.id, log_entries, self.deleted_logs)
            
        # Send confirmation
        success_msg = await ctx.send(f"Deleted {stats.total_deleted} messages in {stats.processing_time:.2f}s.")
        
        # Send to staff channel
        await self.send_staff_notification_bulk(ctx, stats, log_url)
        
        # Auto-delete confirmation if enabled
        if await self.config.guild(ctx.guild).auto_delete_confirmations():
            await asyncio.sleep(5)
            try:
                await success_msg.delete()
            except:
                pass

    async def targeted_prune(self, ctx: commands.Context, user: discord.Member, amount: int, 
                           channel: Optional[discord.TextChannel] = None, keyword: Optional[str] = None):
        """Delete the last <amount> messages from <user> in a specific channel."""
        max_targeted = await self.config.guild(ctx.guild).max_targeted_prune()
        
        if not self._validate_amount(amount, max_targeted, "targeted prune"):
            return await ctx.send(f"Amount must be between 1 and {max_targeted} for targeted prune operations.")

        if not channel:
            channel = ctx.channel
            
        async with ctx.typing():
            def check(msg):
                # Don't delete the command message itself
                if msg.id == ctx.message.id:
                    return False
                # Only delete messages from the specified user
                if msg.author.id != user.id:
                    return False
                # If keyword is specified, only delete messages containing it
                if keyword and keyword.lower() not in msg.content.lower():
                    return False
                return True

            messages_to_delete = []
            search_limit = min(Constants.REASONABLE_SEARCH_LIMIT, amount * Constants.SEARCH_LIMIT_MULTIPLIER)
            
            # Debug: Let's add some logging to see what's happening
            found_user_messages = 0
            total_checked = 0
            
            async for message in channel.history(limit=search_limit):
                total_checked += 1
                if message.author.id == user.id:
                    found_user_messages += 1
                    if check(message):
                        messages_to_delete.append(message)
                        if len(messages_to_delete) >= amount:
                            break
            
            if not messages_to_delete:
                # Provide more detailed feedback
                if found_user_messages == 0:
                    return await ctx.send(f"No messages from {user.mention} found in {channel.mention}. "
                                        f"Searched through the last {total_checked} messages.")
                elif keyword:
                    return await ctx.send(f"Found {found_user_messages} messages from {user.mention} but none containing '{keyword}' in {channel.mention}.")
                else:
                    return await ctx.send(f"Found {found_user_messages} messages from {user.mention} but couldn't delete them. They might be too old or protected.")

            # Create log entries
            log_entries = [
                LogEntry(
                    user_id=msg.author.id,
                    user_name=msg.author.name,
                    content=msg.content,
                    timestamp=msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    channel_id=msg.channel.id,
                    channel_name=msg.channel.name,
                    message_id=msg.id
                )
                for msg in messages_to_delete
            ]
            
            # Store logs before deletion
            await self.log_manager.store_log_entries(ctx.guild.id, log_entries, self.deleted_logs)
            
            # Upload to mclo.gs
            formatted_logs = self.log_manager.format_log_entries(log_entries)
            log_title = f"Prune {user.name} logs"
            log_url = await self.log_manager.upload_to_logs_service(formatted_logs, log_title)
            
            # Delete messages
            stats = await self.message_processor.delete_messages_in_batches(channel, messages_to_delete)

        # Send confirmation
        await ctx.send(f"Deleted {stats.total_deleted} messages from {user.mention} in {channel.mention} (took {stats.processing_time:.2f}s).")
        
        # Send to staff channel
        await self.send_to_staff_channel(ctx, user, [channel], stats, log_url)

    async def send_staff_notification_bulk(self, ctx: commands.Context, stats: PruneStats, log_url: str):
        """Send staff notification for bulk operations."""
        staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        
        if not staff_channel_id:
            return
            
        staff_channel = ctx.guild.get_channel(staff_channel_id)
        if not staff_channel:
            return
        
        staff_message = f"**Bulk Purge Log**\n"
        staff_message += f"• Moderator: {ctx.author.mention} ({ctx.author.name})\n"
        staff_message += f"• Channel: {ctx.channel.mention}\n"
        staff_message += f"• Messages Deleted: {stats.total_deleted}\n"
        staff_message += f"• Processing Time: {stats.processing_time:.2f}s\n"
        if stats.errors_encountered > 0:
            staff_message += f"• Errors: {stats.errors_encountered}\n"
        staff_message += f"• Log URL: {log_url}\n"
        
        if staff_role_id:
            role = ctx.guild.get_role(staff_role_id)
            if role:
                staff_message = f"{role.mention}\n" + staff_message
        
        await staff_channel.send(staff_message)

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def prunelogs(self, ctx: commands.Context, user: discord.Member, 
                        limit: Optional[int] = 20, channel: Optional[discord.TextChannel] = None):
        """Retrieve pruned messages for a user."""
        if limit > Constants.CACHE_MAX_SIZE:
            return await ctx.send(f"Limit cannot exceed {Constants.CACHE_MAX_SIZE} messages.")

        if not channel:
            channel = ctx.channel

        cache_key = f"{ctx.guild.id}:{channel.id}"
        
        # Try memory cache first
        logs = self.deleted_logs.get(cache_key, [])
        
        # Fall back to database
        if not logs:
            guild_data = await self.config.guild(ctx.guild).log_refs()
            logs = guild_data.get(str(channel.id), [])
        
        if not logs:
            return await ctx.send(f"No pruned messages logged for {channel.mention}.")

        # Filter by user
        user_logs = [log for log in logs if log.get("user_id") == user.id]

        if not user_logs:
            return await ctx.send(f"No logs found for {user.mention} in {channel.mention}.")

        # Sort and limit
        user_logs = sorted(user_logs, key=lambda log: log.get("timestamp", ""), reverse=True)[:limit]
        
        formatted_logs = "\n".join([
            f"[{log.get('timestamp', 'Unknown')}] {log.get('user_name', 'Unknown')}: {log.get('content', 'No content')}" 
            for log in user_logs
        ])

        await ctx.send(box(formatted_logs, lang="yaml"))

    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def nuke(self, ctx: commands.Context, user: discord.Member):
        """Delete all messages from a user across all guild channels and assign the Silenced role."""
        async with ctx.typing():
            text_channels = [
                channel for channel in ctx.guild.text_channels 
                if channel.permissions_for(ctx.guild.me).manage_messages
            ]
            
            if not text_channels:
                return await ctx.send("I don't have permission to manage messages in any channels.")
                
            status_msg = await ctx.send(f"Nuking messages from {user.mention} in {len(text_channels)} channels...")
            
            total_stats = PruneStats()
            all_log_entries = []
            affected_channels = []
            
            # Process channels in chunks
            for i in range(0, len(text_channels), Constants.CONCURRENT_CHANNELS):
                channel_chunk = text_channels[i:i+Constants.CONCURRENT_CHANNELS]
                
                await status_msg.edit(content=f"Scanning channels... ({i}/{len(text_channels)})")
                
                for channel in channel_chunk:
                    try:
                        messages_to_delete = []
                        
                        # Collect all messages from the user
                        async for msg in channel.history(limit=None):
                            if msg.author.id == user.id:
                                messages_to_delete.append(msg)
                        
                        if messages_to_delete:
                            affected_channels.append(channel)
                            
                            # Create log entries
                            log_entries = [
                                LogEntry(
                                    user_id=msg.author.id,
                                    user_name=msg.author.name,
                                    content=msg.content,
                                    timestamp=msg.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                                    channel_id=msg.channel.id,
                                    channel_name=msg.channel.name,
                                    message_id=msg.id
                                )
                                for msg in messages_to_delete
                            ]
                            all_log_entries.extend(log_entries)
                            
                            # Delete messages
                            stats = await self.message_processor.delete_messages_in_batches(channel, messages_to_delete)
                            total_stats.total_deleted += stats.total_deleted
                            total_stats.errors_encountered += stats.errors_encountered
                            total_stats.processing_time += stats.processing_time
                            
                    except Exception as e:
                        logging.warning(f"Error processing channel {channel.name}: {e}")
                        total_stats.errors_encountered += 1
                        continue
                
                await asyncio.sleep(1)  # Rate limit protection
            
            total_stats.channels_affected = len(affected_channels)
            
            # Handle logging
            if all_log_entries:
                # Limit log entries for mclo.gs
                if len(all_log_entries) > Constants.MAX_LOG_ENTRIES:
                    all_log_entries = all_log_entries[:Constants.MAX_LOG_ENTRIES]
                    await ctx.send(f"⚠️ More than {Constants.MAX_LOG_ENTRIES} messages found. Only the first {Constants.MAX_LOG_ENTRIES} will be logged.")
                    
                # Upload to mclo.gs
                formatted_logs = self.log_manager.format_log_entries(all_log_entries)
                log_title = f"Nuke {user.name} logs"
                log_url = await self.log_manager.upload_to_logs_service(formatted_logs, log_title)
                
                # Store logs
                await self.log_manager.store_log_entries(ctx.guild.id, all_log_entries, self.deleted_logs)
                
                # Send to staff channel
                await self.send_to_staff_channel(ctx, user, affected_channels, total_stats, log_url, "Nuke")
            
            # Handle silenced role
            silenced_role_id = await self.config.guild(ctx.guild).silenced_role()
            silenced_role = None
            
            if silenced_role_id:
                silenced_role = ctx.guild.get_role(silenced_role_id)
                
            if not silenced_role:
                silenced_role = discord.utils.get(ctx.guild.roles, name="Silenced")
                
                if not silenced_role:
                    await status_msg.edit(content="❌ The `Silenced` role does not exist. Please create it manually.")
                    return
                
                await self.config.guild(ctx.guild).silenced_role.set(silenced_role.id)
            
            # Assign silenced role
            try:
                await user.add_roles(silenced_role)
                await status_msg.edit(content=f"🚨 Nuked **{total_stats.total_deleted}** messages from {user.mention} across {total_stats.channels_affected} channels and assigned the `Silenced` role. (Completed in {total_stats.processing_time:.2f}s)")
            except discord.Forbidden:
                await status_msg.edit(content=f"🚨 Nuked **{total_stats.total_deleted}** messages from {user.mention} across {total_stats.channels_affected} channels, but I don't have permission to assign the `Silenced` role. (Completed in {total_stats.processing_time:.2f}s)")

    @commands.mod()
    @commands.guild_only()
    @commands.group()
    async def pruneset(self, ctx: commands.Context):
        """Configure the prune cog settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @pruneset.command(name="staffchannel")
    async def set_staff_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the staff channel for log notifications. Leave empty to disable."""
        if channel:
            await self.config.guild(ctx.guild).staff_channel.set(channel.id)
            await ctx.send(f"Staff channel set to {channel.mention}. Logs will be sent there.")
        else:
            await self.config.guild(ctx.guild).staff_channel.set(None)
            await ctx.send("Staff channel notifications disabled.")

    @pruneset.command(name="staffrole")
    async def set_staff_role(self, ctx: commands.Context, role: discord.Role = None):
        """Set the staff role to ping with logs. Leave empty to disable pings."""
        if role:
            await self.config.guild(ctx.guild).staff_role.set(role.id)
            await ctx.send(f"Staff role set to {role.mention}. This role will be pinged with logs.")
        else:
            await self.config.guild(ctx.guild).staff_role.set(None)
            await ctx.send("Staff role pings disabled.")

    @pruneset.command(name="silencedrole")
    async def set_silenced_role(self, ctx: commands.Context, role: discord.Role = None):
        """Set the silenced role for the nuke command."""
        if role:
            await self.config.guild(ctx.guild).silenced_role.set(role.id)
            await ctx.send(f"Silenced role set to {role.mention}.")
        else:
            await self.config.guild(ctx.guild).silenced_role.set(None)
            await ctx.send("Silenced role configuration removed.")

    @pruneset.command(name="levelrole")
    async def set_level_role(self, ctx: commands.Context, level: str, role: discord.Role = None):
        """Set a custom role for a lockdown level.
        
        Examples:
        - `.pruneset levelrole 5 @Level5Role` - Set custom role for level 5
        - `.pruneset levelrole staff @StaffRole` - Set custom staff role
        - `.pruneset levelrole 5` - Remove custom role for level 5
        """
        try:
            lockdown_level = LockdownLevel(level.lower())
        except ValueError:
            valid_levels = [level.value for level in LockdownLevel]
            await ctx.send(f"Invalid level. Valid levels: {', '.join(valid_levels)}")
            return
        
        if role:
            await self.role_manager.set_custom_role(ctx.guild, lockdown_level, role.id, self.config)
            await ctx.send(f"Custom role for level `{level}` set to {role.mention}.")
        else:
            async with self.config.guild(ctx.guild).custom_level_roles() as custom_roles:
                if level in custom_roles:
                    del custom_roles[level]
                    await ctx.send(f"Custom role for level `{level}` removed.")
                else:
                    await ctx.send(f"No custom role set for level `{level}`.")

    @pruneset.command(name="limits")
    async def set_limits(self, ctx: commands.Context, bulk_purge: int = None, targeted_prune: int = None):
        """Set message deletion limits.
        
        Examples:
        - `.pruneset limits 50 500` - Set bulk purge limit to 50, targeted prune to 500
        - `.pruneset limits 100` - Set only bulk purge limit
        """
        if bulk_purge is not None:
            if 1 <= bulk_purge <= 1000:
                await self.config.guild(ctx.guild).max_bulk_purge.set(bulk_purge)
                await ctx.send(f"Bulk purge limit set to {bulk_purge} messages.")
            else:
                await ctx.send("Bulk purge limit must be between 1 and 1000.")
                return
        
        if targeted_prune is not None:
            if 1 <= targeted_prune <= 5000:
                await self.config.guild(ctx.guild).max_targeted_prune.set(targeted_prune)
                await ctx.send(f"Targeted prune limit set to {targeted_prune} messages.")
            else:
                await ctx.send("Targeted prune limit must be between 1 and 5000.")
                return
        
        if bulk_purge is None and targeted_prune is None:
            current_bulk = await self.config.guild(ctx.guild).max_bulk_purge()
            current_targeted = await self.config.guild(ctx.guild).max_targeted_prune()
            await ctx.send(f"Current limits:\n• Bulk purge: {current_bulk}\n• Targeted prune: {current_targeted}")

    @pruneset.command(name="autodeleteconfirmations")
    async def set_auto_delete_confirmations(self, ctx: commands.Context, enabled: bool = None):
        """Enable or disable auto-deletion of confirmation messages."""
        if enabled is None:
            current = await self.config.guild(ctx.guild).auto_delete_confirmations()
            await ctx.send(f"Auto-delete confirmations: {'Enabled' if current else 'Disabled'}")
        else:
            await self.config.guild(ctx.guild).auto_delete_confirmations.set(enabled)
            await ctx.send(f"Auto-delete confirmations {'enabled' if enabled else 'disabled'}.")

    @pruneset.command(name="protectedchannels")
    async def manage_protected_channels(self, ctx: commands.Context, action: str = None, *channels: discord.TextChannel):
        """Manage protected channels.
        
        Examples:
        - `.pruneset protectedchannels list` - Show protected channels
        - `.pruneset protectedchannels add #channel1 #channel2` - Add channels
        - `.pruneset protectedchannels remove #channel1` - Remove channels
        - `.pruneset protectedchannels clear` - Clear all protected channels
        """
        if not action:
            await ctx.send("Usage: `.pruneset protectedchannels <list|add|remove|clear> [channels...]`")
            return
        
        if action.lower() == "list":
            protected_ids = await self.protection_manager.get_protected_channels(ctx.guild)
            if not protected_ids:
                await ctx.send("No protected channels configured.")
                return
            
            # Format in chunks to avoid message limits
            chunks = []
            current_chunk = "**Protected Channels:**\n"
            
            for ch_id in protected_ids:
                ch = ctx.guild.get_channel(ch_id)
                channel_text = f"• {ch.mention if ch else f'Unknown Channel (ID: {ch_id})'}\n"
                
                if len(current_chunk) + len(channel_text) > 1900:
                    chunks.append(current_chunk)
                    current_chunk = "**Protected Channels (continued):**\n"
                
                current_chunk += channel_text
            
            if current_chunk:
                chunks.append(current_chunk)
                
            for chunk in chunks:
                await ctx.send(chunk)
        
        elif action.lower() == "add":
            if not channels:
                await ctx.send("Please specify channels to add.")
                return
            
            added = []
            for channel in channels:
                await self.protection_manager.add_protected_channel(ctx.guild, channel.id)
                added.append(channel.mention)
            
            await ctx.send(f"Added {len(added)} channel(s) to protected list:\n" + "\n".join(added))
        
        elif action.lower() == "remove":
            if not channels:
                await ctx.send("Please specify channels to remove.")
                return
            
            removed = []
            for channel in channels:
                await self.protection_manager.remove_protected_channel(ctx.guild, channel.id)
                removed.append(channel.mention)
            
            await ctx.send(f"Removed {len(removed)} channel(s) from protected list:\n" + "\n".join(removed))
        
        elif action.lower() == "clear":
            await self.config.guild(ctx.guild).protected_channels.set([])
            await ctx.send("All protected channels cleared.")
        
        else:
            await ctx.send("Invalid action. Use: `list`, `add`, `remove`, or `clear`")

    @pruneset.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Show current prune settings."""
        staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        silenced_role_id = await self.config.guild(ctx.guild).silenced_role()
        lockdown_status = await self.config.guild(ctx.guild).lockdown_status()
        protected_channels = await self.protection_manager.get_protected_channels(ctx.guild)
        max_bulk = await self.config.guild(ctx.guild).max_bulk_purge()
        max_targeted = await self.config.guild(ctx.guild).max_targeted_prune()
        auto_delete = await self.config.guild(ctx.guild).auto_delete_confirmations()
        
        staff_channel = ctx.guild.get_channel(staff_channel_id) if staff_channel_id else None
        staff_role = ctx.guild.get_role(staff_role_id) if staff_role_id else None
        silenced_role = ctx.guild.get_role(silenced_role_id) if silenced_role_id else None
        
        message = "**Current Prune Settings**\n"
        message += f"• Staff Channel: {staff_channel.mention if staff_channel else 'Not set'}\n"
        message += f"• Staff Role: {staff_role.mention if staff_role else 'Not set'}\n"
        message += f"• Silenced Role: {silenced_role.mention if silenced_role else 'Not set'}\n"
        message += f"• Lockdown Status: {'Active' if lockdown_status else 'Inactive'}\n"
        message += f"• Protected Channels: {len(protected_channels)}\n"
        message += f"• Max Bulk Purge: {max_bulk} messages\n"
        message += f"• Max Targeted Prune: {max_targeted} messages\n"
        message += f"• Auto-delete Confirmations: {'Yes' if auto_delete else 'No'}\n"
        
        await ctx.send(message)

    async def lock_channels(self, ctx: commands.Context, role_id: int):
        """Lock all text channels except protected ones."""
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("❌ The required role does not exist.")
            return False

        protected_channel_ids = await self.protection_manager.get_protected_channels(ctx.guild)
        
        channels_to_lock = [
            channel for channel in ctx.guild.text_channels 
            if channel.id not in protected_channel_ids and 
            channel.permissions_for(ctx.guild.me).manage_channels
        ]
        
        if not channels_to_lock:
            await ctx.send("❌ No channels found to lock.")
            return False

        total_channels = len(channels_to_lock)
        processed = 0
        
        async with ctx.typing():
            status_msg = await ctx.send(f"🔒 Locking channels... (0/{total_channels})")
            
            chunk_size = Constants.CONCURRENT_CHANNELS
            for i in range(0, len(channels_to_lock), chunk_size):
                chunk = channels_to_lock[i:i+chunk_size]
                
                tasks = []
                for channel in chunk:
                    task = self.lock_single_channel(channel, ctx.guild.default_role, role)
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
                
                processed += len(chunk)
                await status_msg.edit(content=f"🔒 Locking channels... ({processed}/{total_channels})")
                
                if i + chunk_size < len(channels_to_lock):
                    await asyncio.sleep(1)
                
            await status_msg.edit(content=f"✅ Lockdown complete! {processed} channels locked successfully.")
            
        return True
    
    async def lock_single_channel(self, channel: discord.TextChannel, default_role: discord.Role, allowed_role: discord.Role):
        """Lock a single text channel."""
        try:
            overwrites = channel.overwrites_for(default_role)
            overwrites.send_messages = False
            await channel.set_permissions(default_role, overwrite=overwrites)
            
            overwrites = channel.overwrites_for(allowed_role)
            overwrites.send_messages = True
            await channel.set_permissions(allowed_role, overwrite=overwrites)
        except Exception as e:
            logging.warning(f"Failed to lock channel {channel.name}: {e}")
            
    async def unlock_channels(self, ctx: commands.Context):
        """Unlock all text channels except protected ones."""
        protected_channel_ids = await self.protection_manager.get_protected_channels(ctx.guild)
        
        channels_to_unlock = [
            channel for channel in ctx.guild.text_channels 
            if channel.id not in protected_channel_ids and
            channel.permissions_for(ctx.guild.me).manage_channels
        ]
        
        if not channels_to_unlock:
            await ctx.send("❌ No channels found to unlock.")
            return False

        total_channels = len(channels_to_unlock)
        processed = 0
        
        async with ctx.typing():
            status_msg = await ctx.send(f"🔓 Unlocking channels... (0/{total_channels})")
            
            chunk_size = Constants.CONCURRENT_CHANNELS
            for i in range(0, len(channels_to_unlock), chunk_size):
                chunk = channels_to_unlock[i:i+chunk_size]
                
                tasks = []
                for channel in chunk:
                    task = self.unlock_single_channel(channel, ctx.guild.default_role)
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
                
                processed += len(chunk)
                await status_msg.edit(content=f"🔓 Unlocking channels... ({processed}/{total_channels})")
                
                if i + chunk_size < len(channels_to_unlock):
                    await asyncio.sleep(1)
                
            await status_msg.edit(content=f"✅ Lockdown deactivated! {processed} channels unlocked successfully.")
            
        return True
    
    async def unlock_single_channel(self, channel: discord.TextChannel, default_role: discord.Role):
        """Unlock a single text channel."""
        try:
            overwrites = channel.overwrites_for(default_role)
            overwrites.send_messages = None
            await channel.set_permissions(default_role, overwrite=overwrites)
        except Exception as e:
            logging.warning(f"Failed to unlock channel {channel.name}: {e}")

    @commands.cooldown(1, 15, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def shield(self, ctx: commands.Context, action: str, level_or_staff: Optional[str] = None):
        """
        Activate or deactivate server lockdown mode.
        
        Examples:
        - `.shield activate 5` - Only Level 5+ users can talk
        - `.shield activate 15` - Only Level 15+ users can talk
        - `.shield activate staff` - Only staff can talk
        - `.shield deactivate` - End lockdown mode
        - `.shield status` - Check current lockdown status
        """
        if action.lower() == "activate":
            if not level_or_staff:
                available_levels = [level.value for level in LockdownLevel]
                return await ctx.send(f"❌ Please specify a level: {', '.join(available_levels)}")
            
            try:
                lockdown_level = LockdownLevel(level_or_staff.lower())
            except ValueError:
                available_levels = [level.value for level in LockdownLevel]
                return await ctx.send(f"❌ Invalid level. Available levels: {', '.join(available_levels)}")
                
            role_id = await self.role_manager.get_role_id(ctx.guild, lockdown_level, self.config)
            if not role_id:
                return await ctx.send(f"❌ No role configured for level `{level_or_staff}`. Use `.pruneset levelrole` to set it.")
            
            role = ctx.guild.get_role(role_id)
            if not role:
                return await ctx.send(f"❌ Role with ID {role_id} not found. Please reconfigure with `.pruneset levelrole`.")
            
            level_display = "Staff" if lockdown_level == LockdownLevel.STAFF else f"Level {level_or_staff}+"
            
            status_msg = await ctx.send(f"🛡️ **Activating Lockdown:** Only users with `{level_display}` can talk.")
            
            success = await self.lock_channels(ctx, role_id)
            if not success:
                return
            
            await status_msg.edit(content=f"🛡️ **Lockdown Activated:** Only users with `{level_display}` can talk.")
            
            await self.config.guild(ctx.guild).lockdown_status.set(True)
            await self.config.guild(ctx.guild).lockdown_level.set(level_or_staff)
            
            # Send to staff channel
            staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
            if staff_channel_id:
                staff_channel = ctx.guild.get_channel(staff_channel_id)
                if staff_channel:
                    await staff_channel.send(f"🛡️ **SERVER LOCKDOWN ACTIVATED**\n• Moderator: {ctx.author.mention}\n• Access: {level_display}\n• All other users cannot send messages.")
        
        elif action.lower() == "deactivate":
            status_msg = await ctx.send("🛡️ **Deactivating Lockdown**...")
            
            success = await self.unlock_channels(ctx)
            if not success:
                return
            
            await status_msg.edit(content="❌ **Lockdown Deactivated:** All users can talk again.")
            
            await self.config.guild(ctx.guild).lockdown_status.set(False)
            await self.config.guild(ctx.guild).lockdown_level.set(None)
            
            # Send to staff channel
            staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
            if staff_channel_id:
                staff_channel = ctx.guild.get_channel(staff_channel_id)
                if staff_channel:
                    await staff_channel.send(f"❌ **SERVER LOCKDOWN DEACTIVATED**\n• Moderator: {ctx.author.mention}\n• All users can send messages again.")
        
        elif action.lower() == "status":
            lockdown_status = await self.config.guild(ctx.guild).lockdown_status()
            lockdown_level = await self.config.guild(ctx.guild).lockdown_level()
            
            if lockdown_status:
                level_display = "Staff" if lockdown_level == "staff" else f"Level {lockdown_level}+"
                await ctx.send(f"🛡️ **Lockdown Status:** Active ({level_display})")
            else:
                await ctx.send("❌ **Lockdown Status:** Inactive")
        
        else:
            available_levels = [level.value for level in LockdownLevel]
            await ctx.send(f"Usage: `.shield activate <level>`, `.shield status`, or `.shield deactivate`\nAvailable levels: {', '.join(available_levels)}")

    @commands.cooldown(1, 60, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def cleanup(self, ctx: commands.Context, days: int = 7):
        """Clean up old log entries from the database.
        
        Example: `.cleanup 7` - Remove logs older than 7 days
        """
        if days < 1 or days > 30:
            return await ctx.send("Days must be between 1 and 30.")
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
        
        async with ctx.typing():
            guild_data = await self.config.guild(ctx.guild).log_refs()
            total_removed = 0
            
            for channel_id, logs in guild_data.items():
                original_count = len(logs)
                # Filter out logs older than cutoff
                filtered_logs = [
                    log for log in logs 
                    if log.get("timestamp", "") > cutoff_str
                ]
                
                removed = original_count - len(filtered_logs)
                total_removed += removed
                
                # Update the data
                guild_data[channel_id] = filtered_logs
            
            # Save the cleaned data
            await self.config.guild(ctx.guild).log_refs.set(guild_data)
            
            # Clean memory cache as well
            self.deleted_logs._clean_expired()
        
        await ctx.send(f"🧹 Cleaned up {total_removed} log entries older than {days} days.")

    @commands.command()
    @commands.mod()
    @commands.guild_only()
    async def prunestats(self, ctx: commands.Context):
        """Show statistics about pruning operations."""
        guild_data = await self.config.guild(ctx.guild).log_refs()
        
        total_logs = sum(len(logs) for logs in guild_data.values())
        channels_with_logs = len([ch for ch, logs in guild_data.items() if logs])
        
        # Memory cache stats
        cache_entries = sum(len(entries) for entries in self.deleted_logs.values())
        cache_channels = len(self.deleted_logs)
        
        message = "**Prune Statistics**\n"
        message += f"• Total logged messages: {total_logs}\n"
        message += f"• Channels with logs: {channels_with_logs}\n"
        message += f"• Cache entries: {cache_entries}\n"
        message += f"• Cached channels: {cache_channels}\n"
        
        # Show top channels by log count
        if guild_data:
            sorted_channels = sorted(
                [(ch_id, len(logs)) for ch_id, logs in guild_data.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            message += "\n**Top Channels by Log Count:**\n"
            for ch_id, count in sorted_channels:
                channel = ctx.guild.get_channel(int(ch_id))
                channel_name = channel.mention if channel else f"Unknown (ID: {ch_id})"
                message += f"• {channel_name}: {count} logs\n"
        
        await ctx.send(message)

async def setup(bot: Red):
    cog = Prune(bot)
    await bot.add_cog(cog)
    await cog.initialize()
