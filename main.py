import os
import requests

def get_coinglass_sentiment():
    url = "https://api.coinglass.com/api/support/sentiment/btc"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.coinglass.com/LongShortRatio"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if data.get("success") and "data" in data:
            s = data["data"]
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
    res = requests.post(url, json=payload)
    print("Telegram Response:", res.text)

if __name__ == "__main__":
    data = get_coinglass_sentiment()
    if data:
        report = (
            "📊 **گزارش ساعتی سنتیمنت بیت‌کوین (Coinglass)**\n\n"
            f"🟢 Very Bullish: {data['very_bullish']}%\n"
            f"🟢 Bullish: {data['bullish']}%\n"
            f"⚪ Neutral: {data['neutral']}%\n"
            f"🔴 Bearish: {data['bearish']}%\n"
            f"🔴 Very Bearish: {data['very_bearish']}%"
        )
        send_telegram(report)
    else:
        send_telegram("⚠️ خطا در دریافت اطلاعات جدید از سایت Coinglass.")
