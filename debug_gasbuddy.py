"""
Debug script - captures GasBuddy HTML so we can find the right CSS selectors.
Run: python debug_gasbuddy.py
Outputs: debug_card.html (first card's HTML) and debug_page.html (full page)
"""

import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

opts = Options()
opts.add_argument("--headless")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-dev-shm-usage")
opts.add_argument("--disable-gpu")
opts.add_argument("--window-size=1920,1080")
opts.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=opts)

try:
    url = "https://www.gasbuddy.com/home?search=60014&fuel=1&method=all&maxAge=0"
    print(f"Loading {url}...")
    driver.get(url)

    wait = WebDriverWait(driver, 20)
    try:
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[class*='StationDisplay']")
        ))
    except Exception:
        time.sleep(5)

    time.sleep(3)

    # Save full page source
    Path("debug_page.html").write_text(driver.page_source, encoding="utf-8")
    print("Saved full page to debug_page.html")

    # Try to find cards and dump first one
    for selector in [
        "[class*='StationDisplay-module__card']",
        "[class*='StationDisplay']",
        "[class*='station']",
    ]:
        cards = driver.find_elements(By.CSS_SELECTOR, selector)
        if cards:
            print(f"\nFound {len(cards)} cards with selector: {selector}")
            Path("debug_card.html").write_text(cards[0].get_attribute("outerHTML"), encoding="utf-8")
            print("Saved first card HTML to debug_card.html")
            print("\n--- First card text ---")
            print(cards[0].text)
            break
    else:
        print("No cards found with any selector")

finally:
    driver.quit()
