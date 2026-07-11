from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any, List, Optional


@dataclass
class TelemetryEvent:
    engine: str
    phase: str
    latency_ms: float
    payload_bytes: int
    status_icon: str
    detail: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "phase": self.phase,
            "latency_ms": round(self.latency_ms, 2),
            "payload_bytes": int(self.payload_bytes),
            "status_icon": self.status_icon,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class TelemetryBuffer:
    """Thread-safe buffer for live network telemetry events."""

    def __init__(self, max_events: int = 80) -> None:
        self._events: List[TelemetryEvent] = []
        self._lock = threading.Lock()
        self._max_events = max_events

    def push(self, event: TelemetryEvent | dict[str, Any] | None, **kwargs: Any) -> None:
        if event is None:
            event = TelemetryEvent(**kwargs)
        elif isinstance(event, dict):
            event = TelemetryEvent(**event)
        elif not isinstance(event, TelemetryEvent):
            raise TypeError("TelemetryBuffer only accepts TelemetryEvent or dict payloads")

        with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events :]

    def __call__(self, engine: str, phase: str, latency_ms: float, payload_bytes: int, status_icon: str, detail: str = "") -> None:
        self.push(
            TelemetryEvent(
                engine=engine,
                phase=phase,
                latency_ms=latency_ms,
                payload_bytes=payload_bytes,
                status_icon=status_icon,
                detail=detail,
            )
        )

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [event.to_dict() for event in self._events[-20:]]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


def format_bytes(payload_bytes: int) -> str:
    if payload_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    size = float(payload_bytes)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024.0
        index += 1
    return f"{size:.1f} {units[index]}"


def render_telemetry_panel(buffer: TelemetryBuffer, placeholder: Any, summary_placeholder: Optional[Any] = None) -> None:
    events = buffer.snapshot()
    if not events:
        placeholder.caption("Waiting for network telemetry...")
        if summary_placeholder is not None:
            summary_placeholder.empty()
        return

    latest = events[-1]
    avg_latency = sum(item["latency_ms"] for item in events) / len(events)
    total_bytes = sum(item["payload_bytes"] for item in events)

    if summary_placeholder is not None:
        summary_placeholder.empty()
        summary_placeholder.metric("Latest Phase", f"{latest['status_icon']} {latest['phase']}")
        summary_placeholder.metric("Avg RTT", f"{avg_latency:.1f} ms")
        summary_placeholder.metric("Volume", format_bytes(total_bytes))

    rows = []
    for item in events[-10:]:
        rows.append(
            {
                "Time": item["timestamp"],
                "Engine": item["engine"],
                "Phase": item["phase"],
                "RTT": f"{item['latency_ms']:.1f} ms",
                "Payload": format_bytes(item["payload_bytes"]),
                "Status": item["status_icon"],
            }
        )

    placeholder.dataframe(rows, width="stretch", hide_index=True)