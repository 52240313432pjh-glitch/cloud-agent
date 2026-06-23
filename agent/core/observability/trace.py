import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


MAX_FIELD_LENGTH = 800
DEFAULT_TRACE_LIMIT = 20
MAX_TRACE_LIMIT = 200
TRACE_LOG_PATH = Path(
    os.getenv(
        "AGENT_TRACE_LOG_PATH",
        Path(__file__).resolve().parents[3] / "logs" / "agent_trace.jsonl",
    )
)
_trace_write_lock = Lock()


def new_trace_id() -> str:
    return uuid.uuid4().hex


def trace_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > MAX_FIELD_LENGTH:
            return value[:MAX_FIELD_LENGTH] + "...[truncated]"
        return value
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value[:20]]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _write_trace_record(record: dict[str, Any]) -> None:
    try:
        TRACE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with _trace_write_lock:
            with TRACE_LOG_PATH.open("a", encoding="utf-8") as file:
                file.write(line)
    except Exception as exc:
        print(f"[AGENT_TRACE_STORE_ERROR] {exc}")


def read_trace_events(trace_id: str) -> list[dict[str, Any]]:
    if not TRACE_LOG_PATH.exists():
        return []

    events: list[dict[str, Any]] = []
    with TRACE_LOG_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("trace_id") == trace_id:
                events.append(record)
    return events


def list_recent_traces(limit: int = DEFAULT_TRACE_LIMIT) -> list[dict[str, Any]]:
    if not TRACE_LOG_PATH.exists():
        return []

    limit = max(1, min(limit, MAX_TRACE_LIMIT))
    summaries: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    with TRACE_LOG_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            trace_id = record.get("trace_id")
            if not trace_id:
                continue

            if trace_id not in summaries:
                order.append(trace_id)
                summaries[trace_id] = {
                    "trace_id": trace_id,
                    "start_ts": record.get("ts"),
                    "end_ts": record.get("ts"),
                    "events": 0,
                    "user_id": record.get("user_id"),
                    "session_id": record.get("session_id"),
                    "query": record.get("payload", {}).get("query"),
                    "total_latency_ms": None,
                    "last_event": record.get("event"),
                }

            summary = summaries[trace_id]
            summary["end_ts"] = record.get("ts")
            summary["events"] += 1
            summary["last_event"] = record.get("event")
            if record.get("user_id"):
                summary["user_id"] = record.get("user_id")
            if record.get("session_id"):
                summary["session_id"] = record.get("session_id")
            if record.get("event") == "chat_start":
                summary["query"] = record.get("payload", {}).get("query")
            if record.get("event") == "chat_end":
                summary["total_latency_ms"] = record.get("latency_ms")

    return [summaries[trace_id] for trace_id in reversed(order[-limit:])]


def trace_log(
    trace_id: str | None,
    event: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    agent: str | None = None,
    tool: str | None = None,
    latency_ms: int | None = None,
    **payload: Any,
) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id or "no-trace",
        "event": event,
    }
    if user_id:
        record["user_id"] = user_id
    if session_id:
        record["session_id"] = session_id
    if agent:
        record["agent"] = agent
    if tool:
        record["tool"] = tool
    if latency_ms is not None:
        record["latency_ms"] = latency_ms
    if payload:
        record["payload"] = _safe_value(payload)

    print("[AGENT_TRACE] " + json.dumps(record, ensure_ascii=False, default=str))
    _write_trace_record(record)
