"""
Gas Price Tracker - 60014 & 60012 ZIP codes
Uses Google Maps Places API to find gas stations and current fuel prices.
Saves to CSV, optionally to Google Sheets, and emails a daily HTML report.
Run daily at 7am via Task Scheduler (Windows) or cron (Mac/Linux).
"""

import csv
import smtplib
import json
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

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

# ── ZIP → LAT/LNG ────────────────────────────────────────────────────────────
def zip_to_latlng(zip_code: str, api_key: str) -> tuple[float, float] | None:
    """Convert a ZIP code to lat/lng using the Geocoding API."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    resp = requests.get(url, params={"address": zip_code, "key": api_key}, timeout=10)
    data = resp.json()
    if data.get("status") == "OK":
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    print(f"  [warn] Could not geocode ZIP {zip_code}: {data.get('status')}")
    return None

# ── FETCH GAS STATIONS ────────────────────────────────────────────────────────
def fetch_stations_for_zip(zip_code: str, api_key: str, radius_meters: int = 5000) -> list[dict]:
    """
    Uses the Places API (Nearby Search) to find gas stations,
    then fetches fuel price details via Place Details.
    """
    coords = zip_to_latlng(zip_code, api_key)
    if not coords:
        return []
    lat, lng = coords

    # Step 1: Nearby Search for gas stations
    nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius":   radius_meters,
        "type":     "gas_station",
        "key":      api_key,
    }
    resp = requests.get(nearby_url, params=params, timeout=15)
    data = resp.json()

    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        print(f"  [warn] Places API error for ZIP {zip_code}: {data.get('status')} — {data.get('error_message','')}")
        return []

    results = data.get("results", [])
    print(f"    Found {len(results)} stations via Places API")

    stations = []
    for place in results[:15]:
        place_id = place.get("place_id")
        name     = place.get("name", "Unknown")
        vicinity = place.get("vicinity", "Unknown")

        # Step 2: Place Details to get fuel prices (if available)
        price_87 = fetch_fuel_price(place_id, api_key)

        stations.append({
            "zip":      zip_code,
            "station":  name,
            "address":  vicinity,
            "price_87": price_87,
            "place_id": place_id,
        })
        time.sleep(0.1)  # stay well within rate limits

    return stations


def fetch_fuel_price(place_id: str, api_key: str) -> str:
    """
    Fetch fuel prices from Place Details.
    Google includes fuel prices in the 'price_levels' / 'fuel_options' field
    for stations that report them. Falls back to 'N/A' gracefully.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields":   "name,fuel_options",
        "key":      api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        result = data.get("result", {})

        # fuel_options is available on the Places API (Advanced tier)
        fuel_options = result.get("fuel_options", {})
        fuel_prices  = fuel_options.get("fuelpricelist", [])

        for fp in fuel_prices:
            fuel_type = fp.get("type", "")
            # Match regular / unleaded / 87
            if any(t in fuel_type.upper() for t in ["REGULAR", "UNLEADED", "87"]):
                price_info = fp.get("price", {})
                units      = price_info.get("units", 0)        # whole dollars
                nanos      = price_info.get("nanos", 0)        # fractional
                price_val  = units + nanos / 1_000_000_000
                if price_val > 0:
                    return f"{price_val:.3f}"
    except Exception as e:
        print(f"    [warn] Price fetch failed for {place_id}: {e}")

    return "N/A"

# ── FETCH ALL ZIPS ────────────────────────────────────────────────────────────
def fetch_all_stations(zip_codes: list[str], api_key: str) -> list[dict]:
    all_stations = []
    for z in zip_codes:
        print(f"  Fetching stations for ZIP {z}...")
        stations = fetch_stations_for_zip(z, api_key)
        all_stations.extend(stations)
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
      Prices sourced via Google Maps Places API. Some stations may show N/A if they haven't
      reported prices to Google. CSV log saved locally for historical tracking.
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
    api_key   = config.get("google_maps_api_key", "")

    if not api_key:
        print("ERROR: google_maps_api_key is missing from config.json")
        raise SystemExit(1)

    print("\n[1/3] Fetching gas prices via Google Maps...")
    stations = fetch_all_stations(zip_codes, api_key)

    if not stations:
        print("  No stations found. Check your API key and internet connection.")
        return

    print(f"\n[2/3] Saving data ({len(stations)} stations)...")
    save_to_csv(stations)
    save_to_google_sheets(stations, config)

    print("\n[3/3] Sending email report...")
    send_email(stations, config)

    print("\n✅ Done!\n")


if __name__ == "__main__":
    main()
