"""
Телеграм-бот: следит за RSS-лентами и публикует новые записи в канал/чат.

Установка:  pip install feedparser requests
Запуск:     BOT_TOKEN=123:ABC CHAT_ID=@my_channel python rss_bot.py
"""
import html
import json
import os
import re
import time
from pathlib import Path

import feedparser
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]          # токен от @BotFather
CHAT_ID = os.environ["CHAT_ID"]              # @username канала или числовой id чата
FEEDS = [                                    # список RSS-лент
    "https://www.worldofreel.com/blog?format=rss",   # World of Reel
]
CHECK_EVERY = 300                            # проверка раз в 5 минут
SEEN_FILE = Path("seen.json")                # уже отправленные записи

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    # храним только последние 5000, чтобы файл не рос бесконечно
    SEEN_FILE.write_text(json.dumps(list(seen)[-5000:]))


def find_image(entry) -> str | None:
    """Ищет картинку поста: media:content, media:thumbnail, вложение или первый <img> в тексте."""
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []):
            if m.get("url"):
                return m["url"]
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image") and enc.get("href"):
            return enc["href"]
    texts = [c.get("value", "") for c in entry.get("content", [])]
    texts.append(entry.get("summary", ""))
    for t in texts:
        m = re.search(r'<img[^>]+src="([^"]+)"', t)
        if m:
            return html.unescape(m.group(1))
    return None


def tg(method: str, payload: dict) -> requests.Response:
    r = requests.post(f"{API}/{method}", json=payload, timeout=30)
    if r.status_code == 429:                 # лимит Telegram — ждём и повторяем
        time.sleep(r.json()["parameters"]["retry_after"])
        return tg(method, payload)
    return r


def send(entry, feed_title: str) -> None:
    link = entry.get("link", "")
    title = html.escape(entry.get("title", "Без заголовка"))
    caption = f'<a href="{link}"><b>{title}</b></a>'   # заголовок-ссылка, без голого URL
    image = find_image(entry)

    # 1) Есть картинка из поста — шлём её крупно с заголовком-ссылкой
    if image:
        r = tg("sendPhoto", {
            "chat_id": CHAT_ID, "photo": image,
            "caption": caption, "parse_mode": "HTML",
        })
        if r.ok:
            return
        print("sendPhoto не сработал, шлю превью ссылки:", r.text)

    # 2) Картинки нет — заголовок-ссылка + крупное превью страницы
    r = tg("sendMessage", {
        "chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML",
        "link_preview_options": {"url": link, "prefer_large_media": True},
    })
    r.raise_for_status()


def check_feeds(seen: set, first_run: bool) -> None:
    for url in FEEDS:
        feed = feedparser.parse(url)
        feed_title = feed.feed.get("title", url)
        # старые записи — первыми, чтобы в канале был хронологический порядок
        for entry in reversed(feed.entries):
            uid = entry.get("id") or entry.get("link")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            if not first_run:                # при первом запуске не спамим архивом
                send(entry, feed_title)
                time.sleep(3)                # пауза между постами
    save_seen(seen)


def main() -> None:
    seen = load_seen()
    first_run = not SEEN_FILE.exists()
    if os.environ.get("RUN_ONCE"):           # режим для GitHub Actions: одна проверка и выход
        check_feeds(seen, first_run)
        return
    while True:
        try:
            check_feeds(seen, first_run)
            first_run = False
        except Exception as e:
            print("Ошибка:", e)
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
