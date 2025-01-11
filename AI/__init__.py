from .ai_character import AICharacter

async def setup(bot):
    bot.add_cog(AICharacter(bot))
