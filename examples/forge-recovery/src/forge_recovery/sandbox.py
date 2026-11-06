from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from .common import BASE_IMAGE, write_json


class Sandbox:
    """Own only the container whose returned ID and attempt label we retained."""

    def __init__(self, workspace: Path, inputs: Path, *, image: str = BASE_IMAGE, owner: str | None = None):
        self.workspace = workspace.resolve()
        self.inputs = inputs.resolve()
        self.image = image
        self.owner = owner or str(uuid.uuid4())
        self.container_id: str | None = None
        self.receipt = self.workspace.parent / (self.workspace.name + ".container.json")

    def start(self) -> "Sandbox":
        self.workspace.mkdir(parents=True, exist_ok=True)
        name = "rea-recovery-" + uuid.uuid4().hex
        write_json(self.receipt, {"owner": self.owner, "name": name, "status": "starting"})
        result = subprocess.run([
            "docker", "run", "-d", "--name", name, "--label", "rea-recovery.owner=" + self.owner,
            "--network", "none", "--cpus", "2", "--memory", "4g", "--pids-limit", "128",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,size=512m", "--mount", f"type=bind,src={self.workspace},dst=/work",
            "--mount", f"type=bind,src={self.inputs},dst=/input,readonly", self.image,
        ], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(f"Container start failed; retain {self.receipt}: {result.stderr.strip()}")
        self.container_id = result.stdout.strip()
        write_json(self.receipt, {"owner": self.owner, "id": self.container_id, "name": name, "status": "running"})
        return self

    def execute(self, command: str, *, timeout: float = 60) -> dict:
        if not self.container_id:
            raise RuntimeError("Container has not started")
        try:
            result = subprocess.run([
                "docker", "exec", "-w", "/work", self.container_id,
                "python", "/opt/recovery/execute.py", command, str(max(1, int(timeout))),
            ], capture_output=True, timeout=timeout + 10)
        except subprocess.TimeoutExpired:
            # The in-container deadline owns the process; the caller stops this container on return.
            return {"exit_code": 124, "stdout": "", "stderr": "Container command deadline expired", "truncated": False}
        if result.returncode:
            raise RuntimeError("Container execution transport failed: " + result.stderr[:4096].decode(errors="replace"))
        return json.loads(result.stdout)

    def resources(self) -> dict:
        result = self.execute("cat /sys/fs/cgroup/cpu.stat; printf '\\nMEMORY_PEAK='; cat /sys/fs/cgroup/memory.peak", timeout=5)
        values = result["stdout"]
        try:
            cpu = next(int(line.split()[1]) for line in values.splitlines() if line.startswith("usage_usec "))
            memory = int(values.split("MEMORY_PEAK=", 1)[1].strip())
            return {"container_cpu_seconds": cpu / 1e6, "container_peak_memory_bytes": memory}
        except (ValueError, IndexError, StopIteration):
            return {"container_cpu_seconds": None, "container_peak_memory_bytes": None, "limitation": "cgroup v2 accounting unavailable"}

    def close(self) -> None:
        if not self.container_id:
            return
        result = subprocess.run(["docker", "inspect", self.container_id], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Cannot establish cleanup ownership; retain {self.receipt}")
        state = json.loads(result.stdout)[0]
        if state["Config"]["Labels"].get("rea-recovery.owner") != self.owner or state["Id"] != self.container_id:
            raise RuntimeError(f"Container identity mismatch; retain {self.receipt}")
        removed = subprocess.run(["docker", "rm", "-f", self.container_id], capture_output=True, text=True)
        if removed.returncode:
            raise RuntimeError(f"Container cleanup failed; retain {self.receipt}: {removed.stderr}")
        write_json(self.receipt, {"owner": self.owner, "id": self.container_id, "status": "removed"})
        self.container_id = None

    def __enter__(self) -> "Sandbox":
        return self.start()

    def __exit__(self, error_type, error, traceback) -> None:
        try:
            self.close()
        except Exception as cleanup:
            if error is not None:
                raise BaseExceptionGroup("Execution and container cleanup failed", [error, cleanup])
            raise
