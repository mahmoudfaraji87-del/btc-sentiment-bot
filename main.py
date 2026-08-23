import os
import time
import requests

def get_coinglass_sentiment():
    # استفاده از ای‌پیوآی عمومی با تغییر پارامتر زمان برای جلوگیری از کش
    timestamp = int(time.time() * 1000)
    url = f"https://api.coinglass.com/api/support/sentiment/btc?_t={timestamp}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.coinglass.com/",
        "Origin": "https://www.coinglass.com"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            res = response.json()
            if res.get("success") and "data" in res:
                return True, res["data"]
    except Exception as e:
        print("Fetch error:", e)
        
    return False, None

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("خطا: تنظیمات تلگرام یافت نشد.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

if __name__ == "__main__":
    success, data = get_coinglass_sentiment()
    current_time = time.strftime("%H:%M:%S UTC")

    if success and data:
        very_bullish = data.get("veryBullish", 0)
        bullish = data.get("bullish", 0)
        neutral = data.get("neutral", 0)
        bearish = data.get("bearish", 0)
        very_bearish = data.get("veryBearish", 0)

        report = (
            f"📊 **پایش ساعتی سنتیمنت بیت‌کوین (Coinglass)**\n"
            f"⏰ زمان: `{current_time}`\n\n"
            f"🟢 Very Bullish: {very_bullish}%\n"
            f"🟢 Bullish: {bullish}%\n"
            f"⚪ Neutral: {neutral}%\n"
            f"🔴 Bearish: {bearish}%\n"
            f"🔴 Very Bearish: {very_bearish}%"
        )
        send_telegram(report)
    else:
        # اگر اطلاعات به هر دلیلی دریافت نشد، پیام هشدار ساده فرستاده می‌شود تا تلگرام قطع نشود
        send_telegram(f"⚠️ **عدم امکان دریافت اطلاعات از سرور کوین‌گلس**\n⏰ `{current_time}`")
