# Wheels are pre-built (examples/build-wheels.sh) rather than fetched from PyPI — neither
# papeete-actor nor papeete-actor-synchronous-messaging is published there yet. Once they are,
# this collapses to `RUN pip install papeete-actor-synchronous-messaging-http` and the wheels/
# folder goes away; nothing else about this file changes.
FROM python:3.12-slim
WORKDIR /app
COPY wheels/*.whl /tmp/wheels/
# `anthropic`/`openai` ARE FROM PyPI, NOT LOCAL WHEELS — neither vendor SDK is a dependency of
# any package this repo builds (`engine.py`'s `resolve()` imports them lazily). Both are
# installed here, unconditionally, so `ENGINE` (see app.py) can pick either one at container
# start with no rebuild — the same "engine is interior" claim ADR-PAS-0003 makes, just paid
# for in image size rather than a second image.
RUN pip install --no-cache-dir /tmp/wheels/*.whl anthropic openai && rm -rf /tmp/wheels
COPY actor.yaml actor-data.yaml actor-message.yaml actor-synchronous-messaging.yaml app.py claims.py ./
# STATIC, BAKED AT BUILD TIME — not a live GET /card (ADR-PASH-0001 still holds: no runtime
# discovery door). `describe` composes the four card files exactly once, here; `app.py` only
# ever serves this file's bytes back verbatim, never recomputes them per request.
RUN papeete-actor-synchronous-messaging describe . > card.yaml
EXPOSE 8080
CMD ["python", "app.py"]
