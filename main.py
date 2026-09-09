import requests
import pytz
import jdatetime
import json
from datetime import datetime


# =========================================================
# تنظیمات
# =========================================================

BOT_TOKEN = "8805039197:AAG2qy6S2ArkjHszmFYVNeSpaYcufLTLMR0"
CHANNEL_ID = "@iranpricenow"

API_URL = (
    "https://api.brsapi.ir/Market/Gold_Currency.php?key=BupMHVpmxnEXDXaKJF7KtN9uKZxd7GCL"
)


# =========================================================
# تبدیل اعداد انگلیسی به فارسی
# =========================================================

def to_persian_number(value):
    if value is None:
        return ""

    value = str(value)

    english = "0123456789"
    persian = "۰۱۲۳۴۵۶۷۸۹"

    translation_table = str.maketrans(english, persian)

    return value.translate(translation_table)


# =========================================================
# دریافت اطلاعات از API
# =========================================================

def get_data():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    response = requests.get(
        API_URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# پیدا کردن آیتم موردنظر
# =========================================================

def find_item(items, target_name):

    if not items:
        return None

    # ابتدا تطبیق دقیق نام
    for item in items:

        name = str(item.get("name", "")).strip()

        if name == target_name:
            return item

    # در صورت پیدا نشدن، تطبیق بخشی
    for item in items:

        name = str(item.get("name", "")).strip()

        if target_name in name:
            return item

    return None


# =========================================================
# فرمت قیمت
# =========================================================

def format_price(price, is_ounce=False):

    try:

        value = float(price)

        if is_ounce:

            # قیمت انس جهانی
            return f"${value:,.2f}"

        # قیمت‌های بازار ایران
        return f"{int(value):,}"

    except (ValueError, TypeError):

        return "—"


# =========================================================
# فرمت درصد تغییرات
# =========================================================

def format_api_change(change_percent):

    try:

        value = float(change_percent)

        if value > 0:

            return f"▲ {value:.2f}%"

        elif value < 0:

            return f"▼ {abs(value):.2f}%"

        else:

            return "━ 0.00%"

    except (ValueError, TypeError):

        return "—"


# =========================================================
# تاریخ شمسی
# =========================================================

def get_persian_datetime():

    tehran_tz = pytz.timezone("Asia/Tehran")

    now = datetime.now(tehran_tz)

    jalali = jdatetime.datetime.fromgregorian(
        datetime=now
    )

    months = {
        1: "فروردین",
        2: "اردیبهشت",
        3: "خرداد",
        4: "تیر",
        5: "مرداد",
        6: "شهریور",
        7: "مهر",
        8: "آبان",
        9: "آذر",
        10: "دی",
        11: "بهمن",
        12: "اسفند",
    }

    day = to_persian_number(jalali.day)

    hour = to_persian_number(now.strftime("%H"))

    minute = to_persian_number(now.strftime("%M"))

    month = months[jalali.month]

    return (
        f"آخرین به‌روزرسانی: "
        f"{day} {month} "
        f"ساعت {hour}:{minute} دقیقه"
    )


# =========================================================
# ساخت جدول Rich Message تلگرام
# =========================================================

def build_table(data):

    gold_list = data.get("gold", [])
    currency_list = data.get("currency", [])

    all_items = gold_list + currency_list

    # -----------------------------------------------------
    # آیتم‌های موردنظر
    # -----------------------------------------------------

    targets = [

        {
            "key": "دلار تتر",
            "label": "تتر 💸",
            "is_ounce": False,
        },

        {
            "key": "دلار",
            "label": "دلار 💵",
            "is_ounce": False,
        },

        {
            "key": "طلای 18 عیار",
            "label": "طلای ۱۸ عیار 🪙",
            "is_ounce": False,
        },

        {
            "key": "سکه امامی",
            "label": "سکه امامی 🌕",
            "is_ounce": False,
        },

        {
            "key": "انس طلا",
            "label": "انس جهانی 🌍",
            "is_ounce": True,
        },
    ]

    # -----------------------------------------------------
    # هدر جدول
    # -----------------------------------------------------

    cells = [

        [
            {
                "text": "عنوان",
                "is_header": True,
                "align": "right",
                "valign": "middle",
            },

            {
                "text": "قیمت",
                "is_header": True,
                "align": "center",
                "valign": "middle",
            },

            {
                "text": "تغییرات",
                "is_header": True,
                "align": "center",
                "valign": "middle",
            },
        ]

    ]

    # -----------------------------------------------------
    # ردیف‌های جدول
    # -----------------------------------------------------

    for target in targets:

        item = find_item(
            all_items,
            target["key"]
        )

        if not item:
            print(
                f"WARNING: آیتم پیدا نشد: {target['key']}"
            )

            continue

        price = format_price(
            item.get("price"),
            target["is_ounce"]
        )

        # مهم:
        # API از change_percent استفاده می‌کند
        change = format_api_change(
            item.get("change_percent", 0)
        )

        row = [

            {
                "text": target["label"],
                "align": "right",
                "valign": "middle",
            },

            {
                "text": price,
                "align": "center",
                "valign": "middle",
            },

            {
                "text": change,
                "align": "center",
                "valign": "middle",
            },

        ]

        cells.append(row)

    # -----------------------------------------------------
    # ساخت Rich Table
    # -----------------------------------------------------

    table = {

        "type": "table",

        "cells": cells,

        # کادر دور جدول
        "is_bordered": True,

        # رنگ‌بندی ردیف‌های یکی در میان
        "is_striped": True,

        # جدول فشرده نباشد
        "is_compact": False,
    }

    return table


# =========================================================
# ارسال Rich Message به تلگرام
# =========================================================

def send_telegram_rich(data):

    date_text = get_persian_datetime()

    table = build_table(data)

    # -----------------------------------------------------
    # محتوای پیام
    # -----------------------------------------------------

    blocks = [

        {
            "type": "heading",
            "text": "🧬 قیمت‌های لحظه‌ای بازار",
            "size": 2,
        },

        {
            "type": "paragraph",
            "text": date_text,
        },

        table,

    ]

    rich_message = {

        "blocks": blocks,

        # راست‌چین و RTL
        "is_rtl": True,
    }

    # -----------------------------------------------------
    # فقط دکمه دوم
    # -----------------------------------------------------

    reply_markup = {

        "inline_keyboard": [

            [

                {
                    "text": "📊 قیمت بروز ارز و خودرو",
                    "url": "https://t.me/iranpricenow",
                }

            ]

        ]

    }

    # -----------------------------------------------------
    # Telegram API
    # -----------------------------------------------------

    telegram_url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendRichMessage"
    )

    payload = {

        "chat_id": CHANNEL_ID,

        "rich_message": json.dumps(
            rich_message,
            ensure_ascii=False
        ),

        "reply_markup": json.dumps(
            reply_markup,
            ensure_ascii=False
        ),
    }

    response = requests.post(
        telegram_url,
        data=payload,
        timeout=30
    )

    # -----------------------------------------------------
    # بررسی پاسخ
    # -----------------------------------------------------

    print("Telegram status:", response.status_code)

    try:

        result = response.json()

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2
            )
        )

    except Exception:

        print(response.text)

    response.raise_for_status()

    return response.json()


# =========================================================
# اجرای اصلی
# =========================================================

def main():

    print("========================================")
    print("Telegram Gold/Currency Bot")
    print("========================================")

    try:

        print("دریافت اطلاعات از API...")

        data = get_data()

        print("اطلاعات API با موفقیت دریافت شد.")

        print("ارسال Rich Message به تلگرام...")

        result = send_telegram_rich(data)

        if result.get("ok"):

            print(
                "پیام با موفقیت ارسال شد."
            )

        else:

            print(
                "خطا در ارسال پیام:"
            )

            print(result)

    except requests.exceptions.Timeout:

        print(
            "ERROR: زمان اتصال به API به پایان رسید."
        )

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: خطای ارتباطی: {e}"
        )

    except Exception as e:

        print(
            f"ERROR: خطای غیرمنتظره: {e}"
        )


# =========================================================
# Start
# =========================================================

if __name__ == "__main__":
    main()
