from .ai_character import AICharacter

await def setup(bot):
    bot.add_cog(AICharacter(bot))
