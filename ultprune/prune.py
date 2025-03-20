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
            "protected_channels": [
                # Protected from lockdowns - Public Info Channels
                708651385729712168,  # #polls
                1343122472790261851, # #0-players-online
                804926342780813312,  # #starboard
                1287263954099240960, # #art-competition
                1336392905568555070, # #launch-test-do-not-enter
                802966392294080522,  # #sports
                793834515213582367,  # #movies-tv-series
                1228063343198208080, # #op-anime-only
                597837630872485911,  # #announcements
                590972222366023718,  # #rules-and-info
                655589140573847582,  # one-piece-updates
                597528644432166948,  # #roles
                374144563482198026,  # #flyingpandatv-content
                1312008589061132288, # #server-partners
                1158862350288421025, # welcome
                1342941591236640800, # opc-calendar
                791251876871143424,  # game-news
                688318774608265405,  # #news
                
                # World Govt (Staff Channels)
                1245278358212841513, # staff-guidelines
                374144169200975873,  # staff-announcements
                446381338195394592,  # staff-chat
                657042293181644830,  # room-of-authority
                1287233798542458890, # events-channel
                1345122677328707784, # mc-staff
                647895768715493437,  # test
                748451591958429809,  # ults
                1328272555731062828, # staffapps
                
                # Logs Channels
                1245208777003634698, # ❗important-logs❗
                797243926871277638,  # extendedlogs
                663108140484657192,  # logs
                802978426045726730,  # silenced
                706497312154714172,  # 🔐-modlogs
                1345059334501040139, # mc-logs
                
                # Miscellaneous Staff
                644733907446792212,  # custom-commands
                782600064370475060,  # discord-announcement
                
                # 10K Members Event
                1302456376613671012, # 10k-member-event-🥳
                
                # Impel Down
                1240104130454880316, # defender
                1253856373381533806, # testnotify
                
                # Server Info
                794882627953885234,  # elz-work-log
                688324357378015252,  # server-info
                688324397492207627,  # level-up-guide
                688324320053035023,  # stats
                793772405511684107,  # casino
                801779804197355520   # economy
            ],
            "channel_permissions": {}  # Store permissions for channels
        }
        self.config.register_guild(**default_guild)
        
        # Rest of initialization remains the same
        self.deleted_logs = TTLCache(ttl=86400, max_size=100)  # 24 hour TTL
        self.logs_api_url = "https://api.mclo.gs/1/log"
        self.session = None
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

    @pruneset.command(name="protectedchannels")
    async def set_protected_channels(self, ctx: commands.Context, *channel_ids: int):
        """Set which channel IDs should be protected from lockdowns.
        
        Example: .pruneset protectedchannels 123456789 987654321
        Leave empty to reset to default list.
        """
        if not channel_ids:
            # Reset to defaults
            default_channels = [
                # Protected from lockdowns - Public Info Channels
                708651385729712168,  # #polls
                1343122472790261851, # #0-players-online
                804926342780813312,  # #starboard
                1287263954099240960, # #art-competition
                1336392905568555070, # #launch-test-do-not-enter
                802966392294080522,  # #sports
                793834515213582367,  # #movies-tv-series
                1228063343198208080, # #op-anime-only
                597837630872485911,  # #announcements
                590972222366023718,  # #rules-and-info
                655589140573847582,  # one-piece-updates
                597528644432166948,  # #roles
                374144563482198026,  # #flyingpandatv-content
                1312008589061132288, # #server-partners
                1158862350288421025, # welcome
                1342941591236640800, # opc-calendar
                791251876871143424,  # game-news
                688318774608265405,  # #news
                
                # World Govt (Staff Channels)
                1245278358212841513, # staff-guidelines
                374144169200975873,  # staff-announcements
                446381338195394592,  # staff-chat
                657042293181644830,  # room-of-authority
                1287233798542458890, # events-channel
                1345122677328707784, # mc-staff
                647895768715493437,  # test
                748451591958429809,  # ults
                1328272555731062828, # staffapps
                
                # Logs Channels
                1245208777003634698, # ❗important-logs❗
                797243926871277638,  # extendedlogs
                663108140484657192,  # logs
                802978426045726730,  # silenced
                706497312154714172,  # 🔐-modlogs
                1345059334501040139, # mc-logs
                
                # Miscellaneous Staff
                644733907446792212,  # custom-commands
                782600064370475060,  # discord-announcement
                
                # 10K Members Event
                1302456376613671012, # 10k-member-event-🥳
                
                # Impel Down
                1240104130454880316, # defender
                1253856373381533806, # testnotify
                
                # Server Info
                794882627953885234,  # elz-work-log
                688324357378015252,  # server-info
                688324397492207627,  # level-up-guide
                688324320053035023,  # stats
                793772405511684107,  # casino
                801779804197355520   # economy
            ]
            await self.config.guild(ctx.guild).protected_channels.set(default_channels)
            
            # Show a summary instead of listing all channels
            await ctx.send(f"✅ Reset to default protected channels list with {len(default_channels)} channels.")
            await ctx.send("The list includes essential info channels, staff channels, logs, and server info channels.")
            
            # Ask if they want to see the full list
            confirm_msg = await ctx.send("Would you like to see the complete list of protected channels? (yes/no)")
            
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no", "y", "n"]
            
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=30.0)
                if msg.content.lower() in ["yes", "y"]:
                    # Format channel names for display in chunks to avoid message size limits
                    chunks = []
                    current_chunk = "**Protected Channels:**\n"
                    
                    for ch_id in default_channels:
                        ch = ctx.guild.get_channel(ch_id)
                        channel_text = f"• {ch.mention if ch else f'Unknown Channel (ID: {ch_id})'}\n"
                        
                        # Check if adding this would exceed Discord's message limit
                        if len(current_chunk) + len(channel_text) > 1900:
                            chunks.append(current_chunk)
                            current_chunk = "**Protected Channels (continued):**\n"
                        
                        current_chunk += channel_text
                    
                    if current_chunk:
                        chunks.append(current_chunk)
                        
                    # Send each chunk as a separate message
                    for chunk in chunks:
                        await ctx.send(chunk)
            except asyncio.TimeoutError:
                await confirm_msg.edit(content="Timed out. You can view settings with `pruneset settings`.")
            
            return
            
        # Rest of the code for custom channel IDs remains the same
        # Validate that these are actual channel IDs
        valid_ids = []
        invalid_ids = []
        for ch_id in channel_ids:
            channel = ctx.guild.get_channel(ch_id)
            if channel and isinstance(channel, discord.TextChannel):
                valid_ids.append(ch_id)
            else:
                invalid_ids.append(ch_id)
        
        if invalid_ids:
            await ctx.send(f"⚠️ Warning: {len(invalid_ids)} IDs are not valid text channels: {', '.join(str(i) for i in invalid_ids)}")
        
        if not valid_ids:
            await ctx.send("❌ No valid channel IDs provided. Protected channels settings unchanged.")
            return
            
        # Save the valid channel IDs
        await self.config.guild(ctx.guild).protected_channels.set(valid_ids)
        
        # Format channel names for display
        channel_list = "\n".join([f"• {ctx.guild.get_channel(ch_id).mention}" for ch_id in valid_ids])
        
        await ctx.send(f"These channels will now be protected from lockdowns:\n{channel_list}")

    @pruneset.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Show current prune settings."""
        staff_channel_id = await self.config.guild(ctx.guild).staff_channel()
        staff_role_id = await self.config.guild(ctx.guild).staff_role()
        silenced_role_id = await self.config.guild(ctx.guild).silenced_role()
        level_5_role_id = await self.config.guild(ctx.guild).level_5_role()
        level_15_role_id = await self.config.guild(ctx.guild).level_15_role()
        lockdown_status = await self.config.guild(ctx.guild).lockdown_status()
        protected_channels = await self.config.guild(ctx.guild).protected_channels()
        
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
        message += f"• Protected Channels: {len(protected_channels)}"
        
        await ctx.send(message)
            
        # If there are protected channels to list, show them in chunks to avoid message size limits
        if protected_channels:
            chunks = []
            current_chunk = "**Protected Channels:**\n"
            
            for ch_id in protected_channels:
                ch = ctx.guild.get_channel(ch_id)
                channel_text = f"• {ch.mention if ch else f'Unknown Channel (ID: {ch_id})'}\n"
                
                # Check if adding this would exceed Discord's message limit
                if len(current_chunk) + len(channel_text) > 1900:
                    chunks.append(current_chunk)
                    current_chunk = "**Protected Channels (continued):**\n"
                
                current_chunk += channel_text
            
            if current_chunk:
                chunks.append(current_chunk)
                
            # Send each chunk as a separate message
            for chunk in chunks:
                await ctx.send(chunk)

    async def lock_channels(self, ctx: commands.Context, role_id: int):
        """Lock all text channels except protected ones."""
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("❌ The required role does not exist. Please check the role IDs or configure them with `pruneset`.")
            return False

        # Get the protected channels list
        protected_channel_ids = await self.config.guild(ctx.guild).protected_channels()
        
        # Get all text channels that aren't protected
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
        
        # Use a typing indicator during this potentially lengthy operation
        async with ctx.typing():
            # Initial status message
            status_msg = await ctx.send(f"🔒 Locking channels... (0/{total_channels})")
            
            # Process channels in chunks for better performance
            chunk_size = 5
            for i in range(0, len(channels_to_lock), chunk_size):
                chunk = channels_to_lock[i:i+chunk_size]
                
                # Process this chunk of channels concurrently
                tasks = []
                for channel in chunk:
                    task = self.lock_single_channel(channel, ctx.guild.default_role, role)
                    tasks.append(task)
                
                # Wait for all tasks in this chunk to complete
                await asyncio.gather(*tasks)
                
                # Update progress counter
                processed += len(chunk)
                await status_msg.edit(content=f"🔒 Locking channels... ({processed}/{total_channels})")
                
                # Brief pause to avoid rate limits
                if i + chunk_size < len(channels_to_lock):
                    await asyncio.sleep(1)
                
            # Final success message
            await status_msg.edit(content=f"✅ Lockdown complete! {processed} channels locked successfully.")
            
        return True
    
    async def lock_single_channel(self, channel: discord.TextChannel, default_role: discord.Role, allowed_role: discord.Role):
        """Lock a single text channel."""
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
            
    async def unlock_channels(self, ctx: commands.Context):
        """Unlock all text channels except protected ones."""
        # Get the protected channels list
        protected_channel_ids = await self.config.guild(ctx.guild).protected_channels()
        
        # Get all text channels that aren't protected
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
        
        # Use a typing indicator during this potentially lengthy operation
        async with ctx.typing():
            # Initial status message
            status_msg = await ctx.send(f"🔓 Unlocking channels... (0/{total_channels})")
            
            # Process channels in chunks for better performance
            chunk_size = 5
            for i in range(0, len(channels_to_unlock), chunk_size):
                chunk = channels_to_unlock[i:i+chunk_size]
                
                # Process this chunk of channels concurrently
                tasks = []
                for channel in chunk:
                    task = self.unlock_single_channel(channel, ctx.guild.default_role)
                    tasks.append(task)
                
                # Wait for all tasks in this chunk to complete
                await asyncio.gather(*tasks)
                
                # Update progress counter
                processed += len(chunk)
                await status_msg.edit(content=f"🔓 Unlocking channels... ({processed}/{total_channels})")
                
                # Brief pause to avoid rate limits
                if i + chunk_size < len(channels_to_unlock):
                    await asyncio.sleep(1)
                
            # Final success message
            await status_msg.edit(content=f"✅ Lockdown deactivated! {processed} channels unlocked successfully.")
            
        return True
    
    async def unlock_single_channel(self, channel: discord.TextChannel, default_role: discord.Role):
        """Unlock a single text channel."""
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
        - `.shield status` - Check current lockdown status
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
            success = await self.lock_channels(ctx, role_id)
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
            success = await self.unlock_channels(ctx)
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
