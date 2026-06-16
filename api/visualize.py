from http.server import BaseHTTPRequestHandler
import os, json

try:
    import requests as _req
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

FAL_KEY       = os.environ.get("FAL_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

STYLE_PROMPTS = {
    "bathroom": (
        "professional interior design photo of a completely remodeled {style} bathroom, "
        "{colors} color palette, large-format porcelain tile, floating vanity, frameless glass shower, "
        "matte black hardware, Seattle luxury home, natural daylight, architectural photography, "
        "ultra detailed, no people, no text, photorealistic"
    ),
    "shower": (
        "professional interior design photo of a brand new {style} walk-in shower, "
        "{colors} color palette, frameless glass enclosure, built-in tile niche, rain ceiling head, "
        "floor-to-ceiling tile, matte black fixtures, Seattle luxury home, natural daylight, "
        "architectural photography, ultra detailed, no people, no text, photorealistic"
    ),
    "master": (
        "professional interior design photo of a luxurious {style} master bathroom spa, "
        "{colors} color palette, freestanding soaking tub, dual vanity with backlit mirror, "
        "heated tile floor, ambient lighting, Seattle luxury home, architectural photography, "
        "ultra detailed, no people, no text, photorealistic"
    ),
}

NEGATIVE = (
    "blurry, low quality, cartoon, watermark, text, logo, people, clutter, "
    "distorted, ugly, before remodel, old bathroom, unfinished"
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
    """Use Claude Vision to extract room layout for prompt personalization."""
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
                "max_tokens": 150,
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
                                "Describe this bathroom's permanent layout in 1 short sentence for a renovation rendering: "
                                "room size, window placement, and fixture positions. Be specific and brief."
                            ),
                        },
                    ],
                }],
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception:
        return ""


def _fal_img2img(image_data_url, prompt):
    """Fal.ai FLUX img2img — transforms user photo to remodeled version."""
    resp = _req.post(
        "https://fal.run/fal-ai/flux/dev/image-to-image",
        headers={
            "Authorization": f"Key {FAL_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "image_url": image_data_url,
            "prompt": prompt,
            "negative_prompt": NEGATIVE,
            "strength": 0.80,
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "num_images": 1,
            "output_format": "jpeg",
            "enable_safety_checker": False,
        },
        timeout=55,
    )
    resp.raise_for_status()
    data = resp.json()
    images = data.get("images") or []
    if images:
        return images[0].get("url", "")
    raise RuntimeError(f"No image in Fal.ai response: {json.dumps(data)[:200]}")


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

            if service not in STYLE_PROMPTS:
                service = "bathroom"

            if not image:
                return _json(self, {"error": "No image provided"}, 400)

            if not FAL_KEY:
                return _json(self, {"error": "Image transformation not configured (FAL_KEY missing)"}, 503)

            # Analyze room layout with Claude (optional enrichment)
            room_desc = ""
            if ANTHROPIC_KEY and "," in image:
                header_part, b64 = image.split(",", 1)
                mtype = header_part.split(":")[1].split(";")[0] if ":" in header_part else "image/jpeg"
                room_desc = _analyze_room(b64, mtype)

            prompt = STYLE_PROMPTS[service].format(style=style, colors=colors)
            if room_desc:
                prompt = room_desc + ", fully remodeled as: " + prompt

            url = _fal_img2img(image, prompt)
            if url:
                return _json(self, {"url": url})
            return _json(self, {"error": "Generation failed — no image returned"}, 502)

        except Exception as e:
            return _json(self, {"error": str(e)}, 502)

    def log_message(self, *_):
        pass
