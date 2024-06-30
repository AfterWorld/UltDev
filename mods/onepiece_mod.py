import discord
from redbot.core import commands, checks, Config, modlog
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
from redbot.core.utils.chat_formatting import pagify
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
import asyncio
import random
from datetime import timedelta

class OnePieceMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "bounties": {},
            "alliances": {},
            "transponder_snails": {},
            "banned_words": [],
            "raid_mode": False,
            "log_book": {},
            "timed_announcements": []
        }
        self.config.register_guild(**default_guild)
        self.log_channel_id = 1245208777003634698
        self.mute_role_id = 808869058476769312

    async def cog_unload(self):
        global original_commands
        for cmd_name, original_cmd in original_commands.items():
            self.bot.remove_command(cmd_name)
            if original_cmd:
                self.bot.add_command(original_cmd)

    @commands.command()
    async def modhelp(self, ctx):
        """Display information about OnePieceMod commands."""
        commands_info = {
            "kick": "Kick a crew member off the ship.\nUsage: `.kick @member [reason]`",
            "ban": "Banish a pirate to Impel Down.\nUsage: `.ban @member [days] [reason]`",
            "impeldown": "Temporarily banish a pirate.\nUsage: `.impeldown @member <days> [reason]`",
            "mute": "Silence a crew member.\nUsage: `.mute @member [duration] [reason]`",
            "unmute": "Remove Sea Prism handcuffs.\nUsage: `.unmute @member [reason]`",
            "addbounty": "Increase a pirate's bounty.\nUsage: `.addbounty @member <amount>`",
            "setbounty": "Set a pirate's bounty and generate a wanted poster.\nUsage: `.setbounty @member <amount>`",
            "raidmode": "Activate/deactivate Raid Mode.\nUsage: `.raidmode <true/false>`",
            "logbook": "Add a log book entry.\nUsage: `.logbook @member <entry>`",
            "viewlogbook": "View a pirate's log book.\nUsage: `.viewlogbook @member`",
            "promote": "Promote a crew member.\nUsage: `.promote @member @role`",
            "demote": "Demote a crew member.\nUsage: `.demote @member @role`",
            "calmbelt": "Enable slow mode in a channel.\nUsage: `.calmbelt <seconds>`",
            "redline": "Prevent new members from joining.\nUsage: `.redline`",
            "bustercall": "Delete multiple messages.\nUsage: `.bustercall <number>`",
            "seaking": "Set up auto-moderation.\nUsage: `.seaking <word1, word2, ...>`",
            "dendenmushi": "Schedule an announcement.\nUsage: `.dendenmushi HH:MM <message>`",
            "viewbounties": "View all pirates' bounties.\nUsage: `.viewbounties`",
            "alliance form": "Form a pirate alliance.\nUsage: `.alliance form <code>`",
            "alliance join": "Join a pirate alliance.\nUsage: `.alliance join <code>`",
            "alliance list": "List all alliances.\nUsage: `.alliance list`",
            "snailcall": "Send a message to allies.\nUsage: `.snailcall <alliance_code> <message>`",
            "snailbox": "Set up Transponder Snail box.\nUsage: `.snailbox <true/false>`",
        }

        def generate_embed(commands_subset):
            embed = discord.Embed(title="🏴‍☠️ OnePieceMod Command Guide", 
                                  description="Ahoy! Here's a list of available commands for managing your crew:",
                                  color=discord.Color.gold())
            for cmd, desc in commands_subset:
                embed.add_field(name=cmd, value=desc, inline=True)
            return embed

        command_groups = [list(commands_info.items())[i:i+6] for i in range(0, len(commands_info), 6)]
        pages = [generate_embed(group) for group in command_groups]

        await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command()
    @checks.admin_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Disrespecting the captain's orders!"):
        """Kick a crew member off the ship."""
        try:
            await ctx.guild.kick(member, reason=reason)
            await ctx.send(f"🦵 {member.name} has been kicked off the ship! They'll have to find another crew.")
            await self.log_action(ctx, member, "Kicked", reason)
            
            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="kick",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been logged in the ship's records. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to kick that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to kick that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.admin_or_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, days: int = 0, *, reason: str = "Mutiny against the crew!"):
        """Banish a pirate to Impel Down."""
        try:
            await ctx.guild.ban(member, reason=reason, delete_message_days=days)
            await ctx.send(f"⛓️ {member.name} has been banished to Impel Down for their crimes against the crew!")
            await self.log_action(ctx, member, "Banned", reason)
            
            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="ban",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The traitor's crimes have been recorded in the ship's log. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to banish that pirate!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to banish that pirate. The Marines must be jamming our signals!")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, duration: str = None, *, reason: str = "Speaking out of turn during a crew meeting!"):
        """Silence a crew member with Sea Prism handcuffs."""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            await ctx.send("The Mute role doesn't exist! We need to craft some Sea Prism handcuffs first.")
            return

        try:
            await member.add_roles(mute_role, reason=reason)
            await ctx.send(f"🔇 {member.name} has been silenced with Sea Prism handcuffs!")
            
            if duration:
                try:
                    duration_seconds = int(duration) * 60  # Convert minutes to seconds
                except ValueError:
                    await ctx.send("Invalid duration. Please provide a number of minutes.")
                    return
                await self.log_action(ctx, member, f"Muted for {duration} minutes", reason)
                await asyncio.sleep(duration_seconds)
                await self.unmute(ctx, member)
            else:
                await self.log_action(ctx, member, "Muted", reason)

            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="mute",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been recorded in the ship's log. Case number: {case.case_number}")

        except discord.Forbidden:
            await ctx.send("I don't have the authority to use Sea Prism handcuffs on that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to silence that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = "Sea Prism effect wore off"):
        """Remove Sea Prism handcuffs from a crew member."""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            await ctx.send("The Mute role doesn't exist! We can't remove non-existent Sea Prism handcuffs.")
            return

        if mute_role not in member.roles:
            await ctx.send(f"{member.name} is not muted. They're free to speak!")
            return

        try:
            await member.remove_roles(mute_role, reason=reason)
            await ctx.send(f"🔊 The Sea Prism effect has worn off. {member.name} can speak again!")
            await self.log_action(ctx, member, "Unmuted", reason)

            case = await modlog.create_case(
                ctx.bot, ctx.guild, ctx.message.created_at, action_type="unmute",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been recorded in the ship's log. Case number: {case.case_number}")

        except discord.Forbidden:
            await ctx.send("I don't have the authority to remove Sea Prism handcuffs from that crew member!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to unmute that crew member. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def addbounty(self, ctx, member: discord.Member, amount: int):
        """Increase a pirate's bounty."""
        async with self.config.guild(ctx.guild).bounties() as bounties:
            current_bounty = bounties.get(str(member.id), 0)
            new_bounty = current_bounty + amount
            bounties[str(member.id)] = new_bounty

        await ctx.send(f"🏴‍☠️ {member.name}'s bounty has increased by {amount} Berries! Their total bounty is now {new_bounty} Berries!")

        if new_bounty >= 500:  # Example threshold
            await ctx.send(f"⚠️ {member.name}'s bounty has exceeded 500 Berries! The Marines are on high alert!")

    async def generate_wanted_poster(self, member: discord.Member, bounty: int):
       async with aiohttp.ClientSession() as session:
            # Get the member's avatar
            async with session.get(str(member.avatar_url)) as resp:
                avatar_data = io.BytesIO(await resp.read())
            
            # Get the wanted poster template
            template_url = "https://raw.githubusercontent.com/AfterWorld/UltDev/main/mods/wanted%20poster/wanted_poster_template.png"
            async with session.get(template_url) as resp:
                template_data = io.BytesIO(await resp.read())
    
            # Open images
            template = Image.open(template_data)
            avatar = Image.open(avatar_data).resize((300, 300))
        
            # Paste the avatar onto the template
            template.paste(avatar, (100, 200))
        
            # Add text to the image
            draw = ImageDraw.Draw(template)
            font_url = "https://raw.githubusercontent.com/AfterWorld/UltDev/main/mods/wanted%20poster/one_piece_font.ttf"
            async with aiohttp.ClientSession() as session:
                async with session.get(font_url) as resp:
                    font_data = io.BytesIO(await resp.read())
            font = ImageFont.truetype(font_data, 60)
            draw.text((250, 550), member.name, font=font, fill=(0, 0, 0))
            draw.text((250, 650), f"{bounty:,} Berries", font=font, fill=(0, 0, 0))
        
            # Save the image to a buffer
            buffer = io.BytesIO()
            template.save(buffer, format='PNG')
            buffer.seek(0)
            return buffer
    
    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def raidmode(self, ctx, state: bool):
        """Activate or deactivate Raid Mode to defend against pirate invasions."""
        await self.config.guild(ctx.guild).raid_mode.set(state)
        if state:
            await ctx.send("🚨 Raid Mode activated! All hands on deck! Prepare to repel invaders!")
            # Here you could add code to change channel permissions, etc.
        else:
            await ctx.send("✅ Raid Mode deactivated. Stand down, crew. The danger has passed.")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def logbook(self, ctx, member: discord.Member, *, entry: str):
        """Add an entry to a pirate's log book."""
        async with self.config.guild(ctx.guild).log_book() as log_book:
            if str(member.id) not in log_book:
                log_book[str(member.id)] = []
            log_book[str(member.id)].append(entry)

        await ctx.send(f"📖 An entry has been added to {member.name}'s log book.")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def promote(self, ctx, member: discord.Member, role: discord.Role):
        """Promote a crew member to a new position."""
        try:
            await member.add_roles(role)
            await ctx.send(f"🎉 Congratulations, {member.name}! You've been promoted to {role.name}!")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to promote crew members!")

    @commands.command()
    @checks.admin_or_permissions(manage_roles=True)
    async def demote(self, ctx, member: discord.Member, role: discord.Role):
        """Demote a crew member from their position."""
        try:
            await member.remove_roles(role)
            await ctx.send(f"😔 {member.name} has been demoted from {role.name}. Better luck next time!")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to demote crew members!")

    @commands.command()
    @checks.admin_or_permissions(manage_channels=True)
    async def calmbelt(self, ctx, seconds: int):
        """Enable slow mode in a channel, simulating entering the Calm Belt."""
        try:
            await ctx.channel.edit(slowmode_delay=seconds)
            await ctx.send(f"⚓ We've entered the Calm Belt! Messages can only be sent every {seconds} seconds.")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to adjust the channel settings!")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def redline(self, ctx):
        """Prevent new members from joining, simulating reaching the Red Line."""
        try:
            await ctx.guild.edit(verification_level=discord.VerificationLevel.highest)
            await ctx.send("🚫 We've reached the Red Line! No new crew members can join until we cross it.")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to change server settings!")

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def bustercall(self, ctx, number: int):
        """Delete multiple messages at once, simulating a Buster Call operation."""
        deleted = await ctx.channel.purge(limit=number+1)  # +1 to include the command message
        await ctx.send(f"💥 Buster Call complete! {len(deleted)-1} messages have been annihilated.", delete_after=5)

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def seaking(self, ctx, *, banned_words):
        """Set up auto-moderation for specific words, themed as Sea Kings patrolling the waters."""
        banned_list = [word.strip() for word in banned_words.split(',')]
        await self.config.guild(ctx.guild).banned_words.set(banned_list)
        await ctx.send(f"🐉 Sea Kings are now patrolling for these words: {', '.join(banned_list)}")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def dendenmushi(self, ctx, time: str, *, message: str):
        """Schedule a timed announcement, themed as a Den Den Mushi broadcast."""
        try:
            hours, minutes = map(int, time.split(':'))
            if not (0 <= hours < 24 and 0 <= minutes < 60):
                raise ValueError
        except ValueError:
            await ctx.send("Invalid time format. Please use HH:MM.")
            return

        async with self.config.guild(ctx.guild).timed_announcements() as announcements:
            announcements.append({"time": time, "message": message})

        await ctx.send(f"📢 A Den Den Mushi broadcast has been scheduled for {time}.")

    @commands.group()
    @checks.admin_or_permissions(manage_guild=True)
    async def alliance(self, ctx):
        """Manage pirate alliances."""
        pass

    @alliance.command(name="form")
    async def alliance_form(self, ctx, ally_code: str):
        """Form an alliance with another server."""
        async with self.config.guild(ctx.guild).alliances() as alliances:
            alliances[ally_code] = {"name": ctx.guild.name, "id": ctx.guild.id}
        await ctx.send(f"Alliance formed! Other servers can now join using the code: {ally_code}")

    @alliance.command(name="join")
    async def alliance_join(self, ctx, ally_code: str):
        """Join an existing alliance."""
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            if ally_code in guild_data.get("alliances", {}):
                async with self.config.guild(ctx.guild).alliances() as alliances:
                    alliances[ally_code] = {"name": guild_data["alliances"][ally_code]["name"], "id": guild_id}
                await ctx.send(f"You've joined the alliance with {guild_data['alliances'][ally_code]['name']}!")
                return
        await ctx.send("Alliance not found. Check the code and try again.")

    @alliance.command(name="list")
    async def alliance_list(self, ctx):
        """List all alliances this server is part of."""
        alliances = await self.config.guild(ctx.guild).alliances()
        if not alliances:
            await ctx.send("This server is not part of any alliances.")
            return
        alliance_list = "\n".join([f"{code}: {data['name']}" for code, data in alliances.items()])
        await ctx.send(f"Current alliances:\n{alliance_list}")

    @commands.command()
    async def snailcall(self, ctx, alliance_code: str, *, message: str):
        """Send a Transponder Snail message to an allied server."""
        alliances = await self.config.guild(ctx.guild).alliances()
        if alliance_code not in alliances:
            await ctx.send("You're not in an alliance with that code.")
            return

        target_guild = self.bot.get_guild(alliances[alliance_code]["id"])
        if not target_guild:
            await ctx.send("Couldn't reach the allied server. The Transponder Snail connection failed.")
            return

        channel = discord.utils.get(target_guild.text_channels, name="transponder-snail")
        if not channel:
            channel = target_guild.system_channel or target_guild.text_channels[0]

        await channel.send(f"Transponder Snail Message from {ctx.guild.name}:\n{message}")
        await ctx.send("Your message has been transmitted through the Transponder Snail!")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def snailbox(self, ctx, status: bool):
        """Set up or disable a Transponder Snail box for incoming messages."""
        async with self.config.guild(ctx.guild).transponder_snails() as snails:
            snails["active"] = status
            if status:
                channel = discord.utils.get(ctx.guild.text_channels, name="transponder-snail")
                if not channel:
                    channel = await ctx.guild.create_text_channel("transponder-snail")
                snails["channel_id"] = channel.id
                await ctx.send(f"Transponder Snail box set up in {channel.mention}!")
            else:
                await ctx.send("Transponder Snail box has been deactivated.")

async def setup(bot):
    global original_commands
    cog = OnePieceMod(bot)

    command_names = ["kick", "ban", "mute", "unmute"]
    for cmd_name in command_names:
        original_cmd = bot.get_command(cmd_name)
        if original_cmd:
            original_commands[cmd_name] = original_cmd
            bot.remove_command(cmd_name)

    await bot.add_cog(cog)
    bot.loop.create_task(cog.check_timed_announcements())

async def teardown(bot):
    global original_commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
