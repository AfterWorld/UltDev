import discord
from discord.errors import Forbidden, HTTPException
from redbot.core import commands, checks, modlog, Config
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta
from redbot.core.utils.mod import get_audit_reason
from redbot.core.bot import Red
from datetime import timedelta, datetime, timezone
import asyncio
import re
import random
import pytz
import logging
from typing import Optional, List, Union, Dict

original_commands = {}

class MuteTime(commands.Converter):
    async def convert(self, ctx, argument):
        matches = re.match(r"(\d+)\s*(m(?:in(?:ute)?s?)?|h(?:ours?)?|d(?:ays?)?|w(?:eeks?)?)?$", argument.lower())
        if matches:
            time = int(matches.group(1))
            unit = matches.group(2) or 'm'
            if unit.startswith('m'):
                return {"duration": timedelta(minutes=time), "reason": None}
            elif unit.startswith('h'):
                return {"duration": timedelta(hours=time), "reason": None}
            elif unit.startswith('d'):
                return {"duration": timedelta(days=time), "reason": None}
            elif unit.startswith('w'):
                return {"duration": timedelta(weeks=time), "reason": None}
        return {"duration": None, "reason": argument}

class OnePieceMod(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.mute_tasks = {}
        default_guild = {
            "general_channel_id": None,
            "main_server_id": None,
            "muted_users": {},
            "restricted_channels": {},
            "minimum_image_role_id": None,
            "warned_users": {},
            "mute_role": None,
            "notification_channel": None,
            "default_time": 0,
            "dm": False,
            "show_mod": False,
        }
        default_member = {
            "nword_offenses": 0,
            "last_offense_time": None
        }
        self.config.register_member(**default_member)
        self.config.register_guild(**default_guild)
        self.mute_role_cache = {}
        self.log_channel_id = 1245208777003634698  # Make sure this is set to your actual log channel ID
        self.mute_role_id = 808869058476769312  # Pre-set mute role ID
        self.general_chat_id = 425068612542398476
        self.default_mute_time = timedelta(hours=24)  # Default mute time of 24 hours
        self.muted_users = {}  # Store muted users' roles
        self.reminder_task = None
        self.nword_pattern = re.compile(r'\bn[i!1l]+[g6b4]+[e3a4]+r?s?\b|\bn[i!1l]+[g6b4]+[a@4]+s?\b', re.IGNORECASE)
        self.logger = logging.getLogger('red.onepiece_mod')
        self.logger.setLevel(logging.DEBUG)
        self.ban_messages = [
            ("Looks like you're taking a trip to Impel Down!", "https://tenor.com/view/one-piece-magellan-magellan-one-piece-impel-down-gif-24849283"),
            ("You've been hit by Nami's Clima-Tact!", "https://tenor.com/view/nami-sanji-slap-one-piece-anime-gif-19985101"),
            ("Zoro got lost again, and somehow you got banned!", "https://tenor.com/view/onepiece-zoro-gif-20413728"),
            ("You've been Gum-Gum Banned!", "https://tenor.com/view/luffy-punch-onepiece-gif-11908462"),
            ("Sanji's kicking you out of the crew!", "https://tenor.com/view/sanji-one-piece-angry-flame-gif-5738862"),
            ("You've been caught in Trafalgar Law's ROOM!", "https://tenor.com/view/room-law-trafalgar-law-shambles-big-mom-gif-26718981"),
            ("Blackbeard's darkness has swallowed you!", "https://tenor.com/view/one-piece-anime-blackbeard-marshall-d-teach-gif-19895866"),
            ("You've been frozen by Aokiji's Ice Age!", "https://tenor.com/view/one-piece-kuzan-aokoji-freeze-charlotte-cracker-gif-15455402913382101990"),
            ("Buggy's Chop-Chop Fruit sent you flying!", "https://tenor.com/view/bara-bara-no-mi-bara-bara-no-mi-o-grande-one-piece-rp-gif-22513624"),
            ("Big Mom's Soul-Soul Fruit has taken your lifespan... and your server access!", "https://tenor.com/view/%E5%A4%A7%E5%AA%BDauntie-aunt-granny-grandmom-gif-12576437")
        ]

    def parse_timedelta(self, time_string: str) -> timedelta:
        match = re.match(r"(\d+)([dwhms])", time_string.lower())
        if not match:
            raise ValueError("Invalid time format")
        
        amount, unit = match.groups()
        amount = int(amount)
        
        if unit == 'd':
            return timedelta(days=amount)
        elif unit == 'm':
            return timedelta(minutes=amount)
        elif unit == 's':
            return timedelta(seconds=amount)
        elif unit == 'w':
            return timedelta(weeks=amount)
        elif unit == 'h':
            return timedelta(hours=amount)
        

    async def initialize(self):
        self.reminder_task = self.bot.loop.create_task(self.send_periodic_reminder())
        self.logger.info("Reminder task initialized")

    def cog_unload(self):
        if self.reminder_task:
            self.reminder_task.cancel()
        self.logger.info("Reminder task unloaded")

    async def is_allowed_by_hierarchy(
        self, guild: discord.Guild, mod: discord.Member, user: discord.Member
    ):
        is_special = mod == guild.owner or await self.bot.is_owner(mod)
        return mod.top_role > user.top_role or is_special

    async def _send_dm_notification(
        self,
        user: Union[discord.User, discord.Member],
        moderator: Union[discord.User, discord.Member],
        guild: discord.Guild,
        action: str,
        reason: Optional[str],
        duration: Optional[timedelta] = None
    ):
        if user.bot:
            return

        if not await self.config.guild(guild).dm():
            return

        show_mod = await self.config.guild(guild).show_mod()
        title = f"🏴‍☠️ {action} 🏴‍☠️"
        
        if duration:
            duration_str = humanize_timedelta(timedelta=duration)
            until = datetime.now(timezone.utc) + duration
            until_str = discord.utils.format_dt(until)

        moderator_str = str(moderator) if show_mod else "A mysterious pirate captain"

        if not reason:
            reason = "No reason provided, ye scurvy dog!"

        message = f"{title}\n\n"
        message += f"**Reason:** {reason}\n"
        if show_mod:
            message += f"**Enforcing Officer:** {moderator_str}\n"
        if duration:
            message += f"**Duration:** {duration_str}\n"
            message += f"**Until:** {until_str}\n"
        message += f"**Crew:** {guild.name}"

        try:
            await user.send(message)
        except discord.Forbidden:
            pass  # Cannot send DM to the user

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setgeneralchannel(self, ctx, channel: discord.TextChannel):
        """Set the general channel for reminders."""
        await self.config.guild(ctx.guild).general_channel_id.set(channel.id)
        await self.config.guild(ctx.guild).main_server_id.set(ctx.guild.id)
        await ctx.send(f"General channel set to {channel.mention} and this server set as the main server for reminders.")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def testreminder(self, ctx):
        """Test the reminder system by sending a random reminder."""
        main_server_id = await self.config.guild(ctx.guild).main_server_id()
        if ctx.guild.id != main_server_id:
            return await ctx.send("This command can only be used in the main server.")

        general_channel_id = await self.config.guild(ctx.guild).general_channel_id()
        if not general_channel_id:
            return await ctx.send("The general channel hasn't been set. Use `setgeneralchannel` first.")

        channel = ctx.guild.get_channel(general_channel_id)
        if not channel:
            return await ctx.send("The set general channel could not be found. Please set it again.")

        reminder = self.get_random_reminder()
        await channel.send(reminder)
        await ctx.send("Test reminder sent successfully!")

    async def send_periodic_reminder(self):
        await self.bot.wait_until_ready()
        self.logger.info("Starting periodic reminder task")
        
        while not self.bot.is_closed():
            try:
                main_server_id = await self.config.guild(self.bot.guilds[0]).main_server_id()
                if not main_server_id:
                    self.logger.warning("Main server ID not set. Skipping reminder.")
                    await asyncio.sleep(300)  # Wait 5 minutes before trying again
                    continue

                guild = self.bot.get_guild(main_server_id)
                if not guild:
                    self.logger.error(f"Main server with ID {main_server_id} not found.")
                    await asyncio.sleep(300)  # Wait 5 minutes before trying again
                    continue

                general_channel_id = await self.config.guild(guild).general_channel_id()
                if not general_channel_id:
                    self.logger.warning(f"No general channel set for main server {guild.name}")
                    await asyncio.sleep(300)  # Wait 5 minutes before trying again
                    continue

                channel = guild.get_channel(general_channel_id)
                if channel:
                    reminder = self.get_random_reminder()
                    await channel.send(reminder)
                    self.logger.info(f"Reminder sent to {guild.name}: {reminder[:30]}...")
                else:
                    self.logger.error(f"General channel not found in main server {guild.name}")

                # Fixed delay of 30 minutes
                delay = 30 * 60  # 30 minutes in seconds
                self.logger.debug(f"Waiting for {delay} seconds before next reminder")
                await asyncio.sleep(delay)
            
            except discord.errors.HTTPException as e:
                self.logger.error(f"HTTP error when sending reminder: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error in reminder task: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before trying again

    def get_random_reminder(self):
        reminder_messages = [
            "# 🏴‍☠️ __**Luffy's Gum-Gum Decree!**__ 🏴‍☠️\n> Shishishi! Listen up, crew!\n> **Keep spoilers out of the general chat,\n> or I'll use my Gear Fifth to bounce you outta here!** 🦹‍♂️",
            
            "# ⚓ __**Nami's Navigational Notice:**__ ⚓\n> The Pirate Code (server rules) is our map to treasure!\n> **Follow it, or you'll face my Thunderbolt Tempo! ⚡\n> Breaking rules costs 1,000,000 berries per offense!** 🗺️💰",
            
            "# 🗡️ __**Zoro's Three-Sword Style: Rule Slash!**__ 🗡️\n> Lost? The rules are that way! No, wait...\n> **Keep discussions on-topic or face my Onigiri ban technique!\n> And don't make me come find you!** 🌪️",
            
            "# 👨‍🍳 __**Sanji's Recipe for Respect:**__ 👨‍🍳\n> In this kitchen, we serve up equality for all!\n> **Discriminate, and you'll taste my Diable Jambe kick!\n> Treat everyone like they're the All Blue of nakama!** 🦵🔥",
            
            "# 🩺 __**Chopper's Medical Advisory:**__ 🩺\n> Doctor's orders: Be nice to each other!\n> **Bullying causes bad health conditions.\n> Don't make me use my Monster Point to enforce kindness!** 🦌",
            
            "# 🎸 __**Brook's Soul-ful Serenade:**__ 🎸\n> Yohohoho! Let's keep it melodious, shall we?\n> **No jarring language or discord in our crew's symphony.\n> Or I'll have to silence you with my Soul Solid!** 💀🎵",
            
            "# 🛠️ __**Franky's SUPER Server Upgrade:**__ 🛠️\n> Keep this server running SUPER smooth!\n> **Use the right channels or I'll Radical Beam you outta here!\n> It's not hard, bros! Channel organization is SUPER!** 🦾",
            
            "# 📚 __**Robin's Historical Perspective:**__ 📚\n> The past teaches us to respect each other.\n> **Treat every nakama with kindness, regardless of background.\n> Or I might just sprout some hands to show you out!** 🌸",
            
            "# 🎯 __**Usopp's 8000-Follower Challenge:**__ 🎯\n> The Great Captain Usopp decrees:\n> **Follow the rules or face my 5-Ton Hammer of Justice!\n> I once moderated a server of 8000 giants, you know!** 🐉",
            
            "# 🦈 __**Jinbe's Fishman Karate Discipline:**__ 🦈\n> Respect flows like water in our crew.\n> **Disrupt that flow, and you'll face my Vagabond Drill!\n> We sink or swim together, so play nice!** 🌊",
            
            "# 📜 __**Oden's Spoiler Scroll:**__ 📜\n> The secrets of Laugh Tale are less guarded than our spoilers!\n> **Keep new chapter talk in designated channels,\n> or you'll be boiled alive... in a ban!** 🍢🔥",
            
            "# 🕰️ __**Toki's Spoiler Time-Jump:**__ 🕰️\n> I've seen the future, and it's spoiler-free for 48 hours!\n> **No spoilers for 2 days after a new release,\n> or I'll send you 800 years into a ban!** ⏳",
            
            "# 👁️ __**Katakuri's Spoiler Mochi:**__ 👁️\n> My future sight predicts perfect spoiler etiquette.\n> **Use spoiler tags for manga content not in the anime,\n> or get stuck in my mochi and miss the next chapter!** 🍡",
            
            "# 📰 __**Morgans' Spoiler Scoop:**__ 📰\n> Wanna share the big news? Hold your News Coos!\n> **Chapter discussions stay in dedicated threads.\n> Spread spoilers elsewhere and you're Fake News!** 🐦",
            
            "# 🎨 __**Kanjuro's Spoiler Scroll:**__ 🎨\n> Your excitement is art, but don't betray our nakama!\n> **Be vague in titles and thumbnails about recent events.\n> Explicit spoilers will be erased like a bad drawing!** 🖌️",
            
            "# 🍖 __**Luffy's Meat Mandate:**__ 🍖\n> Sharing is caring, but not with spoilers!\n> **If Sanji won't give me meat for spoiling, neither will the mods!\n> Keep surprises as safe as my lunchbox!** 🥩",
            
            "# 🃏 __**Law's ROOM: Spoiler Swap:**__ 🃏\n> I can transplant anything, except your right to spoil.\n> **Use ROOM to keep spoilers contained.\n> Shambles them elsewhere and you'll lose your posting privileges!** ⚔️",
            
            "# 🦩 __**Bon Clay's Spoiler Face-Off:**__ 🦩\n> Un, Deux, Trois! Disguise those spoilers!\n> **Use the same care hiding spoilers as I do impersonating friends.\n> Reveal too much and face my Mane Mane No Mi punishment!** 💃",
            
            "# 🍩 __**Katakuri's Mochi Muzzle:**__ 🍩\n> I'll say this once, so listen up!\n> **Spoilers are like mochi - keep 'em wrapped up tight.\n> Let 'em loose, and I'll personally muzzle you!** 🤐",
            
            "# 🔥 __**Ace's Flame of Consideration:**__ 🔥\n> The fire of excitement burns bright, but don't let it burn others!\n> **Cool your jets and avoid spoiling for nakama still catching up.\n> Or you might find yourself in a Fire Fist timeout!** 🕯️",
            
            "# 🐉 __**Dragon's Revolutionary Spoiler Tactics:**__ 🐉\n> Even revolutionaries know some secrets must be kept.\n> **Contain your spoilers like we contain our plans.\n> Loose lips sink revolutionary ships... and get bans.** 🌪️",
            
            "# 🍜 __**Garp's Fist of Spoiler Love:**__ 🍜\n> Listen here, you cheeky sea pups!\n> **Keep your spoilers to yourself, or I'll give you a Fist of Love!\n> Grandpa's orders are absolute!** 👊💕",
            
            "# ☠️ __**Whitebeard's One Server Policy:**__ ☠️\n> In this era of ours, all spoilers should be marked!\n> **Fail to tag your spoilers, and you'll feel the tremors of a ban.\n> This server is my family, so play nice!** 🌋",
        
            "# 🎩 __**Sabo's Noble Spoiler Oath:**__ 🎩\n> I vow upon my restored memories:\n> **All users shall enjoy One Piece at their own pace!\n> Spoil for others and you'll taste revolutionary flames!** 🔥",
        
            # New rules start here
            "# 🦁 __**Shanks' Conqueror's Warning:**__ 🦁\n> Let's keep this server as peaceful as the Red Force.\n> **Respect others or face the pressure of my Conqueror's Haki!\n> I didn't lose an arm teaching Luffy for nothing!** 👑",
        
            "# 🌺 __**Hancock's Love-Love Moderation:**__ 🌺\n> Breaking rules is utterly unbeautiful!\n> **Treat all members with respect, regardless of gender.\n> Or you'll be turned to stone and used as a server decoration!** 💘",
        
            "# 🦊 __**Carrot's Sulong Surveillance:**__ 🦊\n> Garchu! Let's keep this server hopping with positivity!\n> **No aggressive behavior when the full moon of conflict rises.\n> Or I'll use my Sulong form to bounce you out!** 🌕",
        
            "# 🍩 __**Aokiji's Chilly Chat Policy:**__ 🍩\n> Let's keep it cool, yeah?\n> **No heated arguments or flame wars in the chat.\n> Or I'll put you on ice for a bit. Ice Time!** ❄️",
        
            "# 🌋 __**Akainu's Absolute Justice Enforcement:**__ 🌋\n> The rules of this server are absolute justice!\n> **Break them, and you'll face the consequences.\n> My Magu Magu no Mi doesn't discriminate against rule-breakers.** 🔥",
        
            "# 🦜 __**Marco's Phoenix Moderation:**__ 🦜\n> Yoi, let's keep this server healthy and regenerating, eh?\n> **Spread positivity and help others.\n> My flames heal, but they can also ban if necessary.** 🔵🔥",
        
            "# 🐊 __**Crocodile's Desert Decree:**__ 🐊\n> This server should run as smoothly as desert sand.\n> **No gritty behavior or I'll use my Suna Suna no Mi.\n> I'll dry up your posting privileges faster than you can say Alabasta!** 🏜️",
        
            "# 🎭 __**Buggy's Flashy Rule Announcement:**__ 🎭\n> Listen up, you flashy bastards!\n> **Follow the rules or I'll separate you from the server!\n> Captain Buggy's orders are as absolute as they are flashy!** 🔪",
        
            "# 🦈 __**Arlong's Prejudice Prevention:**__ 🦈\n> In this crew, all races swim together!\n> **No species discrimination allowed, human or fishman.\n> Or I'll show you how a saw-shark deals with bigots!** 🔪",
        
            "# 🎋 __**Yamato's Inherited Will of Order:**__ 🎋\n> As Oden, I decree these rules for our server!\n> **Respect each other's freedom and dreams.\n> Break these rules and you'll face my Thunder Bagua!** ⚡",
        
            "# 🗡️ __**Mihawk's Keen-Eyed Moderation:**__ 🗡️\n> My eyes miss nothing in this server.\n> **Keep your behavior as sharp and disciplined as a black blade.\n> Or face the world's strongest ban.** 👁️",
        
            "# 🍭 __**Big Mom's Sweet Commandments:**__ 🍭\n> Welcome to our territory, but mind the rules!\n> **Life or Ban? Your choice.\n> Follow the rules or I'll take decades off your life span!** 👵",
        
            "# 🧑‍🏫 __**Rayleigh's Haki Training:**__ 🧑‍🏫\n> A true pirate knows how to control themselves.\n> **Train your Haki of self-control and respect.\n> Or this Dark King might just have to give you a lesson!** ⚔️",
        
            "# 🎆 __**Ivankov's Emporio Face-Lift Policy:**__ 🎆\n> Hee-haw! Candy-boys and girls, keep it fabulous!\n> **Express yourself freely, but respect others' boundaries.\n> Break the rules and face a hormonal attitude adjustment!** 💉",
        
            "# 🐘 __**Zunisha's Ancient Wisdom:**__ 🐘\n> I've carried the Minks for 1000 years; I'll guide you too.\n> **Respect the long history of our community.\n> Neglect it, and you might be washed away like Jack.** 🌊"
        ]
        return random.choice(reminder_messages)


    async def log_action(self, ctx, member: discord.Member, action: str, reason: str, moderator: discord.Member = None, jump_url: str = None, image_url: str = None):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            log_message = (
                "🏴‍☠️ **Crew Log Entry** 🏴‍☠️\n\n"
                f"**Target Pirate:** {member.name} (ID: {member.id})\n"
                f"**Action Taken:** {action}\n"
                f"**Reason for Action:** {reason}\n"
            )
            if moderator:
                log_message += f"**Enforcing Officer:** {moderator.name} (ID: {moderator.id})\n"
            if jump_url:
                log_message += f"**Incident Report:** [View Incident Details]({jump_url})\n"
            if image_url:
                log_message += f"**Evidence:** [View Image]({image_url})\n"
            
            log_message += f"\nLogged at {ctx.message.created_at.strftime('%Y-%m-%d %H:%M:%S')} | One Piece Moderation"
            
            await log_channel.send(log_message)

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        """Warn a crew member for breaking the Pirate Code."""
        if member.bot:
            return await ctx.send("Ye can't warn a bot, ye scurvy dog!")

        if member == ctx.author:
            return await ctx.send("Ye can't warn yerself, ye barnacle-brained buffoon!")

        current_time = datetime.utcnow()
        async with self.config.guild(ctx.guild).warned_users() as warned_users:
            user_warns = warned_users.get(str(member.id), {})
            
            if user_warns and current_time - datetime.fromisoformat(user_warns['timestamp']) < timedelta(hours=24):
                # Update existing warning
                user_warns['count'] += 1
                user_warns['reasons'].append(reason)
                user_warns['timestamp'] = current_time.isoformat()
            else:
                # Create new warning
                user_warns = {
                    'count': 1,
                    'reasons': [reason],
                    'moderator': ctx.author.id,
                    'timestamp': current_time.isoformat()
                }
            
            warned_users[str(member.id)] = user_warns

        warn_count = user_warns['count']
        
        pirate_warnings = [
            f"Ahoy, {member.mention}! Ye've been given a black spot for breakin' the Pirate Code!",
            f"Shiver me timbers, {member.mention}! Ye've earned yerself a mark on the captain's log!",
            f"Blimey, {member.mention}! Ye've been caught red-handed violatin' our crew's code!",
            f"Arrr, {member.mention}! The Pirate Court has found ye guilty of misbehavior!",
            f"Avast ye, {member.mention}! Ye've been branded with the mark of the mutineer!"
        ]

        if warn_count == 1:
            warning_message = random.choice(pirate_warnings)
        else:
            warning_message = f"Aye, {member.mention}! Ye've been warned {warn_count} times in the last 24 hours! Keep this up, and ye'll be swabbin' the decks in Impel Down!"

        await ctx.send(warning_message)

        # Update or create the log message
        await self.update_warn_log(ctx.guild, member, user_warns)

        if warn_count >= 5:
            recommendation = f"⚠️ {member.mention} has received 5 or more warnings in 24 hours. Consider muting them for 30 minutes using the following command:\n`[p]mute {member.mention} 30m Multiple infractions of the Pirate Code`"
            await ctx.send(recommendation)

    async def update_warn_log(self, guild, member, warn_data):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            return  # Log channel not found

        # Check if there's an existing log message for this user's current warning period
        async for message in log_channel.history(limit=100):
            if message.author == self.bot.user and message.embeds:
                embed = message.embeds[0]
                if embed.title and embed.title.startswith(f"⚠️ Warning Log for {member.display_name}"):
                    # Update existing log message
                    new_embed = self.create_warn_embed(member, warn_data)
                    await message.edit(embed=new_embed)
                    return

        # If no existing message found, create a new one
        new_embed = self.create_warn_embed(member, warn_data)
        await log_channel.send(embed=new_embed)

    def create_warn_embed(self, member, warn_data):
        self.logger.debug(f"Creating warn embed for member: {member.id}")
        self.logger.debug(f"Member avatar: {member.avatar}")
        self.logger.debug(f"Member default avatar: {member.default_avatar}")

        embed = discord.Embed(
            title=f"⚠️ Warning Log for {member.display_name}",
            color=discord.Color.red(),
            timestamp=datetime.fromisoformat(warn_data['timestamp'])
        )
        
        if member.avatar:
            avatar_url = member.avatar.url
            self.logger.debug(f"Using custom avatar: {avatar_url}")
        else:
            avatar_url = member.default_avatar.url
            self.logger.debug(f"Using default avatar: {avatar_url}")
        
        embed.set_thumbnail(url=avatar_url)
        
        embed.add_field(name="Warning Count", value=str(warn_data['count']), inline=False)
        embed.add_field(name="Reasons", value="\n".join(f"• {reason}" for reason in warn_data['reasons']), inline=False)
        moderator = member.guild.get_member(warn_data['moderator'])
        mod_name = moderator.display_name if moderator else "Unknown Moderator"
        embed.add_field(name="Last Updated By", value=mod_name, inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        return embed

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member):
        """Check a crew member's recent warnings."""
        async with self.config.guild(ctx.guild).warned_users() as warned_users:
            user_warns = warned_users.get(str(member.id), {})

        if not user_warns:
            return await ctx.send(f"{member.mention} has a clean record, sailin' smooth seas!")

        current_time = datetime.utcnow()
        if current_time - datetime.fromisoformat(user_warns['timestamp']) >= timedelta(hours=24):
            return await ctx.send(f"{member.mention} has no warnings in the last 24 hours. They've straightened their course!")

        embed = self.create_warn_embed(member, user_warns)
        await ctx.send(embed=embed)

    @commands.command()
    @checks.admin_or_permissions(manage_messages=True)
    async def clearwarnings(self, ctx, member: discord.Member):
        """Clear all warnings for a crew member."""
        async with self.config.guild(ctx.guild).warned_users() as warned_users:
            if str(member.id) in warned_users:
                del warned_users[str(member.id)]
                await ctx.send(f"Yarr! All warnings for {member.mention} have been wiped clean. Their slate be as clear as the horizon!")
            else:
                await ctx.send(f"{member.mention} had no warnings to clear. They be sailin' with a clean record already!")

        # Update the log to reflect cleared warnings
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            async for message in log_channel.history(limit=100):
                if message.author == self.bot.user and message.embeds:
                    embed = message.embeds[0]
                    if embed.title and embed.title.startswith(f"⚠️ Warning Log for {member.display_name}"):
                        await message.delete()
                        break
        
    @commands.command()
    @checks.mod_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Disrespecting the captain's orders!"):
        """Force a crew member to walk the plank."""
        try:
            await ctx.guild.kick(member, reason=reason)
            await ctx.send(f"🦈 {member.name} has walked the plank! They'll have to find another crew or swim with the Sea Kings.")
            await self.log_action(ctx, member, "Forced to Walk the Plank", reason, moderator=ctx.author)
            
            case = await modlog.create_case(
                self.bot, ctx.guild, ctx.message.created_at, action_type="kick",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The incident has been recorded in the ship's log. Case number: {case.case_number}")
        except discord.Forbidden:
            await ctx.send("I don't have the authority to make that crew member walk the plank!")
        except discord.HTTPException:
            await ctx.send("There was an error while trying to make that crew member walk the plank. The Sea Kings must be interfering with our Den Den Mushi!")

    @commands.command()
    @checks.mod_or_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Mutiny against the crew!"):
        """Banish a pirate to Impel Down and erase their messages."""
        try:
            # Ensure the bot has permission to ban
            if not ctx.guild.me.guild_permissions.ban_members:
                return await ctx.send("I don't have the authority to banish pirates to Impel Down!")
        
            # Check role hierarchy
            if ctx.author.top_role <= member.top_role or ctx.guild.me.top_role <= member.top_role:
                return await ctx.send("Ye can't banish a pirate of equal or higher rank!")
        
            # Ban the user
            await ctx.guild.ban(member, reason=reason, delete_message_seconds=7 * 24 * 60 * 60)
        
            # Select a random ban message
            ban_message, ban_gif = random.choice(self.ban_messages)
        
            # Create the ban text message
            ban_text = (
                f"⛓️ Pirate Banished to Impel Down! ⛓️\n\n"
                f"{member.name} has been locked away!\n\n"
                f"**Crimes**\n{reason}\n\n"
                f"**Warden's Note**\n{ban_message}"
            )
        
            # Send the ban message to the general chat or the current channel
            general_chat = self.bot.get_channel(self.general_chat_id)
            if general_chat:
                await general_chat.send(ban_text)
                await general_chat.send(ban_gif)
            else:
                await ctx.send("Couldn't find the general chat channel. Posting here instead:")
                await ctx.send(ban_text)
                await ctx.send(ban_gif)
        
            # Log the action
            await self.log_action(ctx, member, "Banished to Impel Down", reason, moderator=ctx.author)
        
            # Create a case in the modlog
            case = await modlog.create_case(
                self.bot, ctx.guild, ctx.message.created_at, action_type="ban",
                user=member, moderator=ctx.author, reason=reason
            )
            if case:
                await ctx.send(f"The traitor's crimes have been recorded in the ship's log. Case number: {case.case_number}")
        
        except discord.Forbidden:
            await ctx.send("I don't have the authority to banish that pirate to Impel Down!")
        except discord.HTTPException as e:
            await ctx.send(f"There was an error while trying to banish that pirate. The Marines must be jamming our signals! Error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            self.logger.error(f"Error in ban command: {e}", exc_info=True)

    @staticmethod
    async def is_mod_or_admin(ctx):
        """Check if the user is a mod or admin."""
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author == ctx.guild.owner:
            return True
        if await ctx.bot.is_mod(ctx.author):
            return True
        return False
            
    @commands.command(usage="<users...> [time] [reason]")
    @commands.guild_only()
    @commands.check(is_mod_or_admin)
    async def mute(
        self,
        ctx: commands.Context,
        users: commands.Greedy[discord.Member],
        time: Optional[str] = None,
        *,
        reason: str = "No reason provided"
    ):
        """Banish crew members to the Void Century."""
        if not users:
            return await ctx.send_help()
        if ctx.me in users:
            return await ctx.send("You cannot banish the ship's Log Pose to the Void Century!")
        if ctx.author in users:
            return await ctx.send("You cannot banish yourself to the Void Century!")
    
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("Blimey! The Void Century role has vanished like a mirage! Alert the captain!")
    
        async with ctx.typing():
            duration = None
            until = None
            if time:
                try:
                    duration = self.parse_timedelta(time)
                    until = ctx.message.created_at + duration
                except ValueError:
                    return await ctx.send("Yarr! That be an invalid time format. Use something like '1d', '12h', or '30m', ye scurvy dog!")
    
            if not duration:
                default_duration = await self.config.guild(ctx.guild).default_time()
                if default_duration:
                    duration = timedelta(seconds=default_duration)
                    until = ctx.message.created_at + duration
    
            time_str = f"for {humanize_timedelta(timedelta=duration)}" if duration else "indefinitely"
    
            success_list = []
            for user in users:
                result = await self.mute_user(ctx.guild, ctx.author, user, until, reason)
                if result["success"]:
                    success_list.append(user)
                    await modlog.create_case(
                        self.bot,
                        ctx.guild,
                        ctx.message.created_at,
                        "smute",
                        user,
                        ctx.author,
                        reason,
                        until=until,
                    )
                    await self._send_dm_notification(user, ctx.author, ctx.guild, "Banishment to the Void Century", reason, duration)
                    await self.log_action(ctx, user, f"Banished to Void Century {time_str}", reason, ctx.author)
                    
                    # Schedule auto-unmute
                    if duration:
                        self.schedule_unmute(ctx.guild, user, duration)
                else:
                    await ctx.send(f"I couldn't banish {user} to the Void Century: {result['reason']}")
    
        if success_list:
            pirate_messages = [
                f"Yohohoho! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been silenced like Brook without his voice box {time_str}! The sudden silence caused Brook to panic and play his guitar at max volume, shattering all the mirrors in the Whole Cake Chateau. Now Big Mom can't admire her new hairdo, Brulee's mirror world is in chaos, and somehow, Absalom's invisibility has stopped working.",
                
                f"Great Scott! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been sent to the Calm Belt of chat {time_str}! Not even a Den Den Mushi can reach {'them' if len(success_list) > 1 else 'them'}. The resulting silence has lulled all the Sea Kings to sleep, causing a massive traffic jam of Marine ships. Garp is now giving a loud lecture on justice, ironically waking up the Sea Kings and causing general pandemonium.",
                
                f"Holy Merry! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been caught in Foxy's Noro Noro Beam {time_str}! {'Their' if len(success_list) > 1 else 'Their'} messages will be slowed to a crawl. The beam reflected off Franky's super shiny robot body, accidentally slowing down Aokiji's ice powers. Now Punk Hazard is slowly defrosting, Caeser Clown's experiments are melting, and Trafalgar Law is wondering why his 'Room' is expanding at a snail's pace.",
                
                f"Gomu Gomu no Silence! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} had {'their' if len(success_list) > 1 else 'their'} chat privileges stretched to the limit {time_str}! Luffy's arms got tangled in the process, turning him into a giant rubber band. Now Usopp's using him as a slingshot to launch Chopper across the Grand Line for emergency medical house calls, while Zoro's trying to cut Luffy free but keeps getting lost between his stretched fingers.",
                
                f"Mamamama! Big Mom has stolen the voice of {humanize_list([f'`{u}`' for u in success_list])} and put it in her collection {time_str}! She's using it as a ringtone for her Den Den Mushi. The new ringtone is so catchy that all of Totto Land is dancing uncontrollably. Katakuri's trying to predict the next beat, Pudding's memory-wiping everyone who saw her trip during her dance solo, and Streusen's accidentally baked a ten-layer cake in rhythm.",
                
                f"Zoro got lost again and accidentally led {humanize_list([f'`{u}`' for u in success_list])} into the Void Century {time_str}! Good luck finding your way back... maybe ask someone with a better sense of direction? Like a potato. The World Government is in panic mode, Imu is furiously scribbling 'DO NOT ENTER' signs, and the Five Elders are seriously considering hiring Zoro as their new security system. Meanwhile, Robin's having a field day deciphering the Poneglyphs Zoro accidentally uncovered.",
                
                f"Sanji's Diable Jambe was too hot! It burned {humanize_list([f'`{u}`' for u in success_list])}'s keyboard to a crisp {time_str}! On the bright side, their computer setup is now 'toast'... literally. The fire spread to Nami's tangerine grove, but instead of burning, it caramelized all the fruits. Now Luffy won't stop eating them, Chopper's panicking about potential sugar rush, and Sanji's creating a new recipe for 'Flambéed Tangerine Love Hurricane' in honor of his beloved Nami-swan.",
                
                f"Crocodile's sand has dried up the ink in {humanize_list([f'`{u}`' for u in success_list])}'s pen {time_str}. No more writing for you! Time to communicate via interpretive dance. The sand storm has spread across the Grand Line, turning every island into a beach paradise. Buggy's sandals got stuck, his feet detached, and now his crew is chasing them across the New World. Meanwhile, Aokiji's building the world's largest sand castle and Blackbeard's complaining about sand in his beard.",
                
                f"Usopp's latest invention, the 'Shut-Up-A-Pirate 3000', worked perfectly on {humanize_list([f'`{u}`' for u in success_list])} {time_str}! The shock of his success caused Usopp to faint, accidentally launching a Pop Green that grew into a beanstalk reaching Skypiea. Now Enel's trying to slide down it back to Earth, Nami's calculating the profit from a sky-high toll booth, and God Usopp's follower count just broke the Internet.",
                
                f"Chopper's Rumble Ball had an odd effect on {humanize_list([f'`{u}`' for u in success_list])}. {'They' if len(success_list) > 1 else 'They'} can't type {time_str}! Instead, {'they`re' if len(success_list) > 1 else 'they`re'} stuck making adorable reindeer noises. The cuteness overload caused Bartholomew Kuma to malfunction, shooting Pacifistas filled with cotton candy across the Grand Line. Now Perona's negative hollows are turning suspiciously positive, Moria's zombies are having a sugar-fueled dance party, and Doflamingo's strings have turned into licorice whips.",
                
                f"Robin sprouted hands all over {humanize_list([f'`{u}`' for u in success_list])}'s keyboard, preventing {'them' if len(success_list) > 1 else 'them'} from typing {time_str}! Now their keyboard just keeps typing 'hand hand hand hand'. The hands have taken over the ship, forming a giant mecha that's now challenging Queen's dinosaur form to a robot dance-off. Franky's taking notes for his next super upgrade, while Brook's providing the soundtrack with his new hit single, 'Hands Up for Adventure'.",
                
                f"Franky performed a SUPER mute on {humanize_list([f'`{u}`' for u in success_list])} {time_str}! Cola-powered silence! Side effects may include spontaneous posing and an irresistible urge to yell 'SUPER!' The excess cola fumes have turned all the fish in the area into hyperactive disco dancers. Now Jinbe's trying to coral them into formation for an underwater musical, Sanji's inventing new recipes for 'Jitterbug Jellyfish Jambalaya', and the Kraken's become a master of the Swim Swim fruit... dance, that is.",
                
                f"Jinbei's Fish-Man Karate sent {humanize_list([f'`{u}`' for u in success_list])} flying into the Void Century {time_str}! They`re now best friends with Joy Boy, apparently. The shockwave from his karate chop traveled through time, giving Toki's time-time fruit a hiccup. Now Momonosuke is randomly shifting between baby and adult dragon forms, the Nine Red Scabbards are trying to childproof Wano for their time-jumping lord, and Kaido is very confused about why his intimidating roars keep turning into baby dragon squeaks.",
                
                f"Nami's Thunder Tempo has short-circuited {humanize_list([f'`{u}`' for u in success_list])}'s communication devices {time_str}! The resulting power surge overcharged Franky's hair, causing a worldwide shortage of cola. This led to Luffy raiding Chopper's cotton candy supply, Sanji stress-baking until he filled Whole Cake Island with cream puffs, and Pudding having to erase everyone's memories of ever liking cola. Meanwhile, Zoro's somehow gotten lost in Nami's electric currents and ended up in the One Piece live-action set.",
                
                f"Buggy's Chop-Chop Fruit accidentally divided {humanize_list([f'`{u}`' for u in success_list])}'s messages into tiny, unreadable pieces {time_str}! We're still trying to put them back together, but some parts seem to have floated away. In the chaos, Buggy's nose landed on Usopp's face, giving him unprecedented lying powers. His tall tales are now coming true, causing Marines to believe in the existence of a giant gold-pooping beetle. Garp is leading an expedition to find it, much to Sengoku's frustration.",
                
                f"Trafalgar Law's ROOM has temporarily removed {humanize_list([f'`{u}`' for u in success_list])}'s ability to communicate {time_str}! He's replaced it with the ability to make really bad puns. Heart-breaking, isn't it? The puns are so bad They`re causing physical pain, making Chopper rush around trying to cure this new 'disease'. Bepo's actually loving it, much to the horror of the Heart Pirates. Meanwhile, Caesar Clown is trying to weaponize the puns for his next evil scheme.",
                
                f"Blackbeard's Dark-Dark Fruit has swallowed {humanize_list([f'`{u}`' for u in success_list])}'s messages into a void {time_str}! Rumor has it, you can still hear the echoes if you listen closely to a black hole. The void started sucking in everything dark, including Zoro's dark aura when he gets lost. Now Zoro's stuck orbiting Blackbeard, using his swords as oars, while Perona's negative hollows are getting a tan from the darkness absorption. Van Augur's having the time of his life using the void as a portal for trick shots across the Grand Line.",
                
                f"Doflamingo's strings have tied up {humanize_list([f'`{u}`' for u in success_list])}'s fingers, preventing {'them' if len(success_list) > 1 else 'them'} from typing {time_str}! On the bright side, {'they`ve' if len(success_list) > 1 else 'they`ve'} never looked more fabulous in pink feathers. The excess string has turned Dressrosa into a giant cat's cradle. King is stuck thinking it's some kind of advanced interrogation technique, Charlotte Smoothie is trying to juice the strings for a new cocktail, and Leo of the Tontatta Tribe is having a field day with his new sewing materials.",
                
                f"Gecko Moria's shadows have stolen {humanize_list([f'`{u}`' for u in success_list])}'s ability to chat {time_str}! Now their shadows are having a great conversation without them. The shadowless users have teamed up with Brook to form the world's first transparent band. Their music is so soul-stirring it's causing Moria's zombie army to break out in a thriller dance. Perona's ghosts are working as special effects, and Absalom's reporting on it while invisible, leading to floating cameras all over Thriller Bark.",
                
                f"Aokiji's Ice Age has frozen {humanize_list([f'`{u}`' for u in success_list])}'s keyboard solid {time_str}! Might we suggest defrosting it with Ace's Flame-Flame Fruit? ...Oh, too soon? The sudden cold snap has turned all of Water 7 into a giant ice rink. Franky's redesigning the Sea Train with ice skates, Kokoro's Mermaid Cafe is now an igloo, and the Galley-La shipwrights are carving galleons out of ice. Meanwhile, Aokiji's been mistaken for a very lazy ice sculptor and entered into Iceburg's winter festival competition.",
                
                f"Kizaru moved at the speed of light and unplugged {humanize_list([f'`{u}`' for u in success_list])}'s internet connection {time_str}! He would plug it back in, but that sounds like a lot of work. In his haste, Kizaru accidentally caused a worldwide blackout. Now Enel's moonlight is the only source of electricity, making him feel like a god again. Rayleigh's haki training has turned into 'catch the light beams', and Sentomaru's so fed up he's considering leaving the Marines to become a candlemaker.",
                
                f"Kaido's Blast Breath melted {humanize_list([f'`{u}`' for u in success_list])}'s chat privileges {time_str}! We'd offer them a new keyboard, but Kaido drank all the money we were going to use to buy it. The heat from Kaido's breath turned Wano into a sauna. Queen's now running a luxury spa for Beasts Pirates, King's flame powers are being used to keep the towels warm, and Jack's stuck as the pool boy. Meanwhile, Yamato's hosting snowball fights with her ice powers to help everyone cool down.",
                
                f"Marco the Phoenix's blue flames have temporarily incinerated {humanize_list([f'`{u}`' for u in success_list])}'s chat access {time_str}! Don't worry, it'll regenerate... eventually. The blue flames spread across the Moby Dick, turning it into a ghost ship. Now Whitebeard's mustache is glowing blue, Jozu's diamond form is refracting the light into a disco ball effect, and Thatch is cooking with eternal fire. Vista's rose petals have turned into blue fire butterflies, creating the world's most dangerous garden.",
                
                f"Ivankov's hormones have mysteriously changed {humanize_list([f'`{u}`' for u in success_list])}'s voice, making it impossible to type {time_str}! {'They`re' if len(success_list) > 1 else 'They`re'} now communicating exclusively in fabulous winks. The hormone burst has affected all of Kamabakka Kingdom. Sanji's okama disguise is now permanent, Mr. 2 Bon Clay is stuck in a never-ending series of face changes, and somehow, Crocodile is blushing. The Revolutionary Army isn't sure whether to be amused or very, very concerned.",
                
                f"Bartolomeo's Barrier Fruit has cut off {humanize_list([f'`{u}`' for u in success_list])} from the chat {time_str}! He says he'll take it down if you can get him Luffy's autograph. The barrier expanded to cover all of Dressrosa, turning it into a giant bounce house. Cavendish is using it as a beauty sleep chamber, Rebecca's Colosseum fights have turned into sumo matches, and King Riku is seriously considering this as a permanent national defense system. Meanwhile, Pica's voice is echoing hilariously off the barrier walls.",
                
                f"Enel's lightning struck {humanize_list([f'`{u}`' for u in success_list])}'s computer, causing a temporary blackout {time_str}! Their new electric personality is quite shocking. The lightning overcharged the Ark Maxim, sending it crashing back to the Blue Sea. Now Enel's stuck running a tech support hotline for Den Den Mushi, the Skypieans are trying to explain clouds to very confused fish, and Wiper's trying to conquer the ocean with his Burn Bazooka, creating the world's largest jacuzzi.",
                
                f"Garp threw his Fist of Love, knocking {humanize_list([f'`{u}`' for u in success_list])} out of the chat {time_str}! That's what we call 'tough love'... emphasis on the 'tough'. The shockwave from Garp's fist circled the globe, giving everyone a momentary sense of Marine-induced guilt. Sengoku's goat ate the resulting wave of paper apologies, turning it into a Zoan-type 'Guilt-Guilt Fruit' user. Now the goat's making even Akainu question his life choices, Luffy's actually considering becoming a Marine, and Coby's promotion to Admiral is being fast-tracked.",
            
                f"Mihawk's sword slash was so precise, it cut {humanize_list([f'`{u}`' for u in success_list])}'s chat connection {time_str}! He was aiming for a fly, but you know how it goes. The slash continued across the Grand Line, accidentally giving everyone perfect haircuts. Buggy's nose hair got trimmed, allowing him to smell the One Piece. Now the Red-Haired Pirates and the Buggy Pirates are in a sniffing race, Zoro's swords are demanding a style upgrade, and Sanji's somehow gotten his eyebrow un-curled.",
            
                f"Magellan's Venom Demon has poisoned {humanize_list([f'`{u}`' for u in success_list])}'s chatting ability {time_str}! Side effects include an extreme case of verbal diarrhea... ironically. The poison seeped into Impel Down's plumbing, turning the underwater forest into a psychedelic wonderland. Now Hannyabal's impersonating Magellan but with tie-dye skin, Sadi-chan's whip is spouting motivational quotes, and Ivankov's declaring it the new paradise of 'free self-expression'. The World Government is not amused.",
            
                f"Perona's Negative Hollow made {humanize_list([f'`{u}`' for u in success_list])} too depressed to type {time_str}! {'They`re' if len(success_list) > 1 else 'They`re'} currently under their desk, mumbling about being reborn as a lint roller. The negativity spread across Thriller Bark, making even the zombies too depressed to fight. Gecko Moria's now running a support group for 'Shadows with Low Self-Esteem', Absalom's invisible tears are causing mysterious indoor rain, and Kumacy's finally expressing his true feelings through nihilistic poetry.",
            
                f"Caesar Clown's Gastinet made the air around {humanize_list([f'`{u}`' for u in success_list])} unbreathable, forcing {'them' if len(success_list) > 1 else 'them'} to retreat from chat {time_str}! Their last message was just a series of coughs and 'SHURORORORO'. The gas expanded, turning Punk Hazard into a giant bouncy castle. Now Trafalgar Law's 'Room' is full of giggling Straw Hats, Smoker's smoke is coming out in balloon animals, and Vegapunk's long-distance Den Den Mushi are transmitting nothing but laugh tracks.",
            
                f"Fujitora's gravity crushed {humanize_list([f'`{u}`' for u in success_list])}'s keyboard {time_str}, making typing impossible! They`re now communicating via interpretive meteor showers. The altered gravity caused Zunisha to start moonwalking across the New World. Now Jack's seasick, the Mink Tribe is hosting anti-gravity raves, and Raizo's ninja scrolls keep floating away. Meanwhile, Fujitora's trying to convince everyone it's a new form of 'Celestial Navigation'.",
            
                f"Sengoku's Buddha shockwave sent {humanize_list([f'`{u}`' for u in success_list])} flying out of the chat room {time_str}! We expect {'them' if len(success_list) > 1 else 'them'} to achieve enlightenment any day now. The shockwave resonated with all the gold in Mary Geoise, turning the Holy Land into a giant tuning fork. Now Imu's trying to conduct the world's largest celestial orchestra, the Gorosei are vibrating in perfect harmony, and Charlos's bubble helmet has become a floating sound booth. Donquixote Mjosgard is surprisingly into it.",
            
                f"Borsalino's light speed kick launched {humanize_list([f'`{u}`' for u in success_list])} into a communication dead zone {time_str}! He would've brought {'them' if len(success_list) > 1 else 'them'} back, but that sounds like eeeeffort~. The kick tore a hole in the space-time continuum, causing past and future versions of pirates to appear randomly. Now Luffy's getting meat-eating tips from his future self, Blackbeard's trying to steal devil fruits from his past self, and Buggy's past and future selves are forming an endless circus line.",
            
                f"Bonney's Age-Age Fruit regressed {humanize_list([f'`{u}`' for u in success_list])} to an age before they could type {time_str}! {'They`re' if len(success_list) > 1 else 'They`re'} currently teething on the keyboard. The age regression spread across Sabaody, turning it into a giant daycare. Rayleigh's teaching Haki to toddlers, Shakky's bar is now serving juice boxes, and the Human Auction House is hosting nap time. Kid Doflamingo is having a tantrum because his sunglasses don't fit, while baby Kuma is crawling around with a miniature Bible.",
            
                f"Queen's Plague Rounds infected {humanize_list([f'`{u}`' for u in success_list])}'s chat privileges with silence {time_str}! The only cure is to dance like no one's watching... because They`re not. They can't see you. The virus mutated, turning everyone in Wano into funk soul brothers. Now Kaido's Beast Pirates are having a dance-off against the Nine Red Scabbards, Orochi's hair snakes are doing the conga, and Yamato's ice powers are being used to create a giant disco ball. Kin'emon's clothes are changing faster than John Travolta in Saturday Night Fever.",
            
                f"Shirahoshi accidentally called a Sea King, who ate {humanize_list([f'`{u}`' for u in success_list])}'s messages {time_str}! The Sea King is now the most well-informed creature in the ocean. Poseidon's powers went into overdrive, summoning all the Sea Kings to Fishman Island for a ted talk. Now Hody Jones is the reluctant audio-visual guy, Vander Decken IX is trying to throw love letters at the Sea King's non-existent hands, and Neptune's turned the whole thing into a music festival called 'Sea-chella'.",
            
                f"Corazon's Silent-Silent Fruit failed spectacularly, causing him to trip and unplug {humanize_list([f'`{u}`' for u in success_list])}'s computer(s) {time_str}! As he silently screamed, he accidentally knocked over Vegapunk's latest experiment. The resulting explosion turned all Den Den Mushi into break-dancing snails, leaving the Marines to communicate via interpretative dance. Somewhere in the New World, Doflamingo is laughing so hard he's tangled in his own strings.",
            
                f"Hody Jones' Energy Steroids caused {humanize_list([f'`{u}`' for u in success_list])} to rage-quit the chat {time_str}! {'They' if len(success_list) > 1 else 'They'} punched through their monitor in a fit of steroid-induced fury. The steroids seeped into the ocean, turning all the fish into bodybuilders. Now Jinbe's teaching an underwater aerobics class, Arlong Park has been converted into a protein shake bar, and Sanji's having a existential crisis over how to delicately prepare a fish with biceps.",
            
                f"Kuma's Paw-Paw Fruit has deflected all of {humanize_list([f'`{u}`' for u in success_list])}'s messages {time_str}! {'They`re' if len(success_list) > 1 else 'They`re'} expected to land somewhere in the chat... in about 3 days. The deflected messages gained sentience during their flight, forming a new Sky Island made entirely of floating text. Now Urouge's trying to decipher the wisdom of the chat gods, Enel's planning to conquer it with his 'divine grammar', and Nami's calculating the profit margins on selling punctuation to the locals.",
            
                f"Capone Bege trapped {humanize_list([f'`{u}`' for u in success_list])} inside his body fortress, cutting off their communication {time_str}! They`re currently lost somewhere between his pancreas and his spleen. Bege's body has turned into a funhouse of rooms, each themed after a different pirate crew. Now Big Mom's rampaging through his sweet tooth, Kaido's trying to turn his liver into Onigashima, and somehow Luffy's found the meat storage. Bege's really regretting skipping those anatomy classes.",
            
                f"Hawkins' Straw-Straw Fruit has predicted a period of silence for {humanize_list([f'`{u}`' for u in success_list])} {time_str}! The cards also predict they'll stub their toe later. Ouch. The prediction caused a butterfly effect of self-fulfilling prophecies across the New World. Now Kaido's avoiding high places, Big Mom's on a diet, and Blackbeard's desperately trying to return his overdue library books. Meanwhile, Basil Hawkins has become a reluctant relationship counselor, with his cards deciding the fate of pirate ship crushes everywhere.",
            
                f"Pudding's Memory-Memory Fruit made {humanize_list([f'`{u}`' for u in success_list])} forget how to type {time_str}! They`re currently trying to send messages by aggressively poking their screen. The memory loss spread like wildfire through Totto Land. Now Katakuri can't remember how to see the future, Big Mom's forgotten her food cravings, and the Chess Peacekeepers are stuck in an eternal stalemate. Sanji's teaching everyone how to cook, inadvertently turning Whole Cake Island into the Grand Line's largest culinary school.",
            
                f"Tama's Kibi-Kibi Fruit accidentally tamed {humanize_list([f'`{u}`' for u in success_list])}'s keyboard, and now it won't work for anyone else {time_str}! The keyboard now only types in happy animal noises. The dango's effect spread to all technology in Wano, turning Den Den Mushi into loyal pets. Now Queen's cybernetics keep trying to fetch his bombs, Franky's hair is purring contentedly, and poor Apoo can't stop his body from playing 'Who Let the Dogs Out'. Meanwhile, Kaido's drunk-dialing other Yonko with nothing but 'moo's and 'baa's.",
            
                f"Smoker's Smoke-Smoke Fruit has obscured {humanize_list([f'`{u}`' for u in success_list])}'s messages {time_str}! Their chat window now looks like a very unsuccessful attempt at vaping. The smoke spread across Marineford, turning it into a foggy murder mystery dinner party. Now Akainu's trying to solve 'The Case of the Missing Justice', Kizaru's bumping into walls at the speed of light, and Coby's been mistaken for the butler and forced to serve tea. Garp's just napping through the whole thing, occasionally sleep-punching culprits.",
            
                f"X Drake transformed into a dinosaur and accidentally stomped on {humanize_list([f'`{u}`' for u in success_list])}'s communication device {time_str}! In his defense, those tiny keyboards are hard to use with giant dino claws. The soundwave from the stomp resonated with all the Zoan Devil Fruit users, turning Onigashima into a prehistoric party. Now Page One and Ulti are having a head-butting contest, Queen's funk has evolved into dinosaur disco, and poor Jack is stuck as a mammoth in a china shop. Meanwhile, Kaido's dragon form is trying to organize everyone into 'Jurassic Park' style Thriller choreography.",
            
                f"Carrot's Sulong form was too bright, temporarily blinding {humanize_list([f'`{u}`' for u in success_list])} {time_str}! They`re now typing in all caps because they can't see the keyboard properly. The Sulong transformation spread to all the minks, turning Zou into a giant lighthouse. Now Jack's ship keeps crashing into Zunisha's legs, Inuarashi and Nekomamushi have forgotten their day/night feud and are hosting 24/7 raves, and Bepo's luminous fur has turned the Heart Pirates' submarine into a mobile disco ball.",
            
                f"Giolla's Art-Art Fruit turned {humanize_list([f'`{u}`' for u in success_list])}'s messages into abstract art, making them unreadable {time_str}! Critics are calling it 'a bold statement on the futility of communication'. The artistic effect spread across Dressrosa, turning the whole island into a living Picasso painting. Now Pica's voice is coming out in color splatters, Diamante's cape is rearranging itself into cubist forms, and Sugar's toys are all walking around like Dali's melting clocks. King Riku is seriously considering rebranding the country as 'Dressrosa Modern Art Museum'.",
            
                f"Kinemon's disguise for {humanize_list([f'`{u}`' for u in success_list])} was so perfect, nobody could recognize {'them' if len(success_list) > 1 else 'them'} in the chat {time_str}! They`re currently pretending to be a very talkative house plant. Kinemon's power glitched, causing everyone in Wano to swap appearances. Now Kaido looks like O-Tama, Big Mom is stuck in Toko's body, and Orochi keeps shapeshifting between his many heads. The Straw Hats' rescue mission has turned into a ridiculous game of Guess Who, with Luffy enjoying it way too much.",
            
                f"Boa Hancock's Love-Love Fruit turned {humanize_list([f'`{u}`' for u in success_list])}'s keyboard to stone {time_str}! Now that's what we call 'hard' feelings! The petrification spread through the internet, turning all online communication into an ancient form of stone tablets. Now the Revolutionary Army is trying to organize a coup via stone emoji, the Marines are chiseling wanted posters instead of printing them, and poor Morgans is struggling to delivery the 'Daily Stone' newspaper. Meanwhile, Sentomaru's Den Den Mushi has become a very confused garden gnome."
            ]
            await ctx.send(random.choice(pirate_messages))

    def schedule_unmute(self, guild: discord.Guild, user: discord.Member, duration: timedelta):
        async def unmute_later():
            await asyncio.sleep(duration.total_seconds())
            await self.unmute_user(guild, self.bot.user, user, "Automatic unmute: Void Century banishment has ended")
            # Remove the task from the mute_tasks dict
            if guild.id in self.mute_tasks and user.id in self.mute_tasks[guild.id]:
                del self.mute_tasks[guild.id][user.id]

        # Create a task for the delayed unmute
        task = asyncio.create_task(unmute_later())
        
        # Store the task so it can be cancelled if needed
        if guild.id not in self.mute_tasks:
            self.mute_tasks[guild.id] = {}
        self.mute_tasks[guild.id][user.id] = task

    async def mute_user(
        self,
        guild: discord.Guild,
        author: discord.Member,
        user: discord.Member,
        until: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Union[bool, str]]:
        """Handles banishing users to the Void Century"""
        ret = {"success": False, "reason": None}
    
        mute_role = guild.get_role(self.mute_role_id)
        if not mute_role:
            ret["reason"] = "The Void Century role is missing! Have ye checked the Grand Line?"
            return ret
    
        if mute_role in user.roles:
            ret["reason"] = f"{user.name} is already banished to the Void Century!"
            return ret
    
        try:
            # Store current roles
            current_roles = [role for role in user.roles if role != guild.default_role and role != mute_role]
            
            # Remove all roles except @everyone and add mute role
            await user.edit(roles=[mute_role], reason=reason)
    
            if guild.id not in self.mute_role_cache:
                self.mute_role_cache[guild.id] = {}
            self.mute_role_cache[guild.id][user.id] = {
                "author": author.id,
                "member": user.id,
                "until": until.timestamp() if until else None,
                "roles": [r.id for r in current_roles]
            }
            await self.config.guild(guild).muted_users.set(self.mute_role_cache[guild.id])
            ret["success"] = True
        except discord.Forbidden as e:
            ret["reason"] = f"The Sea Kings prevent me from assigning the Void Century role! Error: {e}"
        except discord.HTTPException as e:
            ret["reason"] = f"A mysterious force interferes with the mute! Error: {e}"
        except Exception as e:
            ret["reason"] = f"An unexpected tempest disrupts the mute! Error: {e}"
        return ret

    @commands.command()
    @commands.guild_only()
    @commands.check(is_mod_or_admin)
    async def unmute(
        self,
        ctx: commands.Context,
        users: commands.Greedy[discord.Member],
        *,
        reason: str = "Void Century banishment has ended"
    ):
        """Return crew members from the Void Century."""
        if not users:
            return await ctx.send_help()
        if ctx.me in users:
            return await ctx.send("Ye can't free the ship's Log Pose from the Void Century!")
        if ctx.author in users:
            return await ctx.send("Ye can't free yerself from the Void Century!")
    
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("Shiver me timbers! The Void Century role has vanished like a ghost ship!")
    
        async with ctx.typing():
            success_list = []
            for user in users:
                self.logger.info(f"Attempting to unmute user {user.id}")
                result = await self.unmute_user(ctx.guild, ctx.author, user, reason)
                if result["success"]:
                    success_list.append(user)
                    await modlog.create_case(
                        self.bot,
                        ctx.guild,
                        ctx.message.created_at,
                        "sunmute",
                        user,
                        ctx.author,
                        reason,
                        until=None,
                    )
                    await self._send_dm_notification(user, ctx.author, ctx.guild, "Return from the Void Century", reason)
                else:
                    await ctx.send(f"I couldn't return {user} from the Void Century: {result['reason']}")
        
        if success_list:
            await ctx.send(
                f"{humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} "
                f"returned from the Void Century and can speak again!"
            )
        else:
            await ctx.send("Arrr! No crew members were freed from the Void Century this time.")
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        async with self.config.guild(guild).muted_users() as muted_users:
            if str(member.id) in muted_users:
                mute_data = muted_users[str(member.id)]
                mute_role = guild.get_role(self.mute_role_id)
                
                if mute_role:
                    try:
                        await member.add_roles(mute_role, reason="Reapplying mute on rejoin")
                        until = datetime.fromisoformat(mute_data['until']) if mute_data['until'] else None
                        if until and until > datetime.now(timezone.utc):
                            await self.schedule_unmute(guild, member, until - datetime.now(timezone.utc))
                        self.logger.info(f"Reapplied mute to {member} upon rejoining {guild}")
                    except discord.Forbidden:
                        self.logger.error(f"Failed to reapply mute to {member} in {guild}: Missing Permissions")
                    except discord.HTTPException as e:
                        self.logger.error(f"Failed to reapply mute to {member} in {guild}: {e}")
                        
    async def unmute_user(
        self,
        guild: discord.Guild,
        author: discord.Member,
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> Dict[str, Union[bool, str]]:
        """Handles returning users from the Void Century"""
        ret = {"success": False, "reason": None}
    
        self.logger.info(f"Attempting to unmute user {user.id} in guild {guild.id}")
    
        mute_role = guild.get_role(self.mute_role_id)
        if not mute_role:
            self.logger.error(f"Mute role {self.mute_role_id} not found in guild {guild.id}")
            ret["reason"] = "The Void Century role has vanished like a mirage! Alert the captain!"
            return ret
    
        if mute_role not in user.roles:
            self.logger.info(f"User {user.id} doesn't have the mute role in guild {guild.id}")
            ret["reason"] = f"{user.name} isn't trapped in the Void Century. They`re free as a seagull!"
            return ret
    
        try:
            self.logger.info(f"Removing mute role {mute_role.id} from user {user.id}")
            await user.remove_roles(mute_role, reason=reason)
            
            # Restore previous roles
            async with self.config.guild(guild).muted_users() as muted_users:
                if str(user.id) in muted_users:
                    roles_to_add = []
                    for role_id in muted_users[str(user.id)]["roles"]:
                        role = guild.get_role(role_id)
                        if role and role < guild.me.top_role and role not in user.roles:
                            roles_to_add.append(role)
                    
                    if roles_to_add:
                        await user.add_roles(*roles_to_add, reason="Restoring roles after unmute")
                        self.logger.info(f"Restored roles for {user} in {guild}: {', '.join(r.name for r in roles_to_add)}")
                    
                    del muted_users[str(user.id)]
            
            ret["success"] = True
            self.logger.info(f"Successfully unmuted user {user.id} in guild {guild.id}")
            
            # Cancel any existing unmute task
            if guild.id in self.mute_tasks and user.id in self.mute_tasks[guild.id]:
                self.logger.info(f"Cancelling unmute task for user {user.id} in guild {guild.id}")
                self.mute_tasks[guild.id][user.id].cancel()
                del self.mute_tasks[guild.id][user.id]
            
        except discord.Forbidden as e:
            self.logger.error(f"Forbidden error when unmuting user {user.id} in guild {guild.id}: {e}")
            ret["reason"] = "The Sea Kings prevent me from removing the Void Century role!"
        except discord.HTTPException as e:
            self.logger.error(f"HTTP error when unmuting user {user.id} in guild {guild.id}: {e}")
            ret["reason"] = f"A mysterious force interferes with the unmute! Error: {e}"
        except Exception as e:
            self.logger.error(f"Unexpected error when unmuting user {user.id} in guild {guild.id}: {e}", exc_info=True)
            ret["reason"] = f"An unexpected tempest disrupts the unmute! Error: {e}"
        
        return ret

    async def _restore_roles(self, member: discord.Member, reason: str):
        """Helper method to restore roles for a user."""
        guild = member.guild
        if guild.id in self.mute_role_cache and member.id in self.mute_role_cache[guild.id]:
            roles_to_add = []
            for role_id in self.mute_role_cache[guild.id][member.id]["roles"]:
                role = guild.get_role(role_id)
                if role and role < guild.me.top_role and role not in member.roles:
                    roles_to_add.append(role)
            
            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason=f"Restoring roles after unmute: {reason}")
                    self.logger.info(f"Restored roles for {member} in {guild}: {', '.join(r.name for r in roles_to_add)}")
                except discord.Forbidden:
                    self.logger.error(f"Failed to restore roles for {member} in {guild}: Missing Permissions")
                except discord.HTTPException as e:
                    self.logger.error(f"Failed to restore roles for {member} in {guild}: {e}")
            
            del self.mute_role_cache[guild.id][member.id]
            await self.config.guild(guild).muted_users.set(self.mute_role_cache[guild.id])

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Event listener to catch manual mute role removals."""
        mute_role = before.guild.get_role(self.mute_role_id)
        if not mute_role:
            return

        if mute_role in before.roles and mute_role not in after.roles:
            # The mute role was manually removed
            await self._restore_roles(after, "Manual unmute detected")


    async def log_action(self, ctx, member: discord.Member, action: str, reason: str, moderator: discord.Member = None):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            log_message = (
                "🏴‍☠️ **Crew Log Entry** 🏴‍☠️\n\n"
                f"**Target Pirate:** {member.name} (ID: {member.id})\n"
                f"**Action Taken:** {action}\n"
                f"**Reason for Action:** {reason or 'No reason provided'}\n"
                f"**Enforcing Officer:** {moderator.name} (ID: {moderator.id})\n"
                f"**Incident Report:** [View Incident Details]({ctx.message.jump_url})\n\n"
                f"Logged at {ctx.message.created_at.strftime('%Y-%m-%d %H:%M:%S')} | One Piece Moderation"
            )
            await log_channel.send(log_message)

    @commands.command(name="mutecheck", aliases=["checkmutetimer", "checkmute"])
    @commands.guild_only()
    @commands.check(is_mod_or_admin)
    async def check_mute_timer(self, ctx: commands.Context, user: discord.Member):
        """Check the remaining time for a muted user."""
        mute_role = ctx.guild.get_role(self.mute_role_id)
        if not mute_role:
            return await ctx.send("Arr! The Void Century role be missin'! Someone alert the captain!")
    
        if mute_role not in user.roles:
            return await ctx.send(f"{user.mention} ain't currently banished to the Void Century, ye barnacle-brain!")
    
        async with self.config.guild(ctx.guild).muted_users() as muted_users:
            mute_data = muted_users.get(str(user.id))
            if not mute_data:
                return await ctx.send(f"Blimey! I can't find any mute data for {user.mention}. They might be marooned indefinitely!")
    
            until = mute_data.get("until")
            if not until:
                return await ctx.send(f"{user.mention} be cast into the Void Century without an end date! They be needin' a pardon from the captain!")
    
            now = datetime.now(timezone.utc)
            
            # Convert 'until' to datetime object, handling both timestamp and ISO format
            if isinstance(until, (int, float)):
                until = datetime.fromtimestamp(until, tz=timezone.utc)
            elif isinstance(until, str):
                try:
                    until = datetime.fromisoformat(until).replace(tzinfo=timezone.utc)
                except ValueError:
                    return await ctx.send(f"Arrr! There be some strange magic with {user.mention}'s mute timer. It be needin' the captain's attention!")
            else:
                return await ctx.send(f"Shiver me timbers! {user.mention}'s mute timer be in an unknown format. The captain needs to look into this!")
    
            if until <= now:
                return await ctx.send(f"Shiver me timbers! {user.mention}'s mute timer has already expired! They should be free as a seagull!")
    
            remaining = until - now
            remaining_str = humanize_timedelta(timedelta=remaining)
    
            messages = [
                f"Gomu Gomu no Silence! {user.mention} is stretching through {remaining_str} of quiet time!",
                f"Yohohoho! {user.mention}'s voice is as absent as my flesh for {remaining_str} more!",
                f"Suuuuper! {user.mention} is building their voice back for {remaining_str}!",
                f"Mellorine~! {user.mention} is swirling in a sea of silence for {remaining_str}!",
                f"Meat?! No, {user.mention} can't ask for meat for {remaining_str} more!",
                f"Zoro got lost again, and so did {user.mention}'s voice! {remaining_str} left to find it!",
                f"Nami'd charge 100,000 berries to speak for {user.mention}, but they've still got {remaining_str} to go!",
                f"Franky's cola ran out, and so did {user.mention}'s words! Refilling for {remaining_str}!",
                f"Robin could sprout a hundred mouths, but {user.mention} can't use one for {remaining_str}!",
                f"Sanji's cooking up a storm, but {user.mention}'s voice is still marinating for {remaining_str}!",
                f"Usopp's tall tales are more audible than {user.mention} for {remaining_str} more!",
                f"Chopper's Rumble Ball lasted longer than {user.mention}'s voice! {remaining_str} to go!",
                f"Even the Soul King can't make {user.mention} sing for {remaining_str}!",
                f"Jinbe's making waves, but {user.mention}'s voice is still underwater for {remaining_str}!",
                f"Luffy's Haki can't sense {user.mention}'s voice for {remaining_str} more!",
                f"Smoker's got {user.mention}'s voice trapped in sea stone for {remaining_str}!",
                f"Buggy's Chop-Chop fruit split {user.mention}'s words apart for {remaining_str}!",
                f"Not even Ivankov's hormones can bring {user.mention}'s voice back for {remaining_str}!",
                f"Trafalgar Law swapped {user.mention}'s voice with silence for {remaining_str} more!",
                f"{user.mention}'s voice is as hidden as the One Piece for {remaining_str}!",
                f"Even Garp's Fist of Love can't knock a sound out of {user.mention} for {remaining_str}!",
                f"Doflamingo's strings are keeping {user.mention}'s mouth shut for {remaining_str}!",
                f"Blackbeard's darkness swallowed {user.mention}'s words for {remaining_str} more!",
                f"Not even Shanks' Conqueror's Haki can make {user.mention} speak for {remaining_str}!",
                f"{user.mention}'s voice is taking a longer break than Oda! {remaining_str} to go!",
                f"Aokiji froze {user.mention}'s words solid for {remaining_str}!",
                f"Kizaru's light speed kick sent {user.mention}'s voice flying for {remaining_str}!",
                f"Kaido's Thunder Bagua knocked {user.mention} speechless for {remaining_str}!",
                f"Big Mom's Soul Pocus stole {user.mention}'s voice for {remaining_str} more!",
                f"{user.mention}'s voice is as elusive as the All Blue for {remaining_str}!"
            ]
    
            await ctx.send(random.choice(messages))
            
    @commands.command()
    @checks.admin_or_permissions(manage_channels=True)
    async def restrict(self, ctx, channel: discord.TextChannel, role: discord.Role):
        """Restrict a channel to users with a specific role."""
        async with self.config.guild(ctx.guild).restricted_channels() as restricted:
            restricted[str(channel.id)] = role.id

        await channel.set_permissions(ctx.guild.default_role, send_messages=False, add_reactions=False)
        await channel.set_permissions(role, send_messages=True, add_reactions=True)

        await ctx.send(f"🔒 The {channel.mention} has been restricted to members with the {role.name} role or higher.")

    @commands.command()
    @checks.admin_or_permissions(manage_channels=True)
    async def unrestrict(self, ctx, channel: discord.TextChannel):
        """Remove restrictions from a channel."""
        async with self.config.guild(ctx.guild).restricted_channels() as restricted:
            if str(channel.id) in restricted:
                del restricted[str(channel.id)]

        await channel.set_permissions(ctx.guild.default_role, send_messages=None, add_reactions=None)
        await ctx.send(f"🔓 The restrictions on {channel.mention} have been removed.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # Check for banned words
        if await self.contains_banned_word(message.content):
            await self.handle_banned_word(message)
            return
    
        # Check if the user is new (less than 24 hours in the server)
        utc_now = datetime.now(pytz.utc)
        joined_at_utc = message.author.joined_at.replace(tzinfo=pytz.utc)
        is_new_user = (utc_now - joined_at_utc) < timedelta(hours=24)
    
        if is_new_user:
            # First check for obvious URLs
            contains_url = self.contains_url(message.content)

            if contains_url:
                await self.delete_and_warn(message, "new_user_link")
                return

            # If no obvious URL, wait a short time and check for embeds
            await asyncio.sleep(1)  # Wait for Discord to process potential embeds

            # Fetch the message again to check for embeds
            try:
                updated_message = await message.channel.fetch_message(message.id)
                if updated_message.embeds:
                    await self.delete_and_warn(updated_message, "new_user_link")
                    return
            except discord.NotFound:
                # Message was deleted, no action needed
                pass

        # Get the minimum image role
        minimum_image_role_id = await self.config.guild(message.guild).minimum_image_role_id()
        if minimum_image_role_id is None:
            return  # If no minimum role is set, don't apply any restrictions

        minimum_image_role = message.guild.get_role(minimum_image_role_id)
        if minimum_image_role is None:
            return  # If the role doesn't exist anymore, don't apply any restrictions

        # Check if the user has the minimum role or higher
        has_permission = any(role >= minimum_image_role for role in message.author.roles)

        # Filter images and GIFs for users without the minimum role or higher
        if not has_permission:
            contains_gif = re.search(r'\b(?:gif|giphy)\b', message.content, re.IGNORECASE)
            has_attachments = len(message.attachments) > 0
            if contains_gif or has_attachments or message.embeds:
                await self.delete_and_warn(message, "low_rank_image", minimum_image_role)
                return

        # Check if the channel is restricted
        restricted_channels = await self.config.guild(message.guild).restricted_channels()
        if str(message.channel.id) in restricted_channels:
            required_role_id = restricted_channels[str(message.channel.id)]
            required_role = message.guild.get_role(required_role_id)
            if required_role and not any(role >= required_role for role in message.author.roles):
                await self.delete_and_warn(message, "restricted_channel", required_role)
                return

    async def contains_banned_word(self, content: str) -> bool:
        return bool(self.nword_pattern.search(content))

    async def handle_banned_word(self, message: discord.Message):
        # Delete the message
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass  # If we can't delete the message, we'll still warn the user

        # Increment the offense counter and get the current count
        offense_count = await self.increment_offense_counter(message.author)

        # Determine the action based on the number of offenses
        if offense_count == 1:
            action = "warned"
            duration = None
        else:
            action = "muted"
            duration = timedelta(minutes=30 * (offense_count - 1))  # Escalating mute duration

        # Take action (warn or mute)
        if action == "muted":
            await self.mute_user(message.guild, self.bot.user, message.author, until=datetime.now(timezone.utc) + duration, reason="Use of banned language")

        # Prepare the warning message
        warning_messages = [
            f"Oi oi, {message.author.mention}! Even Luffy wouldn't approve of that language! The Pirate King's dream is about freedom, not disrespect!",
            f"Yohohoho! {message.author.mention}, that word is more forbidden than the Poneglyphs! As a skeleton, I have no ears to hear such things... but I'm all bones! Skull joke!",
            f"Oi, {message.author.mention}! Sanji says a true pirate's Black Leg style is about kicking ass, not using crass words!",
            f"Huh?! {message.author.mention}, are you trying to make Chopper cry with that language? He's a reindeer, not a swear-deer!",
            f"Oi oi oi! {message.author.mention}, Zoro got lost and ended up here, and even he knows that word is more dangerous than Mihawk's sword!",
            f"Nami says if you use that word again, {message.author.mention}, she'll raise your debt by 100,000 berries! And trust me, she WILL collect!"
        ]
        
        base_warning = random.choice(warning_messages)
        
        if action == "warned":
            consequence = (
                "\n\nThis be yer first warnin', rookie! One more slip of the tongue, "
                "and ye'll be scrubbing barnacles off the Thousand Sunny!"
            )
        else:
            consequence = (
                f"\n\nYe've been caught {offense_count} times now, ye scurvy dog! "
                f"By the order of the Fleet Admiral, ye're banished to Impel Down (muted) "
                f"for {humanize_timedelta(timedelta=duration)}! Reflect on the Way of the Pirate!"
            )

        warning_message = base_warning + consequence

        await message.channel.send(warning_message, delete_after=30)

        # Update the log
        await self.update_banned_word_log(message.author, offense_count, action, duration)

    async def mute_user(
        self,
        guild: discord.Guild,
        author: discord.Member,
        user: discord.Member,
        until: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Union[bool, str]]:
        ret = {"success": False, "reason": None}

        mute_role = guild.get_role(self.mute_role_id)
        if not mute_role:
            ret["reason"] = "The Void Century role is missing! Have ye checked the Grand Line?"
            return ret

        if mute_role in user.roles:
            ret["reason"] = f"{user.name} is already banished to the Void Century!"
            return ret

        try:
            # Store current roles
            current_roles = [role for role in user.roles if role != guild.default_role and role != mute_role]
            
            # Remove all roles except @everyone and add mute role
            await user.edit(roles=[mute_role], reason=reason)

            async with self.config.guild(guild).muted_users() as muted_users:
                muted_users[str(user.id)] = {
                    "author": author.id,
                    "user": user.id,
                    "until": until.isoformat() if until else None,
                    "roles": [r.id for r in current_roles]
                }

            ret["success"] = True
        except discord.Forbidden:
            ret["reason"] = "The Sea Kings prevent me from assigning the Void Century role!"
        except discord.HTTPException as e:
            ret["reason"] = f"A mysterious force interferes with the mute! Error: {e}"
        
        return ret

    async def update_banned_word_log(self, user: discord.Member, offense_count: int, action: str, duration: Optional[timedelta] = None):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            return  # Log channel not found

        # Check if there's an existing log message for this user
        async for message in log_channel.history(limit=100):
            if message.author == self.bot.user and message.embeds:
                embed = message.embeds[0]
                if embed.title and embed.title.startswith(f"🚫 Banned Word Log for {user.display_name}"):
                    # Update existing log message
                    new_embed = self.create_banned_word_log_embed(user, offense_count, action, duration)
                    await message.edit(embed=new_embed)
                    return

        # If no existing message found, create a new one
        new_embed = self.create_banned_word_log_embed(user, offense_count, action, duration)
        await log_channel.send(embed=new_embed)

    def create_banned_word_log_embed(self, user: discord.Member, offense_count: int, action: str, duration: Optional[timedelta] = None):
        embed = discord.Embed(
            title=f"🚫 Banned Word Log for {user.display_name}",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
        
        embed.add_field(name="Offense Count", value=str(offense_count), inline=False)
        embed.add_field(name="Latest Action", value=action.capitalize(), inline=False)
        
        if duration:
            embed.add_field(name="Mute Duration", value=humanize_timedelta(timedelta=duration), inline=False)
        
        embed.set_footer(text=f"User ID: {user.id}")
        return embed
        
    async def increment_offense_counter(self, member: discord.Member) -> int:
        async with self.config.member(member).all() as member_data:
            current_time = datetime.now(timezone.utc)
            last_offense_time = member_data['last_offense_time']

            # Reset counter if last offense was more than 24 hours ago
            if last_offense_time and (current_time - datetime.fromisoformat(last_offense_time)) > timedelta(hours=24):
                member_data['nword_offenses'] = 0

            member_data['nword_offenses'] += 1
            member_data['last_offense_time'] = current_time.isoformat()

            return member_data['nword_offenses']


    def contains_url(self, text):
        url_regex = re.compile(
            r'(?i)\b((?:https?://|www\d{0,3}[.]|discord[.]gg|discordapp[.]com|discord[.]com|t[.]me|twitch[.]tv|picarto[.]tv|youtube[.]com|youtu[.]be|facebook[.]com|fb[.]com|instagram[.]com|instagr[.]am|twitter[.]com|x[.]com|tumblr[.]com|reddit[.]com|reddit[.]it|linkedin[.]com|linkd[.]in|snapchat[.]com|snap[.]com|whatsapp[.]com|whatsapp[.]net|weibo[.]com|qq[.]com|qzone[.]qq[.]com|tiktok[.]com|douyin[.]com|bilibili[.]com|b23[.]tv|vk[.]com|ok[.]ru)\S*)\b')
        return re.search(url_regex, text) is not None

    async def delete_and_warn(self, message, message_type, role=None):
        await message.delete()
        await self.send_themed_message(message.channel, message.author, message_type, role)

    async def send_themed_message(self, channel, user, message_type, role=None):
        messages = {
            "new_user_link": [
                f"Avast ye, {user.mention}! New crew members can't be sharing treasure maps (links) until they've proven their sea legs for 24 hours!",
                f"Shiver me timbers, {user.mention}! Ye can't be posting mysterious scrolls (links) 'til ye've sailed with us for a full day!",
                f"Blimey, {user.mention}! No sharing secret routes (links) 'til ye've been part of the crew for 24 hours! Them's the rules of the sea!"
            ],
            "low_rank_image": [
                f"Arr, {user.mention}! Yer bounty's not high enough to be sharing wanted posters (images) yet! Ye need to reach a higher rank first!",
                f"Hold yer seahorses, {user.mention}! Only pirates of higher rank can show off their loot (images). Keep plunderin' and level up!",
                f"Yo ho ho, {user.mention}! Ye need to rank up to unfurl yer map (share images). Hoist yer Jolly Roger higher!"
            ],
            "restricted_channel": [
                f"Gaaar! {user.mention}, this be a restricted part of the ship. Only crew members of a certain rank can enter these waters!",
                f"Avast, {user.mention}! This channel be for certain ranked crew members only. Swab the poop deck and come back when ye've earned yer stripes!",
                f"Blimey, {user.mention}! This be the captain's quarters (restricted channel). Ye'll be keel-hauled if ye try to enter without permission!"
            ]
        }
    
        themed_message = random.choice(messages[message_type])
        
        if role is not None:
            themed_message = themed_message.replace("higher rank", f"the rank of {role.name} or higher")
            themed_message = themed_message.replace("certain rank", f"ranked {role.name} or higher")
        
        await channel.send(themed_message, delete_after=15)

            
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Event listener to catch manual mute role removals."""
        mute_role = before.guild.get_role(self.mute_role_id)
        if not mute_role:
            return

        if mute_role in before.roles and mute_role not in after.roles:
            # The mute role was manually removed
            await self._restore_roles(after, "Manual unmute detected")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def send_server_rules(self, ctx, channel: discord.TextChannel = None):
        """Send the full server rules and information to the specified channel."""
        if channel is None:
            channel = ctx.channel

        rules = """
# 🏴‍☠️ Grand Line Pirates' Code of Conduct 🏴‍☠️

Ahoy, fellow pirates! Welcome aboard the Grand Line Discord Server. Before ye set sail on this grand adventure, make sure to familiarize yourself with our code of conduct and Discord's Terms of Service. Remember, even pirates have rules to follow!

## 📜 Discord Terms of Service

All crew members must adhere to Discord's Terms of Service. Here are some key points:

- 🔞 You must be at least 13 years old to use Discord
- 🚫 No harassment, hate speech, or extreme political content
- 🔒 Respect others' privacy and intellectual property
- 🛡️ Don't share or promote harmful content or illegal activities
- 🤖 Don't use self-bots or user-bots

For the full terms, visit: [Discord Terms of Service](https://discord.com/\u200Bterms)

## 🏴‍☠️ Server Rules (Applies to all crew members, from cabin boys to Yonko)

1. 🤝 Respect yer fellow pirates. Swearing be allowed, but mind yer tongue and respect others' boundaries.
2. 🤐 Sensitive topics such as politics, religion, or personal matters are off-limits. Keep 'em in Davy Jones' locker!
3. 🌈 No discriminatin' against race, religion, or background. We be a diverse crew, savvy?
4. 🔇 No spammin' outside the designated areas. Don't make us walk ye off the plank!
5. 📢 Advertisin' other pirate crews (Discord servers) without permission is mutiny. Ye've been warned!
6. 🤫 Keep manga spoilers in the appropriate channels. Don't ruin the adventure for others!
7. 💡 Respect others' ideas and theories. Ask permission and give credit where it's due.
8. 📖 Read the channel topics before postin'. They contain valuable treasure maps of information!
9. 🔞 No NSFW content. Keep it family-friendly, ye scurvy dogs!
10. 👨‍⚖️ The Moderators and Admins have the final say in disputes. Respect their authority or face the consequences!
"""

        rules_part2 = """
## ⚓ Consequences for Breakin' the Code

1. ⚠️ First offense: Ye'll get a warnin' shot across the bow
2. 🔇 Second offense: Ye'll be thrown in the brig (muted)
3. 🏝️ Third offense: Ye'll be marooned (banned)

## 👑 Crew Hierarchy

- 👑 Pirate King: Server Owner
- ⭐️ Yonko: High-ranking Administrators
- ⚓️ Admirals: Senior Moderators
- 💎 Legends: Trusted friends and partners
- 👑 Shichibukai: Novice Moderators
"""

        rules_part3 = """
## 🌊 Choose Your Sea

Join one of the five seas from One Piece:
- ⭕ Grand Line 
- 🔵 East Blue 
- ⚪ West Blue 
- ⚫ North Blue 
- 🔴 South Blue 

Select your sea in the designated channel to participate in sea tournaments!

## 🏴‍☠️ Join a Pirate Crew

Enlist in one of our fearsome pirate crews:
- 🕷️ Phantom Troupe
- 🦊 Foxy Pirates
- 🐉 Revolutionary Army

Each crew has 4 ranks: Cabin Boy, First Mate, Commander, and Right Hand

## 📈 Pirate Ranking System


Now, hoist the colors and set sail for adventure! If ye have any questions, consult yer Log Pose (ping a moderator). May the winds be ever in yer favor! ⛵🌊🏝️
"""

        chunks = [rules, rules_part2, rules_part3]

        try:
            for chunk in chunks:
                await channel.send(chunk)
            await ctx.send(f"Full server rules and information sent to {channel.mention}!")
        except discord.Forbidden:
            await ctx.send("I don't have permission to send messages in that channel!")
        except discord.HTTPException:
            await ctx.send("There was an error sending the rules. Please try again later.")
            
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
    await cog.initialize()

async def teardown(bot):
    global original_commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
