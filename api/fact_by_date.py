import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.facts import get_fact_for_date_structured
from lib.storage import increment_fact_count

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        date_str = query.get('date', [None])[0]
        user_id = query.get('user_id', [None])[0]

        if user_id:
            try:
                asyncio.run(increment_fact_count(int(user_id)))
            except Exception as e:
                print(f"[fact_by_date] increment error: {e}", file=sys.stderr)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if not date_str:
            self.wfile.write(json.dumps({"error": "Missing date parameter"}).encode())
            return

        try:
            fact_data = get_fact_for_date_structured(date_str)
            if fact_data is None:
                self.wfile.write(json.dumps({"error": f"No fact for date {date_str}"}).encode())
            else:
                self.wfile.write(json.dumps(fact_data, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)}).encode())