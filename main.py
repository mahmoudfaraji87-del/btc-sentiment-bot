import os
import time
import requests

def get_coinglass_long_short_ratio():
    # استفاده از API مستقیم دریافت نسبت Long/Short نمودار اصلی
    timestamp = int(time.time() * 1000)
    url = f"https://open-api.coinglass.com/api/pro/v1/futures/longShort_chart?symbol=BTC&interval=1h&_t={timestamp}"
    
    # آدرس دوم پشتیبان مستقیم سایت
    backup_url = f"https://html.coinglass.com/api/futures/longShortRate?symbol=BTC&timeType=3&_t={timestamp}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Cache-Control": "no-cache"
    }
    
    try:
        # درخواست اولیه
        res = requests.get(backup_url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if data.get("success") and "data" in data:
                d = data["data"]
                # در صورتی که دیتا شامل لیست زمان‌بندی باشد، آخرین مقدار (زنده) را می‌گیرد
                if isinstance(d, list) and len(d) > 0:
                    latest = d[-1]
                    long_rate = latest.get("longRate", latest.get("longRatio", 0))
                    short_rate = latest.get("shortRate", latest.get("shortRatio", 0))
                    return True, float(long_rate), float(short_rate)
                elif isinstance(d, dict):
                    long_rate = d.get("longRate", d.get("longRatio", 0))
                    short_rate = d.get("shortRate", d.get("shortRatio", 0))
                    return True, float(long_rate), float(short_rate)
                    
    except Exception as e:
        print("Error fetching backup API:", e)
        
    return False, 0, 0

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
    success, long_p, short_p = get_coinglass_long_short_ratio()
    current_time = time.strftime("%H:%M:%S UTC")

    if success and (long_p > 0 or short_p > 0):
        # گرد کردن درصدها تا ۲ رقم اعشار
        long_val = f"{long_p:.2f}%"
        short_val = f"{short_p:.2f}%"
        
        report = (
            f"📊 **پایش آنلاین نسبت Long/Short بیت‌کوین**\n"
            f"⏰ زمان بروزرسانی: `{current_time}`\n\n"
            f"🟢 **Long:** {long_val}\n"
            f"🔴 **Short:** {short_val}"
        )
        send_telegram(report)
    else:
        # در صورت عدم دریافت داده، پیام هشدار ساده ارسال می‌شود
        send_telegram(f"⚠️ **خطا در دریافت اطلاعات زنده نمودار**\n⏰ `{current_time}`")
