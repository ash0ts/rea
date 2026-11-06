"""Drain both output streams while retaining a bounded prefix of each."""
import json
import selectors
import subprocess
import sys

command, deadline = sys.argv[1:]
process = subprocess.Popen(
    ["timeout", "--signal=TERM", "--kill-after=3", deadline, "sh", "-c", command],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
streams = selectors.DefaultSelector()
streams.register(process.stdout, selectors.EVENT_READ, "stdout")
streams.register(process.stderr, selectors.EVENT_READ, "stderr")
buffers = {"stdout": bytearray(), "stderr": bytearray()}
sizes = {"stdout": 0, "stderr": 0}
limit = 65536
while streams.get_map():
    for key, _ in streams.select():
        chunk = key.fileobj.read1(16384)
        if not chunk:
            streams.unregister(key.fileobj)
            key.fileobj.close()
            continue
        sizes[key.data] += len(chunk)
        buffers[key.data].extend(chunk[:max(0, limit - len(buffers[key.data]))])
print(json.dumps({
    "exit_code": process.wait(),
    **{name: data.decode("utf-8", errors="replace") for name, data in buffers.items()},
    "truncated": any(size > limit for size in sizes.values()),
}))
