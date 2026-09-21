# pylint: disable = no-member
import re
from urllib.request import urlopen

from bs4 import BeautifulSoup

from classes import Card, Face


def parseCardText(value):
    locations = value.findAll("img", alt = True)
    if locations:
        costs = parseManaCost(value)
        text = str(value)
        text.replace("\n", ".")
        for cost, location in zip(costs, locations):
            text = text.replace(str(location), "{" + cost + "}")
        htmlElements = re.findall(r"<.*?>", text)
        for element in htmlElements:
            text = text.replace(element, "")
    else:
        text = value.text
    text = text.replace("  ", " ")
    text = re.sub(r"(\w)([A-Z])|\.(?! )+(?!\))", r"\1. \2", text)
    text = re.sub(r"\s([?.!\"](?:\s|$))", r"\1", text)
    text = re.sub(r"(\))([A-Z])", r"\1 \2", text)
    text = re.sub(r"(−|\+)?(\d+):", r"{\1\2}:", text).strip()
    return text

def parseGeneral(value):
    return value.text.strip().replace("  ", " ").strip()

def parseManaCost(value):
    costs = value.findAll("img", alt = True)
    cardCost = []
    for cost in costs:
        costSplit = cost["alt"].split()
        if len(costSplit) > 1:
            currentCost = ""
            for cs in costSplit:
                if cs != "or":
                    if cs == "Blue":
                        currentCost += "U/"
                    elif cs == "Variable" or cs == "Cost":
                        currentCost += cs[0]
                    else:
                        currentCost += cs[0] + "/"
            cardCost.append(currentCost[:-1])
        elif cost["alt"] == "Blue":
            cardCost.append("U")
        else:
            cardCost.append(cost["alt"][0])
    return cardCost

def parsePT(value):
    return [v.strip() for v in value.text.split("/")]

def scrapeCard(card):
    if card.Link:
        soup = BeautifulSoup(urlopen(card.Link).read(), features = "html.parser")
        columns = soup.findAll("td", class_ = "rightCol")
        if columns:
            for column in soup.findAll("td", class_ = "rightCol"):
                attributes = column.findAll("div", class_ = "row")
                if attributes:
                    print("\t\tScraping " + getattr(card, "Card Name") + ".")
                    parseFunctions = {"Card Name": parseGeneral, "Card Text": parseCardText, "Converted Mana Cost": parseGeneral, "Mana Cost": parseManaCost, "P/T": parsePT, "Types": parseGeneral}
                    face = Face()
                    for attribute in attributes:
                        label = attribute.find("div", class_ = "label").text.strip().replace(":", "")
                        value = attribute.find("div", class_ = "value")
                        parseFunction = parseFunctions.get(label)
                        if parseFunction:
                            setattr(face, label, parseFunction(value))
                    card.Faces.append(face)
                else:
                    links = soup.findAll("span", class_ = "cardTitle")
                    if any([getattr(card, "Card Name") == link.text.strip().lower() for link in links]):
                        for link in links:
                            if getattr(card, "Card Name") == link.text.strip().lower():
                                card.Link = link.find("a")["href"].replace(r"..", "https://gatherer.wizards.com/Pages")
                                break
                    else:
                        for link in links:
                            if getattr(card, "Card Name") in link.text.lower():
                                card.Link = link.find("a")["href"].replace(r"..", "https://gatherer.wizards.com/Pages")
                                break
                    return scrapeCard(card)
        else:
            input("The card information for " + getattr(card, "Card Name") + " could not be found.")
        return card
    else:
        card.Link = "https://gatherer.wizards.com/Pages/Search/Default.aspx?name=+[" + "]+[".join(getattr(card, "Card Name").split()) + "]"
        return scrapeCard(card)
