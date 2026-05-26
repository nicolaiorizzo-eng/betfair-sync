import requests
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import os
import json

# ==========================================
# ⚙️  All secrets come from environment variables.
#     Set these in GitHub Actions Secrets (or a .env file locally).
# ==========================================
BETFAIR_APP_KEY    = os.environ["BETFAIR_APP_KEY"]
BETFAIR_USERNAME   = os.environ["BETFAIR_USERNAME"]
BETFAIR_PASSWORD   = os.environ["BETFAIR_PASSWORD"]
GOOGLE_SHEET_NAME  = os.environ["GOOGLE_SHEET_NAME"]          # e.g. "Professional Trading WB"
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS_JSON"]    # full JSON string of your service account key
DAYS_TO_FETCH      = int(os.environ.get("DAYS_TO_FETCH", "3")) # default 3 days, override as needed
# ==========================================


def betfair_login(username, password, app_key):
    url = "https://identitysso.betfair.com/api/login"
    headers = {
        "X-Application": app_key,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {"username": username, "password": password}

    raw = requests.post(url, data=payload, headers=headers)
    print(f"Betfair login status code: {raw.status_code}")
    print(f"Betfair login response: {raw.text}")

    response = raw.json()
    if response.get("status") != "SUCCESS":
        raise RuntimeError(f"Betfair login failed: {response.get('error', 'Unknown error')}")

    print("✅ Betfair login successful.")
    return response["token"]


def fetch_backup_market_text(market_ids, session_token, app_key):
    """
    Fallback catalogue lookup. Works for open markets only —
    settled markets won't appear here, which is expected.
    """
    if not market_ids:
        return {}

    url = "https://api.betfair.com/exchange/betting/rest/v1.0/listMarketCatalogue/"
    headers = {
        "X-Application": app_key,
        "X-Authentication": session_token,
        "content-type": "application/json"
    }
    payload = {
        "filter": {"marketIds": list(market_ids)},
        "maxResults": 100,
        "marketProjection": ["EVENT", "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"]
    }

    try:
        response = requests.post(url, json=payload, headers=headers).json()
        lookup = {}
        if isinstance(response, list):
            for market in response:
                m_id = market.get("marketId")
                lookup[m_id] = {
                    "event":   market.get("event", {}).get("name", ""),
                    "market":  market.get("marketName", ""),
                    "runners": {
                        str(r["selectionId"]): r["runnerName"]
                        for r in market.get("runners", [])
                    }
                }
        return lookup
    except Exception as e:
        print(f"⚠️  Catalogue lookup failed (non-critical): {e}")
        return {}


def resolve_item_description(item_desc, market_lookup, market_id, selection_id):
    """
    Resolves human-readable text using the correct Betfair field names:
      eventDesc  → Match name   (e.g. "Man City v Arsenal")
      marketDesc → Market type  (e.g. "Match Odds")
      runnerDesc → Selection    (e.g. "Man City")
    Falls back to catalogue lookup, then a safe default.
    """
    event_name     = item_desc.get("eventDesc")   or market_lookup.get("event")                           or "Unknown Match"
    market_desc    = item_desc.get("marketDesc")  or market_lookup.get("market")                          or f"Market: {market_id}"
    selection_name = item_desc.get("runnerDesc")  or market_lookup.get("runners", {}).get(selection_id)  or "Unknown Selection"
    return event_name, market_desc, selection_name


def sync_trades_to_google():
    print("🚀 Starting automated sync...")

    # --- 1. Auto-login to Betfair ---
    session_token = betfair_login(BETFAIR_USERNAME, BETFAIR_PASSWORD, BETFAIR_APP_KEY)

    # --- 2. Connect to Google Sheets using service account JSON from env var ---
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS)
        creds  = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet  = client.open(GOOGLE_SHEET_NAME).sheet1
    except Exception as e:
        print(f"❌ Google Sheets connection failed: {e}")
        return

    headers_row = sheet.row_values(1)
    if "BetID" not in headers_row:
        print("❌ Missing 'BetID' column header in sheet row 1.")
        return

    existing_rows   = sheet.get_all_records()
    existing_bet_ids = {str(r.get("BetID", "")) for r in existing_rows if r.get("BetID")}
    print(f"📋 Sheet has {len(existing_bet_ids)} existing bets.")

    # --- 3. Fetch settled orders from Betfair ---
    exchange_url = "https://api.betfair.com/exchange/betting/rest/v1.0/listClearedOrders/"
    api_headers  = {
        "X-Application":  BETFAIR_APP_KEY,
        "X-Authentication": session_token,
        "content-type":   "application/json"
    }

    from_date = (datetime.utcnow() - timedelta(days=DAYS_TO_FETCH)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload   = {
        "betStatus":          "SETTLED",
        "groupBy":            "BET",
        "settledDateRange":   {"from": from_date},
        "includeItemDescription": True
    }

    try:
        response       = requests.post(exchange_url, json=payload, headers=api_headers).json()
        cleared_orders = response.get("clearedOrders", [])
    except Exception as e:
        print(f"❌ Betfair API call failed: {e}")
        return

    if not cleared_orders:
        print(f"👀 No settled bets found in the last {DAYS_TO_FETCH} days. Nothing to do.")
        return

    print(f"📡 Fetched {len(cleared_orders)} settled bets from Betfair.")

    # --- 4. Catalogue fallback lookup ---
    all_market_ids = {o["marketId"] for o in cleared_orders if "marketId" in o}
    backup_text_map = fetch_backup_market_text(all_market_ids, session_token, BETFAIR_APP_KEY)

    # --- 5. Write new rows ---
    new_rows_count = 0
    for order in cleared_orders:
        bet_id = str(order.get("betId", ""))
        if not bet_id or bet_id in existing_bet_ids:
            continue

        market_id     = order.get("marketId", "")
        selection_id  = str(order.get("selectionId", ""))
        item_desc     = order.get("itemDescription", {})
        market_lookup = backup_text_map.get(market_id, {})

        event_name, market_desc, selection_name = resolve_item_description(
            item_desc, market_lookup, market_id, selection_id
        )

        pnl          = float(order.get("profit", 0.0))
        liability    = float(order.get("sizeSettled", 0.0))
        avg_odds     = float(order.get("priceMatched", 0.0))
        bet_side     = order.get("side", "N/A")
        settled_date = order.get("settledDate", "").split("T")[0]
        outcome      = "WIN" if pnl > 0 else "LOSS"
        roi          = (pnl / liability * 100) if liability > 0 else 0.0

        new_row = [
            settled_date,
            event_name,
            market_desc,
            selection_name,
            bet_side,
            f"{avg_odds:.2f}",
            f"£{liability:.2f}",
            f"£{pnl:.2f}",
            f"{roi:.2f}%",
            outcome,
            bet_id
        ]

        sheet.append_row(new_row)
        new_rows_count += 1
        existing_bet_ids.add(bet_id)
        print(f"✅ {settled_date} | {event_name} | {market_desc} | {selection_name} | {outcome}")
        time.sleep(0.2)

    print(f"\n🎉 Done! Added {new_rows_count} new records.")


if __name__ == "__main__":
    sync_trades_to_google()
