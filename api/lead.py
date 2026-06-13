from http.server import BaseHTTPRequestHandler
import os, json, http.client
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID  = os.environ.get("TELEGRAM_OWNER_ID", "")

SERVICE_LABELS = {
    "bathroom": "🚿 Bathroom Remodel", "full_remodel": "🚿 Full Bath Remodel",
    "walkin_shower": "🚿 Walk-In Shower", "tub_conversion": "🛁 Tub-to-Shower Conversion",
    "vanity_tile": "🪞 Vanity & Tile", "other": "📦 Not Sure — Let's Talk"
}
SOURCE_LABELS  = {"website_form": "📝 Website Form", "phone_call": "📞 Phone Call",
                  "chat": "💬 AI Chat", "manual": "✍️ Manual Entry",
                  "planner_quote": "🛁 Room Planner"}


def _send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_OWNER_ID:
        return False
    payload = json.dumps({"chat_id": TELEGRAM_OWNER_ID, "text": text, "parse_mode": "Markdown"}).encode()
    try:
        conn = http.client.HTTPSConnection("api.telegram.org", timeout=8)
        conn.request("POST", f"/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                     body=payload, headers={"Content-Type": "application/json"})
        return conn.getresponse().status == 200
    except Exception:
        return False


def _cors_headers(self, status=200):
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.end_headers()


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _cors_headers(self)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length) or b"{}")

        name    = (body.get("name") or "").strip()
        phone   = (body.get("phone") or "").strip()
        email   = (body.get("email") or "").strip()
        service = (body.get("service") or "other").strip()
        message = (body.get("message") or "").strip()
        source  = (body.get("source") or "website_form").strip()
        planner = body.get("planner_config")

        if not name or (not phone and not email):
            _cors_headers(self, 400)
            self.wfile.write(json.dumps({"error": "name and phone or email required"}).encode())
            return

        now   = datetime.now().strftime("%b %d, %H:%M")
        lines = [
            f"🔔 *НОВЫЙ ЛИД!* {now}", "",
            f"👤 *Имя:* {name}",
            f"📱 *Телефон:* {phone or '—'}",
        ]
        if email:
            lines.append(f"📧 *Email:* {email}")
        lines += [
            f"🔧 *Услуга:* {SERVICE_LABELS.get(service, service)}",
            f"📨 *Источник:* {SOURCE_LABELS.get(source, source)}",
        ]
        if planner:
            room = planner.get("room", [])
            fixes = planner.get("fixtures", [])
            floor_t = planner.get("floor", "")
            wall_t = planner.get("wall", "")
            estimate = planner.get("estimate", "")
            lines.append(
                f"\n🛁 *Планировщик:*\n"
                f"  Размер: {room[0]}×{room[1]} фт\n"
                f"  Сантехника: {', '.join(fixes) or 'не выбрано'}\n"
                f"  Плитка пол/стена: {floor_t} / {wall_t}\n"
                f"  Смета: {estimate}"
            )
        if message:
            lines.append(f"💬 *Сообщение:*\n_{message[:300]}_")
        lines += ["", "👉 Позвони в течение 2 часов!"]

        sent = _send_telegram("\n".join(lines))
        _cors_headers(self)
        self.wfile.write(json.dumps({"ok": True, "telegram_sent": sent}).encode())

    def log_message(self, *args):
        pass
