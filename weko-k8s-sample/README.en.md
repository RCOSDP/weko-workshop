# weko3 on kubernetes (kind) — Construction Runbook

How to build a Kubernetes cluster (nodes + API server) from nothing on one host with **kind**, and run **weko3**
on top of [RCOSDP/weko-k8s](https://github.com/RCOSDP/weko-k8s).

- Tested on: arm64 / 20 cores / 121GB RAM / Docker 29 (no sudo; docker runs without sudo)
- Time needed: about 90–120 minutes for a full first build (most of it is waiting for setup under amd64 emulation)
- For background and pitfalls, see [`CONSTRUCTION.en.md`](./CONSTRUCTION.en.md)

### What you get (current setup)
- **Multi-tenancy** (`tenant1.localhost` / `tenant2.localhost` run on their own)
- **Redis Sentinel HA** / **data on PVC** / **S3 (MinIO)** are already set up (closer to production)

Three ways to read this (three routes):
- **Route A (to learn)**: build the **small single-tenant setup from nothing in §1–9** → **[Multi-tenant configuration](#multi-tenant-configuration)** →
  **[Production-fidelity upgrades](#production-fidelity-upgrades-redis-sentinel--persistence--s3)** → **[HA clustering](#ha-clustering-operator-approach-and-arm64-nativization)** → **[NFS](#nfs-shared-storage-equivalent-to-productions-fs-config-fs-data)**, step by step.
- **Route B (production fidelity at once)**: run **[the one-shot runbook in Appendix B](#appendix-b-one-shot-runbook-to-build-the-production-fidelity-configuration-from-scratch)** from top to bottom. You start with Sentinel + persistence + S3 + multi-tenancy (PG/RabbitMQ are still **standalone**).
- **Route D (the current full setup = final form, from nothing in one run)**: **[the end-to-end runbook in Appendix D](#appendix-d-building-the-current-full-configuration-final-form-from-scratch-in-one-pass-on-arm64)** = one `k8s-weko/deploy-arm64.sh` run builds **HA clusters (PG Patroni ×3 / RabbitMQ ×3 / ES ×3) + Sentinel + persistence + NFS + S3 (MinIO) Location + multi-tenancy** (= what is really running on the machine) from nothing. For amd64, use `k8s-weko-amd64/deploy-amd64.sh`.

> **If your server is x86_64 / amd64**: the main text is for arm64, but on amd64 you do not need emulation or arm64
> builds, so it is **simpler**. For the differences see **[Appendix C: Runbook when arm64 is not involved (x86_64 / amd64 servers)](#appendix-c-runbook-when-arm64-is-not-involved-x86_64--amd64-servers)**.

---

## Overall picture (final configuration)

```
[Host: arm64]  kind cluster "weko3"
  control-plane … API server etc. + ingress-nginx (host 80/443)
  worker  (nodeType=WEKO) … tenant1-web / tenant2-web  (each: nginx + web(uwsgi) + worker(celery))
  worker2 (nodeType=DATA) … shared [all PVC]: PostgreSQL / Elasticsearch / RabbitMQ / MinIO(S3)
                            namespace weko3re … Redis master + 2 replicas + 3 sentinels [all PVC]
```

| Separate for each tenant | Shared backends |
|---|---|
| Web Pod + Ingress (host=FQDN) / PostgreSQL DB name / ES index prefix / RabbitMQ vhost / Redis DB number | PostgreSQL, Elasticsearch, RabbitMQ, Redis (Sentinel), MinIO (S3) |

| Element | Choice | Notes |
|---|---|---|
| weko application | **Built from the newest source** (`weko3-web:arm64` / `weko3-web:amd64`) | Set `WEKO_IMAGE` only when you want a prebuilt image |
| DB | PostgreSQL 13 (arm64, on PVC) | One DB per tenant |
| Cache/session | **Redis 6.2 Sentinel HA** (arm64, PVC) | `CACHE_TYPE=redissentinel`. Tenants are split by DB number |
| Queue | RabbitMQ 3.13 (arm64, PVC) | Quorum queues. One vhost `<name>/` per tenant |
| Search | **Elasticsearch 6.8.23** (self-built amd64 + kuromoji/icu, PVC) | weko **needs the ES6 line** (client `elasticsearch==6.1.1`) |
| Object storage | **MinIO** (S3-compatible, arm64, PVC) | For backups/content (like OCI Object Storage) |
| Front proxy | **Self-built WEKO nginx** (`weko3-nginx:<arch>`, has the Shibboleth SP = shibd + nginx-http-shibboleth) | `/etc/nginx` is on NFS (RWX), like production. By default it uses HTTP + `uwsgi_pass`. Set `WEKO_NGINX_SHIB=yes` to turn on the production `weko.conf` (Shibboleth/TLS) |

> Note: §1–9 teach the basics with the small setup — **standalone Redis, emptyDir, one tenant** (easier to learn).
> The last two sections show the changes that grow it into **Sentinel, PVC, multi-tenant**.

> **Important before you start**
> - WEKO3 is **built from the newest source** (step 5). The image is loaded with `kind load` (pulling straight from the in-cluster containerd is not reliable).
> - The prebuilt public images (`mhayashi55/weko3-web`, etc.) are **amd64 only**. Use them only by setting `WEKO_IMAGE`. On arm64 they also need qemu emulation (step 3).

---

## 1. Installing the tools (kubectl / kind)

Put them in `~/.local/bin` (it is on PATH).

```bash
mkdir -p ~/.local/bin

KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/arm64/kubectl"
chmod +x ~/.local/bin/kubectl

curl -sLo ~/.local/bin/kind "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-arm64"
chmod +x ~/.local/bin/kind

hash -r; kubectl version --client; kind version
```

## 2. Creating the kind cluster (3 nodes)

```bash
cd /home/mhaya/weko-k8s-sample
kind create cluster --config kind-weko-cluster.yaml --wait 120s

kubectl get nodes -L nodeType,ingress-ready   # check that 3 nodes are Ready
```

`kind-weko-cluster.yaml` … control-plane (opens 80/443) + worker (`nodeType=WEKO`) + worker2 (`nodeType=DATA`).

## 3. Ingress and amd64 emulation

```bash
# ingress-nginx
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
kubectl wait -n ingress-nginx --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=150s

# register amd64 emulation (the host kernel is shared with the kind nodes)
docker run --rm --privileged tonistiigi/binfmt --install amd64
```

## 4. Building the Elasticsearch image (ES 6.8.23 + kuromoji/icu)

```bash
cd /home/mhaya/weko-k8s-sample/k8s-weko
docker buildx build --platform linux/amd64 -f Dockerfile.es \
  -t weko-elasticsearch:6.8.23 --load .
kind load docker-image weko-elasticsearch:6.8.23 --name weko3
```

## 5. Building the weko application image (from the newest source)

WEKO3 is **built from the newest source, not taken from a prebuilt image** (steps 0 and 2 of `deploy-*.sh` do the same).

```bash
# get the newest source (pull if it is already cloned)
git clone https://github.com/RCOSDP/weko.git /home/mhaya/weko    # already cloned: git -C /home/mhaya/weko pull --ff-only
cd /home/mhaya/weko
# arm64 host: use Dockerfile.arm64, or Dockerfile if it is missing (same content)
docker build -f Dockerfile.arm64 -t weko3-web:arm64 .            # amd64 host: -f Dockerfile -t weko3-web:amd64
kind load docker-image weko3-web:arm64 --name weko3
```

> Set `WEKO_IMAGE=<repo>/<name>:<tag>` **only if you want to use a prebuilt image** (Docker Hub, etc.). Then the build is skipped and the image is pulled.
> To publish your build on Docker Hub, see **[Building the WEKO image and publishing/swapping it on Docker Hub](#building-the-weko-image-and-publishingswapping-it-on-docker-hub)**.

## 6. Deploying the backends + the weko application

```bash
cd /home/mhaya/weko-k8s-sample/k8s-weko
kubectl apply -f 00-namespace.yaml \
              -f 10-postgresql.yaml \
              -f 11-redis.yaml \
              -f 12-rabbitmq.yaml \
              -f 13-elasticsearch.yaml \
              -f 20-weko-config.yaml \
              -f 21-nginx-config.yaml \
              -f 30-weko-web.yaml

# wait until the backends and weko-web are Running (ES/web take minutes under emulation)
kubectl get pods -n weko3 -w
```

- `13-elasticsearch.yaml` has a ConfigMap with `kui.txt` (empty) mounted into the ES config. It is required, because weko's item mapping points to it.
- The Pod in `30-weko-web.yaml` = `nginx` + `web(uwsgi:5000)` + `worker(celery)`. invenio.cfg is made with `jinja2` at startup.

## 7. DB / ES initialization

```bash
POD=$(kubectl get pod -n weko3 -l app=weko-web -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n weko3 $POD -c web -- bash -s < weko-init.sh
```

What `weko-init.sh` does (same as the bundled `populate-instance.sh`):
`invenio db init/create` → `stats/logging partition` → `index init` / `index queue init`
→ make the ES ILM and stats indices → `files location` → grant users / roles / access.

> ⚠️ Because of emulation, each `invenio` command takes 30–60 seconds. The whole setup takes about 30–40 minutes.

## 8. Fixing the 500 (seeding admin_settings) and restarting

Right after setup, the top page returns **HTTP 500** in `_adjust_shib_admin_DB` (`max(id)+1` on an empty
`admin_settings`). Add one seed row and restart web.

```bash
PG=$(kubectl get pod -n weko3 -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n weko3 $PG -- psql -U weko -d wekodb \
  -c "INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb) ON CONFLICT DO NOTHING;"

kubectl rollout restart deployment/weko-web -n weko3
kubectl rollout status deployment/weko-web -n weko3 --timeout=300s
```

## 9. Connectivity check

```bash
# the first request is slow under emulation (before_first_request + JIT) — warm it up
curl -s -o /dev/null -w "warmup: %{http_code} (%{time_total}s)\n" -H "Host: localhost" http://localhost/ --max-time 240
curl -s -o /dev/null -w "top:    %{http_code}\n" -H "Host: localhost" http://localhost/
curl -s -o /dev/null -w "login:  %{http_code}\n" -H "Host: localhost" http://localhost/login/
curl -s -o /dev/null -w "search: %{http_code}\n" -H "Host: localhost" "http://localhost/api/records/?size=1"
```

Expected: top **200** / login **200** / admin **302** / api/records **200**.

| Item | Value |
|---|---|
| URL | `http://localhost/` |
| Administrator | `admin@example.org` / `adminpass123` |
| Namespace | `weko3` |

---

## Operations and cleanup

```bash
kubectl get pods -n weko3                 # status
kubectl logs -n weko3 <pod> -c web        # weko logs
docker exec -it weko3-control-plane bash  # a node (kind nodes are docker containers)

kind delete cluster --name weko3          # delete everything
```

## About 64GB memory environments

This setup runs on **about 5GiB measured** across all nodes (ES up to about 2.5Gi, weko-web about 1.3Gi, etc.).
The default manifests use resources sized for 64GB (ES heap 1g / uwsgi processes=2 / celery `-c 1`; limits total about 8.8Gi).
For how to scale up or down, see [§8bis of `CONSTRUCTION.en.md`](./CONSTRUCTION.en.md).

## Multi-tenant configuration

Run more than one weko3 repository (tenant) on one cluster. Like the original weko-k8s, the
**backends (PostgreSQL / Elasticsearch / RabbitMQ) are shared**, and the following are separate for each tenant.

| Separate resource | How |
|---|---|
| Database | A separate PostgreSQL DB (`INVENIO_POSTGRESQL_DBNAME`) |
| Search index | A separate ES index prefix (`SEARCH_INDEX_PREFIX`) |
| Messaging | A separate RabbitMQ vhost (`<NAME>/`, the same name as upstream `make_rabbitmq_vhost.sh`) |
| Cache/session | One Redis per tenant (`redis-<NAME>`) |
| Web/publication | One Deployment + Service + Ingress per tenant (`host = <W3FQDN>`) |
| Secret keys | `SECRET_KEY` / `WTF_CSRF_SECRET_KEY` / `WEKO_RECORDS_UI_SECRET_KEY` are **different per tenant** (one shared value inside a tenant). `gen-tenant.sh` makes them from `.secret-seed` (made on the first run — back it up), so they stay the same when you regenerate |
| Shibboleth / nginx config | `/fs-shibboleth/<tenant>` and `/fs-nginx/<tenant>` on NFS, kept apart per tenant with static PVs (seeded by `provision-nfs.sh`) |

### Defining and deploying tenants

```bash
cd k8s-weko

# 1) edit tenants.txt (NAME  DBNAME  HOST  ADMIN_EMAIL  ADMIN_PASS  INIT)
cat tenants.txt

# 2) generate manifests → apply
bash gen-tenant.sh                       # makes generated/<name>.yaml
kubectl apply -f generated/

# 3) provision the DB / RabbitMQ vhost
bash provision-tenants.sh

# 4) set up each tenant (those with INIT=yes; about 30–40 min per tenant, can run in parallel)
POD=$(kubectl get pod -n weko3 -l app=<NAME>-web -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n weko3 $POD -c web -- bash -s < weko-init.sh
#   after setup: seed admin_settings + restart web (same as step 8)
kubectl exec -n weko3 <postgres-pod> -- psql -U weko -d <DBNAME> \
  -c "INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb) ON CONFLICT DO NOTHING;"
kubectl rollout restart deployment/<NAME>-web -n weko3

# 5) (if MinIO is deployed) set file storage to the S3 (MinIO) Location
bash set-s3-location.sh                   # makes the weko-<tenant> bucket + sets files_location to type='s3'
```

> `INIT=no` in `tenants.txt` reuses the existing DB/indices (skips setup).
> In this setup, `tenant1` reuses `wekodb` from the single-tenant days.

### Verification (measured)

Two tenants (`tenant1.localhost` / `tenant2.localhost`) running on their own:

```
tenant1.localhost  /  200  /login 200  /admin 302  /api/records 200
tenant2.localhost  /  200  /login 200  /admin 302  /api/records 200
```

| Separation layer | tenant1 | tenant2 |
|---|---|---|
| ES index | `wekodb-*` | `tenant2-*` |
| PostgreSQL DB | `wekodb` | `tenant2` |
| RabbitMQ vhost | `tenant1/` | `tenant2/` |
| Redis | `redis-tenant1` | `redis-tenant2` |
| Administrator | `admin@example.org` | `admin@tenant2.local` |

- Access: `http://tenant1.localhost/` , `http://tenant2.localhost/` (`*.localhost` maps to loopback)
- Even with two tenants, host memory is about **14GiB** (well within 64GB; each new tenant adds about web 1.3Gi + a few tens of Mi for redis)

### Adding a tenant

Add one line to `tenants.txt`, then `gen-tenant.sh` → `kubectl apply -f generated/` → `provision-tenants.sh` → set it up.

### Access via port forwarding (remote / browser)

For opening both tenants in a browser from outside the host (for example over SSH). Tenants are routed by the **Host header**,
so the hostname must match weko's `INVENIO_WEB_HOST_NAME`. **Method A (one forward to the Ingress) is the best choice.**

**Method A: one port-forward to the Ingress (routing by Host; tested) ★best**

port-forward is a **long-running process**, so open a separate terminal for it and leave it running.
In this environment `*.localhost` maps to **IPv6 (`::1`)**, so put `::1` in `--address`.
```bash
# run in a separate terminal (leave it open). Ctrl+C to stop.
kubectl port-forward -n ingress-nginx --address 127.0.0.1,::1 \
  svc/ingress-nginx-controller 8080:80
```
Then open `http://tenant1.localhost:8080/` and `http://tenant2.localhost:8080/`
(the Ingress does not care about the port number and routes by hostname, so one forward reaches both tenants).
Check with curl from another terminal:
```bash
curl -H "Host: tenant1.localhost" http://127.0.0.1:8080/   # 200
curl -H "Host: tenant2.localhost" http://127.0.0.1:8080/   # 200
```

> **Note**: this kind cluster already **opens the Ingress on host ports 80/443**
> (`extraPortMappings` in `kind-weko-cluster.yaml`). **From a browser on this host you do not need port-forward** —
> `http://tenant1.localhost/` and `http://tenant2.localhost/` work as they are (tested: both 200).
> You need port-forward only if you do not want to use port 80 or you want a different port.

**Using it from a remote machine (a browser on another PC):**
```bash
# on the server (separate terminal):
kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80
# on your PC: open an SSH tunnel
ssh -L 8080:localhost:8080 <user>@<server>
# in your PC's browser: http://tenant1.localhost:8080/  /  http://tenant2.localhost:8080/
#   (*.localhost on your PC maps to local loopback → through the tunnel to the server's port-forward)
```

**Method B: one port-forward per tenant (split by port; tested)**
```bash
kubectl port-forward -n weko3 svc/tenant1-nginx 8081:80    # → http://localhost:8081/
kubectl port-forward -n weko3 svc/tenant2-nginx 8082:80    # → http://localhost:8082/
```
The pages show (the in-Pod nginx uses `server_name _`, and weko allows any Host because `APP_ALLOWED_HOSTS` is not set).
But `THEME_SITEURL` is fixed to `http://<W3FQDN>`, so **absolute links and redirects point at the original hostname**.
For browser use, Method A (matching hostnames) is safer.

> Over SSH, add `ssh -L 8080:localhost:8080 <server>` on your PC, or use
> `kubectl port-forward --address 0.0.0.0 ...` to open it on the LAN (watch your firewall).

---

## Production-fidelity upgrades (Redis Sentinel / persistence / S3)

These were added to get closer to production (JAIRO Cloud). The manifests are in `k8s-weko/`.

### Redis Sentinel (`41-redis-sentinel.yaml`)
- **redis master + 2 replicas + 3 sentinels** in namespace `weko3re` (kept on PVCs).
  The service name matches the instance.cfg default: `weko-sentinel-service.weko3re:26379`, master=`mymaster`.
- On the weko side, `CACHE_TYPE='redissentinel'` (instance.cfg is patched with sed when web/worker start).
- Tenants are **split by DB number inside the shared Redis** (tenant1=0/1/2, tenant2=5/6/7, and they avoid the reserved `CRAWLER=3` / `GROUP_INFO=4`).
- Tested: the worker reaches `ready` through sentinel, master→replica replication works, and `sentinel master mymaster` reports quorum=2.

### Data persistence (PVC / kind `standard` StorageClass)
- PostgreSQL / Elasticsearch / RabbitMQ / Redis (×3) / MinIO all **moved to PVCs** (emptyDir removed).
- For PostgreSQL, the data was kept with **`pg_dumpall` → redeploy the PVC version → restore** (no re-setup).
- Tested: after deleting the `postgresql-0` Pod and remaking it on the same PVC, **188 tables and the admin user were still there**.

### S3 object storage (`40-minio.yaml`)
- Deployed **MinIO** (S3-compatible, PVC). Buckets `weko-backup` / `weko-content` / `weko-esbackup` + **one `weko-<tenant>` per tenant (the real file Location)**.
- The S3 connection info is put into each tenant's Secret (`S3_ENDPOINT_URL=http://minio:9000`, key=`wekominio`).
- **WEKO uploads go to the S3 (MinIO) Location**: after setup, `set-s3-location.sh` sets each tenant DB's `files_location` to `type='s3'` / `uri='s3://weko-<tenant>'` (see "How to apply" below). If `type` is not `s3`, invenio-s3 falls back to PyFilesystem2 and fails with `AWS_ACCESS_KEY_ID not set`.
- Backup example: `pg_dumpall` uploaded to `weko-backup/postgres/` (like JAIRO Cloud's Object Storage).
- Console: `kubectl port-forward -n weko3 svc/minio 9001:9001` → `http://localhost:9001` (wekominio / wekominio-secret-key).

### How to apply (summary)
```bash
cd k8s-weko
kubectl apply -f 40-minio.yaml          # S3 (MinIO)
kubectl apply -f 41-redis-sentinel.yaml # Redis Sentinel (weko3re)
# move PG/ES/RabbitMQ to the PVC versions (to keep data, do pg_dumpall → restore first)
kubectl apply -f 10-postgresql.yaml -f 13-elasticsearch.yaml -f 12-rabbitmq.yaml
bash gen-tenant.sh && kubectl apply -f generated/   # tenants wired for redissentinel + S3
bash provision-tenants.sh                            # remake the vhosts
# remake the ES indices (run es-reinit.sh in each tenant's web container)
# after setup + seeding admin_settings, set file storage to S3 (MinIO):
bash set-s3-location.sh                              # makes the weko-<tenant> bucket + sets files_location to type='s3'
```

### What is still different from production (things you could add next)
- PostgreSQL HA (postgres-operator/Spilo + pgpool) is added in the current full setup (Appendix D / `deploy-*.sh`). pgbouncer is still not used.
- F5 NGINX App Protect (WAF), Shibboleth / GakuNin login, fluentd log collection, and Prometheus monitoring are not deployed.
- Per-tenant TLS certificates on the Ingress (now it uses the Ingress default self-signed certificate).

---

## Building the WEKO image and publishing/swapping it on Docker Hub

You can **build the WEKO application image yourself → publish it to Docker Hub → use it at deploy time**.
The deploy side picks the image with the `WEKO_IMAGE` environment variable (it falls back to the default self-built/public image).

- Default images: arm64=`weko3-web:arm64` / amd64=`weko3-web:amd64` — both **local builds from the newest source**. A prebuilt image is pulled only when you set `WEKO_IMAGE`.
- There is one swap point: `WEKO_IMAGE`, read by `gen-tenant.sh` / `deploy-*.sh` (used in all three places: web, worker, and the seed initContainer). The nginx image uses `WEKO_NGINX_IMAGE`.
- The source is the same `Dockerfile` (`python:3.6-slim-buster` is multi-arch; `Dockerfile.arm64` has **the same content as Dockerfile**).

### Build & push (`build-push-weko.sh`)
```bash
cd /home/mhaya/weko-k8s-sample
# example: publish as <user>/weko3-web:v1 on Docker Hub
DOCKERHUB_USER=<user> REPO=weko3-web ./build-push-weko.sh native v1
#   native    … build for the host's CPU type → push (best, reliable)
#   multiarch … buildx amd64+arm64 into one tag (needs binfmt; an amd64 build on an arm64 host is slow)
#   manifest  … join :v1-amd64/:v1-arm64 (built natively with ARCH_SUFFIX=yes on each arch host) into :v1
```
If you have not run `docker login`, it asks you automatically (a Docker Hub **access token** is best).

**Two ways to make a dual-CPU image**:
| Method | Command | Notes |
|---|---|---|
| **Native build on each arch host + manifest** (best, reliable) | On each host: `ARCH_SUFFIX=yes ./build-push-weko.sh native v1` → then on either: `./build-push-weko.sh manifest v1` | C extensions build cleanly |
| **One-shot multi-arch with buildx** | `./build-push-weko.sh multiarch v1` | Easy, but a non-native CPU type is slow under qemu |

### Swapping the image at deploy time
```bash
# use it in the end-to-end deploy (skips the build and pulls the pushed image)
WEKO_IMAGE=<user>/weko3-web:v1 bash k8s-weko/deploy-arm64.sh          # arm64
WEKO_IMAGE=<user>/weko3-web:v1 bash k8s-weko-amd64/deploy-amd64.sh    # amd64

# replace only web on an existing cluster (make manifests → apply → roll out)
cd k8s-weko
WEKO_IMAGE=<user>/weko3-web:v1 bash gen-tenant.sh
kubectl apply -f generated/
kubectl rollout restart -n weko3 $(awk '!/^#|^$/{print "deploy/"$1"-web"}' tenants.txt | tr '\n' ' ')
```
> kind uses local images, so the image must either have been loaded with `kind load docker-image <user>/weko3-web:v1 --name weko3`
> or be pullable from the nodes (public on Docker Hub, or an imagePullSecret set up). `deploy-*.sh` runs `kind load` for you.

---

## Appendix B: one-shot runbook to build the production-fidelity configuration from scratch

How to start from nothing and come up **with Sentinel + persistence (PVC) + S3 (MinIO) + multi-tenancy from the start**.
Unlike Route A (step by step), this deploys the **production-leaning setup directly**, without the simple backends first.
(To rebuild an existing cluster, run `kind delete cluster --name weko3` first.)

Work from `cd /home/mhaya/weko-k8s-sample`. The manifests are in `k8s-weko/`.

### B-1. Installing the tools (kubectl / kind)
```bash
mkdir -p ~/.local/bin
KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/arm64/kubectl"
curl -sLo ~/.local/bin/kind "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-arm64"
chmod +x ~/.local/bin/kubectl ~/.local/bin/kind; hash -r
```

### B-2. Cluster + Ingress + amd64 emulation
```bash
kind create cluster --config kind-weko-cluster.yaml --wait 120s
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
kubectl wait -n ingress-nginx --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=150s
docker run --rm --privileged tonistiigi/binfmt --install amd64
```

### B-3. Preparing images (build ES + load the weko application)
```bash
cd k8s-weko
docker buildx build --platform linux/amd64 -f Dockerfile.es -t weko-elasticsearch:6.8.23 --load .
kind load docker-image weko-elasticsearch:6.8.23 --name weko3
# WEKO3 is built from the newest source (no prebuilt image)
git clone https://github.com/RCOSDP/weko.git /home/mhaya/weko 2>/dev/null || git -C /home/mhaya/weko pull --ff-only
docker build -f /home/mhaya/weko/Dockerfile -t weko3-web:arm64 /home/mhaya/weko
kind load docker-image weko3-web:arm64 --name weko3
```

### B-4. Shared platform (namespace / nginx config / S3 / Sentinel / persisted backends)
```bash
kubectl apply -f 00-namespace.yaml -f 21-nginx-config.yaml
kubectl apply -f 40-minio.yaml            # S3 (MinIO) + PVC
kubectl apply -f 41-redis-sentinel.yaml   # Redis Sentinel HA (weko3re) + PVC
kubectl apply -f 10-postgresql.yaml -f 13-elasticsearch.yaml -f 12-rabbitmq.yaml   # PG/ES/MQ, all PVC versions
# wait until ready
kubectl wait -n weko3 --for=condition=ready pod -l app=postgresql --timeout=180s
kubectl wait -n weko3 --for=condition=ready pod -l app=elasticsearch --timeout=300s
kubectl wait -n weko3 --for=condition=ready pod -l app=rabbitmq --timeout=180s
kubectl wait -n weko3re --for=condition=ready pod -l app=redis --timeout=180s
# make the MinIO buckets
kubectl run mc-init -n weko3 --rm -i --restart=Never --image=minio/mc:RELEASE.2025-04-08T15-39-49Z -- \
  sh -c 'mc alias set l http://minio:9000 wekominio wekominio-secret-key && mc mb -p l/weko-backup l/weko-content l/weko-esbackup'
```

### B-5. Tenant definitions → generation → provisioning
Prepare `k8s-weko/tenants.txt` (for a from-scratch build, use **INIT=yes** = fresh setup). Example:
```
# NAME  DBNAME  HOST  ADMIN_EMAIL  ADMIN_PASS  INIT  CACHE_DB SESSION_DB CELERY_DB
tenant1  tenant1  tenant1.localhost  admin@tenant1.local  adminpass1  yes  0 1 2
tenant2  tenant2  tenant2.localhost  admin@tenant2.local  adminpass2  yes  5 6 7
```
> Give each tenant Redis DBs that avoid the reserved `CRAWLER=3` / `GROUP_INFO=4` (tenant1=0/1/2, tenant2=5/6/7, …).
```bash
bash gen-tenant.sh                    # makes generated/<name>.yaml (redissentinel/S3/PVC-aware)
kubectl apply -f generated/           # per-tenant config/secret/web/svc/ingress
bash provision-tenants.sh             # make the per-tenant PostgreSQL DB and RabbitMQ vhost
# wait for web (uwsgi) to start (minutes under emulation)
for t in tenant1 tenant2; do
  kubectl rollout status deploy/${t}-web -n weko3 --timeout=600s
done
```

### B-6. Setting up each tenant (DB + ES together)
`weko-init.sh` is env-driven and runs `db init/create → index init/queue init → ES stats → users/roles/access`.
Run it inside the web container for each tenant (**30–40 minutes each** under emulation; can run in parallel).
```bash
for t in tenant1 tenant2; do
  POD=$(kubectl get pod -n weko3 -l app=${t}-web -o jsonpath='{.items[0].metadata.name}')
  # in a normal terminal, stdin redirection works:
  kubectl exec -i -n weko3 $POD -c web -- bash < weko-init.sh &
  # ↑ if that does not stream well in your environment, base64 is reliable:
  # B64=$(base64 -w0 weko-init.sh); kubectl exec -n weko3 $POD -c web -- bash -lc "echo $B64 | base64 -d | bash" &
done
wait
```

### B-7. Fixing the 500 (seeding admin_settings) + restarting web
```bash
PG=$(kubectl get pod -n weko3 -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
for db in tenant1 tenant2; do
  kubectl exec -n weko3 $PG -- psql -U weko -d $db \
    -c "INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb) ON CONFLICT DO NOTHING;"
done
kubectl rollout restart deploy/tenant1-web deploy/tenant2-web -n weko3
for t in tenant1 tenant2; do kubectl rollout status deploy/${t}-web -n weko3 --timeout=600s; done

# set file storage to the S3 (MinIO) Location (make buckets + set files_location to type='s3')
bash set-s3-location.sh
```
> After `set-s3-location.sh`, uploads go to `s3://weko-<tenant>` (MinIO). Without it, `files_location.type` stays `None` and uploads fail with `AWS_ACCESS_KEY_ID not set`, because invenio-s3 falls back to PyFilesystem2.

### B-8. Connectivity check
```bash
# the first request takes a while to warm up
for h in tenant1.localhost tenant2.localhost; do
  curl -s -o /dev/null -w "$h -> %{http_code}\n" -H "Host: $h" http://localhost/ --max-time 240
done
# expected: 200 for both tenants / /admin 302 / /api/records 200
```

> **Things to check**: Redis Sentinel (`kubectl exec -n weko3re deploy/sentinel -- redis-cli -p 26379 sentinel master mymaster`),
> persistence (`kubectl get pvc -A`), S3 (the `weko-backup` etc. buckets + the per-tenant `weko-<tenant>`),
> and the file Location (`kubectl exec -n weko3 <PG> -- psql -U weko -d tenant1 -c "SELECT name,type,uri FROM files_location;"` should show `type=s3` / `uri=s3://weko-tenant1`).
> For the backup example (`pg_dumpall` → MinIO) and port forwarding, see the sections above.

---

## HA clustering (operator approach) and arm64 nativization

The final form: the backends become **3-node HA clusters** using the same operator approach as production (JAIRO Cloud),
and the weko application and Elasticsearch are made **arm64 native** to remove emulation.

### Clustering the three backends

| Backend | Approach | Manifest / installation |
|---|---|---|
| **PostgreSQL** | **Zalando postgres-operator** + Patroni 3 nodes (arm64 spilo-17 = PG17, synchronous replication, master=`weko-postgresql` / replica=`weko-postgresql-repl`) | `51-postgresql-ha.yaml` (`postgresql` CR) + `pgop-*.yaml` (operator) |
| **RabbitMQ** | **RabbitMQ Cluster Operator** + a 3-node `RabbitmqCluster` (rabbitmq:4.0.9) | `50-rabbitmq-cluster.yaml` (needs cert-manager) |
| **Elasticsearch** | **3-node cluster** (arm64 native, real kui.txt, kuromoji, repository-s3, zen discovery, replica=1 so shards spread across nodes) | `13-elasticsearch.yaml` (cluster settings passed with `-E` arguments) |

```bash
# the operators
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml
kubectl apply -f pgop-*.yaml            # Zalando postgres-operator (the ghcr.io/zalando build = arm64)
# the clusters themselves
kubectl apply -f 50-rabbitmq-cluster.yaml 51-postgresql-ha.yaml 13-elasticsearch.yaml
```

**Key points / pitfalls:**
- Zalando's `registry.opensource.zalan.do` mirror is **amd64 only** → use the **`ghcr.io/zalando`** build. spilo-13/14 have no arm64 → use **spilo-17**.
- postgres-operator resets the weko user's password to a random value → patch the secret's password back to `weko` and pin it with `ALTER ROLE weko PASSWORD 'weko'`. The endpoint is `INVENIO_POSTGRESQL_HOST=weko-postgresql` (or `pgpool` in the current setup).
- The newest RabbitMQ operator's startup probe `/api/health/checks/reached-target-cluster-size` **does not exist in rabbitmq 4.0.9 and returns 404** → change it to `rabbitmq-diagnostics check_running` with `override.statefulSet`. Writing `default_user` into `additionalConfig` breaks the probe.
- The custom arm64 ES image does not have the official image's env→settings step → pass cluster settings as **`-E` command-line arguments**.

### Making the weko application arm64 native (the key stability fix)

Emulated amd64 weko **segfaults while handling requests** under qemu, and the core dumps fill the disk
(one time this took the host from 294GB free to 0 and broke the kind node's image layers). **Going arm64 native fixed this for good.**

```bash
cd /home/mhaya/weko                       # the weko source tree is the build context
docker build -f Dockerfile.arm64 -t weko3-web:arm64 .
kind load docker-image weko3-web:arm64 --name weko3
# set the image in gen-tenant.sh to weko3-web:arm64 and redeploy
```
Result: **app startup 163s → 5s (30× faster)**, no more qemu segfaults / core dumps / `listen queue full`, and **fully stable at 200×15/15**.

### weko application-layer bug fixes (built into gen-tenant.sh's startup command, so they stay)

| Symptom | Cause | Fix |
|---|---|---|
| `/login/` returns 500 (`RecursionError`) | `invenio_oauthclient`'s before_first_request template override is **not idempotent**; if it runs twice on parallel requests, `OAUTHCLIENT_LOGIN_USER_TEMPLATE_PARENT` points to itself → endless `extends` | Add `OAUTHCLIENT_TEMPLATE_KEY = None` to invenio.cfg to turn off the override |
| `/api/records/` returns 500 (`KeyError: 'aggregations'`) | `RECORDS_REST_FACETS` is empty, so the ES response has no aggregations, and `fix_aggregations_accessrights` reads `data['aggregations']` **before it checks whether it is on** | sed-patch `weko_search_ui/utils.py` to use `data.get('aggregations', {})` |

### Final verification (both tenants)
```
/  → 200   /login/ → 200   /admin/ → 302   /api/records/ → 200   (all stable at 200×15/15)
PostgreSQL: master + 2 replicas / RabbitMQ: 3/3 / Elasticsearch: green, 3 nodes / Redis: Sentinel 6/6 / MinIO: running
weko web: weko3-web:arm64 (native)  15 PVCs  host memory ~18GiB
```

---

## NFS shared storage (equivalent to production's `/fs-config`, `/fs-data`)

Production (JAIRO Cloud) mounts a shared FS on OKE File Storage = **NFS** (`/fs-config`, `/fs-data`, `/fs-nginx`, etc.)
into weko web with PVCs that use `storageClassName: nfs`. This copies that.

### The NFS server (`60-nfs-server.yaml`)
- **nfs-ganesha (user-space NFS)** = `registry.k8s.io/sig-storage/nfs-provisioner` (**arm64 native, no kernel nfsd needed**).
- It ships a dynamic provisioner and gives the **RWX (ReadWriteMany) StorageClass `nfs`**.
```bash
kubectl apply -f 60-nfs-server.yaml
kubectl get sc nfs      # provisioner weko.example.com/nfs
```
> Pitfall: the ClusterRole needs `get` on `services`/`endpoints` (the provisioner reads its own Service to get the NFS IP; without it you get `error getting service` and ProvisioningFailed).

### Moving weko's shared FS to NFS (RWX) (already built into `gen-tenant.sh`)
Like production's `config-pvc` / `data-pvc`, the shared FS is moved to NFS per tenant:

| Mount | Production | NFS PVC | Contents |
|---|---|---|---|
| `.../var/instance/conf` | `/fs-config/<tenant>` | `<tenant>-conf` (static PV, RWX 1Gi) | `invenio.cfg` / `uwsgi.ini` |
| `.../var/instance/data` | `/fs-data/<tenant>` | `<tenant>-data` (static PV, RWX 5Gi) | Theme `_variables.scss` / `indextree` (* uploaded files are not here → S3) |
| `/etc/shibboleth` (nginx) | `/fs-shibboleth/<tenant>` | `<tenant>-shib` (static PV, RWX 1Gi) | Shibboleth SP config (`shibboleth2.xml` etc.). `provision-nfs.sh` seeds it from weko-k8s's `shibboleth_template` and puts the FQDN in place of `__WEKO3_VHOST__` |
| `/etc/nginx` (nginx) | `/fs-nginx/<tenant>` | `<tenant>-nginx-pvc` (static PV, RWX 1Gi) | The whole nginx config. `provision-nfs.sh` seeds it from `nginx_template` (the `seed-nginx` initContainer fills gaps from the weko nginx image) and sets `server_name` to the tenant FQDN |

**The Pod layout matches production's `weko-k8s/deploy/weko/manifest_template/deploy-web.yaml`**:
initContainer `init` (makes `invenio.cfg` with jinja2) plus `seed-data` / `seed-nginx` → containers `nginx`
(the self-built WEKO nginx with the Shibboleth SP) / `web` (uwsgi) / `worker` (celery), with `fsGroup: 1000`,
`hostAliases` (own FQDN → 127.0.0.1), `RollingUpdate(maxSurge 1, maxUnavailable 0)` and `nodeSelector: nodeType=WEKO`.
The shared FS covers conf, data, shib and nginx (static stays Pod-local on emptyDir).

Notes (done for you in `gen-tenant.sh`):
- **conf**: NFS starts empty, so at startup we `cp -f /code/scripts/uwsgi.ini` and make `invenio.cfg` with `jinja2` (the absolute symlink at `var/instance/invenio.cfg` points into NFS).
- **data**: an empty NFS mount hides the image's `_variables.scss`, so the CSS (sass) `@import "../../../data/_variables"` fails and **the top page returns 500**. → An **initContainer** (`weko3-web:arm64`) mounts the NFS data at `/seed` and copies the theme files with `cp -an .../data/. /seed/`.
- **Uploads go to the S3 (MinIO) Location** (not the NFS share): after setup, `set-s3-location.sh` sets the DB `files_location` to `type='s3'` / `uri='s3://weko-<tenant>'` plus the S3 connection info (access_key/secret_key/s3_endpoint_url). weko writes into the MinIO bucket with `invenio-s3`'s s3fs.
  - Careful: if `location.type` stays `None`, invenio-s3 falls back to PyFilesystem2 and fails with `AWS_ACCESS_KEY_ID not set`. Always set `type='s3'`.
  - `gen-tenant.sh` already sets `instance.cfg`'s `S3_ACCCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_ENDPOINT_URL` to read from environment variables. path-style and `signature_version=s3v4` are handled by invenio-s3.

### Verification (measured 2026-07-23, full end-to-end deploy on the real arm64 machine)
```
8 static PVs (conf/data/shib/nginx × 2 tenants) all Bound, RWX, storageClass=nfs-static
On the NFS server: /export/fs-config/<t>(2) /fs-data/<t>(3) /fs-shibboleth/<t>(25) /fs-nginx/<t>(13 files)
All endpoints: / 200 / /login/ 200 / /admin/ 302 / /api/records/ 200 (both tenants, stable at 200×10/10)
PG: Leader + Sync Standby + Replica / ES: green, 3 nodes / Redis: 6/6 / RabbitMQ: weko user + vhosts
files_location: type=s3, uri=s3://weko-<tenant> / secret keys: a different value per tenant
```

> **Operational note**: running `kind delete cluster` while Pods still mount NFS volumes can wedge
> the node containers — the NFS server goes away first, the mounts hang, and the container can no longer
> be removed. Delete the Pods first (for example `kubectl delete deploy -n weko3 --all`), then the cluster.

### The persistence picture, and things to note
| Type | Targets | Notes |
|---|---|---|
| **local-path** (RWO) | PostgreSQL / Elasticsearch / RabbitMQ / Redis / MinIO / backing store of the NFS export | Kept across Pod restarts. Lost on `kind delete cluster` |
| **NFS** (RWX) | Per-tenant conf / data (`/fs-config`, `/fs-data`) | Shared across Pods/nodes. Lets you run more than one weko web replica |

> For **full host persistence** (surviving `kind delete cluster`), the backing store of the NFS export (now local-path)
> must be a **host directory**: either remake kind with `extraMounts` to mount a host dir into the nodes, or run an
> external NFS server on the host.

---

## Appendix C: Runbook when arm64 is not involved (x86_64 / amd64 servers)

On an amd64 (x86_64) server, **you do not need emulation or arm64 builds**, so this is **simpler and more stable**.
The public/official images for the weko application, Elasticsearch, Spilo, and RabbitMQ are all amd64 native,
so everything that arm64 needed — **qemu emulation, self-built arm64 images, core-dump fixes — is not needed**.
(The main text is for arm64; below are the changes from Appendix B.)

### Why amd64 is easier
- `tonistiigi/binfmt` (emulation registration) is **not needed**
- **No self-built arm64 images** for weko / ES (use the public amd64 images as they are)
- **No emulation workarounds** such as fewer uwsgi processes or isolating core dumps
- The first request is fast (no multi-minute wait like arm64 emulation). No qemu segfault → core dump → full disk problems

### C-1. Tools / cluster / Ingress (skipping binfmt)
```bash
mkdir -p ~/.local/bin
KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/amd64/kubectl"
curl -sLo ~/.local/bin/kind    "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-amd64"
chmod +x ~/.local/bin/kubectl ~/.local/bin/kind; hash -r
kind create cluster --config kind-weko-cluster.yaml --wait 120s
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
# ★ the docker run ... tonistiigi/binfmt step is not needed
```

### C-2. Images (amd64 native, minimal building)
```bash
cd k8s-weko
# weko application: get the newest source and build it natively for amd64 (no --platform needed)
git clone https://github.com/RCOSDP/weko.git /home/mhaya/weko 2>/dev/null || git -C /home/mhaya/weko pull --ff-only
docker build -f /home/mhaya/weko/Dockerfile -t weko3-web:amd64 /home/mhaya/weko
kind load docker-image weko3-web:amd64 --name weko3
# Elasticsearch: native build of the weko ES on the official amd64 image (real kui.txt/kuromoji/repository-s3)
docker build -f /home/mhaya/weko/elasticsearch/Dockerfile \
  --build-arg ELASTICSEARCH_S3_ACCESS_KEY=wekominio \
  --build-arg ELASTICSEARCH_S3_SECRET_KEY=wekominio-secret-key \
  --build-arg ELASTICSEARCH_S3_ENDPOINT=http://minio:9000 \
  --build-arg ELASTICSEARCH_S3_BUCKET=weko-esbackup \
  -t weko-elasticsearch:6.8.23 /home/mhaya/weko
kind load docker-image weko-elasticsearch:6.8.23 --name weko3
```

### C-3. Manifest changes (rewriting for amd64)
| File | arm64 version | amd64 version |
|---|---|---|
| `gen-tenant.sh` | `image: weko3-web:arm64` | `image: weko3-web:amd64` (built from the newest source; you can remove the emulation workarounds ulimit/cores/processes=1) |
| `13-elasticsearch.yaml` | `weko-elasticsearch:6.8.23-arm64` + `-E` args | `weko-elasticsearch:6.8.23` (**the official base does convert env → settings**, so env `discovery.zen.*` works instead of `-E` args) |
| `50-rabbitmq-cluster.yaml` | rabbitmq:4.0.9 (multi-arch) | **No change needed** |
| `51-postgresql-ha.yaml` | spilo-17 (arm64) | **No change needed** (spilo-17 runs on amd64). For strict production parity, set the operator's `docker_image` to `registry.opensource.zalan.do/acid/spilo-13:2.0-p6` (= production PG13) |

```bash
sed -i 's#image: weko3-web:arm64#image: weko3-web:amd64#' gen-tenant.sh
sed -i 's#weko-elasticsearch:6.8.23-arm64#weko-elasticsearch:6.8.23#' 13-elasticsearch.yaml
```

### C-4. Deploy → set up → check
Same flow as [HA clustering](#ha-clustering-operator-approach-and-arm64-nativization) / Appendix B:
operators (cert-manager / rabbitmq / postgres-operator) → apply `40`–`51` → `gen-tenant.sh` → `provision-tenants.sh` → `weko-init.sh` per tenant → seed admin_settings → **`set-s3-location.sh` (set file storage to the S3 (MinIO) Location)** → connectivity check.
(For amd64, `k8s-weko-amd64/deploy-amd64.sh` runs steps 1)–9) in one pass. Details in [`k8s-weko-amd64/README-amd64.en.md`](./k8s-weko-amd64/README-amd64.en.md).)

- **App-layer bugs (/login, /api/records)**: they do not happen with the public `mhayashi55/weko3-web:latest` (it already returns 200). When you build from source, keep the matching fixes in `gen-tenant.sh` so the same app-layer patches apply as on arm64 (they are safe: `|| true` / config appends only).
- The Dockerfile used for the build is `/home/mhaya/weko/Dockerfile` (the amd64 version).

> **Summary**: on amd64, emulation, arm64 builds, and core-dump fixes are all not needed — fewer steps and
> more stable than the arm64 version. The **architecture itself** (HA clustering with operators, Sentinel, S3,
> persistence, multi-tenancy) **is the same as the arm64 version.**

---

## Appendix D: Building the current full configuration (final form) from scratch in one pass on arm64

This builds the HA clustering, arm64 nativization, NFS, and S3 (MinIO) Location from the main text **in one script instead of in stages**.
The result is **exactly the setup now running on the machine** (Appendix B does not reach this point → see the table).

| | Appendix B (Route B) | **Appendix D (Route D)** |
|---|---|---|
| PostgreSQL | Standalone (`10-postgresql.yaml`) | **Patroni 3-node HA** (operator, spilo-17 arm64) + **pgpool** |
| RabbitMQ | Standalone (`12-rabbitmq.yaml`) | **3-node cluster** (Cluster Operator) |
| Elasticsearch | 3 nodes (same) | 3 nodes (arm64 native, `-E` args) |
| weko / ES images | Uses existing ones | **Self-built arm64 native** |
| NFS (RWX) shared FS | Not included | **Included** (conf/data) |
| Redis Sentinel / persistence / S3 Location / multi-tenancy | Yes | Yes |

### D-0. Prerequisites (arm64 host)
- arm64 Linux / docker (runs without sudo) / kubectl and kind (for example in `~/.local/bin`) / plenty of free disk.
- Put the **weko source** in place (with the `Dockerfile.arm64` files for ES/weko). The default path is `/home/mhaya/weko`.
- Kernel: `vm.max_map_count=262144` (ES needs it to start), and raise the inotify limits (many Pods).
- **binfmt/qemu are not needed** (everything is arm64 native).

```bash
# example: sysctl (if not set yet)
sudo sysctl -w vm.max_map_count=262144
```

### D-1. Run it (one command)
```bash
cd k8s-weko
bash deploy-arm64.sh                     # runs 1) cluster … 9) connectivity in one pass (includes the arm64 builds of ES/weko; tens of minutes)
# if the weko source is elsewhere: WEKO_SRC=/opt/weko bash deploy-arm64.sh
# to re-run on an existing cluster and follow the INIT column: FORCE_INIT=no bash deploy-arm64.sh
```
What `deploy-arm64.sh` does:
0. **Get/update the newest weko source** (`git clone` when missing, `git pull` when present; set with `WEKO_REPO` / `WEKO_BRANCH` / `WEKO_SRC_UPDATE`)
1. kind cluster + ingress (**no binfmt**)
2. Images: native builds of `weko3-web:arm64` / `weko3-nginx:arm64` (the Shibboleth-SP front proxy) / `weko-elasticsearch:6.8.23-arm64` **from that source** → kind load. It also builds `weko-pgpool:4.2.2-arm64` (no official arm64 pgpool image) → kind load.
   - **weko3-nginx** is built from `$WEKO_SRC/nginx/Dockerfile`. **arm64-specific point**: supervisord.conf hardcodes the `shibauthorizer`/`shibresponder` paths to `/usr/lib/x86_64-linux-gnu/shibboleth/`, so deploy-arm64.sh rewrites them `x86_64 → aarch64-linux-gnu` with a RUN sed before building (skip it and shibd will not start). It also rewrites the `.deb` name `focal_amd64.deb → focal_arm64.deb`, but that does nothing with the current source (the Dockerfile now uses the `focal_*.deb` wildcard; kept for older-source compatibility). None of these images need a registry (local build → `kind load`, `imagePullPolicy: Never`); set `WEKO_IMAGE`/`WEKO_NGINX_IMAGE` only to use prebuilt images.
3. Operators: cert-manager / rabbitmq / **postgres-operator pinned to `ghcr.io/zalando` (arm64) and spilo-17**
4. Shared platform: **ES ×3 / PG (Patroni) ×3 / RabbitMQ ×3 / Redis Sentinel / MinIO / NFS** (all on PVCs) + the common MinIO buckets
5. Set the PG `weko` password to `weko` (the operator resets it)
5.5. Deploy **pgpool** (it sits between weko and PostgreSQL: connection pool + read load-balancing → Patroni primary/replica)
6. `gen-tenant.sh` → `provision-nfs.sh` (make the per-tenant /fs-* directories + seed the nginx/Shibboleth configs) → apply → `provision-tenants.sh`
7. `weko-init.sh` per tenant (default `FORCE_INIT=yes` = fresh setup for all tenants, in parallel)
8. Seed admin_settings + **`set-s3-location.sh` (set files_location to S3 (MinIO))** + restart web
9. Connectivity check (`http://tenantN.localhost/`)

> Expected after it finishes: both tenants return `/` 200, `/login/` 200, `/admin/` 302, `/api/records/` 200;
> PG master + 2 replicas / RabbitMQ 3/3 / ES green with 3 nodes / Redis Sentinel 6/6 / MinIO running;
> `files_location.type=s3` (`uri=s3://weko-<tenant>`). Host memory ~18GiB.

---

## Known caveats

- **No data persistence (in the small §1–9 setup)**: PostgreSQL / Elasticsearch use `emptyDir`. Data is lost on Pod restart → you must set up again. To keep data, switch to PVCs (kind's `standard` StorageClass). The Appendix B/D setups already use PVCs.
- **Slow under emulation**: the first request and the `invenio` commands take a long time. Page loads after the first take seconds.
- **Some production OKE-only features are not used**: pgbouncer / WAF, and the roughly 10 custom images, are not reproduced. (pgpool, Redis Sentinel, and the postgres-operator ARE used in the current full setup.)
