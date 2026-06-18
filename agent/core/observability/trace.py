import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any


MAX_FIELD_LENGTH = 800


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
