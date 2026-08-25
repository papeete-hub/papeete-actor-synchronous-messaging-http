#!/usr/bin/env bash
# Builds the five wheels `docker build` needs and are not on PyPI yet — `papeete-actor`,
# `papeete-actor-message`, `papeete-actor-synchronous-messaging`, `papeete-observability`, and
# this repo itself — into each actor's own `wheels/` folder, so `docker build -t <tag>
# examples/<pair>/<actor>` (the same invocation `papeete-actor build` runs) stays a
# self-contained build with no `--build-context` flag and no change to `papeete-actor build`'s
# own fixed `docker build -t <tag> <folder>` (ADR-PA-0025).
#
# ACTORS ARE DISCOVERED, NOT LISTED — every folder under examples/<pair>/ holding a Dockerfile
# gets wheels, so a new example pair (another `examples/*/`) needs no edit here. Every actor
# gets `papeete-observability` too, even `llm-judged/` (which doesn't call `configure()` yet) —
# an unused wheel in an image costs nothing, and it keeps this loop uniform.
#
# Run once per change to any of the five packages, before building any actor's image.
set -euo pipefail
cd "$(dirname "$0")"                    # examples/
HERE="$(pwd)"
CORE="$HERE/../../papeete-actor"
MESSAGE="$HERE/../../papeete-actor-message"
MESSAGING="$HERE/../../papeete-actor-synchronous-messaging"
OBSERVABILITY="$HERE/../../papeete-observability"
HTTP="$HERE/.."

for dockerfile in "$HERE"/*/*/Dockerfile; do
  actor="$(dirname "$dockerfile")"
  rm -rf "$actor/wheels"
  mkdir -p "$actor/wheels"
  uv build --wheel -o "$actor/wheels" "$CORE"
  uv build --wheel -o "$actor/wheels" "$MESSAGE"
  uv build --wheel -o "$actor/wheels" "$MESSAGING"
  uv build --wheel -o "$actor/wheels" "$OBSERVABILITY"
  uv build --wheel -o "$actor/wheels" "$HTTP"
  echo "wheels ready in ${actor#"$HERE"/}/wheels/"
done
