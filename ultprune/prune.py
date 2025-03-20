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
                # Protected from permission changes
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
                688318774608265405   # #news
            ],
            "channel_permissions": {}  # Store original permissions for channels
        }
        self.config.register_guild(**default_guild)
        
        # In-memory cache with TTL and size limit
        self.deleted_logs = TTLCache(ttl=86400, max_size=100)  # 24 hour TTL
        
        self.logs_api_url = "https://api.mclo.gs/1/log"
        self.session = None
        
        # Rate limiting protection
        self.deletion_tasks = {}
        self.cooldowns = {}
        
        # Schedule permission check task for protected channels
        self.permission_check_task = None

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

    @pruneset.command(name="protectedchannels")
    async def set_protected_channels(self, ctx: commands.Context, *channel_ids: int):
        """Set which channel IDs should be protected from lockdowns.
        
        Example: .pruneset protectedchannels 123456789 987654321
        Leave empty to reset to default list.
        """
        if not channel_ids:
            # Reset to defaults
            default_channels = [
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
                688318774608265405   # #news
            ]
            await self.config.guild(ctx.guild).protected_channels.set(default_channels)
            
            # Format channel names for display
            channel_list = ""
            for ch_id in default_channels:
                ch = ctx.guild.get_channel(ch_id)
                if ch:
                    channel_list += f"• {ch.mention}\n"
                else:
                    channel_list += f"• Unknown Channel (ID: {ch_id})\n"
            
            await ctx.send(f"Reset to default protected channels list:\n{channel_list}")
            return
            
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
