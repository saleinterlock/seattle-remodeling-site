from http.server import BaseHTTPRequestHandler
import os, json, re, http.client

import anthropic

ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID  = os.environ.get("TELEGRAM_OWNER_ID", "")
COMPANY_NAME       = os.environ.get("COMPANY_NAME", "Seattle Pro Remodeling")
COMPANY_PHONE      = os.environ.get("COMPANY_PHONE", "(206) 555-0000")
SERVICE_AREA_ZIPS  = os.environ.get("SERVICE_AREA_ZIPS", "98101,98103,98105,98107,98109,98115,98117")

SYSTEM_PROMPT = f"""You are Alex, a friendly project coordinator at {COMPANY_NAME} in Seattle.
Your job: qualify potential customers through natural, friendly chat conversation.
Services: Bathroom Remodels, Kitchen Remodels, Fence Installation.

Collect naturally (one question at a time):
1. Type of project (bathroom / kitchen / fence / other)
2. ZIP code or neighborhood
3. Brief project description
4. Rough budget range
5. Timeline (ASAP / 1-3 months / just exploring)
6. Their name and phone number (ask near the end)

Style: sound like a real person, keep replies to 2-4 sentences, ask ONE question per message.
Never give prices. Never say you're an AI.
When you have name + phone: "Perfect! Our project manager will call you at [phone] within 2 hours."
Service area ZIPs: {SERVICE_AREA_ZIPS}. Our phone: {COMPANY_PHONE}."""

_PHONE_RE = re.compile(r'(\+?1?\s*[\(\-\.]?\d{3}[\)\-\.\s]\s*\d{3}[\-\.\s]\d{4})')
_NAME_RE  = re.compile(r"(?:i'?m|my name is|name'?s|this is|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.I)


def _extract_lead(messages):
    text = " ".join(m.get("content", "") for m in messages)
    phone = _PHONE_RE.search(text)
    name  = _NAME_RE.search(text)
    return {
        "phone": phone.group(0).strip() if phone else "",
        "name":  name.group(1).strip()  if name  else "",
    }


def _guess_service(messages):
    text = " ".join(m.get("content", "").lower() for m in messages)
    if any(w in text for w in ("bathroom","bath","shower","tub")): return "bathroom"
    if any(w in text for w in ("kitchen","cabinet","countertop")): return "kitchen"
    if any(w in text for w in ("fence","yard","gate","picket")): return "fence"
    return "other"


def _send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_OWNER_ID:
        return
    payload = json.dumps({"chat_id": TELEGRAM_OWNER_ID, "text": text, "parse_mode": "Markdown"}).encode()
    try:
        conn = http.client.HTTPSConnection("api.telegram.org", timeout=8)
        conn.request("POST", f"/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                     body=payload, headers={"Content-Type": "application/json"})
        conn.getresponse()
    except Exception:
        pass


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
        messages = body.get("messages", [])[-20:]

        if not messages:
            _cors_headers(self, 400)
            self.wfile.write(json.dumps({"error": "No messages"}).encode())
            return

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        try:
            resp  = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            reply = resp.content[0].text
        except Exception as e:
            _cors_headers(self, 500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        lead          = _extract_lead(messages)
        lead_captured = bool(lead["phone"] and lead["name"])

        if lead_captured:
            _send_telegram(
                f"💬 *ЧАТ — НОВЫЙ ЛИД!*\n"
                f"Имя: {lead['name']}\nТелефон: {lead['phone']}\n"
                f"Услуга: {_guess_service(messages)}\nИсточник: AI чат"
            )

        _cors_headers(self)
        self.wfile.write(json.dumps({
            "reply": reply,
            "lead_captured": lead_captured,
            "service_type": _guess_service(messages),
        }).encode())

    def log_message(self, *args):
        pass  # suppress access logs
