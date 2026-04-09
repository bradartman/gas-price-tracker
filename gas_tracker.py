"""
Gas Price Tracker - 60014 & 60012 ZIP codes
Scrapes GasBuddy with Selenium for free, no API key required.
Saves to CSV, optionally to Google Sheets, and emails a daily HTML report.
"""

import csv
import json
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# ── CONFIG ───────────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent / "config.json"
CSV_FILE    = Path(__file__).parent / "gas_prices.csv"

def load_config():
    if not CONFIG_FILE.exists():
        print(f"ERROR: config.json not found at {CONFIG_FILE}")
        print("Please copy config.example.json to config.json and fill in your details.")
        raise SystemExit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)

# ── SELENIUM DRIVER ───────────────────────────────────────────────────────────
def _make_driver() -> webdriver.Chrome:
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
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

# ── SCRAPE GASBUDDY ───────────────────────────────────────────────────────────
def fetch_stations_for_zip(zip_code: str, driver: webdriver.Chrome) -> list[dict]:
    url = f"https://www.gasbuddy.com/home?search={zip_code}&fuel=1&method=all&maxAge=0"
    print(f"    Loading {url}")
    driver.get(url)

    # Wait for station cards to appear
    wait = WebDriverWait(driver, 20)
    try:
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[class*='StationDisplay']")
        ))
    except Exception:
        time.sleep(4)  # fallback wait if selector doesn't match

    time.sleep(2)  # let prices finish rendering

    stations = []

    # GasBuddy renders station cards — try a few selector strategies
    cards = driver.find_elements(By.CSS_SELECTOR, "[class*='StationDisplay-module__card']")
    if not cards:
        cards = driver.find_elements(By.CSS_SELECTOR, "[class*='StationDisplay']")
    if not cards:
        # Last resort: any list item that contains a price
        cards = driver.find_elements(By.CSS_SELECTOR, "li[class*='station'], div[class*='station']")

    print(f"    Found {len(cards)} station cards")

    for card in cards:
        try:
            # Try CSS selectors first, fall back to parsing raw card text
            name = _extract_text(card, [
                "[class*='header__']",
                "[class*='StationDisplay-module__name']",
                "[class*='name__']",
                "h3", "h4", "a[class*='name']",
            ])

            address = _extract_text(card, [
                "[class*='Address']",
                "[class*='address']",
                "[class*='locality']",
                "[class*='location']",
                "address",
            ])

            # Fall back to parsing the card's raw text lines
            if not name or not address:
                name_fb, address_fb = _parse_card_text(card.text)
                if not name:
                    name = name_fb
                if not address:
                    address = address_fb

            price_87 = _extract_price(card)

            stations.append({
                "zip":      zip_code,
                "station":  (name or "Unknown").strip(),
                "address":  (address or "Unknown").strip(),
                "price_87": price_87,
            })
        except Exception as e:
            print(f"    [warn] Could not parse card: {e}")
            continue

    return stations


def _extract_text(element, selectors: list[str]) -> str:
    """Try each CSS selector in order, return first non-empty text found."""
    for sel in selectors:
        try:
            el = element.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def _parse_card_text(text: str) -> tuple[str, str]:
    """
    Parse station name and address from raw card text.
    GasBuddy cards typically have the station name on the first line
    and address somewhere in the middle lines.
    """
    import re
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    name = ""
    address = ""

    # First non-price, non-number line is usually the station name
    for line in lines:
        if not re.match(r'^[\d\.\$]', line) and len(line) > 2:
            name = line
            break

    # Look for a line that looks like a street address
    addr_pattern = re.compile(
        r'\d+\s+\w+.*(st|ave|rd|dr|blvd|ln|way|hwy|route|pkwy|ct|pl|cir)',
        re.IGNORECASE
    )
    for line in lines:
        if addr_pattern.search(line) and line != name:
            address = line
            break

    # If no street address found, use second non-price line as address
    if not address:
        count = 0
        for line in lines:
            if not re.match(r'^[\d\.\$]', line) and len(line) > 2:
                count += 1
                if count == 2:
                    address = line
                    break

    return name, address


def _extract_price(card) -> str:
    """Extract the 87-octane price from a station card."""
    # GasBuddy shows prices as e.g. "3.459" or "$3.45" or split across spans
    price_selectors = [
        "[class*='price__'] [class*='integer']",
        "[class*='Price']",
        "[class*='price']",
        "[data-testid*='price']",
        "span[class*='cash']",
    ]
    for sel in price_selectors:
        try:
            els = card.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                text = el.text.strip().replace("$", "").replace(",", "")
                # Validate it looks like a price (e.g. 3.459 or 3.45)
                try:
                    val = float(text)
                    if 1.0 < val < 10.0:
                        return f"{val:.3f}"
                except ValueError:
                    continue
        except Exception:
            continue

    # Try raw text scan of the card for a price pattern
    import re
    text = card.text
    match = re.search(r'\$?\s*([2-9]\.\d{2,3})', text)
    if match:
        try:
            val = float(match.group(1))
            if 1.0 < val < 10.0:
                return f"{val:.3f}"
        except ValueError:
            pass

    return "N/A"


# ── FETCH ALL ZIPS ────────────────────────────────────────────────────────────
def fetch_all_stations(zip_codes: list[str], api_key: str = "") -> list[dict]:
    """Scrape GasBuddy for all ZIP codes. api_key param ignored (kept for compatibility)."""
    driver = _make_driver()
    all_stations = []
    try:
        for z in zip_codes:
            print(f"  Scraping ZIP {z}...")
            stations = fetch_stations_for_zip(z, driver)
            print(f"    → Collected {len(stations)} stations")
            all_stations.extend(stations)
    finally:
        driver.quit()
    return all_stations

# ── CSV STORAGE ───────────────────────────────────────────────────────────────
FIELDNAMES = ["date", "zip", "station", "address", "price_87"]

def save_to_csv(stations: list[dict]):
    today        = datetime.now().strftime("%Y-%m-%d")
    write_header = not CSV_FILE.exists()

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        for s in stations:
            writer.writerow({
                "date":     today,
                "zip":      s["zip"],
                "station":  s["station"],
                "address":  s["address"],
                "price_87": s["price_87"],
            })
    print(f"  Saved {len(stations)} rows to {CSV_FILE}")

# ── OPTIONAL: GOOGLE SHEETS ───────────────────────────────────────────────────
def save_to_google_sheets(stations: list[dict], config: dict):
    sheet_cfg = config.get("google_sheets", {})
    if not sheet_cfg.get("enabled"):
        return
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            sheet_cfg["service_account_json"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)
        today   = datetime.now().strftime("%Y-%m-%d")
        rows    = [
            [today, s["zip"], s["station"], s["address"], s["price_87"]]
            for s in stations
        ]
        service.spreadsheets().values().append(
            spreadsheetId=sheet_cfg["spreadsheet_id"],
            range="Sheet1!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
        print(f"  Appended {len(rows)} rows to Google Sheet.")
    except ImportError:
        print("  [skip] Google Sheets libs not installed. Run: pip install google-auth google-api-python-client")
    except Exception as e:
        print(f"  [warn] Google Sheets upload failed: {e}")

# ── EMAIL REPORT ──────────────────────────────────────────────────────────────
def build_email_html(stations: list[dict], date_str: str) -> str:
    by_zip = {}
    for s in stations:
        by_zip.setdefault(s["zip"], []).append(s)

    sections = ""
    for zip_code, rows in by_zip.items():
        def price_key(r):
            try:    return float(r["price_87"])
            except: return 9999
        rows.sort(key=price_key)

        rows_html = "".join(f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0">{r['station']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;color:#555;font-size:13px">{r['address']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-weight:700;color:#e05c00;text-align:right">
            {"$" + r['price_87'] if r['price_87'] != "N/A" else "N/A"}
          </td>
        </tr>
        """ for r in rows)

        priced = [r for r in rows if r["price_87"] != "N/A"]
        best   = priced[0] if priced else None
        badge  = ""
        if best:
            badge = f"""<div style="margin-bottom:12px;padding:10px 14px;background:#fff8f0;border-left:4px solid #e05c00;border-radius:4px;font-size:13px">
              🏆 <strong>Best price:</strong> {best['station']} — <strong>${best['price_87']}</strong>
            </div>"""

        sections += f"""
        <h2 style="margin:28px 0 8px;font-size:18px;color:#222">ZIP Code {zip_code}</h2>
        {badge}
        <table width="100%" cellpadding="0" cellspacing="0"
          style="border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
          <thead>
            <tr style="background:#f7f7f7">
              <th style="padding:10px 12px;text-align:left;font-size:12px;color:#888;font-weight:600;letter-spacing:.5px">STATION</th>
              <th style="padding:10px 12px;text-align:left;font-size:12px;color:#888;font-weight:600;letter-spacing:.5px">ADDRESS</th>
              <th style="padding:10px 12px;text-align:right;font-size:12px;color:#888;font-weight:600;letter-spacing:.5px">87 OCT</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        """

    note = """<p style="margin-top:28px;font-size:12px;color:#aaa">
      Prices sourced via GasBuddy. CSV log saved locally for historical tracking.
    </p>"""

    return f"""<!DOCTYPE html><html>
    <body style="margin:0;padding:0;background:#f4f4f4;font-family:'Helvetica Neue',Arial,sans-serif">
    <div style="max-width:640px;margin:32px auto">
      <div style="background:#e05c00;padding:24px 28px;border-radius:12px 12px 0 0">
        <h1 style="margin:0;color:#fff;font-size:22px">⛽ Daily Gas Price Report</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:14px">{date_str} · ZIP codes 60014 &amp; 60012</p>
      </div>
      <div style="padding:24px 28px;background:#fff;border-radius:0 0 12px 12px">
        {sections}
        {note}
      </div>
    </div>
    </body></html>"""


def send_email(stations: list[dict], config: dict):
    email_cfg = config["email"]
    date_str  = datetime.now().strftime("%A, %B %d, %Y")
    html_body = build_email_html(stations, date_str)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⛽ Gas Prices Report — {datetime.now().strftime('%b %d, %Y')}"
    msg["From"]    = email_cfg["sender"]
    msg["To"]      = email_cfg["recipient"]
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_cfg["sender"], email_cfg["app_password"])
            server.sendmail(email_cfg["sender"], email_cfg["recipient"], msg.as_string())
        print(f"  Email sent to {email_cfg['recipient']}")
    except Exception as e:
        print(f"  [ERROR] Email failed: {e}")
        print("  Double-check your Gmail App Password in config.json")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"Gas Price Tracker — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    config    = load_config()
    zip_codes = config.get("zip_codes", ["60014", "60012"])

    print("\n[1/3] Scraping gas prices from GasBuddy...")
    stations = fetch_all_stations(zip_codes)

    if not stations:
        print("  No stations found. Check your internet connection.")
        return

    print(f"\n[2/3] Saving data ({len(stations)} stations)...")
    save_to_csv(stations)
    save_to_google_sheets(stations, config)

    print("\n[3/3] Sending email report...")
    send_email(stations, config)

    print("\n✅ Done!\n")


if __name__ == "__main__":
    main()
