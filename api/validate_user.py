import json
import hashlib
import hmac
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BOT_TOKEN = os.environ.get("BOT_TOKEN")

def check_init_data(init_data: str):
    if not init_data:
        return None, "No init_data provided"
    if not BOT_TOKEN:
        return None, "BOT_TOKEN not set on server"

    # Парсим параметры
    params = parse_qs(init_data)
    # Ищем hash
    if 'hash' not in params:
        return None, "Missing 'hash' parameter in init_data"
    hash_str = params.pop('hash')[0]
    # Сортируем оставшиеся параметры и формируем строку
    sorted_params = sorted(params.items())
    data_check_string = "\n".join(f"{k}={v[0]}" for k, v in sorted_params)
    # Вычисляем ожидаемый hash
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if computed_hash != hash_str:
        return None, "Hash mismatch"
    # Извлекаем user
    user_param = params.get('user')
    if not user_param:
        return None, "Missing 'user' parameter in init_data"
    try:
        user = json.loads(user_param[0])
    except Exception as e:
        return None, f"Failed to parse user JSON: {e}"
    return user, None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        init_data = query.get('init_data', [None])[0]
        if not init_data:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing init_data"}).encode())
            return

        user, error = check_init_data(init_data)
        if error:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": error}).encode())
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"user_id": user.get('id')}).encode())