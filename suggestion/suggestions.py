import asyncio
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from typing import Dict, List, Literal, Optional, Union, Any
from datetime import datetime, timedelta
import re
import json
from collections import Counter


class Suggestion(commands.Cog):
    """
    A cog that creates and manages suggestion forum threads with voting functionality.
    Enhanced with tags, analytics, templates, and staff responses.
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
            "active_suggestions": {},  # Maps message_id to thread_id and metadata
            "completed_suggestions": {},  # Archive of processed suggestions
            "blacklisted_users": [],  # List of blacklisted user IDs
            "suggestion_dialog": "📝 **SUGGESTION SYSTEM** 📝\n\nAny message you type in this channel will be submitted as a suggestion and will be deleted from this channel.\n\n**How it works:**\n1️⃣ Type your suggestion in this channel\n2️⃣ A forum thread will be created for community voting\n3️⃣ Members can vote with ✅ or ❌\n4️⃣ Suggestions with 10+ ✅ will be reviewed by staff\n5️⃣ Suggestions with 10+ ❌ will be automatically removed\n\n**⚠️ IMPORTANT:**\n• Trolling or abusing the suggestion system will result in being blacklisted\n• Continued abuse may lead to server-wide moderation actions\n• Only serious, constructive suggestions will be considered\n• You'll receive a DM with a link to your suggestion thread",
            "available_tags": ["Feature Request", "Bug Report", "Content Suggestion", "QoL Improvement", "Other"],  # Default tags
            "suggestion_templates": {
                "default": "**Suggestion Title:** \n**Description:** \n**Why is this needed:** ",
                "feature": "**Feature Request**\n**Title:** \n**What does this feature do:** \n**Why is this needed:** \n**How would this improve the server/product:** ",
                "bug": "**Bug Report**\n**Issue:** \n**Steps to reproduce:** \n**Expected behavior:** \n**Actual behavior:** \n**Screenshots/Evidence:** ",
            },
            "user_cooldowns": {},  # User ID -> next allowed suggestion timestamp
            "cooldown_minutes": 60,  # Default 1 hour cooldown
            "exempt_roles": [],  # Roles exempt from cooldown
            "auto_archive_days": 14,  # Days before auto-archiving inactive suggestions
            "tag_format_regex": r"\[([^\]]+)\]",  # Format for tags in suggestions: [Tag]
            "analytics": {
                "total_submitted": 0,
                "total_approved": 0,
                "total_rejected": 0,
                "by_user": {},  # User ID -> count
                "by_tag": {},  # Tag -> count
                "by_status": {
                    "Implemented": 0,
                    "Planned": 0,
                    "Under Review": 0,
                    "Rejected": 0,
                    "Duplicate": 0
                },
                "last_reset": datetime.now().timestamp()
            }
        }
        
        self.config.register_guild(**default_guild)
        self.emoji_check_task = self.bot.loop.create_task(self.check_emojis_loop())
        self.vote_check_task = self.bot.loop.create_task(self.check_votes_loop())
        self.cleanup_task = self.bot.loop.create_task(self.scheduled_cleanup_loop())
        
    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.emoji_check_task.cancel()
        self.vote_check_task.cancel()
        self.cleanup_task.cancel()
        
    # ================ Tag Management Commands ================
    
    @commands.group(name="suggestiontags")
    @commands.admin_or_permissions(administrator=True)
    async def suggestion_tags(self, ctx: commands.Context):
        """Configure the suggestion tagging system."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
            
    @suggestion_tags.command(name="add")
    async def add_tag(self, ctx: commands.Context, *, tag_name: str):
        """Add a new tag to the available tags list."""
        tags = await self.config.guild(ctx.guild).available_tags()
        
        # Check if tag already exists
        if tag_name in tags:
            await ctx.send(f"Tag `{tag_name}` already exists.")
            return
            
        # Add the new tag
        tags.append(tag_name)
        await self.config.guild(ctx.guild).available_tags.set(tags)
        await ctx.send(f"Tag `{tag_name}` has been added to the available tags.")
        
    @suggestion_tags.command(name="remove")
    async def remove_tag(self, ctx: commands.Context, *, tag_name: str):
        """Remove a tag from the available tags list."""
        tags = await self.config.guild(ctx.guild).available_tags()
        
        # Check if tag exists
        if tag_name not in tags:
            await ctx.send(f"Tag `{tag_name}` does not exist.")
            return
            
        # Remove the tag
        tags.remove(tag_name)
        await self.config.guild(ctx.guild).available_tags.set(tags)
        await ctx.send(f"Tag `{tag_name}` has been removed from the available tags.")
        
    @suggestion_tags.command(name="list")
    async def list_tags(self, ctx: commands.Context):
        """List all available suggestion tags."""
        tags = await self.config.guild(ctx.guild).available_tags()
        
        if not tags:
            await ctx.send("There are no suggestion tags configured.")
            return
            
        embed = discord.Embed(
            title="Available Suggestion Tags",
            description="\n".join([f"• {tag}" for tag in tags]),
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
        
    # ================ Template Management Commands ================
    
    @commands.group(name="suggestiontemplates")
    @commands.admin_or_permissions(administrator=True)
    async def suggestion_templates(self, ctx: commands.Context):
        """Configure the suggestion template system."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @suggestion_templates.command(name="add")
    async def add_template(self, ctx: commands.Context, name: str, *, template: str):
        """
        Add or update a suggestion template.
        
        Parameters:
        - name: The name of the template
        - template: The template text
        """
        templates = await self.config.guild(ctx.guild).suggestion_templates()
        
        # Add/update the template
        templates[name.lower()] = template
        await self.config.guild(ctx.guild).suggestion_templates.set(templates)
        
        await ctx.send(f"Template `{name}` has been added/updated.")
    
    @suggestion_templates.command(name="remove")
    async def remove_template(self, ctx: commands.Context, name: str):
        """
        Remove a suggestion template.
        
        Parameters:
        - name: The name of the template to remove
        """
        templates = await self.config.guild(ctx.guild).suggestion_templates()
        
        # Check if template exists
        if name.lower() not in templates:
            await ctx.send(f"Template `{name}` does not exist.")
            return
            
        # Don't allow removal of the default template
        if name.lower() == "default":
            await ctx.send("You cannot remove the default template.")
            return
            
        # Remove the template
        del templates[name.lower()]
        await self.config.guild(ctx.guild).suggestion_templates.set(templates)
        
        await ctx.send(f"Template `{name}` has been removed.")
    
    @suggestion_templates.command(name="list")
    async def list_templates(self, ctx: commands.Context):
        """List all suggestion templates."""
        templates = await self.config.guild(ctx.guild).suggestion_templates()
        
        if not templates:
            await ctx.send("There are no suggestion templates configured.")
            return
            
        embed = discord.Embed(
            title="Available Suggestion Templates",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        for name, template in templates.items():
            preview = template[:1024] if len(template) <= 1024 else template[:1021] + "..."
            embed.add_field(name=name.capitalize(), value=preview, inline=False)
        
        await ctx.send(embed=embed)
        
    @suggestion_templates.command(name="show")
    async def show_template(self, ctx: commands.Context, name: str):
        """Show a specific suggestion template."""
        templates = await self.config.guild(ctx.guild).suggestion_templates()
        
        # Check if template exists
        if name.lower() not in templates:
            await ctx.send(f"Template `{name}` does not exist.")
            return
            
        template = templates[name.lower()]
        
        embed = discord.Embed(
            title=f"{name.capitalize()} Template",
            description=template,
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await ctx.send(embed=embed)
        
    # ================ Cooldown Management Commands ================
    
    @commands.group(name="suggestioncooldown")
    @commands.admin_or_permissions(administrator=True)
    async def suggestion_cooldown(self, ctx: commands.Context):
        """Configure the suggestion cooldown system."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @suggestion_cooldown.command(name="set")
    async def set_cooldown(self, ctx: commands.Context, minutes: int):
        """
        Set the cooldown between suggestions.
        
        Parameters:
        - minutes: Cooldown time in minutes (0 to disable)
        """
        if minutes < 0:
            await ctx.send("Cooldown minutes cannot be negative.")
            return
            
        await self.config.guild(ctx.guild).cooldown_minutes.set(minutes)
        
        if minutes == 0:
            await ctx.send("Suggestion cooldown has been disabled.")
        else:
            await ctx.send(f"Suggestion cooldown set to {minutes} minutes.")
    
    @suggestion_cooldown.command(name="exempt")
    async def exempt_role(self, ctx: commands.Context, role: discord.Role):
        """
        Add a role to the cooldown exemption list.
        
        Parameters:
        - role: The role to exempt
        """
        exempt_roles = await self.config.guild(ctx.guild).exempt_roles()
        
        # Check if role is already exempt
        if role.id in exempt_roles:
            await ctx.send(f"Role {role.name} is already exempt from cooldowns.")
            return
            
        # Add the role to exemptions
        exempt_roles.append(role.id)
        await self.config.guild(ctx.guild).exempt_roles.set(exempt_roles)
        
        await ctx.send(f"Role {role.name} is now exempt from suggestion cooldowns.")
    
    @suggestion_cooldown.command(name="unexempt")
    async def unexempt_role(self, ctx: commands.Context, role: discord.Role):
        """
        Remove a role from the cooldown exemption list.
        
        Parameters:
        - role: The role to remove from exemptions
        """
        exempt_roles = await self.config.guild(ctx.guild).exempt_roles()
        
        # Check if role is exempt
        if role.id not in exempt_roles:
            await ctx.send(f"Role {role.name} is not exempt from cooldowns.")
            return
            
        # Remove the role from exemptions
        exempt_roles.remove(role.id)
        await self.config.guild(ctx.guild).exempt_roles.set(exempt_roles)
        
        await ctx.send(f"Role {role.name} is no longer exempt from suggestion cooldowns.")
    
    @suggestion_cooldown.command(name="reset")
    async def reset_cooldown(self, ctx: commands.Context, user: discord.Member):
        """
        Reset a user's suggestion cooldown.
        
        Parameters:
        - user: The user to reset cooldown for
        """
        cooldowns = await self.config.guild(ctx.guild).user_cooldowns()
        
        # Check if user has a cooldown
        if str(user.id) not in cooldowns:
            await ctx.send(f"{user.mention} does not have an active cooldown.")
            return
            
        # Remove the cooldown
        del cooldowns[str(user.id)]
        await self.config.guild(ctx.guild).user_cooldowns.set(cooldowns)
        
        await ctx.send(f"Cooldown for {user.mention} has been reset.")
        
    # ================ Analytics Commands ================
    
    @commands.command(name="suggestionstats")
    @commands.mod_or_permissions(manage_messages=True)
    async def suggestion_stats(self, ctx: commands.Context, reset: bool = False):
        """
        View suggestion system analytics.
        
        Parameters:
        - reset: Whether to reset analytics after showing (default: False)
        """
        analytics = await self.config.guild(ctx.guild).analytics()
        
        # Create the analytics embed
        embed = discord.Embed(
            title="Suggestion System Analytics",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Add overview statistics
        embed.add_field(
            name="Overview",
            value=(
                f"**Total Submitted:** {analytics['total_submitted']}\n"
                f"**Total Approved:** {analytics['total_approved']}\n"
                f"**Total Rejected:** {analytics['total_rejected']}\n"
                f"**Approval Rate:** {(analytics['total_approved'] / analytics['total_submitted'] * 100) if analytics['total_submitted'] > 0 else 0:.1f}%"
            ),
            inline=False
        )
        
        # Add tag statistics
        if analytics['by_tag']:
            tag_stats = sorted(analytics['by_tag'].items(), key=lambda x: x[1], reverse=True)
            tags_text = "\n".join([f"• {tag}: {count}" for tag, count in tag_stats[:5]])
            embed.add_field(
                name="Most Popular Tags",
                value=tags_text if tags_text else "No tag data available",
                inline=True
            )
        
        # Add top submitters
        if analytics['by_user']:
            user_stats = sorted(analytics['by_user'].items(), key=lambda x: x[1], reverse=True)
            users_text = ""
            for user_id, count in user_stats[:5]:
                user = ctx.guild.get_member(int(user_id))
                username = user.display_name if user else f"Unknown User ({user_id})"
                users_text += f"• {username}: {count}\n"
            
            embed.add_field(
                name="Top Submitters",
                value=users_text if users_text else "No user data available",
                inline=True
            )
        
        # Add status statistics
        status_text = "\n".join([f"• {status}: {count}" for status, count in analytics['by_status'].items() if count > 0])
        embed.add_field(
            name="Status Distribution",
            value=status_text if status_text else "No status data available",
            inline=False
        )
        
        # Add reset time
        last_reset = datetime.fromtimestamp(analytics['last_reset'])
        embed.set_footer(text=f"Last Reset: {last_reset.strftime('%Y-%m-%d %H:%M:%S')}")
        
        await ctx.send(embed=embed)
        
        # Reset analytics if requested
        if reset:
            new_analytics = {
                "total_submitted": 0,
                "total_approved": 0,
                "total_rejected": 0,
                "by_user": {},
                "by_tag": {},
                "by_status": {
                    "Implemented": 0,
                    "Planned": 0,
                    "Under Review": 0,
                    "Rejected": 0,
                    "Duplicate": 0
                },
                "last_reset": datetime.now().timestamp()
            }
            await self.config.guild(ctx.guild).analytics.set(new_analytics)
            await ctx.send("Analytics have been reset.")
            
    # ================ Staff Response Commands ================
    
    @commands.command(name="suggestionresponse")
    @commands.mod_or_permissions(manage_messages=True)
    async def staff_response(self, ctx: commands.Context, thread: discord.Thread, status: str, *, response: str = None):
        """
        Add an official staff response to a suggestion.
        
        Parameters:
        - thread: The suggestion thread to respond to
        - status: Status to set (Implemented, Planned, Under Review, Rejected, Duplicate)
        - response: Optional response message
        """
        # Validate status
        valid_statuses = ["implemented", "planned", "under review", "rejected", "duplicate"]
        if status.lower() not in valid_statuses:
            await ctx.send(f"Invalid status. Please use one of: {', '.join(valid_statuses)}")
            return
            
        # Normalize status for display
        display_status = status.title() if status.lower() != "under review" else "Under Review"
        
        # Get settings and active suggestions
        settings = await self.config.guild(ctx.guild).all()
        active_suggestions = settings["active_suggestions"]
        
        # Find the suggestion associated with this thread
        thread_id = str(thread.id)
        message_id = None
        suggestion_data = None
        
        for msg_id, data in active_suggestions.items():
            if data.get("thread_id") == int(thread_id):
                message_id = msg_id
                suggestion_data = data
                break
                
        if not suggestion_data:
            await ctx.send("This thread is not associated with an active suggestion.")
            return
            
        # Create the response embed
        embed = discord.Embed(
            title=f"Staff Response: {display_status}",
            description=response if response else f"This suggestion has been marked as {display_status}",
            color=self._get_status_color(display_status),
            timestamp=datetime.now()
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        # Send the response to the thread
        await thread.send(embed=embed)
        
        # Update the analytics
        analytics = await self.config.guild(ctx.guild).analytics()
        analytics["by_status"][display_status] = analytics["by_status"].get(display_status, 0) + 1
        await self.config.guild(ctx.guild).analytics.set(analytics)
        
        # Update the status in the suggestion data
        suggestion_data["status"] = display_status
        suggestion_data["response"] = response
        suggestion_data["responded_by"] = ctx.author.id
        suggestion_data["response_time"] = datetime.now().timestamp()
        active_suggestions[message_id] = suggestion_data
        
        await self.config.guild(ctx.guild).active_suggestions.set(active_suggestions)
        
        # Notify the user if implemented or rejected
        if display_status in ["Implemented", "Rejected"]:
            author_id = suggestion_data.get("author_id")
            author = ctx.guild.get_member(author_id)
            
            if author:
                try:
                    user_embed = discord.Embed(
                        title=f"Your Suggestion has been {display_status}",
                        description=f"Your suggestion has received an official response:\n\n{response if response else f'This suggestion has been marked as {display_status}'}",
                        color=self._get_status_color(display_status),
                        timestamp=datetime.now()
                    )
                    user_embed.add_field(name="Original Suggestion", value=suggestion_data.get("content", ""), inline=False)
                    user_embed.add_field(name="View Thread", value=f"[Click here]({thread.jump_url})", inline=False)
                    
                    await author.send(embed=user_embed)
                except (discord.Forbidden, discord.HTTPException):
                    # Cannot DM the user, continue silently
                    pass
        
        await ctx.send(f"Response added to the suggestion with status: {display_status}")
        
    def _get_status_color(self, status: str) -> discord.Color:
        """Get the appropriate color for a status."""
        status_colors = {
            "Implemented": discord.Color.green(),
            "Planned": discord.Color.blue(),
            "Under Review": discord.Color.orange(),
            "Rejected": discord.Color.red(),
            "Duplicate": discord.Color.purple()
        }
        return status_colors.get(status, discord.Color.default())
        
    # ================ Scheduled Cleanup Command ================
    
    @commands.command(name="suggestcleanup")
    @commands.admin_or_permissions(administrator=True)
    async def manual_cleanup(self, ctx: commands.Context):
        """Manually trigger the suggestion cleanup process."""
        await ctx.send("Starting manual suggestion cleanup...")
        await self.perform_cleanup(ctx.guild)
        await ctx.send("Suggestion cleanup completed.")
        
    @commands.command(name="suggestarchive")
    @commands.admin_or_permissions(administrator=True)
    async def set_archive_days(self, ctx: commands.Context, days: int):
        """
        Set the number of days before suggestions are automatically archived.
        
        Parameters:
        - days: Number of days before archiving (0 to disable)
        """
        if days < 0:
            await ctx.send("Archive days cannot be negative.")
            return
            
        await self.config.guild(ctx.guild).auto_archive_days.set(days)
        
        if days == 0:
            await ctx.send("Automatic archiving has been disabled.")
        else:
            await ctx.send(f"Suggestions will be automatically archived after {days} days of inactivity.")
        
    # ================ Enhanced Original Commands ================
    
    @commands.group(name="suggestionset")
    @commands.admin_or_permissions(administrator=True)
    async def suggestion_settings(self, ctx: commands.Context):
        """Configure the suggestion system."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
        
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
        
        # Get the suggestion dialog to post in the channel
        dialog = await self.config.guild(ctx.guild).suggestion_dialog()
        templates = await self.config.guild(ctx.guild).suggestion_templates()
        tags = await self.config.guild(ctx.guild).available_tags()
        
        # Add available templates and tags to the dialog
        template_info = "\n\n**Available Templates:**\n"
        template_info += "\n".join([f"• `{name}` - Use by typing `/template {name}`" for name in templates.keys()])
        
        tag_info = "\n\n**Available Tags:**\n"
        tag_info += "\n".join([f"• `{tag}` - Use by including `[{tag}]` in your suggestion" for tag in tags])
        
        # Create an embed for the dialog message
        embed = discord.Embed(
            title="Suggestion System Information",
            description=dialog + template_info + tag_info,
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.set_footer(text="Last updated")
        
        try:
            # Send and pin the dialog message
            dialog_message = await channel.send(embed=embed)
            await dialog_message.pin()
            await ctx.send(f"Suggestion channel set to {channel.mention} with dialog message pinned in the channel.")
        except discord.Forbidden:
            await ctx.send(f"Suggestion channel set to {channel.mention}, but I don't have permission to send or pin messages.")
        except discord.HTTPException:
            await ctx.send(f"Suggestion channel set to {channel.mention}, but failed to post or pin the dialog message.")
        
    @suggestion_settings.command(name="userforum")
    async def set_user_forum(self, ctx: commands.Context, forum: discord.ForumChannel = None, category_id: int = 1243536580212166666):
        """
        Set the forum where user suggestion threads will be posted for voting.
        
        Parameters:
        - forum: The forum channel to use (optional - will use the category to find or create a forum)
        - category_id: The category ID to put the forum in (defaults to 1243536580212166666)
        """
        if forum:
            # If a forum is directly provided, use it
            await self.config.guild(ctx.guild).user_forum_id.set(forum.id)
            await ctx.send(f"User voting forum set to {forum.mention}")
            return
            
        # Try to find an existing forum channel in the specified category
        category = ctx.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await ctx.send(f"Error: Category with ID {category_id} not found or is not a category. Please provide a valid category ID.")
            return
            
        # Check for existing forum channels in this category
        existing_forums = [c for c in category.channels if isinstance(c, discord.ForumChannel)]
        
        if existing_forums:
            # Use the first forum found in the category
            forum = existing_forums[0]
            await self.config.guild(ctx.guild).user_forum_id.set(forum.id)
            await ctx.send(f"Found existing forum channel {forum.mention} in the category and set it as the user voting forum.")
        else:
            # Try to create a new forum channel in the category
            try:
                forum = await ctx.guild.create_forum(
                    name="suggestion-voting",
                    category=category,
                    topic="Vote on community suggestions here. Add ✅ to support or ❌ to deny."
                )
                await self.config.guild(ctx.guild).user_forum_id.set(forum.id)
                await ctx.send(f"Created and set new forum channel {forum.mention} as the user voting forum.")
            except discord.Forbidden:
                await ctx.send("I don't have permission to create forum channels. Please create a forum channel in the category and try again with that channel.")
            except discord.HTTPException as e:
                await ctx.send(f"Failed to create forum channel: {str(e)}")
        
    @suggestion_settings.command(name="staffforum")
    async def set_staff_forum(self, ctx: commands.Context, forum: discord.ForumChannel = None, category_id: int = 442253827392143360):
        """
        Set the forum where staff will review approved suggestions.
        
        Parameters:
        - forum: The forum channel to use (optional - will use the category to find or create a forum)
        - category_id: The category ID to put the forum in (defaults to 442253827392143360)
        """
        if forum:
            # If a forum is directly provided, use it
            await self.config.guild(ctx.guild).staff_forum_id.set(forum.id)
            await ctx.send(f"Staff review forum set to {forum.mention}")
            return
            
        # Try to find an existing forum channel in the specified category
        category = ctx.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await ctx.send(f"Error: Category with ID {category_id} not found or is not a category. Please provide a valid category ID.")
            return
            
        # Check for existing forum channels in this category
        existing_forums = [c for c in category.channels if isinstance(c, discord.ForumChannel)]
        
        if existing_forums:
            # Use the first forum found in the category
            forum = existing_forums[0]
            await self.config.guild(ctx.guild).staff_forum_id.set(forum.id)
            await ctx.send(f"Found existing forum channel {forum.mention} in the category and set it as the staff review forum.")
        else:
            # Try to create a new forum channel in the category
            try:
                forum = await ctx.guild.create_forum(
                    name="staff-suggestions",
                    category=category,
                    topic="Review community-approved suggestions here."
                )
                await self.config.guild(ctx.guild).staff_forum_id.set(forum.id)
                await ctx.send(f"Created and set new forum channel {forum.mention} as the staff review forum.")
            except discord.Forbidden:
                await ctx.send("I don't have permission to create forum channels. Please create a forum channel in the category and try again with that channel.")
            except discord.HTTPException as e:
                await ctx.send(f"Failed to create forum channel: {str(e)}")
        
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
        embed.add_field(name="Cooldown", value=f"{settings['cooldown_minutes']} minutes", inline=True)
        
        # Add tags info
        embed.add_field(
            name="Available Tags", 
            value=", ".join(settings["available_tags"]) if settings["available_tags"] else "None configured",
            inline=False
        )
        
        # Add template names
        embed.add_field(
            name="Available Templates",
            value=", ".join(settings["suggestion_templates"].keys()) if settings["suggestion_templates"] else "None configured",
            inline=False
        )
        
        # Add blacklist count
        blacklist_count = len(settings["blacklisted_users"])
        embed.add_field(name="Blacklisted Users", value=str(blacklist_count), inline=True)
        
        # Add analytics summary
        embed.add_field(
            name="Analytics Summary",
            value=f"Submissions: {settings['analytics']['total_submitted']} | Approved: {settings['analytics']['total_approved']} | Rejected: {settings['analytics']['total_rejected']}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    # ================ Blacklist Commands ================
    
    @commands.group(name="ignorelist")
    @commands.mod_or_permissions(manage_messages=True)
    async def ignorelist_commands(self, ctx: commands.Context):
        """Commands for managing the suggestion blacklist."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
    
    @ignorelist_commands.command(name="add")
    async def ignorelist_user(self, ctx: commands.Context, user: discord.Member, *, reason: str = None):
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
    
    @ignorelist_commands.command(name="remove")
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
    
    @ignorelist_commands.command(name="list")
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
        
    # ================ Template Command for Users ================
    
    @commands.command(name="template")
    async def get_template(self, ctx: commands.Context, template_name: str = "default"):
        """
        Get a suggestion template to use.
        
        Parameters:
        - template_name: The template to use (default if not specified)
        """
        # Get the templates
        settings = await self.config.guild(ctx.guild).all()
        templates = settings["suggestion_templates"]
        
        # Check if the requested template exists
        if template_name.lower() not in templates:
            available_templates = ", ".join(templates.keys())
            await ctx.send(
                f"{ctx.author.mention} Template `{template_name}` does not exist. Available templates: {available_templates}",
                delete_after=15
            )
            return
                
        # Get the template
        template = templates[template_name.lower()]
        
        # Send the template to the user via DM
        try:
            await ctx.author.send(f"**Suggestion Template ({template_name}):**\n\n{template}")
            
            # If this is in the suggestion channel, send a notification and delete the command
            if ctx.channel.id == settings.get("suggestion_channel_id"):
                await ctx.send(f"{ctx.author.mention} I've sent you the template via DM.", delete_after=10)
                try:
                    await ctx.message.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass
            else:
                # Otherwise, just send the template in the channel
                await ctx.send(f"Here's the template for `{template_name}`:\n\n{template}")
        except (discord.Forbidden, discord.HTTPException):
            # Cannot DM the user, send in channel
            await ctx.send(f"{ctx.author.mention} Here's the template:\n\n{template}")
        
    # ================ Event Listeners ================
    
    # Modify the on_message event listener to handle forum posts
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Process messages in the suggestion channel and forum posts."""
        # Ignore messages from bots other than our own
        if message.author.bot and message.author.id != self.bot.user.id:
            return
            
        # Check if message is in a guild
        if not message.guild:
            return
            
        # Get the settings for this guild
        settings = await self.config.guild(message.guild).all()
        
        # Check if suggestions are enabled
        if not settings["enabled"]:
            return
        
        # Handle messages in the suggestion channel
        if message.channel.id == settings["suggestion_channel_id"]:
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
                    
            # Check for cooldown
            if settings["cooldown_minutes"] > 0:
                # Check if user has roles that are exempt from cooldown
                exempt = False
                for role_id in settings["exempt_roles"]:
                    role = message.guild.get_role(role_id)
                    if role and role in message.author.roles:
                        exempt = True
                        break
                        
                # If not exempt, check cooldown
                if not exempt:
                    cooldowns = settings["user_cooldowns"]
                    user_id = str(message.author.id)
                    
                    if user_id in cooldowns:
                        next_allowed = datetime.fromtimestamp(cooldowns[user_id])
                        now = datetime.now()
                        
                        if now < next_allowed:
                            # User is on cooldown
                            time_left = next_allowed - now
                            minutes = time_left.seconds // 60
                            seconds = time_left.seconds % 60
                            
                            try:
                                # Delete the message
                                await message.delete()
                                
                                # Inform the user about the cooldown
                                warning = await message.channel.send(
                                    f"{message.author.mention} You are on cooldown. Please wait {minutes}m {seconds}s before submitting another suggestion.",
                                    delete_after=15  # Auto-delete after 15 seconds
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
                # Extract tags from the message using regex
                content = message.content
                tags = []
                tag_regex = settings["tag_format_regex"]
                
                # Find all tags in the message
                match = re.findall(tag_regex, content)
                if match:
                    for tag in match:
                        # Check if the tag is valid
                        if tag in settings["available_tags"]:
                            tags.append(tag)
                        
                    # Remove the tags from the message content
                    content = re.sub(tag_regex, "", content).strip()
                    
                # Delete the original message
                await message.delete()
                
                # Create a thread in the user forum for voting
                thread_name = f"Suggestion from {message.author.display_name}"
                if tags:
                    thread_name = f"[{', '.join(tags)}] {thread_name}"
                
                # Get proper forum tags if available
                forum_tags = []
                if isinstance(user_forum, discord.ForumChannel) and hasattr(user_forum, "available_tags"):
                    for tag_name in tags:
                        # Find matching forum tags by name
                        matching_tag = discord.utils.get(user_forum.available_tags, name=tag_name)
                        if matching_tag:
                            forum_tags.append(matching_tag.id)
                
                # Create the thread with proper API params
                suggestion_thread = await user_forum.create_thread(
                    name=thread_name[:100],  # Discord has a 100 character limit on thread names
                    content=content,
                    auto_archive_duration=10080,  # 7 days
                    applied_tags=forum_tags if forum_tags else None
                )
                
                # Wait a short moment for Discord to process
                await asyncio.sleep(1)
                
                # Try multiple approaches to get the starter message
                starter_message = None
                
                # Approach 1: Try to get the message directly from the thread creation response
                if hasattr(suggestion_thread, "message") and suggestion_thread.message:
                    starter_message = suggestion_thread.message
                    print(f"Got starter message directly from thread creation: {starter_message.id}")
                
                # Approach 2: Try to get the starter message using the API method
                if not starter_message:
                    try:
                        starter_message = await suggestion_thread.starter_message()
                        if starter_message:
                            print(f"Got starter message using starter_message(): {starter_message.id}")
                    except Exception as e:
                        print(f"Error getting starter message with API: {str(e)}")
                
                # Approach 3: Retry a few times with delay
                if not starter_message:
                    for attempt in range(3):
                        try:
                            await asyncio.sleep(1)
                            starter_message = await suggestion_thread.starter_message()
                            if starter_message:
                                print(f"Got starter message after {attempt+1} retries: {starter_message.id}")
                                break
                        except Exception as e:
                            print(f"Error getting starter message (attempt {attempt+1}): {str(e)}")
                
                # Approach 4: If all else fails, try to get the first message from history
                if not starter_message:
                    try:
                        print(f"Using history fallback for thread {suggestion_thread.id}")
                        async for first_msg in suggestion_thread.history(limit=1, oldest_first=True):
                            starter_message = first_msg
                            print(f"Got first message from history: {starter_message.id}")
                            break
                    except Exception as e:
                        print(f"Error getting message from history: {str(e)}")
                
                # Now add reactions if we found a message
                if starter_message:
                    try:
                        # Add reactions with individual error handling
                        try:
                            await starter_message.add_reaction(settings["upvote_emoji"])
                            print(f"Added upvote emoji to {starter_message.id}")
                        except Exception as e:
                            print(f"Error adding upvote reaction: {str(e)}")
                        
                        await asyncio.sleep(0.5)  # Add delay between reactions
                        
                        try:
                            await starter_message.add_reaction(settings["downvote_emoji"])
                            print(f"Added downvote emoji to {starter_message.id}")
                        except Exception as e:
                            print(f"Error adding downvote reaction: {str(e)}")
                        
                        # Update active suggestions in the config
                        active_suggestions = await self.config.guild(message.guild).active_suggestions()
                        active_suggestions[str(starter_message.id)] = {
                            "thread_id": suggestion_thread.id,
                            "author_id": message.author.id,
                            "content": content,
                            "created_at": datetime.now().timestamp(),
                            "upvotes": 0,
                            "downvotes": 0,
                            "tags": tags,
                            "status": "Pending"
                        }
                        await self.config.guild(message.guild).active_suggestions.set(active_suggestions)
                        print(f"Successfully added suggestion to database with ID {starter_message.id}")
                    except Exception as e:
                        print(f"Error updating suggestion data: {str(e)}")
                else:
                    print(f"Failed to find starter message for thread {suggestion_thread.id}")
                
                # Update analytics
                analytics = await self.config.guild(message.guild).analytics()
                
                # Increment total submitted
                analytics["total_submitted"] += 1
                
                # Update by_user count
                user_id_str = str(message.author.id)
                analytics["by_user"][user_id_str] = analytics["by_user"].get(user_id_str, 0) + 1
                
                # Update by_tag count
                for tag in tags:
                    analytics["by_tag"][tag] = analytics["by_tag"].get(tag, 0) + 1
                    
                await self.config.guild(message.guild).analytics.set(analytics)
                
                # Set cooldown for the user
                if settings["cooldown_minutes"] > 0:
                    # Check if user is exempt from cooldown
                    exempt = False
                    for role_id in settings["exempt_roles"]:
                        role = message.guild.get_role(role_id)
                        if role and role in message.author.roles:
                            exempt = True
                            break
                            
                    # If not exempt, set cooldown
                    if not exempt:
                        cooldowns = settings["user_cooldowns"]
                        now = datetime.now()
                        next_allowed = now + timedelta(minutes=settings["cooldown_minutes"])
                        
                        cooldowns[str(message.author.id)] = next_allowed.timestamp()
                        await self.config.guild(message.guild).user_cooldowns.set(cooldowns)
                
                # Notify the user that their suggestion was created
                try:
                    embed = discord.Embed(
                        title="Suggestion Submitted",
                        description=f"Your suggestion has been submitted for community voting!",
                        color=discord.Color.green(),
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Suggestion", value=content, inline=False)
                    
                    if tags:
                        embed.add_field(name="Tags", value=", ".join(tags), inline=False)
                        
                    if starter_message:
                        embed.add_field(name="View Thread", value=f"[Click here]({starter_message.jump_url})", inline=False)
                    else:
                        embed.add_field(name="View Thread", value=f"[Click here]({suggestion_thread.jump_url})", inline=False)
                    
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
                    
                    if settings["cooldown_minutes"] > 0:
                        exempt = False
                        for role_id in settings["exempt_roles"]:
                            role = message.guild.get_role(role_id)
                            if role and role in message.author.roles:
                                exempt = True
                                break
                                
                        if not exempt:
                            next_allowed = datetime.now() + timedelta(minutes=settings["cooldown_minutes"])
                            embed.add_field(
                                name="Cooldown",
                                value=f"You can submit another suggestion after {next_allowed.strftime('%Y-%m-%d %H:%M:%S')}",
                                inline=False
                            )
                    
                    await message.author.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    # Cannot DM the user, continue silently
                    pass
            
            except discord.HTTPException as e:
                # Log the error
                print(f"Error creating suggestion: {str(e)}")
        
        # Add reactions to forum posts in the user forum
        elif isinstance(message.channel, discord.Thread) and message.channel.parent_id == settings["user_forum_id"]:
            # Only process the first message in the thread (the thread starter)
            try:
                # Try to get the starter message and check if this message is it
                starter_message = None
                is_starter = False
                
                try:
                    starter_message = await message.channel.starter_message()
                    if starter_message and message.id == starter_message.id:
                        is_starter = True
                except Exception as e:
                    print(f"Error checking if message is starter: {str(e)}")
                    
                    # Try to check if this is the first message in the thread
                    try:
                        async for first_msg in message.channel.history(limit=1, oldest_first=True):
                            if first_msg.id == message.id:
                                is_starter = True
                            break
                    except Exception as inner_e:
                        print(f"Error checking history: {str(inner_e)}")
                
                # If this is the starter message
                if is_starter:
                    # Check if this is a thread we created for suggestions
                    active_suggestions = await self.config.guild(message.guild).active_suggestions()
                    thread_id = message.channel.id
                    message_id = str(message.id)
                    
                    # Check if we need to add reactions
                    needs_reactions = True
                    
                    # First check if we're already tracking this message
                    if message_id in active_suggestions:
                        print(f"Message {message_id} already in active suggestions")
                        needs_reactions = False
                    
                    # Then check if we're tracking the thread but not the message
                    thread_found = False
                    for msg_id, data in active_suggestions.items():
                        if data.get("thread_id") == thread_id:
                            thread_found = True
                            break
                    
                    # If we should add reactions to this message
                    if needs_reactions or not thread_found:
                        print(f"Adding reactions to thread starter {message.id} in thread {thread_id}")
                        
                        # Add voting reactions with individual error handling
                        try:
                            await message.add_reaction(settings["upvote_emoji"])
                            print(f"Added upvote emoji to {message.id}")
                        except Exception as e:
                            print(f"Error adding upvote reaction: {str(e)}")
                        
                        await asyncio.sleep(0.5)  # Add delay between reactions
                        
                        try:
                            await message.add_reaction(settings["downvote_emoji"])
                            print(f"Added downvote emoji to {message.id}")
                        except Exception as e:
                            print(f"Error adding downvote reaction: {str(e)}")
                        
                        # Store the message in active suggestions if not already there
                        if message_id not in active_suggestions:
                            active_suggestions[message_id] = {
                                "thread_id": thread_id,
                                "author_id": message.author.id,
                                "content": message.content,
                                "created_at": datetime.now().timestamp(),
                                "upvotes": 0,
                                "downvotes": 0,
                                "tags": [],  # Extract tags if needed
                                "status": "Pending"
                            }
                            await self.config.guild(message.guild).active_suggestions.set(active_suggestions)
                            print(f"Added message {message_id} to active suggestions")
            except (discord.HTTPException, discord.Forbidden) as e:
                print(f"Error processing forum post: {str(e)}")
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Process reaction additions."""
        # Ignore bot reactions (except our own bot for voting emojis)
        if user.bot and user.id != self.bot.user.id:
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
            # Check if it's a reaction on a thread starter message we don't have tracked yet
            if isinstance(reaction.message.channel, discord.Thread) and reaction.message.channel.parent_id == settings.get("user_forum_id"):
                try:
                    # Try to get the starter message
                    starter_message = None
                    try:
                        starter_message = await reaction.message.channel.starter_message()
                    except Exception:
                        pass
                        
                    # If we got the starter message and it matches this message
                    if starter_message and starter_message.id == reaction.message.id:
                        # Add this message to active suggestions if it's not already there
                        active_suggestions[message_id] = {
                            "thread_id": reaction.message.channel.id,
                            "author_id": reaction.message.author.id,
                            "content": reaction.message.content,
                            "created_at": reaction.message.created_at.timestamp(),
                            "upvotes": 0,
                            "downvotes": 0,
                            "tags": [],  # We don't have tags here
                            "status": "Pending"
                        }
                        await self.config.guild(reaction.message.guild).active_suggestions.set(active_suggestions)
                        print(f"Added previously untracked message {message_id} to suggestions via reaction")
                except Exception as e:
                    print(f"Error tracking new message from reaction: {str(e)}")
                    return
            else:
                return
                
        # Handle upvotes and downvotes
        if str(reaction.emoji) == settings["upvote_emoji"]:
            active_suggestions[message_id]["upvotes"] += 1
            await self.config.guild(reaction.message.guild).active_suggestions.set(active_suggestions)
            print(f"Upvote added to message {message_id}, new count: {active_suggestions[message_id]['upvotes']}")
            
        elif str(reaction.emoji) == settings["downvote_emoji"]:
            active_suggestions[message_id]["downvotes"] += 1
            await self.config.guild(reaction.message.guild).active_suggestions.set(active_suggestions)
            print(f"Downvote added to message {message_id}, new count: {active_suggestions[message_id]['downvotes']}")
            
        else:
            # Remove non-voting reactions
            try:
                # Only remove if it's not our bot adding the voting reactions
                if user.id != self.bot.user.id:
                    await reaction.remove(user)
                    print(f"Removed invalid reaction {reaction.emoji} from {message_id}")
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"Error removing reaction: {str(e)}")
    
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
    
    # ================ Background Tasks ================
    
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
                        
                    # Check all active suggestions
                    active_suggestions = await self.config.guild(guild).active_suggestions()
                    
                    for message_id, suggestion_data in active_suggestions.items():
                        try:
                            thread_id = suggestion_data.get("thread_id")
                            if not thread_id:
                                continue
                                
                            thread = self.bot.get_channel(thread_id)
                            if not thread:
                                continue
                            
                            # Try to get the starter message
                            starter_message = None
                            
                            # Try multiple approaches to get the starter message
                            try:
                                starter_message = await thread.starter_message()
                            except Exception as e:
                                print(f"Error getting starter message in check_emojis_loop: {str(e)}")
                            
                            # If that failed, try to get the message directly
                            if not starter_message:
                                try:
                                    starter_message = await thread.fetch_message(int(message_id))
                                except Exception as e:
                                    print(f"Error fetching message {message_id}: {str(e)}")
                            
                            # If that failed too, try to get the first message in history
                            if not starter_message:
                                try:
                                    async for first_msg in thread.history(limit=1, oldest_first=True):
                                        starter_message = first_msg
                                        break
                                except Exception as e:
                                    print(f"Error getting history: {str(e)}")
                            
                            if not starter_message:
                                continue
                                
                            # First ensure our voting emojis are present
                            has_upvote = False
                            has_downvote = False
                            
                            # Check existing reactions
                            for reaction in starter_message.reactions:
                                emoji = str(reaction.emoji)
                                
                                # Check if our voting emojis are present
                                if emoji == settings["upvote_emoji"]:
                                    has_upvote = True
                                elif emoji == settings["downvote_emoji"]:
                                    has_downvote = True
                                # Remove any non-voting emoji
                                elif emoji not in valid_emojis:
                                    # Get users who reacted with this emoji
                                    async for user in reaction.users():
                                        if user.id != self.bot.user.id:
                                            try:
                                                await starter_message.remove_reaction(emoji, user)
                                                print(f"Removed invalid reaction {emoji} in thread {thread_id}")
                                            except Exception as e:
                                                print(f"Error removing reaction: {str(e)}")
                            
                            # Add our voting emojis if they're missing
                            if not has_upvote:
                                try:
                                    await starter_message.add_reaction(settings["upvote_emoji"])
                                    print(f"Added missing upvote reaction to {starter_message.id}")
                                except Exception as e:
                                    print(f"Error adding upvote: {str(e)}")
                                    
                            if not has_downvote:
                                try:
                                    await starter_message.add_reaction(settings["downvote_emoji"])
                                    print(f"Added missing downvote reaction to {starter_message.id}")
                                except Exception as e:
                                    print(f"Error adding downvote: {str(e)}")
                                    
                        except Exception as e:
                            print(f"Error checking emojis on suggestion {message_id}: {str(e)}")
                    
                    # Also check recent threads in the forum that might not be tracked yet
                    if isinstance(user_forum, discord.ForumChannel):
                        try:
                            # Get active threads in the forum
                            for thread in user_forum.threads:
                                # Skip if thread is already tracked in active suggestions
                                is_tracked = False
                                for _, data in active_suggestions.items():
                                    if data.get("thread_id") == thread.id:
                                        is_tracked = True
                                        break
                                
                                if is_tracked:
                                    continue
                                    
                                # Only check recent threads (less than 24 hours old)
                                thread_age = (datetime.now() - thread.created_at.replace(tzinfo=None)).total_seconds()
                                if thread_age > 86400:  # 24 hours in seconds
                                    continue
                                    
                                # Try to get the starter message
                                starter_message = None
                                try:
                                    starter_message = await thread.starter_message()
                                except Exception:
                                    pass
                                    
                                if not starter_message:
                                    try:
                                        async for msg in thread.history(limit=1, oldest_first=True):
                                            starter_message = msg
                                            break
                                    except Exception:
                                        pass
                                
                                if starter_message:
                                    # Check if it has our reactions
                                    has_upvote = False
                                    has_downvote = False
                                    
                                    for reaction in starter_message.reactions:
                                        emoji = str(reaction.emoji)
                                        if emoji == settings["upvote_emoji"]:
                                            has_upvote = True
                                        elif emoji == settings["downvote_emoji"]:
                                            has_downvote = True
                                    
                                    # Add missing reactions
                                    if not has_upvote:
                                        try:
                                            await starter_message.add_reaction(settings["upvote_emoji"])
                                            print(f"Added upvote to untracked thread {thread.id}")
                                        except Exception:
                                            pass
                                            
                                    if not has_downvote:
                                        try:
                                            await starter_message.add_reaction(settings["downvote_emoji"])
                                            print(f"Added downvote to untracked thread {thread.id}")
                                        except Exception:
                                            pass
                                    
                                    # Track this thread in active suggestions
                                    active_suggestions[str(starter_message.id)] = {
                                        "thread_id": thread.id,
                                        "author_id": starter_message.author.id,
                                        "content": starter_message.content,
                                        "created_at": thread.created_at.timestamp(),
                                        "upvotes": 0,
                                        "downvotes": 0,
                                        "tags": [],  # We don't have tags here
                                        "status": "Pending"
                                    }
                                    await self.config.guild(guild).active_suggestions.set(active_suggestions)
                                    print(f"Added previously untracked thread {thread.id} to suggestions")
                        except Exception as e:
                            print(f"Error processing forum threads: {str(e)}")
                    
                except Exception as e:
                    print(f"Error in emoji check loop: {str(e)}")
                    
                # Check more frequently (every 30 seconds)
                await asyncio.sleep(30)
        
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
                            # Skip suggestions that already have a status other than "Pending"
                            if suggestion_data.get("status", "Pending") != "Pending":
                                continue
                                
                            # Check upvotes for promotion to staff forum
                            if suggestion_data["upvotes"] >= settings["required_upvotes"]:
                                # Create a thread in the staff forum
                                author = guild.get_member(suggestion_data["author_id"])
                                author_name = author.display_name if author else "Unknown User"
                                
                                # Format the content with tags if present
                                tag_display = f"[{', '.join(suggestion_data.get('tags', []))}] " if suggestion_data.get('tags') else ""
                                thread_title = f"{tag_display}Approved: {author_name}'s Suggestion"
                                thread_content = f"**Original Suggestion:**\n{suggestion_data['content']}\n\n"
                                
                                if suggestion_data.get('tags'):
                                    thread_content += f"**Tags:** {', '.join(suggestion_data['tags'])}\n\n"
                                    
                                thread_content += f"**Votes:** {suggestion_data['upvotes']} {settings['upvote_emoji']} | {suggestion_data['downvotes']} {settings['downvote_emoji']}"
                                
                                staff_thread = await staff_forum.create_thread(
                                    name=thread_title[:100],  # Discord has a 100 character limit on thread names
                                    content=thread_content,
                                    auto_archive_duration=10080,  # 7 days
                                )

                                starter_message = await suggestion_thread.starter_message()
                                if starter_message:
                                    try:
                                        # Add our voting emojis
                                        await starter_message.add_reaction(settings["upvote_emoji"])
                                        await starter_message.add_reaction(settings["downvote_emoji"])
                                        
                                        # Remove any existing reactions that aren't our voting emojis
                                        valid_emojis = [settings["upvote_emoji"], settings["downvote_emoji"]]
                                        for reaction in starter_message.reactions:
                                            if str(reaction.emoji) not in valid_emojis:
                                                async for user in reaction.users():
                                                    if user.id != self.bot.user.id:
                                                        try:
                                                            await starter_message.remove_reaction(reaction.emoji, user)
                                                        except (discord.Forbidden, discord.HTTPException):
                                                            pass
                                    except discord.HTTPException as e:
                                        print(f"Error adding reactions to suggestion thread: {str(e)}")
                                
                                # Add a staff action embed with response options
                                action_embed = discord.Embed(
                                    title="Staff Actions",
                                    description=(
                                        "Use the following command to respond to this suggestion:\n\n"
                                        f"`/suggestionresponse {staff_thread.mention} [status] [response]`\n\n"
                                        "**Available Statuses:**\n"
                                        "• `implemented` - The suggestion has been implemented\n"
                                        "• `planned` - The suggestion is planned for future implementation\n"
                                        "• `under review` - The suggestion is still being considered\n"
                                        "• `rejected` - The suggestion has been rejected\n"
                                        "• `duplicate` - The suggestion is a duplicate of another suggestion"
                                    ),
                                    color=discord.Color.blue(),
                                    timestamp=datetime.now()
                                )
                                
                                await staff_thread.send(embed=action_embed)
                                
                                # Close the user forum thread
                                user_thread = self.bot.get_channel(suggestion_data["thread_id"])
                                if user_thread:
                                    try:
                                        await user_thread.edit(archived=True, locked=True)
                                        
                                        # Send final message with promotion information
                                        await user_thread.send(
                                            "This suggestion has received enough upvotes and has been forwarded to staff for review."
                                        )
                                    except discord.HTTPException:
                                        pass
                                
                                # Update the suggestion status
                                suggestion_data["status"] = "Under Review"
                                updated_suggestions[message_id] = suggestion_data
                                
                                # Update analytics
                                analytics = await self.config.guild(guild).analytics()
                                analytics["total_approved"] += 1
                                await self.config.guild(guild).analytics.set(analytics)
                                
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
                                        # Send final message with rejection information
                                        await user_thread.send(
                                            "This suggestion has received too many downvotes and has been automatically removed."
                                        )
                                        
                                        # Archive and lock the thread rather than deleting it
                                        await user_thread.edit(archived=True, locked=True)
                                    except discord.HTTPException:
                                        pass
                                
                                # Update the suggestion status
                                suggestion_data["status"] = "Rejected"
                                suggestion_data["response"] = "Automatically rejected due to too many downvotes."
                                suggestion_data["response_time"] = datetime.now().timestamp()
                                
                                # Move to completed suggestions
                                completed_suggestions = await self.config.guild(guild).completed_suggestions()
                                completed_suggestions[message_id] = suggestion_data
                                await self.config.guild(guild).completed_suggestions.set(completed_suggestions)
                                
                                # Remove from active suggestions
                                del updated_suggestions[message_id]
                                
                                # Update analytics
                                analytics = await self.config.guild(guild).analytics()
                                analytics["total_rejected"] += 1
                                await self.config.guild(guild).analytics.set(analytics)
                                
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
    
    async def scheduled_cleanup_loop(self):
        """Background loop to clean up and archive old suggestions."""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                # Process each guild's active suggestions
                for guild in self.bot.guilds:
                    await self.perform_cleanup(guild)
                    
            except Exception as e:
                print(f"Error in cleanup loop: {str(e)}")
                
            # Check once per day
            await asyncio.sleep(86400)  # 24 hours
    
    async def perform_cleanup(self, guild: discord.Guild):
        """Perform cleanup of old suggestions for a guild."""
        settings = await self.config.guild(guild).all()
        
        # Skip if suggestions are disabled or auto-archive is disabled
        if not settings["enabled"] or settings["auto_archive_days"] <= 0:
            return
            
        # Calculate the cutoff time
        cutoff_time = datetime.now() - timedelta(days=settings["auto_archive_days"])
        cutoff_timestamp = cutoff_time.timestamp()
        
        active_suggestions = await self.config.guild(guild).active_suggestions()
        updated_suggestions = active_suggestions.copy()
        completed_suggestions = await self.config.guild(guild).completed_suggestions()
        
        # Check for old suggestions to archive
        for message_id, suggestion_data in active_suggestions.items():
            try:
                # Skip suggestions that already have a status other than "Pending"
                if suggestion_data.get("status", "Pending") != "Pending":
                    continue
                    
                # Check if the suggestion is older than the cutoff
                if suggestion_data["created_at"] < cutoff_timestamp:
                    # Get the thread
                    thread = self.bot.get_channel(suggestion_data["thread_id"])
                    
                    if thread:
                        try:
                            # Send notification about archiving
                            await thread.send(
                                f"This suggestion is being automatically archived after {settings['auto_archive_days']} days of inactivity."
                            )
                            
                            # Archive and lock the thread
                            await thread.edit(archived=True, locked=True)
                        except discord.HTTPException:
                            pass
                    
                    # Update the suggestion status
                    suggestion_data["status"] = "Archived"
                    suggestion_data["response"] = f"Automatically archived after {settings['auto_archive_days']} days of inactivity."
                    suggestion_data["response_time"] = datetime.now().timestamp()
                    
                    # Move to completed suggestions
                    completed_suggestions[message_id] = suggestion_data
                    
                    # Remove from active suggestions
                    del updated_suggestions[message_id]
                    
            except Exception as e:
                print(f"Error archiving old suggestion {message_id}: {str(e)}")
        
        # Update the suggestion lists if changes were made
        if updated_suggestions != active_suggestions:
            await self.config.guild(guild).active_suggestions.set(updated_suggestions)
            await self.config.guild(guild).completed_suggestions.set(completed_suggestions)
            
            # Generate a cleanup report
            total_archived = len(active_suggestions) - len(updated_suggestions)
            
            # Try to send the report to a log channel
            # For now, we'll just print it
            print(f"Archived {total_archived} old suggestions in {guild.name}")
    
    # ================ Helper Methods ================
    
    async def _extract_suggestion_analytics(self, guild: discord.Guild):
        """Extract analytics from suggestion data."""
        analytics = {
            "total_submitted": 0,
            "total_approved": 0,
            "total_rejected": 0,
            "by_user": {},
            "by_tag": {},
            "by_status": {
                "Implemented": 0,
                "Planned": 0,
                "Under Review": 0,
                "Rejected": 0,
                "Duplicate": 0
            },
            "last_reset": datetime.now().timestamp()
        }
        
        # Get active and completed suggestions
        active_suggestions = await self.config.guild(guild).active_suggestions()
        completed_suggestions = await self.config.guild(guild).completed_suggestions()
        
        # Count active suggestions
        for suggestion_id, data in active_suggestions.items():
            analytics["total_submitted"] += 1
            
            # Count by user
            user_id = str(data.get("author_id", "unknown"))
            analytics["by_user"][user_id] = analytics["by_user"].get(user_id, 0) + 1
            
            # Count by tags
            for tag in data.get("tags", []):
                analytics["by_tag"][tag] = analytics["by_tag"].get(tag, 0) + 1
                
            # Count by status
            status = data.get("status", "Pending")
            if status in analytics["by_status"]:
                analytics["by_status"][status] += 1
                
            # Count approved/rejected
            if status == "Under Review":
                analytics["total_approved"] += 1
        
        # Count completed suggestions
        for suggestion_id, data in completed_suggestions.items():
            # We already counted it as submitted when active
            
            # Count by status
            status = data.get("status", "Pending")
            if status in analytics["by_status"]:
                analytics["by_status"][status] += 1
                
            # Count rejected
            if status == "Rejected":
                analytics["total_rejected"] += 1
                
        return analytics
    
    def _get_user_display_name(self, guild: discord.Guild, user_id: int) -> str:
        """Get a user's display name."""
        user = guild.get_member(user_id)
        return user.display_name if user else f"Unknown User ({user_id})"

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(Suggestion(bot))
