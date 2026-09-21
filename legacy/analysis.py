# pylint: disable = no-member

# def calculateDeckListsStats(deckLists):
#     archetypes = {}
#     for player in deckLists:
#         deckLists[player].setColorArchetype()
#         if deckLists[player].archetype:
#             pass
#             # if deckLists[player].archetype in archetypes:
#             #     archetypes[deckLists[player].archetype].update({player: deckLists[player]})
#             # else:
#             #     archetypes[deckLists[player].archetype] = {player: deckLists[player]}
#         else:
#             pass


def calculateSimilarity(new, old):
    pass
    # maxComp = 0
    # minComp = 0
    # for attribute in new.__dict__:
    #     if attribute == "deck" or attribute == "sideboard":
    #         deck = getattr(old, "deck")
    #         sideboard = getattr(old, "sideboard")
    #         for card in getattr(new, attribute).cards:
    #             # print("\t" + self.cards[card]["count"] + " " + card)
    #             countNew = 0
    #             countOld = 0
    #             if card in deck:
