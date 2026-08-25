# Two worked pairs, deployed for real

Two conversations `papeete-actor-synchronous-messaging`'s own in-process examples prove, each as
two separate containers talking over `HttpMailbox`, deployable to a real cluster:

| Pair | Actors | What it proves |
|---|---|---|
| [`deterministic/`](./deterministic) | `customer`, `waiter` | `take-order`/`order-status`, `confirm-substitution`/`substitution-decision` — every door answers from the actor's own state; **no door on either card names an `engine:`** (ADR-PAS-0012). |
| [`llm-judged/`](./llm-judged) | `buyer`, `delivery-person` | `report-issue`/`claim-status`, `delivery-notice`/`delivery-status` — `report-issue` is the one door in this repo a real vendor judges: "is this account of a late/wrong/damaged delivery credible, and what remedy does it warrant" has no fixed table that could answer it (ADR-PAS-0012). |

Both pairs share the same file layout and the same `HttpMailbox`/door-per-route mechanism
([ADR-PASH-0004](../adr/ADR-PASH-0004-one-http-route-per-door-not-one-generic-receive.md)); they
differ only in whether any door needs a vendor's judgement.

| File | Role |
|---|---|
| `<pair>/<actor>/actor.yaml` | identity — `papeete-actor-manifest/v0`: name + description |
| `<pair>/<actor>/actor-data.yaml` | the data dictionary — `papeete-actor-data/v0` |
| `<pair>/<actor>/actor-message.yaml` | the message catalog — `papeete-actor-message/v1` |
| `<pair>/<actor>/actor-synchronous-messaging.yaml` | the doors — `synchronous-messaging-doors/v1`: each names a `door_schema`/`completion_schema` message and, only where a fixed rule set genuinely could not answer it, an `engine` (ADR-PAS-0010, narrowed by ADR-PAS-0012) |
| `<pair>/<actor>/Dockerfile` | the build recipe — `python:3.12-slim`, pre-built wheels (see below), bakes `card.yaml` |
| `<pair>/<actor>/app.py` | the actor itself — `Actor` on an `HttpMailbox`, plus `GET /card` |
| `<pair>/<actor>/card.yaml` | NOT committed — `describe`'s output, baked into the image at build time (see below) |
| `<pair>/<actor>/deploy/k8s/` | kustomize deploy config — `base/` + `overlays/develop/` (`ADR-PA-0025`) |
| `<pair>/product.yaml` / `<pair>/productK8s.yaml` | what `papeete-deploy` resolves and runs for that pair |

A peer's door ids (the Waiter's `take-order`/`order-status`, the Delivery Person's
`report-issue`/`claim-status`) are each actor's own business knowledge, not something resolved
from a shared file — see `deterministic/customer/decide.py` and `llm-judged/buyer/app.py`
([ADR-PASH-0002](../adr/ADR-PASH-0002-follow-the-core-packages-back-to-basics-reset.md)).

## `GET /card` — an actor's own composed card, in a browser

Every actor in both pairs serves its own composed card (identity + data dictionary + message
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

Discovers every actor under `examples/*/` that has a `Dockerfile` — both pairs, no per-actor
listing to maintain. Re-run it after any change to any of the sibling packages.

## Try it locally, no cluster — `deterministic/`

```bash
docker build -t customer examples/deterministic/customer
docker build -t waiter   examples/deterministic/waiter

docker network create table-service
docker run -d --rm --name waiter   --network table-service waiter
docker run -d --rm --name customer --network table-service customer

# neither container publishes a host port — reach them from another container on the
# same Docker network, the same way a real deployment would resolve them by name:
docker run --rm --network table-service curlimages/curl -s http://customer:8080/order
docker run --rm --network table-service curlimages/curl -s http://waiter:8080/card

docker rm -f waiter customer && docker network rm table-service
```

`GET /order` on the Customer is what makes the conversation happen: it opens a real `request`
against the Waiter's `take-order`, then a real `query` against `order-status`, both over the
Docker network, and returns what came back — the Waiter's own vocabulary (`accepted`, `order_id`,
`says`, ...), not a fixed reply shape.

## Try it locally, no cluster — `llm-judged/`

```bash
docker build -t buyer            examples/llm-judged/buyer
docker build -t delivery-person  examples/llm-judged/delivery-person

docker network create delivery-claims
docker run -d --rm --name delivery-person --network delivery-claims delivery-person
docker run -d --rm --name buyer            --network delivery-claims buyer

docker run --rm --network delivery-claims curlimages/curl -s http://buyer:8080/claim
docker run --rm --network delivery-claims curlimages/curl -s http://delivery-person:8080/notify-delivery

docker rm -f buyer delivery-person && docker network rm delivery-claims
```

`GET /claim` on the Buyer opens a real `request` against the Delivery Person's `report-issue` —
the pair's one judged door — then a real `query` against `claim-status`. `GET /notify-delivery`
on the Delivery Person exercises the other direction (`delivery-notice`/`delivery-status` on the
Buyer, neither engine-backed): both actors here are actors, neither is a client.

**Which engine judges `report-issue` is an env var, not a rebuild** — `delivery-person/app.py`
reads `ENGINE` at container start and resolves it exactly the way the core package's own
`resolve()` does; the Dockerfile bakes in both the `anthropic` and `openai` SDKs so any of the
three is available with no rebuild:

| `ENGINE` | needs | behaviour with no key |
|---|---|---|
| `scripted` (default) | nothing | deterministic fallback rules — the container builds, runs and answers `report-issue` with no secret at all |
| `claude` | `ANTHROPIC_API_KEY` (or `ant auth login`) — what a pair actually develops against locally | starts fine; only fails, per call, when `report-issue` is actually opened |
| `openai` | `OPENAI_API_KEY` — what a live-vendor conformance run asserts the protocol with | **the container crash-loops at startup** — `openai.OpenAI()`'s own constructor raises immediately with no key, unlike Claude's lazier client |

```bash
docker run -d --rm --name delivery-person --network delivery-claims \
  -e ENGINE=claude -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" delivery-person
```

This is genuinely non-deterministic: a real vendor may uphold or deny the claim, and both are
correct — unlike every door in `deterministic/`, re-running `GET /claim` against `ENGINE=claude`
or `ENGINE=openai` can legitimately answer differently call to call.

## Deploy to local Kubernetes

Needs [`papeete-platform`](https://github.com/papeete-hub/papeete-platform)'s ingress installed
once per cluster (check first — `kubectl get pods -n ingress-nginx`):

```bash
kubectl config use-context docker-desktop
kubectl get pods -n ingress-nginx || \
  ( cd ../papeete-platform/examples/ingress-nginx-local && terraform init && terraform apply )

./examples/build-wheels.sh
docker build -t customer examples/deterministic/customer
docker build -t waiter   examples/deterministic/waiter
```

**`papeete-deploy deploy productK8s.yaml` needs a real git-tagged version to resolve against**
(`<actor>/vX.Y.Z`, per `papeete-actor build`'s own convention). `deterministic/` carries one
(`customer/v0.2.1`, `waiter/v0.2.1` — the real path: `papeete-actor build --label alpha
examples/deterministic/customer examples/deterministic/waiter`, then `papeete-deploy deploy
examples/deterministic/productK8s.yaml`, which resolves and applies both overlays into namespace
`papeete-actor-synchronous-messaging-http-example`). `llm-judged/` does not carry tags yet (see
`open` on each actor's own card) — for either pair, or on a machine that has never tagged
anything, apply the two overlays directly instead, pinning the image tag just built — the same
mechanism `papeete-deploy` itself wraps (`ADR-PD-0002`), with the image pinned explicitly rather
than resolved by name+label:

```bash
PAIR=deterministic ACTORS="waiter customer" NAMESPACE=table-service-demo ./examples/deploy-scratch.sh
# or:
PAIR=llm-judged ACTORS="buyer delivery-person" NAMESPACE=delivery-claims-demo ./examples/deploy-scratch.sh
```

`deploy-scratch.sh` does exactly what a hand-rolled loop would: for each actor, builds a scratch
kustomization naming `examples/<pair>/<actor>/deploy/k8s/overlays/develop` as a **relative**
resource (an absolute path here is rejected outright — `kubectl kustomize` errors `new root '...'
cannot be absolute`, regardless of `--load-restrictor`, which only lifts the restriction on a
*relative* path escaping its root; verified against `kubectl` v1.34 / docker-desktop), pins
`images: [{name: <actor>, newTag: latest}]`, and applies it into `$NAMESPACE`.

```bash
kubectl -n table-service-demo get pods
kubectl -n table-service-demo run curltest --rm -i --restart=Never \
  --image=curlimages/curl -- curl -s http://customer:8080/order

kubectl delete namespace table-service-demo
```

For `llm-judged/`, `delivery-person`'s Deployment reads `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` from
an **optional** Secret named `llm-engine-keys` — the rollout succeeds whether or not that Secret
exists (`ENGINE` defaults to `scripted`, which never touches either), and creating it is the only
step needed to run the pair against a real vendor in-cluster:

```bash
kubectl -n delivery-claims-demo create secret generic llm-engine-keys \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY"
kubectl -n delivery-claims-demo set env deployment/delivery-person ENGINE=claude
```

External reachability (through the ingress, not just cluster-internal DNS) needs a
port-forward on this cluster, since `ingress-nginx-controller`'s Service here is `ClusterIP`
only:

```bash
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18080:80 &
curl http://localhost:18080/develop/customer/api/order
curl http://localhost:18080/develop/waiter/api/card          # or /develop/customer/api/card
curl http://localhost:18080/develop/buyer/api/claim
curl http://localhost:18080/develop/delivery-person/api/card
```

The response to `/order` (`deterministic/`) names a real accepted request at the Waiter's
`take-order` door and a real answer from `order-status`; the response to `/claim`
(`llm-judged/`) names a real judged reply from `report-issue` and a real answer from
`claim-status` — the same two conversations `papeete-actor-synchronous-messaging`'s own
in-process worked examples prove, this time crossing a real Kubernetes `Service` boundary.
`/card` is the same URL a browser would use to read any actor's own composed card — see
"`GET /card`" above.
