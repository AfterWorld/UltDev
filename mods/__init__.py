from .onepiece_mod import OnePieceMod

async def setup(bot):
    await bot.add_cog(OnePieceMod(bot))
