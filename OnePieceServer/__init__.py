from .onepieceserver import OnePieceServer

async def setup(bot):
    await bot.add_cog(OnePieceServer(bot))