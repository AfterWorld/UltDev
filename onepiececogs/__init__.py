from .onepiececogs import OnePieceExpandedCogs

async def setup(bot):
    await bot.add_cog(OnePieceExpandedCogs(bot))