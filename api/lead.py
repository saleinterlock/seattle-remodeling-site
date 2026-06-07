"""
Lead Notification API — Vercel Serverless Function
POST /api/lead

Receives a lead from the website form or owner dashboard,
sends a Telegram notification to the owner.
"""

from __future__ import annotations

import os
import json
import http.client
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID  = os.environ.get("TELEGRAM_OWNER_ID", "")

SERVICE_LABELS = {
    "bathroom": "🚿 Bathroom Remodel",
    "kitchen":  "🍳 Kitchen Remodel",
    "fence":    "🏡 Fence Installation",
    "other":    "📦 Other",
}

SOURCE_LABELS = {
    "website_form": "📝 Website Form",
    "phone_call":   "📞 Phone Call",
    "chat":         "💬 AI Chat",
    "ghl_webhook":  "🔗 GoHighLevel",
    "manual":       "✍️ Manual Entry",
}


def _send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_OWNER_ID:
        return False
    payload = json.dumps({
        "chat_id": TELEGRAM_OWNER_ID,
        "text": text,
        "parse_mode": "Markdown",
    }).encode("utf-8")
    try:
        conn = http.client.HTTPSConnection("api.telegram.org", timeout=8)
        conn.request(
            "POST",
            f"/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        return resp.status == 200
    except Exception:
        return False


def handler(request):
    if request.method == "OPTIONS":
        return _cors({}, 200)

    try:
        body = request.json
    except Exception:
        return _cors({"error": "Invalid JSON"}, 400)

    name    = (body.get("name") or "").strip()
    phone   = (body.get("phone") or "").strip()
    service = (body.get("service") or "other").strip()
    message = (body.get("message") or "").strip()
    source  = (body.get("source") or "website_form").strip()

    if not name or not phone:
        return _cors({"error": "name and phone are required"}, 400)

    service_label = SERVICE_LABELS.get(service, f"📦 {service.title()}")
    source_label  = SOURCE_LABELS.get(source, f"🔗 {source.replace('_', ' ').title()}")
    now           = datetime.now().strftime("%b %d, %H:%M")

    lines = [
        f"🔔 *НОВЫЙ ЛИД!* {now}",
        f"",
        f"👤 *Имя:* {name}",
        f"📱 *Телефон:* {phone}",
        f"🔧 *Услуга:* {service_label}",
        f"📨 *Источник:* {source_label}",
    ]
    if message:
        lines.append(f"💬 *Сообщение:*\n_{message[:300]}_")

    lines.append("")
    lines.append("👉 Позвони в течение 2 часов!")

    telegram_text = "\n".join(lines)
    sent = _send_telegram(telegram_text)

    return _cors({
        "ok": True,
        "telegram_sent": sent,
        "lead": {"name": name, "phone": phone, "service": service},
    }, 200)


def _cors(data: dict, status: int):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(data),
    }
