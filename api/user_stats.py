import json
from http.server import BaseHTTPRequestHandler
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.storage import get_all_fact_counts, get_all_quiz_stats

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        total_facts = asyncio.run(get_all_fact_counts())
        total_correct, total_answers = asyncio.run(get_all_quiz_stats())
        data = {
            "fact_count": total_facts,
            "quiz_correct": total_correct,
            "quiz_total": total_answers
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())