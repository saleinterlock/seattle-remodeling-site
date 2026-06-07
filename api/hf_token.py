from http.server import BaseHTTPRequestHandler
import os, json

HF_API_KEY = os.environ.get("HF_API_KEY", "")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self._send(200, {})

    def do_GET(self):
        if not HF_API_KEY:
            return self._send(503, {"error": "HF_API_KEY not configured"})
        self._send(200, {"token": HF_API_KEY})

    def _send(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, *_):
        pass
