import os
import time
import requests

def get_market_sentiment():
    # دریافت داده‌های زنده و سنتیمنت بازار از سرویس پایدار
    url = "https://api.coingecko.com/api/v3/global"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            data = response.json().get("data", {})
            btc_dominance = data.get("market_cap_percentage", {}).get("btc", 0)
            eth_dominance = data.get("market_cap_percentage", {}).get("eth", 0)
            market_cap_change = data.get("market_cap_change_percentage_24h_usd", 0)
            
            return True, {
                "btc_dom": round(btc_dominance, 2),
                "eth_dom": round(eth_dominance, 2),
                "change": round(market_cap_change, 2)
            }
    except Exception as e:
        print("Error fetching data:", e)
        
    return False, None

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("خطا: توکن یا چت‌آیدی ست نشده است.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

if __name__ == "__main__":
    success, data = get_market_sentiment()
    current_time = time.strftime("%H:%M:%S UTC")

    if success and data:
        status_emoji = "🟢" if data["change"] >= 0 else "🔴"
        report = (
            f"📊 **پایش ساعتی وضعیت بازار**\n"
            f"⏰ زمان: `{current_time}`\n\n"
            f"🔹 دامیننس بیت‌کوین: `{data['btc_dom']}%`\n"
            f"🔹 دامیننس اتریوم: `{data['eth_dom']}%`\n"
            f"{status_emoji} تغییرات ۲۴ ساعته بازار: `{data['change']}%`"
        )
        send_telegram(report)
    else:
        # در صورت نبود داده، جهت جلوگیری از قطع پیام‌ها هشدار ساده فرستاده می‌شود
        send_telegram(f"⚠️ **خطا در دریافت اطلاعات زنده**\n⏰ `{current_time}`")
