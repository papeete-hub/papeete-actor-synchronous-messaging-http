#!/usr/bin/env bash
# Builds the four wheels `docker build` needs and are not on PyPI yet — `papeete-actor`,
# `papeete-actor-message`, `papeete-actor-synchronous-messaging`, and this repo itself — into
# each actor's own `wheels/` folder, so `docker build -t <tag> examples/<actor>` (the same
# invocation `papeete-actor build` runs) stays a self-contained build with no `--build-context`
# flag and no change to `papeete-actor build`'s own fixed `docker build -t <tag> <folder>`
# (ADR-PA-0025).
#
# Run once per change to any of the four packages, before building either actor's image.
set -euo pipefail
cd "$(dirname "$0")"                    # examples/
HERE="$(pwd)"
CORE="$HERE/../../papeete-actor"
MESSAGE="$HERE/../../papeete-actor-message"
MESSAGING="$HERE/../../papeete-actor-synchronous-messaging"
HTTP="$HERE/.."

for actor in waiter customer; do
  rm -rf "$HERE/$actor/wheels"
  mkdir -p "$HERE/$actor/wheels"
  uv build --wheel -o "$HERE/$actor/wheels" "$CORE"
  uv build --wheel -o "$HERE/$actor/wheels" "$MESSAGE"
  uv build --wheel -o "$HERE/$actor/wheels" "$MESSAGING"
  uv build --wheel -o "$HERE/$actor/wheels" "$HTTP"
done

echo "wheels ready in examples/waiter/wheels/ and examples/customer/wheels/"
