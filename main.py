import requests
import pytz
import jdatetime
import json
import os
import re
import statistics
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path


# =========================================================
# تنظیمات
# =========================================================

BOT_TOKEN = "8805039197:AAG2qy6S2ArkjHszmFYVNeSpaYcufLTLMR0"
CHANNEL_ID = "@iranpricenow"

# منابع جدید قیمت‌ها
TABANGOHOAR_URL = "https://tabangohar.com/"
TETHER_URL = "https://arzdigital.com/coins/tether/"
BONBAST_URL = "https://bonbast.com/"

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
# دریافت مستقیم قیمت‌ها از منابع جدید
# =========================================================

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8",
    "Cache-Control": "no-cache",
}


class PlainTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = " ".join((data or "").split())
        if value:
            self.parts.append(value)


class HTMLTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = []
        self.cell_parts = []
        self.in_row = False
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data):
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            self.row.append(" ".join(" ".join(self.cell_parts).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False


def _normalise_digits(value):
    return str(value or "").translate(str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
    ))


def _number(value):
    text = _normalise_digits(value).replace(",", "").replace("٬", "").replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _fetch_text(url):
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()
    parser = PlainTextParser()
    parser.feed(response.text)
    return " ".join(parser.parts), response.text


def _fetch_tether_from_arzdigital():
    """گرفتن قیمت تتر از arzdigital.com"""
    text, _ = _fetch_text(TETHER_URL)
    # جستجوی قیمت تتر بر اساس ساختار صفحه ارزدیجیتال
    match = re.search(r"([0-9۰-۹,٬]+)\s*تومان", text)
    if not match:
        # روش جایگزین با الگوهای متداول
        match = re.search(r"قیمت\s*تتر.*?([0-9۰-۹,٬]{4,})", text)
    
    if match:
        price = _number(match.group(1))
        if price and price > 1000:
            return {"name": "دلار تتر", "price": price, "change_percent": 0.0}
            
    # Fallback از طریق پارسر جدول در صورت نیاز
    response = requests.get(TETHER_URL, headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()
    parser = HTMLTableParser()
    parser.feed(response.text)
    for row in parser.rows:
        joined = " ".join(row)
        num = _number(joined)
        if num and 10000 < num < 200000:
            return {"name": "دلار تتر", "price": num, "change_percent": 0.0}

    raise ValueError("قیمت تتر از ارزدیجیتال پیدا نشد")


def _fetch_bonbast_data():
    """گرفتن دلار، سکه امامی و انس جهانی از bonbast.com"""
    response = requests.get(BONBAST_URL, headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()
    parser = HTMLTableParser()
    parser.feed(response.text)

    dollar_price = None
    sekeh_price = None
    ounce_price = None

    for row in parser.rows:
        joined = " ".join(row).lower()
                
        # جستجوی دلار (USD)
        if "usd" in joined and not dollar_price:
            for cell in row:
                val = _number(cell)
                if val and val > 1000:
                    dollar_price = val
                    break
                    
        # جستجوی سکه امامی (Emami / Azadi)
        if ("emami" in joined or "1sekeh" in joined or "سکه" in joined) and not sekeh_price:
            for cell in row:
                val = _number(cell)
                if val and val > 1000000:
                    sekeh_price = val
                    break

        # جستجوی اونس (Ounce)
        if "ounce" in joined and not ounce_price:
            for cell in row:
                val = _number(cell)
                if val and val > 500:
                    ounce_price = int(val) # بدون اعشار
                    break

    # روش جایگزین با Regex مستقیم روی متن صفحه در صورت کامل نبودن جدول
    text, _ = _fetch_text(BONBAST_URL)
    
    results = {}
    if dollar_price:
        results["دلار"] = {"name": "دلار", "price": dollar_price, "change_percent": 0.0}
    if sekeh_price:
        results["سکه امامی"] = {"name": "سکه امامی", "price": sekeh_price / 10 if sekeh_price > 100000000 else sekeh_price, "change_percent": 0.0} # تبدیل ریال به تومان اگر نیاز باشد
    if ounce_price:
        results["انس طلا"] = {"name": "انس طلا", "price": float(int(ounce_price)), "change_percent": 0.0}

    if not results.get("دلار") or not results.get("انس طلا"):
        raise ValueError("برخی اطلاعات از bonbast.com کامل دریافت نشد")

    return results


def _fetch_18k_from_tabangohar():
    """استخراج قیمت واقعی هر گرم طلای ۱۸ از تابان گوهر (بدون تغییر دستکاری‌شده)"""
    text, html = _fetch_text(TABANGOHOAR_URL)
    normalized = _normalise_digits(text)
    stripped_html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", html, flags=re.I | re.S)
    stripped_html = re.sub(r"<[^>]+>", " ", stripped_html)
    stripped_html = _normalise_digits(stripped_html)
    stripped_html = re.sub(r"\s+", " ", stripped_html)

    sources = (normalized, stripped_html)
    patterns = (
        r"گرم\s*(?:18|۱۸)\s*(?:عیار\s*)?(?:تهران\s*)?[:：\-]?\s*([0-9][0-9,٬]{3,})\s*(?:تومان|ریال)?",
        r"قیمت\s*یک\s*گرم\s*(?:18|۱۸)\s*طلا.*?([0-9][0-9,٬]{3,})\s*(?:تومان|ریال)?",
    )

    candidates = []
    for source in sources:
        for pattern in patterns:
            for match in re.finditer(pattern, source, flags=re.IGNORECASE):
                raw = match.group(1)
                value = _number(raw)
                if value is None or value <= 0:
                    continue
                if 20_000 <= value < 100_000:
                    value *= 1000
                elif 10_000_000 <= value <= 100_000_000:
                    pass
                else:
                    continue
                candidates.append(value)
        if candidates:
            break

    if not candidates:
        raise ValueError("قیمت معتبر گرم طلای ۱۸ در صفحه تابان گوهر پیدا نشد")

    value = statistics.median(candidates)
    return {"name": "طلای 18 عیار", "price": value, "change_percent": 0.0}


def get_data():
    gold = []
    currency = []
    errors = []

    # دریافت طلا از تابان گوهر
    try:
        gold.append(_fetch_18k_from_tabangohar())
        print("دریافت موفق: طلای ۱۸ عیار / تابان گوهر", flush=True)
    except Exception as exc:
        errors.append(f"طلای ۱۸ عیار: {exc}")

    # دریافت تتر از ارزدیجیتال
    try:
        currency.append(_fetch_tether_from_arzdigital())
        print("دریافت موفق: تتر / ارزدیجیتال", flush=True)
    except Exception as exc:
        errors.append(f"تتر: {exc}")

    # دریافت دلار، سکه و انس از بن‌بست
    try:
        bonbast_data = _fetch_bonbast_data()
        if "دلار" in bonbast_data:
            currency.append(bonbast_data["دلار"])
        if "سکه امامی" in bonbast_data:
            gold.append(bonbast_data["سکه امامی"])
        if "انس طلا" in bonbast_data:
            gold.append(bonbast_data["انس طلا"])
        print("دریافت موفق: اطلاعات از bonbast.com", flush=True)
    except Exception as exc:
        errors.append(f"Bonbast: {exc}")

    return {"gold": gold, "currency": currency, "fetch_errors": errors}


# =========================================================
# پیدا کردن آیتم موردنظر
# =========================================================

def find_item(items, target_name):
    if not items:
        return None

    def norm(value):
        value = str(value or "").strip()
        value = value.translate(str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
        ))
        return " ".join(
            value.replace("ي", "ی").replace("ك", "ک")
                 .replace("‌", " ").split()
        ).lower()

    target = norm(target_name)
    valid_items = [item for item in items if isinstance(item, dict)]

    for item in valid_items:
        if norm(item.get("name")) == target:
            return item

    for item in valid_items:
        name = norm(item.get("name"))
        if target and (target in name or name in target):
            return item

    return None


# =========================================================
# تغییر قیمت نسبت به مبنای نیمه‌شب تهران
# =========================================================

BASELINE_FILE = Path(__file__).with_name("price_baseline.json")


def apply_midnight_baseline(data):
    tehran_tz = pytz.timezone("Asia/Tehran")
    now = datetime.now(tehran_tz)
    day_key = now.strftime("%Y-%m-%d")
    items = data.get("gold", []) + data.get("currency", [])

    current_prices = {}
    for item in items:
        try:
            price = float(item.get("price"))
        except (TypeError, ValueError):
            continue
        if price > 0:
            current_prices[str(item.get("name", "")).strip()] = price

    baseline = {}
    try:
        saved = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        if saved.get("date") == day_key and isinstance(saved.get("prices"), dict):
            baseline = saved["prices"]
    except (OSError, ValueError, TypeError):
        pass

    if not baseline:
        baseline = current_prices.copy()
        try:
            BASELINE_FILE.write_text(
                json.dumps({"date": day_key, "prices": baseline}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    for item in items:
        name = str(item.get("name", "")).strip()
        try:
            current = float(item.get("price"))
            opening = float(baseline.get(name))
            if current > 0 and opening > 0:
                item["change_percent"] = ((current - opening) / opening) * 100.0
            else:
                item["change_percent"] = 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            item["change_percent"] = 0.0

    return data


# =========================================================
# فرمت قیمت و تغییرات
# =========================================================

def format_price(price, is_ounce=False):
    try:
        value = float(price)
        if is_ounce:
            return f"${int(value):,}"
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
# بخش قیمت خودروها و سایر توابع کمکی
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
# جدول ارزش ذاتی طلای ۱۸ عیار و حباب (دقیق)
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
        if min(market_price, dollar_price, ounce_price) <= 0:
            return None

        # فرمول دقیق محاسبه ارزش ذاتی طلای 18 عیار
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

        raw_price = float(item.get("price", 0))
        price = format_price(raw_price, target["is_ounce"])
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


def send_telegram_rich(data):
    if not BOT_TOKEN:
        raise RuntimeError("توکن ربات تنظیم نشده است.")
        
    date_text = get_persian_datetime()
    table = build_table(data)
    gold_intrinsic_table = build_gold_intrinsic_table(data)

    blocks = [
        {"type": "heading", "text": RLM + "🧬 قیمت‌های لحظه‌ای بازار", "size": 2},
        {"type": "heading", "text": date_text, "size": 4},
        table,
        gold_intrinsic_table if gold_intrinsic_table else {
            "type": "table",
            "cells": [[{"text": RLM + "اطلاعات ارزش ذاتی طلا در دسترس نیست", "is_header": True, "align": "right", "valign": "middle"}]],
            "is_bordered": True, "is_striped": False, "is_compact": True,
        }
    ]

    rich_message = {"blocks": blocks, "is_rtl": True}
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendRichMessage"

    payload = {
        "chat_id": CHANNEL_ID,
        "rich_message": json.dumps(rich_message, ensure_ascii=False),
    }

    response = requests.post(telegram_url, data=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def main():
    try:
        print("دریافت اطلاعات از منابع جدید...", flush=True)
        data = get_data()
        data = apply_midnight_baseline(data)
        print("ارسال Rich Message به تلگرام...", flush=True)
        result = send_telegram_rich(data)
        print(f"پاسخ تلگرام: {result}", flush=True)
    except Exception as exc:
        print(f"خطا: {type(exc).__name__}: {exc}", flush=True)
        raise


if __name__ == "__main__":
    main()
