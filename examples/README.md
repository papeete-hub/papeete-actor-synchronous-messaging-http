# customer / waiter — deployed for real

The same conversation `papeete-actor-synchronous-messaging`'s own in-process scenario proves —
`take-order`/`order-status`, `confirm-substitution`/`substitution-decision` — this time as two
separate containers, talking over `HttpMailbox`, deployable to a real cluster.

| File | Role |
|---|---|
| `<actor>/actor.yaml` | identity — `papeete-actor-manifest/v0`: name + description |
| `<actor>/actor-data.yaml` | the data dictionary — `papeete-actor-data/v0` |
| `<actor>/actor-message.yaml` | the message catalog — `papeete-actor-message/v1` |
| `<actor>/actor-synchronous-messaging.yaml` | the doors — `synchronous-messaging-doors/v1`: each names a `door_schema`/`completion_schema` message and, only where a fixed rule set genuinely could not answer it, an `engine` (ADR-PAS-0010, narrowed by ADR-PAS-0012) — neither door here names one |
| `<actor>/Dockerfile` | the build recipe — `python:3.12-slim`, pre-built wheels (see below), bakes `card.yaml` |
| `<actor>/app.py` | the actor itself — `Actor` on an `HttpMailbox`, plus `GET /card` |
| `<actor>/card.yaml` | NOT committed — `describe`'s output, baked into the image at build time (see below) |
| `<actor>/deploy/k8s/` | kustomize deploy config — `base/` + `overlays/develop/` (`ADR-PA-0025`) |
| `product.yaml` / `productK8s.yaml` | what `papeete-deploy` resolves and runs |

A peer's door ids (`Waiter`'s `take-order`/`order-status`) are each actor's own business
knowledge, not something resolved from a shared file — see `customer/app.py` and
`customer/decide.py` ([ADR-PASH-0002](../adr/ADR-PASH-0002-follow-the-core-packages-back-to-basics-reset.md)).

## `GET /card` — an actor's own composed card, in a browser

Both `waiter` and `customer` serve their own composed card (identity + data dictionary + message
catalog + doors — everything `papeete-actor-synchronous-messaging describe FOLDER` prints) at
`GET /card`. It is **not** a live discovery door — `ADR-PASH-0001`'s "no `GET /card`" still
holds. Each `Dockerfile` runs `describe` exactly once, at build time, baking the result into the
image as `card.yaml`; `app.py` reads that file once at startup and serves the same fixed dict on
every request, never recomputing it. See
[ADR-PASH-0003](../adr/ADR-PASH-0003-a-static-baked-card-route-is-not-the-door-adr-pash-0001-rejected.md)
for why this doesn't reopen that decision.

## Build the wheels first

`papeete-actor`, `papeete-actor-message` and `papeete-actor-synchronous-messaging` are all on
PyPI now, but each actor's Docker build context still carries its own copy of all three wheels
(plus this package's own), built locally rather than fetched — the `Dockerfile`'s `RUN
papeete-actor-synchronous-messaging describe .` step needs the CLI on `PATH` before the image's
final layer, and pinning to whatever's on disk in this workspace keeps that in step with
whatever's being worked on here, rather than drifting from the latest PyPI release:

```bash
./examples/build-wheels.sh
```

Re-run it after any change to any of the sibling packages.

## Try it locally, no cluster

```bash
docker build -t customer examples/customer
docker build -t waiter examples/waiter

docker network create table-service
docker run -d --rm --name waiter   --network table-service waiter
docker run -d --rm --name customer --network table-service customer

# neither container publishes a host port — reach them from another container on the
# same Docker network, the same way a real deployment would resolve them by name:
docker run --rm --network table-service curlimages/curl -s http://customer:8080/order
docker run --rm --network table-service curlimages/curl -s http://waiter:8080/card
```

`GET /order` on the Customer is what makes the conversation happen: it opens a real `request`
against the Waiter's `take-order`, then a real `query` against `order-status`, both over the
Docker network, and returns what came back — the Waiter's own vocabulary (`accepted`, `order`,
`says`, ...), not a fixed reply shape. Verified in this repo's own session end to end, real
containers, real sockets, no mock.

```bash
docker rm -f waiter customer && docker network rm table-service
```

## Deploy to local Kubernetes

Needs [`papeete-platform`](https://github.com/papeete-hub/papeete-platform)'s ingress installed
once per cluster (check first — `kubectl get pods -n ingress-nginx`; this session's own cluster
already had it):

```bash
kubectl config use-context docker-desktop
kubectl get pods -n ingress-nginx || \
  ( cd ../papeete-platform/examples/ingress-nginx-local && terraform init && terraform apply )

./examples/build-wheels.sh
docker build -t customer examples/customer
docker build -t waiter examples/waiter
```

**`papeete-deploy deploy productK8s.yaml` needs a real git-tagged version to resolve against**
(`<actor>/vX.Y.Z`, per `papeete-actor build`'s own convention) — this worked example doesn't
carry one yet (see `open` on each actor's own card), and on a machine that has ever built
`papeete-deploy`'s *own* customer/waiter demo, its tag-scanning resolver will find THOSE images
instead of these — same names, different actors, a real local-registry collision worth knowing
about rather than a hypothetical one. Until this example carries its own version tags, apply
the two overlays directly instead, pinning the exact tag just built — the same mechanism
`papeete-deploy` itself wraps (`ADR-PD-0002`), with the image pinned explicitly rather than
resolved by name+label:

```bash
kubectl create namespace table-service-demo
for actor in waiter customer; do
  dir=$(mktemp -d)
  target="$(pwd)/examples/$actor/deploy/k8s/overlays/develop"
  rel=$(python3 -c "import os; print(os.path.relpath('$target', '$dir'))")
  cat > "$dir/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [$rel]
images: [{name: $actor, newTag: latest}]
EOF
  kubectl kustomize "$dir" --load-restrictor=LoadRestrictionsNone | \
    kubectl apply -n table-service-demo -f -
done

kubectl -n table-service-demo get pods
kubectl -n table-service-demo run curltest --rm -i --restart=Never \
  --image=curlimages/curl -- curl -s http://customer:8080/order

kubectl delete namespace table-service-demo
```

**The scratch kustomization's `resources:` entry must be RELATIVE, never absolute.** An earlier
version of this recipe wrote an absolute path there; `kubectl kustomize` rejects that outright
(`new root '...' cannot be absolute`) regardless of `--load-restrictor`, which only lifts the
restriction on a *relative* path escaping its root — it does not make an absolute path
acceptable. `python3 -c "os.path.relpath(...)"` above computes the relative hop from the scratch
dir back to this repo's checkout; that is what `--load-restrictor=LoadRestrictionsNone` is
actually for. Verified against `kubectl` v1.34 / docker-desktop.

External reachability (through the ingress, not just cluster-internal DNS) needs a
port-forward on this cluster, since `ingress-nginx-controller`'s Service here is `ClusterIP`
only:

```bash
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18080:80 &
curl http://localhost:18080/develop/customer/api/order
curl http://localhost:18080/develop/waiter/api/card       # or /develop/customer/api/card
```

The response to `/order` names a real accepted request at the Waiter's `take-order` door and a
real answer from `order-status` — the same conversation
`papeete-actor-synchronous-messaging`'s own in-process worked example proves, this time crossing
a real Kubernetes `Service` boundary. `/card` is the same URL a browser would use to read either
actor's own composed card — see "`GET /card`" above. Verified in this repo's own session, both
cluster-internal (`curltest` above) and through the ingress port-forward.
