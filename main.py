import os
import requests
import json

def get_coinglass_sentiment():
    # استفاده از پروکسی AllOrigins برای عبور از محدودیت Cloudflare
    target_url = "https://api.coinglass.com/api/support/sentiment/btc"
    proxy_url = f"https://api.allorigins.win/get?url={target_url}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        response = requests.get(proxy_url, headers=headers, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            # داده اصلی داخل کلید contents قرار دارد
            raw_data = json.loads(res_json.get("contents", "{}"))
            
            if raw_data.get("success") and "data" in raw_data:
                s = raw_data["data"]
                return {
                    "very_bullish": s.get("veryBullish", 0),
                    "bullish": s.get("bullish", 0),
                    "neutral": s.get("neutral", 0),
                    "bearish": s.get("bearish", 0),
                    "very_bearish": s.get("veryBearish", 0)
                }
    except Exception as e:
        print("Error fetching data:", e)
    
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
            "📊 **گزارش سنتیمنت بیت‌کوین (Coinglass)**\n\n"
            f"🟢 Very Bullish: {data['very_bullish']}%\n"
            f"🟢 Bullish: {data['bullish']}%\n"
            f"⚪ Neutral: {data['neutral']}%\n"
            f"🔴 Bearish: {data['bearish']}%\n"
            f"🔴 Very Bearish: {data['very_bearish']}%"
        )
        send_telegram(report)
    else:
        send_telegram("⚠️ دریافت اطلاعات با خطا مواجه شد. در حال بررسی مجدد...")
