import requests
import pytz
import jdatetime
import re
from datetime import datetime

BOT_TOKEN = "8805039197:AAG2qy6S2ArkjHszmFYVNeSpaYcufLTLMR0"
CHANNEL_ID = "@iranpricenow"
BRS_API_URL = "https://api.brsapi.ir/Market/Gold_Currency.php?key=BupMHVpmxnEXDXaKJF7KtN9uKZxd7GCL"
IRANJIB_URL = "https://www.iranjib.ir/showgroup/45/%D9%82%DB%8C%D9%85%D8%AA-%D8%AE%D9%88%D8%AF%D8%B1%D9%88-%D8%AA%D9%88%D9%84%DB%8C%D8%AF-%D8%AF%D8%A7%D8%AE%D9%84/"


def to_persian_number(value):
    table = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")
    return str(value).translate(table)


def get_market_data():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36", "Accept": "application/json"}
    try:
        r = requests.get(BRS_API_URL, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"BRS API Error: {e}")
        return None


def find_market_item(items, names):
    for item in items:
        name = str(item.get("name", "")).strip()
        if any(name == x for x in names):
            return item
    for item in items:
        name = str(item.get("name", "")).strip()
        if any(x in name for x in names):
            return item
    return None


def format_market_price(price, ounce=False):
    try:
        value = float(str(price).replace(",", "").strip())
        return f"${value:,.2f}" if ounce else to_persian_number(f"{int(value):,}")
    except (ValueError, TypeError):
        return "—"


def format_change(value):
    try:
        value = float(str(value).replace("%", "").replace(",", "").strip())
        if value > 0:
            return f"▲ {to_persian_number(f'{value:.2f}')}٪"
        if value < 0:
            return f"▼ {to_persian_number(f'{abs(value):.2f}')}٪"
        return "━ ۰.۰۰٪"
    except (ValueError, TypeError):
        return "—"


def get_car_prices():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        r = requests.get(IRANJIB_URL, headers=headers, timeout=30)
        r.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        targets = {
            "سورن TU5": ["سورن (TU5P)", "سورن TU5P"],
            "۲۰۷ پانوراما": ["پژو 207 دنده‌ای پانوراما", "پژو 207 پانوراما", "207 دنده‌ای پانوراما"],
            "دنا پلاس MT6": ["دنا پلاس MT6", "دنا پلاس 6 دنده"],
            "تارا دستی V1": ["تارا دستی V1", "تارا V1"],
        }
        result = {}

        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue
                values = [c.get_text(" ", strip=True) for c in cells]
                row_text = " ".join(values)

                selected = None
                for key, aliases in targets.items():
                    if any(alias in row_text for alias in aliases):
                        selected = key
                        break
                if not selected:
                    continue

                price = None
                # قیمت بازار را از اولین عدد بزرگ موجود در ردیف می‌گیریم.
                for value in values[1:]:
                    digits = re.sub(r"[^\d]", "", value)
                    if len(digits) >= 7:
                        price = digits
                        break
                if not price:
                    continue

                change = "—"
                for value in values:
                    m = re.search(r"([+-]?\d+(?:[.,]\d+)?)\s*%", value)
                    if m:
                        try:
                            p = float(m.group(1).replace(",", "."))
                            if p > 0:
                                change = f"▲ {to_persian_number(f'{p:.2f}')}٪"
                            elif p < 0:
                                change = f"▼ {to_persian_number(f'{abs(p):.2f}')}٪"
                            else:
                                change = "━ ۰.۰۰٪"
                            break
                        except ValueError:
                            pass

                result[selected] = {
                    "name": values[0],
                    "price": to_persian_number(f"{int(price):,}"),
                    "change": change,
                }

        print("IranJib result:")
        for k, v in result.items():
            print(f"{k}: {v['price']} | {v['change']}")
        return result
    except Exception as e:
        print(f"IranJib Error: {e}")
        return {}


def get_persian_datetime():
    tehran = pytz.timezone("Asia/Tehran")
    now = datetime.now(tehran)
    jalali = jdatetime.datetime.fromgregorian(datetime=now)
    months = {1:"فروردین",2:"اردیبهشت",3:"خرداد",4:"تیر",5:"مرداد",6:"شهریور",7:"مهر",8:"آبان",9:"آذر",10:"دی",11:"بهمن",12:"اسفند"}
    return f"آخرین به‌روزرسانی: {to_persian_number(jalali.day)} {months[jalali.month]} ساعت {to_persian_number(now.strftime('%H'))}:{to_persian_number(now.strftime('%M'))} دقیقه"


def build_market_rows(data):
    items = data.get("gold", []) + data.get("currency", [])
    targets = [
        ({"names":["دلار تتر","تتر"],"label":"تتر 💸","ounce":False}),
        ({"names":["دلار"],"label":"دلار 💵","ounce":False}),
        ({"names":["طلای 18 عیار","طلای ۱۸ عیار"],"label":"طلای ۱۸ عیار 🪙","ounce":False}),
        ({"names":["سکه امامی","تمام سکه"],"label":"سکه امامی 🌕","ounce":False}),
        ({"names":["انس طلا","انس"],"label":"انس جهانی 🌍","ounce":True}),
    ]
    rows = []
    for t in targets:
        item = find_market_item(items, t["names"])
        if item:
            rows.append((t["label"], format_market_price(item.get("price"), t["ounce"]), format_change(item.get("change_percent", 0))))
    return rows


def html_market_table(rows):
    html = "<pre>عنوان                 قیمت             تغییرات\n──────────────────────────────────────────────\n"
    for title, price, change in rows:
        html += f"{title:<20}{price:>16}{change:>14}\n"
    return html + "</pre>"


def html_car_table(cars):
    html = "<pre>خودرو                    قیمت          تغییرات\n──────────────────────────────────────────────\n"
    order = ["سورن TU5", "۲۰۷ پانوراما", "دنا پلاس MT6", "تارا دستی V1"]
    for name in order:
        if name in cars:
            item = cars[name]
            html += f"{name:<24}{item['price']:>14}{item['change']:>14}\n"
    return html + "</pre>"


def telegram_request(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = requests.post(url, json=payload, timeout=30)
    print(f"Telegram {method}: {r.status_code}")
    print(r.text)
    r.raise_for_status()
    return r.json()


def send_price_message(market_data):
    rows = build_market_rows(market_data)
    if not rows:
        raise RuntimeError("No market rows found")
    text = f"<b>🧬 قیمت‌های لحظه‌ای بازار</b>\n\n{get_persian_datetime()}\n\n{html_market_table(rows)}"
    keyboard = {"inline_keyboard":[
        [{"text":"🚗 قیمت خودرو ▼","callback_data":"show_cars"}],
        [{"text":"📊 قیمت بروز ارز و خودرو","url":"https://t.me/iranpricenow"}]
    ]}
    return telegram_request("sendMessage", {"chat_id":CHANNEL_ID,"text":text,"parse_mode":"HTML","reply_markup":keyboard,"disable_web_page_preview":True})


def answer_callback(callback_id):
    try:
        telegram_request("answerCallbackQuery", {"callback_query_id": callback_id})
    except Exception as e:
        print(f"answerCallbackQuery error: {e}")


def edit_message(callback, show_cars, market_data):
    message = callback.get("message")
    if not message:
        return
    car_data = get_car_prices() if show_cars else {}
    rows = build_market_rows(market_data)
    text = f"<b>🧬 قیمت‌های لحظه‌ای بازار</b>\n\n{get_persian_datetime()}\n\n{html_market_table(rows)}"
    if show_cars:
        text += f"\n<b>🚗 قیمت خودرو</b>\n\n{html_car_table(car_data)}"
    button_text = "🚗 قیمت خودرو ▲" if show_cars else "🚗 قیمت خودرو ▼"
    action = "hide_cars" if show_cars else "show_cars"
    keyboard = {"inline_keyboard":[
        [{"text":button_text,"callback_data":action}],
        [{"text":"📊 قیمت بروز ارز و خودرو","url":"https://t.me/iranpricenow"}]
    ]}
    telegram_request("editMessageText", {
        "chat_id":message["chat"]["id"],
        "message_id":message["message_id"],
        "text":text,
        "parse_mode":"HTML",
        "reply_markup":keyboard,
        "disable_web_page_preview":True
    })


def main():
    market_data = get_market_data()
    if not market_data:
        return
    send_price_message(market_data)


if __name__ == "__main__":
    main()
