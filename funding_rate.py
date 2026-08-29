"""
Coinglass Funding Rate Tracker (BTC + ETH)
--------------------------------------------
Reads the "Current" funding rate table from:
  https://www.coinglass.com/FundingRate

For BTC and ETH, extracts the current funding rate (%) from the
USDT/USD-Margined section (NOT Token-Margined, NOT Predicted) for:
  - Binance
  - OKX
  - Bybit

Sends a combined summary for both coins to Telegram.

Reuses the same infrastructure as the other bots in this repo:
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
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

TARGET_URL = "https://www.coinglass.com/FundingRate"

COINS = ["BTC", "ETH"]
EXCHANGES = ["Binance", "OKX", "Bybit"]


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
        print(f"[scraperapi] attempt {attempt} failed: {last_error}", file=sys.stderr)
        if attempt < 3:
            time.sleep(5 * attempt)
    return None


def parse_with_claude(page_text: str):
    """Ask Claude to extract current BTC/ETH funding rates for Binance/OKX/Bybit."""
    if not ANTHROPIC_API_KEY:
        return None
    prompt = (
        "Below is the text content of the Coinglass 'Funding Rate' page. It shows "
        "a table of current funding rates per coin per exchange. There are TWO "
        "sections of exchange columns side by side: first a 'USDT or USD Margined' "
        "section (columns like Binance, OKX, Bybit, KuCoin, MEXC, BingX, Gate, "
        "Bitunix, Bitget, WhiteBIT, LBank, tradeXYZ), and then further right a "
        "'Token Margined' section which ALSO has columns named Binance, OKX, Bybit. "
        "There is also a 'Predicted' row under each coin row -- ignore that, use "
        "only the 'Current' values (the main row, not Predicted).\n\n"
        "I need ONLY the values from the FIRST (USDT or USD Margined) section, "
        "for the 'Current' row, for these two coins: BTC and ETH, and only these "
        "three exchanges: Binance, OKX, Bybit.\n\n"
        "Reply with ONLY a JSON object, no other text, in exactly this shape "
        "(percentages as signed numbers, e.g. 0.01 or -0.0015):\n"
        '{"BTC": {"Binance": <number>, "OKX": <number>, "Bybit": <number>}, '
        '"ETH": {"Binance": <number>, "OKX": <number>, "Bybit": <number>}}\n\n'
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
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        reply_text = r.json()["content"][0]["text"].strip()
        reply_text = re.sub(r"^```(json)?|```$", "", reply_text, flags=re.MULTILINE).strip()
        data = json.loads(reply_text)
        result = {}
        for coin in COINS:
            if coin not in data:
                print(f"[claude-parse] missing coin {coin}: {data}", file=sys.stderr)
                return None
            result[coin] = {}
            for ex in EXCHANGES:
                if ex not in data[coin]:
                    print(f"[claude-parse] missing {coin}/{ex}: {data}", file=sys.stderr)
                    return None
                result[coin][ex] = float(data[coin][ex])
        return result
    except Exception as e:
        print(f"[claude-parse] failed: {e}", file=sys.stderr)
        return None


def parse_with_regex(page_text: str):
    """Fallback: find each coin's row and grab the first 3 percentages after it
    (Binance, OKX, Bybit -- in that column order in the USDT/USD Margined section).
    Fragile -- breaks if Coinglass changes the table layout or column order."""
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]
    result = {}
    for coin in COINS:
        try:
            idx = lines.index(coin)
        except ValueError:
            print(f"[regex] could not find row for {coin}", file=sys.stderr)
            return None
        window = " ".join(lines[idx: idx + 15])
        pct_matches = re.findall(r"([+-]?\d+\.?\d*)\s*%", window)
        if len(pct_matches) < 3:
            print(f"[regex] not enough matches for {coin}: {pct_matches}", file=sys.stderr)
            return None
        result[coin] = {
            "Binance": float(pct_matches[0]),
            "OKX": float(pct_matches[1]),
            "Bybit": float(pct_matches[2]),
        }
    return result


def get_funding_data():
    html = fetch_rendered_html(TARGET_URL)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")

    result = parse_with_claude(text)
    if result is not None:
        return result
    return parse_with_regex(text)


def format_pct(value: float) -> str:
    arrow = "🔺" if value > 0 else ("🔻" if value < 0 else "⏸")
    return f"{arrow} {value:+.4f}%"


def current_timestamp_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_message(data: dict) -> str:
    lines = [
        "💸 پایش نرخ فاندینگ (Funding Rate)",
        f"🕒 {current_timestamp_str()}",
        "",
    ]
    for coin in COINS:
        d = data.get(coin)
        lines.append(f"— {coin} —")
        if d is None:
            lines.append("⚠️ داده در دسترس نبود")
        else:
            for ex in EXCHANGES:
                lines.append(f"{ex}: {format_pct(d[ex])}")
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
    data = get_funding_data()

    if data is None:
        send_telegram(
            "⚠️ پایش نرخ فاندینگ\n"
            f"🕒 {current_timestamp_str()}\n\n"
            "این ساعت نتونستم داده رو بگیرم. ساعت بعد دوباره تلاش می‌کنم."
        )
        raise RuntimeError("Could not fetch funding rate data.")

    message = build_message(data)
    print(message)
    send_telegram(message)


if __name__ == "__main__":
    main()
