from http.server import BaseHTTPRequestHandler
import os, json, time

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

KIE_API_KEY = os.environ.get("KIE_API_KEY", "")

PROMPTS = {
    "bathroom": (
        "Ultra-realistic professional real-estate listing photograph of a {style} full bathroom remodel, "
        "{colors} color palette, Seattle luxury Pacific Northwest home, large-format porcelain tile floor and walls, "
        "double floating vanity with vessel sinks, frameless glass walk-in shower, natural window daylight, "
        "24mm wide-angle lens f/8 ISO 200 tripod, architectural interior photography, ultra detailed, no people, no text, no watermark"
    ),
    "shower": (
        "Ultra-realistic professional interior design photograph of a {style} walk-in shower conversion, "
        "{colors} color palette, Seattle luxury home, frameless glass enclosure, built-in tile niche, "
        "rain head ceiling fixture, floor-to-ceiling large-format tile, pebble floor, matte black hardware, "
        "natural daylight 24mm lens f/8 ISO 200, architectural photography, ultra detailed, no people, no text"
    ),
    "master": (
        "Ultra-realistic professional interior design photograph of a {style} master bathroom spa retreat, "
        "{colors} color palette, Seattle luxury home, freestanding soaking tub, dual vanity with backlit mirror, "
        "heated tile floor, ambient and natural lighting, 24mm wide-angle lens f/8 ISO 200, "
        "architectural photography, ultra detailed, no people, no text, no watermark"
    ),
}

NEGATIVE = (
    "blurry, low resolution, cartoon, illustration, oversaturated, text, watermark, logo, "
    "people, distorted geometry, clutter, CGI, plastic look, fake lighting, low quality"
)


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

        if service not in PROMPTS:
            service = "bathroom"

        if not KIE_API_KEY:
            return _json(self, {"error": "Image generation not configured."}, 503)

        prompt = PROMPTS[service].format(style=style, colors=colors)

        # Step 1 — create task
        try:
            resp = _req.post(
                "https://api.kie.ai/api/v1/jobs/createTask",
                headers={"Authorization": f"Bearer {KIE_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "nano-banana-2",
                    "input": {
                        "prompt": prompt,
                        "negative_prompt": NEGATIVE,
                        "aspect_ratio": "4:3",
                        "resolution": "1K",
                        "output_format": "jpg"
                    }
                },
                timeout=15,
            )
            resp.raise_for_status()
            task_id = resp.json().get("data", {}).get("taskId")
        except Exception as e:
            return _json(self, {"error": f"Could not start generation: {str(e)}"}, 502)

        if not task_id:
            return _json(self, {"error": "No taskId returned from image API"}, 502)

        # Step 2 — poll for result (max ~51s)
        poll_headers = {"Authorization": f"Bearer {KIE_API_KEY}"}
        for _ in range(17):
            time.sleep(3)
            try:
                poll = _req.get(
                    "https://api.kie.ai/api/v1/jobs/recordInfo",
                    headers=poll_headers,
                    params={"taskId": task_id},
                    timeout=10,
                )
                poll.raise_for_status()
                data = poll.json().get("data", {})
            except Exception:
                continue

            state = data.get("state", "")
            if state in ("success", "completed"):
                try:
                    urls = json.loads(data.get("resultJson", "{}")).get("resultUrls", [])
                    if urls:
                        return _json(self, {"url": urls[0]})
                except Exception:
                    pass
                return _json(self, {"error": "Image ready but URL not found"}, 502)

            if state in ("failed", "error"):
                return _json(self, {"error": "Image generation failed — please try again"}, 502)

        return _json(self, {"error": "Generation timed out — please try again"}, 504)

    def log_message(self, *_):
        pass
