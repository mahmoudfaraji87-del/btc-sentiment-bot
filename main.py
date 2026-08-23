import os
import json
import requests

STATE_FILE = "last_sentiment.json"

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

def load_last_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_current_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

if __name__ == "__main__":
    current_data = get_coinglass_sentiment()
    
    if current_data:
        last_data = load_last_state()
        
        if current_data != last_data:
            report = (
                "📊 **تغییر در سنتیمنت بیت‌کوین (Coinglass)**\n\n"
                f"🟢 Very Bullish: {current_data['very_bullish']}%\n"
                f"🟢 Bullish: {current_data['bullish']}%\n"
                f"⚪ Neutral: {current_data['neutral']}%\n"
                f"🔴 Bearish: {current_data['bearish']}%\n"
                f"🔴 Very Bearish: {current_data['very_bearish']}%"
            )
            send_telegram(report)
            save_current_state(current_data)
        else:
            print("داده‌ها تغییری نکرده‌اند.")
