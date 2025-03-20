import discord
import aiohttp
import asyncio
import datetime
import time
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box
from typing import Optional, List, Dict, Any, Tuple, Union, Set
from collections import defaultdict, OrderedDict

class TTLCache(OrderedDict):
    """Time-based LRU cache with automatic expiration of items."""
    
    def __init__(self, ttl: int = 86400, max_size: int = 100, *args, **kwargs):
        """Initialize the TTL cache.
        
        Args:
            ttl: Time to live in seconds (default: 24 hours)
            max_size: Maximum number of items in cache (default: 100)
        """
        self.ttl = ttl
        self.max_size = max_size
        super().__init__(*args, **kwargs)
    
    def __setitem__(self, key, value):
        """Set an item with timestamp."""
        # Clean expired entries whenever we add a new item
        self._clean_expired()
        
        # Add the new item with current timestamp
        super().__setitem__(key, {
            'data': value,
            'timestamp': time.time()
        })
        
        # If we exceed max size, remove the oldest entry
        if len(self) > self.max_size:
            self.popitem(last=False)
    
    def __getitem__(self, key):
        """Get an item, return None if expired."""
        item = super().__getitem__(key)
        
        # Check if item has expired
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


class Prune(commands.Cog):
    """A cog for pruning and nuking messages with log uploads to mclo.gs."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1303050205)
        default_guild = {
            "staff_channel": None,
            "staff_role": None,
            "log_refs": {},  # Store log references in the database
            "silenced_role": None,  # Store the silenced role ID
            "level_5_role": None,   # Role ID for Level 5 lockdown
            "level_15_role": None,  # Role ID for Level 15 lockdown
            "lockdown_status": False,  # Is lockdown active
            "lockdown_level": None,  # Current lockdown level
            "allowed_categories": [
                1243536580212166666,  # grand line hq
                1350967803435548712,  # media share
                374126802836258817,   # one piece central
                793834222284570664,   # ohara's library
                802966896155688960,   # vega punk
                1245221633518604359,  # games
                1243539315523326024,  # talent
                705907719466516541    # seas of bluestar
            ],
            "original_permissions": {}  # Store original permissions for restoration
        }
        self.config.register_guild(**default_guild)
        
        # In-memory cache with TTL and size limit
        self.deleted_logs = TTLCache(ttl=86400, max_size=100)  # 24 hour TTL
        
        self.logs_api_url = "https://api.mclo.gs/1/log"
        self.session = None
        
        # Rate limiting protection
        self.deletion_tasks = {}
        self.cooldowns = {}

    async def initialize(self):
        """Initialize the aiohttp session."""
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        """Clean up the aiohttp session on unload."""
        if self.session:
            await self.session.close()
            
        # Cancel any running deletion tasks
        for task in self.deletion_tasks.values():
            if not task.done():
                task.cancel()

    async def upload_to_logs_service(self, content: str, title: str = "Prune logs") -> str:
        """Upload content to mclo.gs and return the URL."""
        # Add a title to the content
        content_with_title = f"# {title}\n\n{content}"
        
        if not self.session:
            await self.initialize()
            
        # Implement retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                data = {'content': content_with_title}
                async with self.session.post(self.logs_api_url, data=data, timeout=10) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if response_data.get('success'):
                            return response_data['url']
                        else:
                            error = response_data.get('error', 'Unknown error')
                            if attempt == max_retries - 1:
                                return f"Upload error: {error}"
                    else:
                        if attempt == max_retries - 1:
                            return f"Failed to upload: {response.status} - {await response.text()}"
            except Exception as e:
                if attempt == max_retries - 1:
                    return f"Error uploading log: {str(e)}"
            
            # Wait before retrying with exponential backoff
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return "Failed to upload log after multiple attempts"

    async def send_to_staff_channel(self, ctx: commands.Context, user: discord.Member, 
                                    channels: List[discord.TextChannel], count: int, 
                                    log_url: str, command_type: str = "Prune"):
        """Send notification to the staff channel if configured."""
        staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        
        if not staff_channel_id:
            return
            
        staff_channel = ctx.guild.get_channel(staff_channel_id)
        if not staff_channel:
            return
            
        # Create a more detailed message for staff
        staff_message = f"**{command_type} Action Log**\n"
        staff_message += f"• Moderator: {ctx.author.mention} ({ctx.author.name})\n"
        staff_message += f"• Target: {user.mention} ({user.name})\n"
        
        if len(channels) == 1:
            staff_message += f"• Channel: {channels[0].mention}\n"
        else:
            staff_message += f"• Channels: {len(channels)} channels\n"
            
        staff_message += f"• Messages Deleted: {count}\n"
        staff_message += f"• Log URL: {log_url}\n"
        
        # Add role mention if configured
        if staff_role_id:
            role = ctx.guild.get_role(staff_role_id)
            if role:
                staff_message = f"{role.mention}\n" + staff_message
        
        await staff_channel.send(staff_message)

    async def store_log(self, guild_id: int, channel_id: int, logs: List[Dict[str, Any]]):
        """Store logs in memory cache and database."""
        cache_key = f"{guild_id}:{channel_id}"
        
        # Store in memory cache
        if cache_key not in self.deleted_logs:
            self.deleted_logs[cache_key] = []
        
        self.deleted_logs[cache_key].extend(logs)
        
        # Store in database
        async with self.config.guild_from_id(guild_id).log_refs() as log_refs:
            channel_key = str(channel_id)
            if channel_key not in log_refs:
                log_refs[channel_key] = []
            
            log_refs[channel_key].extend(logs)
            
            # Keep only the most recent 100 entries
            if len(log_refs[channel_key]) > 100:
                log_refs[channel_key] = log_refs[channel_key][-100:]

    async def delete_messages_in_batches(self, channel: discord.TextChannel, 
                                        messages: List[discord.Message]) -> int:
        """Delete messages in efficient batches respecting Discord's API limits.
        
        Returns the number of successfully deleted messages.
        """
        if not messages:
            return 0
            
        deleted_count = 0
        
        # Sort messages by ID (effectively by timestamp)
        messages.sort(key=lambda m: m.id)
        
        # Separate messages by age (Discord can bulk delete messages < 14 days old)
        two_weeks_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
        
        # Messages newer than 14 days - can use bulk delete
        recent_messages = [msg for msg in messages if msg.created_at > two_weeks_ago]
        
        # Messages older than 14 days - must delete one by one
        old_messages = [msg for msg in messages if msg.created_at <= two_weeks_ago]
        
        # Bulk delete recent messages in batches of 100
        if recent_messages:
            # Split into batches of 100 (Discord's limit)
            batches = [recent_messages[i:i + 100] for i in range(0, len(recent_messages), 100)]
            
            for batch in batches:
                try:
                    await channel.delete_messages(batch)
                    deleted_count += len(batch)
                    
                    # Respect rate limits
                    if len(batches) > 1:
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    # If bulk delete fails, try individual deletion as fallback
                    for msg in batch:
                        try:
                            await msg.delete()
                            deleted_count += 1
                            await asyncio.sleep(0.5)  # Respect rate limits
                        except:
                            pass
        
        # Delete old messages individually
        if old_messages:
            for msg in old_messages:
                try:
                    await msg.delete()
                    deleted_count += 1
                    
                    # Add delay to respect rate limits
                    await asyncio.sleep(0.5)
                except:
                    pass
                    
        return deleted_count

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
        - `.prune @user 10` - Delete the last 10 messages from a specific user
        - `.prune @user 20 #channel` - Delete the last 20 messages from a user in a specific channel
        - `.prune @user 15 #channel keyword` - Delete messages containing the keyword
        """
        # If first parameter is a number, it's a simple purge
        if isinstance(amount_or_user, int):
            await self.simple_purge(ctx, amount_or_user)
        
        # If first parameter is a user, it's a targeted prune
        elif isinstance(amount_or_user, discord.Member):
            # If amount wasn't provided after the user, show error
            if amount_if_user is None:
                await ctx.send("Please specify the number of messages to delete.\nUsage: `.prune @user 10`")
                return
                
            await self.targeted_prune(ctx, amount_or_user, amount_if_user, channel, keyword)
        
        else:
            await ctx.send("Invalid parameters. Use `.prune 15` or `.prune @user 10`.")

    async def simple_purge(self, ctx: commands.Context, amount: int):
        """Delete a specific number of recent messages in a channel."""
        if amount <= 0:
            return await ctx.send("Amount must be a positive number.")
            
        if amount > 100:
            return await ctx.send("For safety reasons, you can only delete up to 100 messages at once with this command.")
            
        # Show a typing indicator during potentially lengthy operation
        async with ctx.typing():
            # Skip the command message itself
            messages_to_delete = []
            
            # Collect messages first
            async for message in ctx.channel.history(limit=amount+1):  # +1 to include command message
                if message.id != ctx.message.id:  # Skip the command message
                    messages_to_delete.append(message)
                    if len(messages_to_delete) >= amount:
                        break
                        
            if not messages_to_delete:
                return await ctx.send("No messages found to delete.")
                
            # Format for log upload
            formatted_logs = "\n".join([
                f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}" 
                for msg in messages_to_delete
            ])
            
            # Upload to mclo.gs
            log_title = f"Channel Purge - {ctx.channel.name}"
            log_url = await self.upload_to_logs_service(formatted_logs, log_title)
            
            # Delete messages efficiently
            deleted_count = await self.delete_messages_in_batches(ctx.channel, messages_to_delete)
            
            # Store logs by moderator instead of by author
            log_entries = [
                {
                    "user_id": msg.author.id, 
                    "user": msg.author.name, 
                    "content": msg.content, 
                    "timestamp": msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                } 
                for msg in messages_to_delete
            ]
            
            await self.store_log(ctx.guild.id, ctx.channel.id, log_entries)
            
        # Confirm deletion to user
        success_msg = await ctx.send(f"Deleted {deleted_count} messages.")
        
        # Send to staff channel if configured
        staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        
        if staff_channel_id:
            staff_channel = ctx.guild.get_channel(staff_channel_id)
            if staff_channel:
                # Create a more detailed message for staff
                staff_message = f"**Bulk Purge Log**\n"
                staff_message += f"• Moderator: {ctx.author.mention} ({ctx.author.name})\n"
                staff_message += f"• Channel: {ctx.channel.mention}\n"
                staff_message += f"• Messages Deleted: {deleted_count}\n"
                staff_message += f"• Log URL: {log_url}\n"
                
                # Add role mention if configured
                if staff_role_id:
                    role = ctx.guild.get_role(staff_role_id)
                    if role:
                        staff_message = f"{role.mention}\n" + staff_message
                
                await staff_channel.send(staff_message)
                
        # Auto-delete the success message after 5 seconds
        await asyncio.sleep(5)
        try:
            await success_msg.delete()
        except:
            pass

    async def targeted_prune(self, ctx: commands.Context, user: discord.Member, amount: int, 
                           channel: Optional[discord.TextChannel] = None, keyword: Optional[str] = None):
        """Delete the last <amount> messages from <user> in a specific channel."""
        if amount <= 0:
            return await ctx.send("Amount must be a positive number.")

        # Use current channel if none specified
        if not channel:
            channel = ctx.channel
            
        # Show a typing indicator during potentially lengthy operation
        async with ctx.typing():
            # Define check function to filter messages
            def check(msg):
                if msg.id == ctx.message.id:
                    return False
                if msg.author.id != user.id:
                    return False
                if keyword and keyword.lower() not in msg.content.lower():
                    return False
                return True

            # Collect messages first without deleting
            messages_to_delete = []
            
            # Use a reasonable search limit based on the amount requested
            search_limit = min(500, amount * 3)
            
            async for message in channel.history(limit=search_limit):
                if check(message):
                    messages_to_delete.append(message)
                    if len(messages_to_delete) >= amount:
                        break
            
            if not messages_to_delete:
                return await ctx.send(f"No messages from {user.mention} found matching the criteria.")

            # Store logs before deletion
            log_entries = [
                {
                    "user_id": msg.author.id, 
                    "user": msg.author.name, 
                    "content": msg.content, 
                    "timestamp": msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                } 
                for msg in messages_to_delete
            ]
            
            await self.store_log(ctx.guild.id, channel.id, log_entries)
            
            # Format for log upload
            formatted_logs = "\n".join([
                f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}" 
                for msg in messages_to_delete
            ])
            
            # Upload to mclo.gs
            log_title = f"Prune {user.name} logs"
            log_url = await self.upload_to_logs_service(formatted_logs, log_title)
            
            # Delete messages efficiently
            deleted_count = await self.delete_messages_in_batches(channel, messages_to_delete)

        # Confirm deletion to user
        await ctx.send(f"Deleted {deleted_count} messages from {user.mention} in {channel.mention}.")
        
        # Send to staff channel if configured
        await self.send_to_staff_channel(ctx, user, [channel], deleted_count, log_url)

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def prunelogs(self, ctx: commands.Context, user: discord.Member, 
                        limit: Optional[int] = 20, channel: Optional[discord.TextChannel] = None):
        """Retrieve pruned messages for a user."""
        if limit > 100:
            return await ctx.send("Limit cannot exceed 100 messages.")

        if not channel:
            channel = ctx.channel

        guild_id = ctx.guild.id
        channel_id = channel.id
        cache_key = f"{guild_id}:{channel_id}"
        
        # Try to get logs from memory cache first
        logs = self.deleted_logs.get(cache_key, [])
        
        # If not found in cache, check database
        if not logs:
            guild_data = await self.config.guild(ctx.guild).log_refs()
            logs = guild_data.get(str(channel_id), [])
        
        if not logs:
            return await ctx.send(f"No pruned messages logged for {channel.mention}.")

        # Filter by user
        logs = [log for log in logs if log.get("user_id") == user.id]

        if not logs:
            return await ctx.send(f"No logs found for {user.mention} in {channel.mention}.")

        # Sort by timestamp and limit results
        logs = sorted(logs, key=lambda log: log.get("timestamp", ""), reverse=True)[:limit]
        
        formatted_logs = "\n".join([
            f"[{log.get('timestamp', 'Unknown')}] {log.get('user', 'Unknown')}: {log.get('content', 'No content')}" 
            for log in logs
        ])

        await ctx.send(box(formatted_logs, lang="yaml"))

    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def nuke(self, ctx: commands.Context, user: discord.Member):
        """Delete all messages from a user across all guild channels and assign the Silenced role."""
        # Show a typing indicator during this lengthy operation
        async with ctx.typing():
            # Get all text channels in the guild where bot has permissions
            text_channels = [
                channel for channel in ctx.guild.text_channels 
                if channel.permissions_for(ctx.guild.me).manage_messages
            ]
            
            if not text_channels:
                return await ctx.send("I don't have permission to manage messages in any channels.")
                
            # Send initial status message
            status_msg = await ctx.send(f"Nuking messages from {user.mention} in {len(text_channels)} channels...")
            
            # Track overall stats
            total_deleted = 0
            all_messages = []
            affected_channels = []
            
            # Process channels concurrently in chunks to avoid overloading
            for i in range(0, len(text_channels), 5):  # Process 5 channels at once
                channel_chunk = text_channels[i:i+5]
                
                # Update status every 5 channels
                await status_msg.edit(content=f"Scanning channels... ({i}/{len(text_channels)})")
                
                # Process each channel in the chunk
                for channel in channel_chunk:
                    try:
                        # Collect messages to delete
                        messages_to_delete = []
                        
                        # Track if we found any messages in this channel
                        found_in_channel = False
                        
                        # Process in batches of 100 to avoid timeouts
                        while True:
                            batch = []
                            async for msg in channel.history(limit=100):
                                if msg.author.id == user.id:
                                    batch.append(msg)
                                    all_messages.append(msg)
                            
                            if not batch:
                                break
                                
                            found_in_channel = True
                            messages_to_delete.extend(batch)
                            
                            # Delete this batch
                            deleted = await self.delete_messages_in_batches(channel, batch)
                            total_deleted += deleted
                            
                            # If we got less than 100, we've reached the end
                            if len(batch) < 100:
                                break
                                
                        if found_in_channel:
                            affected_channels.append(channel)
                            
                    except Exception as e:
                        continue
                
                # Brief pause between chunks to avoid rate limits
                await asyncio.sleep(1)
            
            # If we found messages, create a log
            if all_messages:
                # Sort messages by timestamp
                all_messages.sort(key=lambda msg: msg.created_at)
                
                # Format for log upload
                formatted_logs = []
                for msg in all_messages:
                    channel_name = msg.channel.name
                    formatted_logs.append(
                        f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] #{channel_name}: {msg.content}"
                    )
                
                # Handle mclo.gs limits
                if len(formatted_logs) > 25000:
                    formatted_logs = formatted_logs[:25000]
                    await ctx.send("⚠️ More than 25,000 messages found. Only the first 25,000 will be logged.")
                    
                log_content = "\n".join(formatted_logs)
                
                # Upload to mclo.gs
                log_title = f"Nuke {user.name} logs"
                log_url = await self.upload_to_logs_service(log_content, log_title)
                
                # Store log references in each affected channel
                for channel in affected_channels:
                    channel_messages = [msg for msg in all_messages if msg.channel.id == channel.id]
                    log_entries = [
                        {
                            "user_id": msg.author.id, 
                            "user": msg.author.name, 
                            "content": msg.content, 
                            "timestamp": msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                        } 
                        for msg in channel_messages
                    ]
                    await self.store_log(ctx.guild.id, channel.id, log_entries)
                
                # Send to staff channel if configured
                await self.send_to_staff_channel(ctx, user, affected_channels, total_deleted, log_url, "Nuke")
            
            # Get or create silenced role
            silenced_role_id = await self.config.guild(ctx.guild).silenced_role()
            silenced_role = None
            
            if silenced_role_id:
                silenced_role = ctx.guild.get_role(silenced_role_id)
                
            if not silenced_role:
                # Try to find by name
                silenced_role = discord.utils.get(ctx.guild.roles, name="Silenced")
                
                if not silenced_role:
                    await status_msg.edit(content="❌ The `Silenced` role does not exist. Please create it manually.")
                    return
                
                # Store for future use
                await self.config.guild(ctx.guild).silenced_role.set(silenced_role.id)
            
            # Assign silenced role
            try:
                await user.add_roles(silenced_role)
                await status_msg.edit(content=f"🚨 Nuked **{total_deleted}** messages from {user.mention} across {len(affected_channels)} channels and assigned the `Silenced` role.")
            except discord.Forbidden:
                await status_msg.edit(content=f"🚨 Nuked **{total_deleted}** messages from {user.mention} across {len(affected_channels)} channels, but I don't have permission to assign the `Silenced` role.")

    @commands.mod()
    @commands.guild_only()
    @commands.group()
    async def pruneset(self, ctx: commands.Context):
        """Configure the prune cog settings."""
        pass

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

    @pruneset.command(name="level5role")
    async def set_level5_role(self, ctx: commands.Context, role: discord.Role = None):
        """Set the Level 5 role for the shield command."""
        if role:
            await self.config.guild(ctx.guild).level_5_role.set(role.id)
            await ctx.send(f"Level 5 role set to {role.mention}.")
        else:
            await self.config.guild(ctx.guild).level_5_role.set(None)
            await ctx.send("Level 5 role configuration removed.")

    @pruneset.command(name="level15role")
    async def set_level15_role(self, ctx: commands.Context, role: discord.Role = None):
        """Set the Level 15 role for the shield command."""
        if role:
            await self.config.guild(ctx.guild).level_15_role.set(role.id)
            await ctx.send(f"Level 15 role set to {role.mention}.")
        else:
            await self.config.guild(ctx.guild).level_15_role.set(None)
            await ctx.send("Level 15 role configuration removed.")

    @pruneset.command(name="categories")
    async def set_lockdown_categories(self, ctx: commands.Context, *category_ids: int):
        """Set which category IDs are affected by the shield command.
        
        Example: .pruneset categories 123456789 987654321
        Leave empty to reset to default list.
        """
        if not category_ids:
            # Reset to defaults
            default_categories = [
                1243536580212166666,  # grand line hq
                1350967803435548712,  # media share
                374126802836258817,   # one piece central
                793834222284570664,   # ohara's library
                802966896155688960,   # vega punk
                1245221633518604359,  # games
                1243539315523326024,  # talent
                705907719466516541    # seas of bluestar
            ]
            await self.config.guild(ctx.guild).allowed_categories.set(default_categories)
            
            # Format category names for display
            category_list = "\n".join([f"• {ctx.guild.get_channel(cat_id).name if ctx.guild.get_channel(cat_id) else f'Unknown ({cat_id})'}" 
                                     for cat_id in default_categories])
            
            await ctx.send(f"Reset to default category list:\n{category_list}")
            return
            
        # Validate that these are actual category IDs
        valid_ids = []
        invalid_ids = []
        for cat_id in category_ids:
            channel = ctx.guild.get_channel(cat_id)
            if channel and isinstance(channel, discord.CategoryChannel):
                valid_ids.append(cat_id)
            else:
                invalid_ids.append(cat_id)
        
        if invalid_ids:
            await ctx.send(f"⚠️ Warning: {len(invalid_ids)} IDs are not valid categories: {', '.join(str(i) for i in invalid_ids)}")
        
        if not valid_ids:
            await ctx.send("❌ No valid category IDs provided. Shield settings unchanged.")
            return
            
        # Save the valid category IDs
        await self.config.guild(ctx.guild).allowed_categories.set(valid_ids)
        
        # Format category names for display
        category_list = "\n".join([f"• {ctx.guild.get_channel(cat_id).name}" for cat_id in valid_ids])
        
        await ctx.send(f"Shield will now only affect these categories:\n{category_list}")

    @pruneset.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Show current prune settings."""
        staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        silenced_role_id = await self.config.guild(ctx.guild).silenced_role()
        level_5_role_id = await self.config.guild(ctx.guild).level_5_role()
        level_15_role_id = await self.config.guild(ctx.guild).level_15_role()
        lockdown_status = await self.config.guild(ctx.guild).lockdown_status()
        allowed_categories = await self.config.guild(ctx.guild).allowed_categories()
        
        staff_channel = ctx.guild.get_channel(staff_channel_id) if staff_channel_id else None
        staff_role = ctx.guild.get_role(staff_role_id) if staff_role_id else None
        silenced_role = ctx.guild.get_role(silenced_role_id) if silenced_role_id else None
        level_5_role = ctx.guild.get_role(level_5_role_id) if level_5_role_id else None
        level_15_role = ctx.guild.get_role(level_15_role_id) if level_15_role_id else None
        
        message = "**Current Prune Settings**\n"
        message += f"• Staff Channel: {staff_channel.mention if staff_channel else 'Not set'}\n"
        message += f"• Staff Role: {staff_role.mention if staff_role else 'Not set'}\n"
        message += f"• Silenced Role: {silenced_role.mention if silenced_role else 'Not set'}\n"
        message += f"• Level 5 Role: {level_5_role.mention if level_5_role else 'Not set'}\n"
        message += f"• Level 15 Role: {level_15_role.mention if level_15_role else 'Not set'}\n"
        message += f"• Lockdown Status: {'Active' if lockdown_status else 'Inactive'}\n"
        message += f"• Protected Categories: {len(allowed_categories)}"
        
        await ctx.send(message)
        
        # If there are too many categories to list in one message, show them in a separate message
        if allowed_categories:
            category_list = ""
            for cat_id in allowed_categories:
                cat = ctx.guild.get_channel(cat_id)
                if cat:
                    category_list += f"• {cat.name} (ID: {cat.id})\n"
                else:
                    category_list += f"• Unknown Category (ID: {cat_id})\n"
                    
            await ctx.send(f"**Protected Categories:**\n{category_list}")

    async def store_original_permissions(self, guild_id: int, category_id: int, default_role_id: int, permissions):
        """Store original permissions for a category to be restored later."""
        async with self.config.guild_from_id(guild_id).original_permissions() as perms:
            # Create a key combining category and role IDs
            key = f"{category_id}:{default_role_id}"
            
            # Store the permissions
            perms[key] = {
                "send_messages": permissions.send_messages
            }

    async def get_original_permissions(self, guild_id: int, category_id: int, default_role_id: int):
        """Get original permissions for a category."""
        perms = await self.config.guild_from_id(guild_id).original_permissions()
        key = f"{category_id}:{default_role_id}"
        
        if key in perms:
            return perms[key]
        return None

    async def lock_categories(self, ctx: commands.Context, role_id: int):
        """Lock specific categories for everyone except the specified role."""
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("❌ The required role does not exist. Please check the role IDs or configure them with `pruneset`.")
            return False

        # Get the allowed categories
        allowed_category_ids = await self.config.guild(ctx.guild).allowed_categories()
        
        # Filter to get only valid category channels
        valid_categories = []
        for cat_id in allowed_category_ids:
            cat = ctx.guild.get_channel(cat_id)
            if cat and isinstance(cat, discord.CategoryChannel):
                valid_categories.append(cat)
        
        if not valid_categories:
            await ctx.send("❌ No valid categories found to lock. Please check category IDs.")
            return False

        # Use a typing indicator during this potentially lengthy operation
        async with ctx.typing():
            # First, update progress message
            status_msg = await ctx.send(f"🔒 Locking {len(valid_categories)} categories and syncing their channels...")
            
            # Process categories in parallel for better performance
            tasks = []
            for category in valid_categories:
                # Store original permissions before modifying
                overwrites = category.overwrites_for(ctx.guild.default_role)
                await self.store_original_permissions(
                    ctx.guild.id, 
                    category.id, 
                    ctx.guild.default_role.id,
                    overwrites
                )
                
                # Lock the category
                task = self.lock_single_category(category, ctx.guild.default_role, role)
                tasks.append(task)
            
            # Wait for all category updates to complete
            await asyncio.gather(*tasks)
                
            # Final success message with count of affected categories
            await status_msg.edit(content=f"✅ {len(valid_categories)} categories and their channels locked successfully!")
            
        return True

    async def lock_single_category(self, category: discord.CategoryChannel, default_role: discord.Role, allowed_role: discord.Role):
        """Lock a single category and ensure channels inherit the settings."""
        try:
            # Update permissions for the default role at category level
            overwrites = category.overwrites_for(default_role)
            overwrites.send_messages = False
            await category.set_permissions(default_role, overwrite=overwrites)
            
            # Update permissions for the allowed role at category level
            overwrites = category.overwrites_for(allowed_role)
            overwrites.send_messages = True
            await category.set_permissions(allowed_role, overwrite=overwrites)
            
            # Make sure all channels in this category have sync permissions enabled
            for channel in category.channels:
                if isinstance(channel, discord.TextChannel):
                    # If the channel doesn't have synced permissions, sync them
                    if not channel.permissions_synced:
                        await channel.edit(sync_permissions=True)
                        
        except Exception as e:
            # Continue even if one category fails
            pass

    async def lock_single_channel(self, channel: discord.TextChannel, default_role: discord.Role, allowed_role: discord.Role):
        """Lock a single text channel that's not in a category."""
        try:
            # Update permissions for the default role
            overwrites = channel.overwrites_for(default_role)
            overwrites.send_messages = False
            await channel.set_permissions(default_role, overwrite=overwrites)
            
            # Update permissions for the allowed role
            overwrites = channel.overwrites_for(allowed_role)
            overwrites.send_messages = True
            await channel.set_permissions(allowed_role, overwrite=overwrites)
        except Exception as e:
            # Continue even if one channel fails
            pass

    async def unlock_categories(self, ctx: commands.Context):
        """Unlock specific categories by restoring original permissions."""
        # Get the allowed categories
        allowed_category_ids = await self.config.guild(ctx.guild).allowed_categories()
        
        # Get saved permissions
        original_permissions = await self.config.guild(ctx.guild).original_permissions()
        
        # Filter to get only valid category channels
        valid_categories = []
        for cat_id in allowed_category_ids:
            cat = ctx.guild.get_channel(cat_id)
            if cat and isinstance(cat, discord.CategoryChannel):
                valid_categories.append(cat)
        
        if not valid_categories:
            await ctx.send("❌ No valid categories found to unlock. Please check category IDs.")
            return False

        # Use a typing indicator during this potentially lengthy operation
        async with ctx.typing():
            # First, update progress message
            status_msg = await ctx.send(f"🔓 Unlocking {len(valid_categories)} categories and restoring original permissions...")
            
            # Process categories in parallel
            tasks = []
            for category in valid_categories:
                # Get the original permissions
                key = f"{category.id}:{ctx.guild.default_role.id}"
                original_perms = original_permissions.get(key, None)
                
                # If we have original permissions, restore them
                if original_perms:
                    task = self.restore_category_permissions(category, ctx.guild.default_role, original_perms)
                else:
                    # Otherwise just reset to None (default)
                    task = self.unlock_single_category(category, ctx.guild.default_role)
                
                tasks.append(task)
            
            # Wait for all category updates to complete
            await asyncio.gather(*tasks)
                
            # Clear stored permissions
            await self.config.guild(ctx.guild).original_permissions.set({})
            
            # Final success message
            await status_msg.edit(content=f"✅ {len(valid_categories)} categories and their channels unlocked successfully!")
        
        return True

    async def restore_category_permissions(self, category: discord.CategoryChannel, default_role: discord.Role, original_perms: dict):
        """Restore original permissions for a category."""
        try:
            # Get current overwrites
            overwrites = category.overwrites_for(default_role)
            
            # Restore original send_messages permission
            if "send_messages" in original_perms:
                overwrites.send_messages = original_perms["send_messages"]
            else:
                overwrites.send_messages = None
                
            # Apply the restored permissions
            await category.set_permissions(default_role, overwrite=overwrites)
            
            # Make sure all channels in this category have sync permissions enabled
            for channel in category.channels:
                if isinstance(channel, discord.TextChannel):
                    # If the channel doesn't have synced permissions, sync them
                    if not channel.permissions_synced:
                        await channel.edit(sync_permissions=True)
        except Exception as e:
            # Continue even if one category fails
            pass

    async def unlock_single_category(self, category: discord.CategoryChannel, default_role: discord.Role):
        """Unlock a single category and ensure channels inherit the settings."""
        try:
            # Reset permissions for the default role
            overwrites = category.overwrites_for(default_role)
            overwrites.send_messages = None  # Reset to default
            await category.set_permissions(default_role, overwrite=overwrites)
            
            # Make sure all channels in this category have sync permissions enabled
            for channel in category.channels:
                if isinstance(channel, discord.TextChannel):
                    # If the channel doesn't have synced permissions, sync them
                    if not channel.permissions_synced:
                        await channel.edit(sync_permissions=True)
        except Exception as e:
            # Continue even if one category fails
            pass

    async def unlock_single_channel(self, channel: discord.TextChannel, default_role: discord.Role):
        """Unlock a single text channel that's not in a category."""
        try:
            # Reset permissions for the default role
            overwrites = channel.overwrites_for(default_role)
            overwrites.send_messages = None  # Reset to default
            await channel.set_permissions(default_role, overwrite=overwrites)
        except Exception as e:
            # Continue even if one channel fails
            pass

    @commands.cooldown(1, 15, commands.BucketType.guild)
    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def shield(self, ctx: commands.Context, action: str, level: Optional[int] = None):
        """
        Activate or deactivate server lockdown mode.
        
        Examples:
        - `.shield activate 5` - Only Level 5+ users can talk
        - `.shield activate 15` - Only Level 15+ users can talk
        - `.shield deactivate` - End lockdown mode
        """
        if action.lower() == "activate" and level in [5, 15]:
            # Get the appropriate role
            role_id = None
            if level == 5:
                role_id = await self.config.guild(ctx.guild).level_5_role()
                if not role_id:
                    await ctx.send("❌ Level 5 role not configured. Use `pruneset level5role` to set it.")
                    return
            else:  # level == 15
                role_id = await self.config.guild(ctx.guild).level_15_role()
                if not role_id:
                    await ctx.send("❌ Level 15 role not configured. Use `pruneset level15role` to set it.")
                    return
            
            # Initial message
            status_msg = await ctx.send(f"🛡️ **Activating Lockdown:** Only users with `Level {level}+` can talk.")
            
            # Lock the server
            success = await self.lock_categories(ctx, role_id)
            if not success:
                return
            
            # Update status
            await status_msg.edit(content=f"🛡️ **Lockdown Activated:** Only users with `Level {level}+` can talk.")
            
            # Store lockdown state
            await self.config.guild(ctx.guild).lockdown_status.set(True)
            await self.config.guild(ctx.guild).lockdown_level.set(level)
            
            # Send to staff channel if configured
            staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
            if staff_channel_id:
                staff_channel = ctx.guild.get_channel(staff_channel_id)
                if staff_channel:
                    await staff_channel.send(f"🛡️ **SERVER LOCKDOWN ACTIVATED**\n• Moderator: {ctx.author.mention}\n• Level: {level}+\n• All other users cannot send messages.")
        
        elif action.lower() == "deactivate":
            # Initial message
            status_msg = await ctx.send("🛡️ **Deactivating Lockdown**...")
            
            # Unlock the server
            success = await self.unlock_categories(ctx)
            if not success:
                return
            
            # Update status
            await status_msg.edit(content="❌ **Lockdown Deactivated:** All users can talk again.")
            
            # Store lockdown state
            await self.config.guild(ctx.guild).lockdown_status.set(False)
            await self.config.guild(ctx.guild).lockdown_level.set(None)
            
            # Send to staff channel if configured
            staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
            if staff_channel_id:
                staff_channel = ctx.guild.get_channel(staff_channel_id)
                if staff_channel:
                    await staff_channel.send(f"❌ **SERVER LOCKDOWN DEACTIVATED**\n• Moderator: {ctx.author.mention}\n• All users can send messages again.")
        
        elif action.lower() == "status":
            # Check current lockdown status
            lockdown_status = await self.config.guild(ctx.guild).lockdown_status()
            lockdown_level = await self.config.guild(ctx.guild).lockdown_level()
            
            if lockdown_status:
                await ctx.send(f"🛡️ **Lockdown Status:** Active (Level {lockdown_level}+)")
            else:
                await ctx.send("❌ **Lockdown Status:** Inactive")
        
        else:
            await ctx.send("Usage: `.shield activate 5`, `.shield activate 15`, `.shield status`, or `.shield deactivate`")

async def setup(bot: Red):
    cog = Prune(bot)
    await bot.add_cog(cog)
    await cog.initialize()
