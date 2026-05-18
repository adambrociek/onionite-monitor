from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


DEFAULT_URL = "https://onionite.pl/83-szafa-ziemniaka-wyprzedaz"
STATE_FILE = Path(__file__).resolve().parent / "state" / "seen_products.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 OnioniteMonitor/1.0"
)


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    url: str
    price: str = ""
    sold_out: bool = False


class ProductListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {name.lower(): value or "" for name, value in attrs}
        href = attr_map.get("href")
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._current_href:
            return
        text = normalize_text(" ".join(self._current_text))
        if text:
            self.links.append((self._current_href, text))
        self._current_href = None
        self._current_text = []


def normalize_text(value: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", value)).strip()


def product_list_html(page_html: str) -> str:
    lowered = page_html.lower()
    start = lowered.find("znaleziono:")
    end = lowered.find("pokazano", start if start != -1 else 0)
    if start == -1 or end == -1:
        return page_html
    return page_html[start:end]


def fetch_page(url: str, timeout: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_products(page_html: str) -> list[Product]:
    page_html = product_list_html(page_html)
    parser = ProductListParser()
    parser.feed(page_html)

    products: list[Product] = []
    seen: set[str] = set()

    for href, text in parser.links:
        if not looks_like_product_link(href, text):
            continue

        product_id = product_id_from_url(href)
        if not product_id or product_id in seen:
            continue

        clean_name = clean_product_name(text)
        if not clean_name:
            continue

        products.append(
            Product(
                id=product_id,
                name=clean_name,
                url=absolute_url(href),
                price=find_price_near_link(page_html, href),
                sold_out=is_sold_out(page_html, href, text),
            )
        )
        seen.add(product_id)

    return products


def looks_like_product_link(href: str, text: str) -> bool:
    if not href.lower().split("?", 1)[0].endswith(".html"):
        return False
    if not re.search(r"/\d+-", href):
        return False
    lowered = text.lower()
    ignored = (
        "szybki podglad",
        "szybki podgląd",
        "sprzedany",
        "strona glowna",
        "strona główna",
        "pokaz wszystkie",
        "pokaż wszystkie",
    )
    return not any(value == lowered or lowered.endswith(value) for value in ignored)


def product_id_from_url(url: str) -> str:
    match = re.search(r"/(\d+)-", url)
    return match.group(1) if match else ""


def clean_product_name(text: str) -> str:
    text = re.sub(r"\b(Nowy|SPRZEDANY!|Szybki podgl[aą]d|search)\b", " ", text, flags=re.I)
    text = normalize_text(text)
    if text.lower().endswith(" ziemniak"):
        text = text[: -len(" ziemniak")].strip()
    return text


def absolute_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://onionite.pl/" + url.lstrip("/")


def find_price_near_link(page_html: str, href: str) -> str:
    index = page_html.find(href)
    if index == -1:
        return ""
    chunk = page_html[max(0, index - 500) : index + 1600]
    text = normalize_text(re.sub(r"<[^>]+>", " ", chunk))
    match = re.search(r"\d+(?:[,.]\d{2})?\s*zł", text)
    return match.group(0) if match else ""


def is_sold_out(page_html: str, href: str, text: str) -> bool:
    if "sprzedany" in text.lower():
        return True
    index = page_html.find(href)
    if index == -1:
        return False
    nearby = normalize_text(re.sub(r"<[^>]+>", " ", page_html[max(0, index - 1500) : index + 1500]))
    return "sprzedany" in nearby.lower()


def load_seen(path: Path) -> dict[str, dict[str, str | bool]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def save_seen(path: Path, products: Iterable[Product]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        product.id: {**asdict(product), "last_seen_at": datetime.now().isoformat(timespec="seconds")}
        for product in products
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)


def print_products(products: Iterable[Product]) -> None:
    for product in products:
        status = "sold out" if product.sold_out else "available/unknown"
        price = f" | {product.price}" if product.price else ""
        print(f"- [{status}] {product.name}{price}")
        print(f"  {product.url}")


def beep() -> None:
    if sys.platform != "win32":
        print("\a", end="", flush=True)
        return
    try:
        import winsound

        winsound.Beep(1200, 500)
        winsound.Beep(1600, 500)
    except RuntimeError:
        print("\a", end="", flush=True)


def send_telegram_alert(args: argparse.Namespace, products: list[Product]) -> None:
    if not args.telegram:
        return

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", bot_token),
            ("TELEGRAM_CHAT_ID", chat_id),
        )
        if not value
    ]
    if missing:
        print(f"Telegram alert skipped. Missing environment variable(s): {', '.join(missing)}")
        return

    body = build_alert_message(products)
    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    post_data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": body,
            "disable_web_page_preview": "false",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=post_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        message_id = payload.get("result", {}).get("message_id", "unknown message id")
        print(f"Telegram alert sent: {message_id}")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print(f"Telegram alert failed: HTTP {exc.code} {details}")
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Telegram alert failed: {exc}")


def build_alert_message(products: list[Product]) -> str:
    lines = ["New Onionite product detected:" if len(products) == 1 else "New Onionite products detected:"]
    for product in products:
        price = f" ({product.price})" if product.price else ""
        status = " sold out" if product.sold_out else ""
        lines.append(f"{product.name}{price}{status}")
        lines.append(product.url)
    return "\n".join(lines)


def run_once(args: argparse.Namespace) -> list[Product]:
    page = fetch_page(args.url, args.timeout)
    products = extract_products(page)
    seen = load_seen(args.state_file)
    new_products = [product for product in products if args.alert_existing or product.id not in seen]

    if args.show_all:
        print(f"Products found: {len(products)}")
        print_products(products)

    if not seen and not args.alert_existing:
        save_seen(args.state_file, products)
        print(f"Initial snapshot saved with {len(products)} products. Watching for future changes.")
        return []

    if new_products:
        print(f"\nNEW PRODUCT(S) at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print_products(new_products)
        beep()
        send_telegram_alert(args, new_products)
        if args.open_browser:
            for product in new_products:
                webbrowser.open(product.url, new=2)
    else:
        print(f"No new products. Checked {len(products)} products at {datetime.now().strftime('%H:%M:%S')}.")

    save_seen(args.state_file, products)
    return new_products


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 5:
        raise argparse.ArgumentTypeError("Use an interval of at least 5 seconds.")
    return parsed


def send_telegram_test(args: argparse.Namespace) -> int:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", bot_token),
            ("TELEGRAM_CHAT_ID", chat_id),
        )
        if not value
    ]
    if missing:
        print(f"Test message failed. Missing environment variable(s): {', '.join(missing)}")
        return 1

    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    post_data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": "Test message from Onionite monitor. Bot is working correctly.",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=post_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        message_id = payload.get("result", {}).get("message_id", "unknown")
        print(f"Test message sent successfully (message_id: {message_id})")
        return 0
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print(f"Test message failed: HTTP {exc.code} {details}")
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Test message failed: {exc}")
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch Onionite's Szafa Ziemniaka category for new products.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--interval", type=positive_int, default=30, help="Seconds between checks.")
    parser.add_argument("--timeout", type=positive_int, default=15, help="HTTP timeout in seconds.")
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--once", action="store_true", help="Check once and exit.")
    parser.add_argument("--alert-existing", action="store_true", help="Treat products already on the page as alerts.")
    parser.add_argument("--open-browser", action="store_true", help="Open newly detected product pages in your browser.")
    parser.add_argument("--telegram", action="store_true", help="Send Telegram alerts through a Telegram bot.")
    parser.add_argument("--show-all", action="store_true", help="Print all parsed products on each check.")
    parser.add_argument("--test-telegram", action="store_true", help="Send a test message via Telegram and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.test_telegram:
        return send_telegram_test(args)

    print(f"Watching {args.url}")
    print(f"Snapshot: {args.state_file}")

    while True:
        try:
            run_once(args)
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"Fetch failed: {exc}")
        except KeyboardInterrupt:
            print("\nStopped.")
            return 0

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
