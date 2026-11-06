"""Durable reservations: an interrupted/unknown request retains its full charge."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .common import read_json, write_json

INPUT_USD_PER_MILLION = 0.71
OUTPUT_USD_PER_MILLION = 3.50
# Reserve a complete model context, including server-side prompt/tool framing.
CONTEXT_LIMIT = 262144
OUTPUT_LIMIT = 8192
REQUEST_RESERVATION = (CONTEXT_LIMIT * INPUT_USD_PER_MILLION + OUTPUT_LIMIT * OUTPUT_USD_PER_MILLION) / 1e6


class BudgetStop(Exception):
    pass


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = read_json(self.path) if self.path.exists() else {
                "ceiling_usd": 150, "attempts_ceiling_usd": 130,
                "notebook_reservation_usd": 20, "requests": [],
            }
            yield state
            write_json(self.path, state)

    def reserve(self, attempt: str) -> str:
        with self.locked() as state:
            rows = state["requests"]
            own = [r for r in rows if r["attempt_id"] == attempt]
            if len(own) >= 40 or sum(r["charge_usd"] for r in own) + REQUEST_RESERVATION > 5:
                raise BudgetStop("Attempt request/cost ceiling reached")
            if sum(r["charge_usd"] for r in rows) + REQUEST_RESERVATION > state["attempts_ceiling_usd"]:
                raise BudgetStop("Campaign execution ceiling reached")
            key = uuid4().hex
            rows.append({"id": key, "attempt_id": attempt, "charge_usd": REQUEST_RESERVATION,
                         "state": "reserved", "usage": None})
            return key

    def settle(self, key: str, usage: dict | None) -> float:
        with self.locked() as state:
            row = next(r for r in state["requests"] if r["id"] == key)
            if row["state"] != "reserved":
                raise ValueError("Reservation already settled")
            if usage is None:
                row["state"] = "unknown_charge"
            else:
                # Conservatively charge cached input at the uncached rate.
                cost = (usage["prompt_tokens"] * INPUT_USD_PER_MILLION + usage["completion_tokens"] * OUTPUT_USD_PER_MILLION) / 1e6
                if cost > row["charge_usd"]:
                    raise BudgetStop("Provider usage exceeded the pre-request reservation; stop and reconcile")
                row.update(state="settled", charge_usd=cost, usage=usage)
            return row["charge_usd"]

    def summary(self, attempt: str | None = None) -> dict:
        with self.locked() as state:
            rows = [r for r in state["requests"] if attempt is None or r["attempt_id"] == attempt]
            known = [r for r in rows if r["usage"] is not None]
            return {
                "requests": len(rows), "reserved_or_estimated_usd": sum(r["charge_usd"] for r in rows),
                "unknown_usage_requests": len(rows) - len(known),
                "input_tokens": sum(r["usage"]["prompt_tokens"] for r in known),
                "output_tokens": sum(r["usage"]["completion_tokens"] for r in known),
                "cost_basis": "Published uncached input/output rates; unknown calls retain full reservation",
            }
