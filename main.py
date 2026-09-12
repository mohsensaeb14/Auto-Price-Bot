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

# کاراکتر کنترل راست به چپ (RLM) برای اجبار تلگرام به نمایش RTL
RLM = "\u200f"


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

    response = requests.get(API_URL, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


# =========================================================
# پیدا کردن آیتم موردنظر
# =========================================================

def find_item(items, target_name):
    if not items:
        return None

    for item in items:
        name = str(item.get("name", "")).strip()
        if name == target_name:
            return item

    for item in items:
        name = str(item.get("name", "")).strip()
        if target_name in name:
            return item

    return None


# =========================================================
# فرمت قیمت و تغییرات
# =========================================================

def format_price(price, is_ounce=False):
    try:
        value = float(price)
        if is_ounce:
            return f"${value:,.2f}"
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return "—"


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
# بخش قیمت خودروها
# =========================================================

IRANJIB_CAR_URL = "https://www.iranjib.ir/showgroup/45/%D9%82%DB%8C%D9%85%D8%AA-%D8%AE%D9%88%D8%AF%D8%B1%D9%88-%D8%AA%D9%88%D9%84%DB%8C%D8%AF-%D8%AF%D8%A7%D8%AE%D9%84/"


def normalize_text(value):
    value = str(value or "")
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    value = value.translate(translation)
    return " ".join(value.replace("‌", " ").replace("ي", "ی").replace("ك", "ک").split())


def parse_toman(value):
    if value is None:
        return None
    text = normalize_text(value).replace(",", "").replace("٬", "")
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def format_toman(value):
    number = parse_toman(value)
    if number is None:
        return str(value).strip() if value not in (None, "") else "—"
    return to_persian_number(f"{number:,}")


def format_price_difference(factory, market):
    factory_value = parse_toman(factory)
    market_value = parse_toman(market)

    if factory_value is None or market_value is None:
        return "—"

    difference = market_value - factory_value
    sign = "+" if difference > 0 else ""
    return to_persian_number(f"{sign}{difference:,}")


def get_car_prices():
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
        for row in all_rows:
            if len(row) < 4:
                continue
            row_name = normalize_text(row[0])
            if row_name in normalized_aliases:
                return row

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
                market = row[1]
                factory = row[2]
                change = row[3]
            else:
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
    cells = [[
        {"text": RLM + "نام خودرو", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "قیمت کارخانه", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "قیمت بازار", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "تفاوت بازار و کارخانه", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "تغییرات", "is_header": True, "align": "right", "valign": "middle"},
    ]]

    for car in cars:
        cells.append([
            {"text": RLM + car["name"], "align": "right", "valign": "middle"},
            {"text": RLM + car["factory"], "align": "right", "valign": "middle"},
            {"text": RLM + car["market"], "align": "right", "valign": "middle"},
            {"text": RLM + car["difference"], "align": "right", "valign": "middle"},
            {"text": RLM + car["change"], "align": "right", "valign": "middle"},
        ])

    return {
        "type": "table",
        "cells": cells,
        "is_bordered": True,
        "is_striped": True,
        "is_compact": True,
    }


# =========================================================
# جدول ارزش ذاتی طلای ۱۸ عیار و حباب
# =========================================================

TROY_OUNCE_GRAMS = 31.1034768
GOLD_18K_PURITY = 0.75


def build_gold_intrinsic_table(data):
    gold_list = data.get("gold", [])
    currency_list = data.get("currency", [])
    all_items = gold_list + currency_list

    gold_18 = find_item(all_items, "طلای 18 عیار")
    dollar = find_item(all_items, "دلار")
    ounce = find_item(all_items, "انس طلا")

    if not gold_18 or not dollar or not ounce:
        return None

    try:
        market_price = float(gold_18.get("price"))
        dollar_price = float(dollar.get("price"))
        ounce_price = float(ounce.get("price"))

        # ارزش ذاتی هر گرم طلای ۱۸ عیار:
        # (انس جهانی × دلار ÷ 31.1034768) × 0.75
        intrinsic_price = (
            ounce_price * dollar_price / TROY_OUNCE_GRAMS
        ) * GOLD_18K_PURITY

        bubble = market_price - intrinsic_price
        bubble_percent = (bubble / intrinsic_price) * 100

        sign = "+" if bubble > 0 else ""
        bubble_text = (
            f"{to_persian_number(f'{sign}{bubble:,.0f}')} تومان"
            f" ({to_persian_number(f'{sign}{bubble_percent:.2f}')}%)"
        )

        # ستون «دلار محاسباتی» عمداً حذف شده است.
        cells = [[
            {"text": RLM + "قیمت ذاتی طلا ۱۸", "is_header": True, "align": "right", "valign": "middle"},
            {"text": RLM + "مقدار حباب", "is_header": True, "align": "right", "valign": "middle"},
        ], [
            {"text": RLM + to_persian_number(f"{intrinsic_price:,.0f}") + " تومان", "align": "right", "valign": "middle"},
            {"text": RLM + bubble_text, "align": "right", "valign": "middle"},
        ]]

        return {
            "type": "table",
            "cells": cells,
            "is_bordered": True,
            "is_striped": False,
            "is_compact": True,
        }

    except (ValueError, TypeError, ZeroDivisionError):
        return None


# =========================================================
# حمایت و مقاومت طلا و دلار
# =========================================================

# منبع تکنیکال:
# TGJU - سطوح کلاسیک روزانه
# دلار: https://www.tgju.org/profile/price_dollar_rl/indicator
# طلا:  https://www.tgju.org/profile/geram18/indicator
#
# TGJU قیمت را به ریال اعلام می‌کند؛ پس از استخراج، بر ۱۰ تقسیم می‌شود.
# سپس اختلاف قیمت جاری TGJU با قیمت جاری BRSAPI محاسبه و کل سطوح
# به همان اندازه جابه‌جا می‌شوند. بنابراین مبنای تکنیکال خارجی حفظ
# می‌شود ولی اعداد نهایی دقیقاً با فید قیمت خودمان هم‌تراز می‌شوند.

TECHNICAL_URLS = {
    "دلار": "https://www.tgju.org/profile/price_dollar_rl/indicator",
    "طلا": "https://www.tgju.org/profile/geram18/indicator",
}

# آخرین snapshot معتبر که در صورت عدم دسترسی TGJU به عنوان fallback استفاده می‌شود.
# مقادیر منبع به ریال هستند و بعداً به تومان تبدیل می‌شوند.
TECHNICAL_FALLBACK = {
    "دلار": {
        "current": 2359750,
        "support": [2345500, 2331250, 2323900],
        "resistance": [2367100, 2374450, 2388700],
    },
    "طلا": {
        "current": 241814000,
        "support": [240728000, 239642000, 238170000],
        "resistance": [243286000, 244758000, 245844000],
    },
}


def _normalize_digits(value):
    value = str(value or "")
    return value.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _extract_number(value):
    text = _normalize_digits(value).replace(",", "").replace("٬", "").replace(" ", "")
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _fetch_tgju_levels(kind):
    """
    استخراج سطوح Classic از صفحه اندیکاتور TGJU.
    خروجی به ریال است:
      current, support=[S1,S2,S3], resistance=[R1,R2,R3]
    """
    url = TECHNICAL_URLS[kind]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    html = response.text

    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_tr = False
            self.in_cell = False
            self.row = []
            self.rows = []

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self.in_tr = True
                self.row = []
            elif tag in ("td", "th") and self.in_tr:
                self.in_cell = True

        def handle_data(self, data):
            if self.in_cell:
                self.row.append(data.strip())

        def handle_endtag(self, tag):
            if tag in ("td", "th"):
                self.in_cell = False
            elif tag == "tr" and self.in_tr:
                if self.row:
                    self.rows.append([x for x in self.row if x])
                self.in_tr = False

    parser = TableParser()
    parser.feed(html)

    result = {
        "current": None,
        "support": [None, None, None],
        "resistance": [None, None, None],
    }

    # نرخ فعلی
    import re
    current_patterns = [
        r"نرخ فعلی[^0-9۰-۹]*(?:[:：])?[^0-9۰-۹]*([0-9۰-۹,٬]+)",
        r"نرخ فعلی::?[^0-9۰-۹]*([0-9۰-۹,٬]+)",
    ]
    for pattern in current_patterns:
        match = re.search(pattern, html)
        if match:
            result["current"] = _extract_number(match.group(1))
            break

    # ردیف‌های جدول Classic
    for row in parser.rows:
        joined = " ".join(row)
        normalized = _normalize_digits(joined)

        m = re.search(r"حمایت\s*([123])", normalized)
        if m and len(row) >= 2:
            level = int(m.group(1))
            value = _extract_number(row[1])
            if value is not None:
                result["support"][level - 1] = value
            continue

        m = re.search(r"مقاومت\s*([123])", normalized)
        if m and len(row) >= 2:
            level = int(m.group(1))
            value = _extract_number(row[1])
            if value is not None:
                result["resistance"][level - 1] = value

    if (
        result["current"] is None
        or any(v is None for v in result["support"])
        or any(v is None for v in result["resistance"])
    ):
        raise ValueError(f"سطوح تکنیکال {kind} از TGJU به طور کامل استخراج نشد.")

    return result


def get_support_resistance(data):
    """
    سطوح کلاسیک TGJU را می‌گیرد و با قیمت جاری BRSAPI هم‌تراز می‌کند.

    اگر قیمت جاری منبع خارجی C_src و قیمت جاری BRSAPI برابر C_ours باشد:
        level_final = level_src + (C_ours - C_src)

    این روش باعث می‌شود فاصله سطوح از مبنای تکنیکال حفظ شود،
    اما مرکز سطوح با قیمت واقعی API خودمان منطبق باشد.
    """
    all_items = data.get("gold", []) + data.get("currency", [])
    gold_18 = find_item(all_items, "طلای 18 عیار")
    dollar = find_item(all_items, "دلار")

    if not gold_18 or not dollar:
        return None

    ours = {
        "طلا": float(gold_18.get("price")),
        "دلار": float(dollar.get("price")),
    }

    levels = {}

    for kind in ("طلا", "دلار"):
        try:
            source = _fetch_tgju_levels(kind)
        except Exception as exc:
            print(f"هشدار: دریافت سطوح {kind} از TGJU ناموفق بود: {exc}")
            source = TECHNICAL_FALLBACK[kind]

        # تبدیل ریال به تومان
        source_current_toman = source["current"] / 10.0
        delta = ours[kind] - source_current_toman

        supports = [
            round((value / 10.0) + delta)
            for value in source["support"]
        ]
        resistances = [
            round((value / 10.0) + delta)
            for value in source["resistance"]
        ]

        # مرتب‌سازی نهایی برای اطمینان از S1 < S2 < S3 و R1 < R2 < R3
        supports = sorted(supports, reverse=True)
        resistances = sorted(resistances)

        levels[kind] = {
            "support": supports,
            "resistance": resistances,
        }

    return levels


def build_support_resistance_table(data):
    levels = get_support_resistance(data)
    if not levels:
        return None

    def fmt(value):
        return RLM + to_persian_number(f"{int(value):,}")

    cells = [[
        {"text": RLM + "سطح", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "سطح ۱", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "سطح ۲", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "سطح ۳", "is_header": True, "align": "right", "valign": "middle"},
    ]]

    cells.append([
        {"text": RLM + "مقاومت طلا", "align": "right", "valign": "middle"},
        {"text": fmt(levels["طلا"]["resistance"][0]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["طلا"]["resistance"][1]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["طلا"]["resistance"][2]), "align": "right", "valign": "middle"},
    ])

    cells.append([
        {"text": RLM + "مقاومت دلار", "align": "right", "valign": "middle"},
        {"text": fmt(levels["دلار"]["resistance"][0]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["دلار"]["resistance"][1]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["دلار"]["resistance"][2]), "align": "right", "valign": "middle"},
    ])

    cells.append([
        {"text": RLM + "حمایت طلا", "align": "right", "valign": "middle"},
        {"text": fmt(levels["طلا"]["support"][0]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["طلا"]["support"][1]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["طلا"]["support"][2]), "align": "right", "valign": "middle"},
    ])

    cells.append([
        {"text": RLM + "حمایت دلار", "align": "right", "valign": "middle"},
        {"text": fmt(levels["دلار"]["support"][0]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["دلار"]["support"][1]), "align": "right", "valign": "middle"},
        {"text": fmt(levels["دلار"]["support"][2]), "align": "right", "valign": "middle"},
    ])

    return {
        "type": "table",
        "cells": cells,
        "is_bordered": True,
        "is_striped": False,
        "is_compact": True,
    }


# =========================================================
# تاریخ شمسی
# =========================================================

def get_persian_datetime():
    tehran_tz = pytz.timezone("Asia/Tehran")
    now = datetime.now(tehran_tz)
    jalali = jdatetime.datetime.fromgregorian(datetime=now)

    months = {
        1: "فروردین", 2: "اردیبهشت", 3: "خرداد", 4: "تیر",
        5: "مرداد", 6: "شهریور", 7: "مهر", 8: "آبان",
        9: "آذر", 10: "دی", 11: "بهمن", 12: "اسفند",
    }

    day = to_persian_number(jalali.day)
    hour = to_persian_number(now.strftime("%H"))
    minute = to_persian_number(now.strftime("%M"))
    month = months[jalali.month]

    return f"{RLM}بروز رسانی: {day} {month}   {hour}:{minute}"


# =========================================================
# ساخت جدول Rich Message تلگرام
# =========================================================

def build_table(data):
    gold_list = data.get("gold", [])
    currency_list = data.get("currency", [])
    all_items = gold_list + currency_list

    targets = [
        {"key": "دلار تتر", "label": "تتر 💸", "is_ounce": False},
        {"key": "دلار", "label": "دلار 💵", "is_ounce": False},
        {"key": "طلای 18 عیار", "label": "طلای ۱۸ عیار 🪙", "is_ounce": False},
        {"key": "سکه امامی", "label": "سکه امامی 🌕", "is_ounce": False},
        {"key": "انس طلا", "label": "انس جهانی 🌍", "is_ounce": True},
    ]

    cells = [[
        {"text": RLM + "عنوان", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "قیمت", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "تغییرات", "is_header": True, "align": "right", "valign": "middle"},
    ]]

    for target in targets:
        item = find_item(all_items, target["key"])
        if not item:
            continue

        price = format_price(item.get("price"), target["is_ounce"])
        change = format_api_change(item.get("change_percent", 0))

        cells.append([
            {"text": RLM + target["label"], "align": "right", "valign": "middle"},
            {"text": RLM + price, "align": "right", "valign": "middle"},
            {"text": RLM + change, "align": "right", "valign": "middle"},
        ])

    return {
        "type": "table",
        "cells": cells,
        "is_bordered": True,
        "is_striped": True,
        "is_compact": False,
    }


# =========================================================
# ارسال Rich Message به تلگرام
# =========================================================

def send_telegram_rich(data):
    date_text = get_persian_datetime()
    table = build_table(data)
    gold_intrinsic_table = build_gold_intrinsic_table(data)
    support_resistance_table = build_support_resistance_table(data)
    car_prices = get_car_prices()

    blocks = [
        {
            "type": "heading",
            "text": RLM + "🧬 قیمت‌های لحظه‌ای بازار",
            "size": 2,
        },
        {
            "type": "heading",
            "text": date_text,
            "size": 4,
        },
        table,
        gold_intrinsic_table if gold_intrinsic_table else {
            "type": "table",
            "cells": [[
                {"text": RLM + "اطلاعات ارزش ذاتی طلا در دسترس نیست", "is_header": True, "align": "right", "valign": "middle"},
            ]],
            "is_bordered": True,
            "is_striped": False,
            "is_compact": True,
        },
        support_resistance_table if support_resistance_table else {
            "type": "table",
            "cells": [[
                {"text": RLM + "اطلاعات حمایت و مقاومت در دسترس نیست", "is_header": True, "align": "right", "valign": "middle"},
            ]],
            "is_bordered": True,
            "is_striped": False,
            "is_compact": True,
        },
        {
            "type": "details",
            "summary": RLM + "🚗 قیمت خودروها",
            "is_open": False,
            "blocks": [
                {
                    "type": "heading",
                    "text": RLM + "🇮🇷 ایرانخودرو",
                    "size": 4,
                },
                build_car_table(car_prices["ایرانخودرو"]),
                {
                    "type": "details",
                    "summary": RLM + "🚙 سایپا",
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
        "is_rtl": True,
    }

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

    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendRichMessage"

    payload = {
        "chat_id": CHANNEL_ID,
        "rich_message": json.dumps(rich_message, ensure_ascii=False),
        "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
    }

    response = requests.post(telegram_url, data=payload, timeout=30)
    response.raise_for_status()
    return response.json()


# =========================================================
# اجرای اصلی
# =========================================================

def main():
    print("دریافت اطلاعات از API...")
    data = get_data()
    print("ارسال Rich Message به تلگرام...")
    result = send_telegram_rich(data)
    if result.get("ok"):
        print("پیام با موفقیت ارسال شد.")


if __name__ == "__main__":
    main()
