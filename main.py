import os
import time
import json
from playwright.sync_api import sync_playwright
import requests

def get_coinglass_sentiment_exact():
    sentiment_data = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # شنود به پاسخ‌های شبکه برای پیدا کردن دیتای دقیق نمودار
        def handle_response(response):
            nonlocal sentiment_data
            try:
                if "sentiment" in response.url or "longRate" in response.url or "longShort" in response.url:
                    if response.status == 200:
                        json_data = response.json()
                        if isinstance(json_data, dict) and "data" in json_data:
                            sentiment_data = json_data["data"]
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            # باز کردن صفحه اصلی نمودار
            page.goto("https://www.coinglass.com/LongShortRatio", wait_until="networkidle", timeout=60000)
            time.sleep(6) # زمان دادن برای ثبت پاسخ شبکه

            # اگر از طریق شبکه دیتا گرفتیم
            if sentiment_data and isinstance(sentiment_data, dict):
                browser.close()
                return True, "network", sentiment_data

            # روش جایگزین مستقیم (خواندن متن دقیق کارت نمودار دایره‌ای)
            page.wait_for_selector("text=%", timeout=10000)
            
            # استخراج متن‌های داخل باکس اختصاصی سنتیمنت
            text_content = page.evaluate('''() => {
                let el = document.querySelector('.sentiment-box') || document.body;
                return el.innerText;
            }''')
            
            browser.close()
            return True, "dom", text_content

        except Exception as e:
            browser.close()
            return False, "error", str(e)

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
    success, mode, result = get_coinglass_sentiment_exact()
    current_time = time.strftime("%H:%M:%S UTC")

    if success:
        if mode == "network" and isinstance(result, dict):
            # فرمت‌دهی دیتای واقعی دریافت شده از API شبکه
            v_bull = result.get("veryBullish", result.get("h5Rate", 0))
            bull = result.get("bullish", result.get("h1Rate", 0))
            neutral = result.get("neutral", 0)
            bear = result.get("bearish", 0)
            v_bear = result.get("veryBearish", 0)
            
            report = (
                f"📊 **پایش آنلاین سنتیمنت بیت‌کوین (Coinglass)**\n"
                f"⏰ زمان بروزرسانی: `{current_time}`\n\n"
                f"🟢 Long / Bullish: {bull}%\n"
                f"🔴 Short / Bearish: {bear}%\n"
            )
            send_telegram(report)
        else:
            # اگر به صورت متن خام دریافت شد
            send_telegram(f"📊 **اطلاعات سنتیمنت ({current_time}):**\n\n{str(result)[:500]}")
    else:
        send_telegram(f"⚠️ **خطا در دریافت اطلاعات:**\n\n{result}")
