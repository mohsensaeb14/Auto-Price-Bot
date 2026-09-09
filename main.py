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




IRANJIB_CAR_URL = "https://www.iranjib.ir/showgroup/45/%D9%82%DB%8C%D9%85%D8%AA-%D8%AE%D9%88%D8%AF%D8%B1%D9%88-%D8%AA%D9%88%D9%84%DB%8C%D8%AF-%D8%AF%D8%A7%D8%AE%D9%84/"


def normalize_text(value):
    """یکسان‌سازی اعداد و فاصله/نیم‌فاصله برای تطبیق نام خودروها."""
    value = str(value or "")
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    value = value.translate(translation)
    return " ".join(value.replace("‌", " ").replace("ي", "ی").replace("ك", "ک").split())


def parse_toman(value):
    """تبدیل قیمت درج‌شده در ایران‌جیب به عدد تومان؛ مقادیر متنی None برمی‌گردانند."""
    if value is None:
        return None
    text = normalize_text(value).replace(",", "").replace("٬", "")
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def format_toman(value):
    """نمایش قیمت به‌صورت عدد فارسی با جداکننده سه‌رقمی."""
    number = parse_toman(value)
    if number is None:
        return str(value).strip() if value not in (None, "") else "—"
    return to_persian_number(f"{number:,}")


def format_price_difference(factory, market):
    """قیمت بازار منهای قیمت کارخانه."""
    factory_value = parse_toman(factory)
    market_value = parse_toman(market)

    if factory_value is None or market_value is None:
        return "—"

    difference = market_value - factory_value
    sign = "+" if difference > 0 else ""
    return to_persian_number(f"{sign}{difference:,}")


def get_car_prices():
    """دریافت قیمت خودروهای منتخب از جدول ایران‌جیب."""
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_tr = False
            self.in_td = False
            self.rows = []
            self.row = []
            self.cell = ""

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.in_tr = True
                self.row = []
            elif tag in ("td", "th") and self.in_tr:
                self.in_td = True
                self.cell = ""

        def handle_data(self, data):
            if self.in_td:
                self.cell += data

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self.in_td:
                self.row.append(" ".join(self.cell.split()))
                self.in_td = False
            elif tag == "tr" and self.in_tr:
                if self.row:
                    self.rows.append(self.row)
                self.in_tr = False

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    response = requests.get(IRANJIB_CAR_URL, headers=headers, timeout=30)
    response.raise_for_status()

    parser = TableParser()
    parser.feed(response.text)

    # نام نمایشی در ربات -> نام/نام‌های موجود در جدول ایران‌جیب
    targets = {
        "ایرانخودرو": [
            ("۲۰۷ دنده‌ای برقی", ["پژو 207 دنده‌ای (برقی)"]),
            ("۲۰۷ دنده‌ای پانا", ["پژو 207 دنده‌ای پانوراما"]),
            ("۲۰۷ اتومات فلز", ["پژو 207 اتوماتیک"]),
            ("۲۰۷ اتومات پانا", ["پژو 207 اتوماتیک پانوراما"]),
            ("۲۰۷ TU3", ["پژو 207 موتور TU3"]),
            ("سورن XU7P فولادی", ["سورن XU7P (رینگ فولادی)"]),
            ("سورن TU5", ["سورن (TU5P)"]),
            ("سورن دوگانه کوچک", ["سورن پلاس دوگانه‌سوز (کپسول کوچک)", "سورن پلاس دوگانه سوز (کپسول کوچک)"]),
            ("سورن دوگانه بزرگ", ["سورن پلاس دوگانه‌سوز (کپسول بزرگ)", "سورن پلاس دوگانه سوز (کپسول بزرگ)"]),
            ("دنا MT6 قالپاق", ["دنا پلاس MT6 (رینگ فولادی)"]),
            ("دنا MT6 رینگ", ["دنا پلاس MT6"]),
            ("دنا اتوماتیک", ["دنا پلاس اتوماتیک"]),
            ("تارا دستی V1", ["تارا دستی V1"]),
            ("تارا اتومات V4", ["تارا اتوماتیک V4"]),
            ("تارا اتومات توربو", ["تارا اتوماتیک (توربو)"]),
            ("ریرا", ["ری را"]),
        ],
        "سایپا": [
            ("کوییک S", ["کوییک S"]),
            ("کوییک RS", ["کوییک RS"]),
            ("کوییک GXR", ["کوییک GXR"]),
            ("ساینا S", ["ساینا S"]),
            ("ساینا دوگانه", ["ساینا دوگانه سوز", "ساینا دوگانه‌سوز"]),
            ("سهند S", ["سهند S"]),
            ("اطلس S", ["اطلس S"]),
            ("اطلس G", ["اطلس G"]),
            ("اطلس GL", ["اطلس GL"]),
            ("سایپا 151 GX", ["سایپا 151 GX"]),
            ("شاهین G", ["شاهین G (سانروف)"]),
            ("شاهین اتو G", ["شاهین اتوماتیک G"]),
            ("شاهین اتو پلاس", ["شاهین اتوماتیک پلاس"]),
            ("زامیاد", ["زامیاد اکستند EX"]),
            ("زامیاد دوگانه", ["زامیاد اکستند EX (دوگانه‌سوز)", "زامیاد اکستند EX (دوگانه سوز)"]),
        ],
    }

    all_rows = parser.rows

    def find_row(aliases):
        normalized_aliases = [normalize_text(alias) for alias in aliases]

        # ابتدا تطبیق دقیق؛ این کار برای مدل‌هایی که نسخه رینگ/قالپاق دارند مهم است.
        for row in all_rows:
            if len(row) < 4:
                continue
            row_name = normalize_text(row[0])
            if row_name in normalized_aliases:
                return row

        # سپس تطبیق جزئی.
        for row in all_rows:
            if len(row) < 4:
                continue
            row_name = normalize_text(row[0])
            if any(alias in row_name for alias in normalized_aliases):
                return row

        return None

    result = {"ایرانخودرو": [], "سایپا": []}

    for company, company_targets in targets.items():
        for label, aliases in company_targets:
            row = find_row(aliases)

            if row:
                # ساختار ایران‌جیب: نام، قیمت بازار، قیمت کارخانه، تغییر
                market = row[1]
                factory = row[2]
                change = row[3]
            else:
                print(f"WARNING: خودرو پیدا نشد: {label}")
                market = factory = change = "—"

            result[company].append({
                "name": label,
                "factory": format_toman(factory),
                "market": format_toman(market),
                "difference": format_price_difference(factory, market),
                "change": change,
            })

    return result


def build_car_table(cars):
    """ساخت جدول قیمت خودرو با ستون تفاوت بازار و کارخانه."""
    # در حالت RTL، نام خودرو باید در سمت راست و اولین ستون دیداری باشد.
    cells = [[
        {"text": "نام خودرو", "is_header": True, "align": "right", "valign": "middle"},
        {"text": "قیمت کارخانه", "is_header": True, "align": "center", "valign": "middle"},
        {"text": "قیمت بازار", "is_header": True, "align": "center", "valign": "middle"},
        {"text": "تفاوت بازار و کارخانه", "is_header": True, "align": "center", "valign": "middle"},
        {"text": "تغییرات", "is_header": True, "align": "center", "valign": "middle"},
    ]]

    for car in cars:
        cells.append([
            {"text": car["name"], "align": "right", "valign": "middle"},
            {"text": car["factory"], "align": "center", "valign": "middle"},
            {"text": car["market"], "align": "center", "valign": "middle"},
            {"text": car["difference"], "align": "center", "valign": "middle"},
            {"text": car["change"], "align": "center", "valign": "middle"},
        ])

    return {
        "type": "table",
        "cells": cells,
        "direction": "rtl",
        "is_bordered": True,
        "is_striped": True,
        "is_compact": True,
    }

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

        "direction": "rtl",

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
    car_prices = get_car_prices()

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
            "type": "heading",
            "text": date_text,
            "size": 6,
        },

        table,

        {
            "type": "details",
            "summary": "🚗 قیمت خودروها",
            "is_open": False,
            "blocks": [
                {
                    "type": "heading",
                    "text": "🇮🇷 ایرانخودرو",
                    "size": 4,
                },
                build_car_table(car_prices["ایرانخودرو"]),
                {
                    "type": "details",
                    "summary": "🚙 سایپا",
                    "is_open": False,
                    "blocks": [
                        build_car_table(car_prices["سایپا"]),
                    ],
                },
            ],
        },

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
