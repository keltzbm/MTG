# pylint: disable = no-member
import calendar
import collections
import datetime
import os
import re
import sys
from urllib.request import urlopen

from bs4 import BeautifulSoup

from classes import Deck, DeckList
from scrapeDecks import getMagicGGDeckLists, getMTGODeckLists, getMTGOEvents

def convertFileToDeckList(path):
    deck = Deck([], [])
    sideboard = Deck([], [])
    flag = False
    with open(path, "r") as deckList:
        for line in deckList:
            lineSplit = line.strip().split()
            if not(lineSplit):
                flag = True
            elif flag:
                sideboard.counts.append(lineSplit[0])
                sideboard.cards.append(" ".join(lineSplit[1:]))
            else:
                deck.counts.append(lineSplit[0])
                deck.cards.append(" ".join(lineSplit[1:]))
    return DeckList(deck, sideboard)

def createDeckListFile(deckList, path):
    with open(path, "w") as newList:
        for deck in deckList.__dict__:
            deck = getattr(deckList, deck)
            for card, count in zip(getattr(deck, "cards"), getattr(deck, "counts")):
                newList.write(count + " " + getattr(card, "Card Name") + "\n")
            newList.write("\n")

def createFolders(path, addOns):
    for addOn in addOns:
        path = os.path.join(path, addOn)
        if not(os.path.exists(path)):
            try:
                os.mkdir(path)
            except:
                print("Failed to create directory " + addOn + ".")
    return path

def compareDecks(newDeckList, existingDeckList):
    for card, count in zip(newDeckList.deck.cards, newDeckList.deck.counts):
        if getattr(card, "Card Name") in existingDeckList.deck.cards:
            cardIndex = existingDeckList.deck.cards.index(getattr(card, "Card Name"))
            if count != existingDeckList.deck.counts[cardIndex]:
                return False
        else:
            return False
    for card, count in zip(newDeckList.sideboard.cards, newDeckList.sideboard.counts):
        if getattr(card, "Card Name") in existingDeckList.sideboard.cards:
            cardIndex = existingDeckList.sideboard.cards.index(getattr(card, "Card Name"))
            if count != existingDeckList.sideboard.counts[cardIndex]:
                return False
        else:
            return False
    return True

def getExpansion(date):
    date = datetime.datetime.strptime(date, r"%Y-%m-%d")
    expansions = {
        "Kaldheim": datetime.datetime(2021, 1, 28),
        "Zendikar Rising": datetime.datetime(2020, 9, 17),
        "Core Set 2021": datetime.datetime(2020, 6, 25),
        "Ikoria_ Lair of Behemoths": datetime.datetime(2020, 4, 16),
        "Theros Beyond Death": datetime.datetime(2020, 1, 16),
        "Throne of Eldraine": datetime.datetime(2020, 9, 27)
    }
    for expansion in expansions:
        if expansions[expansion] < date:
            return expansion

date, deckLists, event = getMagicGGDeckLists("https://magic.gg/news/magic-world-championship-xxvi-metagame-breakdown")
# date, event, deckLists = getMagicGGDeckLists("https://magic.gg/news/2020-mythic-invitational-decklists")

# for username in deckLists:
#     deckLists[username].setColorArchetype()
#     print("Color Archetype: " + deckLists[username].colorArchetype)

# dates, links, events = getMTGOEvents(5)

# for date, link, event in zip(dates, links, events):

#     print("Date: " + date)
#     print("Link: " + link)
#     print("Event: " + event) 

#     path = createFolders("P:\\MTG", [getExpansion(date), date, event])
#     soup = BeautifulSoup(urlopen(link).read(), features = "html.parser")
#     usernames = [username.text.split(r"(")[0].strip() for username in soup.findAll("span", class_ = "deck-meta")]

#     deckLists = getMTGODeckLists(soup.findAll("div", class_ = "deck-list-text"), usernames)

#     for username in usernames:
#         # colorArchetype = getColorArchetype(deckLists[username])
#         colorArchetype = deckLists[username].getColorArchetype()
#         print("\tUsername: " + username)
#         print("\t\tColor Archetype: " + colorArchetype)

#         deckPath = os.path.join(path, colorArchetype + " - " + username)

#         if os.path.exists(path + colorArchetype + " - " + username + ".txt"):
#             existingDeckList = convertFileToDeckList(path + colorArchetype + " - " + username + ".txt")
#             if not(compareDecks(deckLists[username], existingDeckList)):
#                 os.mkdir(deckPath)
#                 os.rename(path + colorArchetype + " - " + username + ".txt", os.path.join(deckPath, "List 1.txt"))
#                 createDeckListFile(deckLists[username], os.path.join(deckPath, "List 2.txt"))
#         elif os.path.isdir(deckPath):
#             existingDeckLists = os.listdir(deckPath)
#             create = True
#             while create and existingDeckLists:
#                 existingDeckList = convertFileToDeckList(os.path.join(deckPath, existingDeckLists.pop()))
#                 create = not(compareDecks(deckLists[username], existingDeckList))
#             if create:
#                 createDeckListFile(deckLists[username], os.path.join(deckPath, "List " + str(len(os.listdir(deckPath)) + 1) + ".txt"))
#         else:
#             createDeckListFile(deckLists[username], os.path.join(path, colorArchetype + " - " + username + ".txt"))
