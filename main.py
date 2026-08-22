import os
import requests
import anthropic

def get_sentiment_analysis():
    client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY"))
    prompt = "لطفا یک تحلیل کوتاه، مفید و سریع از وضعیت و سنتیمنت کلی بازار بیت‌کوین (BTC) ارائه بده. پاسخ به زبان فارسی، خلاصه‌شده و شامل بولت‌پوینت‌های کاربردی باشد."
    
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    response = requests.post(url, json=payload)
    print("Telegram Response:", response.text)

if __name__ == "__main__":
    try:
        report = get_sentiment_analysis()
        send_telegram(report)
    except Exception as e:
        print("Error:", str(e))
        send_telegram(f"خطا در دریافت تحلیل: {str(e)}")
