from fastapi import APIRouter, HTTPException, Query

from core.observability import list_recent_traces, read_trace_events

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("")
async def list_traces(limit: int = Query(default=20, ge=1, le=200)):
    return {
        "items": list_recent_traces(limit),
        "limit": limit,
    }


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    events = read_trace_events(trace_id)
    if not events:
        raise HTTPException(status_code=404, detail="Trace not found")

    return {
        "trace_id": trace_id,
        "events": events,
        "count": len(events),
    }
