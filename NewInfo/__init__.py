from .onepiece_info import OnePieceInfo

async def setup(bot):
    cog = OnePieceInfo(bot)
    await bot.add_cog(cog)
