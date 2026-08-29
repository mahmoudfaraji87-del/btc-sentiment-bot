"""
Coinglass Open Interest Tracker (BTC + ETH)
--------------------------------------------
Reads the "All" row (aggregate across all exchanges) from:
  https://www.coinglass.com/open-interest/BTC
  https://www.coinglass.com/open-interest/ETH

For each coin, extracts:
  - Total Open Interest in USD  (e.g. "$54.04B")
  - Rate (always ~100% for the "All" row, included for completeness)
  - OI Change 1h  (percentage, signed)
  - OI Change 4h  (percentage, signed)
  - OI Change 24h (percentage, signed)

Sends a combined summary for both coins to Telegram.

Reuses the same infrastructure as the sentiment bot:
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
import csv
import json
import time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

LOG_FILE = "data/open_interest_log.csv"
LOG_HEADER = [
    "timestamp_utc",
    "btc_oi_usd", "btc_rate", "btc_change_1h", "btc_change_4h", "btc_change_24h",
    "eth_oi_usd", "eth_rate", "eth_change_1h", "eth_change_4h", "eth_change_24h",
    "btc_price_usd", "eth_price_usd",
]

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

COINS = {
    "BTC": "https://www.coinglass.com/open-interest/BTC",
    "ETH": "https://www.coinglass.com/open-interest/ETH",
}

FIELDS = ["oi_usd", "rate", "change_1h", "change_4h", "change_24h"]


def fetch_rendered_html(url: str):
    """Fetch a JS-rendered page via ScraperAPI (premium pool), with retries."""
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
    """Ask Claude to extract the 'All' row Open Interest stats for this coin."""
    if not ANTHROPIC_API_KEY:
        return None
    prompt = (
        f"Below is the text content of the Coinglass '{coin} Open Interest' page. "
        "It contains a table with a header row 'Ranking Exchanges OI(...) OI Rate "
        "OI Change (1h) OI Change (4h) OI Change (24h) OI/24h_Vol Trade', followed "
        "by a row starting with 'All' that gives the aggregate across all exchanges, "
        "then individual exchange rows (CME, Binance, OKX, Bybit, etc).\n\n"
        "Find ONLY the 'All' row (the aggregate total, not any individual exchange) "
        "and extract:\n"
        "- oi_usd: the total Open Interest in USD as a plain number (convert B=billion, "
        "M=million, K=thousand to full numbers, e.g. '$54.04B' -> 54040000000)\n"
        "- rate: the Rate percentage as a number (e.g. 100)\n"
        "- change_1h: the OI Change (1h) percentage as a signed number (e.g. -0.09 or 0.08)\n"
        "- change_4h: the OI Change (4h) percentage as a signed number\n"
        "- change_24h: the OI Change (24h) percentage as a signed number\n\n"
        "Reply with ONLY a JSON object, no other text, in exactly this shape:\n"
        '{"oi_usd": <number>, "rate": <number>, "change_1h": <number>, '
        '"change_4h": <number>, "change_24h": <number>}\n\n'
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
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        reply_text = r.json()["content"][0]["text"].strip()
        reply_text = re.sub(r"^```(json)?|```$", "", reply_text, flags=re.MULTILINE).strip()
        data = json.loads(reply_text)
        if all(f in data for f in FIELDS):
            return {f: float(data[f]) for f in FIELDS}
        print(f"[claude-parse:{coin}] missing fields: {data}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[claude-parse:{coin}] failed: {e}", file=sys.stderr)
        return None


def parse_with_regex(page_text: str, coin: str):
    """Fallback: find the 'All' row and grab the numbers in column order.
    Fragile -- breaks if Coinglass changes the table layout."""
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    try:
        idx = lines.index("All")
    except ValueError:
        print(f"[regex:{coin}] could not find 'All' row", file=sys.stderr)
        return None

    window = lines[idx: idx + 12]  # a few lines after "All" should hold the row's values
    window_text = " ".join(window)

    usd_match = re.search(r"\$([\d.]+)\s*([BMK])", window_text)
    pct_matches = re.findall(r"([+-]?\d+\.?\d*)\s*%", window_text)

    if not usd_match or len(pct_matches) < 4:
        print(f"[regex:{coin}] not enough matches: usd={usd_match}, pct={pct_matches}", file=sys.stderr)
        return None

    multiplier = {"B": 1e9, "M": 1e6, "K": 1e3}[usd_match.group(2)]
    oi_usd = float(usd_match.group(1)) * multiplier

    # pct_matches order should be: rate, change_1h, change_4h, change_24h
    rate, c1h, c4h, c24h = (float(p) for p in pct_matches[:4])

    return {
        "oi_usd": oi_usd,
        "rate": rate,
        "change_1h": c1h,
        "change_4h": c4h,
        "change_24h": c24h,
    }


def get_coin_data(coin: str, url: str):
    html = fetch_rendered_html(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")

    result = parse_with_claude(text, coin)
    if result is not None:
        return result
    return parse_with_regex(text, coin)


def format_usd(value: float) -> str:
    """Turn a raw dollar number back into a readable $X.XXB / $X.XXM string."""
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    if value >= 1e3:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


def format_pct(value: float) -> str:
    arrow = "🔺" if value > 0 else ("🔻" if value < 0 else "⏸")
    return f"{arrow} {value:+.2f}%"


def current_timestamp_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_prices():
    """Fetch current BTC and ETH prices from Binance's free public API (no key needed)."""
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbols": '["BTCUSDT","ETHUSDT"]'},
            timeout=10,
        )
        r.raise_for_status()
        data = {item["symbol"]: float(item["price"]) for item in r.json()}
        return data.get("BTCUSDT"), data.get("ETHUSDT")
    except Exception as e:
        print(f"[prices] failed: {e}", file=sys.stderr)
        return None, None


def build_message(data: dict, btc_price=None, eth_price=None) -> str:
    lines = [
        "📈 پایش Open Interest (مجموع همه‌ی صرافی‌ها)",
        f"🕒 {current_timestamp_str()}",
        "",
    ]
    if btc_price is not None:
        lines.append(f"💵 BTC Price: ${btc_price:,.2f}")
    if eth_price is not None:
        lines.append(f"💵 ETH Price: ${eth_price:,.2f}")
    if btc_price is not None or eth_price is not None:
        lines.append("")
    for coin in ("BTC", "ETH"):
        d = data.get(coin)
        lines.append(f"— {coin} —")
        if d is None:
            lines.append("⚠️ داده در دسترس نبود")
        else:
            lines.append(f"💰 Open Interest: {format_usd(d['oi_usd'])}")
            lines.append(f"📐 Rate: {d['rate']:.0f}%")
            lines.append(f"1️⃣h: {format_pct(d['change_1h'])}")
            lines.append(f"4️⃣h: {format_pct(d['change_4h'])}")
            lines.append(f"2️⃣4️⃣h: {format_pct(d['change_24h'])}")
        lines.append("")
    return "\n".join(lines).strip()


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
    resp.raise_for_status()
    print("Telegram message sent.")


def append_to_log(data: dict, btc_price=None, eth_price=None):
    """Append this run's data as one row to a CSV file in the repo."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_exists = os.path.isfile(LOG_FILE)
    row = [current_timestamp_str()]
    for coin in ("BTC", "ETH"):
        d = data.get(coin)
        if d is None:
            row.extend(["", "", "", "", ""])
        else:
            row.extend([d["oi_usd"], d["rate"], d["change_1h"], d["change_4h"], d["change_24h"]])
    row.append(btc_price if btc_price is not None else "")
    row.append(eth_price if eth_price is not None else "")
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(LOG_HEADER)
        writer.writerow(row)
    print(f"Logged row to {LOG_FILE}")


def main():
    data = {}
    for coin, url in COINS.items():
        data[coin] = get_coin_data(coin, url)

    btc_price, eth_price = get_prices()
    message = build_message(data, btc_price, eth_price)
    print(message)
    append_to_log(data, btc_price, eth_price)

    if all(v is None for v in data.values()):
        # Both failed -- still notify so silence doesn't look like the bot is broken.
        send_telegram(
            "⚠️ پایش Open Interest\n"
            f"🕒 {current_timestamp_str()}\n\n"
            "این ساعت نتونستم داده‌ی هیچ‌کدوم از دو ارز رو بگیرم. "
            "ساعت بعد دوباره تلاش می‌کنم."
        )
        raise RuntimeError("Could not fetch Open Interest data for BTC or ETH.")

    send_telegram(message)


if __name__ == "__main__":
    main()
