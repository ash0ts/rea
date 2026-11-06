from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from .common import BASE_IMAGE, write_json


class SandboxTransportError(RuntimeError):
    """Docker management/transport failed; this is not a candidate command exit."""


class Sandbox:
    """Own only the container whose returned ID and attempt label we retained."""

    def __init__(self, workspace: Path, inputs: Path, *, image: str = BASE_IMAGE, owner: str | None = None):
        self.workspace = workspace.resolve()
        self.inputs = inputs.resolve()
        self.image = image
        self.owner = owner or str(uuid.uuid4())
        self.container_id: str | None = None
        self.start_pending = False
        self.receipt = self.workspace.parent / (self.workspace.name + ".container.json")

    def _docker(self, operation: str, arguments: list[str], *, timeout: float, **kwargs):
        try:
            return subprocess.run(["docker", *arguments], timeout=timeout, **kwargs)
        except subprocess.TimeoutExpired as error:
            raise SandboxTransportError(
                f"Docker {operation} did not respond within {timeout:g}s; retain {self.receipt}"
            ) from error

    def start(self) -> "Sandbox":
        self.workspace.mkdir(parents=True, exist_ok=True)
        name = "rea-recovery-" + uuid.uuid4().hex
        write_json(self.receipt, {"owner": self.owner, "name": name, "status": "starting"})
        self.start_pending = True
        result = self._docker("start", [
            "run", "-d", "--name", name, "--label", "rea-recovery.owner=" + self.owner,
            "--network", "none", "--cpus", "2", "--memory", "4g", "--pids-limit", "128",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,size=512m", "--mount", f"type=bind,src={self.workspace},dst=/work",
            "--mount", f"type=bind,src={self.inputs},dst=/input,readonly", self.image,
        ], timeout=30, text=True, capture_output=True)
        if result.returncode:
            raise SandboxTransportError(f"Container start failed; retain {self.receipt}: {result.stderr.strip()}")
        self.container_id = result.stdout.strip()
        self.start_pending = False
        write_json(self.receipt, {"owner": self.owner, "id": self.container_id, "name": name, "status": "running"})
        return self

    def execute(self, command: str, *, timeout: float = 60) -> dict:
        if not self.container_id:
            raise RuntimeError("Container has not started")
        result = self._docker("execute", [
            "exec", "-w", "/work", self.container_id,
            "python", "/opt/recovery/execute.py", command, str(max(1, int(timeout))),
        ], capture_output=True, timeout=timeout + 10)
        if result.returncode:
            raise SandboxTransportError("Container execution transport failed: " + result.stderr[:4096].decode(errors="replace"))
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
            if self.start_pending:
                raise RuntimeError(f"Container startup identity is unresolved; retain {self.receipt} for cleanup retry")
            return
        result = self._docker("inspect for cleanup", ["inspect", self.container_id], timeout=15, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Cannot establish cleanup ownership; retain {self.receipt}")
        state = json.loads(result.stdout)[0]
        if state["Config"]["Labels"].get("rea-recovery.owner") != self.owner or state["Id"] != self.container_id:
            raise RuntimeError(f"Container identity mismatch; retain {self.receipt}")
        removed = self._docker("remove", ["rm", "-f", self.container_id], timeout=15, capture_output=True, text=True)
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
