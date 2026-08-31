"""
Fear & Greed Index Tracker
----------------------------
Uses the official free Alternative.me Fear & Greed Index API
(https://alternative.me/crypto/fear-and-greed-index/) -- no scraping needed,
no ScraperAPI credits used, very reliable.

Required GitHub Actions secrets:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import sys
import csv
from datetime import datetime, timezone
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

LOG_FILE = "data/fear_greed_log.csv"
LOG_HEADER = ["timestamp_utc", "value", "classification", "btc_price_usd", "eth_price_usd"]


def get_prices():
    """Fetch current BTC and ETH prices from CoinGecko's free public API (no key needed)."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin,ethereum", "vs_currencies": "usd"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("bitcoin", {}).get("usd"), data.get("ethereum", {}).get("usd")
    except Exception as e:
        print(f"[prices] failed: {e}", file=sys.stderr)
        return None, None


def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/", params={"limit": 1}, timeout=15)
        r.raise_for_status()
        item = r.json()["data"][0]
        return int(item["value"]), item["value_classification"]
    except Exception as e:
        print(f"[fng] failed: {e}", file=sys.stderr)
        return None, None


def current_timestamp_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def append_to_log(value, classification, btc_price, eth_price):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(LOG_HEADER)
        writer.writerow([
            current_timestamp_str(),
            value if value is not None else "",
            classification if classification is not None else "",
            btc_price if btc_price is not None else "",
            eth_price if eth_price is not None else "",
        ])
    print(f"Logged row to {LOG_FILE}")


def emoji_for(value):
    if value is None:
        return "❓"
    if value <= 24:
        return "🟥"  # Extreme Fear
    if value <= 44:
        return "🟧"  # Fear
    if value <= 55:
        return "🟨"  # Neutral
    if value <= 74:
        return "🟩"  # Greed
    return "🟢"      # Extreme Greed


def send_telegram(value, classification, btc_price, eth_price):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    if value is None:
        message = (
            "⚠️ پایش شاخص Fear & Greed\n"
            f"🕒 {current_timestamp_str()}\n\n"
            "این ساعت نتونستم داده رو بگیرم. ساعت بعد دوباره تلاش می‌کنم."
        )
    else:
        price_lines = ""
        if btc_price is not None:
            price_lines += f"💵 BTC: ${btc_price:,.2f}\n"
        if eth_price is not None:
            price_lines += f"💵 ETH: ${eth_price:,.2f}\n"
        if price_lines:
            price_lines += "\n"
        message = (
            "😨😐😄 شاخص Fear & Greed\n"
            f"🕒 {current_timestamp_str()}\n\n"
            f"{price_lines}"
            f"{emoji_for(value)} مقدار: {value}/100\n"
            f"وضعیت: {classification}"
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
    resp.raise_for_status()
    print("Telegram message sent.")


def main():
    value, classification = get_fear_greed()
    btc_price, eth_price = get_prices()
    append_to_log(value, classification, btc_price, eth_price)
    send_telegram(value, classification, btc_price, eth_price)
    if value is None:
        raise RuntimeError("Could not fetch Fear & Greed index.")


if __name__ == "__main__":
    main()
