"""
Cron-эндпоинт. Vercel дёргает каждый час (0 * * * *).
Определяет текущий час МСК и рассылает факт подписчикам этого часа,
учитывая персональные категории каждого.
"""

import os
import sys
import json
import asyncio
import datetime
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot  # noqa: E402
from telegram.error import Forbidden, BadRequest, TelegramError  # noqa: E402

from lib.storage import (  # noqa: E402
    get_all_subscribers, remove_subscriber, get_user_categories,
)
from lib.facts import get_today_fact_filtered  # noqa: E402

BOT_TOKEN = os.environ["BOT_TOKEN"]
CRON_SECRET = os.environ.get("CRON_SECRET", "")


def _msk_hour() -> int:
    msk = datetime.timezone(datetime.timedelta(hours=3))
    return datetime.datetime.now(msk).hour


async def broadcast() -> dict:
    subs = await get_all_subscribers()
    if not subs:
        return {"total": 0, "sent": 0, "failed": 0, "removed": 0}
    sent, failed, removed = 0, 0, 0
    bot = Bot(token=BOT_TOKEN)
    async with bot:
        for chat_id in subs:
            try:
                cats = await get_user_categories(chat_id)  # категории оставляем
                fact = await get_today_fact_filtered(categories=cats)
                await bot.send_message(chat_id, fact, parse_mode="HTML", disable_web_page_preview=True)
                sent += 1
            except Forbidden:
                await remove_subscriber(chat_id)
                removed += 1
            except Exception as e:
                print(f"[cron] error {chat_id}: {e!r}", file=sys.stderr)
                failed += 1
            await asyncio.sleep(0.05)
    return {"total": len(subs), "sent": sent, "failed": failed, "removed": removed}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if CRON_SECRET and auth != f"Bearer {CRON_SECRET}":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        try:
            result = asyncio.run(broadcast())
        except Exception as e:
            print(f"[cron] fatal: {e!r}", file=sys.stderr)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
