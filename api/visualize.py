from http.server import BaseHTTPRequestHandler
import os, json, base64

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

SEGMIND_KEY = os.environ.get("SEGMIND_KEY", "")

NEGATIVE = "blurry, low quality, watermark, text, cartoon, painting, sketch, distorted, ugly, people, person"

INSTRUCTIONS = {
    "bathroom": (
        "professional interior design photo of a {style} bathroom renovation, {colors} color palette, "
        "new custom tiles, walk-in shower, modern fixtures, luxury Seattle home, natural lighting, "
        "architectural photography, ultra detailed, no people"
    ),
    "kitchen": (
        "professional interior design photo of a {style} kitchen renovation, {colors} color palette, "
        "new custom cabinetry, quartz countertops, pendant lighting, modern appliances, "
        "luxury Seattle home, architectural photography, ultra detailed, no people"
    ),
    "fence": (
        "professional landscape photo of a beautiful {style} cedar privacy fence and backyard, "
        "{colors} color tones, Pacific Northwest garden, Seattle residential neighborhood, "
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
        image   = body.get("image", "").strip()  # base64 data URL

        if service not in INSTRUCTIONS:
            service = "bathroom"

        if not image:
            return _json(self, {"error": "No image provided."}, 400)

        if not SEGMIND_KEY:
            return _json(self, {
                "error": "Photo redesign not configured. Try without a photo for AI-generated concepts."
            }, 503)

        # Strip data URL prefix → raw base64
        if "," in image:
            image_b64 = image.split(",", 1)[1]
        else:
            image_b64 = image

        prompt = INSTRUCTIONS[service].format(style=style, colors=colors)

        try:
            resp = _req.post(
                "https://api.segmind.com/v1/sdxl1.0-img2img",
                headers={"x-api-key": SEGMIND_KEY, "Content-Type": "application/json"},
                json={
                    "image": image_b64,
                    "prompt": prompt,
                    "negative_prompt": NEGATIVE,
                    "samples": 1,
                    "scheduler": "UniPC",
                    "num_inference_steps": 25,
                    "guidance_scale": 7.5,
                    "strength": 0.75,
                    "img_width": 768,
                    "img_height": 512,
                    "base64": True,
                },
                timeout=58,
            )
        except Exception as e:
            return _json(self, {"error": f"Request failed: {str(e)}"}, 502)

        if resp.status_code == 401:
            return _json(self, {"error": "SEGMIND_KEY invalid"}, 401)

        if resp.status_code == 429:
            return _json(self, {"error": "Daily limit reached (100/day). Try again tomorrow."}, 429)

        if resp.status_code not in (200, 201):
            return _json(self, {"error": f"Segmind error {resp.status_code}: {resp.text[:200]}"}, 502)

        try:
            data = resp.json()
            img_b64 = data.get("image", "")
            if img_b64:
                return _json(self, {"url": f"data:image/jpeg;base64,{img_b64}"})
        except Exception:
            # Response might be raw image bytes
            if resp.content and resp.headers.get("Content-Type", "").startswith("image/"):
                img_b64 = base64.b64encode(resp.content).decode()
                ct = resp.headers.get("Content-Type", "image/jpeg")
                return _json(self, {"url": f"data:{ct};base64,{img_b64}"})

        return _json(self, {"error": "No image in response"}, 502)

    def log_message(self, *_):
        pass
