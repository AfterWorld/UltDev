import asyncio
import itertools
from typing import Union, List, Iterable

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

class OnePieceHelp(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            "help": "Shows help about the bot, a command, or a category",
            "cooldown": commands.Cooldown(1, 3, commands.BucketType.user),
        })
        self.devil_fruits = {}

    async def send_bot_help(self, mapping):
        ctx = self.context
        description = (
            "Ahoy, brave pirate! Welcome aboard the Thousand Sunny. "
            "I'm your trusty navigator through the Grand Line of commands. "
            "What kind of adventure are you looking for today?"
        )
        
        embed = discord.Embed(
            title="📜 Grand Line Navigation Chart 🗺️",
            description=description,
            color=discord.Color.gold()
        )

        cogs = sorted(ctx.bot.cogs.values(), key=lambda cog: cog.qualified_name)
        for cog in cogs:
            cog_commands = await self.filter_commands(cog.get_commands(), sort=True)
            if cog_commands:
                value = ", ".join(f"`{c.name}`" for c in cog_commands)
                embed.add_field(name=f"🏴‍☠️ {cog.qualified_name} Crew", value=value, inline=False)

        embed.set_footer(text=f"Type {ctx.clean_prefix}help <command> for more info on a command. "
                              f"You can also type {ctx.clean_prefix}help <category> for more info on a category.")

        await ctx.send(embed=embed)

    async def send_command_help(self, command):
        ctx = self.context
        devil_fruit = self.devil_fruits.get(command.qualified_name, "Unknown Devil Fruit")
        
        embed = discord.Embed(
            title=f"🍎 Devil Fruit Power: {command.qualified_name.capitalize()}",
            description=command.help or "No description available. This fruit's powers are a mystery!",
            color=discord.Color.red()
        )
        
        if command.aliases:
            embed.add_field(name="🏴‍☠️ Alias Techniques", value=", ".join(f"`{a}`" for a in command.aliases), inline=False)
        
        signature = self.get_command_signature(command)
        embed.add_field(name="👣 Usage", value=f"`{signature}`", inline=False)
        
        if isinstance(command, commands.Group):
            subcommands = [f"`{c.name}`" for c in command.commands]
            embed.add_field(name="🌊 Sub-techniques", value=" ".join(subcommands), inline=False)
        
        embed.add_field(name="🍇 Devil Fruit Type", value=devil_fruit, inline=False)
        
        embed.set_footer(text="Remember, with great power comes great responsibility, pirate!")
        
        await ctx.send(embed=embed)

    async def send_group_help(self, group):
        ctx = self.context
        subcommands = group.commands
        if len(subcommands) == 0:
            return await self.send_command_help(group)

        entries = await self.filter_commands(subcommands, sort=True)
        pages = []
        for i, page in enumerate(pagify(self.list_cmds(entries), page_length=1000)):
            embed = discord.Embed(
                title=f"🏴‍☠️ {group.qualified_name} Crew Techniques",
                description=group.description,
                color=discord.Color.blue()
            )
            embed.add_field(name="Techniques", value=page, inline=False)

            signature = self.get_command_signature(group)
            embed.add_field(name="👣 Usage", value=f"`{signature}`", inline=False)
            
            embed.set_footer(text=f"Page {i+1}/{len(pages)+1}")
            pages.append(embed)

        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            await menu(ctx, pages, DEFAULT_CONTROLS)

    async def send_cog_help(self, cog):
        ctx = self.context
        cog_name = cog.qualified_name or "No Category"
        
        embed = discord.Embed(
            title=f"🏴‍☠️ {cog_name} Crew",
            description=cog.description or "This crew's specialties are shrouded in mystery!",
            color=discord.Color.blue()
        )
        
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        if filtered:
            for command in filtered:
                embed.add_field(
                    name=f"🏴‍☠️ {command.name}",
                    value=command.short_doc or "No description available. A secret technique!",
                    inline=False
                )
        
        embed.set_footer(text=f"Use {ctx.clean_prefix}help <command> for more info on a command.")
        
        await ctx.send(embed=embed)

    def list_cmds(self, commands_iterable: Iterable):
        return "\n".join(f"`{c.name}` - {c.short_doc}" for c in commands_iterable)

    @commands.command()
    @commands.is_owner()
    async def setdevilfruit(self, ctx, command_name: str, *, devil_fruit_type: str):
        """Set a Devil Fruit type for a command."""
        self.devil_fruits[command_name] = devil_fruit_type
        await ctx.send(f"Devil Fruit type for {command_name} set to {devil_fruit_type}.")

def setup(bot):
    help_command = OnePieceHelp()
    help_command.devil_fruits = getattr(bot, "_devil_fruits", {})
    old_help = bot.help_command
    bot.help_command = help_command
    bot._devil_fruits = help_command.devil_fruits

    @bot.command()
    @commands.is_owner()
    async def setdevilfruit(ctx, command_name: str, *, devil_fruit_type: str):
        """Set a Devil Fruit type for a command."""
        bot._devil_fruits[command_name] = devil_fruit_type
        await ctx.send(f"Devil Fruit type for {command_name} set to {devil_fruit_type}.")

def teardown(bot):
    bot.remove_command("setdevilfruit")
    bot.help_command = commands.DefaultHelpCommand()
