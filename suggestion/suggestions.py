import asyncio
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Dict, List, Literal, Optional, Union
from datetime import datetime, timedelta


class Suggestion(commands.Cog):
    """
    A cog that creates and manages suggestion forum threads with voting functionality.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=954751253)
        
        default_guild = {
            "suggestion_channel_id": None,
            "user_forum_id": None,
            "staff_forum_id": None,
            "required_upvotes": 10,
            "required_downvotes": 10,
            "enabled": False,
            "auto_delete": True,
            "upvote_emoji": "✅",
            "downvote_emoji": "❌",
            "active_suggestions": {},  # Maps message_id to thread_id
            "blacklisted_users": [],  # List of blacklisted user IDs
            "suggestion_dialog": "Your suggestion has been submitted for community voting. If approved, it will be reviewed by staff. Misuse of this system may result in losing suggestion privileges.",
        }
        
        self.config.register_guild(**default_guild)
        self.emoji_check_task = self.bot.loop.create_task(self.check_emojis_loop())
        self.vote_check_task = self.bot.loop.create_task(self.check_votes_loop())
        
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.emoji_check_task.cancel()
        self.vote_check_task.cancel()
    
    @commands.group(name="suggestionset")
    @commands.admin_or_permissions(administrator=True)
    async def suggestion_settings(self, ctx: commands.Context):
        """Configure the suggestion system."""
        pass
        
    @suggestion_settings.command(name="enable")
    async def set_enabled(self, ctx: commands.Context, enabled: bool):
        """Enable or disable the suggestion system."""
        await self.config.guild(ctx.guild).enabled.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"The suggestion system has been {status}.")
        
    @suggestion_settings.command(name="suggestionchannel")
    async def set_suggestion_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where users will submit suggestions."""
        await self.config.guild(ctx.guild).suggestion_channel_id.set(channel.id)
        
        # Get the suggestion dialog to set as channel topic
        dialog = await self.config.guild(ctx.guild).suggestion_dialog()
        
        # Set the channel topic
        try:
            await channel.edit(topic=dialog)
            await ctx.send(f"Suggestion channel set to {channel.mention} with dialog message as the channel topic.")
        except discord.Forbidden:
            await ctx.send(f"Suggestion channel set to {channel.mention}, but I don't have permission to set the channel topic.")
        except discord.HTTPException:
            await ctx.send(f"Suggestion channel set to {channel.mention}, but failed to set the channel topic.")
        
    @suggestion_settings.command(name="userforum")
    async def set_user_forum(self, ctx: commands.Context, forum: discord.ForumChannel):
        """Set the forum where user suggestion threads will be posted for voting."""
        await self.config.guild(ctx.guild).user_forum_id.set(forum.id)
        await ctx.send(f"User voting forum set to {forum.mention}")
        
    @suggestion_settings.command(name="staffforum")
    async def set_staff_forum(self, ctx: commands.Context, forum: discord.ForumChannel):
        """Set the forum where staff will review approved suggestions."""
        await self.config.guild(ctx.guild).staff_forum_id.set(forum.id)
        await ctx.send(f"Staff review forum set to {forum.mention}")
        
    @suggestion_settings.command(name="requiredvotes")
    async def set_required_votes(self, ctx: commands.Context, upvotes: int, downvotes: int):
        """
        Set the number of votes required for promotion or deletion.
        
        Parameters:
        - upvotes: Number of upvotes required to move a suggestion to staff review
        - downvotes: Number of downvotes required to auto-delete a suggestion
        """
        await self.config.guild(ctx.guild).required_upvotes.set(upvotes)
        await self.config.guild(ctx.guild).required_downvotes.set(downvotes)
        await ctx.send(f"Required votes set to {upvotes} upvotes and {downvotes} downvotes")
        
    @suggestion_settings.command(name="autodelete")
    async def set_auto_delete(self, ctx: commands.Context, enabled: bool):
        """Enable or disable automatic deletion of heavily downvoted suggestions."""
        await self.config.guild(ctx.guild).auto_delete.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"Auto-deletion of downvoted suggestions has been {status}.")
        
    @suggestion_settings.command(name="emoji")
    async def set_voting_emoji(self, ctx: commands.Context, upvote_emoji: str, downvote_emoji: str):
        """Set the emoji to use for upvotes and downvotes."""
        # Store the emoji strings
        await self.config.guild(ctx.guild).upvote_emoji.set(upvote_emoji)
        await self.config.guild(ctx.guild).downvote_emoji.set(downvote_emoji)
        await ctx.send(f"Voting emojis set to {upvote_emoji} for upvotes and {downvote_emoji} for downvotes")
        
    @suggestion_settings.command(name="blacklist")
    async def blacklist_user(self, ctx: commands.Context, user: discord.Member, *, reason: str = None):
        """
        Blacklist a user from submitting suggestions.
        
        Parameters:
        - user: The user to blacklist
        - reason: Optional reason for the blacklist
        """
        # Get the current blacklist
        blacklisted_users = await self.config.guild(ctx.guild).blacklisted_users()
        
        # Check if the user is already blacklisted
        if user.id in blacklisted_users:
            await ctx.send(f"{user.mention} is already blacklisted from submitting suggestions.")
            return
        
        # Add the user to the blacklist
        blacklisted_users.append(user.id)
        await self.config.guild(ctx.guild).blacklisted_users.set(blacklisted_users)
        
        # Send confirmation
        if reason:
            await ctx.send(f"{user.mention} has been blacklisted from submitting suggestions.\nReason: {reason}")
        else:
            await ctx.send(f"{user.mention} has been blacklisted from submitting suggestions.")
        
        # Notify the user
        try:
            if reason:
                await user.send(f"You have been blacklisted from submitting suggestions in {ctx.guild.name}.\nReason: {reason}")
            else:
                await user.send(f"You have been blacklisted from submitting suggestions in {ctx.guild.name}.")
        except (discord.Forbidden, discord.HTTPException):
            # Cannot DM the user, continue silently
            pass
    
    @suggestion_settings.command(name="unblacklist")
    async def unblacklist_user(self, ctx: commands.Context, user: discord.Member):
        """Remove a user from the suggestion blacklist."""
        # Get the current blacklist
        blacklisted_users = await self.config.guild(ctx.guild).blacklisted_users()
        
        # Check if the user is blacklisted
        if user.id not in blacklisted_users:
            await ctx.send(f"{user.mention} is not blacklisted from submitting suggestions.")
            return
        
        # Remove the user from the blacklist
        blacklisted_users.remove(user.id)
        await self.config.guild(ctx.guild).blacklisted_users.set(blacklisted_users)
        
        # Send confirmation
        await ctx.send(f"{user.mention} has been removed from the suggestion blacklist.")
        
        # Notify the user
        try:
            await user.send(f"You are no longer blacklisted from submitting suggestions in {ctx.guild.name}.")
        except (discord.Forbidden, discord.HTTPException):
            # Cannot DM the user, continue silently
            pass
    
    @suggestion_settings.command(name="listblacklist")
    async def list_blacklisted_users(self, ctx: commands.Context):
        """View all blacklisted users."""
        # Get the current blacklist
        blacklisted_users = await self.config.guild(ctx.guild).blacklisted_users()
        
        if not blacklisted_users:
            await ctx.send("There are no blacklisted users.")
            return
        
        # Create an embed to display the blacklisted users
        embed = discord.Embed(
            title="Suggestion Blacklist",
            color=discord.Color.red(),
            description="Users who cannot submit suggestions:",
            timestamp=datetime.now()
        )
        
        # Add each user to the embed
        for user_id in blacklisted_users:
            user = ctx.guild.get_member(user_id)
            if user:
                embed.add_field(name=f"{user.display_name}", value=f"ID: {user.id}", inline=False)
            else:
                embed.add_field(name=f"Unknown User", value=f"ID: {user_id}", inline=False)
        
        await ctx.send(embed=embed)
    
    @suggestion_settings.command(name="dialog")
    async def set_suggestion_dialog(self, ctx: commands.Context, *, message: str):
        """
        Set the suggestion dialog message shown in the channel.
        
        This message will appear as the channel topic in the suggestion channel.
        """
        await self.config.guild(ctx.guild).suggestion_dialog.set(message)
        await ctx.send("Suggestion dialog message has been updated.")
        
        # Update the channel topic if the suggestion channel is set
        suggestion_channel_id = await self.config.guild(ctx.guild).suggestion_channel_id()
        if suggestion_channel_id:
            suggestion_channel = self.bot.get_channel(suggestion_channel_id)
            if suggestion_channel and isinstance(suggestion_channel, discord.TextChannel):
                try:
                    await suggestion_channel.edit(topic=message)
                    await ctx.send(f"Updated the channel topic for {suggestion_channel.mention}.")
                except discord.Forbidden:
                    await ctx.send("I don't have permission to update the channel topic.")
                except discord.HTTPException:
                    await ctx.send("Failed to update the channel topic.")
        
    @suggestion_settings.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View the current suggestion system settings."""
        settings = await self.config.guild(ctx.guild).all()
        
        # Get channel mentions if they exist
        suggestion_channel = self.bot.get_channel(settings["suggestion_channel_id"])
        user_forum = self.bot.get_channel(settings["user_forum_id"])
        staff_forum = self.bot.get_channel(settings["staff_forum_id"])
        
        suggestion_channel_str = suggestion_channel.mention if suggestion_channel else "Not set"
        user_forum_str = user_forum.mention if user_forum else "Not set"
        staff_forum_str = staff_forum.mention if staff_forum else "Not set"
        
        enabled_str = "Enabled" if settings["enabled"] else "Disabled"
        auto_delete_str = "Enabled" if settings["auto_delete"] else "Disabled"
        
        embed = discord.Embed(
            title="Suggestion System Settings",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Status", value=enabled_str, inline=True)
        embed.add_field(name="Auto-delete", value=auto_delete_str, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Empty field for spacing
        embed.add_field(name="Suggestion Channel", value=suggestion_channel_str, inline=True)
        embed.add_field(name="User Forum", value=user_forum_str, inline=True)
        embed.add_field(name="Staff Forum", value=staff_forum_str, inline=True)
        embed.add_field(name="Required Upvotes", value=settings["required_upvotes"], inline=True)
        embed.add_field(name="Required Downvotes", value=settings["required_downvotes"], inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Empty field for spacing
        embed.add_field(name="Upvote Emoji", value=settings["upvote_emoji"], inline=True)
        embed.add_field(name="Downvote Emoji", value=settings["downvote_emoji"], inline=True)
        
        # Add dialog message to embed
        embed.add_field(
            name="Suggestion Dialog", 
            value=settings["suggestion_dialog"][:1024] if len(settings["suggestion_dialog"]) <= 1024 
                  else settings["suggestion_dialog"][:1021] + "...",
            inline=False
        )
        
        # Add blacklist count
        blacklist_count = len(settings["blacklisted_users"])
        embed.add_field(name="Blacklisted Users", value=str(blacklist_count), inline=True)
        
        await ctx.send(embed=embed)
        
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Process messages in the suggestion channel."""
        # Ignore messages from bots
        if message.author.bot:
            return
            
        # Check if message is in a guild
        if not message.guild:
            return
            
        # Get the settings for this guild
        settings = await self.config.guild(message.guild).all()
        
        # Check if suggestions are enabled and if the message is in the suggestion channel
        if not settings["enabled"] or message.channel.id != settings["suggestion_channel_id"]:
            return
            
        # Check if user is blacklisted
        if message.author.id in settings["blacklisted_users"]:
            try:
                # Delete the message
                await message.delete()
                
                # Inform the user they are blacklisted
                warning = await message.channel.send(
                    f"{message.author.mention} You are blacklisted from submitting suggestions.",
                    delete_after=10  # Auto-delete after 10 seconds
                )
                
                return
            except (discord.Forbidden, discord.HTTPException):
                # If we can't delete the message, just return
                return
            
        # Get the user and staff forums
        user_forum = self.bot.get_channel(settings["user_forum_id"])
        staff_forum = self.bot.get_channel(settings["staff_forum_id"])
        
        if not user_forum:
            return
            
        try:
            # Delete the original message
            await message.delete()
            
            # Create a thread in the user forum for voting
            suggestion_thread = await user_forum.create_thread(
                name=f"Suggestion from {message.author.display_name}",
                content=message.content,
                auto_archive_duration=10080,  # 7 days
            )
            
            # Add voting reactions to the thread starter message
            starter_message = await suggestion_thread.starter_message()
            if starter_message:
                await starter_message.add_reaction(settings["upvote_emoji"])
                await starter_message.add_reaction(settings["downvote_emoji"])
                
                # Update active suggestions in the config
                active_suggestions = await self.config.guild(message.guild).active_suggestions()
                active_suggestions[str(starter_message.id)] = {
                    "thread_id": suggestion_thread.id,
                    "author_id": message.author.id,
                    "content": message.content,
                    "created_at": datetime.now().timestamp(),
                    "upvotes": 0,
                    "downvotes": 0,
                }
                await self.config.guild(message.guild).active_suggestions.set(active_suggestions)
                
                # Notify the user that their suggestion was created
                try:
                    embed = discord.Embed(
                        title="Suggestion Submitted",
                        description=f"Your suggestion has been submitted for community voting!",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Suggestion", value=message.content, inline=False)
                    embed.add_field(name="View Thread", value=f"[Click here]({starter_message.jump_url})", inline=False)
                    embed.add_field(
                        name="What happens next?", 
                        value=(
                            f"- Other users will vote on your suggestion with {settings['upvote_emoji']} or {settings['downvote_emoji']}\n"
                            f"- If it receives {settings['required_upvotes']} upvotes, it will be reviewed by staff\n"
                            f"- If it receives {settings['required_downvotes']} downvotes, it may be automatically deleted\n"
                            f"- Submitting inappropriate suggestions may result in being blacklisted"
                        ),
                        inline=False
                    )
                    
                    await message.author.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    # Cannot DM the user, continue silently
                    pass
        
        except discord.HTTPException as e:
            # Log the error
            print(f"Error creating suggestion: {str(e)}")
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Process reaction additions."""
        # Ignore bot reactions
        if user.bot:
            return
            
        # Check if the reaction is on a message in a guild
        if not reaction.message.guild:
            return
            
        # Get settings for this guild
        settings = await self.config.guild(reaction.message.guild).all()
        
        # Check if the system is enabled
        if not settings["enabled"]:
            return
            
        # Get active suggestions
        active_suggestions = await self.config.guild(reaction.message.guild).active_suggestions()
        
        # Check if this is a reaction on a suggestion message
        message_id = str(reaction.message.id)
        if message_id not in active_suggestions:
            return
            
        # Handle upvotes and downvotes
        if str(reaction.emoji) == settings["upvote_emoji"]:
            active_suggestions[message_id]["upvotes"] += 1
            await self.config.guild(reaction.message.guild).active_suggestions.set(active_suggestions)
            
        elif str(reaction.emoji) == settings["downvote_emoji"]:
            active_suggestions[message_id]["downvotes"] += 1
            await self.config.guild(reaction.message.guild).active_suggestions.set(active_suggestions)
            
        else:
            # Remove non-voting reactions
            try:
                await reaction.remove(user)
            except (discord.Forbidden, discord.HTTPException):
                pass
    
    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        """Process reaction removals."""
        # Ignore bot reactions
        if user.bot:
            return
            
        # Check if the reaction is on a message in a guild
        if not reaction.message.guild:
            return
            
        # Get settings for this guild
        settings = await self.config.guild(reaction.message.guild).all()
        
        # Check if the system is enabled
        if not settings["enabled"]:
            return
            
        # Get active suggestions
        active_suggestions = await self.config.guild(reaction.message.guild).active_suggestions()
        
        # Check if this is a reaction on a suggestion message
        message_id = str(reaction.message.id)
        if message_id not in active_suggestions:
            return
            
        # Update vote counts
        if str(reaction.emoji) == settings["upvote_emoji"]:
            active_suggestions[message_id]["upvotes"] = max(0, active_suggestions[message_id]["upvotes"] - 1)
            await self.config.guild(reaction.message.guild).active_suggestions.set(active_suggestions)
            
        elif str(reaction.emoji) == settings["downvote_emoji"]:
            active_suggestions[message_id]["downvotes"] = max(0, active_suggestions[message_id]["downvotes"] - 1)
            await self.config.guild(reaction.message.guild).active_suggestions.set(active_suggestions)
    
    async def check_emojis_loop(self):
        """Background loop to check and remove invalid emojis from suggestion threads."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Process each guild's active suggestions
                for guild in self.bot.guilds:
                    settings = await self.config.guild(guild).all()
                    
                    # Skip if suggestions are disabled
                    if not settings["enabled"]:
                        continue
                        
                    valid_emojis = [settings["upvote_emoji"], settings["downvote_emoji"]]
                    user_forum = self.bot.get_channel(settings["user_forum_id"])
                    
                    if not user_forum:
                        continue
                        
                    active_suggestions = await self.config.guild(guild).active_suggestions()
                    
                    for message_id, suggestion_data in active_suggestions.items():
                        try:
                            thread = self.bot.get_channel(suggestion_data["thread_id"])
                            
                            if not thread:
                                continue
                                
                            starter_message = await thread.starter_message()
                            
                            if not starter_message:
                                continue
                                
                            # Get all reactions on the message
                            for reaction in starter_message.reactions:
                                # If this is not a valid voting emoji
                                if str(reaction.emoji) not in valid_emojis:
                                    # Get users who reacted with this emoji
                                    async for user in reaction.users():
                                        # Don't remove the bot's own reactions
                                        if user.id != self.bot.user.id:
                                            try:
                                                await starter_message.remove_reaction(reaction.emoji, user)
                                            except (discord.Forbidden, discord.HTTPException):
                                                pass
                        except Exception as e:
                            print(f"Error checking emojis on suggestion {message_id}: {str(e)}")
                    
            except Exception as e:
                print(f"Error in emoji check loop: {str(e)}")
                
            # Check every 60 seconds
            await asyncio.sleep(60)
    
    async def check_votes_loop(self):
        """Background loop to check vote counts and promote/delete suggestions."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Process each guild's active suggestions
                for guild in self.bot.guilds:
                    settings = await self.config.guild(guild).all()
                    
                    # Skip if suggestions are disabled
                    if not settings["enabled"]:
                        continue
                        
                    user_forum = self.bot.get_channel(settings["user_forum_id"])
                    staff_forum = self.bot.get_channel(settings["staff_forum_id"])
                    
                    if not user_forum or not staff_forum:
                        continue
                        
                    active_suggestions = await self.config.guild(guild).active_suggestions()
                    updated_suggestions = active_suggestions.copy()
                    
                    for message_id, suggestion_data in active_suggestions.items():
                        try:
                            # Check upvotes for promotion to staff forum
                            if suggestion_data["upvotes"] >= settings["required_upvotes"]:
                                # Create a thread in the staff forum
                                author = guild.get_member(suggestion_data["author_id"])
                                author_name = author.display_name if author else "Unknown User"
                                
                                staff_thread = await staff_forum.create_thread(
                                    name=f"Approved Suggestion from {author_name}",
                                    content=f"**Original Suggestion:**\n{suggestion_data['content']}\n\n"
                                            f"**Votes:** {suggestion_data['upvotes']} ✅ | {suggestion_data['downvotes']} ❌",
                                    auto_archive_duration=10080,  # 7 days
                                )
                                
                                # Close the user forum thread
                                user_thread = self.bot.get_channel(suggestion_data["thread_id"])
                                if user_thread:
                                    try:
                                        await user_thread.edit(archived=True, locked=True)
                                    except discord.HTTPException:
                                        pass
                                
                                # Remove from active suggestions
                                del updated_suggestions[message_id]
                                
                                # Notify the author if possible
                                if author:
                                    try:
                                        await author.send(
                                            f"Your suggestion received enough votes and has been forwarded to the staff for review!"
                                        )
                                    except (discord.Forbidden, discord.HTTPException):
                                        pass
                            
                            # Check downvotes for auto-deletion
                            elif settings["auto_delete"] and suggestion_data["downvotes"] >= settings["required_downvotes"]:
                                # Close and delete the user forum thread
                                user_thread = self.bot.get_channel(suggestion_data["thread_id"])
                                if user_thread:
                                    try:
                                        await user_thread.delete()
                                    except discord.HTTPException:
                                        pass
                                
                                # Remove from active suggestions
                                del updated_suggestions[message_id]
                                
                                # Notify the author if possible
                                author = guild.get_member(suggestion_data["author_id"])
                                if author:
                                    try:
                                        await author.send(
                                            f"Your suggestion received too many downvotes and has been automatically removed."
                                        )
                                    except (discord.Forbidden, discord.HTTPException):
                                        pass
                                        
                        except Exception as e:
                            print(f"Error processing votes for suggestion {message_id}: {str(e)}")
                    
                    # Update active suggestions
                    if updated_suggestions != active_suggestions:
                        await self.config.guild(guild).active_suggestions.set(updated_suggestions)
                    
            except Exception as e:
                print(f"Error in vote check loop: {str(e)}")
                
            # Check every 5 minutes
            await asyncio.sleep(300)

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(Suggestion(bot))
