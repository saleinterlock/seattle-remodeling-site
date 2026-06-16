from http.server import BaseHTTPRequestHandler
import os, json, base64, time  # base64 used for decode+encode, time for warmup sleep

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

HF_KEY        = os.environ.get("HF_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# instruct-pix2pix: takes a photo + text instruction, transforms the room
HF_MODEL = "https://router.huggingface.co/hf-inference/models/timothybrooks/instruct-pix2pix"

INSTRUCTIONS = {
    "bathroom": "Remodel this bathroom with {style} design and {colors} color palette. Add large-format porcelain tile, floating vanity, frameless glass shower, matte black hardware. Make it look like a luxury Seattle renovation. Photorealistic.",
    "shower":   "Convert this bathroom into a {style} walk-in shower with {colors} colors. Add frameless glass enclosure, ceiling rain head, floor-to-ceiling tile, built-in niche. Make it photorealistic and luxurious.",
    "master":   "Transform this into a {style} master bathroom spa with {colors} palette. Add freestanding soaking tub, dual vanity with backlit mirror, heated tile floor. Photorealistic luxury renovation.",
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


def _analyze_room(image_b64, media_type="image/jpeg"):
    if not ANTHROPIC_KEY:
        return ""
    try:
        resp = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                        {"type": "text", "text": "Describe this bathroom in 1 sentence: room size, window, current fixtures. Brief."},
                    ],
                }],
            },
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception:
        return ""


def _hf_img2img(image_data_url, prompt):
    """HuggingFace instruct-pix2pix — free tier."""
    # Extract base64 bytes from data URL
    if "," in image_data_url:
        b64 = image_data_url.split(",", 1)[1]
    else:
        b64 = image_data_url
    headers = {
        "Authorization": f"Bearer {HF_KEY}",
        "Content-Type": "application/json",
        "X-Use-Cache": "false",
    }

    # HF pix2pix API: image as base64 in parameters, prompt as inputs
    payload = {
        "inputs": prompt,
        "parameters": {
            "image": b64,
            "num_inference_steps": 20,
            "image_guidance_scale": 1.5,
            "guidance_scale": 7.0,
        }
    }

    # Model may be loading — retry once after warmup
    for attempt in range(2):
        resp = _req.post(HF_MODEL, headers=headers, json=payload, timeout=50)

        if resp.status_code == 503:
            # Model loading
            try:
                wait = resp.json().get("estimated_time", 20)
            except Exception:
                wait = 20
            if attempt == 0:
                time.sleep(min(wait, 25))
                continue
            raise RuntimeError("HuggingFace model is warming up — please try again in 30 seconds")

        if resp.status_code == 200:
            # Returns image bytes directly
            img_b64 = base64.b64encode(resp.content).decode()
            ct = resp.headers.get("Content-Type", "image/jpeg")
            return f"data:{ct};base64,{img_b64}"

        # Any other error
        try:
            err = resp.json()
        except Exception:
            err = resp.text[:200]
        raise RuntimeError(f"HuggingFace error {resp.status_code}: {err}")

    raise RuntimeError("HuggingFace unavailable — please try again")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _cors(self)

    def do_POST(self):
        try:
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
            image   = body.get("image", "").strip()

            if service not in INSTRUCTIONS:
                service = "bathroom"

            if not image:
                return _json(self, {"error": "No image provided"}, 400)

            if not HF_KEY:
                return _json(self, {"error": "HF_API_KEY not configured"}, 503)

            # Optional Claude room analysis
            room_desc = ""
            if ANTHROPIC_KEY and "," in image:
                hdr, b64 = image.split(",", 1)
                mtype = hdr.split(":")[1].split(";")[0] if ":" in hdr else "image/jpeg"
                room_desc = _analyze_room(b64, mtype)

            base_prompt = INSTRUCTIONS[service].format(style=style, colors=colors)
            prompt = (room_desc + ". " + base_prompt) if room_desc else base_prompt

            data_url = _hf_img2img(image, prompt)
            return _json(self, {"url": data_url})

        except Exception as e:
            return _json(self, {"error": str(e)}, 502)

    def log_message(self, *_):
        pass
