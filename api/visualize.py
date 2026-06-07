from http.server import BaseHTTPRequestHandler
import os, json, time

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

REPLICATE_API_KEY = os.environ.get("REPLICATE_API_KEY", "")

PROMPTS = {
    "bathroom": (
        "professional interior design photo of a {style} bathroom remodel, {colors} color palette, "
        "Seattle luxury home, custom tile work, modern fixtures, natural lighting, architectural photography, "
        "4K ultra-detailed, no people"
    ),
    "kitchen": (
        "professional interior design photo of a {style} kitchen renovation, {colors} color palette, "
        "Seattle luxury home, custom cabinetry, quartz countertops, pendant lighting, architectural photography, "
        "4K ultra-detailed, no people"
    ),
    "fence": (
        "professional landscape photo of a beautiful {style} cedar privacy fence and backyard, "
        "{colors} color tones, Seattle residential neighborhood, lush Pacific Northwest garden, "
        "golden hour lighting, architectural photography, 4K ultra-detailed, no people"
    ),
}

NEGATIVE = (
    "blurry, low quality, watermark, text, ugly, distorted, cartoon, "
    "painting, sketch, 3d render, oversaturated, people, persons"
)


def _cors(handler, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()


def _json(handler, data, status=200):
    _cors(handler, status)
    handler.wfile.write(json.dumps(data).encode())


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _cors(self)

    def do_POST(self):
        if not HAS_REQUESTS:
            return _json(self, {"error": "requests library not available"}, 500)

        if not REPLICATE_API_KEY:
            return _json(self, {
                "error": "REPLICATE_API_KEY not configured. Sign up at replicate.com (free) and add the key to Vercel environment variables."
            }, 503)

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return _json(self, {"error": "Invalid JSON"}, 400)

        service = body.get("service", "bathroom").strip()
        style = body.get("style", "modern minimalist").strip()
        colors = body.get("colors", "white and gray tones").strip()

        if service not in PROMPTS:
            service = "bathroom"

        prompt = PROMPTS[service].format(style=style, colors=colors)

        headers = {
            "Authorization": f"Bearer {REPLICATE_API_KEY}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        }

        # Use SDXL via Replicate
        payload = {
            "input": {
                "prompt": prompt,
                "negative_prompt": NEGATIVE,
                "width": 768,
                "height": 512,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
                "num_outputs": 1,
            }
        }

        try:
            resp = _req.post(
                "https://api.replicate.com/v1/models/stability-ai/sdxl/predictions",
                headers=headers,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            pred = resp.json()
        except Exception as e:
            return _json(self, {"error": f"Replicate API error: {str(e)}"}, 502)

        pred_id = pred.get("id")
        if not pred_id:
            return _json(self, {"error": "No prediction ID returned"}, 502)

        # Poll until done (max 55 seconds)
        for _ in range(27):
            time.sleep(2)
            try:
                status_resp = _req.get(
                    f"https://api.replicate.com/v1/predictions/{pred_id}",
                    headers={"Authorization": f"Bearer {REPLICATE_API_KEY}"},
                    timeout=10,
                )
                status_data = status_resp.json()
            except Exception as e:
                return _json(self, {"error": f"Polling error: {str(e)}"}, 502)

            state = status_data.get("status")
            if state == "succeeded":
                output = status_data.get("output", [])
                if output:
                    return _json(self, {"url": output[0]})
                return _json(self, {"error": "No output in response"}, 502)
            if state == "failed":
                err = status_data.get("error", "Unknown error")
                return _json(self, {"error": f"Generation failed: {err}"}, 502)
            if state == "canceled":
                return _json(self, {"error": "Generation was canceled"}, 502)

        return _json(self, {"error": "Generation timed out. Please try again."}, 504)

    def log_message(self, *args):
        pass
