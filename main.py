import os
import json
import requests
from anthropic import Anthropic

CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = Anthropic(api_key=CLAUDE_API_KEY)
DB_FILE = "last_sentiment.json"

def get_coinglass_sentiment():
    url = "https://open-api.coinglass.com/public/v1/home/sentiment"
    headers = {"accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("data")
    except Exception as e:
        print(f"Error fetching data: {e}")
    return None

def load_previous_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return None

def save_current_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def main():
    current_data = get_coinglass_sentiment()
    if not current_data:
        return

    previous_data = load_previous_data()

    if current_data != previous_data:
        prompt = f"""
        تو یک تحلیل‌گر ارشد کریپتو هستی. سنتیمنت بیت‌کوین در Coinglass تغییر کرده.
        داده قبلی: {json.dumps(previous_data, ensure_ascii=False)}
        داده جدید: {json.dumps(current_data, ensure_ascii=False)}
        تغییرات را در ۳ جمله خلاصه کن و بگو چه سیگنالی برای بازار دارد.
        """

        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        analysis = response.content[0].text
        send_telegram(f"📊 **تغییر سنتیمنت BTC در Coinglass:**\n\n{analysis}")
        save_current_data(current_data)

if __name__ == "__main__":
    main()
