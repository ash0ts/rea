"""Real-browser regressions, using the same isolated checker image as a campaign.

Set REA_RECOVERY_CHECKER_IMAGE to an existing image ID to run these tests. The
production checker is copied into the container; no candidate or browser code
runs on the credentialed host.
"""
import json
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from forge_recovery.sandbox import Sandbox

IMAGE = os.environ.get("REA_RECOVERY_CHECKER_IMAGE")
pytestmark = pytest.mark.skipif(not IMAGE, reason="Set REA_RECOVERY_CHECKER_IMAGE for real isolated browser verification")


def preview(output, actual_fps, hidden):
    output.mkdir()
    count = 9
    frames = []
    sheet = Image.new("RGBA", (count * 4, 3))
    for i in range(count):
        frame = Image.new("RGBA", (4, 3), (i * 25, 100, 255 - i * 25, 255))
        name = f"frame-{i}.png"
        frame.save(output / name)
        sheet.paste(frame, (i * 4, 0))
        frames.append(name)
    sheet.save(output / "spritesheet.png")
    order = [i for i in range(count) if i not in hidden]
    metadata = {"width": 4, "height": 3, "fps": 13, "frames": frames, "hidden_frames": hidden, "playback_order": order}
    (output / "manifest.json").write_text(json.dumps(metadata))
    html = '''<!doctype html><canvas width="4" height="3"></canvas>
<input aria-label="Frame" type="range" min="0" max="8" value="0">
<button>Play</button><a href="spritesheet.png" download>Download sprite sheet</a>
<script>
const files = FRAMES, order = ORDER, fps = FPS;
const canvas = document.querySelector('canvas'), ctx = canvas.getContext('2d');
const slider = document.querySelector('input'), button = document.querySelector('button');
let playing = false, index = 0, last = 0, elapsed = 0, raf;
const images = files.map(src => { const im = new Image(); im.src = src; return im; });
function show(n) { index = n; slider.value = n; ctx.clearRect(0,0,4,3); ctx.drawImage(images[n],0,0); }
Promise.all(images.map(im => im.decode())).then(() => show(0));
slider.oninput = () => { playing = false; cancelAnimationFrame(raf); button.textContent = 'Play'; show(+slider.value); };
function tick(now) {
 if (!playing) return;
 elapsed += now-last; last = now;
 while (elapsed >= 1000/fps) { elapsed -= 1000/fps; show(order[(order.indexOf(index)+1)%order.length]); }
 raf = requestAnimationFrame(tick);
}
button.onclick = () => {
 playing = !playing; button.textContent = playing ? 'Pause' : 'Play';
 if (playing) { last = performance.now(); elapsed = 0; raf = requestAnimationFrame(tick); }
 else cancelAnimationFrame(raf);
};
</script>'''.replace('FRAMES', json.dumps(frames)).replace('ORDER', json.dumps(order)).replace('FPS', str(actual_fps))
    (output / "index.html").write_text(html)


@pytest.mark.parametrize("actual_fps,hidden,expected", [(13, [], True), (13, [1, 7], True), (7, [], False)])
def test_virtual_clock_owns_time_despite_driver_delay(tmp_path, actual_fps, hidden, expected):
    work = tmp_path / "work"
    work.mkdir()
    inputs = tmp_path / "input"
    inputs.mkdir()
    preview(work / "output", actual_fps, hidden)
    checker = Path(__file__).resolve().parents[1] / "containers/preview_check.py"
    shutil.copyfile(checker, work / "preview_check.py")
    # Delay the driver between manual ticks: this reproduces the measured RPC
    # overhead without changing the production checker or the browser's timers.
    (work / "delayed_check.py").write_text('''import runpy, time
from playwright.sync_api._generated import Clock
original = Clock.run_for
def delayed(self, ticks):
    result = original(self, ticks)
    time.sleep(0.01)
    return result
Clock.run_for = delayed
runpy.run_path('/work/preview_check.py', run_name='__main__')
''')
    with Sandbox(work, inputs, image=IMAGE) as box:
        executed = box.execute("python delayed_check.py", timeout=45)
    assert executed["exit_code"] == 0, executed
    result = json.loads(executed["stdout"])
    assert result["scrubbing"] and result["download"], result
    assert result["playback"] is expected, result
    assert result["passed"] is expected, result
