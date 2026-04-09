"""
Debug script - captures GasBuddy HTML and price data.
Run: python debug_gasbuddy.py
Outputs: debug_card.html, debug_page.html, debug_text.txt
"""

import re
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

    # Wait for station cards
    wait = WebDriverWait(driver, 20)
    try:
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[class*='StationDisplay']")
        ))
        print("Station elements found. Waiting 8s for prices to load...")
    except Exception:
        print("Station selector not found. Waiting 8s anyway...")

    time.sleep(8)

    # Save full page source
    Path("debug_page.html").write_text(driver.page_source, encoding="utf-8")
    print("Saved full page to debug_page.html")

    # Find cards — keep only ones with substantial text
    cards = []
    for selector in [
        "[class*='StationDisplay-module__card']",
        "[class*='StationDisplay']",
        "[class*='station']",
    ]:
        all_cards = driver.find_elements(By.CSS_SELECTOR, selector)
        cards = [c for c in all_cards if len(c.text.strip()) > 40]
        if cards:
            print(f"\nFound {len(cards)} real cards with selector: {selector}")
            break

    debug_lines = []

    if cards:
        # Save the first card's HTML
        Path("debug_card.html").write_text(cards[0].get_attribute("outerHTML"), encoding="utf-8")
        print("Saved first card HTML to debug_card.html")

        for i, card in enumerate(cards[:5]):
            debug_lines.append(f"\n{'='*60}")
            debug_lines.append(f"CARD {i+1}")
            debug_lines.append(f"{'='*60}")
            debug_lines.append(f".text:\n{card.text}")
            debug_lines.append(f"\ntextContent:\n{card.get_attribute('textContent')}")

            # Check each price-related selector
            debug_lines.append("\n--- Price selector results ---")
            for sel in [
                "[class*='PriceDisplay']",
                "[class*='price']",
                "[class*='Price']",
                "[class*='integer']",
                "[class*='decimal']",
                "[class*='superscript']",
                "[class*='cash']",
                "[data-testid*='price']",
                "span",
            ]:
                els = card.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    texts = [
                        f"'{e.get_attribute('textContent').strip()}' (class={e.get_attribute('class') or ''})"[:120]
                        for e in els[:3]
                    ]
                    debug_lines.append(f"  {sel}: {texts}")
    else:
        debug_lines.append("No cards found with any selector!")

    # Search whole page for price-like text
    debug_lines.append("\n\n--- All elements with price-like text on page ---")
    for el in driver.find_elements(By.CSS_SELECTOR, "span, div"):
        try:
            tc = (el.get_attribute("textContent") or "").strip()
            if re.search(r'\b[2-9]\.\d{2,3}\b', tc) and len(tc) < 30:
                cls = el.get_attribute("class") or ""
                debug_lines.append(f"  text='{tc}' class='{cls[:100]}'")
        except Exception:
            continue

    out = "\n".join(debug_lines)
    Path("debug_text.txt").write_text(out, encoding="utf-8")
    print("\nSaved debug info to debug_text.txt")
    print("\n--- debug_text.txt preview ---")
    print(out[:3000])

finally:
    driver.quit()
