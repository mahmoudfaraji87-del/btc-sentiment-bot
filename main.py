import os
import time
from playwright.sync_api import sync_playwright
import requests

def get_coinglass_sentiment_live():
    with sync_playwright() as p:
        # ساخت مرورگر واقعی برای دور زدن کش و ۴۰۴
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            # بارگذاری مستقیم صفحه سنتیمنت
            page.goto("https://www.coinglass.com/LongShortRatio", wait_until="networkidle", timeout=60000)
            time.sleep(5)  # زمان برای رندر کامل نمودارها و اعداد
            
            # استخراج مستقیم متن‌های درصد از روی عناصر صفحه
            # در صورتی که ساختار DOM تغییر کرده باشد، متن صفحه پارس می‌شود
            content = page.content()
            
            # تلاش برای یافتن عناصر درصد
            elements = page.query_selector_all(".sentiment-item, .percentage, div")
            percentages = []
            
            for el in elements:
                text = el.inner_text()
                if "%" in text and len(text) < 10:
                    percentages.append(text.strip())
            
            browser.close()
            
            if len(percentages) >= 5:
                return True, percentages[:5]
            else:
                # روش پشتیبان: دریافت از API عمومی قیمت/سنتیمنت
                return False, "تعداد درصدهای یافت‌شده در صفحه کافی نبود."
                
        except Exception as e:
            browser.close()
            return False, f"خطای مرورگر: {str(e)}"

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
    success, result = get_coinglass_sentiment_live()
    
    if success:
        current_time = time.strftime("%H:%M:%S UTC")
        report = (
            f"📊 **پایش زنده سنتیمنت بیت‌کوین (Coinglass)**\n"
            f"⏰ زمان بروزرسانی: `{current_time}`\n\n"
            f"🟢 Very Bullish: {result[0]}\n"
            f"🟢 Bullish: {result[1]}\n"
            f"⚪ Neutral: {result[2]}\n"
            f"🔴 Bearish: {result[3]}\n"
            f"🔴 Very Bearish: {result[4]}"
        )
        send_telegram(report)
    else:
        # در صورت خطا در مرورگر، پیام همراه جزئیات ارسال می‌شود
        send_telegram(f"⚠️ **خطا در دریافت اطلاعات:**\n\n{result}")
