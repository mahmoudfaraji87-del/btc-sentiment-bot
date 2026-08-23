import os
import requests
import json
import re

def get_coinglass_sentiment():
    # فراخوانی مستقیم صفحه با User-Agent مرورگر و لایه بای‌پاس
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    # آدرس مستقیم ای‌پي‌آی داده‌های سنتیمنت Coinglass
    urls = [
        "https://api.coinglass.com/api/support/sentiment/btc",
        "https://html.duckduckgo.com/html/"
    ]
    
    # تست دریافت مستقیم از endpoint اختصاصی
    try:
        req = requests.get("https://coinglass.com/LongShortRatio", headers=headers, timeout=12)
        text = req.text
        # استخراج داده‌های Sentiment از دل سورس HTML
        match = re.search(r'"veryBullish":(\d+).*?"bullish":(\d+).*?"neutral":(\d+).*?"bearish":(\d+).*?"veryBearish":(\d+)', text)
        if match:
            return {
                "very_bullish": match.group(1),
                "bullish": match.group(2),
                "neutral": match.group(3),
                "bearish": match.group(4),
                "very_bearish": match.group(5)
            }
    except Exception as e:
        print("HTML Regex fetch failed:", e)

    # API فال‌بک مستقیم با پارامترهای جدید
    try:
        api_url = "https://api.coinglass.com/api/support/sentiment/btc"
        res = requests.get(api_url, headers=headers, timeout=10).json()
        if res.get("data"):
            d = res["data"]
            return {
                "very_bullish": d.get("veryBullish", 0),
                "bullish": d.get("bullish", 0),
                "neutral": d.get("neutral", 0),
                "bearish": d.get("bearish", 0),
                "very_bearish": d.get("veryBearish", 0)
            }
    except Exception as e:
        print("Direct API failed:", e)

    return None

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    data = get_coinglass_sentiment()
    
    if data:
        report = (
            "📊 **BTC Sentiment (Coinglass)**\n\n"
            f"🟢 Very Bullish: {data['very_bullish']}%\n"
            f"🟢 Bullish: {data['bullish']}%\n"
            f"⚪ Neutral: {data['neutral']}%\n"
            f"🔴 Bearish: {data['bearish']}%\n"
            f"🔴 Very Bearish: {data['very_bearish']}%"
        )
        send_telegram(report)
    else:
        # اگر Cloudflare از سرور گیت‌هاب تمام مسیرها را بلوک کرد:
        # استفاده از روش Scraper Target
        try:
            r = requests.get("https://api.coingecko.com/api/v3/coins/bitcoin", timeout=10).json()
            up = r['sentiment_votes_up_percentage']
            down = r['sentiment_votes_down_percentage']
            alt_report = (
                "📊 **BTC Sentiment (صفحه جایگزین - Live)**\n\n"
                f"🟢 Bullish / مثبت: {up}%\n"
                f"🔴 Bearish / منفی: {down}%\n\n"
                f"*(Coinglass IP را محدود کرده است؛ در حال تغییر آی‌پی سرور...)*"
            )
            send_telegram(alt_report)
        except Exception as ex:
            send_telegram("⚠️ عدم امکان اتصال به سرور داده.")
