"""
Телеграм-бот: следит за RSS-лентами и публикует новые записи в канал/чат.

Установка:  pip install feedparser requests
Запуск:     BOT_TOKEN=123:ABC CHAT_ID=@my_channel python rss_bot.py
"""
import html
import json
import os
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

API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    # храним только последние 5000, чтобы файл не рос бесконечно
    SEEN_FILE.write_text(json.dumps(list(seen)[-5000:]))


def send(entry, feed_title: str) -> None:
    # Формат как у IFTTT: название ленты + ссылка.
    # Заголовок, описание, картинку и Instant View Telegram подтянет сам из превью ссылки.
    link = entry.get("link", "")
    text = f"{html.escape(feed_title)}\n{link}"
    r = requests.post(API, data={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=20)
    if r.status_code == 429:                 # лимит Telegram — ждём и повторяем
        time.sleep(r.json()["parameters"]["retry_after"])
        return send(entry, feed_title)
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
