import discord
import json
import aiohttp
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box
from typing import Optional, Union
from collections import defaultdict

class Prune(commands.Cog):
    """A cog to skadosh messages from a specific user with an optional keyword, channel selection, and uploads logs to mclo.gs."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.deleted_logs = defaultdict(lambda: defaultdict(list))
        # Using mclo.gs API for log storage
        self.logs_api_url = "https://api.mclo.gs/1/log"

    async def upload_to_logs_service(self, content):
        """Upload content to mclo.gs and return the URL."""
        async with aiohttp.ClientSession() as session:
            data = {'content': content}
            async with session.post(self.logs_api_url, data=data) as response:
                if response.status == 200:
                    response_data = await response.json()
                    if response_data.get('success'):
                        return response_data['url']
                    else:
                        return f"Upload error: {response_data.get('error', 'Unknown error')}"
                else:
                    # If the upload fails, return error info
                    return f"Failed to upload: {response.status} - {await response.text()}"

    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def skadosh(self, ctx: commands.Context, user: discord.Member, amount: int, keyword: Optional[str] = None, channel: Optional[discord.TextChannel] = None):
        """Delete the last <amount> messages from <user> in a specific channel (default: current channel)."""
        if amount <= 0:
            return await ctx.send("Amount must be a positive number.")

        if not channel:
            channel = ctx.channel  

        def check(msg):
            return msg.author.id == user.id and (keyword.lower() in msg.content.lower() if keyword else True)

        deleted_messages = await channel.purge(limit=amount * 2, check=check, before=ctx.message)
        
        if not deleted_messages:
            return await ctx.send(f"No messages from {user.mention} found matching the criteria.")

        # Format the deleted messages for logging
        formatted_logs = "\n".join([
            f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author.name}: {msg.content}" 
            for msg in deleted_messages
        ])
        
        # Upload to mclo.gs
        log_url = await self.upload_to_logs_service(formatted_logs)
        
        # Store only the URL in memory temporarily
        guild_id = str(ctx.guild.id)
        channel_id = str(channel.id)
        self.deleted_logs[guild_id][channel_id].append({
            "user_id": user.id,
            "user": user.name,
            "count": len(deleted_messages),
            "timestamp": ctx.message.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "log_url": log_url
        })
        
        # Limit the number of stored links to prevent memory bloat
        if len(self.deleted_logs[guild_id][channel_id]) > 10:
            self.deleted_logs[guild_id][channel_id] = self.deleted_logs[guild_id][channel_id][-10:]

        await ctx.send(f"Deleted {len(deleted_messages)} messages from {user.mention} in {channel.mention}.\nLog: {log_url}")

    @commands.mod()
    @commands.guild_only()
    @commands.command()
    async def skadoshlogs(self, ctx: commands.Context, user: Optional[discord.Member] = None, limit: int = 5, channel: Optional[discord.TextChannel] = None):
        """Retrieve recent skadosh actions. Can filter by user and channel (default: current channel)."""
        if limit > 20:
            return await ctx.send("Limit cannot exceed 20 entries.")

        if not channel:
            channel = ctx.channel  

        guild_id = str(ctx.guild.id)
        channel_id = str(channel.id)

        logs = self.deleted_logs.get(guild_id, {}).get(channel_id, [])
        if not logs:
            return await ctx.send(f"No skadosh actions logged for {channel.mention}.")
       
        if user:
            logs = [log for log in logs if log["user_id"] == user.id]

        if not logs:
            return await ctx.send(f"No logs found for {user.mention if user else 'any users'} in {channel.mention}.")

        logs = logs[-limit:]  
        formatted_logs = "\n".join([
            f"[{log['timestamp']}] {log['user']}: {log['count']} messages - {log['log_url']}" 
            for log in logs
        ])

        await ctx.send(box(formatted_logs, lang="yaml"))

async def setup(bot: Red):
    await bot.add_cog(Prune(bot))
