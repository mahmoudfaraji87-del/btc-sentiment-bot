"""
Coinglass Liquidation Tracker (BTC + ETH + Market-Wide "All")
------------------------------------------------------------------
Reads two kinds of liquidation data:

1. Per-coin 24h totals, from:
     https://www.coinglass.com/liquidations/BTC
     https://www.coinglass.com/liquidations/ETH
   -> total 24h liquidation (USD), long USD, short USD, per coin.

2. Market-wide ("All" exchanges, all coins combined) totals across FOUR
   timeframes at once, from the single page:
     https://www.coinglass.com/liquidations
   -> for each of 1h / 4h / 12h / 24h: total, long, short (USD).
   This is NOT specific to any one exchange -- it's the aggregated
   "Total Liquidations" panel on that page.

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
    "BTC": "https://www.coinglass.com/liquidations/BTC",
    "ETH": "https://www.coinglass.com/liquidations/ETH",
}
MARKET_URL = "https://www.coinglass.com/liquidations"
TIMEFRAMES = ["1h", "4h", "12h", "24h"]

LOG_FILE = "data/liquidation_log.csv"
LOG_HEADER = [
    "timestamp_utc",
    "btc_total_24h_usd", "btc_long_usd", "btc_short_usd",
    "eth_total_24h_usd", "eth_long_usd", "eth_short_usd",
]
for tf in TIMEFRAMES:
    LOG_HEADER += [f"market_{tf}_total_usd", f"market_{tf}_long_usd", f"market_{tf}_short_usd"]
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


# ---------- Per-coin (BTC / ETH) parsing ----------

def parse_coin_with_claude(page_text: str, coin: str):
    if not ANTHROPIC_API_KEY:
        return None
    prompt = (
        f"Below is the text content of the Coinglass '{coin} Liquidations' page. "
        "It states the total amount of USD liquidated across the network in the "
        "past 24 hours, and a breakdown of Long vs Short liquidations.\n\n"
        "Extract:\n"
        "- total_24h_usd: total 24h liquidation amount in USD as a plain number "
        "(convert B=billion, M=million, K=thousand, e.g. '$120.5M' -> 120500000)\n"
        "- long_usd: the portion from Long position liquidations, as a plain number\n"
        "- short_usd: the portion from Short position liquidations, as a plain number\n\n"
        "Reply with ONLY a JSON object, no other text, in exactly this shape:\n"
        '{"total_24h_usd": <number>, "long_usd": <number>, "short_usd": <number>}\n\n'
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
        fields = ["total_24h_usd", "long_usd", "short_usd"]
        if all(f in data for f in fields):
            return {f: float(data[f]) for f in fields}
        print(f"[claude-parse:{coin}] missing fields: {data}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[claude-parse:{coin}] failed: {e}", file=sys.stderr)
        return None


def parse_coin_with_regex(page_text: str, coin: str):
    lower = page_text.lower()
    idx = lower.find("liquidat")
    if idx == -1:
        print(f"[regex:{coin}] word 'liquidat' not found on page", file=sys.stderr)
        return None
    window = page_text[max(0, idx - 200): idx + 2000]
    matches = re.findall(r"\$?([\d.]+)\s*([BMK])\b", window)
    if len(matches) < 3:
        print(f"[regex:{coin}] not enough dollar amounts found: {matches}", file=sys.stderr)
        return None
    multiplier = {"B": 1e9, "M": 1e6, "K": 1e3}
    values = [float(v) * multiplier[u] for v, u in matches[:3]]
    return {"total_24h_usd": values[0], "long_usd": values[1], "short_usd": values[2]}


def get_coin_liquidation(coin: str, url: str):
    html = fetch_rendered_html(url)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    result = parse_coin_with_claude(text, coin)
    if result is not None:
        return result
    return parse_coin_with_regex(text, coin)


# ---------- Market-wide "All" parsing (1h/4h/12h/24h at once) ----------

def parse_market_with_claude(page_text: str):
    if not ANTHROPIC_API_KEY:
        return None
    prompt = (
        "Below is the text content of the Coinglass 'Liquidations' overview page "
        "(market-wide, all exchanges and all coins combined -- NOT specific to any "
        "single exchange). It has a 'Total Liquidations' panel with FOUR timeframes: "
        "'1h Rekt', '4h Rekt', '12h Rekt', '24h Rekt'. Each timeframe shows a total "
        "USD amount, plus a Long amount and a Short amount.\n\n"
        "Extract all four timeframes. Reply with ONLY a JSON object, no other text, "
        "in exactly this shape (numbers as plain numbers, converting B/M/K, e.g. "
        "'$11.95M' -> 11950000):\n"
        '{"1h": {"total": <number>, "long": <number>, "short": <number>}, '
        '"4h": {"total": <number>, "long": <number>, "short": <number>}, '
        '"12h": {"total": <number>, "long": <number>, "short": <number>}, '
        '"24h": {"total": <number>, "long": <number>, "short": <number>}}\n\n'
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
        for tf in TIMEFRAMES:
            if tf not in data or not all(k in data[tf] for k in ("total", "long", "short")):
                print(f"[claude-parse:market] missing {tf}: {data}", file=sys.stderr)
                return None
            result[tf] = {k: float(data[tf][k]) for k in ("total", "long", "short")}
        return result
    except Exception as e:
        print(f"[claude-parse:market] failed: {e}", file=sys.stderr)
        return None


def parse_market_with_regex(page_text: str):
    """Fallback: find 'Xh Rekt' labels and grab the next 3 dollar amounts
    (total, long, short) after each. Fragile -- breaks if layout changes."""
    result = {}
    for tf in TIMEFRAMES:
        label = f"{tf} Rekt"
        idx = page_text.find(label)
        if idx == -1:
            print(f"[regex:market] could not find label '{label}'", file=sys.stderr)
            return None
        window = page_text[idx: idx + 300]
        matches = re.findall(r"\$?([\d.]+)\s*([BMK])\b", window)
        if len(matches) < 3:
            print(f"[regex:market] not enough matches for {tf}: {matches}", file=sys.stderr)
            return None
        multiplier = {"B": 1e9, "M": 1e6, "K": 1e3}
        values = [float(v) * multiplier[u] for v, u in matches[:3]]
        result[tf] = {"total": values[0], "long": values[1], "short": values[2]}
    return result


def get_market_liquidations():
    html = fetch_rendered_html(MARKET_URL)
    if html is None:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    result = parse_market_with_claude(text)
    if result is not None:
        return result
    return parse_market_with_regex(text)


# ---------- Shared helpers ----------

def format_usd(value: float) -> str:
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    if value >= 1e3:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


def current_timestamp_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def append_to_log(coin_data, market_data, btc_price, eth_price):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_exists = os.path.isfile(LOG_FILE)
    row = [current_timestamp_str()]
    for coin in ("BTC", "ETH"):
        d = coin_data.get(coin)
        if d is None:
            row.extend(["", "", ""])
        else:
            row.extend([d["total_24h_usd"], d["long_usd"], d["short_usd"]])
    for tf in TIMEFRAMES:
        d = market_data.get(tf) if market_data else None
        if d is None:
            row.extend(["", "", ""])
        else:
            row.extend([d["total"], d["long"], d["short"]])
    row.append(btc_price if btc_price is not None else "")
    row.append(eth_price if eth_price is not None else "")
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(LOG_HEADER)
        writer.writerow(row)
    print(f"Logged row to {LOG_FILE}")


def build_message(coin_data, market_data, btc_price, eth_price):
    lines = [
        "💥 پایش لیکویید شدن‌ها",
        f"🕒 {current_timestamp_str()}",
        "",
    ]
    if btc_price is not None:
        lines.append(f"💵 BTC: ${btc_price:,.2f}")
    if eth_price is not None:
        lines.append(f"💵 ETH: ${eth_price:,.2f}")
    if btc_price is not None or eth_price is not None:
        lines.append("")

    lines.append("===== به‌تفکیک ارز (۲۴ ساعته) =====")
    for coin in ("BTC", "ETH"):
        d = coin_data.get(coin)
        lines.append(f"— {coin} —")
        if d is None:
            lines.append("⚠️ داده در دسترس نبود")
        else:
            lines.append(f"مجموع: {format_usd(d['total_24h_usd'])}")
            lines.append(f"🟢 Long: {format_usd(d['long_usd'])}")
            lines.append(f"🔴 Short: {format_usd(d['short_usd'])}")
    lines.append("")

    lines.append("===== کل بازار (All، همه‌ی صرافی‌ها) =====")
    if market_data is None:
        lines.append("⚠️ داده در دسترس نبود")
    else:
        for tf in TIMEFRAMES:
            d = market_data.get(tf)
            if d is None:
                continue
            lines.append(f"— {tf} —")
            lines.append(f"مجموع: {format_usd(d['total'])} | 🟢 {format_usd(d['long'])} | 🔴 {format_usd(d['short'])}")
    return "\n".join(lines).strip()


def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
    resp.raise_for_status()
    print("Telegram message sent.")


def main():
    coin_data = {}
    for coin, url in COINS.items():
        coin_data[coin] = get_coin_liquidation(coin, url)

    market_data = get_market_liquidations()
    btc_price, eth_price = get_prices()

    message = build_message(coin_data, market_data, btc_price, eth_price)
    print(message)
    append_to_log(coin_data, market_data, btc_price, eth_price)

    if all(v is None for v in coin_data.values()) and market_data is None:
        send_telegram(
            "⚠️ پایش لیکویید شدن‌ها\n"
            f"🕒 {current_timestamp_str()}\n\n"
            "این ساعت نتونستم هیچ داده‌ای بگیرم. ساعت بعد دوباره تلاش می‌کنم."
        )
        raise RuntimeError("Could not fetch any liquidation data.")

    send_telegram(message)


if __name__ == "__main__":
    main()
