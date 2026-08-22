import os
import requests

def get_sentiment_analysis():
    # دریافت قیمت و دیتای زنده بیت‌کوین از کوین‌گکو
    url = "https://api.coingecko.com/api/v10/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
    res = requests.get(url).json()
    btc_data = res.get("bitcoin", {})
    price = btc_data.get("usd", "N/A")
    change_24h = round(btc_data.get("usd_24h_change", 0), 2)
    
    status = "📈 صعودی (Bullish)" if change_24h > 0 else "📉 نزولی (Bearish)"
    
    report = (
        f"📊 **گزارش لحظه‌ای سنتیمنت بیت‌کوین (BTC)**\n\n"
        f"💰 **قیمت فعلی:** ${price:,}\n"
        f"🔄 **تغییرات ۲۴ ساعت گذشته:** {change_24h}%\n"
        f"💡 **وضعیت کلی بازار:** {status}\n\n"
        f"🤖 *این گزارش به‌صورت خودکار توسط سیستم مانیتورینگ شما تولید شده است.*"
    )
    return report

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    response = requests.post(url, json=payload)
    print("Telegram Response:", response.text)

if __name__ == "__main__":
    try:
        report = get_sentiment_analysis()
        send_telegram(report)
    except Exception as e:
        print("Error:", str(e))
        send_telegram(f"خطا در اجرای برنامه: {str(e)}")
