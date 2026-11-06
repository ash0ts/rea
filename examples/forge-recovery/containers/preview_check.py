"""Check the delivered UI inside an isolated, credential-free browser container."""
import base64
import functools
import http.server
import io
import json
import threading
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

root = Path("/work/output")
metadata = json.loads((root / "manifest.json").read_text())
result = {"scrubbing": False, "playback": False, "download": False, "errors": []}
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root)))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
origin = f"http://127.0.0.1:{server.server_port}"
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(accept_downloads=True)
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort())
        page.goto(origin + "/index.html")
        page.wait_for_function("document.querySelector('canvas')?.width > 0")
        slider = page.get_by_role("slider", name="Frame", exact=True)
        slider.wait_for()
        for i, frame_name in enumerate(metadata["frames"]):
            slider.evaluate("(el, n) => { el.value = n; el.dispatchEvent(new Event('input', {bubbles: true})); }", i)
            # Decode completes independently of rendering; wait for the selected canvas pixels.
            expected = Image.open(root / frame_name).convert("RGBA")
            for retry in range(30):
                data = page.locator("canvas").first.evaluate("c => c.toDataURL('image/png')")
                observed = Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGBA")
                if observed.size == expected.size and ImageChops.difference(observed, expected).getbbox(alpha_only=False) is None:
                    break
                page.wait_for_timeout(50)
            else:
                raise ValueError(f"Canvas differs at frame {i}")
        result["scrubbing"] = True
        page.clock.install()
        slider.evaluate("el => { el.value = 0; el.dispatchEvent(new Event('input', {bubbles: true})); }")
        page.get_by_role("button", name="Play", exact=True).click()
        seen = set()
        for _ in range(len(metadata["frames"]) * 3):
            page.clock.run_for(max(1, int(1000 / metadata["fps"] / 2)))
            seen.add(int(slider.input_value()))
        page.get_by_role("button", name="Pause", exact=True).click()
        result["playback"] = len(seen) > 1 and not seen.intersection(metadata["hidden_frames"])
        with page.expect_download() as download:
            page.get_by_role("link", name="Download sprite sheet", exact=True).click()
        saved = Path("/tmp/download.png")
        download.value.save_as(saved)
        expected_sheet = Image.open(root / "spritesheet.png").convert("RGBA")
        downloaded = Image.open(saved).convert("RGBA")
        result["download"] = downloaded.size == expected_sheet.size and ImageChops.difference(downloaded, expected_sheet).getbbox(alpha_only=False) is None
        browser.close()
except Exception as error:
    result["errors"].append(f"{type(error).__name__}: {error}")
finally:
    server.shutdown()
    server.server_close()
result["passed"] = all(result[key] for key in ("scrubbing", "playback", "download"))
print(json.dumps(result))
