from http.server import BaseHTTPRequestHandler
import os, json, http.client, urllib.parse
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID  = os.environ.get("TELEGRAM_OWNER_ID", "")
SUPABASE_URL       = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

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


def _push_to_supabase(name, phone, email, service, message, source):
    """Append a new lead into the CRM's Supabase crm_state JSON blob."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        parsed = urllib.parse.urlparse(SUPABASE_URL)
        host   = parsed.hostname
        base   = parsed.path.rstrip("/")
        hdrs   = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }

        # 1. Read current state
        conn = http.client.HTTPSConnection(host, timeout=8)
        conn.request("GET", f"{base}/rest/v1/crm_state?id=eq.1&select=state",
                     headers=hdrs)
        resp = conn.getresponse()
        rows = json.loads(resp.read())

        if not rows:
            return  # state row not initialised yet
        state = rows[0].get("state") or {}

        # 2. Increment lead counter
        counter = (state.get("leadCounter") or 0) + 1
        state["leadCounter"] = counter

        # 3. Build client record
        today = datetime.now().strftime("%Y-%m-%d")
        client = {
            "id": f"cl-{int(datetime.now().timestamp() * 1000)}",
            "leadNumber": counter,
            "name": name,
            "phone": phone or "",
            "email": email or "",
            "address": "",
            "city": "",
            "state": "WA",
            "source": SOURCE_LABELS.get(source, source),
            "rating": 3,
            "status": "New Lead",
            "stage": "new",
            "project": SERVICE_LABELS.get(service, service),
            "budget": 0,
            "notes": message or "",
            "createdAt": today,
            "lastTouch": today,
            "emailConsent": False,
            "smsConsent": False,
        }

        if not isinstance(state.get("clients"), list):
            state["clients"] = []
        state["clients"].insert(0, client)

        if not isinstance(state.get("activity"), list):
            state["activity"] = []
        state["activity"].insert(0, {
            "date": today,
            "text": f"New lead #{counter} {name} created from website form."
        })

        # 4. Save back
        patch_payload = json.dumps({
            "state": state,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }).encode()
        conn2 = http.client.HTTPSConnection(host, timeout=8)
        conn2.request(
            "PATCH",
            f"{base}/rest/v1/crm_state?id=eq.1",
            body=patch_payload,
            headers={**hdrs, "Prefer": "return=minimal"},
        )
        conn2.getresponse().read()
    except Exception as exc:
        # Non-fatal — Telegram notification still went through
        print(f"Supabase push failed: {exc}")


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
        _push_to_supabase(name, phone, email, service, message, source)
        _cors_headers(self)
        self.wfile.write(json.dumps({"ok": True, "telegram_sent": sent}).encode())

    def log_message(self, *_):
        pass
