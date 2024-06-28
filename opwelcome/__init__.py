from .opwelcome import OPWelcome

async def setup(bot):
    await bot.add_cog(OPwelcome(bot))
