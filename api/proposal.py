from http.server import BaseHTTPRequestHandler
import os, json

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OWNER_PASSWORD    = os.environ.get("OWNER_PASSWORD", "PRO2026seattle")
COMPANY_NAME      = os.environ.get("COMPANY_NAME", "Seattle Pro Remodeling")

BUDGET_LABELS = {"under_5k": "Under $5,000", "5k_10k": "$5,000–$10,000",
                 "10k_20k": "$10,000–$20,000", "20k_40k": "$20,000–$40,000", "40k_plus": "$40,000+"}

SYSTEM_PROMPT = f"""You are an expert remodeling estimator at {COMPANY_NAME} in Seattle, WA.
Generate a detailed project proposal as HTML (no markdown, no code fences — pure HTML only).

Use these HTML elements: <h2> for sections, <h3> for subsections, <ul>/<ol> for lists,
<table> for cost breakdowns, and this for the estimate:
<div class="estimate-range"><div class="amount">$X,000 – $Y,000</div><div>Estimated project cost</div></div>

Required sections:
1. Project Overview (2-3 sentences)
2. Design Concept (style, materials palette matching client wishes)
3. Scope of Work (detailed list)
4. Materials Recommendations (specific products + why they fit)
5. Cost Estimate (table: labor, materials, permits, contingency, total range)
6. Project Timeline (phase breakdown)
7. Questions for Site Visit
8. Next Steps

Seattle 2026 pricing: Bathroom labor $45-75/hr, tile $3-15/sqft installed, shower $1200-5000+.
Kitchen: cabinets $200-600/lin ft installed, countertop $50-200/sqft. Fence: cedar $25-45/lin ft.
Always give RANGE estimates."""


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

        if body.get("password") != OWNER_PASSWORD:
            _cors_headers(self, 401)
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
            return

        if body.get("check_auth"):
            _cors_headers(self)
            self.wfile.write(json.dumps({"ok": True}).encode())
            return

        client_name  = (body.get("client_name") or "Client").strip()
        service_type = (body.get("service_type") or "bathroom").strip()
        size         = (body.get("size") or "not specified").strip()
        budget_key   = (body.get("budget") or "10k_20k").strip()
        wishes       = (body.get("wishes") or "").strip()
        notes        = (body.get("notes") or "").strip()

        if not wishes:
            _cors_headers(self, 400)
            self.wfile.write(json.dumps({"error": "Client wishes required"}).encode())
            return

        service_label = {"bathroom": "Bathroom Remodel", "kitchen": "Kitchen Remodel",
                         "fence": "Fence Installation"}.get(service_type, service_type.title())

        user_prompt = (
            f"Client: {client_name}\nService: {service_label}\n"
            f"Size: {size}\nBudget: {BUDGET_LABELS.get(budget_key, budget_key)}\n"
            f"Client wishes: {wishes}\nNotes: {notes or 'None'}\n\n"
            "Generate the full proposal HTML now."
        )

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            html = resp.content[0].text.strip()
            # Strip accidental markdown code fences
            if html.startswith("```"):
                html = html.split("```", 2)[-1]
                if html.startswith("html\n"):
                    html = html[5:]
                html = html.rsplit("```", 1)[0].strip()
        except Exception as e:
            _cors_headers(self, 500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())
            return

        _cors_headers(self)
        self.wfile.write(json.dumps({"html": html, "client_name": client_name}).encode())

    def log_message(self, *args):
        pass
