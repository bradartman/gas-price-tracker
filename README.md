# ⛽ Gas Price Tracker — Setup Guide

Fetches daily 87-octane gas prices for ZIP codes **60014** and **60012** using Selenium**, saves them to a local CSV, and emails you a formatted
report at 7 AM every day.

Update with your own zip codes for searching
---

## 1. Install Python

Download Python 3.10+ from https://python.org/downloads  
(Check "Add Python to PATH" during install on Windows.)

---

## 2. Install Dependencies

Open Terminal (Mac/Linux) or Command Prompt (Windows) in this folder:

```bash
pip install -r requirements.txt
```

---

## 3. Get a Google Maps API Key

1. Go to https://console.cloud.google.com
2. Create a new project (e.g. "Gas Tracker")
3. Go to **APIs & Services → Library** and enable these two APIs:
   - **Places API**
   - **Geocoding API**
4. Go to **APIs & Services → Credentials → Create Credentials → API Key**
5. Copy the key — you'll paste it into `config.json`

> 💡 **Cost:** Google gives you $200/month free credit. This script makes ~30 API
> calls per day (15 stations × 2 ZIPs), which costs well under $1/month — effectively free.

> 🔒 **Optional security:** In the API key settings, restrict the key to only the
> Places API and Geocoding API so it can't be misused if leaked.

---

## 4. Configure

```bash
cp config.example.json config.json
```

Open `config.json` and fill in:

| Field | What to put |
|-------|-------------|
| `google_maps_api_key` | The API key from Step 3 |
| `email.sender` | Your Gmail address |
| `email.recipient` | Where to send the report (can be same address) |
| `email.app_password` | A Gmail App Password (NOT your regular password — see below) |

### Getting a Gmail App Password

1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** (required)
3. Go to https://myaccount.google.com/apppasswords
4. Create an app password → name it "Gas Tracker"
5. Copy the 16-character password into `config.json`

---

## 5. Test It

```bash
python gas_tracker.py
```

You should see stations fetched and an email arrive in your inbox.

> **Note on prices showing N/A:** Google Maps has fuel prices for many stations,
> but not all. Stations that haven't reported prices to Google will show "N/A".
> This is normal — typically 50–80% of stations will have prices.

---

## 6. Schedule at 7 AM Daily

### Windows (Task Scheduler)

1. Open **Task Scheduler** → Create Basic Task
2. Name: `Gas Price Tracker`
3. Trigger: **Daily** at **7:00 AM**
4. Action: **Start a program**
   - Program: `python`  
     (or full path like `C:\Python312\python.exe`)
   - Arguments: `gas_tracker.py`
   - Start in: `C:\path\to\this\folder`
5. Finish → right-click → Run to test

### Mac / Linux (cron)

```bash
crontab -e
```

Add this line (update the path to your folder):

```
0 7 * * * /usr/bin/python3 /path/to/gas_tracker/gas_tracker.py >> /path/to/gas_tracker/cron.log 2>&1
```

---

## 7. CSV Database

Prices are automatically appended to `gas_prices.csv` each run:

```
date,zip,station,address,price_87
2025-04-08,60014,Shell,1234 Main St Crystal Lake IL,3.259
2025-04-08,60012,BP,5678 Elm Ave Crystal Lake IL,3.299
```

Open this in Excel or Google Sheets anytime for historical tracking.

---

## 8. Optional: Google Sheets Integration

To *also* log to a Google Sheet automatically:

1. In Google Cloud Console, enable the **Google Sheets API**
2. Create a **Service Account** → Download the JSON key → save as `service_account.json` in this folder
3. Share your Google Sheet with the service account email (give it Editor access)
4. In `config.json` set:
   ```json
   "google_sheets": {
     "enabled": true,
     "spreadsheet_id": "YOUR_SHEET_ID_FROM_URL",
     "service_account_json": "service_account.json"
   }
   ```
5. Install extra libraries:
   ```bash
   pip install google-auth google-auth-httplib2 google-api-python-client
   ```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `REQUEST_DENIED` from API | Check your API key is correct and Places/Geocoding APIs are enabled |
| All prices show N/A | Normal for some stations — Google doesn't have prices for all locations |
| Email not sending | Double-check Gmail App Password; make sure 2FA is on |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |
| Windows: script doesn't run at 7am | In Task Scheduler, check "Run whether user is logged on or not" |
