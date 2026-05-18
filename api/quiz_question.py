import json
from http.server import BaseHTTPRequestHandler
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.facts import get_random_quiz_structured

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            quiz_data = get_random_quiz_structured()
            if quiz_data is None:
                self.wfile.write(json.dumps({"error": "No quiz available"}).encode())
            else:
                self.wfile.write(json.dumps(quiz_data, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)}).encode())