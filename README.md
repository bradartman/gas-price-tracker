# ⛽ Gas Price Tracker — Setup Guide

Fetches daily 87-octane gas prices for ZIP codes **60014** and **60012** by scraping
**GasBuddy** with Selenium, saves them to a local CSV, and emails you a formatted
report at 7 AM every day. No API keys or accounts required.

---

## Files

| File | Purpose |
|------|---------|
| `gas_tracker.py` | Main script — scrape, save, email |
| `debug_gasbuddy.py` | Debug tool — run if prices stop working |
| `config.example.json` | Template — copy to `config.json` and fill in |
| `requirements.txt` | Python dependencies |
| `gas_prices.csv` | Generated automatically — your price history |

---

## 1. Install Python

Download Python 3.10+ from https://python.org/downloads  
(On Windows, check **"Add Python to PATH"** during install.)

---

## 2. Install Google Chrome

Selenium controls a real Chrome browser in the background. If Chrome isn't already
installed, download it from https://www.google.com/chrome

The script uses `webdriver-manager` to automatically download the correct
ChromeDriver version — you don't need to install it manually.

---

## 3. Install Python Dependencies

Open Terminal (Mac/Linux) or Command Prompt (Windows) in this folder:

```bash
pip install -r requirements.txt
```

---

## 4. Configure

```bash
cp config.example.json config.json
```

Open `config.json` and fill in your email details:

```json
{
  "zip_codes": ["60014", "60012"],
  "email": {
    "sender": "your.gmail@gmail.com",
    "recipient": "your.gmail@gmail.com",
    "app_password": "xxxx xxxx xxxx xxxx"
  },
  "google_sheets": {
    "enabled": false,
    "spreadsheet_id": "",
    "service_account_json": "service_account.json"
  }
}
```

| Field | What to put |
|-------|-------------|
| `email.sender` | Your Gmail address |
| `email.recipient` | Where to send the report (can be the same address) |
| `email.app_password` | A Gmail App Password — **not** your regular password (see below) |

### Getting a Gmail App Password

1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** (required)
3. Go to https://myaccount.google.com/apppasswords
4. Click **Create** → name it "Gas Tracker"
5. Copy the 16-character password into `config.json`

---

## 5. Test It

```bash
python gas_tracker.py
```

You should see output like:

```
==================================================
Gas Price Tracker — 2026-04-08 07:00:01
==================================================

[1/3] Scraping gas prices from GasBuddy...
  Scraping ZIP 60014...
    Loading https://www.gasbuddy.com/home?search=60014&fuel=1&method=all&maxAge=0
    Found 12 station cards
    → Collected 12 stations
  ...

[2/3] Saving data (24 stations)...
  Saved 24 rows to gas_prices.csv

[3/3] Sending email report...
  Email sent to your.gmail@gmail.com

✅ Done!
```

An email will arrive in your inbox with stations sorted cheapest first per ZIP.

---

## 6. Schedule at 7 AM Daily

### Mac / Linux (cron)

```bash
crontab -e
```

Add this line — update the paths to match your folder:

```
0 7 * * * /usr/bin/python3 /path/to/gas_tracker/gas_tracker.py >> /path/to/gas_tracker/cron.log 2>&1
```

Save and exit. The script will now run automatically every morning at 7 AM.

### Windows (Task Scheduler)

1. Open **Task Scheduler** → **Create Basic Task**
2. Name: `Gas Price Tracker`
3. Trigger: **Daily** at **7:00 AM**
4. Action: **Start a program**
   - Program: `python` (or full path like `C:\Python312\python.exe`)
   - Arguments: `gas_tracker.py`
   - Start in: `C:\path\to\this\folder`
5. Finish → right-click the task → **Run** to test
6. In task **Properties**, check **"Run whether user is logged on or not"** so it runs even when you're not at your computer

---

## 7. CSV Database

Prices are automatically appended to `gas_prices.csv` each run:

```
date,zip,station,address,price_87
2026-04-08,60014,Sam's Club,"5670 Northwest Hwy, Crystal Lake, IL",4.15
2026-04-08,60014,Marathon,"770 Virginia Rd, Crystal Lake, IL",4.24
2026-04-08,60012,BP,"123 Main St, Crystal Lake, IL",4.19
```

Open this in Excel or Google Sheets anytime to view historical trends.

---

## 8. Optional: Google Sheets Integration

To also log prices to a Google Sheet automatically:

1. Go to https://console.cloud.google.com and create a project
2. Enable the **Google Sheets API**
3. Go to **IAM & Admin → Service Accounts** → Create a service account → Download the JSON key → save it as `service_account.json` in this folder
4. Open your Google Sheet → **Share** → paste the service account email → give it **Editor** access
5. Copy the Sheet ID from the URL (the long string between `/d/` and `/edit`)
6. In `config.json` set:
   ```json
   "google_sheets": {
     "enabled": true,
     "spreadsheet_id": "YOUR_SHEET_ID_HERE",
     "service_account_json": "service_account.json"
   }
   ```
7. Install the extra libraries:
   ```bash
   pip install google-auth google-auth-httplib2 google-api-python-client
   ```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No stations found / 0 collected | GasBuddy may have updated their HTML — run `debug_gasbuddy.py` and check the screenshot |
| Prices stopped working after an update | Run `python debug_gasbuddy.py`, check `debug_screenshot.png` and share output to get selectors updated |
| Email not sending | Double-check Gmail App Password in `config.json`; make sure 2-Step Verification is on |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |
| `ChromeDriver` version error | Run `pip install --upgrade webdriver-manager` |
| Windows: script doesn't run at 7am | In Task Scheduler Properties, check "Run whether user is logged on or not" |
| Mac: cron job not running | Check cron has Full Disk Access in System Settings → Privacy & Security |

### If GasBuddy Changes Their Layout

GasBuddy occasionally updates their CSS class names, which can break the scraper.
If prices suddenly stop being collected:

1. Run the debug script:
   ```bash
   python debug_gasbuddy.py
   ```
2. Open `debug_screenshot.png` to confirm the page loaded correctly
3. Check the terminal output for updated class names and update the selectors in `gas_tracker.py`
