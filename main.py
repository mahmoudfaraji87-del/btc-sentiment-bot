import os
import time
import re
from playwright.sync_api import sync_playwright
import requests

def get_coinglass_sentiment_fixed():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # تنظیم ابعاد مرورگر واقعی برای رندر کامل نمودارها
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://www.coinglass.com/LongShortRatio", wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            # رد کردن بنر کوکی در صورت وجود
            try:
                accept_btn = page.query_selector("button:has-text('Accept'), button:has-text('Agree')")
                if accept_btn:
                    accept_btn.click()
                    time.sleep(1)
            except Exception:
                pass

            # اسکرول اندک برای فعال‌شدن لود نمودارها
            page.evaluate("window.scrollBy(0, 300)")
            time.sleep(3)

            # استخراج تمام کارهای متنی درون کارت‌های درصد
            content_text = page.inner_text("body")
            
            browser.close()

            # الگوی استخراج درصدهای دقیق Long و Short
            # جستجوی درصدهای همراه با علامت %
            matches = re.findall(r'(\d+(?:\.\d+)?%)', content_text)
            
            if matches:
                return True, matches
            else:
                return False, "هیچ درصدی در صفحه پیدا نشد."

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
    success, result = get_coinglass_sentiment_fixed()
    current_time = time.strftime("%H:%M:%S UTC")

    if success:
        # نمایش 6 درصد اول استخراج‌شده از نمودار برای اطمینان
        formatted_rates = "\n".join([f"🔹 {rate}" for rate in result[:6]])
        report = (
            f"📊 **پایش آنلاین سنتیمنت (Coinglass)**\n"
            f"⏰ زمان بروزرسانی: `{current_time}`\n\n"
            f"{formatted_rates}"
        )
        send_telegram(report)
    else:
        send_telegram(f"⚠️ **خطا در دریافت اطلاعات:**\n\n{result}")
