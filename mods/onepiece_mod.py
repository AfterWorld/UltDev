import discord
from discord.ext import commands, tasks
from discord.errors import Forbidden, HTTPException
from redbot.core import commands, checks, modlog, Config
from redbot.core.utils.chat_formatting import humanize_list, humanize_timedelta
from redbot.core.utils.mod import get_audit_reason
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.chat_formatting import inline, bold
from redbot.core.i18n import Translator
from redbot.core.bot import Red
from datetime import timedelta, datetime, timezone
from dataclasses import dataclass
import asyncio
import re
import random
import pytz
import logging
from typing import Optional, List, Union, Dict, TypedDict, Union

_ = Translator("OnePieceMod", __file__)

original_commands = {}

@dataclass
class MuteResponse:
    success: bool
    reason: Optional[str]
    user: discord.Member

class OnePieceMod(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "muted_users": {},
            "banned_words": [],
            "banned_word_strikes": {},
            "mute_role": None,
            "mod_log_channel": None,
            "general_channel": None,
            "notification_channel": None,
            "muted_users": {},
            "default_time": 0,
            "dm": False,
            "show_mod": False,
        }
        self.config.register_guild(**default_guild)
        self.reminder_task = None
        self.start_tasks()
        self._server_mutes = {}  # Add this line
        self.bot.loop.create_task(self.initialize())
        self.mute_tasks = {}
        self.check_mutes.start()
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
            ("Big Mom's Soul-Soul Fruit has taken your lifespan... and your server access!", "https://tenor.com/view/%E5%A4%A7%E5%AA%BDauntie-aunt-granny-grandmom-gif-12576437"),
            ("Silence… Kidd Fan :LuffyTRUTH:","https://tenor.com/view/shanks-one-piece-divine-departure-kamusari-kid-gif-2484508146019442683")
        ]

    async def initialize(self):
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            muted_users = guild_data.get("muted_users", {})
            self._server_mutes[guild_id] = muted_users

    def cog_unload(self):
        self.check_mutes.cancel()
        global original_commands
        for cmd_name, cmd in original_commands.items():
            if self.bot.get_command(cmd_name):
                self.bot.remove_command(cmd_name)
            if cmd:
                self.bot.add_command(cmd)
        original_commands.clear()
        
    def start_tasks(self):
        self.reminder_task = self.bot.loop.create_task(self.send_periodic_reminder())

    def cog_unload(self):
        if self.reminder_task:
            self.reminder_task.cancel()

    @staticmethod
    def parse_timedelta(time_string: str) -> Optional[timedelta]:
        if not time_string:
            return None
        try:
            # Remove all whitespace and convert to lowercase
            time_string = "".join(time_string.split()).lower()
            total_seconds = 0
            current_number = ""
            for char in time_string:
                if char.isdigit():
                    current_number += char
                elif char in ['s', 'm', 'h', 'd', 'w']:
                    if not current_number:
                        raise ValueError("Invalid time format")
                    number = int(current_number)
                    if char == 's':
                        total_seconds += number
                    elif char == 'm':
                        total_seconds += number * 60
                    elif char == 'h':
                        total_seconds += number * 3600
                    elif char == 'd':
                        total_seconds += number * 86400
                    elif char == 'w':
                        total_seconds += number * 604800
                    current_number = ""
                else:
                    raise ValueError("Invalid time format")
            if current_number:
                raise ValueError("Invalid time format")
            return timedelta(seconds=total_seconds)
        except ValueError:
            return None

    async def send_periodic_reminder(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                guild = self.bot.get_guild(374126802836258816)  # Replace with your guild ID
                if not guild:
                    continue

                channel_id = await self.config.guild(guild).general_channel()
                channel = guild.get_channel(channel_id)
                if channel:
                    reminder = self.get_random_reminder()
                    await channel.send(reminder)

                # Wait for 6 hours before sending the next reminder
                await asyncio.sleep(6 * 60 * 60)  # 6 hours in seconds
            except Exception as e:
                print(f"Error in send_periodic_reminder: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before trying again if there's an error

    async def _send_dm_notification(
        self,
        user: Union[discord.User, discord.Member],
        moderator: Optional[Union[discord.User, discord.Member]],
        guild: discord.Guild,
        mute_type: str,
        reason: Optional[str],
        duration: Optional[timedelta] = None,
    ):
        if user.bot:
            return
    
        if not await self.config.guild(guild).dm():
            return
    
        show_mod = await self.config.guild(guild).show_mod()
        title = bold(mute_type)
        if duration:
            duration_str = humanize_timedelta(timedelta=duration)
            until = datetime.now(timezone.utc) + duration
            until_str = discord.utils.format_dt(until)
    
        if moderator is None:
            moderator_str = _("Unknown")
        else:
            moderator_str = str(moderator)
    
        if not reason:
            reason = _("No reason provided.")
    
        embed = discord.Embed(
            title=title,
            description=reason,
            color=await self.bot.get_embed_color(user),
        )
        embed.timestamp = datetime.now(timezone.utc)
        if duration:
            embed.add_field(name=_("Until"), value=until_str)
            embed.add_field(name=_("Duration"), value=duration_str)
        embed.add_field(name=_("Guild"), value=guild.name, inline=False)
        if show_mod:
            embed.add_field(name=_("Moderator"), value=moderator_str)
    
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass  # Can't send DM to the user

    @tasks.loop(minutes=5)
    async def check_mutes(self):
        for guild in self.bot.guilds:
            muted_users = await self.config.guild(guild).muted_users()
            for user_id, mute_data in list(muted_users.items()):
                if mute_data["until"]:
                    until = mute_data["until"]
                    if isinstance(until, str):
                        until = datetime.fromisoformat(until)
                    elif isinstance(until, (int, float)):
                        until = datetime.fromtimestamp(until, tz=timezone.utc)
                    else:
                        continue  # Skip if the format is unrecognized
    
                    if until <= datetime.now(timezone.utc):
                        user = guild.get_member(int(user_id))
                        if user:
                            await self.unmute_user(guild, user, "Automatic unmute: mute duration expired")

    async def _check_for_mute_role(self, ctx: commands.Context) -> bool:
        """
        This explains to the user whether or not mutes are setup correctly for
        automatic unmutes.
        """
        command_1 = f"{ctx.clean_prefix}muteset role"
        command_2 = f"{ctx.clean_prefix}muteset makerole"
        msg = _(
            "This server does not have a mute role setup. "
            "You can setup a mute role with {command_1} or"
            " {command_2} if you just want a basic role created setup.\n\n"
        ).format(
            command_1=inline(command_1),
            command_2=inline(command_2),
        )
        mute_role_id = await self.config.guild(ctx.guild).mute_role()
        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            await ctx.send(msg)
            return False
    
        return True

    async def is_allowed_by_hierarchy(self, guild: discord.Guild, mod: discord.Member, user: discord.Member):
        is_special = mod == guild.owner or await self.bot.is_owner(mod)
        return mod.top_role > user.top_role or is_special

    async def mute_user(
        self,
        guild: discord.Guild,
        author: discord.Member,
        user: discord.Member,
        until: Optional[datetime] = None,
        reason: Optional[str] = None,
    ) -> MuteResponse:
        """
        Handles muting users
        """
        ret: MuteResponse = MuteResponse(success=False, reason=None, user=user)
    
        if user.guild_permissions.administrator:
            ret.reason = "Cannot mute an administrator."
            return ret
        if not await self.is_allowed_by_hierarchy(guild, author, user):
            ret.reason = "You are not higher than the user in the role hierarchy."
            return ret
        
        mute_role_id = await self.config.guild(guild).mute_role()
        mute_role = guild.get_role(mute_role_id)
    
        if not mute_role:
            ret.reason = "Mute role not found."
            return ret
        
        if author != guild.owner and mute_role >= author.top_role:
            ret.reason = "The mute role is higher than your highest role."
            return ret
        if not guild.me.guild_permissions.manage_roles:
            ret.reason = "I don't have 'Manage Roles' permission."
            return ret
        if mute_role >= guild.me.top_role:
            ret.reason = "The mute role is higher than my highest role."
            return ret
        
        # Store current roles
        current_roles = [role for role in user.roles if role != guild.default_role and role != mute_role]
        
        try:
            if guild.id not in self._server_mutes:
                self._server_mutes[guild.id] = {}
    
            self._server_mutes[guild.id][user.id] = {
                "author": author.id,
                "member": user.id,
                "until": until.timestamp() if until else None,
                "roles": [r.id for r in current_roles]
            }
            
            # Remove all roles except @everyone and add mute role
            await user.edit(roles=[mute_role], reason=reason)
            await self.config.guild(guild).muted_users.set(self._server_mutes[guild.id])
    
            if user.voice:
                try:
                    await user.move_to(user.voice.channel)
                except discord.HTTPException:
                    ret.reason = "Couldn't move user in voice channel."
            ret.success = True
        except discord.errors.Forbidden:
            if guild.id in self._server_mutes and user.id in self._server_mutes[guild.id]:
                del self._server_mutes[guild.id][user.id]
            ret.reason = "I don't have permission to edit this user's roles."
        except discord.errors.HTTPException as e:
            if guild.id in self._server_mutes and user.id in self._server_mutes[guild.id]:
                del self._server_mutes[guild.id][user.id]
            ret.reason = f"An HTTP error occurred: {str(e)}"
        
        return ret

    async def unmute_user(
        self,
        guild: discord.Guild,
        user: discord.Member,
        reason: Optional[str] = None,
    ) -> Dict[str, Union[bool, str]]:
        """Handles returning users from the Void Century"""
        ret = {"success": False, "reason": None}
    
        mute_role_id = await self.config.guild(guild).mute_role()
        if not mute_role_id:
            ret["reason"] = "The Void Century role is not set! Use [p]setmuterole to set it."
            return ret
    
        mute_role = guild.get_role(mute_role_id)
        if not mute_role:
            ret["reason"] = "The Void Century role has vanished like a mirage! Alert the captain!"
            return ret
    
        if mute_role not in user.roles:
            ret["reason"] = f"{user.name} isn't trapped in the Void Century. They're free as a seagull!"
            return ret
    
        try:
            roles_to_restore = []
            if guild.id in self._server_mutes and str(user.id) in self._server_mutes[guild.id]:
                for role_id in self._server_mutes[guild.id][str(user.id)]["roles"]:
                    role = guild.get_role(role_id)
                    if role and role < guild.me.top_role and role != mute_role:
                        roles_to_restore.append(role)
            
            await user.edit(roles=roles_to_restore, reason=f"Unmuting user: {reason}")
            
            if guild.id in self._server_mutes and str(user.id) in self._server_mutes[guild.id]:
                del self._server_mutes[guild.id][str(user.id)]
                await self.config.guild(guild).muted_users.set(self._server_mutes[guild.id])
    
            ret["success"] = True
        except discord.Forbidden as e:
            ret["reason"] = f"The Sea Kings prevent me from managing roles! Error: {e}"
        except discord.HTTPException as e:
            ret["reason"] = f"A mysterious force interferes with the unmute! Error: {e}"
        except Exception as e:
            ret["reason"] = f"An unexpected tempest disrupts the unmute! Error: {e}"
        return ret

    async def schedule_unmute(self, guild: discord.Guild, user: discord.Member, duration: timedelta):
        async def unmute_later():
            await asyncio.sleep(duration.total_seconds())
            await self.unmute_user(guild, user, "Automatic unmute: mute duration expired")

        task = asyncio.create_task(unmute_later())
        if guild.id not in self.mute_tasks:
            self.mute_tasks[guild.id] = {}
        self.mute_tasks[guild.id][user.id] = task

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
        
    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setreminderchannel(self, ctx, channel: discord.TextChannel):
        """Set the channel for periodic reminders."""
        await self.config.guild(ctx.guild).general_channel.set(channel.id)
        await ctx.send(f"Reminder channel set to {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def sendreminder(self, ctx):
        """Manually send a reminder to the set channel."""
        channel_id = await self.config.guild(ctx.guild).general_channel()
        channel = ctx.guild.get_channel(channel_id)
        if channel:
            reminder = self.get_random_reminder()
            await channel.send(reminder)
            await ctx.send("Reminder sent!")
        else:
            await ctx.send("Reminder channel not set or not found.")

    @commands.command(usage="<users...> [duration] [reason]")
    @commands.guild_only()
    @commands.mod_or_permissions(manage_roles=True)
    async def mute(
        self,
        ctx: commands.Context,
        users: commands.Greedy[discord.Member],
        duration: Optional[str] = None,
        *,
        reason: Optional[str] = None,
    ):
        """Mute users.
    
        `<users...>` is a space separated list of usernames, ID's, or mentions.
        `[duration]` is the amount of time to mute for. Time units are s(econds), m(inutes), h(ours), d(ays), w(eeks).
        `[reason]` is the reason for the mute.
    
        Examples:
        `[p]mute @member1 @member2 5h spam`
        `[p]mute @member 3d`
        """
        if not users:
            return await ctx.send_help()
        if ctx.me in users:
            return await ctx.send(_("You cannot mute me."))
        if ctx.author in users:
            return await ctx.send(_("You cannot mute yourself."))
    
        if not await self._check_for_mute_role(ctx):
            return
    
        mute_time = self.parse_timedelta(duration)  # Use self.parse_timedelta instead of parse_timedelta
        if duration and not mute_time:
            return await ctx.send(_("Invalid time format. Try `5h` or `1d`."))
        
        until = None
        if mute_time:
            until = ctx.message.created_at + mute_time
    
        async with ctx.typing():
            author = ctx.message.author
            guild = ctx.guild
            audit_reason = get_audit_reason(author, reason, shorten=True)
            success_list = []
            issue_list = []
            for user in users:
                result = await self.mute_user(guild, author, user, until, audit_reason)
                if result.success:
                    success_list.append(user)
                    await modlog.create_case(
                        self.bot,
                        guild,
                        ctx.message.created_at,
                        "smute",
                        user,
                        author,
                        reason,
                        until=until,
                        channel=None,
                    )
                    await self._send_dm_notification(
                        user, author, guild, _("Server mute"), reason, mute_time
                    )
                else:
                    issue_list.append(result)
    
        if success_list:
            if ctx.guild.id not in self._server_mutes:
                self._server_mutes[ctx.guild.id] = {}
            if mute_time:
                time = _(" for {duration}").format(duration=humanize_timedelta(timedelta=mute_time))
            else:
                time = ""
            msg = _("{users} has been muted in this server{time}.")
            if len(success_list) > 1:
                msg = _("{users} have been muted in this server{time}.")
            await ctx.send(
                msg.format(users=humanize_list([f"`{u}`" for u in success_list]), time=time)
            )
    
        if success_list:
            pirate_messages = [
                f"Yohohoho! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been silenced like Brook without his voice box {time}! The sudden silence caused Brook to panic and play his guitar at max volume, shattering all the mirrors in the Whole Cake Chateau. Now Big Mom can't admire her new hairdo, Brulee's mirror world is in chaos, and somehow, Absalom's invisibility has stopped working.",
                
                f"Great Scott! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been sent to the Calm Belt of chat {time}! Not even a Den Den Mushi can reach {'them' if len(success_list) > 1 else 'them'}. The resulting silence has lulled all the Sea Kings to sleep, causing a massive traffic jam of Marine ships. Garp is now giving a loud lecture on justice, ironically waking up the Sea Kings and causing general pandemonium.",
                
                f"Holy Merry! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} been caught in Foxy's Noro Noro Beam {time}! {'Their' if len(success_list) > 1 else 'Their'} messages will be slowed to a crawl. The beam reflected off Franky's super shiny robot body, accidentally slowing down Aokiji's ice powers. Now Punk Hazard is slowly defrosting, Caeser Clown's experiments are melting, and Trafalgar Law is wondering why his 'Room' is expanding at a snail's pace.",
                
                f"Gomu Gomu no Silence! {humanize_list([f'`{u}`' for u in success_list])} {'has' if len(success_list) == 1 else 'have'} had {'their' if len(success_list) > 1 else 'their'} chat privileges stretched to the limit {time}! Luffy's arms got tangled in the process, turning him into a giant rubber band. Now Usopp's using him as a slingshot to launch Chopper across the Grand Line for emergency medical house calls, while Zoro's trying to cut Luffy free but keeps getting lost between his stretched fingers.",
                
                f"Mamamama! Big Mom has stolen the voice of {humanize_list([f'`{u}`' for u in success_list])} and put it in her collection {time}! She's using it as a ringtone for her Den Den Mushi. The new ringtone is so catchy that all of Totto Land is dancing uncontrollably. Katakuri's trying to predict the next beat, Pudding's memory-wiping everyone who saw her trip during her dance solo, and Streusen's accidentally baked a ten-layer cake in rhythm.",
                
                f"Zoro got lost again and accidentally led {humanize_list([f'`{u}`' for u in success_list])} into the Void Century {time}! Good luck finding your way back... maybe ask someone with a better sense of direction? Like a potato. The World Government is in panic mode, Imu is furiously scribbling 'DO NOT ENTER' signs, and the Five Elders are seriously considering hiring Zoro as their new security system. Meanwhile, Robin's having a field day deciphering the Poneglyphs Zoro accidentally uncovered.",
                
                f"Sanji's Diable Jambe was too hot! It burned {humanize_list([f'`{u}`' for u in success_list])}'s keyboard to a crisp {time}! On the bright side, their computer setup is now 'toast'... literally. The fire spread to Nami's tangerine grove, but instead of burning, it caramelized all the fruits. Now Luffy won't stop eating them, Chopper's panicking about potential sugar rush, and Sanji's creating a new recipe for 'Flambéed Tangerine Love Hurricane' in honor of his beloved Nami-swan.",
                
                f"Crocodile's sand has dried up the ink in {humanize_list([f'`{u}`' for u in success_list])}'s pen {time}. No more writing for you! Time to communicate via interpretive dance. The sand storm has spread across the Grand Line, turning every island into a beach paradise. Buggy's sandals got stuck, his feet detached, and now his crew is chasing them across the New World. Meanwhile, Aokiji's building the world's largest sand castle and Blackbeard's complaining about sand in his beard.",
                
                f"Usopp's latest invention, the 'Shut-Up-A-Pirate 3000', worked perfectly on {humanize_list([f'`{u}`' for u in success_list])} {time}! The shock of his success caused Usopp to faint, accidentally launching a Pop Green that grew into a beanstalk reaching Skypiea. Now Enel's trying to slide down it back to Earth, Nami's calculating the profit from a sky-high toll booth, and God Usopp's follower count just broke the Internet.",
                
                f"Chopper's Rumble Ball had an odd effect on {humanize_list([f'`{u}`' for u in success_list])}. {'They' if len(success_list) > 1 else 'They'} can't type {time}! Instead, {'they`re' if len(success_list) > 1 else 'they`re'} stuck making adorable reindeer noises. The cuteness overload caused Bartholomew Kuma to malfunction, shooting Pacifistas filled with cotton candy across the Grand Line. Now Perona's negative hollows are turning suspiciously positive, Moria's zombies are having a sugar-fueled dance party, and Doflamingo's strings have turned into licorice whips.",
                
                f"Robin sprouted hands all over {humanize_list([f'`{u}`' for u in success_list])}'s keyboard, preventing {'them' if len(success_list) > 1 else 'them'} from typing {time}! Now their keyboard just keeps typing 'hand hand hand hand'. The hands have taken over the ship, forming a giant mecha that's now challenging Queen's dinosaur form to a robot dance-off. Franky's taking notes for his next super upgrade, while Brook's providing the soundtrack with his new hit single, 'Hands Up for Adventure'.",
                
                f"Franky performed a SUPER mute on {humanize_list([f'`{u}`' for u in success_list])} {time}! Cola-powered silence! Side effects may include spontaneous posing and an irresistible urge to yell 'SUPER!' The excess cola fumes have turned all the fish in the area into hyperactive disco dancers. Now Jinbe's trying to coral them into formation for an underwater musical, Sanji's inventing new recipes for 'Jitterbug Jellyfish Jambalaya', and the Kraken's become a master of the Swim Swim fruit... dance, that is.",
                
                f"Jinbei's Fish-Man Karate sent {humanize_list([f'`{u}`' for u in success_list])} flying into the Void Century {time}! They`re now best friends with Joy Boy, apparently. The shockwave from his karate chop traveled through time, giving Toki's time-time fruit a hiccup. Now Momonosuke is randomly shifting between baby and adult dragon forms, the Nine Red Scabbards are trying to childproof Wano for their time-jumping lord, and Kaido is very confused about why his intimidating roars keep turning into baby dragon squeaks.",
                
                f"Nami's Thunder Tempo has short-circuited {humanize_list([f'`{u}`' for u in success_list])}'s communication devices {time}! The resulting power surge overcharged Franky's hair, causing a worldwide shortage of cola. This led to Luffy raiding Chopper's cotton candy supply, Sanji stress-baking until he filled Whole Cake Island with cream puffs, and Pudding having to erase everyone's memories of ever liking cola. Meanwhile, Zoro's somehow gotten lost in Nami's electric currents and ended up in the One Piece live-action set.",
                
                f"Buggy's Chop-Chop Fruit accidentally divided {humanize_list([f'`{u}`' for u in success_list])}'s messages into tiny, unreadable pieces {time}! We're still trying to put them back together, but some parts seem to have floated away. In the chaos, Buggy's nose landed on Usopp's face, giving him unprecedented lying powers. His tall tales are now coming true, causing Marines to believe in the existence of a giant gold-pooping beetle. Garp is leading an expedition to find it, much to Sengoku's frustration.",
                
                f"Trafalgar Law's ROOM has temporarily removed {humanize_list([f'`{u}`' for u in success_list])}'s ability to communicate {time}! He's replaced it with the ability to make really bad puns. Heart-breaking, isn't it? The puns are so bad They`re causing physical pain, making Chopper rush around trying to cure this new 'disease'. Bepo's actually loving it, much to the horror of the Heart Pirates. Meanwhile, Caesar Clown is trying to weaponize the puns for his next evil scheme.",
                
                f"Blackbeard's Dark-Dark Fruit has swallowed {humanize_list([f'`{u}`' for u in success_list])}'s messages into a void {time}! Rumor has it, you can still hear the echoes if you listen closely to a black hole. The void started sucking in everything dark, including Zoro's dark aura when he gets lost. Now Zoro's stuck orbiting Blackbeard, using his swords as oars, while Perona's negative hollows are getting a tan from the darkness absorption. Van Augur's having the time of his life using the void as a portal for trick shots across the Grand Line.",
                
                f"Doflamingo's strings have tied up {humanize_list([f'`{u}`' for u in success_list])}'s fingers, preventing {'them' if len(success_list) > 1 else 'them'} from typing {time}! On the bright side, {'they`ve' if len(success_list) > 1 else 'they`ve'} never looked more fabulous in pink feathers. The excess string has turned Dressrosa into a giant cat's cradle. King is stuck thinking it's some kind of advanced interrogation technique, Charlotte Smoothie is trying to juice the strings for a new cocktail, and Leo of the Tontatta Tribe is having a field day with his new sewing materials.",
                
                f"Gecko Moria's shadows have stolen {humanize_list([f'`{u}`' for u in success_list])}'s ability to chat {time}! Now their shadows are having a great conversation without them. The shadowless users have teamed up with Brook to form the world's first transparent band. Their music is so soul-stirring it's causing Moria's zombie army to break out in a thriller dance. Perona's ghosts are working as special effects, and Absalom's reporting on it while invisible, leading to floating cameras all over Thriller Bark.",
                
                f"Aokiji's Ice Age has frozen {humanize_list([f'`{u}`' for u in success_list])}'s keyboard solid {time}! Might we suggest defrosting it with Ace's Flame-Flame Fruit? ...Oh, too soon? The sudden cold snap has turned all of Water 7 into a giant ice rink. Franky's redesigning the Sea Train with ice skates, Kokoro's Mermaid Cafe is now an igloo, and the Galley-La shipwrights are carving galleons out of ice. Meanwhile, Aokiji's been mistaken for a very lazy ice sculptor and entered into Iceburg's winter festival competition.",
                
                f"Kizaru moved at the speed of light and unplugged {humanize_list([f'`{u}`' for u in success_list])}'s internet connection {time}! He would plug it back in, but that sounds like a lot of work. In his haste, Kizaru accidentally caused a worldwide blackout. Now Enel's moonlight is the only source of electricity, making him feel like a god again. Rayleigh's haki training has turned into 'catch the light beams', and Sentomaru's so fed up he's considering leaving the Marines to become a candlemaker.",
                
                f"Kaido's Blast Breath melted {humanize_list([f'`{u}`' for u in success_list])}'s chat privileges {time}! We'd offer them a new keyboard, but Kaido drank all the money we were going to use to buy it. The heat from Kaido's breath turned Wano into a sauna. Queen's now running a luxury spa for Beasts Pirates, King's flame powers are being used to keep the towels warm, and Jack's stuck as the pool boy. Meanwhile, Yamato's hosting snowball fights with her ice powers to help everyone cool down.",
                
                f"Marco the Phoenix's blue flames have temporarily incinerated {humanize_list([f'`{u}`' for u in success_list])}'s chat access {time}! Don't worry, it'll regenerate... eventually. The blue flames spread across the Moby Dick, turning it into a ghost ship. Now Whitebeard's mustache is glowing blue, Jozu's diamond form is refracting the light into a disco ball effect, and Thatch is cooking with eternal fire. Vista's rose petals have turned into blue fire butterflies, creating the world's most dangerous garden.",
                
                f"Ivankov's hormones have mysteriously changed {humanize_list([f'`{u}`' for u in success_list])}'s voice, making it impossible to type {time}! {'They`re' if len(success_list) > 1 else 'They`re'} now communicating exclusively in fabulous winks. The hormone burst has affected all of Kamabakka Kingdom. Sanji's okama disguise is now permanent, Mr. 2 Bon Clay is stuck in a never-ending series of face changes, and somehow, Crocodile is blushing. The Revolutionary Army isn't sure whether to be amused or very, very concerned.",
                
                f"Bartolomeo's Barrier Fruit has cut off {humanize_list([f'`{u}`' for u in success_list])} from the chat {time}! He says he'll take it down if you can get him Luffy's autograph. The barrier expanded to cover all of Dressrosa, turning it into a giant bounce house. Cavendish is using it as a beauty sleep chamber, Rebecca's Colosseum fights have turned into sumo matches, and King Riku is seriously considering this as a permanent national defense system. Meanwhile, Pica's voice is echoing hilariously off the barrier walls.",
                
                f"Enel's lightning struck {humanize_list([f'`{u}`' for u in success_list])}'s computer, causing a temporary blackout {time}! Their new electric personality is quite shocking. The lightning overcharged the Ark Maxim, sending it crashing back to the Blue Sea. Now Enel's stuck running a tech support hotline for Den Den Mushi, the Skypieans are trying to explain clouds to very confused fish, and Wiper's trying to conquer the ocean with his Burn Bazooka, creating the world's largest jacuzzi.",
                
                f"Garp threw his Fist of Love, knocking {humanize_list([f'`{u}`' for u in success_list])} out of the chat {time}! That's what we call 'tough love'... emphasis on the 'tough'. The shockwave from Garp's fist circled the globe, giving everyone a momentary sense of Marine-induced guilt. Sengoku's goat ate the resulting wave of paper apologies, turning it into a Zoan-type 'Guilt-Guilt Fruit' user. Now the goat's making even Akainu question his life choices, Luffy's actually considering becoming a Marine, and Coby's promotion to Admiral is being fast-tracked.",
            
                f"Mihawk's sword slash was so precise, it cut {humanize_list([f'`{u}`' for u in success_list])}'s chat connection {time}! He was aiming for a fly, but you know how it goes. The slash continued across the Grand Line, accidentally giving everyone perfect haircuts. Buggy's nose hair got trimmed, allowing him to smell the One Piece. Now the Red-Haired Pirates and the Buggy Pirates are in a sniffing race, Zoro's swords are demanding a style upgrade, and Sanji's somehow gotten his eyebrow un-curled.",
            
                f"Magellan's Venom Demon has poisoned {humanize_list([f'`{u}`' for u in success_list])}'s chatting ability {time}! Side effects include an extreme case of verbal diarrhea... ironically. The poison seeped into Impel Down's plumbing, turning the underwater forest into a psychedelic wonderland. Now Hannyabal's impersonating Magellan but with tie-dye skin, Sadi-chan's whip is spouting motivational quotes, and Ivankov's declaring it the new paradise of 'free self-expression'. The World Government is not amused.",
            
                f"Perona's Negative Hollow made {humanize_list([f'`{u}`' for u in success_list])} too depressed to type {time}! {'They`re' if len(success_list) > 1 else 'They`re'} currently under their desk, mumbling about being reborn as a lint roller. The negativity spread across Thriller Bark, making even the zombies too depressed to fight. Gecko Moria's now running a support group for 'Shadows with Low Self-Esteem', Absalom's invisible tears are causing mysterious indoor rain, and Kumacy's finally expressing his true feelings through nihilistic poetry.",
            
                f"Caesar Clown's Gastinet made the air around {humanize_list([f'`{u}`' for u in success_list])} unbreathable, forcing {'them' if len(success_list) > 1 else 'them'} to retreat from chat {time}! Their last message was just a series of coughs and 'SHURORORORO'. The gas expanded, turning Punk Hazard into a giant bouncy castle. Now Trafalgar Law's 'Room' is full of giggling Straw Hats, Smoker's smoke is coming out in balloon animals, and Vegapunk's long-distance Den Den Mushi are transmitting nothing but laugh tracks.",
            
                f"Fujitora's gravity crushed {humanize_list([f'`{u}`' for u in success_list])}'s keyboard {time}, making typing impossible! They`re now communicating via interpretive meteor showers. The altered gravity caused Zunisha to start moonwalking across the New World. Now Jack's seasick, the Mink Tribe is hosting anti-gravity raves, and Raizo's ninja scrolls keep floating away. Meanwhile, Fujitora's trying to convince everyone it's a new form of 'Celestial Navigation'.",
            
                f"Sengoku's Buddha shockwave sent {humanize_list([f'`{u}`' for u in success_list])} flying out of the chat room {time}! We expect {'them' if len(success_list) > 1 else 'them'} to achieve enlightenment any day now. The shockwave resonated with all the gold in Mary Geoise, turning the Holy Land into a giant tuning fork. Now Imu's trying to conduct the world's largest celestial orchestra, the Gorosei are vibrating in perfect harmony, and Charlos's bubble helmet has become a floating sound booth. Donquixote Mjosgard is surprisingly into it.",
            
                f"Borsalino's light speed kick launched {humanize_list([f'`{u}`' for u in success_list])} into a communication dead zone {time}! He would've brought {'them' if len(success_list) > 1 else 'them'} back, but that sounds like eeeeffort~. The kick tore a hole in the space-time continuum, causing past and future versions of pirates to appear randomly. Now Luffy's getting meat-eating tips from his future self, Blackbeard's trying to steal devil fruits from his past self, and Buggy's past and future selves are forming an endless circus line.",
            
                f"Bonney's Age-Age Fruit regressed {humanize_list([f'`{u}`' for u in success_list])} to an age before they could type {time}! {'They`re' if len(success_list) > 1 else 'They`re'} currently teething on the keyboard. The age regression spread across Sabaody, turning it into a giant daycare. Rayleigh's teaching Haki to toddlers, Shakky's bar is now serving juice boxes, and the Human Auction House is hosting nap time. Kid Doflamingo is having a tantrum because his sunglasses don't fit, while baby Kuma is crawling around with a miniature Bible.",
            
                f"Queen's Plague Rounds infected {humanize_list([f'`{u}`' for u in success_list])}'s chat privileges with silence {time}! The only cure is to dance like no one's watching... because They`re not. They can't see you. The virus mutated, turning everyone in Wano into funk soul brothers. Now Kaido's Beast Pirates are having a dance-off against the Nine Red Scabbards, Orochi's hair snakes are doing the conga, and Yamato's ice powers are being used to create a giant disco ball. Kin'emon's clothes are changing faster than John Travolta in Saturday Night Fever.",
            
                f"Shirahoshi accidentally called a Sea King, who ate {humanize_list([f'`{u}`' for u in success_list])}'s messages {time}! The Sea King is now the most well-informed creature in the ocean. Poseidon's powers went into overdrive, summoning all the Sea Kings to Fishman Island for a ted talk. Now Hody Jones is the reluctant audio-visual guy, Vander Decken IX is trying to throw love letters at the Sea King's non-existent hands, and Neptune's turned the whole thing into a music festival called 'Sea-chella'.",
            
                f"Corazon's Silent-Silent Fruit failed spectacularly, causing him to trip and unplug {humanize_list([f'`{u}`' for u in success_list])}'s computer(s) {time}! As he silently screamed, he accidentally knocked over Vegapunk's latest experiment. The resulting explosion turned all Den Den Mushi into break-dancing snails, leaving the Marines to communicate via interpretative dance. Somewhere in the New World, Doflamingo is laughing so hard he's tangled in his own strings.",
            
                f"Hody Jones' Energy Steroids caused {humanize_list([f'`{u}`' for u in success_list])} to rage-quit the chat {time}! {'They' if len(success_list) > 1 else 'They'} punched through their monitor in a fit of steroid-induced fury. The steroids seeped into the ocean, turning all the fish into bodybuilders. Now Jinbe's teaching an underwater aerobics class, Arlong Park has been converted into a protein shake bar, and Sanji's having a existential crisis over how to delicately prepare a fish with biceps.",
            
                f"Kuma's Paw-Paw Fruit has deflected all of {humanize_list([f'`{u}`' for u in success_list])}'s messages {time}! {'They`re' if len(success_list) > 1 else 'They`re'} expected to land somewhere in the chat... in about 3 days. The deflected messages gained sentience during their flight, forming a new Sky Island made entirely of floating text. Now Urouge's trying to decipher the wisdom of the chat gods, Enel's planning to conquer it with his 'divine grammar', and Nami's calculating the profit margins on selling punctuation to the locals.",
            
                f"Capone Bege trapped {humanize_list([f'`{u}`' for u in success_list])} inside his body fortress, cutting off their communication {time}! They`re currently lost somewhere between his pancreas and his spleen. Bege's body has turned into a funhouse of rooms, each themed after a different pirate crew. Now Big Mom's rampaging through his sweet tooth, Kaido's trying to turn his liver into Onigashima, and somehow Luffy's found the meat storage. Bege's really regretting skipping those anatomy classes.",
            
                f"Hawkins' Straw-Straw Fruit has predicted a period of silence for {humanize_list([f'`{u}`' for u in success_list])} {time}! The cards also predict they'll stub their toe later. Ouch. The prediction caused a butterfly effect of self-fulfilling prophecies across the New World. Now Kaido's avoiding high places, Big Mom's on a diet, and Blackbeard's desperately trying to return his overdue library books. Meanwhile, Basil Hawkins has become a reluctant relationship counselor, with his cards deciding the fate of pirate ship crushes everywhere.",
            
                f"Pudding's Memory-Memory Fruit made {humanize_list([f'`{u}`' for u in success_list])} forget how to type {time}! They`re currently trying to send messages by aggressively poking their screen. The memory loss spread like wildfire through Totto Land. Now Katakuri can't remember how to see the future, Big Mom's forgotten her food cravings, and the Chess Peacekeepers are stuck in an eternal stalemate. Sanji's teaching everyone how to cook, inadvertently turning Whole Cake Island into the Grand Line's largest culinary school.",
            
                f"Tama's Kibi-Kibi Fruit accidentally tamed {humanize_list([f'`{u}`' for u in success_list])}'s keyboard, and now it won't work for anyone else {time}! The keyboard now only types in happy animal noises. The dango's effect spread to all technology in Wano, turning Den Den Mushi into loyal pets. Now Queen's cybernetics keep trying to fetch his bombs, Franky's hair is purring contentedly, and poor Apoo can't stop his body from playing 'Who Let the Dogs Out'. Meanwhile, Kaido's drunk-dialing other Yonko with nothing but 'moo's and 'baa's.",
            
                f"Smoker's Smoke-Smoke Fruit has obscured {humanize_list([f'`{u}`' for u in success_list])}'s messages {time}! Their chat window now looks like a very unsuccessful attempt at vaping. The smoke spread across Marineford, turning it into a foggy murder mystery dinner party. Now Akainu's trying to solve 'The Case of the Missing Justice', Kizaru's bumping into walls at the speed of light, and Coby's been mistaken for the butler and forced to serve tea. Garp's just napping through the whole thing, occasionally sleep-punching culprits.",
            
                f"X Drake transformed into a dinosaur and accidentally stomped on {humanize_list([f'`{u}`' for u in success_list])}'s communication device {time}! In his defense, those tiny keyboards are hard to use with giant dino claws. The soundwave from the stomp resonated with all the Zoan Devil Fruit users, turning Onigashima into a prehistoric party. Now Page One and Ulti are having a head-butting contest, Queen's funk has evolved into dinosaur disco, and poor Jack is stuck as a mammoth in a china shop. Meanwhile, Kaido's dragon form is trying to organize everyone into 'Jurassic Park' style Thriller choreography.",
            
                f"Carrot's Sulong form was too bright, temporarily blinding {humanize_list([f'`{u}`' for u in success_list])} {time}! They`re now typing in all caps because they can't see the keyboard properly. The Sulong transformation spread to all the minks, turning Zou into a giant lighthouse. Now Jack's ship keeps crashing into Zunisha's legs, Inuarashi and Nekomamushi have forgotten their day/night feud and are hosting 24/7 raves, and Bepo's luminous fur has turned the Heart Pirates' submarine into a mobile disco ball.",
            
                f"Giolla's Art-Art Fruit turned {humanize_list([f'`{u}`' for u in success_list])}'s messages into abstract art, making them unreadable {time}! Critics are calling it 'a bold statement on the futility of communication'. The artistic effect spread across Dressrosa, turning the whole island into a living Picasso painting. Now Pica's voice is coming out in color splatters, Diamante's cape is rearranging itself into cubist forms, and Sugar's toys are all walking around like Dali's melting clocks. King Riku is seriously considering rebranding the country as 'Dressrosa Modern Art Museum'.",
            
                f"Kinemon's disguise for {humanize_list([f'`{u}`' for u in success_list])} was so perfect, nobody could recognize {'them' if len(success_list) > 1 else 'them'} in the chat {time}! They`re currently pretending to be a very talkative house plant. Kinemon's power glitched, causing everyone in Wano to swap appearances. Now Kaido looks like O-Tama, Big Mom is stuck in Toko's body, and Orochi keeps shapeshifting between his many heads. The Straw Hats' rescue mission has turned into a ridiculous game of Guess Who, with Luffy enjoying it way too much.",
            
                f"Boa Hancock's Love-Love Fruit turned {humanize_list([f'`{u}`' for u in success_list])}'s keyboard to stone {time}! Now that's what we call 'hard' feelings! The petrification spread through the internet, turning all online communication into an ancient form of stone tablets. Now the Revolutionary Army is trying to organize a coup via stone emoji, the Marines are chiseling wanted posters instead of printing them, and poor Morgans is struggling to delivery the 'Daily Stone' newspaper. Meanwhile, Sentomaru's Den Den Mushi has become a very confused garden gnome."
            ]
            await ctx.send(random.choice(pirate_messages))
            
    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = None):
        """Unmute a muted user."""
        success, error_message = await self.unmute_user(ctx.guild, member, reason)
        if success:
            await ctx.send(f"{member.mention} has been unmuted.")
            await self.send_themed_message(ctx.channel, member, "unmute")
        else:
            await ctx.send(f"Failed to unmute {member.mention}: {error_message}")

    @commands.command()
    @checks.mod_or_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """Kick a user from the server."""
        try:
            await member.kick(reason=reason)
            await ctx.send(f"{member.mention} has been kicked from the server.")
            await self.send_mod_log(ctx.guild, "kick", member, ctx.author, reason)
            await self.send_themed_message(ctx.channel, member, "kick")
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick that user.")
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to kick the user.")

    @commands.command()
    @checks.mod_or_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, delete_days: int = 0, *, reason: str = None):
        """Ban a user from the server."""
        try:
            await member.ban(reason=reason, delete_message_days=delete_days)
            
            ban_message, ban_gif = random.choice(self.ban_messages)
            ban_text = (
                f"⛓️ Pirate Banished to Impel Down! ⛓️\n\n"
                f"{member.name} has been locked away!\n\n"
                f"**Crimes**\n{reason or 'No reason provided'}\n\n"
                f"**Warden's Note**\n{ban_message}"
            )
            
            await ctx.send(ban_text)
            await ctx.send(ban_gif)
            
            await self.send_mod_log(ctx.guild, "ban", member, ctx.author, reason)
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban that user.")
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to ban the user.")

    async def send_mod_log(self, guild: discord.Guild, action: str, target: Optional[discord.Member], moderator: discord.Member, reason: str = None, duration: timedelta = None, ctx: commands.Context = None):
        log_channel_id = await self.config.guild(guild).mod_log_channel()
        if not log_channel_id:
            return
    
        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return
    
        action_str = f"{action.capitalize()}"
        if duration:
            action_str += f" for {humanize_timedelta(timedelta=duration)}"
    
        log_message = "🏴‍☠️ **Crew Log Entry** 🏴‍☠️\n\n"
    
        if target:
            log_message += f"**Target Pirate:** {target.name} (ID: {target.id})\n"
        else:
            log_message += "**Target Pirate:** N/A\n"
    
        log_message += (
            f"**Action Taken:** {action_str}\n"
            f"**Reason for Action:** {reason or 'No reason provided'}\n"
            f"**Enforcing Officer:** {moderator.name} (ID: {moderator.id})\n"
        )
    
        if ctx and ctx.message:
            log_message += f"**Incident Report:** [View Incident Details]({ctx.message.jump_url})\n\n"
        else:
            log_message += "**Incident Report:** No details available\n\n"
    
        log_message += f"Logged at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} | One Piece Moderation"
    
        await log_channel.send(log_message)

    async def send_themed_message(self, channel: discord.TextChannel, user: discord.Member, action: str, duration: str = ""):
        messages = {
            "mute": [
                f"Yohohoho! {user.mention} has been sent to the Void Century{duration}! Even I, as a skeleton, can hear better than them now!",
                f"Gomu Gomu no Silence! {user.mention}'s voice has been stretched into the distance{duration}!",
                f"{user.mention} has been caught by Bartolomeo's Barrier{duration}! Not even sound can escape!"
            ],
            "unmute": [
                f"Break through! {user.mention} has escaped the Void Century and can speak again!",
                f"{user.mention}'s voice has returned from its grand adventure! Did you bring back any treasure?",
                f"The Sea Kings have granted {user.mention} their voice back! Use it wisely, or they might change their minds!"
            ],
            "kick": [
                f"{user.mention} has been sent flying by Luffy's Gomu Gomu no Bazooka! They're blasting off again!",
                f"Sanji's Diable Jambe just kicked {user.mention} clean off the ship! Hope they can swim!",
                f"{user.mention} got lost following Zoro and ended up kicked from the server! Typical Zoro..."
            ],
            "ban": [
                f"{user.mention} has been banished to Impel Down! Not even Buggy could escape this ban!",
                f"Akainu's Absolute Justice has been served! {user.mention} is hereby banned from this pirate crew!",
                f"{user.mention} has been caught in Blackbeard's darkness and swallowed by a ban! Zehahaha!"
            ]
        }
        
        await channel.send(random.choice(messages[action]))

    @commands.command()
    @commands.admin_or_permissions(manage_roles=True)
    async def setmuterole(self, ctx, role: discord.Role):
        """Set the role to be used for mutes."""
        await self.config.guild(ctx.guild).mute_role.set(role.id)
        await ctx.send(f"The Void Century role has been set to {role.name}.")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setmodlogchannel(self, ctx, channel: discord.TextChannel):
        """Set the mod log channel for the server."""
        await self.config.guild(ctx.guild).mod_log_channel.set(channel.id)
        await ctx.send(f"Mod log channel has been set to {channel.mention}")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def setgeneralchannel(self, ctx, channel: discord.TextChannel):
        """Set the general channel for the server."""
        await self.config.guild(ctx.guild).general_channel.set(channel.id)
        await ctx.send(f"General channel has been set to {channel.mention}")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def addbannedword(self, ctx, word: str):
        """Add a word to the banned words list."""
        async with self.config.guild(ctx.guild).banned_words() as banned_words:
            if word.lower() not in banned_words:
                banned_words.append(word.lower())
                await ctx.send(f"Added '{word}' to the banned words list.")
            else:
                await ctx.send(f"'{word}' is already in the banned words list.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def removebannedword(self, ctx, word: str):
        """Remove a word from the banned words list."""
        async with self.config.guild(ctx.guild).banned_words() as banned_words:
            if word.lower() in banned_words:
                banned_words.remove(word.lower())
                await ctx.send(f"Removed '{word}' from the banned words list.")
            else:
                await ctx.send(f"'{word}' is not in the banned words list.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def listbannedwords(self, ctx):
        """List all banned words."""
        banned_words = await self.config.guild(ctx.guild).banned_words()
        if banned_words:
            words_list = ", ".join(banned_words)
            await ctx.author.send(f"Banned words: {words_list}")
            await ctx.send("I've sent you a DM with the list of banned words.")
        else:
            await ctx.send("There are no banned words.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        banned_words = await self.config.guild(message.guild).banned_words()
        if any(word in message.content.lower() for word in banned_words):
            await message.delete()
            await self.handle_banned_word(message)

    async def handle_banned_word(self, message):
        async with self.config.guild(message.guild).banned_word_strikes() as strikes:
            strikes[str(message.author.id)] = strikes.get(str(message.author.id), 0) + 1
            strike_count = strikes[str(message.author.id)]

        warning = random.choice([
            f"Oi oi, {message.author.mention}! Even Luffy wouldn't approve of that language! The Pirate King's dream is about freedom, not disrespect!",
            f"Yohohoho! {message.author.mention}, that word is more forbidden than the Poneglyphs! As a skeleton, I have no ears to hear such things... but I'm all bones! Skull joke!",
            f"Oi, {message.author.mention}! Sanji says a true pirate's Black Leg style is about kicking ass, not using crass words!",
            f"Huh?! {message.author.mention}, are you trying to make Chopper cry with that language? He's a reindeer, not a swear-deer!",
            f"Oi oi oi! {message.author.mention}, Zoro got lost and ended up here, and even he knows that word is more dangerous than Mihawk's sword!",
            f"Nami says if you use that word again, {message.author.mention}, she'll raise your debt by 100,000 berries! And trust me, she WILL collect!"
        ])

        await message.channel.send(warning, delete_after=10)

        if strike_count == 3:
            duration = timedelta(minutes=10)
            success, _ = await self.mute_user(message.guild, message.author, self.bot.user, duration, "Repeated use of banned words")
            if success:
                await message.channel.send(f"{message.author.mention} has been muted for 10 minutes due to repeated use of banned words.")
        elif strike_count == 5:
            duration = timedelta(hours=1)
            success, _ = await self.mute_user(message.guild, message.author, self.bot.user, duration, "Excessive use of banned words")
            if success:
                await message.channel.send(f"{message.author.mention} has been muted for 1 hour due to excessive use of banned words.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def resetbannedwordstrikes(self, ctx, member: discord.Member):
        """Reset the banned word strike count for a user."""
        async with self.config.guild(ctx.guild).banned_word_strikes() as strikes:
            if str(member.id) in strikes:
                del strikes[str(member.id)]
                await ctx.send(f"Reset banned word strikes for {member.mention}.")
            else:
                await ctx.send(f"{member.mention} has no banned word strikes.")

    @commands.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def checkbannedwordstrikes(self, ctx, member: discord.Member):
        """Check the banned word strike count for a user."""
        strikes = await self.config.guild(ctx.guild).banned_word_strikes()
        strike_count = strikes.get(str(member.id), 0)
        await ctx.send(f"{member.mention} has {strike_count} banned word strike(s).")

    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def tempmute(self, ctx, member: discord.Member, duration: str, *, reason: str = None):
        """Temporarily mute a user."""
        try:
            duration = self.parse_duration(duration)
        except ValueError as e:
            return await ctx.send(str(e))

        success, error_message = await self.mute_user(ctx.guild, member, ctx.author, duration, reason)
        if success:
            await ctx.send(f"{member.mention} has been temporarily muted for {humanize_timedelta(timedelta=duration)}.")
            await self.send_mod_log(ctx.guild, "tempmute", member, ctx.author, reason, duration)
            await self.send_themed_message(ctx.channel, member, "mute", f" for {humanize_timedelta(timedelta=duration)}")
        else:
            await ctx.send(f"Failed to mute {member.mention}: {error_message}")

    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def checkmutesystem(self, ctx):
        """Check the mute system setup."""
        mute_role_id = await self.config.guild(ctx.guild).mute_role()
        mute_role = ctx.guild.get_role(mute_role_id)
        
        if not mute_role:
            await ctx.send("The Void Century role is not set or no longer exists!")
            return
    
        bot_member = ctx.guild.me
        issues = []
    
        if not bot_member.guild_permissions.manage_roles:
            issues.append("I don't have the 'Manage Roles' permission in this server!")
    
        if not bot_member.top_role > mute_role:
            issues.append("The Void Century role is above my highest role! I can't manage it!")
    
        # Check mute role permissions
        if mute_role.permissions.send_messages:
            issues.append("The Void Century role can still send messages!")
    
        if not issues:
            await ctx.send("Arr! The mute system seems to be set up correctly!")
        else:
            issues_text = "\n".join(f"- {issue}" for issue in issues)
            await ctx.send(f"Avast! There be some issues with the mute system:\n{issues_text}")

    @commands.command()
    @checks.mod_or_permissions(manage_roles=True)
    async def mutecheck(self, ctx, member: discord.Member):
        """Check the remaining mute time for a user."""
        muted_users = await self.config.guild(ctx.guild).muted_users()
        mute_data = muted_users.get(str(member.id))

        if not mute_data:
            return await ctx.send(f"{member.mention} is not muted.")

        if mute_data["until"]:
            until = datetime.fromisoformat(mute_data["until"])
            now = datetime.now(timezone.utc)
            if until > now:
                remaining = until - now
                await ctx.send(f"{member.mention} is muted for {humanize_timedelta(timedelta=remaining)} more.")
            else:
                await ctx.send(f"{member.mention}'s mute has expired. They should be unmuted soon.")
        else:
            await ctx.send(f"{member.mention} is muted indefinitely.")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def mutedrole(self, ctx):
        """Show the current muted role."""
        mute_role_id = await self.config.guild(ctx.guild).mute_role()
        if mute_role_id:
            mute_role = ctx.guild.get_role(mute_role_id)
            if mute_role:
                await ctx.send(f"The current muted role is: {mute_role.name}")
            else:
                await ctx.send("The muted role is set, but I couldn't find it in the server. It may have been deleted.")
        else:
            await ctx.send("No muted role has been set for this server.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Re-apply mute if a muted user rejoins."""
        muted_users = await self.config.guild(member.guild).muted_users()
        mute_data = muted_users.get(str(member.id))
    
        if mute_data:
            mute_role_id = await self.config.guild(member.guild).mute_role()
            if mute_role_id:
                mute_role = member.guild.get_role(mute_role_id)
                if mute_role:
                    await member.add_roles(mute_role, reason="Re-applying mute on rejoin")
                    await self.send_mod_log(member.guild, "mute", member, self.bot.user, "Re-applied mute on rejoin")

    @commands.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def clearmutes(self, ctx):
        """Clear all mutes in the server."""
        mute_role_id = await self.config.guild(ctx.guild).mute_role()
        if not mute_role_id:
            return await ctx.send("No mute role set for this server.")
    
        mute_role = ctx.guild.get_role(mute_role_id)
        if not mute_role:
            return await ctx.send("Mute role not found in the server.")
    
        count = 0
        async with ctx.typing():
            for member in ctx.guild.members:
                if mute_role in member.roles:
                    await member.remove_roles(mute_role, reason="Mass mute clearance")
                    count += 1
    
            await self.config.guild(ctx.guild).muted_users.set({})
    
        await ctx.send(f"Cleared mutes for {count} member(s).")
        await self.send_mod_log(ctx.guild, "clearmutes", None, ctx.author, f"Cleared mutes for {count} member(s)", ctx=ctx)
        
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

async def teardown(bot):
    global original_commands
    for cmd_name, cmd in original_commands.items():
        if bot.get_command(cmd_name):
            bot.remove_command(cmd_name)
        if cmd:
            bot.add_command(cmd)
    original_commands.clear()
