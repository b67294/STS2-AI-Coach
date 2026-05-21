from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator


class TraceContext:
    def __init__(self) -> None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.trace_id = f"trace_{stamp}"
        self._started = time.perf_counter()
        self._spans: list[dict[str, Any]] = []
        self._meta: dict[str, Any] = {}
        self._failed_span: str | None = None

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        except Exception:
            self._failed_span = self._failed_span or name
            raise
        finally:
            self._spans.append({"name": name, "ms": round((time.perf_counter() - started) * 1000)})

    def set_meta(self, **values: Any) -> None:
        for key, value in values.items():
            if value is not None:
                self._meta[key] = value

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "trace_id": self.trace_id,
            "total_ms": round((time.perf_counter() - self._started) * 1000),
            "spans": list(self._spans),
            "meta": dict(self._meta),
        }
        if self._failed_span:
            payload["failed_span"] = self._failed_span
        return payload
