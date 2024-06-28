from .onepiece_info import setup

async def setup(bot):
    bot.add_cog(OnePieceInfo(bot))
