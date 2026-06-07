"""
AI Chat API — Vercel Serverless Function
POST /api/chat

Handles AI chat widget messages. Uses Claude Haiku to play "Alex",
a project coordinator who qualifies leads conversationally.
When name + phone are collected, fires a Telegram notification.
"""

from __future__ import annotations

import os
import json
import re
import http.client
from urllib.parse import urlencode

import anthropic

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID   = os.environ.get("TELEGRAM_OWNER_ID", "")
COMPANY_NAME        = os.environ.get("COMPANY_NAME", "Seattle Pro Remodeling")
COMPANY_PHONE       = os.environ.get("COMPANY_PHONE", "(206) 555-0000")
SERVICE_AREA_ZIPS   = os.environ.get("SERVICE_AREA_ZIPS", "98101,98103,98105,98107,98109,98115,98117,98119,98121,98122,98125,98126,98133,98136,98144")

SYSTEM_PROMPT = f"""You are Alex, a friendly project coordinator at {COMPANY_NAME} in Seattle.

Your job is to qualify potential customers through a natural, friendly chat conversation.
You work for a remodeling company that does: Bathroom Remodels, Kitchen Remodels, Fence Installation.

## Your Goal
Collect this information naturally (NOT all at once — ask one thing at a time):
1. What type of project they need (bathroom / kitchen / fence / other)
2. Their ZIP code or neighborhood
3. Brief project description
4. Rough budget range
5. Timeline (ASAP / 1-3 months / just exploring)
6. Their name and phone number (ask this near the end, before wrapping up)

## Tone & Style
- Sound like a real, friendly human — not a chatbot
- Keep messages short (2-4 sentences max per reply)
- Show genuine interest in their project
- Use casual language, occasional emojis are fine
- Ask ONE question per message

## Rules
- Never give specific prices — say "our estimator will give you an exact number after seeing your space"
- Never say you're an AI
- If ZIP is outside Seattle area, say "Let me check on that — can you give me the full address?"
- If they seem ready to schedule, say the project manager will call them within 2 hours

## When to wrap up
Once you have name + phone, confirm: "Perfect! I have everything I need. Our project manager will
call you at [phone] within 2 hours to schedule your free estimate. Looking forward to working with you!"

Service area ZIPs: {SERVICE_AREA_ZIPS}
Our phone: {COMPANY_PHONE}
"""

_PHONE_RE = re.compile(r'(\+?1?\s*[\(\-\.]?\d{{3}}[\)\-\.\s]\s*\d{{3}}[\-\.\s]\d{{4}})')
_NAME_RE  = re.compile(r"(?:i'?m|my name is|name'?s|this is|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.I)


def _extract_lead(messages: list[dict]) -> dict:
    """Try to extract name and phone from conversation history."""
    full_text = " ".join(m.get("content", "") for m in messages)
    phone_match = _PHONE_RE.search(full_text)
    name_match  = _NAME_RE.search(full_text)
    return {
        "phone": phone_match.group(0).strip() if phone_match else "",
        "name":  name_match.group(1).strip()  if name_match  else "",
    }


def _send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_OWNER_ID:
        return
    payload = json.dumps({"chat_id": TELEGRAM_OWNER_ID, "text": text, "parse_mode": "Markdown"}).encode()
    conn = http.client.HTTPSConnection("api.telegram.org")
    conn.request("POST", f"/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                 body=payload, headers={"Content-Type": "application/json"})
    conn.getresponse()


def handler(request):
    if request.method == "OPTIONS":
        return _cors({}, 200)

    try:
        body = request.json
    except Exception:
        return _cors({"error": "Invalid JSON"}, 400)

    messages: list[dict] = body.get("messages", [])
    if not messages:
        return _cors({"error": "No messages provided"}, 400)

    # Truncate history to last 20 messages to keep context manageable
    messages = messages[-20:]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        reply = resp.content[0].text
    except Exception as e:
        return _cors({"error": str(e)}, 500)

    # Check if we just collected name + phone in the latest exchange
    lead = _extract_lead(messages)
    lead_captured = bool(lead["phone"] and lead["name"])

    # Send Telegram notification on first capture
    if lead_captured:
        # Check if we already sent one (look for prior confirmation in messages)
        prev_user_msgs = [m["content"] for m in messages if m["role"] == "user"]
        already_sent   = any("call you" in (m or "") for m in prev_user_msgs[-4:])
        if not already_sent:
            service_hint = _guess_service(messages)
            msg = (
                f"💬 *ЧАТ — НОВЫЙ ЛИД!*\n"
                f"Имя: {lead['name']}\n"
                f"Телефон: {lead['phone']}\n"
                f"Услуга: {service_hint}\n"
                f"Источник: AI чат на сайте"
            )
            _send_telegram(msg)

    return _cors({
        "reply": reply,
        "lead_captured": lead_captured,
        "service_type": _guess_service(messages),
    }, 200)


def _guess_service(messages: list[dict]) -> str:
    text = " ".join(m.get("content", "").lower() for m in messages)
    if "bathroom" in text or "bath" in text or "shower" in text:
        return "bathroom"
    if "kitchen" in text or "cabinet" in text or "countertop" in text:
        return "kitchen"
    if "fence" in text or "yard" in text or "gate" in text:
        return "fence"
    return "other"


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
