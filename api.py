# pylint: disable = no-member
from enum import unique
# from analysis import calculateArchetypeStats, calculateDeckListsStats
import firebase_admin
from firebase_admin import firestore
from scrapeCards import scrapeCard
from classes import Card, DeckList

# Use a service account
cred = firebase_admin.credentials.Certificate(r'P:\\MTG\\Scraping\\database key.json')
firebase_admin.initialize_app(cred)

db = firestore.client()

def getAllCards():
    cards = []
    references = db.collection("Cards").stream()
    for reference in references:
        card = Card()
        card.fromDict(reference.to_dict())
        cards.append(card)
    return cards

# def getArchetypeDeckLists(deckLists):
#     colorArchetypes = getColorArchetypes(deckLists)
#     for colorArchetype in colorArchetypes:
#         references = db.collection(colorArchetype).stream()

    

def getColorArchetypes(deckLists):
    colorArchetypes = {}
    for player in deckLists:
        deckLists[player].setColorArchetype()
        if deckLists[player].colorArchetype not in colorArchetypes:
            colorArchetypes[deckLists[player].colorArchetype] = []
        colorArchetypes[deckLists[player].colorArchetype].append(player)
    return colorArchetypes

def removeDuplicateCards(deckLists):
    uniqueCards = {}
    for player in deckLists:
        for attribute in deckLists[player].__dict__:
            if attribute == "deck" or attribute == "sideboard":
                deck = getattr(deckLists[player], attribute)
                for card in deck.cards:
                    if card not in uniqueCards:
                        uniqueCards[card] = deck.cards[card]["card"]
    return uniqueCards

def removeDuplicateEvents(events):
    for event in events:
        eventReference = db.collection("Events").document(event.date + " - " + event.name)

def updateArchetypes(deckLists):
    colorArchetypes = getColorArchetypes(deckLists)
    for colorArchetype in colorArchetypes:
        references = db.collection(colorArchetype).stream()

def updateDeckLists(deckLists):
    uniqueCards = removeDuplicateCards(deckLists)
    for card in uniqueCards:
        cardReference = db.collection("Cards").document(card.replace("/", "\\"))
        cardReferenceInfo = cardReference.get()
        if cardReferenceInfo.exists and cardReferenceInfo.to_dict().get("Faces"):
            print("\tFound " + card + " in the database.")
            updatedCard = Card()
            updatedCard.fromDict(cardReferenceInfo.to_dict())
        else:
            print("\tCould not find " + card + " in the database.")
            updatedCard = scrapeCard(uniqueCards[card])
            cardReference.set(updatedCard.toDict())
        uniqueCards[card] = updatedCard
    updateCardPointers(deckLists, uniqueCards)
    updateArchetypes(deckLists)

def updateCardPointers(deckLists, uniqueCards):
    for player in deckLists:
        for attribute in deckLists[player].__dict__:
            if attribute == "deck" or attribute == "sideboard":
                deck = getattr(deckLists[player], attribute)
                for card in deck.cards:
                    deck.cards[card]["card"] = uniqueCards[card]

# def updateColorArchetypes(deckLists):
#     for player in deckLists:
#         deckLists[player].setColorArchetype()



specialCards = [Card({"Card Name": "lim-daul's vault", "Faces": [], "Link": "https://gatherer.wizards.com/pages/card/details.aspx?multiverseid=3223"})]
for card in specialCards:
    cardReference = db.collection("Cards").document(getattr(card, "Card Name").replace("/", "\\"))
    cardReferenceInfo = cardReference.get()
    if not(cardReferenceInfo.exists and cardReferenceInfo.to_dict().get("Faces")):
        db.collection("Cards").document(getattr(card, "Card Name")).set(scrapeCard(card).toDict())