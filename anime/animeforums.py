import asyncio
import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify
from typing import List, Dict, Optional
import aiohttp
import json


class AnimeForumCreator(commands.Cog):
    """
    A cog that creates and manages anime-themed forum channels for ongoing discussions.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=8675309, force_registration=True)
        self.session = aiohttp.ClientSession()
        
        # Default settings
        default_guild = {
            "forum_command_prefix": ".",
            "forums_category_name": "Anime Forums",
            "mention_message": "Hello there! If you want to discuss anime, please use one of our forum channels or create a new one with `.forum [anime name]`!",
            "default_tags": ["Discussion", "Question", "Recommendation", "Review", "Spoiler", "Fanart", "News", "Meme", "Seasonal", "Top Rated"],
            "auto_topic": True,
            "anime_api_url": "https://api.jikan.moe/v4",
            "use_mal_data": True,
            "default_post_guidelines": True
        }
        
        self.config.register_guild(**default_guild)
        
        # Cache for MyAnimeList data to avoid API rate limits
        self.anime_cache = {}
        
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        asyncio.create_task(self.session.close())
        
    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def animeset(self, ctx):
        """Configure the Anime Forum Creator cog"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

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
        
    @animeset.command(name="togglemaltopics")
    async def toggle_mal_topics(self, ctx):
        """Toggle using MyAnimeList data for forum topics"""
        current = await self.config.guild(ctx.guild).use_mal_data()
        await self.config.guild(ctx.guild).use_mal_data.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"Using MyAnimeList data for forum topics has been {state}.")
        
    @animeset.command(name="toggleguidelines")
    async def toggle_guidelines(self, ctx):
        """Toggle default post guidelines for new forums"""
        current = await self.config.guild(ctx.guild).default_post_guidelines()
        await self.config.guild(ctx.guild).default_post_guidelines.set(not current)
        state = "enabled" if not current else "disabled"
        await ctx.send(f"Default post guidelines for new forums has been {state}.")

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

    async def get_anime_info(self, anime_name: str) -> Optional[Dict]:
        """Fetch anime information from MyAnimeList via Jikan API"""
        if anime_name in self.anime_cache:
            return self.anime_cache[anime_name]
            
        try:
            settings = await self.config.guild_from_id(1).all()  # Using a dummy guild ID to get settings
            base_url = settings.get("anime_api_url", "https://api.jikan.moe/v4")
            
            async with self.session.get(f"{base_url}/anime", params={"q": anime_name, "limit": 1}) as resp:
                if resp.status != 200:
                    return None
                    
                data = await resp.json()
                
                if not data.get("data") or len(data["data"]) == 0:
                    return None
                    
                anime_data = data["data"][0]
                
                # Cache the result
                self.anime_cache[anime_name] = {
                    "id": anime_data.get("mal_id"),
                    "title": anime_data.get("title"),
                    "synopsis": anime_data.get("synopsis"),
                    "genres": [genre["name"] for genre in anime_data.get("genres", [])],
                    "image_url": anime_data.get("images", {}).get("jpg", {}).get("image_url"),
                    "episodes": anime_data.get("episodes"),
                    "score": anime_data.get("score"),
                    "url": anime_data.get("url")
                }
                
                return self.anime_cache[anime_name]
                
        except Exception as e:
            print(f"Error fetching anime info: {e}")
            return None

    async def create_forum_channel(self, guild, name: str, category=None, anime_data=None, is_seasonal=False, is_top_rated=False):
        """Create a forum channel with optimized settings"""
        settings = await self.config.guild(guild).all()
        
        # Prepare forum tags
        forum_tags = []
        
        # Add special tags based on type
        if is_seasonal:
            seasonal_tag = discord.ForumTag(name="Seasonal")
            forum_tags.append(seasonal_tag)
            
        if is_top_rated:
            top_rated_tag = discord.ForumTag(name="Top Rated")
            forum_tags.append(top_rated_tag)
        
        # Add default tags
        for tag_name in settings["default_tags"]:
            # Skip the tags we already added
            if (tag_name == "Seasonal" and is_seasonal) or (tag_name == "Top Rated" and is_top_rated):
                continue
            forum_tags.append(discord.ForumTag(name=tag_name))
            
        # Add genre tags if available
        if anime_data and anime_data.get("genres"):
            for genre in anime_data["genres"][:10]:  # Limit to 10 genres
                if genre not in settings["default_tags"]:
                    forum_tags.append(discord.ForumTag(name=genre))
        
        # Create guidelines for the forum
        if settings["default_post_guidelines"]:
            if anime_data:
                guidelines = (
                    f"# {anime_data['title']}\n\n"
                    f"{anime_data['synopsis'][:500]}...\n\n"
                    f"## Guidelines:\n"
                    f"- Be respectful to other fans\n"
                    f"- Mark spoilers appropriately\n"
                    f"- Keep discussions on-topic\n"
                    f"- Have fun discussing your favorite anime!\n\n"
                    f"[MyAnimeList Page]({anime_data['url']})"
                )
            else:
                guidelines = (
                    f"# Welcome to the {name} Forum!\n\n"
                    f"This is a place to discuss everything related to {name}.\n\n"
                    f"## Guidelines:\n"
                    f"- Be respectful to other fans\n"
                    f"- Mark spoilers appropriately\n"
                    f"- Keep discussions on-topic\n"
                    f"- Have fun discussing your favorite anime!"
                )
        else:
            guidelines = f"Discussion forum for {name}"
            
        # Create the forum channel
        forum_channel = await guild.create_forum(
            name=name,
            category=category,
            topic=guidelines[:1000],  # Discord's limit
            reason=f"Anime forum"
        )
        
        # Set the available tags
        await forum_channel.edit(available_tags=forum_tags)
        
        # Set suggested format if using MyAnimeList data
        if anime_data and settings["use_mal_data"]:
            # Create guidelines format that encourages structured discussions
            suggested_format = (
                f"**Topic**: \n\n"
                f"**Episodes Covered**: \n\n"
                f"**Discussion Points**: \n\n"
                f"**Rating**: /10\n\n"
                f"**Thoughts**: "
            )
            await forum_channel.edit(default_thread_slowmode_delay=0)
            
            # Set auto-archive to maximum
            await forum_channel.edit(default_auto_archive_duration=4320)  # 3 days in minutes
        
        return forum_channel

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
            
        async with ctx.typing():
            try:
                # Status message
                status_msg = await ctx.send(f"Creating forum for **{name}**... Gathering anime information...")
                
                # Find or create the forums category
                category_name = settings["forums_category_name"]
                category = discord.utils.get(ctx.guild.categories, name=category_name)
                
                if not category:
                    # Create the forums category if it doesn't exist
                    category = await ctx.guild.create_category(category_name)
                
                # Get anime info if enabled
                anime_data = None
                if settings["use_mal_data"]:
                    anime_data = await self.get_anime_info(name)
                    if anime_data:
                        await status_msg.edit(content=f"Creating forum for **{anime_data['title']}**... Setting up forum...")
                    
                # Create the forum
                forum_channel = await self.create_forum_channel(ctx.guild, name, category, anime_data)
                
                # Send completion message with anime thumbnail if available
                if anime_data and anime_data.get("image_url"):
                    embed = discord.Embed(
                        title=f"Forum Created: {anime_data['title']}",
                        url=forum_channel.jump_url,
                        description=f"A new anime forum has been created for {anime_data['title']}!",
                        color=discord.Color.blue()
                    )
                    embed.set_thumbnail(url=anime_data["image_url"])
                    embed.add_field(name="Episodes", value=anime_data.get("episodes", "Unknown"), inline=True)
                    embed.add_field(name="Score", value=f"{anime_data.get('score', 'N/A')}/10", inline=True)
                    embed.add_field(name="Genres", value=", ".join(anime_data.get("genres", ["Unknown"])[:3]), inline=True)
                    
                    await status_msg.delete()
                    await ctx.send(embed=embed)
                else:
                    await status_msg.edit(content=f"Anime forum channel **{name}** has been created!")
                
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
            
        status_msg = await ctx.send("Gathering information about seasonal anime. This may take a moment...")
        
        try:
            # Find or create the forums category
            category_name = settings["forums_category_name"]
            category = discord.utils.get(ctx.guild.categories, name=category_name)
            
            if not category:
                # Create the category
                category = await ctx.guild.create_category(category_name)
                
            # Get current season anime from Jikan API
            try:
                base_url = settings.get("anime_api_url", "https://api.jikan.moe/v4")
                async with self.session.get(f"{base_url}/seasons/now") as resp:
                    if resp.status != 200:
                        await status_msg.edit(content="Error accessing anime API. Using fallback list.")
                        seasonal_anime = ["Spy x Family", "Demon Slayer", "Jujutsu Kaisen", "My Hero Academia", "One Piece"]
                    else:
                        data = await resp.json()
                        seasonal_anime = []
                        
                        # Sort by popularity (members)
                        sorted_anime = sorted(data.get("data", []), key=lambda x: x.get("members", 0), reverse=True)
                        
                        # Take top 15 most popular anime
                        for anime in sorted_anime[:15]:
                            title = anime.get("title")
                            if title:
                                seasonal_anime.append(title)
                                # Cache the result
                                self.anime_cache[title] = {
                                    "id": anime.get("mal_id"),
                                    "title": title,
                                    "synopsis": anime.get("synopsis", ""),
                                    "genres": [genre["name"] for genre in anime.get("genres", [])],
                                    "image_url": anime.get("images", {}).get("jpg", {}).get("image_url"),
                                    "episodes": anime.get("episodes"),
                                    "score": anime.get("score"),
                                    "url": anime.get("url")
                                }
            except Exception as e:
                await status_msg.edit(content=f"Error accessing anime API: {e}. Using fallback list.")
                seasonal_anime = ["Spy x Family", "Demon Slayer", "Jujutsu Kaisen", "My Hero Academia", "One Piece"]
            
            await status_msg.edit(content=f"Creating forums for {len(seasonal_anime)} seasonal anime...")
            
            created_forums = []
            existing_forums = []
            
            for index, anime in enumerate(seasonal_anime):
                # Update status every 3 anime
                if index % 3 == 0:
                    await status_msg.edit(content=f"Creating forums for seasonal anime... ({index}/{len(seasonal_anime)})")
                
                # Check if forum already exists (case insensitive)
                existing_channel = discord.utils.find(
                    lambda c: c.name.lower() == anime.lower().replace(" ", "-"),
                    ctx.guild.channels
                )
                
                if existing_channel:
                    existing_forums.append(anime)
                    continue
                
                # Get cached anime data
                anime_data = self.anime_cache.get(anime)
                
                # Create the forum
                try:
                    await self.create_forum_channel(ctx.guild, anime, category, anime_data, is_seasonal=True)
                    created_forums.append(anime)
                    
                    # Sleep to avoid rate limits
                    await asyncio.sleep(1.5)
                except Exception as e:
                    print(f"Error creating forum for {anime}: {e}")
            
            # Final message
            message = []
            if created_forums:
                message.append(f"Created {len(created_forums)} seasonal anime forums!")
            if existing_forums:
                message.append(f"{len(existing_forums)} forums already existed.")
                
            await status_msg.edit(content="\n".join(message))
                
        except Exception as e:
            await status_msg.edit(content=f"Error creating seasonal anime forums: {e}")

    @commands.command()
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    async def toptier(self, ctx):
        """Create forum channels for top-rated anime"""
        settings = await self.config.guild(ctx.guild).all()
        
        # Check if user has permission
        if not ctx.author.guild_permissions.manage_channels and not await ctx.bot.is_admin(ctx.author):
            await ctx.send("You don't have permission to create forums.")
            return
            
        status_msg = await ctx.send("Gathering information about top-rated anime. This may take a moment...")
        
        try:
            # Find or create the forums category
            category_name = settings["forums_category_name"]
            category = discord.utils.get(ctx.guild.categories, name=category_name)
            
            if not category:
                # Create the category
                category = await ctx.guild.create_category(category_name)
                
            # Get top anime from Jikan API
            try:
                base_url = settings.get("anime_api_url", "https://api.jikan.moe/v4")
                async with self.session.get(f"{base_url}/top/anime", params={"limit": 15}) as resp:
                    if resp.status != 200:
                        await status_msg.edit(content="Error accessing anime API. Using fallback list.")
                        top_anime = ["Fullmetal Alchemist: Brotherhood", "Steins;Gate", "Hunter x Hunter", "Attack on Titan", "Gintama"]
                    else:
                        data = await resp.json()
                        top_anime = []
                        
                        for anime in data.get("data", [])[:15]:
                            title = anime.get("title")
                            if title:
                                top_anime.append(title)
                                # Cache the result
                                self.anime_cache[title] = {
                                    "id": anime.get("mal_id"),
                                    "title": title,
                                    "synopsis": anime.get("synopsis", ""),
                                    "genres": [genre["name"] for genre in anime.get("genres", [])],
                                    "image_url": anime.get("images", {}).get("jpg", {}).get("image_url"),
                                    "episodes": anime.get("episodes"),
                                    "score": anime.get("score"),
                                    "url": anime.get("url")
                                }
            except Exception as e:
                await status_msg.edit(content=f"Error accessing anime API: {e}. Using fallback list.")
                top_anime = ["Fullmetal Alchemist: Brotherhood", "Steins;Gate", "Hunter x Hunter", "Attack on Titan", "Gintama"]
            
            await status_msg.edit(content=f"Creating forums for {len(top_anime)} top-rated anime...")
            
            created_forums = []
            existing_forums = []
            
            for index, anime in enumerate(top_anime):
                # Update status every 3 anime
                if index % 3 == 0:
                    await status_msg.edit(content=f"Creating forums for top anime... ({index}/{len(top_anime)})")
                
                # Check if forum already exists
                existing_channel = discord.utils.find(
                    lambda c: c.name.lower() == anime.lower().replace(" ", "-"),
                    ctx.guild.channels
                )
                
                if existing_channel:
                    existing_forums.append(anime)
                    continue
                
                # Get cached anime data
                anime_data = self.anime_cache.get(anime)
                
                # Create the forum
                try:
                    await self.create_forum_channel(ctx.guild, anime, category, anime_data, is_top_rated=True)
                    created_forums.append(anime)
                    
                    # Sleep to avoid rate limits
                    await asyncio.sleep(1.5)
                except Exception as e:
                    print(f"Error creating forum for {anime}: {e}")
            
            # Final message
            message = []
            if created_forums:
                message.append(f"Created {len(created_forums)} top-rated anime forums!")
            if existing_forums:
                message.append(f"{len(existing_forums)} forums already existed.")
                
            await status_msg.edit(content="\n".join(message))
                
        except Exception as e:
            await status_msg.edit(content=f"Error creating top anime forums: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle messages in forum channels"""
        if message.author.bot or not message.guild:
            return
            
        # Get settings for this guild
        settings = await self.config.guild(message.guild).all()
        
        # Handle bot mention
        if self.bot.user in message.mentions and not message.mention_everyone:
            await message.channel.send(settings["mention_message"])
            
        # Handle forum thread interaction
        if isinstance(message.channel, discord.Thread) and message.channel.parent:
            parent_channel = message.channel.parent
            
            # Check if parent is a forum channel
            if isinstance(parent_channel, discord.ForumChannel):
                # Auto-tag based on content
                content_lower = message.content.lower()
                keywords = {
                    "spoiler": "Spoiler",
                    "fanart": "Fanart", 
                    "recommend": "Recommendation",
                    "help": "Question",
                    "news": "News",
                    "meme": "Meme",
                    "review": "Review"
                }
                
                current_tags = message.channel.applied_tags
                new_tags = list(current_tags)
                tag_added = False
                
                # Look for keywords to auto-tag
                for tag in parent_channel.available_tags:
                    for keyword, tag_name in keywords.items():
                        # Check if keyword is in message and tag not already applied
                        if keyword in content_lower and tag.name == tag_name and tag not in new_tags:
                            new_tags.append(tag)
                            tag_added = True
                
                # Update tags if needed
                if tag_added and len(new_tags) > len(current_tags):
                    try:
                        await message.channel.edit(applied_tags=new_tags)
                    except:
                        pass

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        """Enhance new threads in anime forums"""
        # Check if thread parent is a forum channel
        if not isinstance(thread.parent, discord.ForumChannel):
            return
            
        # Only process if in anime category
        settings = await self.config.guild(thread.guild).all()
        anime_category_names = [
            settings["forums_category_name"],
            settings["seasonal_category_name"],
            "Top Tier Anime"
        ]
        
        category_name = thread.parent.category.name if thread.parent.category else None
        
        if not category_name or category_name not in anime_category_names:
            return
            
        # Give the thread starter a welcoming message
        try:
            # Find anime name from forum name
            anime_name = thread.parent.name.replace("-", " ").title()
            
            # Create a welcoming message
            welcome_message = (
                f"Welcome to the discussion about **{thread.name}**!\n\n"
                f"Feel free to share your thoughts, theories, favorite moments, or questions about {anime_name}.\n\n"
                f"Remember to use tags to help others find your thread. Enjoy your discussion!"
            )
            
            # Send the message
            await thread.send(welcome_message)
        except Exception as e:
            print(f"Error sending welcome message to new thread: {e}")

async def setup(bot):
    await bot.add_cog(AnimeForumCreator(bot))
