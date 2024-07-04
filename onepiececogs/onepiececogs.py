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
            "quiz_scores": {"sword": 0, "personality": ""},
            "voice_of_all_things_score": 0,
            "cp_rank": None,
            "void_century_knowledge": 0,
            "revolutionary_status": None,
            "world_noble_reputation": 0,
            "poneglyph_fragments": [],
            "rokushiki_techniques": [],
            "fish_man_karate_level": 0
        }
        default_guild = {
            "ongoing_games": {}
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)
        
        self.devil_fruits = {
            'Gomu Gomu': 'Grants the user\'s body the properties of rubber',
            'Mera Mera': 'Allows the user to create, control, and transform into fire',
            'Hie Hie': 'Allows the user to create, control, and transform into ice',
            'Gura Gura': 'Allows the user to create vibrations, or "quakes"',
            'Ope Ope': 'Allows the user to create a spherical space or "room"',
            'Yami Yami': 'Allows the user to create and control darkness',
            'Pika Pika': 'Allows the user to create, control, and transform into light',
            'Mochi Mochi': 'Allows the user to create, control, and transform into mochi',
            'Gasu Gasu': 'Allows the user to create, control, and transform into gas',
            'Suna Suna': 'Allows the user to create, control, and transform into sand',
            'Bara Bara': 'Allows the user to split their body into separate parts',
            'Hana Hana': 'Allows the user to replicate and sprout body parts',
            'Doku Doku': 'Allows the user to create and control poison',
            'Magu Magu': 'Allows the user to create, control, and transform into magma',
            'Goro Goro': 'Allows the user to create, control, and transform into electricity',
            'Kilo Kilo': 'Allows the user to change their body weight',
            'Bane Bane': 'Allows the user to turn their limbs into springs',
            'Ito Ito': 'Allows the user to create and manipulate strings',
            'Awa Awa': 'Allows the user to create and control soap bubbles',
            'Noro Noro': 'Allows the user to slow down anything and anyone'
        }
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
        self.sword_questions = [
            {"q": "Which sword is known as 'Black Blade'?", "a": "Yoru"},
            {"q": "Who wields the Wado Ichimonji?", "a": "Zoro"},
            {"q": "What grade is the sword Enma?", "a": "Great Grade"},
            {"q": "Who forged the Kitetsu swords?", "a": "Kitetsu"},
            {"q": "What is the name of Mihawk's sword?", "a": "Yoru"},
            {"q": "What is the name of Zoro's cursed sword?", "a": "Sandai Kitetsu"},
            {"q": "Which sword did Kozuki Oden wield?", "a": "Enma"},
            {"q": "What is the highest grade of swords in One Piece?", "a": "Supreme Grade"},
            {"q": "Who is the current owner of the Nidai Kitetsu?", "a": "Tenguyama Hitetsu"},
            {"q": "What type of sword is Shusui?", "a": "Black Blade"},
            {"q": "Which sword is known as the 'Sword of the Sea Kings'?", "a": "Kiribachi"},
            {"q": "What is the name of Brook's sword?", "a": "Soul Solid"},
            {"q": "Which sword was made by the legendary swordsmith Shimotsuki Kozaburo?", "a": "Wado Ichimonji"},
            {"q": "What is the name of the sword that 'drinks' blood?", "a": "Shodai Kitetsu"},
            {"q": "Which sword is known as one of the 21 Great Grade swords?", "a": "Shusui"}
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
            "ACBCA": "Chopper", "BAACC": "Franky", "CBACB": "Brook",
            "ABAAC": "Ace", "BCAAB": "Sabo", "CABBA": "Law",
            "ABCCC": "Buggy", "BAAAA": "Shanks", "CBBBA": "Whitebeard",
            "ACCBB": "Jinbe", "BABAC": "Boa Hancock", "CBABA": "Crocodile",
            "AACBC": "Doflamingo", "BCBAA": "Kaido", "CAABC": "Big Mom",
            "ABABB": "Blackbeard", "BACBA": "Marco", "CBAAA": "Rayleigh"
        }
        self.cryptic_messages = {
            "The ancient weapon lies beneath the sea": "Poseidon is hidden in Fishman Island",
            "When all moons align, the path will clear": "The Road Poneglyphs will reveal the way to Laugh Tale",
            "In the land of Wano, a secret sleeps": "The truth about the Void Century is connected to Wano",
            "The voice of all things speaks in silence": "The ability to hear the Voice of All Things is rare and powerful",
            "To reach Laugh Tale, follow the Road": "The Road Poneglyphs are needed to find the final island",
            "The true history lies hidden in the shadows": "The World Government is hiding the truth about the Void Century",
            "Only those with the will of D can change the world": "The D. clan has a special role in the world's destiny",
            "The great kingdom fell, but its legacy endures": "The Ancient Kingdom's ideals live on through its descendants",
            "In the eye of the storm, the truth awaits": "Im-sama holds the secrets of the World Government",
            "The three weapons united will bring about a new dawn": "Pluton, Poseidon, and Uranus together can change the world",
            "The twenty kingdoms formed a pact of silence": "The World Government was founded on a conspiracy of silence",
            "The void century holds the key to freedom": "Understanding the Void Century is crucial for world liberation",
            "When sea and sky become one, the door will open": "The All Blue and the One Piece are connected",
            "The one piece is more than just a treasure": "The One Piece represents the truth of the world",
            "The ancient kingdom's name must never be forgotten": "The name of the Ancient Kingdom is a key to understanding history"
        }
        self.riddles = [
            {"question": "I am not alive, but I grow; I don't have lungs, but I need air; I don't have a mouth, but water kills me. What am I?", "answer": "fire"},
            {"question": "I have cities, but no houses. I have mountains, but no trees. I have water, but no fish. What am I?", "answer": "map"},
            {"question": "What has keys, but no locks; space, but no room; you can enter, but not go in?", "answer": "keyboard"},
            {"question": "I am always hungry; I must always be fed. The finger I touch, will soon turn red. What am I?", "answer": "fire"},
            {"question": "I have a head and a tail that will never meet. Having too many of me is always a treat. What am I?", "answer": "coin"},
            {"question": "I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?", "answer": "echo"},
            {"question": "You see a boat filled with people. It has not sunk, but when you look again you don't see a single person on the boat. Why?", "answer": "All the people were married"},
            {"question": "What has branches, but no fruit, trunk or leaves?", "answer": "bank"},
            {"question": "What can travel around the world while staying in a corner?", "answer": "stamp"},
            {"question": "I have cities, but no houses; forests, but no trees; and rivers, but no water. What am I?", "answer": "map"},
            {"question": "What has a head and a tail that are only made of digits?", "answer": "coin"},
            {"question": "I am taken from a mine and shut up in a wooden case, from which I am never released, and yet I am used by everyone. What am I?", "answer": "pencil lead"},
            {"question": "What belongs to you, but other people use it more than you?", "answer": "your name"},
            {"question": "The more you take, the more you leave behind. What am I?", "answer": "footsteps"},
            {"question": "What has many keys, but no locks; space, but no room; you can enter, but not go in?", "answer": "keyboard"}
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
            await ctx.send(f"You have {60 // difficulty} seconds! Type '!hint' for a clue.")

            hint_level = 0
            hint_penalty = 0

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author and (m.content.lower() == message.lower() or m.content.lower() == '!hint')

            end_time = asyncio.get_event_loop().time() + 60.0 / difficulty

            while asyncio.get_event_loop().time() < end_time:
                try:
                    msg = await self.bot.wait_for('message', timeout=end_time - asyncio.get_event_loop().time(), check=check)
                    if msg.content.lower() == '!hint':
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
                except asyncio.TimeoutError:
                    await ctx.send(f"Time's up! The correct decoding was: {message}")
                    break

            difficulty += 1
            await ctx.send("Prepare for the next Poneglyph! Type 'continue' to proceed or 'stop' to end the game.")
            
            def continue_check(m):
                return m.author == ctx.author and m.content.lower() in ['continue', 'stop']

            try:
                continue_msg = await self.bot.wait_for('message', timeout=15.0, check=continue_check)
                if continue_msg.content.lower() == 'stop':
                    break
            except asyncio.TimeoutError:
                await ctx.send("No response received. Ending the game.")
                break

        await ctx.send(f"Game Over! Your final score is {score}. You reached difficulty level {difficulty}.")

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
        embed = discord.Embed(title="One Piece Character Quiz", color=discord.Color.blue())
        
        for i, q in enumerate(self.personality_questions, start=1):
            embed.clear_fields()
            embed.add_field(name=f"Question {i}", value=q['q'], inline=False)
            for option in q['options']:
                embed.add_field(name=option[0], value=option[2:], inline=True)
            
            await ctx.send(embed=embed)
            
            def check(m):
                return m.author == ctx.author and m.content.upper() in "ABC"
            
            try:
                answer = await self.bot.wait_for('message', timeout=30.0, check=check)
                answers += answer.content.upper()
            except asyncio.TimeoutError:
                await ctx.send("You took too long to answer. Quiz cancelled.")
                return

        character = self.character_results.get(answers, "Pandaman")
        result_embed = discord.Embed(title="Quiz Result", color=discord.Color.green())
        result_embed.add_field(name="Your One Piece Character", value=f"You're most like {character}!")
        await ctx.send(embed=result_embed)
        await self.config.user(ctx.author).quiz_scores.personality.set(character)

    @commands.command()
    async def voiceofallthings(self, ctx):
        """Use the Voice of All Things to decipher cryptic messages"""
        if await self.config.guild(ctx.guild).ongoing_games.get("voice_of_all_things", False):
            await ctx.send("A Voice of All Things challenge is already in progress!")
            return

        await self.config.guild(ctx.guild).ongoing_games.set({"voice_of_all_things": True})

        await ctx.send("You've awakened the Voice of All Things! Decipher the cryptic messages to uncover the world's secrets.")
        
        score = 0
        rounds = 3

        for round in range(1, rounds + 1):
            cryptic_message, true_meaning = random.choice(list(self.cryptic_messages.items()))
            
            embed = discord.Embed(title=f"Round {round}: Voice of All Things", color=discord.Color.purple())
            embed.add_field(name="Cryptic Message", value=cryptic_message, inline=False)
            embed.add_field(name="Instructions", value="Interpret the meaning of this message. You have 60 seconds!", inline=False)
            await ctx.send(embed=embed)

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                user_interpretation = await self.bot.wait_for('message', timeout=60.0, check=check)
                
                # Simple similarity check (you might want to use a more sophisticated method)
                similarity = sum(word in user_interpretation.content.lower() for word in true_meaning.lower().split())
                similarity_score = similarity / len(true_meaning.split())

                if similarity_score > 0.5:
                    await ctx.send(f"Your interpretation resonates with the Voice of All Things! The true meaning was: {true_meaning}")
                    score += 1
                else:
                    await ctx.send(f"Your interpretation was close, but not quite there. The true meaning was: {true_meaning}")

            except asyncio.TimeoutError:
                await ctx.send(f"Time's up! The true meaning was: {true_meaning}")

            await asyncio.sleep(2)  # Short pause between rounds

        await ctx.send(f"Challenge complete! You correctly interpreted {score} out of {rounds} messages.")
        
        user_data = await self.config.user(ctx.author).all()
        user_data["voice_of_all_things_score"] += score
        await self.config.user(ctx.author).set(user_data)

        await ctx.send(f"Your total Voice of All Things score is now {user_data['voice_of_all_things_score']}!")

        await self.config.guild(ctx.guild).ongoing_games.clear
        
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
        guild_data = await self.config.guild(ctx.guild).all()
        if guild_data["ongoing_games"].get("butterfly", False):
            await ctx.send("A Mero Mero challenge is already in progress!")
            return

        guild_data["ongoing_games"]["butterfly"] = True
        await self.config.guild(ctx.guild).set(guild_data)

        await ctx.send(f"{ctx.author.mention} uses the power of the Mero Mero no Mi on a {object}!")
        await ctx.send(f"Everyone, you have 2 minutes to describe this {object} in the most attractive way possible!")

        descriptions = {}

        def check(m):
            return m.channel == ctx.channel and m.author != self.bot.user and m.author not in descriptions

        try:
            while len(descriptions) < 10:  # Limit to 10 entries
                msg = await self.bot.wait_for('message', timeout=120.0, check=check)
                descriptions[msg.author] = msg.content
        except asyncio.TimeoutError:
            pass

        if not descriptions:
            await ctx.send("No one was charmed enough to describe the object. The challenge is cancelled.")
            guild_data["ongoing_games"]["butterfly"] = False
            await self.config.guild(ctx.guild).set(guild_data)
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
        votes = {r.emoji: r.count - 1 for r in vote_msg.reactions}  # Subtract 1 to account for bot's reaction
        winner_emoji = max(votes, key=votes.get)
        winner = list(descriptions.keys())[int(winner_emoji[0]) - 1]

        await ctx.send(f"The most charming description was by {winner.mention}! They've mastered the power of the Mero Mero no Mi!")

        guild_data["ongoing_games"]["butterfly"] = False
        await self.config.guild(ctx.guild).set(guild_data)

    @commands.group()
    async def cp(self, ctx):
        """Cipher Pol commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `.help cp` to see available Cipher Pol commands.")

    @cp.command(name="join")
    async def cp_join(self, ctx):
        """Join Cipher Pol as a rookie agent"""
        user_data = await self.config.user(ctx.author).all()
        if user_data['cp_rank']:
            await ctx.send("You're already a member of Cipher Pol!")
            return

        user_data['cp_rank'] = "Rookie"
        await self.config.user(ctx.author).set(user_data)
        await ctx.send("Welcome to Cipher Pol, rookie! Your training begins now.")

    @cp.command(name="mission")
    async def cp_mission(self, ctx):
        """Undertake a Cipher Pol mission"""
        user_data = await self.config.user(ctx.author).all()
        if not user_data['cp_rank']:
            await ctx.send("You must join Cipher Pol first!")
            return

        missions = [
            "Infiltrate a pirate crew",
            "Gather intelligence on a Revolutionary Army base",
            "Protect a Celestial Dragon during their visit to a kingdom",
            "Investigate rumors of an Ancient Weapon",
            "Assassinate a corrupt kingdom official"
        ]

        mission = random.choice(missions)
        await ctx.send(f"Your mission, should you choose to accept it: {mission}")

        await ctx.send("Do you accept this mission? (yes/no)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['yes', 'no']

        try:
            msg = await self.bot.wait_for('message', timeout=30.0, check=check)
            if msg.content.lower() == 'yes':
                success = random.choice([True, False])
                if success:
                    await ctx.send("Mission accomplished! Your rank in Cipher Pol has increased.")
                    ranks = ["Rookie", "Agent", "Senior Agent", "CP9 Candidate", "CP9 Member"]
                    current_rank_index = ranks.index(user_data['cp_rank'])
                    if current_rank_index < len(ranks) - 1:
                        user_data['cp_rank'] = ranks[current_rank_index + 1]
                        await self.config.user(ctx.author).set(user_data)
                else:
                    await ctx.send("Mission failed. Better luck next time, agent.")
            else:
                await ctx.send("Mission declined. Remember, the World Government is always watching.")
        except asyncio.TimeoutError:
            await ctx.send("Time's up! The mission was reassigned to another agent.")

    @commands.command()
    async def void_century(self, ctx):
        """Research the Void Century"""
        user_data = await self.config.user(ctx.author).all()
        
        research_topics = [
            "The Great Kingdom",
            "The Ancient Weapons",
            "The Will of D",
            "The Creation of the World Government",
            "The True History"
        ]
        
        topic = random.choice(research_topics)
        await ctx.send(f"You've uncovered information about: {topic}")
        
        await ctx.send("What do you think this means? (Enter your interpretation)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            interpretation = await self.bot.wait_for('message', timeout=60.0, check=check)
            user_data['void_century_knowledge'] += 1
            user_data['poneglyph_fragments'].append({"topic": topic, "interpretation": interpretation.content})
            await self.config.user(ctx.author).set(user_data)
            await ctx.send(f"Interesting theory! Your Void Century knowledge has increased to {user_data['void_century_knowledge']}.")
        except asyncio.TimeoutError:
            await ctx.send("The secrets of the Void Century remain elusive...")

    @commands.group()
    async def revolutionary(self, ctx):
        """Revolutionary Army commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `!help revolutionary` to see available Revolutionary Army commands.")

    @revolutionary.command(name="join")
    async def revolutionary_join(self, ctx):
        """Join the Revolutionary Army"""
        user_data = await self.config.user(ctx.author).all()
        if user_data['revolutionary_status']:
            await ctx.send("You're already a member of the Revolutionary Army!")
            return

        user_data['revolutionary_status'] = "Recruit"
        await self.config.user(ctx.author).set(user_data)
        await ctx.send("Welcome to the Revolutionary Army! Together, we'll change the world.")

    @revolutionary.command(name="mission")
    async def revolutionary_mission(self, ctx):
        """Undertake a mission for the Revolutionary Army"""
        user_data = await self.config.user(ctx.author).all()
        if not user_data['revolutionary_status']:
            await ctx.send("You must join the Revolutionary Army first!")
            return

        missions = [
            "Liberate a kingdom from a tyrannical ruler",
            "Sabotage a World Government weapons facility",
            "Rescue prisoners from a corrupt Marine base",
            "Gather intelligence on Celestial Dragon activities",
            "Distribute revolutionary propaganda in a controlled territory"
        ]

        mission = random.choice(missions)
        await ctx.send(f"Your mission for the Revolutionary Army: {mission}")

        await ctx.send("Do you accept this mission? (yes/no)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['yes', 'no']

        try:
            msg = await self.bot.wait_for('message', timeout=30.0, check=check)
            if msg.content.lower() == 'yes':
                success = random.choice([True, False])
                if success:
                    await ctx.send("Mission successful! You've struck a blow against the World Government.")
                    ranks = ["Recruit", "Soldier", "Commander", "Chief of Staff", "Army General"]
                    current_rank_index = ranks.index(user_data['revolutionary_status'])
                    if current_rank_index < len(ranks) - 1:
                        user_data['revolutionary_status'] = ranks[current_rank_index + 1]
                        await self.config.user(ctx.author).set(user_data)
                        await ctx.send(f"You've been promoted to {user_data['revolutionary_status']}!")
                else:
                    await ctx.send("Mission failed. The World Government's grip remains strong...")
            else:
                await ctx.send("Mission declined. Remember, the fate of the world hangs in the balance.")
        except asyncio.TimeoutError:
            await ctx.send("Time's up! The opportunity to make a difference has passed.")

    @commands.command()
    async def celestial_dragon(self, ctx):
        """Interact with a Celestial Dragon"""
        user_data = await self.config.user(ctx.author).all()
        
        scenarios = [
            "A Celestial Dragon demands you bow before them.",
            "A Celestial Dragon is mistreating a slave in front of you.",
            "A Celestial Dragon offers you a large sum of money to perform a questionable task.",
            "You witness a Celestial Dragon abusing their authority with the Marines.",
            "A Celestial Dragon is about to shoot someone for bumping into them."
        ]
        
        scenario = random.choice(scenarios)
        await ctx.send(f"Scenario: {scenario}\n\nHow do you respond? (obey/defy)")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['obey', 'defy']

        try:
            response = await self.bot.wait_for('message', timeout=30.0, check=check)
            if response.content.lower() == 'obey':
                user_data['world_noble_reputation'] += 1
                await ctx.send("You've pleased the Celestial Dragon, but at what cost to your conscience?")
            else:
                user_data['world_noble_reputation'] -= 1
                await ctx.send("You've defied the Celestial Dragon. Your actions may have consequences...")
            
            await self.config.user(ctx.author).set(user_data)
            await ctx.send(f"Your reputation with World Nobles is now {user_data['world_noble_reputation']}.")
        except asyncio.TimeoutError:
            await ctx.send("You hesitated too long. The Celestial Dragon has lost interest in you.")

    @commands.command()
    async def rokushiki(self, ctx):
        """Train in Rokushiki techniques"""
        user_data = await self.config.user(ctx.author).all()
        
        techniques = [
            "Geppo (Moon Step)",
            "Tekkai (Iron Body)",
            "Shigan (Finger Pistol)",
            "Rankyaku (Storm Leg)",
            "Soru (Shave)",
            "Kami-e (Paper Art)"
        ]
        
        available_techniques = [t for t in techniques if t not in user_data['rokushiki_techniques']]
        
        if not available_techniques:
            await ctx.send("You have mastered all Rokushiki techniques!")
            return
        
        technique = random.choice(available_techniques)
        await ctx.send(f"You begin training in {technique}.")
        
        await ctx.send("React with 💪 when you're ready to attempt mastering this technique.")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == '💪'

        try:
            await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            success = random.random() < 0.5  # 50% chance of success
            if success:
                user_data['rokushiki_techniques'].append(technique)
                await self.config.user(ctx.author).set(user_data)
                await ctx.send(f"Congratulations! You've mastered {technique}.")
            else:
                await ctx.send(f"You weren't able to master {technique} this time. Keep training!")
        except asyncio.TimeoutError:
            await ctx.send("Training session expired. Remember, mastering Rokushiki requires dedication!")

    @commands.command()
    async def fishman_karate(self, ctx):
        """Train in Fish-Man Karate"""
        user_data = await self.config.user(ctx.author).all()
        
        current_level = user_data['fish_man_karate_level']
        
        if current_level >= 10:
            await ctx.send("You have mastered Fish-Man Karate!")
            return
        
        await ctx.send(f"Current Fish-Man Karate Level: {current_level}")
        await ctx.send("You begin your Fish-Man Karate training. React with 🌊 when you're ready to test your skills.")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == '🌊'

        try:
            await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
            success = random.random() < 0.7  # 70% chance of success
            if success:
                user_data['fish_man_karate_level'] += 1
                await self.config.user(ctx.author).set(user_data)
                await ctx.send(f"Your Fish-Man Karate skills have improved! New level: {user_data['fish_man_karate_level']}")
            else:
                await ctx.send("Your training was unsuccessful this time. Keep practicing!")
        except asyncio.TimeoutError:
            await ctx.send("Training session expired. The secrets of Fish-Man Karate require patience and dedication!")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Update user's last activity when they send a message"""
        if message.author.bot:
            return
        await self.config.user(message.author).last_activity.set(int(message.created_at.timestamp()))

def setup(bot):
    bot.add_cog(OnePieceExpandedCogs(bot))
