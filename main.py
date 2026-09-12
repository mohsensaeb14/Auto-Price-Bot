import requests
import pytz
import jdatetime
import json
import os
import base64
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

        # «دلار محاسباتی» طبق درخواست حذف شده است.
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
            # Telegram Rich Message API has no numeric font-size field;
            # compact=True is the supported compact rendering mode.
            "is_compact": True,
        }

    except (ValueError, TypeError, ZeroDivisionError):
        return None


# =========================================================
# تاریخچه و محاسبه حمایت/مقاومت
# =========================================================

HISTORY_FILE = "market_history.json"
HISTORY_MAX_DAYS = 30
HISTORY_SAVE_INTERVAL = 60 * 60  # ذخیره حداکثر یک نمونه در هر ساعت


def _github_headers():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_history():
    """
    ابتدا از GitHub Actions repository خوانده می‌شود، در صورت نبودن
    دسترسی/توکن از فایل محلی استفاده می‌شود.
    """
    repo = os.getenv("GITHUB_REPOSITORY")
    token_headers = _github_headers()

    if repo and token_headers:
        branch = os.getenv("GITHUB_REF_NAME", "main")
        url = f"https://api.github.com/repos/{repo}/contents/{HISTORY_FILE}?ref={branch}"
        try:
            r = requests.get(url, headers=token_headers, timeout=15)
            if r.ok:
                content = base64.b64decode(r.json()["content"]).decode("utf-8")
                return json.loads(content)
        except Exception as exc:
            print(f"هشدار: خواندن تاریخچه از GitHub ناموفق بود: {exc}")

    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        print(f"هشدار: خواندن فایل تاریخچه ناموفق بود: {exc}")

    return {"gold": [], "dollar": []}


def _trim_history(history):
    cutoff = datetime.now(pytz.timezone("Asia/Tehran")).timestamp() - (
        HISTORY_MAX_DAYS * 86400
    )

    for key in ("gold", "dollar"):
        history[key] = [
            x for x in history.get(key, [])
            if float(x.get("ts", 0)) >= cutoff
        ]

    return history


def save_history(history):
    """
    فایل را محلی ذخیره می‌کند و در GitHub Actions در صورت وجود GITHUB_TOKEN
    آن را در repository نیز به‌روزرسانی می‌کند.
    """
    history = _trim_history(history)

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, separators=(",", ":"))

    repo = os.getenv("GITHUB_REPOSITORY")
    token_headers = _github_headers()

    if not repo or not token_headers:
        return

    branch = os.getenv("GITHUB_REF_NAME", "main")
    url = f"https://api.github.com/repos/{repo}/contents/{HISTORY_FILE}"
    content_b64 = base64.b64encode(
        json.dumps(history, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")

    try:
        current = requests.get(
            url, headers=token_headers, params={"ref": branch}, timeout=15
        )

        payload = {
            "message": "Update market history",
            "content": content_b64,
            "branch": branch,
        }

        if current.ok:
            payload["sha"] = current.json().get("sha")

        r = requests.put(url, headers=token_headers, json=payload, timeout=20)
        if not r.ok:
            print(f"هشدار: ذخیره تاریخچه در GitHub ناموفق بود: {r.text[:300]}")
    except Exception as exc:
        print(f"هشدار: خطا در ذخیره تاریخچه GitHub: {exc}")


def update_market_history(data):
    """
    از قیمت فعلی طلا و دلار نمونه می‌گیرد.
    برای جلوگیری از صدها رکورد تکراری، حداکثر یک نمونه در هر ساعت ذخیره می‌شود.
    """
    gold_list = data.get("gold", [])
    currency_list = data.get("currency", [])
    all_items = gold_list + currency_list

    gold = find_item(all_items, "طلای 18 عیار")
    dollar = find_item(all_items, "دلار")

    if not gold or not dollar:
        return load_history()

    try:
        gold_price = float(gold["price"])
        dollar_price = float(dollar["price"])
        api_ts = max(
            float(gold.get("time_unix") or 0),
            float(dollar.get("time_unix") or 0),
        )
        if api_ts <= 0:
            api_ts = datetime.now(pytz.timezone("Asia/Tehran")).timestamp()

        history = load_history()

        for key, price in (("gold", gold_price), ("dollar", dollar_price)):
            rows = history.setdefault(key, [])
            if rows and api_ts - float(rows[-1].get("ts", 0)) < HISTORY_SAVE_INTERVAL:
                continue

            rows.append({
                "ts": api_ts,
                "price": price,
            })

        history = _trim_history(history)
        save_history(history)
        return history

    except (ValueError, TypeError):
        return load_history()


def _daily_ohlc(rows):
    """
    از نمونه‌های ذخیره‌شده، OHLC روزانه می‌سازد.
    """
    tz = pytz.timezone("Asia/Tehran")
    days = {}

    for row in rows:
        try:
            ts = float(row["ts"])
            price = float(row["price"])
            dt = datetime.fromtimestamp(ts, tz)
            day = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, KeyError, OSError):
            continue

        if day not in days:
            days[day] = {
                "high": price,
                "low": price,
                "close": price,
                "last_ts": ts,
            }
        else:
            days[day]["high"] = max(days[day]["high"], price)
            days[day]["low"] = min(days[day]["low"], price)
            if ts >= days[day]["last_ts"]:
                days[day]["close"] = price
                days[day]["last_ts"] = ts

    return days


def calculate_support_resistance(rows):
    """
    Pivot Point روزانه:
      P  = (H + L + C) / 3
      R1 = 2P - L
      R2 = P + H - L
      R3 = H + 2(P - L)
      S1 = 2P - H
      S2 = P - H + L
      S3 = L - 2(H - P)

    برای جلوگیری از استفاده از داده ناقص امروز، آخرین روز کاملِ قبل از امروز
    مبنای محاسبه قرار می‌گیرد.
    """
    daily = _daily_ohlc(rows)
    if len(daily) < 2:
        return None

    sorted_days = sorted(daily.keys())
    # آخرین روز را جاری در نظر می‌گیریم و روز قبل را مبنای Pivot قرار می‌دهیم.
    previous = daily[sorted_days[-2]]

    h = previous["high"]
    l = previous["low"]
    c = previous["close"]

    p = (h + l + c) / 3.0

    return {
        "resistance": [
            2 * p - l,
            p + h - l,
            h + 2 * (p - l),
        ],
        "support": [
            2 * p - h,
            p - h + l,
            l - 2 * (h - p),
        ],
        "based_on": sorted_days[-2],
    }


def format_level(value):
    if value is None:
        return "—"
    return RLM + to_persian_number(f"{value:,.0f}")


def build_support_resistance_table(history):
    gold_levels = calculate_support_resistance(history.get("gold", []))
    dollar_levels = calculate_support_resistance(history.get("dollar", []))

    cells = [[
        {"text": RLM + "عنوان", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "مقاومت سطح ۱", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "مقاومت سطح ۲", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "مقاومت سطح ۳", "is_header": True, "align": "right", "valign": "middle"},
    ]]

    if gold_levels:
        cells.append([
            {"text": RLM + "مقاومت طلا", "align": "right", "valign": "middle"},
            {"text": format_level(gold_levels["resistance"][0]), "align": "right", "valign": "middle"},
            {"text": format_level(gold_levels["resistance"][1]), "align": "right", "valign": "middle"},
            {"text": format_level(gold_levels["resistance"][2]), "align": "right", "valign": "middle"},
        ])
    else:
        cells.append([
            {"text": RLM + "مقاومت طلا", "align": "right", "valign": "middle"},
            {"text": "—", "align": "right", "valign": "middle"},
            {"text": "—", "align": "right", "valign": "middle"},
            {"text": "—", "align": "right", "valign": "middle"},
        ])

    if dollar_levels:
        cells.append([
            {"text": RLM + "مقاومت دلار", "align": "right", "valign": "middle"},
            {"text": format_level(dollar_levels["resistance"][0]), "align": "right", "valign": "middle"},
            {"text": format_level(dollar_levels["resistance"][1]), "align": "right", "valign": "middle"},
            {"text": format_level(dollar_levels["resistance"][2]), "align": "right", "valign": "middle"},
        ])
    else:
        cells.append([
            {"text": RLM + "مقاومت دلار", "align": "right", "valign": "middle"},
            {"text": "—", "align": "right", "valign": "middle"},
            {"text": "—", "align": "right", "valign": "middle"},
            {"text": "—", "align": "right", "valign": "middle"},
        ])

    return {
        "type": "table",
        "cells": cells,
        "is_bordered": True,
        "is_striped": False,
        "is_compact": True,
    }


def build_support_table(history):
    gold_levels = calculate_support_resistance(history.get("gold", []))
    dollar_levels = calculate_support_resistance(history.get("dollar", []))

    cells = [[
        {"text": RLM + "عنوان", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "حمایت سطح ۱", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "حمایت سطح ۲", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "حمایت سطح ۳", "is_header": True, "align": "right", "valign": "middle"},
    ]]

    for label, levels in (("حمایت طلا", gold_levels), ("حمایت دلار", dollar_levels)):
        cells.append([
            {"text": RLM + label, "align": "right", "valign": "middle"},
            {"text": format_level(levels["support"][0]) if levels else "—", "align": "right", "valign": "middle"},
            {"text": format_level(levels["support"][1]) if levels else "—", "align": "right", "valign": "middle"},
            {"text": format_level(levels["support"][2]) if levels else "—", "align": "right", "valign": "middle"},
        ])

    return {
        "type": "table",
        "cells": cells,
        "is_bordered": True,
        "is_striped": False,
        "is_compact": True,
    }


def build_support_resistance_section(history):
    """
    یک جدول واحد شامل مقاومت و حمایت، با همان فونت/فشردگی جدول حباب.
    """
    gold_levels = calculate_support_resistance(history.get("gold", []))
    dollar_levels = calculate_support_resistance(history.get("dollar", []))

    cells = [[
        {"text": RLM + "عنوان", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "سطح ۱", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "سطح ۲", "is_header": True, "align": "right", "valign": "middle"},
        {"text": RLM + "سطح ۳", "is_header": True, "align": "right", "valign": "middle"},
    ]]

    rows = [
        ("مقاومت طلا", gold_levels["resistance"] if gold_levels else None),
        ("مقاومت دلار", dollar_levels["resistance"] if dollar_levels else None),
        ("حمایت طلا", gold_levels["support"] if gold_levels else None),
        ("حمایت دلار", dollar_levels["support"] if dollar_levels else None),
    ]

    for label, levels in rows:
        cells.append([
            {"text": RLM + label, "align": "right", "valign": "middle"},
            {"text": format_level(levels[0]) if levels else "—", "align": "right", "valign": "middle"},
            {"text": format_level(levels[1]) if levels else "—", "align": "right", "valign": "middle"},
            {"text": format_level(levels[2]) if levels else "—", "align": "right", "valign": "middle"},
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
    history = update_market_history(data)
    support_resistance_table = build_support_resistance_section(history)
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
        {
            "type": "heading",
            "text": RLM + "📊 حمایت و مقاومت",
            "size": 4,
        },
        support_resistance_table,
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
