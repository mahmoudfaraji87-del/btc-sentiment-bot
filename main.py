import os
import time
import requests

def get_coinglass_sentiment():
    # اضافه کردن پارامتر زمان لحظه‌ای برای جلوگیری از دریافت داده‌های کش‌شده (Cache-busting)
    timestamp = int(time.time() * 1000)
    url = f"https://fapi.coinglass.com/api/support/sentiment/btc?_t={timestamp}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "Origin": "https://www.coinglass.com",
        "Referer": "https://www.coinglass.com/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("success") and "data" in res_json:
                return True, res_json["data"]
            return False, f"خطای ساختار داده: {res_json}"
        return False, f"کد خطا: {response.status_code}"
    except Exception as e:
        return False, f"خطای اتصال: {str(e)}"

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("توکن یا چت‌آیدی ست نشده است.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("خطا در ارسال تلگرام:", e)

if __name__ == "__main__":
    success, data = get_coinglass_sentiment()
    
    if success and isinstance(data, dict):
        # دریافت زمان لحظه‌ای به ساعت UTC جهت اطمینان از به روز بودن
        current_time = time.strftime("%H:%M:%S UTC")
        
        very_bullish = data.get("veryBullish", 0)
        bullish = data.get("bullish", 0)
        neutral = data.get("neutral", 0)
        bearish = data.get("bearish", 0)
        very_bearish = data.get("veryBearish", 0)
        
        report = (
            f"📊 **پایش آنلاین سنتیمنت بیت‌کوین (Coinglass)**\n"
            f"⏰ زمان بروزرسانی: `{current_time}`\n\n"
            f"🟢 Very Bullish: {very_bullish}%\n"
            f"🟢 Bullish: {bullish}%\n"
            f"⚪ Neutral: {neutral}%\n"
            f"🔴 Bearish: {bearish}%\n"
            f"🔴 Very Bearish: {very_bearish}%"
        )
        send_telegram(report)
    else:
        send_telegram(f"⚠️ **خطا در دریافت اطلاعات:**\n\n{data}")
