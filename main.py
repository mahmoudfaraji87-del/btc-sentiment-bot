import os
import requests

def get_coinglass_sentiment():
    url = "https://api.coinglass.com/api/support/sentiment/btc"
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9",
        "origin": "https://www.coinglass.com",
        "referer": "https://www.coinglass.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
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
        # ساختار جایگزین مستقیم در صورت مسدودی IP سرور گیت‌هاب
        send_telegram("⚠️ سرور Coinglass درخواست پایتون را مسدود کرد. در حال بازتنظیم اتصال...")
