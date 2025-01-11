from .ai_character import AICharacter

def setup(bot):
    bot.add_cog(AICharacter(bot))
