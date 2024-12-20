import random


def show_random_proverb():
    proverbs = [
        "Fall down seven times, stand up eight. - Japanese Proverb",
        "Better late than never. - English Proverb",
        "The early bird catches the worm. - English Proverb",
        "A journey of a thousand miles begins with a single step. - Chinese Proverb",
        "The pen is mightier than the sword. - English Proverb",
        "Actions speak louder than words. - American Proverb",
        "He who asks a question is a fool for five minutes; he who does not ask remains a fool forever. - Chinese Proverb",
        "Don't count your chickens before they hatch. - English Proverb",
        "If you want to go fast, go alone. If you want to go far, go together. - African Proverb",
        "The nail that sticks out gets hammered down. - Japanese Proverb",
        "Even monkeys fall from trees. - Japanese Proverb",
        "When in Rome, do as the Romans do. - Latin Proverb",
        "Do not worry about tomorrow. - Biblical Proverb",
        "Necessity is the mother of invention. - English Proverb",
        "The enemy of my enemy is my friend. - Arabic Proverb",
        "Knowledge is power. - Latin Proverb",
        "Time and tide wait for no man. - English Proverb",
        "Walls have ears. - English Proverb",
        "Practice makes perfect. - English Proverb",
        # add more..
    ]

    proverb = random.choice(proverbs)
    print(proverb)
