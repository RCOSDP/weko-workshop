# weko3 k8s Environment — Construction Guide

How to build a real Kubernetes cluster (nodes + full API server) on one host with **kind**, using
[RCOSDP/weko-k8s](https://github.com/RCOSDP/weko-k8s).

- Made: 2026-07-20 (updated 2026-07-21: multi-tenancy → production fidelity → **HA clustering + arm64 native**)
- Target host: `/home/mhaya/weko-k8s-sample`
- Status: **PostgreSQL/RabbitMQ/Elasticsearch are now 3-node HA clusters, and the weko application is arm64-native**
  - Both `http://tenant1.localhost/` and `http://tenant2.localhost/` return `/` 200, `/login/` 200, `/admin/` 302, `/api/records/` 200 (**stable at 200×15/15**)
  - For details on HA clustering, arm64 nativization, and app-layer bug fixes, see the ["HA clustering and arm64 nativization" section of `README.en.md`](./README.en.md)
- Manifest set: `/home/mhaya/weko-k8s-sample/k8s-weko/`
- **The copy-paste runbook is [`README.en.md`](./README.en.md)** (this document is the background, details, and pitfalls)

> This guide builds a **small single-tenant setup** from nothing in §1–9. Then §10 sums up the
> **multi-tenancy** and **production-fidelity upgrades (Sentinel / persistence / S3)** added on top.

---

## 0. Current final configuration (summary)

```
[Host: arm64] kind cluster "weko3"
  control-plane … API server etc. + ingress-nginx (host 80/443)
  worker (nodeType=WEKO) … tenant1-web / tenant2-web (each: nginx+web+worker)
  worker2(nodeType=DATA) … shared: PostgreSQL / Elasticsearch / RabbitMQ / MinIO(S3)  * all on PVCs
                            namespace weko3re … Redis master + 2 replicas + 3 sentinels * all on PVCs
```

| Layer | Setup | Separation key (per tenant) |
|---|---|---|
| Web | `<tenant>-web` (nginx+uwsgi+celery) + Ingress (host=FQDN) | FQDN |
| DB | Shared PostgreSQL (PVC) | DB name |
| Search | Shared Elasticsearch 6.8.23 (PVC) | Index prefix |
| MQ | Shared RabbitMQ (PVC) | vhost `<name>/` |
| Cache | Shared Redis **Sentinel HA** (PVC) | Redis DB number |
| Object storage | Shared MinIO (S3) (PVC) | Bucket/prefix |

**Manifest map:**

| File | Role | Notes |
|---|---|---|
| `00-namespace.yaml` | namespace weko3 | |
| `10-postgresql.yaml` | PostgreSQL (PVC version) | StatefulSet |
| `12-rabbitmq.yaml` | RabbitMQ (PVC version) | StatefulSet |
| `13-elasticsearch.yaml` | Elasticsearch 6.8.23 + kui.txt (PVC version) | StatefulSet |
| `40-minio.yaml` | MinIO (S3, PVC) | 3 buckets + per-tenant `weko-<tenant>` |
| `41-redis-sentinel.yaml` | Redis Sentinel HA (weko3re, PVC) | master + 2 replicas + 3 sentinels |
| `21-nginx-config.yaml` | Front nginx config (shared by all tenants) | uwsgi_pass |
| `tenants.txt` + `gen-tenant.sh` | Tenant definitions → manifest generation | redissentinel-aware. Secret keys (`SECRET_KEY` etc.) come from `.secret-seed`, one set per tenant |
| `provision-tenants.sh` | Makes the per-tenant PG DB / RabbitMQ vhost | |
| `provision-nfs.sh` | Makes the per-tenant `/fs-nginx`, `/fs-shibboleth`, `/fs-config`, `/fs-data` directories on the shared FS (NFS) and seeds the nginx/Shibboleth templates | Like production's `make_volumes.sh`; it backs the static PVs, so run it before you apply |
| `weko-init.sh` / `es-reinit.sh` | DB setup / ES index setup | env-driven |
| `set-s3-location.sh` | Makes the per-tenant bucket + sets `files_location` to the S3 type | run after setup |
| `deploy-arm64.sh` | Builds the current full setup (HA/Sentinel/persistence/NFS/S3/multi-tenant) from nothing in one pass | README Appendix D. amd64: `k8s-weko-amd64/deploy-amd64.sh` |
| `build-push-weko.sh` (top level) | Builds the WEKO image → pushes to Docker Hub (native/multiarch/manifest) | Swap images with the `WEKO_IMAGE` environment variable. `Dockerfile` and `Dockerfile.arm64` have the same content |
| `Dockerfile.es` | Builds ES 6.8.23 + kuromoji/icu | amd64 |
| ~~`11-redis.yaml` / `20-weko-config.yaml` / `30-weko-web.yaml`~~ | Old single-tenant versions | Not used from §10 on |

---

## 1. Prerequisites / environment

| Item | Value | Notes |
|---|---|---|
| Architecture | **arm64 (aarch64)** | The official weko images are amd64 only → you need emulation |
| CPU / RAM / Disk | 20 cores / 121GB / 294GB free | Plenty |
| Docker | 29.1.3 | **Works without sudo** (in the docker group) |
| sudo | **Needs a password, so you cannot use it** | Binaries go in `~/.local/bin` |
| OS | Linux 6.17 (Ubuntu family) | — |

### Why kind

`weko-k8s` is made for multi-tenant production on **Oracle Kubernetes Engine (OKE)**.
To "build both the nodes and the API server yourself" on one host, we use **kind (Kubernetes in Docker)**.
It treats Docker containers as k8s nodes and builds a real control-plane / worker / API server.

---

## 2. Installing the tools

`sudo` is not usable, so put the binaries in `~/.local/bin`, which is on PATH.

```bash
mkdir -p ~/.local/bin

# kubectl (arm64)
KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/arm64/kubectl"
chmod +x ~/.local/bin/kubectl

# kind (arm64)
curl -sLo ~/.local/bin/kind "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-arm64"
chmod +x ~/.local/bin/kind

# check
hash -r
kubectl version --client
kind version    # kind v0.30.0
```

Installed versions: kubectl **v1.36.2** / kind **v0.30.0**.

---

## 3. Getting the repository

```bash
cd /home/mhaya/weko-k8s-sample
git clone --depth 1 https://github.com/RCOSDP/weko-k8s.git
```

Key directories:

| Path | Content |
|---|---|
| `weko-k8s/deploy/weko/manifest_template/` | Deployment/Service/Ingress/ConfigMap templates for the weko application |
| `weko-k8s/deploy/{postgresql,elasticsearch,redis,rabbitmq,...}` | Manifests for each backend (for OKE) |
| `weko-k8s/scripts/make_weko_manifests.sh` | Makes real manifests from the templates |
| `weko-k8s/scripts/deploy_weko.sh` | Applies the made manifests |

---

## 4. kind cluster configuration file

`kind-weko-cluster.yaml` (1 control-plane + 2 workers).
The workers get labels to match weko-k8s's node selector `nodeType=WEKO`.

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: weko3
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:            # open ingress on host 80/443
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
  - role: worker
    labels:
      nodeType: WEKO              # runs the weko application (web/nginx/worker)
  - role: worker
    labels:
      nodeType: DATA             # runs the backends (DB/ES/Redis/MQ)
```

---

## 5. Creating the cluster

```bash
cd /home/mhaya/weko-k8s-sample
kind create cluster --config kind-weko-cluster.yaml --wait 120s
```

### Check

```bash
kubectl cluster-info
kubectl get nodes -L nodeType,ingress-ready
kubectl get pods -n kube-system
```

Expected state (all 3 nodes Ready):

```
NAME                  STATUS   ROLES           NODETYPE   INGRESS-READY
weko3-control-plane   Ready    control-plane              true
weko3-worker          Ready    <none>          WEKO
weko3-worker2         Ready    <none>          DATA
```

`kube-apiserver / etcd / kube-scheduler / kube-controller-manager / coredns / kube-proxy / kindnet (CNI)` must all be
Running on the control-plane.

---

## 6. Installing the Ingress controller

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml

# wait for Ready
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=150s
```

### Connectivity check

```bash
curl -s  -o /dev/null -w "HTTP %{http_code}\n" http://localhost:80/
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://localhost:443/
# → both 404 (this is fine: the controller is running, but no routes are set yet)
```

---

## 7. Enabling amd64 emulation

The weko application images (`mhayashi55/weko3-web` / `mhayashi55/weko3-nginx`) are **amd64 only**.
To run them on an arm64 host, register qemu binfmt (the host kernel is shared with the kind nodes).

```bash
docker run --rm --privileged tonistiigi/binfmt --install amd64
```

### Check (run an amd64 container inside the cluster)

```bash
docker pull --platform linux/amd64 amd64/alpine:latest
docker tag amd64/alpine:latest amd64-emu-test:local
kind load docker-image amd64-emu-test:local --name weko3

kubectl run amd64-test --restart=Never --image=amd64-emu-test:local \
  --image-pull-policy=Never \
  --overrides='{"spec":{"nodeSelector":{"nodeType":"WEKO"}}}' \
  -- sh -c 'echo ARCH=$(uname -m)'
kubectl logs amd64-test    # → ARCH=x86_64 means it worked
kubectl delete pod amd64-test
```

> ⚠️ **Important**: pulling amd64 images **straight from the in-cluster containerd often fails**.
> **Pull on the host with `docker pull --platform linux/amd64` and load with `kind load docker-image`** — that is reliable.
> Always load the weko application images this way.

---

## 8. Deploying weko3 (simple configuration — done)

`weko-k8s` targets OKE production and needs `postgres-operator(Spilo)` / `pgpool` / `Redis Sentinel` /
a custom ES / WAF / Oracle Object Storage, plus about 10 custom images that are not in the repository.
On one host it was first built in a **simple configuration**.

The manifests are in `k8s-weko/`. They are shown in the order you apply them.

### 8.0 Important prerequisites (findings from the weko image)

Things found by looking inside `mhayashi55/weko3-web:latest`:

| Topic | Detail |
|---|---|
| ES version | **You need Elasticsearch 6.x** (client `elasticsearch==6.1.1`). ES7 will not work |
| ES plugins | You need `analysis-kuromoji` and `analysis-icu` |
| ES dictionary file | The item mapping points to char_filter `mappings_path: kui.txt` → put `kui.txt` in the ES config |
| Config generation | `jinja2 /code/scripts/instance.cfg > var/instance/conf/invenio.cfg` (env expansion with `environ()`). The bundled instance.cfg already has `CACHE_TYPE='redis'` |
| uwsgi | `socket = 0.0.0.0:5000` (**uwsgi protocol**) → you must have an nginx front end that does `uwsgi_pass` |
| Initialization | The full steps are in `/code/scripts/populate-instance.sh` (`db init/create` → `index init` → users/roles/access) |

### 8.1 Backends (`k8s-weko/10–13`)

- **PostgreSQL 13** (`postgres:13`, arm64) … `10-postgresql.yaml`
- **Redis 6.2** (`redis:6.2`, arm64) … `11-redis.yaml` (standalone, not Sentinel; `CACHE_TYPE=redis`)
- **RabbitMQ 3.13** (`rabbitmq:3.13-management`, arm64) … `12-rabbitmq.yaml` (can do quorum queues; default vhost `/`)
- **Elasticsearch 6.8.23 + kuromoji/icu** (self-built amd64, emulated) … `13-elasticsearch.yaml`

Building and loading the ES image:
```bash
cd k8s-weko
docker buildx build --platform linux/amd64 -f Dockerfile.es -t weko-elasticsearch:6.8.23 --load .
kind load docker-image weko-elasticsearch:6.8.23 --name weko3

kubectl apply -f 00-namespace.yaml -f 10-postgresql.yaml -f 11-redis.yaml \
               -f 12-rabbitmq.yaml -f 13-elasticsearch.yaml
```
> `13-elasticsearch.yaml` has a ConfigMap for `kui.txt` (an empty file = no character mappings), mounted with subPath at
> `/usr/share/elasticsearch/config/kui.txt`.
> The real weko ES image ships a kui.txt for character normalization, but index creation works with an empty one.

### 8.2 weko config and application (`k8s-weko/20–30`)

```bash
docker pull --platform linux/amd64 mhayashi55/weko3-web:latest
kind load docker-image mhayashi55/weko3-web:latest --name weko3

kubectl apply -f 20-weko-config.yaml   # ConfigMap + Secret (endpoints, admin login)
kubectl apply -f 21-nginx-config.yaml  # front nginx (uwsgi_pass) config
kubectl apply -f 30-weko-web.yaml      # Deployment (nginx+web+worker) + Service + Ingress
```
- Pod layout = `nginx (stock nginx:alpine)` + `web (uwsgi:5000)` + `worker (celery)` (1 Pod, `nodeType=WEKO`)
- web/worker remake invenio.cfg with `jinja2` at startup, before they start uwsgi / celery
- The complex production nginx (Shibboleth/SSL/AppProtect) is replaced by stock nginx + `uwsgi_pass 127.0.0.1:5000`

### 8.3 DB / ES initialization

Run the same steps as `populate-instance.sh` inside the web container (same as the contents of `scripts/`):
```bash
POD=$(kubectl get pod -n weko3 -l app=weko-web -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n weko3 $POD -c web -- bash -s < scratchpad/weko-init.sh
# Contents: invenio db init/create → stats/logging partition → index init/queue init
#           → make ES ILM/stats indices → files location → grant users/roles/access
```
> ⚠️ **Because of emulation, each `invenio` command takes 30–60 seconds.** The whole setup takes about 30–40 minutes.

### 8.4 Known pitfalls and workarounds (really seen)

| Symptom | Cause | Workaround |
|---|---|---|
| `index init` fails with `IOException ... kui.txt` | ES has no `kui.txt` | Mount the `es-kui` ConfigMap into the config (8.1) |
| Top page returns **HTTP 500** (`None + int` in `_adjust_shib_admin_DB`) | `max(id)+1` fails on an empty `admin_settings` (because `demo init` was skipped) | Add one seed row to `admin_settings`:<br>`INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb);` then restart web |
| First request times out | `before_first_request` + JIT are slow under emulation | Use about `--max-time 240` on the first request. Later requests take seconds |

### 8.5 Access information

| Item | Value |
|---|---|
| URL | `http://localhost/` (Ingress host = `localhost`) |
| Administrator | `admin@example.org` / `adminpass123` |
| Namespace | `weko3` |
| DB | `wekodb` / user `weko` / pass `weko` |

Connectivity results (measured):
```
Top page /         → HTTP 200 (<title>WEKO3</title>)
/login/            → HTTP 200
/admin/            → HTTP 302 (not logged in → login)
/api/records/      → HTTP 200 (ES works)
/static/favicon.ico→ HTTP 200
```

---

## 8bis. Deployment plan for a 64GB memory environment

This setup runs in **about 5GiB measured — far below 64GB** (see below). Even so, here is a resource plan that stays
on the safe side for a 64GB machine.

### Measured memory (everything, exactly this setup)

| Node (kind container) | Role | Measured |
|---|---|---|
| `weko3-control-plane` | API server etc. + ingress | ~1.1 GiB |
| `weko3-worker` (WEKO) | weko-web (nginx+web+worker) | ~1.3 GiB |
| `weko3-worker2` (DATA) | ES + PG + Redis + RabbitMQ | ~2.5 GiB |
| **Total** | | **~5 GiB** |

### Resource plan for 64GB (the defaults in these manifests)

| Component | requests | limits | Tuning point |
|---|---|---|---|
| Elasticsearch | 1.5Gi | 2.5Gi | `ES_JAVA_OPTS=-Xms1g -Xmx1g` (heap 1g) |
| PostgreSQL | 256Mi | 1Gi | — |
| Redis | 128Mi | 512Mi | Standalone |
| RabbitMQ | 256Mi | 1Gi | — |
| weko web (uwsgi) | 700Mi | 2Gi | `uwsgi processes=2` |
| weko worker (celery) | 500Mi | 1.5Gi | `celery -c 1` (concurrency 1) |
| nginx | 64Mi | 256Mi | — |
| **Total limits** | — | **~8.8Gi** | Small next to 64GB |

### To make it even smaller (for example, sharing with other work / 16–32GB class)

- ES heap to `-Xms512m -Xmx512m`, limit 1.5Gi
- uwsgi `processes=1`, celery `-c 1`
- Drop to **2 nodes** (control-plane + 1 worker) and put both `nodeType` selectors on one node
- Single-node ES with `index.number_of_replicas=0` (yellow is fine by default on a single node)

> To do the opposite and **use plenty of memory (64GB+) for speed**: ES heap 2–4g, uwsgi `processes=4`, celery `-c 2–4`,
> and more `replicas` for weko-web (watch the sharing of static files/sessions).

---

## 10. Multi-tenancy and production-fidelity upgrades

These were added on top of the small single-tenant setup from §1–9 to **get closer to JAIRO Cloud production**.
For the real commands see [`README.en.md`](./README.en.md) (the multi-tenant configuration / production-fidelity upgrade sections).

### 10.1 Multi-tenancy (shared backends, split per tenant)
- `gen-tenant.sh` reads `tenants.txt` (NAME/DBNAME/HOST/admin/INIT/Redis DBs) and makes per-tenant
  ConfigMap/Secret/Deployment(web)/Service/Ingress into `generated/`.
- Split per tenant: **PostgreSQL DB name / ES index prefix / RabbitMQ vhost (`<name>/`) / Redis DB number / FQDN**.
- `provision-tenants.sh` makes the PG DB and RabbitMQ vhost; `weko-init.sh` (= same as `populate-instance.sh`) sets them up.
- Tested: `tenant1.localhost` / `tenant2.localhost` route to their own Pods and return 200.

### 10.2 Redis Sentinel (`41-redis-sentinel.yaml`, namespace `weko3re`)
- Redis **master + 2 replicas + 3 sentinels**. The service name matches the instance.cfg default `weko-sentinel-service.weko3re:26379`, master=`mymaster`.
- weko switched to `CACHE_TYPE='redissentinel'` (instance.cfg is patched with sed when web/worker start).
- Tenants are **split by DB number inside the shared Redis** (tenant1=0/1/2, tenant2=5/6/7, and they avoid the reserved `CRAWLER=3`/`GROUP_INFO=4`).
- Tested: the worker reaches `ready` via sentinel, master→replica replication works, `sentinel master mymaster` shows quorum=2.

### 10.3 Data persistence (PVC / kind `standard` StorageClass)
- PostgreSQL / Elasticsearch / RabbitMQ / Redis ×3 / MinIO all moved to PVCs (emptyDir removed).
- **PG data was kept**: `pg_dumpall` → redeploy the PVC version → restore (no re-setup). ES indices were remade after redeploy.
- Tested: after deleting and remaking the `postgresql-0` Pod, 188 tables and the admin user were still there.

### 10.4 S3 object storage (`40-minio.yaml`) + file Location
- **MinIO** (S3-compatible, PVC) + buckets `weko-backup`/`weko-content`/`weko-esbackup` + **per-tenant `weko-<tenant>`**.
- Connection info in each tenant Secret's `S3_*` (`http://minio:9000`, key=`wekominio`).
- **WEKO uploads go to the S3 (MinIO) Location** (`set-s3-location.sh`): UPDATE each tenant DB's `files_location` to `type='s3'` / `uri='s3://weko-<tenant>'` plus `access_key`/`secret_key`/`s3_endpoint_url`/`s3_send_file_directly=true`/`s3_default_block_size=5242880`/`s3_signature_version='s3v4'`. weko writes objects into the MinIO bucket with `invenio-s3`'s s3fs.
  - **The main pitfall**: `invenio-s3`'s `storage.py _get_fs` connects s3fs with the location's S3 info only when `location.type=='s3'`. If `type` stays `None`, it falls back to PyFilesystem2 and fails with `AWS_ACCESS_KEY_ID not set`. → Always set `type='s3'`. path-style and `signature_version=s3v4` are handled by invenio-s3.
  - `gen-tenant.sh` sets `instance.cfg`'s `S3_ACCCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_ENDPOINT_URL` (for both web and worker) to read from environment variables.
  - Tested (on the real arm64 machine): real objects at `s3://weko-tenant1/...` for tenant1 and `s3://weko-tenant2/...` for tenant2. The NFS share (RWX) holds only theme conf/data (not the uploaded files).
- Tested: `pg_dumpall` → backup into `weko-backup/postgres/` (a two-stage Job: an initContainer dumps, then mc uploads).

### 10.5 Implementation pitfalls (really seen)
| Symptom | Cause | Workaround |
|---|---|---|
| ES `index init` fails on `kui.txt` | The dictionary file is missing in ES | Mount the `es-kui` ConfigMap |
| Top page 500 in `_adjust_shib_admin_DB` | `max(id)+1` on an empty `admin_settings` | Add one seed row + restart web |
| `bash -s < file` / a pipe runs empty | `nohup`'s stdin is /dev/null | base64-encode the script and run `base64 -d \| bash` inside the pod |
| `pkill -f port-forward` exits 144 | The command line matches itself and kills itself | Do not use pkill patterns that match their own command string |
| S3 upload fails with `AWS_ACCESS_KEY_ID not set` | `files_location.type` is `None`, so invenio-s3 falls back to PyFilesystem2 | UPDATE `type='s3'` + the S3 info with `set-s3-location.sh` |
| The mc Job does not start | The mc image's entrypoint | Override with `command:["/bin/sh","-c"]` in the Job (`kubectl run -- sh -c` does not work) |
| First request is slow / times out | Emulation + JIT | Use `--max-time 240` on the first request; later ones take seconds |

### 10.6 Pitfalls found in the real-machine test (2026-07-23), and their fixes
| Symptom | Cause | Fix (already applied) |
|---|---|---|
| Applying `RabbitmqCluster` fails the webhook call | The CR is applied before the Cluster Operator's webhook is up | `deploy-*.sh` waits on the operator's `rollout status` and retries the CR apply |
| NFS mount of the static PVs fails with `access denied by server` | The dynamic provisioner (ganesha) only exports the volumes it made | The postStart hook in `60-nfs-server.yaml` adds a static export for all of `/export` over dbus |
| ganesha stops starting at all | Appending to `/export/vfs.conf` races with the provisioner remaking it and corrupts the file | The EXPORT block goes into a **separate file** (`/export/static-export.conf`) added with dbus `AddExport` |
| Template seeding fails without an error | The `nfs-provisioner` image has no `tar`, and busybox's `cp -an` copies nothing | Use a busybox helper Pod and **extract the tar straight into the destination** (`-k` = do not overwrite) |
| celery CrashLoops with `ACCESS_REFUSED` | RabbitMQ has no `weko` user (the operator only makes its own) | `provision-tenants.sh` runs `add_user` / `set_user_tags` / `set_permissions` |
| `shibauthorizer` / `shibresponder` do not start on arm64 | `supervisord.conf` hardcodes `/usr/lib/x86_64-linux-gnu/shibboleth/` | The nginx image build rewrites the path to `aarch64-linux-gnu` (`deploy-arm64.sh`) |
| Top page 500, `styles.scss` missing | Mounting an emptyDir at `static` hides the image's static files | A `seed-static` initContainer copies the static files from the image |
| nginx will not start: `unknown "shib_mail" variable` | Production's `weko.conf` (which sets the shib variables) and `nginx.conf` (whose log_format uses them) go together; turning off one breaks the other | By default use the image's own `/etc/nginx` set; seed the production template only when `WEKO_NGINX_SHIB=yes` |
| Node container cannot be deleted after `kind delete cluster` | The NFS server goes away while mounts are active, so they hang (D state) | Delete the Pods first, then the cluster; if it is wedged, `docker rm -f` as root |

---

## 9. Operational command quick reference

```bash
# list / delete clusters
kind get clusters
kind delete cluster --name weko3

# context
kubectl config current-context          # kind-weko3
kubectl config use-context kind-weko3

# status
kubectl get nodes -o wide
kubectl get pods -A

# enter a node (kind nodes are docker containers)
docker exec -it weko3-control-plane bash
```

---

## Appendix: summary of the built state

| Component | State |
|---|---|
| kind cluster `weko3` | ✅ Running (context: `kind-weko3`) |
| Nodes | ✅ 1 control-plane + 2 workers (`nodeType=WEKO`/`DATA`) |
| Control plane (API server etc.) | ✅ All Running |
| ingress-nginx | ✅ Running (host 80/443) |
| amd64 emulation | ✅ On (checked in-cluster: `uname -m` → `x86_64`) |
| PostgreSQL | ✅ **Patroni 3-node HA** (Zalando operator, arm64 spilo-17, master + 2 replicas) |
| RabbitMQ | ✅ **3-node cluster** (Cluster Operator, rabbitmq:4.0.9) |
| Elasticsearch | ✅ **3-node cluster** (**arm64 native**, real kui.txt/kuromoji/repository-s3, green, shards spread out) |
| Redis | ✅ Sentinel HA (`weko3re`: master + 2 replicas + 3 sentinels) |
| MinIO (S3) | ✅ Running (3 buckets + per-tenant `weko-<tenant>`, pg_dumpall backup shown) |
| File Location | ✅ **S3 (MinIO)** (`files_location.type='s3'`, `uri=s3://weko-<tenant>`). Uploads checked into MinIO for both tenants |
| weko application | ✅ **arm64 native** (`weko3-web:arm64`). 5-second startup, no qemu trouble, 3/3 on both tenants |
| Multi-tenancy | ✅ tenant1 / tenant2 run on their own |
| Site connectivity | ✅ Both tenants: `/` 200, `/login/` 200, `/admin/` 302, `/api/records/` 200 (**stable at 200×15/15**) |
| 　　Administrators | tenant1: `admin@example.org`/`adminpass123`, tenant2: `admin@tenant2.local`/`adminpass2` |
| Data persistence | ✅ 15 PVCs. Data kept across Pod restarts (checked) |
| Measured memory | ✅ ~18 GiB overall (fits in 64GB) |
