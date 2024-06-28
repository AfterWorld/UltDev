from .onepiece_info import OnePieceInfo

async def setup(bot: Red):
    cog = OnePieceInfo(bot)
    await bot.add_cog(cog)
