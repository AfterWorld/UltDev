import json
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify


class AnimeForumCreator(commands.Cog):
    """
    A cog that creates and manages anime-themed forum channels.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8675309, force_registration=True)
        
        # Default settings
        default_guild = {
            "resolution_tag_name": "Answered",
            "forum_command_prefix": ".",
            "forums_category_name": "Anime Discussions",
            "mention_message": "Hello there! If you want to discuss anime, please use one of our forum channels or create a new one with `.forum [anime name]`!",
            "default_tags": ["Discussion", "Question", "Recommendation", "Review", "Spoiler", "Fanart"]
        }
        
        self.config.register_guild(**default_guild)
        
    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def animeset(self, ctx):
        """Configure the Anime Forum Creator cog"""
        pass

    @animeset.command(name="prefix")
    async def set_prefix(self, ctx, prefix: str):
        """Set the prefix for forum commands (default '.')"""
        await self.config.guild(ctx.guild).forum_command_prefix.set(prefix)
        await ctx.send(f"Forum command prefix set to: {prefix}")

    @animeset.command(name="category")
    async def set_category(self, ctx, *, category_name: str):
        """Set the category name for anime forums"""
        await self.config.guild(ctx.guild).forums_category_name.set(category_name)
        await ctx.send(f"Anime forums category name set to: {category_name}")

    @animeset.command(name="tag")
    async def set_resolution_tag(self, ctx, *, tag_name: str):
        """Set the resolution tag name (default 'Answered')"""
        await self.config.guild(ctx.guild).resolution_tag_name.set(tag_name)
        await ctx.send(f"Resolution tag name set to: {tag_name}")

    @animeset.command(name="mentionmsg")
    async def set_mention_message(self, ctx, *, message: str):
        """Set the message sent when the bot is mentioned"""
        await self.config.guild(ctx.guild).mention_message.set(message)
        await ctx.send("Mention message has been updated.")
        
    @animeset.command(name="addtag")
    async def add_default_tag(self, ctx, *, tag_name: str):
        """Add a tag to the default forum tags"""
        async with self.config.guild(ctx.guild).default_tags() as tags:
            if tag_name in tags:
                await ctx.send(f"Tag '{tag_name}' already exists.")
                return
            tags.append(tag_name)
        await ctx.send(f"Added '{tag_name}' to default forum tags.")
        
    @animeset.command(name="removetag")
    async def remove_default_tag(self, ctx, *, tag_name: str):
        """Remove a tag from the default forum tags"""
        async with self.config.guild(ctx.guild).default_tags() as tags:
            if tag_name not in tags:
                await ctx.send(f"Tag '{tag_name}' doesn't exist.")
                return
            tags.remove(tag_name)
        await ctx.send(f"Removed '{tag_name}' from default forum tags.")

    @animeset.command(name="settings")
    async def show_settings(self, ctx):
        """Show current anime forum settings"""
        settings = await self.config.guild(ctx.guild).all()
        
        output = "**Anime Forum Creator Settings:**\n"
        for key, value in settings.items():
            if key == "default_tags":
                tags_str = ", ".join(value)
                output += f"**{key}:** {tags_str}\n"
            else:
                output += f"**{key}:** {value}\n"
        
        for page in pagify(output):
            await ctx.send(page)

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    async def forum(self, ctx, *, name: str):
        """Create a new anime forum channel in the configured category"""
        settings = await self.config.guild(ctx.guild).all()
        
        # Check if user has permission
        if not ctx.author.guild_permissions.manage_channels and not await ctx.bot.is_admin(ctx.author):
            await ctx.send("You don't have permission to create forums.")
            return
            
        # Check if the command prefix matches
        prefix = settings["forum_command_prefix"]
        if not ctx.message.content.startswith(f"{ctx.prefix}{ctx.command.name}"):
            return
            
        try:
            # Find or create the forums category
            category_name = settings["forums_category_name"]
            category = discord.utils.get(ctx.guild.categories, name=category_name)
            
            if not category:
                # Create the forums category if it doesn't exist
                category = await ctx.guild.create_category(category_name)
                
            # Prepare forum tags
            forum_tags = []
            # Add resolution tag first
            forum_tags.append(discord.ForumTag(name=settings["resolution_tag_name"]))
            
            # Add other default tags
            for tag_name in settings["default_tags"]:
                forum_tags.append(discord.ForumTag(name=tag_name))
            
            # Create the forum channel with anime-themed tags
            forum_channel = await ctx.guild.create_forum(
                name=name,
                category=category,
                topic=f"Discussion forum for {name}",
                reason=f"Anime forum requested by {ctx.author.display_name}"
            )
            
            # Add tags
            await forum_channel.edit(available_tags=forum_tags)
            
            # Set up guidelines for the forum
            guidelines = (
                f"# Welcome to the {name} Forum!\n\n"
                f"This is a place to discuss everything related to {name}.\n\n"
                f"## Guidelines:\n"
                f"- Use the **{settings['resolution_tag_name']}** tag when your question has been answered\n"
                f"- Mark spoilers appropriately using the **Spoiler** tag\n"
                f"- Be respectful to other fans\n"
                f"- Have fun discussing your favorite anime!"
            )
            
            await forum_channel.edit(topic=guidelines[:1024])  # Truncate to Discord's limit
            
            await ctx.send(f"Anime forum channel **{name}** has been created!")
            
        except Exception as e:
            await ctx.send(f"Error creating forum channel: {e}")

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    async def seasonal(self, ctx):
        """Create forum channels for current season anime"""
        settings = await self.config.guild(ctx.guild).all()
        
        # Check if user has permission
        if not ctx.author.guild_permissions.manage_channels and not await ctx.bot.is_admin(ctx.author):
            await ctx.send("You don't have permission to create forums.")
            return
            
        await ctx.send("Creating forums for seasonal anime. This may take a moment...")
        
        try:
            # Find or create the forums category
            category_name = f"Current Season Anime"
            category = discord.utils.get(ctx.guild.categories, name=category_name)
            
            if not category:
                # Create the category
                category = await ctx.guild.create_category(category_name)
                
            # Get current season anime (simplified version - in a real bot, you'd fetch this data from an API)
            seasonal_anime = [
                "Spy x Family",
                "Demon Slayer",
                "Jujutsu Kaisen",
                "My Hero Academia",
                "One Piece"
            ]
            
            created_forums = []
            
            for anime in seasonal_anime:
                # Check if forum already exists
                existing_channel = discord.utils.get(ctx.guild.channels, name=anime.lower().replace(" ", "-"))
                if existing_channel:
                    continue
                    
                # Prepare forum tags
                forum_tags = []
                # Add resolution tag first
                forum_tags.append(discord.ForumTag(name=settings["resolution_tag_name"]))
                
                # Add other default tags
                for tag_name in settings["default_tags"]:
                    forum_tags.append(discord.ForumTag(name=tag_name))
                
                # Create the forum 
                forum_channel = await ctx.guild.create_forum(
                    name=anime,
                    category=category,
                    topic=f"Discussion forum for {anime}",
                    reason=f"Seasonal anime forum requested by {ctx.author.display_name}"
                )
                
                # Add tags
                await forum_channel.edit(available_tags=forum_tags)
                
                created_forums.append(anime)
            
            if created_forums:
                await ctx.send(f"Created forums for: {', '.join(created_forums)}")
            else:
                await ctx.send("No new seasonal anime forums needed to be created.")
                
        except Exception as e:
            await ctx.send(f"Error creating seasonal anime forums: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
            
        # Get settings for this guild
        settings = await self.config.guild(message.guild).all()
        
        # Handle bot mention
        if self.bot.user in message.mentions and not message.mention_everyone:
            await message.channel.send(settings["mention_message"])
            
        # Handle thread interactions in forum channels
        if isinstance(message.channel, discord.Thread) and message.channel.parent:
            parent_channel = message.channel.parent
            
            # Check if parent is a forum channel
            if isinstance(parent_channel, discord.ForumChannel):
                # Auto-tag common anime terms in messages
                keywords = {
                    "spoiler": "Spoiler",
                    "fanart": "Fanart",
                    "recommend": "Recommendation",
                    "help": "Question"
                }
                
                content_lower = message.content.lower()
                
                # Get the solved tag if available
                answered_tag = None
                current_tags = message.channel.applied_tags
                new_tags = list(current_tags)
                
                for tag in parent_channel.available_tags:
                    # Look for keywords that would trigger auto-tagging
                    for keyword, tag_name in keywords.items():
                        if keyword in content_lower and tag.name == tag_name and tag not in new_tags:
                            new_tags.append(tag)
                            
                if len(new_tags) > len(current_tags):
                    try:
                        await message.channel.edit(applied_tags=new_tags)
                    except:
                        pass
                        
                # Check for command to mark as answered
                if message.content.startswith("!answered") or message.content.startswith("!solved"):
                    # Find the answered tag
                    answered_tag_name = settings["resolution_tag_name"]
                    answered_tag = None
                    
                    for tag in parent_channel.available_tags:
                        if tag.name == answered_tag_name:
                            answered_tag = tag
                            break
                            
                    if answered_tag and answered_tag not in new_tags:
                        new_tags.append(answered_tag)
                        
                        try:
                            await message.channel.edit(applied_tags=new_tags)
                            await message.add_reaction("✅")
                            try:
                                await message.delete()
                            except:
                                pass
                        except:
                            pass

async def setup(bot):
    await bot.add_cog(AnimeForumCreator(bot))
