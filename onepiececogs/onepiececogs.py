import random
import asyncio
from redbot.core import commands, Config
import discord

class OnePieceExpandedCogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_user = {
            "last_activity": None,
            "character": None,
            "devil_fruit": None,
            "quiz_scores": {"sword": 0, "personality": ""}
        }
        default_guild = {
            "ongoing_games": {}
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        
        self.devil_fruits = {
            'Gomu Gomu': 'Grants the user body the properties of rubber',
            'Mera Mera': 'Allows the user to create, control, and transform into fire',
            'Hie Hie': 'Allows the user to create, control, and transform into ice',
            'Gura Gura': 'Allows the user to create vibrations, or "quakes"',
            'Ope Ope': 'Allows the user to create a spherical space or "room"',
            'Yami Yami': 'Allows the user to create and control darkness',
            'Pika Pika': 'Allows the user to create, control, and transform into light',
            'Mochi Mochi': 'Allows the user to create, control, and transform into mochi',
            'Gasu Gasu': 'Allows the user to create, control, and transform into gas',
            'Suna Suna': 'Allows the user to create, control, and transform into sand'
        }
        self.poneglyph_messages = [
            "The ancient weapon lies beneath the sea",
            "When all moons align, the path will clear",
            "In the land of Wano, a secret sleeps",
            "The voice of all things speaks in silence",
            "To reach Laugh Tale, follow the Road"
        ]
        self.sword_questions = [
            {"q": "Which sword is known as 'Black Blade'?", "a": "Yoru"},
            {"q": "Who wields the Wado Ichimonji?", "a": "Zoro"},
            {"q": "What grade is the sword Enma?", "a": "Great Grade"},
            {"q": "Who forged the Kitetsu swords?", "a": "Kitetsu"},
            {"q": "What is the name of Mihawk's sword?", "a": "Yoru"}
        ]
        self.personality_questions = [
            {"q": "How do you approach problems?", "options": ["A) Head-on", "B) Strategically", "C) With help from friends"]},
            {"q": "What's your dream?", "options": ["A) To be the strongest", "B) To find a legendary treasure", "C) To see the world"]},
            {"q": "How do you treat your friends?", "options": ["A) Protect them at all costs", "B) Rely on them for support", "C) Tease them playfully"]},
            {"q": "What's your favorite type of island?", "options": ["A) Summer island", "B) Winter island", "C) Sky island"]},
            {"q": "How do you feel about the World Government?", "options": ["A) They're the enemy", "B) They're necessary for order", "C) I don't really care"]}
        ]
        self.character_results = {
            "AAAAA": "Luffy", "BBBBB": "Nami", "CCCCC": "Usopp",
            "AABBC": "Zoro", "BBCCA": "Robin", "CACAB": "Sanji",
            "ACBCA": "Chopper", "BAACC": "Franky", "CBACB": "Brook"
        }
        self.cryptic_responses = [
            "The sea whispers of ancient battles...",
            "Echoes of lost kingdoms resonate...",
            "The wind carries tales of forgotten treasures...",
            "Shadows of the void century linger...",
            "The rhythm of the world pulses beneath...",
            "Voices of the past call out for justice...",
            "The truth of history lies hidden in plain sight..."
        ]
        self.riddles = [
            {"question": "I am not alive, but I grow; I don't have lungs, but I need air; I don't have a mouth, but water kills me. What am I?", "answer": "fire"},
            {"question": "I have cities, but no houses. I have mountains, but no trees. I have water, but no fish. What am I?", "answer": "map"},
            {"question": "What has keys, but no locks; space, but no room; you can enter, but not go in?", "answer": "keyboard"},
            {"question": "I am always hungry; I must always be fed. The finger I touch, will soon turn red. What am I?", "answer": "fire"},
            {"question": "I have a head and a tail that will never meet. Having too many of me is always a treat. What am I?", "answer": "coin"}
        ]

    @commands.command()
    async def fusefruit(self, ctx):
        """Generate a fusion of two Devil Fruits and discuss its powers"""
        fruit1 = random.choice(list(self.devil_fruits.keys()))
        fruit2 = random.choice(list(self.devil_fruits.keys()))
        while fruit1 == fruit2:
            fruit2 = random.choice(list(self.devil_fruits.keys()))
        
        fusion_name = f"{fruit1.split()[0]} {fruit2.split()[1]}"
        await ctx.send(f"New Devil Fruit Fusion: {fusion_name} no Mi!")
        await ctx.send("What powers do you think this fruit would have? You have 60 seconds to discuss. Each user can submit one idea.")

        responses = {}
        discussion_duration = 60  # 60 seconds for discussion

        def check(m):
            return m.channel == ctx.channel and m.author != self.bot.user and m.author not in responses

        end_time = asyncio.get_event_loop().time() + discussion_duration

        while asyncio.get_event_loop().time() < end_time:
            try:
                msg = await self.bot.wait_for('message', timeout=end_time - asyncio.get_event_loop().time(), check=check)
                responses[msg.author] = msg.content
                await msg.add_reaction("👍")  # React to confirm the response was recorded
            except asyncio.TimeoutError:
                break

        if responses:
            await ctx.send("Here are the ideas for the fusion fruit's powers:")
            for author, response in responses.items():
                await ctx.send(f"{author.name}: {response}")
            
            if len(responses) > 1:
                vote_msg = await ctx.send("Vote for the best power idea by reacting with the corresponding number:")
                for i, (author, response) in enumerate(list(responses.items())[:5], start=1):
                    await vote_msg.add_reaction(f"{i}\N{COMBINING ENCLOSING KEYCAP}")

                await asyncio.sleep(30)  # 30 seconds for voting
                vote_msg = await ctx.channel.fetch_message(vote_msg.id)
                votes = {r.emoji: r.count for r in vote_msg.reactions}
                winner = max(votes, key=votes.get)
                winning_author, winning_idea = list(responses.items())[int(winner[0]) - 1]

                await ctx.send(f"The most popular power for the {fusion_name} no Mi is:\n{winning_author.name}: {winning_idea}")
            else:
                await ctx.send(f"Only one idea was submitted for the {fusion_name} no Mi.")
        else:
            await ctx.send("No one suggested any powers. The fruit's abilities remain a mystery!")
    @commands.command()
    async def poneglyph(self, ctx):
        """Start a Poneglyph decoding game with increasing difficulty"""
        difficulty = 1
        score = 0
        
        await ctx.send("Welcome to the Poneglyph Decoding Challenge! Decipher as many Poneglyphs as you can. The difficulty will increase with each correct answer.")

        while True:
            message = random.choice(self.poneglyph_messages)
            encoded = self.encode_message(message, difficulty)
            await ctx.send(f"Difficulty Level {difficulty}\nDecipher this Poneglyph: `{encoded}`")
            await ctx.send(f"You have {60 // difficulty} seconds!")

            def check(m):
                return m.channel == ctx.channel and m.content.lower() == message.lower()

            try:
                msg = await self.bot.wait_for('message', timeout=60.0 / difficulty, check=check)
                await ctx.send(f"Congratulations {msg.author.mention}! You've decoded the Poneglyph!")
                score += difficulty * 10
                difficulty += 1
                await ctx.send(f"Your current score: {score}")
                await ctx.send("Prepare for the next Poneglyph! Type 'continue' to proceed or 'stop' to end the game.")
                
                def continue_check(m):
                    return m.author == msg.author and m.content.lower() in ['continue', 'stop']

                try:
                    continue_msg = await self.bot.wait_for('message', timeout=15.0, check=continue_check)
                    if continue_msg.content.lower() == 'stop':
                        break
                except asyncio.TimeoutError:
                    await ctx.send("No response received. Ending the game.")
                    break

            except asyncio.TimeoutError:
                await ctx.send(f"Time's up! The correct decoding was: {message}")
                break

        await ctx.send(f"Game Over! Your final score is {score}. You reached difficulty level {difficulty}.")

    def encode_message(self, message, difficulty):
        shift = difficulty * 2
        return ''.join(chr((ord(c) - 97 + shift) % 26 + 97) if c.isalpha() else c for c in message.lower())

    @commands.command()
    async def fruitinfo(self, ctx, *, fruit_name: str):
        """Get detailed information about a specific Devil Fruit"""
        fruit_name = fruit_name.lower().title()
        if fruit_name in self.devil_fruits:
            await ctx.send(f"Devil Fruit: {fruit_name} no Mi\nAbility: {self.devil_fruits[fruit_name]}")
        else:
            await ctx.send("That Devil Fruit is not in our database!")

    @commands.command()
    async def swordquiz(self, ctx):
        """Start a sword knowledge quiz"""
        score = 0
        for q in self.sword_questions:
            await ctx.send(q["q"])
            try:
                answer = await self.bot.wait_for('message', timeout=30.0, check=lambda m: m.author == ctx.author)
                if answer.content.lower() == q["a"].lower():
                    await ctx.send("Correct!")
                    score += 1
                else:
                    await ctx.send(f"Wrong! The correct answer was {q['a']}.")
            except asyncio.TimeoutError:
                await ctx.send("Time's up!")
        await ctx.send(f"Quiz over! Your score: {score}/{len(self.sword_questions)}")
        await self.config.user(ctx.author).quiz_scores.sword.set(score)

    @commands.command()
    async def whichcharacter(self, ctx):
        """Take a personality quiz to find out which One Piece character you're most like"""
        answers = ""
        for q in self.personality_questions:
            await ctx.send(f"{q['q']}\n" + "\n".join(q['options']))
            answer = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author and m.content.upper() in "ABC")
            answers += answer.content.upper()

        character = self.character_results.get(answers, "Pandaman")
        await ctx.send(f"You're most like {character}!")
        await self.config.user(ctx.author).quiz_scores.personality.set(character)

    @commands.command()
    async def voiceofallthings(self, ctx, *, message: str):
        """Attempt to decipher cryptic messages as if you had the Voice of All Things ability"""
        decoded = ' '.join(random.choice(self.cryptic_responses) for _ in range(3))
        await ctx.send(f"You hear: {decoded}\nCan you interpret its meaning?")

    @commands.command()
    async def eatingcontest(self, ctx):
        """Compete in Luffy's Eating Contest"""
        await ctx.send("Luffy's Eating Contest begins! Type food emojis as fast as you can for 30 seconds!")
        
        def check(m):
            return m.author == ctx.author and any(c in m.content for c in '🍖🍗🍔🍕🍟🌭🥩🍣')

        count = 0
        end_time = asyncio.get_event_loop().time() + 30.0

        while asyncio.get_event_loop().time() < end_time:
            try:
                await self.bot.wait_for('message', timeout=end_time - asyncio.get_event_loop().time(), check=check)
                count += 1
            except asyncio.TimeoutError:
                break

        await ctx.send(f"Time's up! You ate {count} items. {'Luffy would be proud!' if count > 20 else 'Keep practicing!'}")

    @commands.command()
    async def rogerriddle(self, ctx):
        """Get a riddle from Gol D. Roger"""
        riddle = random.choice(self.riddles)
        await ctx.send(f"Gol D. Roger's Riddle: {riddle['question']}")

        hints = [
            f"The first letter of the answer is '{riddle['answer'][0]}'",
            f"The answer has {len(riddle['answer'])} letters",
            f"The last letter of the answer is '{riddle['answer'][-1]}'"
        ]

        def check(m):
            return m.channel == ctx.channel and m.content.lower() == riddle['answer'].lower()

        for i in range(3):  # 3 attempts with hints
            try:
                msg = await self.bot.wait_for('message', timeout=30.0, check=check)
                await ctx.send(f"Congratulations, {msg.author.name}! You've solved Roger's riddle!")
                return
            except asyncio.TimeoutError:
                if i < 2:  # Don't give a hint after the last attempt
                    await ctx.send(f"Not quite! Here's a hint: {hints[i]}")

        await ctx.send(f"Time's up! The answer was: {riddle['answer']}")

    @commands.command()
    async def butterfly(self, ctx, *, object: str):
        """Describe an object in the most attractive way possible"""
        if await self.config.guild(ctx.guild).ongoing_games.get("butterfly", False):
            await ctx.send("A Mero Mero challenge is already in progress!")
            return

        await self.config.guild(ctx.guild).ongoing_games.set({"butterfly": True})

        await ctx.send(f"{ctx.author.name} uses the power of the Mero Mero no Mi on a {object}!")
        await ctx.send(f"Everyone, you have 2 minutes to describe this {object} in the most attractive way possible!")

        descriptions = {}

        def check(m):
            return m.channel == ctx.channel and m.author != self.bot.user and m.author not in descriptions

        try:
            while True:
                msg = await self.bot.wait_for('message', timeout=120.0, check=check)
                descriptions[msg.author] = msg.content
        except asyncio.TimeoutError:
            pass

        if not descriptions:
            await ctx.send("No one was charmed enough to describe the object. The challenge is cancelled.")
            await self.config.guild(ctx.guild).ongoing_games.clear()
            return

        # Create an embed for voting
        embed = discord.Embed(title=f"Mero Mero Challenge: {object}", color=discord.Color.pink())
        for i, (author, desc) in enumerate(descriptions.items(), start=1):
            embed.add_field(name=f"{i}. {author.name}'s description", value=desc, inline=False)

        vote_msg = await ctx.send(embed=embed)

        # Add reaction options for voting
        for i in range(1, len(descriptions) + 1):
            await vote_msg.add_reaction(f"{i}\N{COMBINING ENCLOSING KEYCAP}")

        await ctx.send("Vote for the most charming description by reacting to the message above!")

        await asyncio.sleep(30)  # Allow 30 seconds for voting

        vote_msg = await ctx.channel.fetch_message(vote_msg.id)
        votes = {r.emoji: r.count for r in vote_msg.reactions}
        winner_emoji = max(votes, key=votes.get)
        winner = list(descriptions.keys())[int(winner_emoji[0]) - 1]

        await ctx.send(f"The most charming description was by {winner.mention}! They've mastered the power of the Mero Mero no Mi!")

        await self.config.guild(ctx.guild).ongoing_games.clear()

    @commands.Cog.listener()
    async def on_message(self, message):
        """Update user's last activity when they send a message"""
        if message.author.bot:
            return
        await self.config.user(message.author).last_activity.set(int(message.created_at.timestamp()))

def setup(bot):
    bot.add_cog(OnePieceExpandedCogs(bot))
