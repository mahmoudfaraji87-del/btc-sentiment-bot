import os
import requests

def get_coinglass_data():
    # استفاده از API ساختاریافته‌ی هندبیل کوین‌گلس
    url = "https://fapi.coinglass.com/api/support/sentiment/btc"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.coinglass.com",
        "Referer": "https://www.coinglass.com/"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            res_json = response.json()
            if res_json.get("success") and "data" in res_json:
                return True, res_json["data"]
            return False, f"دیتا دریافت نشد: {res_json}"
        else:
            # اگر آدرس اول مسدود بود، تلاش با Endpoint جایگزین
            alt_url = "https://html.coinglass.com/api/index/sentiment"
            res_alt = requests.get(alt_url, headers=headers, timeout=15)
            if res_alt.status_code == 200:
                return True, res_alt.json().get("data", {})
                
            return False, f"خطای سرور کوین‌گلس (کد {response.status_code})"
    except Exception as e:
        return False, f"خطای ارتباط: {str(e)}"

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("خطا: توکن یا چت‌آیدی تنظیم نشده است.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("خطا در ارسال پیام به تلگرام:", e)

if __name__ == "__main__":
    success, data = get_coinglass_data()
    
    if success and isinstance(data, dict):
        very_bullish = data.get("veryBullish", data.get("vBullish", 0))
        bullish = data.get("bullish", 0)
        neutral = data.get("neutral", 0)
        bearish = data.get("bearish", 0)
        very_bearish = data.get("veryBearish", data.get("vBearish", 0))
        
        report = (
            "📊 **پایش ساعتی سنتیمنت بیت‌کوین (Coinglass)**\n\n"
            f"🟢 Very Bullish: {very_bullish}%\n"
            f"🟢 Bullish: {bullish}%\n"
            f"⚪ Neutral: {neutral}%\n"
            f"🔴 Bearish: {bearish}%\n"
            f"🔴 Very Bearish: {very_bearish}%"
        )
        send_telegram(report)
    else:
        # اگر باز هم مسدود بود، پیام خطا ارسال می‌شود
        send_telegram(f"⚠️ **خطا در اتصال به سایت:**\n\n{data}")
