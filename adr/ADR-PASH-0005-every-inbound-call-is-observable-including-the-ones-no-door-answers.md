---
id: ADR-PASH-0005
title: "Every inbound call is observable, including the ones no door answers"
status: Accepted
date: 2026-09-02
supersedes: []
references:
  - ../src/papeete_actor_synchronous_messaging_http/mailbox.py
  - ../src/papeete_actor_synchronous_messaging_http/_tracing.py
  - ./ADR-PASH-0004-one-http-route-per-door-not-one-generic-receive.md
---

# ADR-PASH-0005 — Every inbound call is observable, including the ones no door answers

## Context

`do_POST` acquired a `SERVER` span, a `door_calls_total`/`door_latency_seconds` tick and an
access log line when OpenTelemetry was first wired into this binding. All three sat *after*
routing and body-parsing:

```python
verb = doors.get(self.path)
if verb is None:
    return self._reply(404, ...)          # ← returns here
try:
    body = json.loads(...)
except json.JSONDecodeError:
    return self._reply(400, ...)          # ← and here
...
try:
    with _tracing.span(door, SERVER, ...):    # ← span starts only now
        ...
finally:
    logging.info("do_POST door=%s ...")       # ← and the line only now
```

So the two failure modes a *caller* is most likely to hit — addressing a door this actor does
not declare, and sending a body that is not JSON — produced **no span, no metric and no log
record at all**. From the answering process's own telemetry, a caller hammering the wrong path
for an hour is indistinguishable from a caller that never connected. The one thing that did
survive was the HTTP status on the caller's own side, which is exactly the side that already
knew something went wrong.

A third case is subtler and is what actually surfaced this. `Actor.receive()` refuses an
undeclared door or a payload its `request_schema` rejects (`ADR-PAS-0009`) by raising `Refusal`,
*before* any handler of the answering actor's own runs. That call did get a span and a line —
but a consumer that stamps its own correlation ids onto log records does so from inside its
handler, which never ran. Its own convention could not reach the very records that say a call
was rejected. Since the trace context the caller sent (`traceparent`) is available to this
binding from the first line of `do_POST`, a consumer *can* recover the run's identity from the
active span — but only if there is an active span at the moment the record is emitted, which
for two of the four outcomes there was not, and for the access line never was (it sat in a
`finally` outside the `with`).

## Decision

**One span, one metric tick and one log line per inbound POST — opened before the path is routed
and before the body is read, and closed around both.**

- The `SERVER` span is started first, parented on the caller's `traceparent`, named for the
  door when one matches and for the raw path when none does.
- Routing and parsing move into a `_dispatch()` helper that answers the call and *names its
  outcome*, never logging or metering itself.
- `outcome` gains two values: `no-route` (nothing answers this path) and `bad-request` (the body
  is not JSON), beside the existing `accepted`, `refused` and `error`. When no door matched
  there is no verb either, and the placeholder `-` is recorded rather than an empty string.
- The log line and the metric move INSIDE the span, so every record emitted while answering a
  call — this binding's own included — carries the caller's trace context.
- `GET` to an unknown path logs one `WARNING`. `GET /health` deliberately stays silent and
  unspanned: a readiness probe firing every few seconds would bury real calls in a deployment's
  traces, and a probe answering `{"status": "ok"}` is not news.

## Rationale

**Why not simply log the early returns where they stood.** That fixes the missing line and
leaves the missing span, which is the half that matters for correlation: a record emitted with
no active span carries no trace id, so nothing downstream can tie it to the run that caused it.
Spanning the whole request is also what every mature HTTP server instrumentation does — you span
the request, then set the status, rather than deciding whether the request deserves a span based
on how it turned out.

**Why the binding, and not the consumer.** A consumer can stamp whatever it likes onto records
its own code emits; it cannot stamp anything onto records emitted by a call that was rejected
before its code ran. Only the transport is present for every inbound call, whatever becomes of
it. That is the same reasoning `ADR-PASH-0004` used to put routing here: the adapter owns what
crosses the socket, including the fact that something crossed it and was turned away.

**Why this adds no dependency.** Nothing here reaches for a correlation-id abstraction, an
observability package, or baggage. It uses what `_tracing.py` already had — the OTel API,
guarded, a genuine no-op when absent — and simply makes sure a span is open when the interesting
records are written. What a correlation id is *called*, and which of them a deployment cares
about, stays entirely the consumer's business (`papeete-observability` is where that belongs);
this binding only guarantees there is a trace to hang one on.

**Why `-` and not an empty string for a missing verb.** A metric attribute is a label. An empty
string reads as "this label was not set" in most query languages, which is a claim about the
*instrument*; `-` reads as "there was no verb", which is a claim about the *call* — and is the
true one.

## Consequences

- Callers see identical HTTP responses. Status codes, bodies and headers are unchanged; this is
  purely about what the answering process records.
- `door_calls_total` and `door_latency_seconds` now tick for calls that never reached an actor.
  A dashboard summing them will show counts it did not show before — that is the point, but a
  panel that assumed every tick reached a door needs its query re-read.
- `outcome` is no longer three-valued. Anything matching on it exhaustively (an alert, a Loki
  or PromQL filter) must account for `no-route` and `bad-request`.
- An unexpected exception from `Actor.receive()` still propagates out of `do_POST` after being
  recorded as `error`, exactly as before — this ADR does not turn crashes into replies.
- `GET /health` remains the one inbound call this binding does not observe at all.
