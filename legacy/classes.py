# pylint: disable = no-member
import re

class Card:
    def __init__(self, values = None):
        if values:
            self.__dict__ = values

    def __eq__(self, other):
        return self.toDict() == other.toDict()

    def fromDict(self, values):
        self.__dict__ = values
        Faces = []
        for face in values["Faces"]:
            Faces.append(Face(face))
        setattr(self, "Faces", Faces)
        setattr(self, "Card Name", getattr(self, "Card Name").replace("\\", "/"))

    def toDict(self):
        dictionary = self.__dict__.copy()
        dictionary["Faces"] = []
        for face in self.Faces:
            dictionary["Faces"].append(face.__dict__)
        return dictionary

class Deck:
    def __init__(self, cards):
        self.cards = cards

    def getDeckColors(self):
        basics = {"Forest": "G", "Island": "U", "Mountain": "R", "Plains": "W", "Swamp": "B"}
        demand = []
        supply = []
        for card in self.cards:
            for face in self.cards[card].Faces:
                colors = []
                manaCost = []
                if "land" in face.Types.lower():
                    if getattr(face, "Card Name") in basics:
                        manaCost = [basics[getattr(face, "Card Name")]]
                    elif hasattr(face, "Card Text"):
                        manaCost = re.findall(r"{(\D*?)}", getattr(face, "Card Text"))
                    for mana in manaCost:
                        colors.extend(mana.split("/"))
                    supply.extend(colors)
                elif hasattr(face, "Mana Cost"):
                    manaCost = getattr(face, "Mana Cost")
                    for mana in manaCost:
                        colors.extend(mana.split("/"))
                    demand.extend(colors)
        return demand, supply

    def print(self):
        for card in self.cards:
            print("\t" + self.cards[card]["count"] + " " + card)

class DeckList:
    def __init__(self, mainboard, sideboard, archetype = None, companion = None):
        if archetype:
            self.archetype = archetype
        if companion:
            self.companion = companion
        self.mainboard = mainboard
        self.sideboard = sideboard

    def getDeckListColors(self):
        demand = []
        supply = []
        for attribute in self.__dict__:
            if attribute == "mainboard" or attribute == "sideboard":
                d, s = getattr(self, attribute).getDeckColors()
                demand.extend(d)
                supply.extend(s)
        colors = sorted(list(set(demand) & set(supply)))
        if "C" in colors:
            colors.remove("C")
        if "T" in colors:
            colors.remove("T")
        return colors

    def print(self):
        for attribute in self.__dict__:
            print(attribute.capitalize() + ": ", end = "")
            if attribute == "mainboard" or attribute == "sideboard":
                print("")
                getattr(self, attribute).print()
            else:
                print(getattr(self, attribute))

    def setColorArchetype(self):
        colorArchtypes = {
                "": "Colorless",
                "B": "Mono-Black", "G": "Mono-Green", "R": "Mono-Red", "U": "Mono-Blue", "W": "Mono-White",
                "BG": "Golgari", "BR": "Rakdos", "BU": "Dimir", "BW": "Orzhov", "GR": "Gruul", "GU": "Simic", "GW": "Selesnya", "RU": "Izzet", "RW": "Boros", "UW": "Azorius",
                "BGR": "Jund", "BGU": "Sultai", "BGW": "Abzan", "BRU": "Grixis", "BRW": "Mardu", "BUW": "Esper", "GRU": "Temur", "GRW": "Naya", "GUW": "Bant", "RUW": "Jeskai",
                "BGRU": "Glint", "BGRW": "Dune", "BGUW": "Witch", "BRUW": "Yore", "GRUW": "Ink",
                "BGRUW": "Five-Color"
                }
        self.colorArchetype = colorArchtypes["".join(self.getDeckListColors())]

class Event:
    def __init__(self, values = None):
        if values:
            self.__dict__ = values

class Face:
    def __init__(self, values = None):
        if values:
            self.__dict__ = values