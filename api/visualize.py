from http.server import BaseHTTPRequestHandler
import os, json, base64

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

FAL_KEY = os.environ.get("FAL_KEY", "")

INSTRUCTIONS = {
    "bathroom": (
        "Transform this bathroom with a complete {style} renovation: new custom tile work, "
        "{colors} color palette, walk-in shower, modern fixtures, heated floor, luxury Seattle home quality, "
        "professional architectural photography, ultra realistic, no people"
    ),
    "kitchen": (
        "Renovate this kitchen with {style} design: new custom cabinetry, "
        "{colors} color palette, quartz countertops, pendant lighting, modern appliances, "
        "luxury Seattle home quality, professional architectural photography, ultra realistic, no people"
    ),
    "fence": (
        "Replace the fence and redesign this yard with {style} landscaping: "
        "cedar privacy fence, {colors} color tones, Pacific Northwest native plants, "
        "stone pathway, golden hour lighting, professional photography, ultra realistic, no people"
    ),
}

# Fallback text-to-image prompts (used when no image uploaded, server-side path)
TXT_PROMPTS = {
    "bathroom": (
        "professional interior design photo of a {style} bathroom remodel, {colors} color palette, "
        "Seattle luxury home, custom tile work, walk-in shower, modern fixtures, natural lighting, "
        "architectural photography, ultra detailed, no people"
    ),
    "kitchen": (
        "professional interior design photo of a {style} kitchen renovation, {colors} color palette, "
        "Seattle luxury home, custom cabinetry, quartz countertops, pendant lighting, "
        "architectural photography, ultra detailed, no people"
    ),
    "fence": (
        "professional landscape photo of a beautiful {style} cedar privacy fence and backyard, "
        "{colors} color tones, Seattle residential neighborhood, Pacific Northwest garden, "
        "golden hour lighting, architectural photography, ultra detailed, no people"
    ),
}


def _cors(h, status=200):
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.end_headers()


def _json(h, data, status=200):
    _cors(h, status)
    h.wfile.write(json.dumps(data).encode())


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _cors(self)

    def do_POST(self):
        if not HAS_REQUESTS:
            return _json(self, {"error": "requests library not available"}, 500)

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return _json(self, {"error": "Invalid JSON"}, 400)

        service = body.get("service", "bathroom").strip()
        style   = body.get("style", "modern minimalist").strip()
        colors  = body.get("colors", "white and gray tones").strip()
        image   = body.get("image", "").strip()  # base64 data URL from browser

        if service not in INSTRUCTIONS:
            service = "bathroom"

        if not image:
            return _json(self, {"error": "No image provided. Use frontend text-to-image mode."}, 400)

        # ── IMG2IMG via Fal.ai FLUX Kontext ──────────────────────────
        if not FAL_KEY:
            return _json(self, {
                "error": "Photo redesign not configured yet. Try without a photo for AI-generated concepts."
            }, 503)

        instruction = INSTRUCTIONS[service].format(style=style, colors=colors)

        try:
            resp = _req.post(
                "https://fal.run/fal-ai/flux-pro/kontext",
                headers={
                    "Authorization": f"Key {FAL_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "image_url": image,
                    "prompt": instruction,
                    "guidance_scale": 3.5,
                    "num_images": 1,
                    "safety_tolerance": "2",
                },
                timeout=58,
            )
        except Exception as e:
            return _json(self, {"error": f"Request failed: {str(e)}"}, 502)

        if resp.status_code == 401:
            return _json(self, {"error": "FAL_KEY invalid — check Vercel env vars"}, 401)

        if resp.status_code == 402:
            return _json(self, {"error": "Fal.ai credit exhausted — top up at fal.ai/dashboard"}, 402)

        if resp.status_code == 422:
            return _json(self, {"error": f"Invalid request: {resp.text[:200]}"}, 422)

        if resp.status_code not in (200, 201):
            return _json(self, {"error": f"Fal.ai error {resp.status_code}: {resp.text[:200]}"}, 502)

        try:
            data = resp.json()
            images = data.get("images") or data.get("output") or []
            if images:
                url = images[0].get("url") or images[0]
                return _json(self, {"url": url})
            return _json(self, {"error": "No image in response"}, 502)
        except Exception:
            return _json(self, {"error": "Failed to parse Fal.ai response"}, 502)

    def log_message(self, *_):
        pass
