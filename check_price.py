import os
import re
import json
import time
import requests
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


# ── LOAD .env ─────────────────────────────────────────────────────────────────

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

load_env()

ANAKIN_API_KEY  = os.environ["ANAKIN_API_KEY"]
SPREADSHEET_ID  = os.environ["SPREADSHEET_ID"]
GCP_CREDS_JSON  = os.environ["ACCOUNT_CREDENTIALS"]
PRICE_THRESHOLD = float(os.environ.get("PRICE_THRESHOLD", "40000"))
TWILIO_SID      = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN    = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM     = os.environ.get("TWILIO_FROM", "whatsapp:+14155238886")
WHATSAPP_TO     = os.environ.get("WHATSAPP_TO", "")

FLIPKART_URL = (
    "https://www.flipkart.com/oneplus-nord-6-pitch-black-256-gb/p/itmc49f71cdc4080"
    "?pid=MOBHMBXBMGCDHP55&marketplace=FLIPKART"
)


# ── STEP 1: SCRAPE PRICE ──────────────────────────────────────────────────────

def get_price():
    print("Step 1: Submitting scrape job...")

    resp = requests.post(
        "https://api.anakin.io/v1/url-scraper",
        headers={"X-API-Key": ANAKIN_API_KEY, "Content-Type": "application/json"},
        json={"url": FLIPKART_URL, "useBrowser": True, "generateJson": True},
        timeout=30,
    )
    resp.raise_for_status()
    job_id = resp.json()["jobId"]
    print(f"  Job ID: {job_id}")

    print("Step 2: Waiting for result...")
    for attempt in range(20):
        time.sleep(3)
        result = requests.get(
            f"https://api.anakin.io/v1/url-scraper/{job_id}",
            headers={"X-API-Key": ANAKIN_API_KEY},
            timeout=15,
        ).json()

        status = result.get("status")
        print(f"  Attempt {attempt + 1}: {status}")

        if status == "completed":
            break
        if status == "failed":
            raise RuntimeError(f"Scrape failed: {result.get('error')}")
    else:
        raise TimeoutError("Timed out waiting for scrape.")

    for field in ("cleanedHtml", "markdown"):
        text = result.get(field, "") or ""

        # Strategy 1: Flipkart price block — "32% 56,999 ₹38,999"
        m = re.search(r"\d+%\s+[\d,]+\s+[\u20b9]\s*([\d,]+)", text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 5000 <= val <= 500000:
                print(f"  Price (strategy 1 - price block): Rs {val:,.0f}")
                return val

        # Strategy 2: Flipkart CSS class v1zwn21l that holds selling price
        m = re.search(r"v1zwn21l[^>]*>[\u20b9]\s*([\d,]+)", text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 5000 <= val <= 500000:
                print(f"  Price (strategy 2 - CSS class): Rs {val:,.0f}")
                return val

        # Strategy 3: First ₹ price in range (DOM order = selling price first)
        text = text.replace("&#8377;", "\u20b9").replace("&#x20B9;", "\u20b9")
        for m in re.finditer(r"[\u20b9]\s*([\d,]+)", text):
            val = float(m.group(1).replace(",", ""))
            if 5000 <= val <= 500000:
                print(f"  Price (strategy 3 - first match): Rs {val:,.0f}")
                return val

    raise ValueError("Price not found on page.")


# ── STEP 2: WRITE TO GOOGLE SHEET ────────────────────────────────────────────

def write_to_sheet(price):
    print("Step 3: Connecting to Google Sheets...")

    creds_dict = json.loads(GCP_CREDS_JSON)
    print(f"  Service account: {creds_dict.get('client_email')}")
    print(f"  Spreadsheet ID : {SPREADSHEET_ID}")

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    sheet = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

    try:
        meta = sheet.get(spreadsheetId=SPREADSHEET_ID).execute()
    except Exception as e:
        err = str(e)
        if "404" in err:
            print("\n  ERROR 404 - Sheet not found. Two things to check:")
            print("  1. Open your sheet and click Share")
            print(f"     Add: {creds_dict.get('client_email')} as Editor")
            print("  2. Enable Google Sheets API at:")
            print("     https://console.cloud.google.com/apis/library/sheets.googleapis.com")
            print(f"     (project: {creds_dict.get('project_id')})")
        elif "403" in err:
            print("\n  ERROR 403 - Google Sheets API not enabled.")
            print("  Enable it at:")
            print("     https://console.cloud.google.com/apis/library/sheets.googleapis.com")
            print(f"     (project: {creds_dict.get('project_id')})")
        else:
            print(f"\n  ERROR: {e}")
        raise

    tab_name = meta["sheets"][0]["properties"]["title"]
    print(f"  Tab: '{tab_name}'")

    # Write headers if the sheet is empty
    existing = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{tab_name}!A1:C1",
    ).execute()

    if not existing.get("values"):
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{tab_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [["Timestamp", "Product URL", "Price (Rs)"]]},
        ).execute()
        print("  Headers written.")

    # Append price row
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [timestamp, FLIPKART_URL, price]

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{tab_name}!A:C",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    print(f"  Row added: {row}")
    print(f"  Sheet URL: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")


# ── STEP 3: WHATSAPP ALERT via TWILIO ────────────────────────────────────────

def send_whatsapp_alert(price):
    # Check credentials are filled in
    if (not TWILIO_SID or not TWILIO_TOKEN or not WHATSAPP_TO
            or "xxxx" in TWILIO_SID.lower() or "XXXXXXXXXX" in WHATSAPP_TO):
        print("  WhatsApp skipped — fill Twilio credentials in .env")
        print("  Get free credentials at: https://www.twilio.com")
        return

    from twilio.rest import Client

    message_body = (
        f"PriceSpy Alert!\n"
        f"OnePlus Nord 6 is now Rs {price:,.0f}\n"
        f"Your target: Rs {PRICE_THRESHOLD:,.0f}\n"
        f"Buy now: {FLIPKART_URL}"
    )

    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(
            from_=TWILIO_FROM,
            to=WHATSAPP_TO,
            body=message_body,
        )
        print(f"  Message SID    : {msg.sid}")
        print(f"  Status         : {msg.status}")
        print(f"  Sent to        : {WHATSAPP_TO}")
        if msg.error_code:
            print(f"  Error code     : {msg.error_code}")
            print(f"  Error message  : {msg.error_message}")
        else:
            print("  WhatsApp alert sent successfully!")
    except Exception as e:
        print(f"  WhatsApp failed: {e}")
        print("  Make sure the recipient has joined the Twilio sandbox by")
        print(f"  sending 'join <your-sandbox-word>' to +14155238886 on WhatsApp")


# ── STEP 4: SAVE TO LOCAL JSON ────────────────────────────────────────────────

def save_to_json(price):
    output_file = os.path.join(os.path.dirname(__file__), "price_data.json")

    data = []
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    data.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "product_url": FLIPKART_URL,
        "price_rs": price,
    })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  Saved to price_data.json  (total entries: {len(data)})")


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  PriceSpy - Flipkart Price Checker")
    print("=" * 50)

    price = get_price()
    print(f"\n  >> Current Price : Rs {price:,.0f}")
    print(f"     Target Price  : Rs {PRICE_THRESHOLD:,.0f}")
    print(f"     Status        : {'BELOW TARGET - sending alert!' if price < PRICE_THRESHOLD else 'Above target'}\n")

    save_to_json(price)
    write_to_sheet(price)

    if price < PRICE_THRESHOLD:
        print("Step 4: Sending WhatsApp alert...")
        send_whatsapp_alert(price)
    else:
        print("Step 4: Price is above threshold — no WhatsApp alert sent.")

    print("\nDone!")
