# pylint: disable = no-member
from bs4 import BeautifulSoup
import calendar, collections, re, os, sys
from urllib.request import urlopen

from calendar import month_name

from datetime import datetime
from datetime import date
from datetime import timedelta
import time

from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.common.keys import Keys

link = "https://www.cardhoarder.com/cards/index/sort:sell-asc/viewtype:detailed?data%5Bsearch%5D=jace%2C+the+mind+sculptor&data%5Bis_foil%5D=0&data%5Bin_stock_only%5D=1"

options = FirefoxOptions()
# options.add_argument("--headless")
# options.add_argument("--disable-gpu")
driver = webdriver.Firefox(options = options, service_log_path = os.path.devnull)
driver.get(link)

# for t in driver.find_elements_by_tag_name("span"):
#     print(t.text)

for tr in driver.find_element_by_tag_name("tbody").find_elements_by_tag_name("tr"):
    print(tr.find_elements_by_tag_name("td")[-1].find_elements_by_tag_name("div")[-1].find_element_by_tag_name("span").text)


# driver.find_element_by_css_selector("html body div#__nuxt div#__layout div.css-3Dp6r.css-1KY0s div#primary-area.css-1lm9y div.css-1jnJK div.css-12g7C div.css-1GflL div.css-39jOU button.css-3Q4Tf").click()

# currentHeight = 0
# previousHeight = -1
# while previousHeight != currentHeight:

#     driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
#     time.sleep(0.5)
#     previousHeight = currentHeight
#     currentHeight = driver.execute_script("return document.body.scrollHeight")
    
#     try:
#         driver.find_element_by_class_name("css-2HqxF").find_element_by_class_name("css-3UJqZ").click()
#     except:
#         pass

# eventsInfo = driver.find_element_by_class_name("css-3OZOO").find_elements_by_class_name("css-ajYO7")
# for eventInfo in eventsInfo:
#     date = parseDate(eventInfo.find_element_by_class_name("css-3xJlN").text)
#     event = parseEvent(eventInfo.find_element_by_class_name("css-19vXe").text)
#     link = eventInfo.get_attribute("href")
#     print("Date: " + date)
#     print("Event: " + event)
#     deckLists = getMagicGGDeckLists(link)
# driver.quit()