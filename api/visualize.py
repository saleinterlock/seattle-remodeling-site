from http.server import BaseHTTPRequestHandler
import os, json, time

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

REPLICATE_KEY = os.environ.get("REPLICATE_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# instruct-pix2pix — takes a photo + instruction, transforms it
PIX2PIX_VERSION = "30c1d0b916a6f8efce20493f5d61ee27491ab2a60437c13c588468b9810ec23d"

INSTRUCTIONS = {
    "bathroom": "Transform this bathroom into a fully remodeled {style} bathroom with {colors} color palette. New large-format porcelain tile, floating vanity, frameless glass shower, matte black hardware. Photorealistic, architectural photography, no people.",
    "shower":   "Transform this bathroom into a {style} walk-in shower with {colors} colors. Frameless glass enclosure, ceiling rain head, floor-to-ceiling tile, built-in niche. Photorealistic, architectural photography, no people.",
    "master":   "Transform this bathroom into a luxurious {style} master spa with {colors} palette. Freestanding tub, dual vanity, backlit mirror, heated tile floor. Photorealistic, architectural photography, no people.",
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
                "max_tokens": 120,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                        {"type": "text", "text": "Describe this bathroom layout in 1 sentence: room size, window placement, current fixture positions. Be brief and specific."},
                    ],
                }],
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception:
        return ""


def _replicate_img2img(image_data_url, prompt):
    headers = {
        "Authorization": f"Token {REPLICATE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "wait=55",
    }

    # Create prediction
    resp = _req.post(
        "https://api.replicate.com/v1/predictions",
        headers=headers,
        json={
            "version": PIX2PIX_VERSION,
            "input": {
                "image": image_data_url,
                "prompt": prompt,
                "negative_prompt": "blurry, low quality, cartoon, watermark, text, people, clutter, distorted",
                "image_guidance_scale": 1.5,
                "guidance_scale": 7.5,
                "num_inference_steps": 25,
                "num_outputs": 1,
            },
        },
        timeout=15,
    )
    resp.raise_for_status()
    prediction = resp.json()

    # If Prefer: wait worked, might already be done
    if prediction.get("status") == "succeeded":
        output = prediction.get("output") or []
        if output:
            return output[0]

    pred_id = prediction.get("id")
    if not pred_id:
        raise RuntimeError(f"No prediction ID: {json.dumps(prediction)[:200]}")

    # Poll for result
    poll_url = f"https://api.replicate.com/v1/predictions/{pred_id}"
    for _ in range(16):
        time.sleep(3)
        try:
            poll = _req.get(poll_url, headers={"Authorization": f"Token {REPLICATE_KEY}"}, timeout=10)
            poll.raise_for_status()
            data = poll.json()
        except Exception:
            continue

        status = data.get("status", "")
        if status == "succeeded":
            output = data.get("output") or []
            if output:
                return output[0]
            raise RuntimeError("No output URL in succeeded prediction")
        if status == "failed":
            raise RuntimeError(f"Replicate prediction failed: {data.get('error', 'unknown')}")

    raise RuntimeError("Generation timed out — please try again")


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

            if not REPLICATE_KEY:
                return _json(self, {"error": "Image transformation not configured (REPLICATE_API_KEY missing)"}, 503)

            # Optional: enrich prompt with Claude room analysis
            room_desc = ""
            if ANTHROPIC_KEY and "," in image:
                header_part, b64 = image.split(",", 1)
                mtype = header_part.split(":")[1].split(";")[0] if ":" in header_part else "image/jpeg"
                room_desc = _analyze_room(b64, mtype)

            base_instruction = INSTRUCTIONS[service].format(style=style, colors=colors)
            prompt = (room_desc + ". " + base_instruction) if room_desc else base_instruction

            url = _replicate_img2img(image, prompt)
            return _json(self, {"url": url})

        except Exception as e:
            return _json(self, {"error": str(e)}, 502)

    def log_message(self, *_):
        pass
