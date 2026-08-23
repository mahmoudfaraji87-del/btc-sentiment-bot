import os
import requests

def get_coinglass_sentiment():
    # استفاده از Endpoints اصلی کوین‌گلس همراه با هدرهای مرورگر واقعی
    url = "https://api.coinglass.com/api/support/sentiment/btc"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.coinglass.com/LongShortRatio"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and "data" in data:
                s = data["data"]
                return True, s
            return False, f"داده یافت نشد: {response.text[:100]}"
        else:
            return False, f"خطای سرور سایت (کد {response.status_code})"
    except Exception as e:
        return False, f"خطای اتصال: {str(e)}"

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("خطا: TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID تنظیم نشده است.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        res = requests.post(url, json=payload, timeout=10)
        print("نتیجه ارسال به تلگرام:", res.status_code, res.text)
    except Exception as e:
        print("خطا در ارسال تلگرام:", e)

if __name__ == "__main__":
    success, result = get_coinglass_sentiment()
    
    if success:
        report = (
            "📊 **پایش ساعتی سنتیمنت بیت‌کوین (Coinglass)**\n\n"
            f"🟢 Very Bullish: {result.get('veryBullish', 0)}%\n"
            f"🟢 Bullish: {result.get('bullish', 0)}%\n"
            f"⚪ Neutral: {result.get('neutral', 0)}%\n"
            f"🔴 Bearish: {result.get('bearish', 0)}%\n"
            f"🔴 Very Bearish: {result.get('veryBearish', 0)}%"
        )
        send_telegram(report)
    else:
        # ارسال گزارش خطا به تلگرام برای عیب‌یابی مستقیم
        error_msg = f"⚠️ **خطا در دریافت اطلاعات نمودار:**\n\n{result}"
        send_telegram(error_msg)
