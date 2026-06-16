from http.server import BaseHTTPRequestHandler
import os, json, time

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

KIE_API_KEY     = os.environ.get("KIE_API_KEY", "")
ANTHROPIC_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")

STYLE_PROMPTS = {
    "bathroom": (
        "Ultra-realistic professional real-estate listing photograph of a fully remodeled {style} bathroom, "
        "{colors} color palette, {room_desc}"
        "large-format porcelain tile floor and walls, floating double vanity, frameless glass walk-in shower, "
        "matte black hardware, natural window daylight, 24mm wide-angle lens f/8 ISO 200 tripod, "
        "architectural interior photography, ultra detailed, no people, no text"
    ),
    "shower": (
        "Ultra-realistic professional interior photo of a {style} walk-in shower conversion, "
        "{colors} color palette, {room_desc}"
        "frameless glass enclosure, built-in tile niche, ceiling rain head, floor-to-ceiling large-format tile, "
        "pebble mosaic floor, matte black hardware, natural daylight, 24mm lens f/8 ISO 200, "
        "architectural photography, ultra detailed, no people, no text"
    ),
    "master": (
        "Ultra-realistic professional interior photograph of a {style} master bathroom spa retreat, "
        "{colors} color palette, {room_desc}"
        "freestanding soaking tub, dual vanity with backlit mirror, heated tile floor, "
        "ambient and natural lighting, 24mm wide-angle lens f/8 ISO 200, "
        "architectural photography, ultra detailed, no people, no text"
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


def _analyze_room(image_b64, media_type="image/jpeg"):
    """Call Claude Vision to extract room layout details from the uploaded photo."""
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
                "max_tokens": 200,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this bathroom's permanent structural features for an interior design rendering prompt. "
                                "Include: room size (small/medium/large), window placement and natural light amount, "
                                "ceiling height (standard/high/vaulted), and current layout (where tub/shower/vanity/toilet are). "
                                "2 sentences max. Be specific and visual. Start with the room size."
                            ),
                        },
                    ],
                }],
            },
            timeout=18,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception:
        return ""


def _kie_generate(prompt):
    """Create a Kie.ai task and poll until done. Returns image URL or raises."""
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
                "output_format": "jpg",
            },
        },
        timeout=15,
    )
    resp.raise_for_status()
    task_id = resp.json().get("data", {}).get("taskId")
    if not task_id:
        raise RuntimeError("No taskId from Kie.ai")

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
            urls = json.loads(data.get("resultJson", "{}")).get("resultUrls", [])
            if urls:
                return urls[0]
            raise RuntimeError("Image ready but URL missing")
        if state in ("failed", "error"):
            raise RuntimeError("Kie.ai generation failed")

    raise RuntimeError("Generation timed out")


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
        image   = body.get("image", "").strip()   # base64 data URL, optional

        if service not in STYLE_PROMPTS:
            service = "bathroom"

        if not KIE_API_KEY:
            return _json(self, {"error": "Image generation not configured."}, 503)

        # If user uploaded a photo — analyze it with Claude Vision
        room_desc = ""
        if image and ANTHROPIC_KEY:
            if "," in image:
                header, image_b64 = image.split(",", 1)
                media_type = header.split(":")[1].split(";")[0] if ":" in header else "image/jpeg"
            else:
                image_b64 = image
                media_type = "image/jpeg"

            room_context = _analyze_room(image_b64, media_type)
            if room_context:
                room_desc = room_context + ", "

        prompt = STYLE_PROMPTS[service].format(
            style=style,
            colors=colors,
            room_desc=room_desc,
        )

        try:
            url = _kie_generate(prompt)
            return _json(self, {"url": url})
        except Exception as e:
            return _json(self, {"error": str(e)}, 502)

    def log_message(self, *_):
        pass
