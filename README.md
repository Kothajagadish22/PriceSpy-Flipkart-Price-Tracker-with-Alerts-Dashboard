# PriceSpy-Flipkart-Price-Tracker-with-Alerts-Dashboard
Automated Flipkart price tracker that scrapes live prices, logs them to Google Sheets, sends WhatsApp alerts via Twilio, and displays a real-time web dashboard.
Full README Description:

PriceSpy is a Python-based price monitoring tool that watches a Flipkart product listing and notifies you when the price drops below your target.

Features:

Live price scraping — Uses the Anakin.io scraper API with multiple regex fallback strategies to reliably extract the current selling price from Flipkart.
Google Sheets logging — Automatically writes each price check (timestamp, URL, price) to a Google Sheet using a GCP service account.
WhatsApp alerts — Sends an instant WhatsApp message via Twilio when the price falls below your configured threshold.
Local JSON history — Stores all price snapshots in price_data.json for offline access and dashboard use.
Web dashboard — A Flask-powered dashboard (dashboard.py) served on port 5050 with a rich UI showing current price, historical chart, lowest/highest/average stats, and a live "Run Check" button that streams the script output in real time.
Tech Stack: Python, Flask, Requests, Google Sheets API, Twilio, Anakin.io API

Setup: Configure your API keys and credentials in .env, install dependencies with pip install -r requirements.txt, and run dashboard.py or check_price.py directly.

