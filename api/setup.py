"""
Одноразовый эндпоинт: устанавливает webhook у Telegram.
Использование: https://<app>.vercel.app/api/setup?key=<SETUP_SECRET>
"""

import os
import sys
import json
import asyncio
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot  # noqa: E402

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
SETUP_SECRET = os.environ.get("SETUP_SECRET", "")


async def install() -> dict:
    bot = Bot(token=BOT_TOKEN)
    async with bot:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"],
        )
        info = await bot.get_webhook_info()
        return {
            "ok": True,
            "url": info.url,
            "pending_update_count": info.pending_update_count,
        }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        key = (qs.get("key") or [""])[0]
        if SETUP_SECRET and key != SETUP_SECRET:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        try:
            result = asyncio.run(install())
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
