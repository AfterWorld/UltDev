from .onepieceai import OnePieceAI

   async def setup(bot):
       await bot.add_cog(OnePieceAI(bot))
