@commands.command()
    async def info(self, ctx):
        """Shows One Piece themed information about the Thousand Sunny Bot."""
        python_version = "{}.{}.{}".format(*sys.version_info[:3])
        dpy_version = discord.__version__
        ping = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)
        max_guilds = 20  # Assuming 20 is the max slots reserved for the bot

        # Get system info
        cpu_usage = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Embed content
        embed = discord.Embed(
            title="🏴‍☠️ Welcome Aboard the Thousand Sunny! 🌞",
            description=(
                "Ahoy, brave pirates! I'm the Thousand Sunny, the dream ship crafted by the legendary shipwright Franky. "
                "I've sailed through digital Grand Lines to reach you, powered by the spirit of adventure and the technology of "
                "[Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot)!"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://example.com/thousand_sunny.png")

        # Add inline fields for Ship's Log and Ship's Specs side by side
        embed.add_field(
            name="🧭 **Ship's Log**",
            value=(
                f"**🏴‍☠️ Crew Members:** {ctx.guild.member_count}\n"
                f"**🌊 Sailing on:** {guild_count} / {max_guilds} seas\n"
                f"**⚓ Docked at:** {ctx.guild.name}\n"
                f"**🐉 Captain:** {ctx.guild.owner.mention}"
            ),
            inline=True
        )

        embed.add_field(
            name="🔧 **Ship's Specs**",
            value=(
                f"**🐏 Ram:** {memory.percent}% occupied\n"
                f"**⚙️ Engine Load:** {cpu_usage}%\n"
                f"**🗺️ Chart Storage:** {disk.percent}% full\n"
                f"**🌡️ Ocean Temperature:** {ping}ms"
            ),
            inline=True
        )

        embed.add_field(
            name="\u200B",  # Empty field for spacing
            value="\u200B",
            inline=False
        )

        embed.add_field(
            name="🏴‍☠️ **Pirate Crew**",
            value=(
                "🍖 **Luffy:** The Chatty Captain (Chat Commands)\n"
                "🗡️ **Zoro:** The Moderating Swordsman (Moderation)\n"
                "💰 **Nami:** The Trading Navigator (Economy System)\n"
                "🎯 **Usopp:** The Tall Tale Teller (Fun Commands)\n"
                "🍳 **Sanji:** The Culinary Informant (Information Commands)\n"
                "🩺 **Chopper:** The Helping Doctor (Support Features)\n"
                "📚 **Robin:** The Historian (Logging and Database)\n"
                "🛠️ **Franky:** The SUPER Technician (Utility Commands)\n"
                "🎻 **Brook:** The Soul King of Music (Music Commands)"
            ),
            inline=False
        )

        embed.add_field(
            name="🗝️ **Devil Fruit Powers**",
            value=(
                "🐍 **Python:** {}\n"
                "🤖 **Discord.py:** {}\n"
                "🔴 **Red-DiscordBot:** {}".format(python_version, dpy_version, red_version)
            ),
            inline=True
        )

        embed.add_field(
            name="🧭 **Navigation**",
            value=(
                "`[p]help`: View all commands\n"
                "`[p]info`: Display this ship's log\n"
                "`[p]ping`: Test the waters with Aokiji and Akainu"
            ),
            inline=True
        )

        embed.set_footer(text="Set sail for adventure with the Straw Hat Pirates!")
        
        await ctx.send(embed=embed)
