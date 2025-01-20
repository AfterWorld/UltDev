from .advancedwgsimulator import AdvancedWorldGovernmentSimulator

async def setup(bot):
    await bot.add_cog(AdvancedWorldGovernmentSimulator(bot))
