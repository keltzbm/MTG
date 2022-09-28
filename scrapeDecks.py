# pylint: disable = no-member
import calendar
import collections
import os
import re
import sys
import time
from calendar import month_name
from datetime import date, datetime, timedelta
from urllib.request import urlopen

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

# from api import updateDeckLists
from classes import Card, Deck, DeckList, Event

# def getMTGODeck(deckInfo):
#     cards = []
#     counts = [card.text.strip() for card in deckInfo.findAll("span", class_ = "card-count")]
#     for card in deckInfo.findAll("span", class_ = "card-name"):
#         try:
#             link = card.find("a", class_ = "deck-list-link")["href"]
#         except:
#             link = "https://gatherer.wizards.com/Pages/Search/Default.aspx?name=+[" + "]+[".join(card.text.lower().split()) + "]"
#         cards.append(Card({"Card Name": card.text.lower(), "Faces": [], "Link": link}))
#     return Deck(cards, counts)

# def getMTGODeckLists(deckListsInfo, usernames):
#     deckLists = {}
#     for listInfo, username in zip(deckListsInfo, usernames):
#         deck = getMTGODeck(listInfo.find("div", class_ = "sorted-by-overview-container"))
#         try:
#             sideboard = getMTGODeck(listInfo.find("div", class_ = "sorted-by-sideboard-container"))
#         except:
#             sideboard = Deck([], [])
#         deckLists[username] = DeckList(deck, sideboard)
#     return updateDeckLists(deckLists)

# def getMTGOEventInfo(events):
#     dates = []
#     links = []
#     titles = []
#     for event in events:
#         date = "-".join([e.text for e in event.find_element_by_class_name("title").find_element_by_class_name("date").find_elements_by_tag_name("span")])
#         dates.append(datetime.strptime(date, r"%B-%d-%Y").strftime(r"%Y-%m-%d"))
#         links.append(event.find_element_by_tag_name("a").get_attribute("href"))
#         titles.append(event.find_element_by_class_name("title").find_element_by_tag_name("h3").text)
#     return dates, links, titles

# def getMTGOEvents(delta):
#     today = date.today()
#     yesterday = today - timedelta(days = delta)

#     options = FirefoxOptions()
#     options.add_argument("--headless")
#     options.add_argument("--disable-gpu")
#     driver = webdriver.Firefox(options = options, service_log_path = os.path.devnull)
#     driver.get("https://magic.wizards.com/en/content/deck-lists-magic-online-products-game-info")
#     driver.find_element_by_css_selector("html.js.csstransitions body.html.not-front.not-logged-in.no-sidebars.page-node.page-node-.page-node-118441.node-type-big-page.i18n-en.content-panels.role-anonymous-user.with-subnav.page-content-deck-lists-magic-online-products-game-info.section-content.eu-cookie-compliance-processed.loaded.windows div#sliding-popup.sliding-popup-bottom div.eu-cookie-compliance-banner.eu-cookie-compliance-banner-info.eu-cookie-compliance-banner--opt-in div.popup-content.info div#popup-buttons button.decline-button.eu-cookie-compliance-default-button").click()
#     try:
#         WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".closer"))).click()
#         driver.find_element_by_css_selector(".closer").click()
#     except:
#         pass
#     startDate = driver.find_element_by_id("datepickerFrom")
#     startDate.clear()
#     startDate.send_keys(yesterday.strftime(r"%m/%d/%Y"))
#     endDate = driver.find_element_by_id("datepickerTo")
#     endDate.clear()
#     endDate.send_keys(today.strftime(r"%m/%d/%Y"))

#     driver.find_element_by_id("custom-search-submit").click()

#     for _ in range(0, 5 * delta):
#         aElements = driver.find_elements_by_tag_name("a")
#         for name in aElements:
#             if(name.get_attribute("href") is not None and "javascript:void" in name.get_attribute("href")):
#                 try:
#                     name.click()
#                     WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, "href")))
#                 except:
#                     pass

#     aElements = driver.find_elements_by_class_name("article-item-extended")
#     dates, links, titles = getMTGOEventInfo(aElements)
#     driver.quit()
#     return dates, links, titles

def getMagicGGDeckList(archetype, companion, deckListInfo):
    mainboard = {}
    sideboard = {}
    flag = False
    for section in deckListInfo.find_elements_by_class_name("css-6DY_C"):
        if section.find_element_by_class_name("css-2mAuz").find_element_by_class_name("css-2UONU").text.strip().lower() == "sideboard":
            flag = True
        for card in section.find_elements_by_class_name("css-10Al7"):
            count = card.find_element_by_class_name("css-f_CVJ").text.lower()
            name = card.find_element_by_class_name("css-1E6ZG").text.lower()
            if count or name:
                if flag:
                    sideboard[name] = {"card": Card({"faces": [], "link": "", "name": name}), "count": count}
                else:
                    mainboard[name] = {"card": Card({"faces": [], "link": "", "name": name}), "count": count}
    return DeckList(Deck(mainboard), Deck(sideboard), archetype, companion)

# def getMagicGGDeckLists(link):
#     date = ""
#     event = ""

#     options = FirefoxOptions()
#     # options.add_argument("--headless")
#     # options.add_argument("--disable-gpu")
#     driver = webdriver.Firefox(options = options, service_log_path = os.path.devnull)
#     driver.get(link)

#     driver.find_element_by_css_selector("html body div#__nuxt div#__layout div.css-3Dp6r.css-1KY0s div#primary-area.css-1lm9y div.css-1jnJK div.css-12g7C div.css-1GflL div.css-39jOU button.css-3Q4Tf").click()

#     deckLists = {}

#     first = True

#     currentHeight = 0
#     previousHeight = -1
#     while previousHeight != currentHeight:

#         visible = driver.find_elements_by_class_name("css-326b5")
#         if first and visible:
#             eventInfo = visible[0].find_elements_by_class_name("css-3F_4f")
#             event = parseEvent(eventInfo[0].text)
#             date = parseDate(eventInfo[2].text)
#             print("Event: " + event)
#             print("Date: " + date)
#             driver.execute_script("window.scrollBy(0, -540)")
#             time.sleep(0.5)
#             driver.find_element_by_class_name("css-2ih-3").click()
#             first = False

#         while visible:
#             current = visible.pop(0)
#             username = parseUsername(current.find_element_by_class_name("css-3LH7E").text)
#             if username not in deckLists:
#                 archetype = parseArchetype(current.find_element_by_class_name("css-ausnN").text)
#                 dropDown = current.find_element_by_class_name("css-2ih-3")
#                 dropDown.click()
#                 print("User: " + username)
#                 print("\tArchetype: " + archetype)
#                 deckLists[username] = getMagicGGDeckList(archetype, current.find_elements_by_class_name("css-2iJc9"))
#                 for new in driver.find_elements_by_class_name("css-326b5"):
#                     newUsername = parseUsername(new.find_element_by_class_name("css-3LH7E").text)
#                     if newUsername not in deckLists:
#                         visible.append(new)

#         driver.execute_script("window.scrollBy(0, 1080)")
#         previousHeight = currentHeight
#         currentHeight = driver.execute_script("return window.pageYOffset")
#         time.sleep(0.5)
#     driver.quit()
#     return date, updateDeckLists(deckLists), event

def getMagicGGDeckLists(events):
    for event in events:
        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_experimental_option("detach", True)
        driver = webdriver.Chrome(executable_path = r"C:\bin\chromedriver.exe", options = options, service_log_path = os.path.devnull)
        driver.get(event.link)
        driver.set_window_size(1920, 1080)

        driver.find_element_by_css_selector("html body div#__nuxt div#__layout div.css-3Dp6r.css-1KY0s div#primary-area.css-1lm9y div.css-1jnJK div.css-12g7C div.css-1GflL div.css-39jOU button.css-3Q4Tf").click()

        for index, playerInfo in enumerate(driver.find_elements_by_class_name("css-dHEUf")):
            try:
                companion = playerInfo.find_element_by_class_name("css-3Cg3l").text.strip().lower()
            except:
                companion = ""
            try:
                archetype = playerInfo.find_element_by_class_name("css-rmbyb").text
                if companion.lower() in archetype.lower():
                    archetype = ""
                else:
                    archetype = parseArchetype(archetype)
            except:
                archetype = ""
            player = parsePlayer(index + 1, playerInfo.find_element_by_class_name("css-2KQeA").text)
            event.deckLists[player] = getMagicGGDeckList(archetype, companion, playerInfo.find_element_by_class_name("css-1uO75"))

        # time.sleep(0.5)
        driver.quit()
        # updateDeckLists(deckLists)
    return events

def getMagicGGEvents():
    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(executable_path = r"C:\bin\chromedriver.exe", options = options, service_log_path = os.path.devnull)
    driver.get("https://magic.gg/decklists")
    driver.set_window_size(1920, 1080)

    driver.find_element_by_css_selector("html body div#__nuxt div#__layout div.css-3Dp6r.css-1KY0s div#primary-area.css-1lm9y div.css-1jnJK div.css-12g7C div.css-1GflL div.css-39jOU button.css-3Q4Tf").click()

    currentHeight = 0
    previousHeight = -1
    while previousHeight != currentHeight:

        try:
            driver.find_element_by_class_name("css-2HqxF").find_element_by_class_name("css-3UJqZ").click()
        except:
            pass

        driver.execute_script("window.scrollBy(0, 1080)")
        time.sleep(1)
        previousHeight = currentHeight
        currentHeight = driver.execute_script("return window.pageYOffset")

    eventsInfo = driver.find_element_by_class_name("css-3OZOO").find_elements_by_class_name("css-ajYO7")
    events = []
    for eventInfo in eventsInfo:
        date = parseDate(eventInfo.find_element_by_class_name("css-3xJlN").text)
        name = parseName(eventInfo.find_element_by_class_name("css-19vXe").text)
        link = eventInfo.get_attribute("href")
        events.append(Event({"date": date, "deckLists": {}, "link": link, "name": name}))
    driver.quit()
    return getMagicGGDeckLists(events)

def parseArchetype(archetype):
    colors = ["Black", "Green", "Red", "Blue", "White"]
    colorArchtypes = {
            "": "Colorless",
            "B": "Mono-Black", "G": "Mono-Green", "R": "Mono-Red", "U": "Mono-Blue", "W": "Mono-White",
            "BG": "Golgari", "BR": "Rakdos", "BU": "Dimir", "BW": "Orzhov", "GR": "Gruul", "GU": "Simic", "GW": "Selesnya", "RU": "Izzet", "RW": "Boros", "UW": "Azorius",
            "BGR": "Jund", "BGU": "Sultai", "BGW": "Abzan", "BRU": "Grixis", "BRW": "Mardu", "BUW": "Esper", "GRU": "Temur", "GRW": "Naya", "GUW": "Bant", "RUW": "Jeskai",
            "BGRU": "Glint", "BGRW": "Dune", "BGUW": "Witch", "BRUW": "Yore", "GRUW": "Ink",
            "BGRUW": "Five-Color"
            }
    split = re.split(" |-", archetype.split("\n")[0])
    archetype = []
    for s in split:
        if s.capitalize() != "Mono" and s.capitalize() not in colors and s.capitalize() not in colorArchtypes and s.capitalize() not in list(colorArchtypes.values()) and s.capitalize() not in "Four-Color":
            archetype.append(s.capitalize())
    return " ".join(archetype)

def parseDate(date):
    return datetime.strptime(date, r"%B %d, %Y").strftime(r"%Y-%m-%d")

def parseName(event):
    event = event.lower().replace("decklists", "")
    event = event.split(":")[0]
    event = re.sub(r"20\d{2}", "", event)
    event = event.replace("mpl", "magic pro league")
    for month in month_name:
        event = event.replace(month.lower(), "")
    return event.title().strip()

def parsePlayer(index, player):
    if "platinum-mythic" in player.lower():
        return "Unknown Player " + str(index)
    else:
        return " ".join([string.capitalize() for string in reversed(player.split(", "))]).title()

events = getMagicGGEvents()
for event in events:
    print("Date: " + event.date)
    print("Name: " + event.name)
    print(event.date + " - " + event.name)
    # print("Event: " + event.name)
    # for player in event.deckLists:
    #     print("Player: " + player)
    #     event.deckLists[player].print()
