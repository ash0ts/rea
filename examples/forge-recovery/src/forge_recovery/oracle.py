from __future__ import annotations

import base64
import functools
import http.server
import threading
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

from .common import FAMILIES, write_json


@contextmanager
def serve(directory: Path):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def generate(reference: Path, destination: Path, script: Path) -> dict:
    """Use Piskel's model, serializer and renderer, rather than a second decoder."""
    outputs = {}
    with serve(reference) as url, sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url)
            page.wait_for_function("window.pskl && pskl.app && pskl.app.piskelController")
            page.evaluate(script.read_text())
            for family in (*FAMILIES, "qualification"):
                for seed, kind in ((17, "visible"), (83, "heldout")):
                    result = page.evaluate("([family, seed]) => window.makeRecoveryFixture(family, seed)", [family, seed])
                    folder = destination / family / kind
                    folder.mkdir(parents=True, exist_ok=True)
                    write_json(folder / "animation.piskel", result["saved"])
                    frames = result.pop("frames")
                    layer_frames = result.pop("layers")
                    result.pop("saved")
                    for i, encoded in enumerate(frames):
                        (folder / f"frame-{i:03}.png").write_bytes(base64.b64decode(encoded.split(",", 1)[1]))
                    for layer, encoded_frames in enumerate(layer_frames):
                        for i, encoded in enumerate(encoded_frames):
                            (folder / f"layer-{layer}-{i:03}.png").write_bytes(base64.b64decode(encoded.split(",", 1)[1]))
                    write_json(folder / "expected.json", result)
                    outputs[f"{family}/{kind}"] = result
            version = browser.version
        finally:
            browser.close()
    return {"browser_version": version, "cases": outputs}
