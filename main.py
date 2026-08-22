import os
import requests

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    response = requests.post(url, json=payload)
    print("Telegram Response:", response.text)

if __name__ == "__main__":
    send_telegram("تست ربات: ارتباط با موفقیت برقرار شد!")
