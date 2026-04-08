"""
Gas Price Tracker - 60014 & 60012 ZIP codes
Fetches gas prices, saves to CSV, and emails a daily report.
Run daily at 7am via Task Scheduler (Windows) or cron (Mac/Linux).
"""

import csv
import os
import smtplib
import json
import time
import random
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── CONFIG ──────────────────────────────────────────────────────────────────
# Edit config.json instead of touching this file.
CONFIG_FILE = Path(__file__).parent / "config.json"
CSV_FILE    = Path(__file__).parent / "gas_prices.csv"

# ── LOAD CONFIG ──────────────────────────────────────────────────────────────
def load_config():
    if not CONFIG_FILE.exists():
        print(f"ERROR: config.json not found at {CONFIG_FILE}")
        print("Please copy config.example.json to config.json and fill in your details.")
        raise SystemExit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)

# ── GAS PRICE FETCHING ───────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_gasbuddy(zip_code: str) -> list[dict]:
    """Scrape GasBuddy for stations in a ZIP code."""
    url = f"https://www.gasbuddy.com/gas-prices/{zip_code}"
    stations = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # GasBuddy station cards
        cards = soup.select("div[class*='StationDisplay']")
        if not cards:
            # Fallback: try the list items
            cards = soup.select("div.styles__StationListItem-sc")

        for card in cards[:15]:  # cap at 15 per ZIP
            try:
                name_el  = card.select_one("[class*='StationDisplayName'], h3, [class*='displayName']")
                addr_el  = card.select_one("[class*='StationAddress'], [class*='address']")
                price_el = card.select_one("[class*='Price__StyledPrice'], [class*='price']")

                name  = name_el.get_text(strip=True)  if name_el  else "Unknown"
                addr  = addr_el.get_text(strip=True)  if addr_el  else "Unknown"
                price = price_el.get_text(strip=True) if price_el else "N/A"

                # Clean price — keep digits and decimal only
                price_clean = "".join(c for c in price if c.isdigit() or c == ".")
                if price_clean and float(price_clean) > 0:
                    stations.append({
                        "zip":     zip_code,
                        "station": name,
                        "address": addr,
                        "price_87": price_clean,
                    })
            except Exception:
                continue

        # If scraping yielded nothing, fall back to the GasBuddy API
        if not stations:
            stations = fetch_gasbuddy_api(zip_code)

    except Exception as e:
        print(f"  [warn] GasBuddy scrape failed for {zip_code}: {e}")
        stations = fetch_gasbuddy_api(zip_code)

    return stations


def fetch_gasbuddy_api(zip_code: str) -> list[dict]:
    """
    Unofficial GasBuddy GraphQL endpoint.
    Falls back gracefully to empty list if it breaks.
    """
    url = "https://www.gasbuddy.com/graphql"
    query = """
    query LocationBySearchTerm($search: String) {
      locationBySearchTerm(search: $search) {
        stations {
          results {
            name
            address { line1 city state }
            prices { credit { nickname postedTime } fuelProduct }
          }
        }
      }
    }
    """
    stations = []
    try:
        resp = requests.post(
            url,
            json={"query": query, "variables": {"search": zip_code}},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        data = resp.json()
        results = (
            data.get("data", {})
                .get("locationBySearchTerm", {})
                .get("stations", {})
                .get("results", [])
        )
        for r in results[:15]:
            addr_obj = r.get("address", {})
            addr = f"{addr_obj.get('line1','')}, {addr_obj.get('city','')}, {addr_obj.get('state','')}"
            price = "N/A"
            for p in r.get("prices", []):
                if "Regular" in p.get("fuelProduct", "") or "87" in p.get("fuelProduct", ""):
                    price = str(p.get("credit", {}).get("postedTime", "N/A"))
                    break
            stations.append({
                "zip":     zip_code,
                "station": r.get("name", "Unknown"),
                "address": addr,
                "price_87": price,
            })
    except Exception as e:
        print(f"  [warn] GasBuddy API also failed for {zip_code}: {e}")
    return stations


def fetch_all_stations(zip_codes: list[str]) -> list[dict]:
    all_stations = []
    for z in zip_codes:
        print(f"  Fetching prices for ZIP {z}...")
        results = fetch_gasbuddy(z)
        print(f"    → Found {len(results)} stations")
        all_stations.extend(results)
        time.sleep(random.uniform(1.5, 3.0))  # be polite
    return all_stations


# ── CSV STORAGE ───────────────────────────────────────────────────────────────
FIELDNAMES = ["date", "zip", "station", "address", "price_87"]

def save_to_csv(stations: list[dict]):
    today = datetime.now().strftime("%Y-%m-%d")
    write_header = not CSV_FILE.exists()

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        for s in stations:
            writer.writerow({
                "date":    today,
                "zip":     s["zip"],
                "station": s["station"],
                "address": s["address"],
                "price_87": s["price_87"],
            })
    print(f"  Saved {len(stations)} rows to {CSV_FILE}")


# ── OPTIONAL: GOOGLE SHEETS ───────────────────────────────────────────────────
def save_to_google_sheets(stations: list[dict], config: dict):
    """
    Append rows to a Google Sheet via the Sheets API.
    Requires: pip install google-auth google-auth-httplib2 google-api-python-client
    And a service account JSON key — see README for setup steps.
    """
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
        sheet   = service.spreadsheets()

        today = datetime.now().strftime("%Y-%m-%d")
        rows  = [
            [today, s["zip"], s["station"], s["address"], s["price_87"]]
            for s in stations
        ]
        sheet.values().append(
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
        # Sort cheapest first
        def price_key(r):
            try:    return float(r["price_87"])
            except: return 9999
        rows.sort(key=price_key)

        rows_html = "".join(f"""
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0">{r['station']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;color:#555;font-size:13px">{r['address']}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;font-weight:700;color:#e05c00;text-align:right">${r['price_87']}</td>
        </tr>
        """ for r in rows)

        best = rows[0] if rows else None
        badge = ""
        if best:
            badge = f"""<div style="margin-bottom:12px;padding:10px 14px;background:#fff8f0;border-left:4px solid #e05c00;border-radius:4px;font-size:13px">
              🏆 <strong>Best price:</strong> {best['station']} — <strong>${best['price_87']}</strong>
            </div>"""

        sections += f"""
        <h2 style="margin:28px 0 8px;font-size:18px;color:#222">ZIP Code {zip_code}</h2>
        {badge}
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
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

    return f"""
    <!DOCTYPE html><html><body style="margin:0;padding:0;background:#f4f4f4;font-family:'Helvetica Neue',Arial,sans-serif">
    <div style="max-width:640px;margin:32px auto;background:#f4f4f4">
      <div style="background:#e05c00;padding:24px 28px;border-radius:12px 12px 0 0">
        <h1 style="margin:0;color:#fff;font-size:22px">⛽ Daily Gas Price Report</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:14px">{date_str} · ZIP codes 60014 &amp; 60012</p>
      </div>
      <div style="padding:24px 28px;background:#fff;border-radius:0 0 12px 12px">
        {sections}
        <p style="margin-top:28px;font-size:12px;color:#aaa">Prices sourced from GasBuddy. Data may be user-reported and may vary slightly. CSV log saved locally.</p>
      </div>
    </div>
    </body></html>
    """


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

    print("\n[1/3] Fetching gas prices...")
    stations = fetch_all_stations(zip_codes)

    if not stations:
        print("  No stations found. Check your internet connection or try again later.")
        return

    print(f"\n[2/3] Saving data ({len(stations)} stations)...")
    save_to_csv(stations)
    save_to_google_sheets(stations, config)

    print("\n[3/3] Sending email report...")
    send_email(stations, config)

    print("\n✅ Done!\n")


if __name__ == "__main__":
    main()
