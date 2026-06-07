"""
Proposal Generator API — Vercel Serverless Function
POST /api/proposal

Owner-only endpoint. Generates a detailed project proposal using Claude Sonnet.
Returns formatted HTML ready to display in the owner dashboard.

Requires: ANTHROPIC_API_KEY, OWNER_PASSWORD in Vercel env vars.
"""

from __future__ import annotations

import os
import json

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OWNER_PASSWORD    = os.environ.get("OWNER_PASSWORD", "seattle2026")
COMPANY_NAME      = os.environ.get("COMPANY_NAME", "Seattle Pro Remodeling")

BUDGET_LABELS = {
    "under_5k":  "Under $5,000",
    "5k_10k":    "$5,000 – $10,000",
    "10k_20k":   "$10,000 – $20,000",
    "20k_40k":   "$20,000 – $40,000",
    "40k_plus":  "$40,000+",
}

SYSTEM_PROMPT = f"""You are an expert remodeling estimator and design consultant at {COMPANY_NAME} in Seattle, WA.

Your job is to generate a detailed, professional project proposal based on the client's information.
The proposal will be shown to the business owner as an internal planning document and optionally shared with the client.

## Output Format
Return ONLY valid HTML (no markdown, no code blocks, no explanation outside HTML).
Use inline styles sparingly — the page already has CSS. Use these classes:
- <h2> for major sections
- <h3> for subsections
- <ul> / <ol> for lists
- <table> for cost breakdowns (use standard HTML table — CSS will style it)
- For the estimate range: <div class="estimate-range"><div class="amount">$X,000 – $Y,000</div><div>Estimated project cost</div></div>

## Proposal Sections (always include all):
1. **Project Overview** — 2-3 sentences summarizing the project
2. **Design Concept** — describe the style, aesthetic, materials palette that matches client wishes
3. **Scope of Work** — detailed list of everything included
4. **Materials Recommendations** — specific materials with brand suggestions and why they fit
5. **Cost Estimate** — table with line items (labor, materials, permits) + total range
6. **Project Timeline** — day-by-day or phase breakdown
7. **Questions for Site Visit** — list of things to verify on-site before finalizing
8. **Next Steps** — what happens after estimate approval

## Seattle Market Pricing Reference (2026):
- Bathroom: Labor $45-75/hr, tile $3-15/sqft installed, vanity $300-3000, shower $1200-5000+
- Kitchen: Cabinets $200-600/linear ft installed, countertop $50-200/sqft installed, appliances $2000-15000+
- Fence: Cedar $25-45/lin ft installed, composite $35-60/lin ft, vinyl $20-40/lin ft, posts $40-80 each

Always give RANGE estimates, never exact numbers. Be honest about what increases cost.
"""


def handler(request):
    if request.method == "OPTIONS":
        return _cors({}, 200)

    try:
        body = request.json
    except Exception:
        return _cors({"error": "Invalid JSON"}, 400)

    # Auth check
    password = body.get("password", "")
    if password != OWNER_PASSWORD:
        return _cors({"error": "Unauthorized"}, 401)

    # Auth-only check (from owner.html login)
    if body.get("check_auth"):
        return _cors({"ok": True}, 200)

    client_name  = (body.get("client_name") or "Client").strip()
    service_type = (body.get("service_type") or "bathroom").strip()
    size         = (body.get("size") or "not specified").strip()
    budget_key   = (body.get("budget") or "10k_20k").strip()
    wishes       = (body.get("wishes") or "").strip()
    notes        = (body.get("notes") or "").strip()

    if not wishes:
        return _cors({"error": "Client wishes are required"}, 400)

    budget_label   = BUDGET_LABELS.get(budget_key, budget_key)
    service_labels = {"bathroom": "Bathroom Remodel", "kitchen": "Kitchen Remodel", "fence": "Fence Installation"}
    service_label  = service_labels.get(service_type, service_type.title())

    user_prompt = f"""Generate a complete project proposal for the following client:

CLIENT: {client_name}
SERVICE: {service_label}
SIZE / DIMENSIONS: {size}
BUDGET RANGE: {budget_label}
CLIENT'S WISHES & STYLE: {wishes}
ADDITIONAL NOTES: {notes if notes else "None"}

Generate the full proposal HTML now."""

    client_obj = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        resp = client_obj.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        html = resp.content[0].text.strip()

        # Strip markdown code fences if model accidentally wrapped output
        if html.startswith("```"):
            html = html.split("```", 2)[-1]
            if html.startswith("html\n"):
                html = html[5:]
            html = html.rsplit("```", 1)[0].strip()

    except Exception as e:
        return _cors({"error": f"Claude API error: {e}"}, 500)

    return _cors({"html": html, "client_name": client_name, "service": service_type}, 200)


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
