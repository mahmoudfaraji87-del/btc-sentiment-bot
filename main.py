"""
BTC Sentiment Tracker Bot
--------------------------
Reads the "What Is Your Current BTC Sentiment?" pie-chart widget from
https://www.coinglass.com/LongShortRatio and sends the 5 percentages
(Very Bullish, Bullish, Neutral, Bearish, Very Bearish) to Telegram.

STRATEGY (in order of preference):
  1. Try a direct JSON API call (fastest, cheapest, most reliable) --
     you must fill in COINGLASS_SENTIMENT_ENDPOINT below after finding
     it in your browser's DevTools > Network tab (see instructions in chat).
  2. Fallback: use a scraping/unlocker API (ScraperAPI) to render the
     page through a non-datacenter IP and bypass Cloudflare, then parse
     the rendered HTML.

Required GitHub Actions secrets:
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
  SCRAPERAPI_KEY        (free tier: https://www.scraperapi.com/ -- 1000 req/month)
Optional:
  COINGLASS_SENTIMENT_ENDPOINT   (fill in once you find the real JSON endpoint)
  ANTHROPIC_API_KEY     (if set, Claude is used to parse the percentages out of the
                         rendered page instead of fragile regex -- far more robust
                         to Coinglass changing its page layout)
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

LOG_FILE = "data/sentiment_log.csv"
LOG_HEADER = ["timestamp_utc", "very_bullish", "bullish", "neutral", "bearish", "very_bearish",
              "btc_price_usd", "eth_price_usd"]

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# --- Fill this in after inspecting the Network tab in your browser ---
# Example shape (guess, verify yourself):
# COINGLASS_SENTIMENT_ENDPOINT = "https://fapi.coinglass.com/api/xxx/sentiment"
COINGLASS_SENTIMENT_ENDPOINT = os.environ.get("COINGLASS_SENTIMENT_ENDPOINT", "")

TARGET_URL = "https://www.coinglass.com/LongShortRatio"

LABELS = ["Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish"]


def try_direct_json():
    """Attempt 1: call the real underlying JSON endpoint directly (no browser needed)."""
    if not COINGLASS_SENTIMENT_ENDPOINT:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": TARGET_URL,
        "Accept": "application/json, text/plain, */*",
    }
    try:
        r = requests.get(COINGLASS_SENTIMENT_ENDPOINT, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        # NOTE: adjust these keys once you see the real JSON shape.
        return {
            "Very Bullish": data.get("veryBullish"),
            "Bullish": data.get("bullish"),
            "Neutral": data.get("neutral"),
            "Bearish": data.get("bearish"),
            "Very Bearish": data.get("veryBearish"),
        }
    except Exception as e:
        print(f"[direct_json] failed: {e}", file=sys.stderr)
        return None


def try_scraperapi_render():
    """Attempt 2: render the page via ScraperAPI (non-datacenter IP, handles Cloudflare),
    then parse the percentages out of the rendered HTML.
    Retries a few times and enables ScraperAPI's premium proxy pool, since
    Coinglass has strong anti-bot protection that plain datacenter render
    requests sometimes fail against (transient 500s)."""
    if not SCRAPERAPI_KEY:
        print("[scraperapi] no SCRAPERAPI_KEY set, skipping", file=sys.stderr)
        return None
    api_url = "https://api.scraperapi.com/"
    base_params = {
        "api_key": SCRAPERAPI_KEY,
        "url": TARGET_URL,
        "render": "true",     # renders JS, needed for this widget
        "premium": "true",    # use premium/residential proxy pool for tougher sites
    }
    last_error = None
    for attempt in range(1, 4):  # up to 3 tries
        try:
            r = requests.get(api_url, params=base_params, timeout=120)
            r.raise_for_status()
            result = parse_percentages_from_html(r.text)
            if result is not None:
                return result
            last_error = "parsed 0/5 labels from rendered HTML"
        except Exception as e:
            last_error = str(e)
        print(f"[scraperapi] attempt {attempt} failed: {last_error}", file=sys.stderr)
        if attempt < 3:
            time.sleep(5 * attempt)  # simple backoff: 5s, 10s
    return None


def parse_with_claude(page_text: str):
    """Ask Claude to extract the 5 sentiment percentages from the page text.
    Far more robust than regex against Coinglass changing its page layout --
    Claude reads it the way a human would instead of matching exact patterns."""
    if not ANTHROPIC_API_KEY:
        return None
    prompt = (
        "Below is the text content of a webpage. Find the 'What Is Your Current "
        "BTC Sentiment?' section and extract the percentage for each of these "
        "five categories: Very Bullish, Bullish, Neutral, Bearish, Very Bearish.\n\n"
        "Reply with ONLY a JSON object, no other text, in exactly this shape:\n"
        '{"Very Bullish": <int>, "Bullish": <int>, "Neutral": <int>, '
        '"Bearish": <int>, "Very Bearish": <int>}\n\n'
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
        # Claude might wrap the JSON in ```json fences despite instructions; strip them.
        reply_text = re.sub(r"^```(json)?|```$", "", reply_text.strip(), flags=re.MULTILINE).strip()
        data = json.loads(reply_text)
        if all(label in data for label in LABELS):
            return {label: int(data[label]) for label in LABELS}
        print(f"[claude-parse] missing labels in response: {data}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[claude-parse] failed: {e}", file=sys.stderr)
        return None


def parse_percentages_from_html(html: str):
    """Find each sentiment label in the rendered HTML and grab the % next to it.
    Tries Claude first (robust to layout changes), falls back to regex.

    NOTE (regex fallback): "Bullish" and "Bearish" are substrings of "Very Bullish" /
    "Very Bearish", so a plain search for "Bullish" would incorrectly match inside
    "Very Bullish" and steal its percentage. We match "Very X" first, then for plain
    "Bullish"/"Bearish" require that "Very " does NOT precede them (negative lookbehind).
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")

    claude_result = parse_with_claude(text)
    if claude_result is not None:
        return claude_result

    results = {}
    for label in LABELS:
        if label in ("Bullish", "Bearish"):
            # negative lookbehind: not preceded by "Very "
            pattern = re.compile(r"(?<!Very )\b" + re.escape(label) + r"\b[^\d]{0,40}?(\d{1,3})\s*%")
        else:
            pattern = re.compile(re.escape(label) + r"[^\d]{0,40}?(\d{1,3})\s*%")
        m = pattern.search(text)
        if m:
            results[label] = int(m.group(1))
    if len(results) == len(LABELS):
        return results
    print(f"[parse] only found {len(results)}/{len(LABELS)} labels", file=sys.stderr)
    return None


def current_timestamp_str() -> str:
    """Gregorian date + time, both UTC and Sweden local (UTC+1 winter / UTC+2 summer
    handled automatically is not available without extra deps, so we show UTC and
    label it clearly -- Telegram already shows each message's own local arrival time
    too, but this makes the *data's* timestamp explicit and unambiguous)."""
    now_utc = datetime.now(timezone.utc)
    return now_utc.strftime("%Y-%m-%d %H:%M UTC")


def send_telegram(results: dict, btc_price=None, eth_price=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    price_lines = ""
    if btc_price is not None or eth_price is not None:
        price_lines = (
            f"💵 BTC: ${btc_price:,.2f}\n" if btc_price is not None else ""
        ) + (
            f"💵 ETH: ${eth_price:,.2f}\n" if eth_price is not None else ""
        ) + "\n"

    message = (
        "📊 پایش ساعتی وضعیت بازار (BTC Sentiment)\n"
        f"🕒 {current_timestamp_str()}\n\n"
        f"{price_lines}"
        f"🟢 Very Bullish: {results.get('Very Bullish', '؟')}%\n"
        f"🟢 Bullish: {results.get('Bullish', '؟')}%\n"
        f"⚪ Neutral: {results.get('Neutral', '؟')}%\n"
        f"🔴 Bearish: {results.get('Bearish', '؟')}%\n"
        f"🔴 Very Bearish: {results.get('Very Bearish', '؟')}%"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
    resp.raise_for_status()
    print("Telegram message sent.")


def send_failure_notice():
    """Let the user know the bot ran but couldn't fetch data this hour,
    instead of staying silent (silence looks like the bot is broken)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    message = (
        "⚠️ پایش ساعتی بازار (BTC Sentiment)\n"
        f"🕒 {current_timestamp_str()}\n\n"
        "این ساعت نتونستم داده رو از Coinglass بگیرم (احتمالاً به‌خاطر "
        "محافظت ضد-ربات سایت). ربات هنوز فعاله و ساعت بعد دوباره تلاش می‌کنه."
    )
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=15)
    except Exception as e:
        print(f"[send_failure_notice] also failed to notify: {e}", file=sys.stderr)


def get_prices():
    """Fetch current BTC and ETH prices from Binance's free public API (no key needed).
    Returns (btc_price, eth_price) or (None, None) on failure."""
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


def append_to_log(results: dict, btc_price, eth_price):
    """Append this run's data as one row to a CSV file in the repo, so months of
    hourly data build up into a single structured file ready for later analysis
    (Excel, pandas, or asking Claude to analyze it directly)."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(LOG_HEADER)
        writer.writerow([
            current_timestamp_str(),
            results.get("Very Bullish", ""),
            results.get("Bullish", ""),
            results.get("Neutral", ""),
            results.get("Bearish", ""),
            results.get("Very Bearish", ""),
            btc_price if btc_price is not None else "",
            eth_price if eth_price is not None else "",
        ])
    print(f"Logged row to {LOG_FILE}")


def main():
    results = try_direct_json()
    if results is None:
        print("Direct JSON endpoint unavailable/failed, falling back to ScraperAPI render...")
        results = try_scraperapi_render()

    if results is None:
        send_failure_notice()
        raise RuntimeError(
            "Could not obtain sentiment data from either method. "
            "Check COINGLASS_SENTIMENT_ENDPOINT and SCRAPERAPI_KEY, "
            "or the page structure may have changed."
        )

    btc_price, eth_price = get_prices()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    append_to_log(results, btc_price, eth_price)
    send_telegram(results, btc_price, eth_price)


if __name__ == "__main__":
    main()
