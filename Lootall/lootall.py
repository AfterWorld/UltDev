import discord
from redbot.core import commands, checks
from redbot.core.utils.chat_formatting import box
from typing import Optional

class LootAll(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.is_owner()
    async def lootall(self, ctx, role: discord.Role, rarity: str, amount: int = 1):
        """Give loot boxes to all members with a specific role."""
        adventure = self.bot.get_cog("Adventure")
        if not adventure:
            return await ctx.send("The Adventure cog is not loaded.")

        valid_rarities = ["normal", "rare", "epic", "legendary", "ascended", "set"]
        if rarity.lower() not in valid_rarities:
            return await ctx.send(f"Invalid rarity. Choose from: {', '.join(valid_rarities)}")

        members = role.members
        if not members:
            return await ctx.send(f"No members found with the role {role.name}")

        loot_type = getattr(adventure.Rarities, rarity.lower())
        
        success_count = 0
        for member in members:
            try:
                # We're directly calling the Adventure cog's _give_loot method
                await ctx.invoke(
                    adventure._give_loot,
                    loot_type=loot_type,
                    users=[member],
                    number=amount
                )
                success_count += 1
            except Exception as e:
                await ctx.send(f"Failed to give loot to {member.display_name}: {str(e)}")

        await ctx.send(
            box(
                f"Successfully gave {amount} {rarity} loot box(es) to {success_count} members with the {role.name} role.",
                lang="ansi",
            )
        )

async def setup(bot):
    await bot.add_cog(LootAll(bot))