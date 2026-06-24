"""Run tracer — records every agent run as a JSONL entry.

Each line in data/traces/traces.jsonl is one complete run:
  query, tool calls (name/args/result/latency), iterations,
  final diagnosis, token usage, and total latency.

Used by the eval harness (Milestone 6) to score citation recall
and diagnosis accuracy without re-running the agent.

Usage:
    tracer = Tracer()
    diagnosis = run(query, tracer=tracer)
    tracer.save()
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).parent.parent
TRACES_FILE = _ROOT / "data" / "traces" / "traces.jsonl"


class Tracer:
    """Collects events for one agent run, then writes a single JSONL record."""

    def __init__(self) -> None:
        self._run_id = str(uuid.uuid4())
        self._timestamp = datetime.now(timezone.utc).isoformat()
        self._query: str = ""
        self._tool_calls: list[dict] = []
        self._iterations: int = 0
        self._diagnosis: dict = {}
        self._usage: dict = {}
        self._t_start = time.time()

    # ------------------------------------------------------------------
    # Event recording methods (called by loop.py)
    # ------------------------------------------------------------------

    def start(self, query: str) -> None:
        self._query = query
        self._t_start = time.time()

    def record_tool_call(
        self,
        name: str,
        args: dict,
        result: dict,
        latency_ms: int,
    ) -> None:
        self._tool_calls.append({
            "name":       name,
            "args":       args,
            "result":     result,
            "latency_ms": latency_ms,
        })

    def record_iteration(self, iteration: int) -> None:
        self._iterations = iteration

    def finish(self, diagnosis, usage) -> None:
        """Call after the final structured output is returned."""
        self._diagnosis = diagnosis.model_dump()
        if usage:
            self._usage = {
                "prompt_tokens":     usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens":      usage.total_tokens,
            }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "run_id":          self._run_id,
            "timestamp":       self._timestamp,
            "query":           self._query,
            "iterations":      self._iterations,
            "tool_calls":      self._tool_calls,
            "diagnosis":       self._diagnosis,
            "usage":           self._usage,
            "total_latency_ms": int((time.time() - self._t_start) * 1000),
        }

    def save(self, path: Path = TRACES_FILE) -> Path:
        """Append this run's record to the traces JSONL file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(self.to_dict()) + "\n")
        return path
