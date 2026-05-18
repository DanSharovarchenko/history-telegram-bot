import json
import asyncio
from http.server import BaseHTTPRequestHandler
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.storage import quiz_record_answer

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(content_length)
        try:
            data = json.loads(raw)
            # Получаем user_id из тела запроса (будем передавать из miniapp)
            user_id = data.get('user_id', 0)
            selected = data.get('selected')
            correct_index = data.get('correct')
            is_correct = (selected == correct_index)

            # Асинхронную функцию запускаем синхронно
            stats = asyncio.run(quiz_record_answer(user_id, is_correct))

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"correct": is_correct, "stats": stats}).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())