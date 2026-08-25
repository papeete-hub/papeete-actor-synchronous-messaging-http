"""Lazy, no-op-safe OpenTelemetry glue — the observability "port" `mailbox.py` calls into.

NOT A HAND-ROLLED PORT. `opentelemetry`'s own API is already the port: `propagate.inject()` and
`trace.get_tracer(...).start_as_current_span(...)` are genuine no-ops — write nothing, record
nothing — when no SDK `TracerProvider`/`MeterProvider` was ever configured (`opentelemetry-sdk`
installed but nobody called `configure()`; that call lives in `papeete-observability`, this
ecosystem's sibling repo). `Engine`'s `Protocol`-per-door shape exists because *which vendor*
genuinely varies per door; observability is uniform across every door, so mirroring that shape
here would be a redundant abstraction over an API that is already swappable.

WHAT THIS MODULE ADDS ON TOP OF THE BARE API: graceful behaviour when `opentelemetry-api` isn't
even INSTALLED — this package's own dependency on it stays optional (`pip install
papeete-actor-synchronous-messaging-http[otel]`), so every call site here is a `try: from
opentelemetry import ... except ImportError:` guard around a trivial stand-in, the same
lazy-import discipline `Engine.resolve()` already established for optional vendor adapters.

PRIVATE. Nothing here is public API — `mailbox.py` is the only caller; no other package in this
ecosystem should import this module directly.
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

CLIENT = "CLIENT"          # deliver() — outbound
SERVER = "SERVER"          # do_POST() — inbound

_tracer_singleton: Any = None
_meter_singleton: Any = None
_calls_counter: Any = None
_latency_histogram: Any = None


class _NoOpInstrument:
    """Stands in for a `Counter`/`Histogram` when `opentelemetry-api` isn't installed."""

    def add(self, *_args, **_kwargs) -> None:
        pass

    def record(self, *_args, **_kwargs) -> None:
        pass


class _NoOpMeter:
    def create_counter(self, *_args, **_kwargs) -> _NoOpInstrument:
        return _NoOpInstrument()

    def create_histogram(self, *_args, **_kwargs) -> _NoOpInstrument:
        return _NoOpInstrument()


class _NoOpTracer:
    def start_as_current_span(self, *_args, **_kwargs):
        return contextlib.nullcontext()


def _tracer() -> Any:
    """Lazy + cached. The real OTel tracer is itself a no-op with no SDK configured, so caching
    it is safe regardless of whether `configure()` (in `papeete-observability`) runs before or
    after this module is first imported — `trace.get_tracer()` hands back a proxy that starts
    forwarding to a real `TracerProvider` the moment one is set, not a frozen snapshot."""
    global _tracer_singleton
    if _tracer_singleton is None:
        try:
            from opentelemetry import trace
            _tracer_singleton = trace.get_tracer("papeete_actor_synchronous_messaging_http")
        except ImportError:
            _tracer_singleton = _NoOpTracer()
    return _tracer_singleton


def _meter() -> Any:
    """Same proxy reasoning as `_tracer()`, for `MeterProvider`."""
    global _meter_singleton
    if _meter_singleton is None:
        try:
            from opentelemetry import metrics
            _meter_singleton = metrics.get_meter("papeete_actor_synchronous_messaging_http")
        except ImportError:
            _meter_singleton = _NoOpMeter()
    return _meter_singleton


def _calls() -> Any:
    global _calls_counter
    if _calls_counter is None:
        _calls_counter = _meter().create_counter(
            "door_calls_total", description="Doors called, labelled door/verb/outcome.")
    return _calls_counter


def _latency() -> Any:
    global _latency_histogram
    if _latency_histogram is None:
        _latency_histogram = _meter().create_histogram(
            "door_latency_seconds", unit="s",
            description="Time spent inside a door call, labelled door/verb/outcome.")
    return _latency_histogram


def inject(headers: dict) -> dict:
    """Stamp `headers` with the current span's W3C `traceparent`, in place, and hand `headers`
    itself back — so a call site chains straight into `urllib.request.Request(headers=...)`. A
    no-op passthrough if `opentelemetry-api` isn't installed."""
    try:
        from opentelemetry import propagate
    except ImportError:
        return headers
    propagate.inject(headers)
    return headers


def extract(request_headers: Any) -> Any:
    """Read `traceparent`/`tracestate` off an inbound request's headers and hand back an OTel
    `Context` `span()` can parent a `SERVER` span against. `request_headers` is anything with a
    case-insensitive `.get()` — `BaseHTTPRequestHandler.headers` already is one. Returns `None`
    if `opentelemetry-api` isn't installed; `span()` treats `None` the same as "no parent"."""
    try:
        from opentelemetry import propagate
    except ImportError:
        return None
    carrier = {key: request_headers.get(key)
               for key in ("traceparent", "tracestate") if request_headers.get(key) is not None}
    return propagate.extract(carrier)


@contextlib.contextmanager
def span(name: str, kind: str, attributes: dict | None = None, *, context: Any = None
          ) -> Iterator[None]:
    """One span — `CLIENT` around `deliver()`, `SERVER` around `do_POST`'s dispatch. A true
    no-op context manager if `opentelemetry-api` isn't installed or no SDK was ever configured."""
    kwargs: dict = {"attributes": attributes or {}}
    try:
        from opentelemetry.trace import SpanKind
        kwargs["kind"] = getattr(SpanKind, kind)
    except ImportError:
        pass
    if context is not None:
        kwargs["context"] = context
    with _tracer().start_as_current_span(name, **kwargs):
        yield


def record(*, door: str, verb: str, outcome: str, elapsed: float) -> None:
    """One counter tick + one histogram observation, labelled `door`/`verb`/`outcome`. A no-op
    if `opentelemetry-api` isn't installed."""
    attributes = {"door": door, "verb": verb, "outcome": outcome}
    _calls().add(1, attributes=attributes)
    _latency().record(elapsed, attributes=attributes)
