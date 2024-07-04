import random
import asyncio
import string
from datetime import datetime, timedelta
from redbot.core import commands, Config
import discord

class OnePieceExpandedCogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_user = {
            "last_activity": None,
            "character": None,
            "devil_fruit": None
        }
        default_guild = {
            "ongoing_games": {}
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        
        self.devil_fruits = [
            'Gomu Gomu', 'Mera Mera', 'Hie Hie', 'Gura Gura', 'Ope Ope', 'Yami Yami', 'Pika Pika', 'Mochi Mochi', 'Gasu Gasu', 'Suna Suna',
            'Bara Bara', 'Bane Bane', 'Doku Doku', 'Hana Hana', 'Soru Soru', 'Goro Goro', 'Horo Horo', 'Kilo Kilo', 'Bari Bari'
        ]
        self.poneglyph_messages = [
            "The ancient weapon lies beneath the sea",
            "When all moons align, the path will clear",
            "In the land of Wano, a secret sleeps",
            "The voice of all things speaks in silence",
            "To reach Laugh Tale, follow the Road",
            "The true history lies hidden in the shadows",
            "Only those with the will of D can change the world",
            "The great kingdom fell, but its legacy endures",
            "In the eye of the storm, the truth awaits",
            "The three weapons united will bring about a new dawn",
            "The twenty kingdoms formed a pact of silence",
            "The void century holds the key to freedom",
            "When sea and sky become one, the door will open",
            "The one piece is more than just a treasure",
            "The ancient kingdom's name must never be forgotten"
        ]
        self.ship_materials = ['Adam Wood', 'Seastone', 'Treasure', 'Cannon', 'Sail', 'Figurehead', 'Helm', 'Kairoseki', 'Dials', 'Transponder Snail']
        self.weather_conditions = ['Sunny', 'Rainy', 'Thunderstorm', 'Cyclone', 'Sea King Attack', 'Candy Rain', 'Meat Meteor Shower', 'Fog', 'Hail', 'Rainbow Mist']
        self.riddles = [
            {"question": "I am not alive, but I grow; I don't have lungs, but I need air; I don't have a mouth, but water kills me. What am I?", "answer": "fire"},
            {"question": "I have cities, but no houses. I have mountains, but no trees. I have water, but no fish. What am I?", "answer": "map"},
            {"question": "What has keys, but no locks; space, but no room; you can enter, but not go in?", "answer": "keyboard"},
            {"question": "I am always hungry; I must always be fed. The finger I touch, will soon turn red. What am I?", "answer": "fire"},
            {"question": "I have a head and a tail that will never meet. Having too many of me is always a treat. What am I?", "answer": "coin"},
            {"question": "I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?", "answer": "echo"},
            {"question": "You see a boat filled with people. It has not sunk, but when you look again you don't see a single person on the boat. Why?", "answer": "All the people were married"},
            {"question": "What has cities, but no houses; forests, but no trees; and rivers, but no water?", "answer": "map"},
            {"question": "I have branches, but no fruit, trunk or leaves. What am I?", "answer": "bank"},
            {"question": "What can travel around the world while staying in a corner?", "answer": "stamp"}
        ]
        self.characters = ['Luffy', 'Zoro', 'Nami', 'Usopp', 'Sanji', 'Chopper', 'Robin', 'Franky', 'Brook', 'Jinbe', 'Ace', 'Sabo', 'Law', 'Kid', 'Shanks', 'Whitebeard', 'Kaido', 'Big Mom', 'Blackbeard']

    @commands.command()
    async def fusefruit(self, ctx):
        """Generate a fusion of two Devil Fruits and discuss its powers"""
        fruit1 = random.choice(self.devil_fruits)
        fruit2 = random.choice(self.devil_fruits)
        while fruit1 == fruit2:
            fruit2 = random.choice(self.devil_fruits)
        
        fusion_name = f"{fruit1.split()[0]} {fruit2.split()[1]}"
        await ctx.send(f"New Devil Fruit Fusion: {fusion_name} no Mi!")
        await ctx.send("What powers do you think this fruit would have? You have 2 minutes to discuss!")

        def check(m):
            return m.channel == ctx.channel and m.author != self.bot.user

        responses = []
        try:
            async with ctx.typing():
                while True:
                    msg = await self.bot.wait_for('message', timeout=120.0, check=check)
                    responses.append(f"{msg.author.name}: {msg.content}")
        except asyncio.TimeoutError:
            pass

        if responses:
            await ctx.send("Here are the ideas for the fusion fruit's powers:")
            for response in responses:
                await ctx.send(response)
            
            # Vote for the best power
            vote_msg = await ctx.send("Vote for the best power idea by reacting with the corresponding number:")
            for i, response in enumerate(responses[:5], start=1):  # Limit to top 5 ideas
                await vote_msg.add_reaction(f"{i}\N{COMBINING ENCLOSING KEYCAP}")

            await asyncio.sleep(30)  # Allow 30 seconds for voting

            vote_msg = await ctx.channel.fetch_message(vote_msg.id)
            votes = {r.emoji: r.count for r in vote_msg.reactions}
            winner = max(votes, key=votes.get)
            winning_idea = responses[int(winner[0]) - 1]

            await ctx.send(f"The most popular power for the {fusion_name} no Mi is:\n{winning_idea}")
        else:
            await ctx.send("Looks like the fruit's powers remain a mystery!")

    def create_cipher(self, message, difficulty):
        unique_chars = list(set(message.lower()))
        shuffled = unique_chars.copy()
        for _ in range(difficulty):
            random.shuffle(shuffled)
        return dict(zip(unique_chars, shuffled))

    def encode_message(self, message, cipher):
        return ''.join(cipher.get(c.lower(), c) for c in message)

    def get_hint(self, message, hint_level):
        if hint_level == 1:
            return f"The message starts with '{message[0]}' and ends with '{message[-1]}'."
        elif hint_level == 2:
            words = message.split()
            return f"The message contains {len(words)} words."
        elif hint_level == 3:
            return f"A key word in the message is '{random.choice(message.split())}'."

    @commands.command()
    async def poneglyph(self, ctx):
        """Start a Poneglyph decoding game with increasing difficulty and hints"""
        difficulty = 1
        score = 0
        
        await ctx.send("Welcome to the Poneglyph Decoding Challenge! Decipher as many Poneglyphs as you can. The difficulty will increase with each correct answer. Type '!hint' for a clue, but be aware it will reduce your score for the current round.")

        while True:
            message = random.choice(self.poneglyph_messages)
            cipher = self.create_cipher(message, difficulty)
            encoded = self.encode_message(message, cipher)
            await ctx.send(f"Difficulty Level {difficulty}\nDecipher this Poneglyph: `{encoded}`")
            await ctx.send(f"You have {60 // difficulty} seconds! Type '.hint' for a clue.")

            hint_level = 0
            hint_penalty = 0

            def check(m):
                return m.channel == ctx.channel and (m.content.lower() == message.lower() or m.content.lower() == '!hint')

            try:
                while True:
                    msg = await self.bot.wait_for('message', timeout=60.0 / difficulty, check=check)
                    if msg.content.lower() == '.hint':
                        hint_level += 1
                        if hint_level <= 3:
                            hint = self.get_hint(message, hint_level)
                            hint_penalty += 2 * difficulty  # Increase penalty with difficulty
                            await ctx.send(f"Hint {hint_level}: {hint}")
                        else:
                            await ctx.send("No more hints available!")
                    else:
                        await ctx.send(f"Congratulations {msg.author.mention}! You've decoded the Poneglyph!")
                        round_score = max(0, difficulty * 10 - hint_penalty)
                        score += round_score
                        await ctx.send(f"Round score: {round_score} (Hint penalty: -{hint_penalty})")
                        await ctx.send(f"Your total score: {score}")
                        break

                difficulty += 1
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


    @commands.command()
    async def buildship(self, ctx):
        """Start an extended Shipwright Challenge with multiple rounds"""
        rounds = 3
        participants = {}

        await ctx.send(f"Welcome to the Grand Shipwright Challenge! We'll have {rounds} rounds of ship building.")

        for round_num in range(1, rounds + 1):
            materials = random.sample(self.ship_materials, 5)
            await ctx.send(f"Round {round_num}! Build a ship using these materials: {', '.join(materials)}")
            await ctx.send("Describe your ship design in the next 2 minutes. Other crew members will vote on the best design!")

            designs = {}

            def check(m):
                return m.channel == ctx.channel and m.author != self.bot.user

            try:
                async with ctx.typing():
                    while True:
                        msg = await self.bot.wait_for('message', timeout=120.0, check=check)
                        designs[msg.author] = msg.content
            except asyncio.TimeoutError:
                pass

            if not designs:
                await ctx.send("No designs submitted. Moving to the next round.")
                continue

            design_msg = await ctx.send("Time's up! Vote for your favorite design by reacting with the corresponding number:")
            for i, (author, design) in enumerate(designs.items(), start=1):
                await ctx.send(f"{i}. {author.name}'s design: {design}")
                await design_msg.add_reaction(f"{i}\N{COMBINING ENCLOSING KEYCAP}")

            await asyncio.sleep(30)  # Allow 30 seconds for voting

            design_msg = await ctx.channel.fetch_message(design_msg.id)
            votes = {r.emoji: r.count for r in design_msg.reactions}
            winner = max(votes, key=votes.get)
            winning_author = list(designs.keys())[int(winner[0]) - 1]

            await ctx.send(f"The winning design for round {round_num} is by {winning_author.mention}! Congratulations!")
            participants[winning_author] = participants.get(winning_author, 0) + 1

        # Announce overall winner
        overall_winner = max(participants, key=participants.get)
        await ctx.send(f"The Grand Shipwright Champion is {overall_winner.mention} with {participants[overall_winner]} round wins!")

    @commands.command()
    async def vivrecard(self, ctx, member: discord.Member):
        """Check the 'health' of a user based on their recent activity"""
        last_activity = await self.config.user(member).last_activity()
        if not last_activity:
            await ctx.send(f"{member.name}'s Vivre Card hasn't been created yet.")
            return

        last_activity = datetime.fromtimestamp(last_activity)
        time_diff = datetime.now() - last_activity
        health = max(0, 100 - time_diff.days * 10)  # Decrease health by 10% each day of inactivity

        if health > 75:
            status = "is in perfect health!"
        elif health > 50:
            status = "is doing alright, but could use some rest."
        elif health > 25:
            status = "is in danger! They need support!"
        else:
            status = "is barely hanging on! Send help immediately!"

        # Create a visual representation of the Vivre Card
        vivre_card = "🟩" * (health // 10) + "⬜" * (10 - health // 10)

        await ctx.send(f"{member.name}'s Vivre Card:\n{vivre_card}\nHealth: {health}%\nThey {status}")

    @commands.command()
    async def fruitroulette(self, ctx):
        """Play an extended version of Devil Fruit Russian Roulette"""
        if await self.config.guild(ctx.guild).ongoing_games.get("fruitroulette", False):
            await ctx.send("A game of Devil Fruit Roulette is already in progress!")
            return

        await self.config.guild(ctx.guild).ongoing_games.set({"fruitroulette": True})

        players = []
        await ctx.send("Devil Fruit Roulette is starting! Type '!join' to participate. Game starts in 30 seconds!")

        def check(m):
            return m.content.lower() == '!join' and m.channel == ctx.channel and m.author not in players

        try:
            while True:
                msg = await self.bot.wait_for('message', timeout=30.0, check=check)
                players.append(msg.author)
                await ctx.send(f"{msg.author.name} has joined the game!")
        except asyncio.TimeoutError:
            if len(players) < 2:
                await ctx.send("Not enough players. Game cancelled.")
                await self.config.guild(ctx.guild).ongoing_games.clear()
                return

        await ctx.send("The game begins! Each player will eat a Devil Fruit and face its consequences.")
        
        for player in players:
            fruit = random.choice(self.devil_fruits)
            await ctx.send(f"{player.name} eats the {fruit} no Mi...")
            await asyncio.sleep(2)
            
            effect = random.choice([
                "gains incredible power",
                "struggles with their new ability",
                "feels sick and dizzy",
                "transforms unexpectedly",
                "can't control their power"
            ])
            
            await ctx.send(f"{player.name} {effect}!")
            await asyncio.sleep(2)

        await ctx.send("All players have eaten their Devil Fruits! Now it's time for a challenge to test your new powers!")
        
        challenge = random.choice([
            "swim across a small pond",
            "lift a heavy boulder",
            "catch a flying bird",
            "resist the temptation of your natural weakness",
            "perform a unique trick with your new power"
        ])

        await ctx.send(f"The challenge is to {challenge}! Players, describe how you attempt this with your new power.")

        responses = {}
        
        def response_check(m):
            return m.author in players and m.author not in responses

        try:
            while len(responses) < len(players):
                msg = await self.bot.wait_for('message', timeout=60.0, check=response_check)
                responses[msg.author] = msg.content
        except asyncio.TimeoutError:
            pass

        if responses:
            await ctx.send("Let's vote on who used their power best!")
            vote_msg = await ctx.send("React to vote:")
            for i, (player, response) in enumerate(responses.items(), start=1):
                await ctx.send(f"{i}. {player.name}: {response}")
                await vote_msg.add_reaction(f"{i}\N{COMBINING ENCLOSING KEYCAP}")

            await asyncio.sleep(30)  # Allow 30 seconds for voting

            vote_msg = await ctx.channel.fetch_message(vote_msg.id)
            votes = {r.emoji: r.count for r in vote_msg.reactions}
            winner_emoji = max(votes, key=votes.get)
            winner = list(responses.keys())[int(winner_emoji[0]) - 1]

            await ctx.send(f"The winner is {winner.mention}! They've mastered their new Devil Fruit power!")
        else:
            await ctx.send("No one managed to complete the challenge. It seems mastering Devil Fruits is harder than it looks!")

        await self.config.guild(ctx.guild).ongoing_games.clear()

    @commands.command()
    async def whoami(self, ctx):
        """Start an extended impersonation game"""
        if await self.config.guild(ctx.guild).ongoing_games.get("whoami", False):
            await ctx.send("An impersonation game is already in progress!")
            return

        await self.config.guild(ctx.guild).ongoing_games.set({"whoami": True})

        character = random.choice(self.characters)
        await self.config.user(ctx.author).character.set(character)
        await ctx.author.send(f"You are {character}! Start acting like them in the chat. Others will try to guess who you are!")
        await ctx.send(f"{ctx.author.name} has received their character! Everyone else, try to guess who they are!")

        # Add some character traits to help the player
        traits = {
            "Luffy": "loves meat, says 'I'm gonna be the Pirate King!'",
            "Zoro": "often gets lost, loves sake",
            "Nami": "loves money and tangerines, expert navigator",
            "Usopp": "tells tall tales, a bit cowardly but brave when it counts",
            "Sanji": "never hits women, excellent cook, flirts a lot",
            # Add traits for other characters...
        }

        if character in traits:
            await ctx.author.send(f"Some traits to help you act like {character}: {traits[character]}")

        await ctx.send("The game will last for 5 minutes. Use `!guess <character>` to make a guess!")

        await asyncio.sleep(300)  # 5 minutes game time

        await ctx.send("Time's up! The impersonation game has ended.")
        await self.config.guild(ctx.guild).ongoing_games.clear()
        await self.config.user(ctx.author).character.set(None)

    @commands.command()
    async def guess(self, ctx, *, character: str):
        """Guess a player's character in the impersonation game"""
        game_status = await self.config.guild(ctx.guild).ongoing_games.get("whoami", False)
        if not game_status:
            await ctx.send("There's no active impersonation game right now!")
            return

        for member in ctx.guild.members:
            true_character = await self.config.user(member).character()
            if true_character:
                if character.lower() == true_character.lower():
                    await ctx.send(f"Correct! {member.name} was indeed {true_character}!")
                    await self.config.user(member).character.set(None)
                    await self.config.guild(ctx.guild).ongoing_games.clear()
                    return
        
        await ctx.send("Sorry, that's not correct. Keep guessing!")

    @commands.command()
    async def namiforecast(self, ctx):
        """Get an interactive Grand Line weather forecast"""
        forecast = [random.choice(self.weather_conditions) for _ in range(5)]
        danger_level = sum(self.weather_conditions.index(condition) for condition in forecast) / len(forecast)
        
        embed = discord.Embed(title="Nami's Grand Line Forecast", color=discord.Color.blue())
        for i, condition in enumerate(forecast, 1):
            embed.add_field(name=f"Hour {i}", value=condition, inline=False)
        
        if danger_level < 3:
            embed.set_footer(text="Nami says: 'Smooth sailing ahead! Perfect weather for treasure hunting!'")
        elif danger_level < 6:
            embed.set_footer(text="Nami says: 'Be cautious! The weather might turn tricky.'")
        else:
            embed.set_footer(text="Nami says: 'All hands on deck! We're in for a wild ride!'")

        forecast_msg = await ctx.send(embed=embed)

        # Add reaction options for user interaction
        reactions = ["⛵", "🏝️", "🌊", "🏴‍☠️"]
        for reaction in reactions:
            await forecast_msg.add_reaction(reaction)

        await ctx.send("How will you respond to this forecast? React to choose your action!")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in reactions

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            if str(reaction.emoji) == "⛵":
                await ctx.send("You decide to set sail despite the conditions. Adventure awaits!")
            elif str(reaction.emoji) == "🏝️":
                await ctx.send("You choose to stay on the island and wait for better weather. Safety first!")
            elif str(reaction.emoji) == "🌊":
                await ctx.send("You brave the storms and high waves. It's a rough journey, but you might find unexpected treasures!")
            elif str(reaction.emoji) == "🏴‍☠️":
                await ctx.send("You raise the Jolly Roger and challenge the weather itself. That's the pirate spirit!")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to decide. The weather waits for no one!")

    @commands.command()
    async def rogerriddle(self, ctx):
        """Get a riddle from Gol D. Roger with hints"""
        riddle = random.choice(self.riddles)
        await ctx.send(f"Gol D. Roger's Riddle: {riddle['question']}")

        hints = [
            "The first letter of the answer is " + riddle['answer'][0],
            f"The answer has {len(riddle['answer'])} letters",
            "The last letter of the answer is " + riddle['answer'][-1]
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
        await self.config.user(message.author).last_activity.set(int(datetime.now().timestamp()))

def setup(bot):
    bot.add_cog(OnePieceExpandedCogs(bot))
