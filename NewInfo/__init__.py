from .onepiece_info import OnePieceInfo

async def setup(bot):
    bot.add_cog(OnePieceInfo(bot))
