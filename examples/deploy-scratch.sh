#!/usr/bin/env bash
# Applies one example pair's `deploy/k8s/overlays/develop` for each of its actors, pinned to
# whatever image tag was just built locally — the workaround for a pair that carries no
# `<actor>/vX.Y.Z` git tag yet, so `papeete-deploy deploy <pair>/productK8s.yaml` has nothing to
# resolve against (see examples/README.md's "Deploy to local Kubernetes"). Once a pair carries
# real tags, prefer `papeete-actor build` + `papeete-deploy deploy` instead — this script stays
# the fallback for everything that doesn't yet.
#
# Required env: PAIR (e.g. deterministic, llm-judged), ACTORS (space-separated, e.g.
# "waiter customer"), NAMESPACE (created if it doesn't exist).
set -euo pipefail
: "${PAIR:?set PAIR, e.g. PAIR=deterministic}"
: "${ACTORS:?set ACTORS, e.g. ACTORS=\"waiter customer\"}"
: "${NAMESPACE:?set NAMESPACE, e.g. NAMESPACE=table-service-demo}"

cd "$(dirname "$0")"                    # examples/
HERE="$(pwd)"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

for actor in $ACTORS; do
  dir=$(mktemp -d)
  target="$HERE/$PAIR/$actor/deploy/k8s/overlays/develop"
  # RELATIVE, NEVER ABSOLUTE — `kubectl kustomize` rejects an absolute `resources:` entry
  # outright (`new root '...' cannot be absolute`), regardless of `--load-restrictor`, which
  # only lifts the restriction on a *relative* path escaping its root.
  rel=$(python3 -c "import os; print(os.path.relpath('$target', '$dir'))")
  cat > "$dir/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [$rel]
images: [{name: $actor, newTag: latest}]
EOF
  kubectl kustomize "$dir" --load-restrictor=LoadRestrictionsNone | \
    kubectl apply -n "$NAMESPACE" -f -
done

kubectl -n "$NAMESPACE" get pods
