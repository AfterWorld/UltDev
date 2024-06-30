from .onepiecebot import OnePieceBot

async def setup(bot):
    await bot.add_cog(OnePieceBot(bot))
