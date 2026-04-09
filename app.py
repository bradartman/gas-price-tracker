"""
Gas Price Tracker - Flask Web App
Serves a simple web UI to fetch latest prices and export CSV.
"""

import csv
import io
import json
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, Response

from gas_tracker import (
    load_config,
    fetch_all_stations,
    save_to_csv,
    save_to_google_sheets,
    CSV_FILE,
)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fetch", methods=["POST"])
def fetch_prices():
    """Fetch latest gas prices, save to CSV, return JSON."""
    try:
        config = load_config()
    except SystemExit:
        return jsonify({"error": "config.json not found. Please create it from config.example.json."}), 500

    # ZIP codes can come from the request body (UI input) or fall back to config
    body = request.get_json(silent=True) or {}
    zip_codes = body.get("zip_codes") or config.get("zip_codes", ["60014", "60012"])
    zip_codes = [str(z).strip() for z in zip_codes if str(z).strip()]
    if not zip_codes:
        return jsonify({"error": "No ZIP codes provided."}), 400

    stations = fetch_all_stations(zip_codes)
    if not stations:
        return jsonify({"error": "No stations found. Check your internet connection, or GasBuddy may have changed their layout."}), 502

    save_to_csv(stations)
    save_to_google_sheets(stations, config)

    # Group by ZIP for display
    by_zip = {}
    for s in stations:
        by_zip.setdefault(s["zip"], []).append(s)

    for z, rows in by_zip.items():
        rows.sort(key=lambda r: float(r["price_87"]) if r["price_87"] != "N/A" else 9999)

    return jsonify({
        "date": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        "by_zip": by_zip,
        "total": len(stations),
    })


@app.route("/api/export")
def export_csv():
    """Download the gas_prices.csv file."""
    if not CSV_FILE.exists():
        return jsonify({"error": "No data yet. Fetch prices first."}), 404

    return send_file(
        CSV_FILE,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"gas_prices_{datetime.now().strftime('%Y%m%d')}.csv",
    )


@app.route("/api/history")
def history():
    """Return all rows from the CSV as JSON for the history table."""
    if not CSV_FILE.exists():
        return jsonify([])

    rows = []
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    return jsonify(rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5999)
