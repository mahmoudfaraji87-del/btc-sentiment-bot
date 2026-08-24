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
"""

import os
import re
import sys
import json
import requests
from bs4 import BeautifulSoup

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SCRAPERAPI_KEY = os.environ.get("SCRAPERAPI_KEY")

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
    then parse the percentages out of the rendered HTML."""
    if not SCRAPERAPI_KEY:
        print("[scraperapi] no SCRAPERAPI_KEY set, skipping", file=sys.stderr)
        return None
    api_url = "https://api.scraperapi.com/"
    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": TARGET_URL,
        "render": "true",   # renders JS, needed for this widget
    }
    try:
        r = requests.get(api_url, params=params, timeout=90)
        r.raise_for_status()
        return parse_percentages_from_html(r.text)
    except Exception as e:
        print(f"[scraperapi] failed: {e}", file=sys.stderr)
        return None


def parse_percentages_from_html(html: str):
    """Find each sentiment label in the rendered HTML and grab the % next to it.

    NOTE: "Bullish" and "Bearish" are substrings of "Very Bullish" / "Very Bearish",
    so a plain search for "Bullish" would incorrectly match inside "Very Bullish"
    and steal its percentage. We match "Very X" first, then for plain "Bullish"/
    "Bearish" require that "Very " does NOT precede them (negative lookbehind).
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
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


def send_telegram(results: dict):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    message = (
        "📊 پایش ساعتی وضعیت بازار (BTC Sentiment)\n\n"
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


def main():
    results = try_direct_json()
    if results is None:
        print("Direct JSON endpoint unavailable/failed, falling back to ScraperAPI render...")
        results = try_scraperapi_render()

    if results is None:
        raise RuntimeError(
            "Could not obtain sentiment data from either method. "
            "Check COINGLASS_SENTIMENT_ENDPOINT and SCRAPERAPI_KEY, "
            "or the page structure may have changed."
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))
    send_telegram(results)


if __name__ == "__main__":
    main()
