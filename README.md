# ⛽ Gas Price Tracker

Fetches 87-octane gas prices for ZIP codes **60014** and **60012** by scraping
**GasBuddy** with Selenium — free, no API key required. Saves to a local CSV
and displays results in a simple web app. Optionally emails a daily HTML report
and logs to Google Sheets.

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Flask web app — click a button to fetch prices & export CSV |
| `gas_tracker.py` | Core logic — API calls, CSV saving, email, Google Sheets |
| `config.example.json` | Template — copy to `config.json` and fill in |
| `requirements.txt` | Python dependencies |
| `gas_prices.csv` | Generated automatically — your price history |

---

## 1. Install Python

Download Python 3.10+ from https://python.org/downloads  
(On Windows, check **"Add Python to PATH"** during install.)

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Configure

```bash
cp config.example.json config.json
```

Open `config.json` and fill in your details:

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

### Getting a Gmail App Password (for email reports)

1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** (required)
3. Go to https://myaccount.google.com/apppasswords
4. Click **Create** → name it "Gas Tracker"
5. Copy the 16-character password into `config.json`

---

## 4. Run the Web App

```bash
python app.py
```

Open **http://localhost:5000** in your browser. You'll see:

- **Fetch Latest Prices** — calls the Google Maps API and displays results grouped by ZIP, sorted cheapest first
- **Export CSV** — downloads your full price history as a CSV file

---

## 5. Run as a Script (no web UI)

```bash
python gas_tracker.py
```

Fetches prices, saves to CSV, and sends an email report.

---

## 6. Schedule at 7 AM Daily (script mode)

### Mac / Linux (cron)

```bash
crontab -e
```

Add this line — update the paths to match your folder:

```
0 7 * * * /usr/bin/python3 /path/to/gas_tracker/gas_tracker.py >> /path/to/gas_tracker/cron.log 2>&1
```

### Windows (Task Scheduler)

1. Open **Task Scheduler** → **Create Basic Task**
2. Trigger: **Daily** at **7:00 AM**
3. Action: **Start a program**
   - Program: `python`
   - Arguments: `gas_tracker.py`
   - Start in: `C:\path\to\this\folder`
4. In task **Properties**, check **"Run whether user is logged on or not"**

---

## 7. CSV Format

Prices are appended to `gas_prices.csv` on each run:

```
date,zip,station,address,price_87
2026-04-09,60014,Sam's Club,"5670 Northwest Hwy, Crystal Lake, IL",4.15
2026-04-09,60014,Marathon,"770 Virginia Rd, Crystal Lake, IL",4.24
2026-04-09,60012,BP,"123 Main St, Crystal Lake, IL",4.19
```

---

## 8. Optional: Google Sheets Integration

1. Go to https://console.cloud.google.com → enable **Google Sheets API**
2. **IAM & Admin → Service Accounts** → Create account → Download JSON key → save as `service_account.json`
3. Share your Google Sheet with the service account email (Editor access)
4. Copy the Sheet ID from the URL (the string between `/d/` and `/edit`)
5. In `config.json`:
   ```json
   "google_sheets": {
     "enabled": true,
     "spreadsheet_id": "YOUR_SHEET_ID_HERE",
     "service_account_json": "service_account.json"
   }
   ```
6. Install extra libraries:
   ```bash
   pip install google-auth google-auth-httplib2 google-api-python-client
   ```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No stations found | GasBuddy may have updated their layout — check your internet connection |
| Prices show N/A | Station price not visible on GasBuddy for that ZIP |
| Email not sending | Double-check Gmail App Password; make sure 2-Step Verification is on |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |
