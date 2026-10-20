import requests
import pytz
import jdatetime
import json
import os
import re
import statistics
import time
import atexit
from html.parser import HTMLParser
from playwright.sync_api import sync_playwright
from datetime import datetime
from pathlib import Path


# =========================================================
# تنظیمات
# =========================================================

# GitHub Actions must expose one of these secrets as an environment variable.
# Supported names: BOT_TOKEN or TELEGRAM_BOT_TOKEN.
BOT_TOKEN = "8805039197:AAG2qy6S2ArkjHszmFYVNeSpaYcufLTLMR0"CHANNEL_ID = "@iranpricenow"
# منابع قیمت‌ها: طلای ۱۸ از تابان گوهر، ارز از Bonbast و تتر از ارزدیجیتال
TABANGOHOAR_URL = "https://tabangohar.com/"
BONBAST_URL = "https://bonbast.com/"
ARZDIGITAL_TETHER_URL = "https://arzdigital.com/coins/tether/"

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
# دریافت قیمت‌ها از تابان گوهر، Bonbast و ارزدیجیتال
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


class _BrowserResponse:
    """پاسخ ساده با رابط سازگار با بخش‌های فعلی کد که response.text می‌خوانند."""
    def __init__(self, url, status_code, text):
        self.url = url
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code} while loading {self.url}",
                response=self,
            )


_playwright = None
_browser = None


def _close_market_browser():
    global _playwright, _browser
    try:
        if _browser is not None:
            _browser.close()
    except Exception:
        pass
    try:
        if _playwright is not None:
            _playwright.stop()
    except Exception:
        pass
    _browser = None
    _playwright = None


atexit.register(_close_market_browser)


def _get_market_page(url, **kwargs):
    """صفحه را با Chromium واقعی باز می‌کند و ۵ ثانیه پس از بارگذاری صبر می‌کند."""
    global _playwright, _browser
    host = url.split("/", 3)[2].lower() if "://" in url else ""
    if not (host.endswith("tabangohar.com") or host.endswith("bonbast.com") or host.endswith("arzdigital.com")):
        return requests.get(url, **kwargs)

    if _browser is None:
        _playwright = sync_playwright().start()
        try:
            _browser = _playwright.chromium.launch(headless=True)
        except Exception as exc:
            _close_market_browser()
            raise RuntimeError(
                "مرورگر Chromium برای Playwright نصب نیست. در GitHub Actions "
                "دستورهای `pip install playwright` و `playwright install chromium` را اجرا کنید."
            ) from exc

    timeout_seconds = kwargs.get("timeout", 25)
    headers = kwargs.get("headers", REQUEST_HEADERS)
    page = _browser.new_page(
        user_agent=headers.get("User-Agent", REQUEST_HEADERS["User-Agent"]),
        extra_http_headers={
            key: value for key, value in headers.items()
            if key.lower() != "user-agent"
        },
        locale="fa-IR",
    )
    try:
        print(f"باز کردن {host} با مرورگر واقعی؛ انتظار ۵ ثانیه پس از بارگذاری...", flush=True)
        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=int(timeout_seconds * 1000),
        )
        # این مکث بعد از بارگذاری صفحه و اجرای JavaScript انجام می‌شود.
        page.wait_for_timeout(5000)
        html = page.content()
        status_code = response.status if response is not None else 200
        return _BrowserResponse(page.url, status_code, html)
    finally:
        page.close()


def _fetch_text(url):
    response = _get_market_page(url, headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()
    parser = PlainTextParser()
    parser.feed(response.text)
    return " ".join(parser.parts), response.text


def _fetch_bonbast_dollar():
    """دریافت قیمت فروش دلار از صفحه عمومی Bonbast؛ اعداد این سایت تومان هستند."""
    response = _get_market_page(BONBAST_URL, headers=REQUEST_HEADERS, timeout=25)
    response.raise_for_status()

    # ابتدا از جدول صفحه استفاده می‌کنیم؛ ستون‌های نرخ فروش و خرید در انتهای ردیف‌اند.
    parser = HTMLTableParser()
    parser.feed(response.text)
    sell = None
    buy = None
    for row in parser.rows:
        row_text = " ".join(row).upper()
        if not (re.search(r"\bUSD\b", row_text) or "US DOLLAR" in row_text):
            continue
        numeric_values = [_number(cell) for cell in row]
        numeric_values = [value for value in numeric_values if value is not None and value > 0]
        if len(numeric_values) >= 2:
            sell, buy = numeric_values[-2], numeric_values[-1]
            break

    # پشتیبان برای زمانی که ساختار جدول عوض شود اما شناسه‌های شناخته‌شده باقی بمانند.
    if sell is None or buy is None:
        def value_by_id(element_id):
            match = re.search(
                rf"id=[\"']{re.escape(element_id)}[\"'][^>]*>(.*?)</",
                response.text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not match:
                return None
            raw = re.sub(r"<[^>]+>", " ", match.group(1))
            return _number(raw)

        sell = sell or value_by_id("usd1")
        buy = buy or value_by_id("usd2")

    if sell is None or sell <= 0:
        raise ValueError("قیمت فروش دلار از صفحه Bonbast پیدا نشد")

    print(f"Bonbast: دلار فروش={sell:,.0f} تومان" + (f"، خرید={buy:,.0f} تومان" if buy else ""), flush=True)
    return {"name": "دلار", "price": sell, "change_percent": 0.0}



def _fetch_arzdigital_tether():
    """دریافت قیمت تتر به تومان از صفحه رسمی قیمت تتر در ارزدیجیتال."""
    text, html = _fetch_text(ARZDIGITAL_TETHER_URL)
    normalized = _normalise_digits(text)

    # در صفحه ارزدیجیتال، قیمت تتر در سربرگ و بخش قیمت لحظه‌ای نمایش داده می‌شود.
    patterns = (
        r"قیمت\s*تتر\s*[:：]\s*([0-9][0-9,٬]{3,})",
        r"قیمت\s*امروز\s*تتر\s*در\s*ایران\s*([0-9][0-9,٬]{3,})\s*تومان",
        r"قیمت\s*تتر\s*[:：]?\s*([0-9][0-9,٬]{3,})\s*تومان",
    )
    candidates = []
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            value = _number(match.group(1))
            if value is not None and 10_000 <= value <= 10_000_000:
                candidates.append(value)
        if candidates:
            break

    # پشتیبان برای تغییرات احتمالی متن صفحه: مقدار قیمت تتر در بخش اصلی صفحه.
    if not candidates:
        plain_html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", html, flags=re.I | re.S)
        plain_html = re.sub(r"<[^>]+>", " ", plain_html)
        plain_html = _normalise_digits(plain_html)
        plain_html = re.sub(r"\s+", " ", plain_html)
        match = re.search(r"قیمت\s*تتر.{0,180}?([0-9][0-9,٬]{3,})\s*تومان", plain_html, flags=re.I)
        if match:
            value = _number(match.group(1))
            if value is not None and 10_000 <= value <= 10_000_000:
                candidates.append(value)

    if not candidates:
        raise ValueError("قیمت تتر از صفحه ارزدیجیتال پیدا نشد")

    # اولین تطبیق معتبر معمولاً قیمتِ سربرگ صفحه است و به تومان گزارش می‌شود.
    price = candidates[0]
    print(f"ارزدیجیتال: تتر={price:,.0f} تومان", flush=True)
    return {"name": "دلار تتر", "price": price, "change_percent": 0.0}

def _fetch_18k_from_tabangohar():
    """استخراج قیمت واقعی هر گرم طلای ۱۸ از متن و HTML تابان گوهر."""
    text, html = _fetch_text(TABANGOHOAR_URL)
    normalized = _normalise_digits(text)
    stripped_html = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", html, flags=re.I | re.S)
    stripped_html = re.sub(r"<[^>]+>", " ", stripped_html)
    stripped_html = re.sub(r"&nbsp;|&#160;", " ", stripped_html, flags=re.I)
    stripped_html = _normalise_digits(stripped_html)
    stripped_html = re.sub(r"\s+", " ", stripped_html)

    # اولویت با برچسب مشخص قیمت گرم ۱۸ است؛ از عدد «۱۸» داخل عنوان
    # یا عیار به‌عنوان قیمت استفاده نمی‌کنیم.
    sources = (normalized, stripped_html)
    patterns = (
        r"گرم\s*(?:18|۱۸)\s*(?:عیار\s*)?(?:تهران\s*)?[:：\-]?\s*([0-9][0-9,٬]{3,})\s*(?:تومان|ریال)?",
        r"قیمت\s*یک\s*گرم\s*(?:18|۱۸)\s*طلا\s*در\s*این\s*لحظه.{0,100}?([0-9][0-9,٬]{3,})\s*(?:تومان|ریال)?",
        r"قیمت\s*یک\s*گرم\s*طلای?\s*(?:18|۱۸)\s*عیار.{0,100}?([0-9][0-9,٬]{3,})\s*(?:تومان|ریال)?",
    )

    candidates = []
    for source in sources:
        for pattern in patterns:
            for match in re.finditer(pattern, source, flags=re.IGNORECASE):
                raw = match.group(1)
                value = _number(raw)
                if value is None or value <= 0:
                    continue
                # تابان گوهر گاهی قیمت را به هزار تومان (مثلاً 25,606)
                # و گاهی به تومان کامل (مثلاً 25,606,000) نمایش می‌دهد.
                if 20_000 <= value < 100_000:
                    value *= 1000
                elif 10_000_000 <= value <= 100_000_000:
                    pass
                else:
                    # مقادیری مثل 18,000 که از عدد عیار/عنوان اشتباهاً
                    # استخراج می‌شوند، قیمت معتبر گرم طلای ۱۸ نیستند.
                    continue
                candidates.append(value)
        if candidates:
            break

    if not candidates:
        raise ValueError("قیمت معتبر گرم طلای ۱۸ در صفحه تابان گوهر پیدا نشد")

    # اگر چند تطبیق معتبر وجود داشت، مقدار میانه اثر تطبیق اشتباه را کم می‌کند.
    value = statistics.median(candidates)
    return {"name": "طلای 18 عیار", "price": value, "change_percent": 0.0}


def get_data():
    """طلای ۱۸ از تابان گوهر، دلار از Bonbast و تتر از ارزدیجیتال دریافت می‌شود.
    برای سایر موارد فقط در صورت وجود نرخ در Bonbast از همان منبع استفاده می‌شود؛
    منبع TGJU در این نسخه استفاده نمی‌شود.
    """
    gold = []
    currency = []
    errors = []

    fetchers = [
        ("طلای ۱۸ عیار / تابان گوهر", lambda: gold.append(_fetch_18k_from_tabangohar())),
        ("دلار / Bonbast", lambda: currency.append(_fetch_bonbast_dollar())),
        ("تتر / ارزدیجیتال", lambda: currency.append(_fetch_arzdigital_tether())),
    ]

    for label, fetch in fetchers:
        try:
            fetch()
            print(f"دریافت موفق: {label}", flush=True)
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            print(f"هشدار دریافت قیمت {label}: {type(exc).__name__}: {exc}", flush=True)

    if errors:
        print("برخی قیمت‌ها در دسترس نبودند؛ ربات تلاش می‌کند بخش خودرو را نیز منتشر کند.", flush=True)
    print(f"تعداد قیمت‌های دریافتی: gold={len(gold)}, currency={len(currency)}", flush=True)
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

    # ابتدا تطبیق دقیق پس از یکسان‌سازی اعداد فارسی/عربی و حروف عربی.
    for item in valid_items:
        if norm(item.get("name")) == target:
            return item

    # سپس تطبیق جزئی برای تغییرات جزئی در نام آیتم‌های API.
    for item in valid_items:
        name = norm(item.get("name"))
        if target and (target in name or name in target):
            return item

    # نام‌های رایج جایگزین در فیدهای قیمت.
    aliases = {
        "دلار تتر": ("تتر", "تتر usdt", "usdt"),
        "دلار": ("دلار آزاد", "دلار بازار آزاد", "usd"),
        "طلای 18 عیار": ("طلای ۱۸ عیار", "هر گرم طلای 18", "گرم طلای 18 عیار", "طلای 18"),
        "سکه امامی": ("سکه طرح جدید", "امامی"),
        "انس طلا": ("انس جهانی طلا", "اونس طلا", "انس جهانی", "gold ounce"),
    }
    for alias in aliases.get(target_name, ()):
        alias_norm = norm(alias)
        for item in valid_items:
            if alias_norm and alias_norm in norm(item.get("name")):
                return item

    return None


# =========================================================
# تغییر قیمت نسبت به مبنای نیمه‌شب تهران
# =========================================================

BASELINE_FILE = Path(__file__).with_name("price_baseline.json")


def apply_midnight_baseline(data):
    """در اولین اجرای هر روز تهران، قیمت‌ها را مبنای تغییرات همان روز می‌کند."""
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

    # اگر روز عوض شده یا فایل مبنا وجود ندارد، اولین قیمت‌های روز ثبت می‌شوند.
    if not baseline:
        baseline = current_prices.copy()
        try:
            BASELINE_FILE.write_text(
                json.dumps({"date": day_key, "prices": baseline}, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"مبنای تغییرات روز {day_key} ثبت شد.", flush=True)
        except OSError as exc:
            print(f"هشدار: ذخیره مبنای روزانه ممکن نشد: {exc}", flush=True)

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
            return f"${value:,.0f}"
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
    translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
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
        if min(market_price, dollar_price, ounce_price) <= 0:
            return None

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

    matched_count = 0
    for target in targets:
        item = find_item(all_items, target["key"])
        if not item:
            print(f"هشدار: آیتم API پیدا نشد: {target['key']}", flush=True)
            continue

        try:
            raw_price = float(item.get("price"))
        except (TypeError, ValueError):
            raw_price = 0
        if raw_price <= 0:
            print(f"هشدار: قیمت معتبر برای {target['key']} موجود نیست؛ از جدول حذف شد.", flush=True)
            continue

        matched_count += 1
        price = format_price(raw_price, target["is_ounce"])
        change = format_api_change(item.get("change_percent", 0))

        cells.append([
            {"text": RLM + target["label"], "align": "right", "valign": "middle"},
            {"text": RLM + price, "align": "right", "valign": "middle"},
            {"text": RLM + change, "align": "right", "valign": "middle"},
        ])

    if matched_count == 0:
        print("خطا: هیچ‌یک از آیتم‌های ارز/طلا با نام‌های مورد انتظار تطبیق نکرد.", flush=True)

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
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_NEW_TELEGRAM_BOT_TOKEN_HERE":
        raise RuntimeError(
            "توکن ربات تنظیم نشده است؛ متغیر محیطی BOT_TOKEN را با توکن جدید تنظیم کنید."
        )
    date_text = get_persian_datetime()
    table = build_table(data)
    gold_intrinsic_table = build_gold_intrinsic_table(data)
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
    try:
        print("دریافت اطلاعات از API...", flush=True)
        data = get_data()
        data = apply_midnight_baseline(data)
        print("ارسال Rich Message به تلگرام...", flush=True)
        result = send_telegram_rich(data)
        print(f"پاسخ تلگرام: {result}", flush=True)
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")
        print("پیام با موفقیت ارسال شد.", flush=True)
    except Exception as exc:
        print(f"خطای main.py: {type(exc).__name__}: {exc}", flush=True)
        raise


if __name__ == "__main__":
    main()
