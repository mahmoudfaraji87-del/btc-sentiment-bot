"""
Coinglass Long/Short Ratio Tracker (BTC + ETH)
-------------------------------------------------
Reads the per-exchange Long/Short Ratio tables from:
  https://www.coinglass.com/LongShortRatio      (BTC)
  https://www.coinglass.com/LongShortRatio/ETH  (ETH)

For each coin, for Binance, OKX, and Bybit, extracts:
  - Retail Long/Short ratio
  - Whale Account Long/Short ratio
  - Whale Position Long/Short ratio

Required GitHub Actions secrets:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  SCRAPERAPI_KEY
Optional:
  ANTHROPIC_API_KEY   (if set, Claude parses the page -- far more robust than regex)
"""

import os
import re
import sys
import json
import time
import csv
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

COINS = {
    "BTC": "https://www.coinglass.com/LongShortRatio",
    "ETH": "https://www.coinglass.com/LongShortRatio/ETH",
}
EXCHANGES = ["Binance", "OKX", "Bybit"]
ROWS = ["Retail", "Whale Account", "Whale Position"]

LOG_FILE = "data/long_short_ratio_log.csv"
LOG_HEADER = ["timestamp_utc"]
for coin in COINS:
    for ex in EXCHANGES:
        for row in ROWS:
            LOG_HEADER.append(f"{coin.lower()}_{ex.lower().replace(' ', '_')}_{row.lower().replace(' ', '_')}")
LOG_HEADER += ["btc_price_usd", "eth_price_usd"]


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


def fetch_rendered_html(url: str):
    if not SCRAPERAPI_KEY:
        print("[scraperapi] no SCRAPERAPI_KEY set", file=sys.stderr)
        return None
    api_url = "https://api.scraperapi.com/"
    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": url,
        "render": "true",
        "premium": "true",
    }
    last_error = None
    for attempt in range(1, 4):
        try:
            r = requests.get(api_url, params=params, timeout=120)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_error = str(e)
        print(f"[scraperapi] {url} attempt {attempt} failed: {last_error}", file=sys.stderr)
        if attempt < 3:
            time.sleep(5 * attempt)
    return None


def parse_with_claude(page_text: str, coin: str):
    if not ANTHROPIC_API_KEY:
        return None
    prompt = (
        f"Below is the text content of the Coinglass '{coin} Long/Short Ratio' page. "
        "It has separate tables per exchange (e.g. 'Binance ... Long/Short Ratio', "
        "'OKX ... Long/Short Ratio', 'Bybit ... Long/Short Ratio'), each with rows: "
        "Retail, Whale Account, Whale Position, Smart Money Sentiment. Each of the "
        "first three rows has a numeric Long/Short ratio value (e.g. 0.96, 1.04, 2.07).\n\n"
        "I need ONLY the numeric ratio value for these three rows, for these three "
        "exchanges: Binance, OKX, Bybit -- Retail, Whale Account, Whale Position "
        "(ignore Smart Money Sentiment, that one has no numeric ratio).\n\n"
        "Reply with ONLY a JSON object, no other text, in exactly this shape:\n"
        '{"Binance": {"Retail": <number>, "Whale Account": <number>, "Whale Position": <number>}, '
        '"OKX": {"Retail": <number>, "Whale Account": <number>, "Whale Position": <number>}, '
        '"Bybit": {"Retail": <number>, "Whale Account": <number>, "Whale Position": <number>}}\n\n'
        "Page text:\n" + page_text[:15000]
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        reply_text = r.json()["content"][0]["text"].strip()
        reply_text = re.sub(r"^```(json)?|```$", "", reply_text, flags=re.MULTILINE).strip()
        data = json.loads(reply_text)
        result = {}
        for ex in EXCHANGES:
            if ex not in data:
                print(f"[claude-parse:{coin}] missing exchange {ex}: {data}", file=sys.stderr)
                return None
            result[ex] = {}
            for row in ROWS:
                if row not in data[ex]:
                    print(f"[claude-parse:{coin}] missing {ex}/{row}: {data}", file=sys.stderr)
                    return None
                result[ex][row] = float(data[ex][row])
        return result
    except Exception as e:
        print(f"[claude-parse:{coin}] failed: {e}", file=sys.stderr)
        return None


def parse_with_regex(page_text: str, coin: str):
    """Fallback: find each exchange's section header, then grab the first 3 numeric
    ratio values (Retail, Whale Account, Whale Position, in that order)."""
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    result = {}
    for ex in EXCHANGES:
        idx = None
        for i, l in enumerate(lines):
            if ex in l and "Long/Short" in l:
                idx = i
                break
        if idx is None:
            print(f"[regex:{coin}] could not find section header for {ex}", file=sys.stderr)
            return None
        window = " ".join(lines[idx: idx + 25])
        matches = re.findall(r"(\d+\.\d+)", window)
        if len(matches) < 3:
            print(f"[regex:{coin}] not enough matches for {ex}: {matches}", file=sys.stderr)
            return None
        result[ex] = {
            "Retail": float(matches[0]),
            "Whale Account": float(matches[1]),
            "Whale Position": float(matches[2]),
        }
    return result


def get_ratio_data(coin: str, url: str):
    html = fetch_rendered_html(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    result = parse_with_claude(text, coin)
    if result is not None:
        return result
    return parse_with_regex(text, coin)


def current_timestamp_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def append_to_log(data, btc_price, eth_price):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_exists = os.path.isfile(LOG_FILE)
    row = [current_timestamp_str()]
    for coin in COINS:
        coin_data = data.get(coin)
        for ex in EXCHANGES:
            for r in ROWS:
                if coin_data is None:
                    row.append("")
                else:
                    row.append(coin_data.get(ex, {}).get(r, ""))
    row.append(btc_price if btc_price is not None else "")
    row.append(eth_price if eth_price is not None else "")
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(LOG_HEADER)
        writer.writerow(row)
    print(f"Logged row to {LOG_FILE}")


def build_message(data, btc_price, eth_price):
    lines = [
        "⚖️ پایش نسبت Long/Short",
        f"🕒 {current_timestamp_str()}",
        "",
    ]
    if btc_price is not None:
        lines.append(f"💵 BTC: ${btc_price:,.2f}")
    if eth_price is not None:
        lines.append(f"💵 ETH: ${eth_price:,.2f}")
    if btc_price is not None or eth_price is not None:
        lines.append("")
    for coin in COINS:
        coin_data = data.get(coin)
        lines.append(f"===== {coin} =====")
        for ex in EXCHANGES:
            lines.append(f"— {ex} —")
            d = coin_data.get(ex) if coin_data else None
            if d is None:
                lines.append("⚠️ داده در دسترس نبود")
            else:
                for r in ROWS:
                    lines.append(f"{r}: {d[r]}")
        lines.append("")
    return "\n".join(lines).strip()


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
    resp.raise_for_status()
    print("Telegram message sent.")


def main():
    data = {}
    for coin, url in COINS.items():
        data[coin] = get_ratio_data(coin, url)

    btc_price, eth_price = get_prices()
    message = build_message(data, btc_price, eth_price)
    print(message)
    append_to_log(data, btc_price, eth_price)

    if all(v is None for v in data.values()):
        send_telegram(
            "⚠️ پایش نسبت Long/Short\n"
            f"🕒 {current_timestamp_str()}\n\n"
            "این ساعت نتونستم داده‌ی هیچ‌کدوم از دو ارز رو بگیرم. ساعت بعد دوباره تلاش می‌کنم."
        )
        raise RuntimeError("Could not fetch Long/Short ratio data for BTC or ETH.")

    send_telegram(message)


if __name__ == "__main__":
    main()
