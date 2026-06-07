from http.server import BaseHTTPRequestHandler
import os, json, base64

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

HF_API_KEY = os.environ.get("HF_API_KEY", "")

PROMPTS = {
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

NEGATIVE = "blurry, low quality, watermark, text, cartoon, painting, sketch, distorted, people"

HF_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"


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

        if not HF_API_KEY:
            return _json(self, {
                "error": "HF_API_KEY not configured. Get a free token at huggingface.co → Settings → Access Tokens"
            }, 503)

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

        prompt = PROMPTS[service].format(style=style, colors=colors)

        try:
            resp = _req.post(
                f"https://api-inference.huggingface.co/models/{HF_MODEL}",
                headers={
                    "Authorization": f"Bearer {HF_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": prompt,
                    "parameters": {
                        "negative_prompt": NEGATIVE,
                        "width": 768,
                        "height": 512,
                        "num_inference_steps": 30,
                        "guidance_scale": 7.5,
                    }
                },
                timeout=55,
            )
        except Exception as e:
            return _json(self, {"error": f"Request failed: {str(e)}"}, 502)

        if resp.status_code == 503:
            return _json(self, {"error": "Model loading, please try again in 20 seconds"}, 503)

        if resp.status_code == 429:
            return _json(self, {"error": "Rate limit reached. Please wait a minute and try again."}, 429)

        if resp.status_code != 200:
            return _json(self, {"error": f"HuggingFace error {resp.status_code}: {resp.text[:200]}"}, 502)

        # Response is raw image bytes — convert to base64 data URL
        img_b64 = base64.b64encode(resp.content).decode()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        data_url = f"data:{content_type};base64,{img_b64}"

        return _json(self, {"url": data_url})

    def log_message(self, *_):
        pass
