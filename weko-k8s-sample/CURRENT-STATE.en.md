# weko3 on kind — Current State (snapshot)

- Recorded: 2026-07-21 (**re-checked on 2026-07-23 with a full end-to-end deploy on the real arm64 machine**: built from nothing with `deploy-arm64.sh`, all checks passed)
- Cluster: kind `weko3` (context `kind-weko3`) / Host: **arm64** single server (20 cores / 121GB RAM)
- Overall status: **two tenants run stably on a production-like HA cluster** (all endpoints 200/302)

Connectivity (measured):
```
tenant1.localhost : / 200  /login 200  /admin 302  /api/records 200
tenant2.localhost : / 200  /login 200  /admin 302  /api/records 200
Host memory usage: 18GiB / 121GiB
```

---

## 1. Overall architecture

```
kind cluster "weko3" (3 containers = nodes on one physical host)
├ weko3-control-plane           : API server etc. + ingress-nginx (host 80/443)
├ weko3-worker  (nodeType=WEKO) : tenant1-web / tenant2-web
└ weko3-worker2 (nodeType=DATA) : ES / RabbitMQ / MinIO / part of PG / NFS / Redis (weko3re)

App: weko3-web:arm64 (native) = nginx + web(uwsgi) + worker(celery) per tenant
Shared backends (HA clusters):
  PostgreSQL : Zalando postgres-operator + Patroni 3 nodes (spilo-17 = PG17, synchronous replication)
  RabbitMQ   : RabbitMQ Cluster Operator + 3 nodes (rabbitmq:4.0.9)
  Elasticsearch : 3-node cluster (arm64-native 6.8.23, kuromoji / kui.txt / repository-s3)
  Redis      : Sentinel HA (master + 2 replicas + 3 sentinels) @ namespace weko3re
  MinIO(S3)  : weko-backup / weko-content / weko-esbackup + per-tenant weko-<tenant> (the real file Location)
Shared FS (NFS/RWX): nfs-ganesha → per-tenant conf (/fs-config) / data (/fs-data)
```

---

## 2. Pod list and node placement

| Type | Pod | Node | State |
|---|---|---|---|
| tenant1 web | `tenant1-web-*` (nginx/web/worker) | weko3-worker | 3/3 Running |
| tenant2 web | `tenant2-web-*` (nginx/web/worker) | weko3-worker | 3/3 Running |
| PostgreSQL | `weko-postgresql-0` (master) | weko3-worker | Running |
| ″ | `weko-postgresql-1` (replica) | weko3-worker2 | Running |
| ″ | `weko-postgresql-2` (replica) | weko3-worker | Running |
| RabbitMQ | `weko-rabbitmq-server-0/1/2` | **all on weko3-worker2** | 3/3 Running |
| Elasticsearch | `elasticsearch-0/1/2` | **all on weko3-worker2** | 3/3 Running |
| Redis (weko3re) | `redis-0/1/2` + `sentinel-*` ×3 | — | 6/6 Running |
| MinIO | `minio-*` | weko3-worker2 | Running |
| Operators | postgres-operator (default) / rabbitmq-cluster-operator / cert-manager ×3 / nfs-provisioner | — | Running |

> ⚠️ **All three ES and RabbitMQ nodes sit on weko3-worker2** (`nodeSelector: nodeType: DATA` matches only that one node).
> → If that node goes down, the whole cluster goes with it — a **single point of failure**. PG is spread over two nodes. See §5.

---

## 3. Images in use

| Purpose | Image | Type |
|---|---|---|
| weko app (web/worker) | `weko3-web:arm64` | **self-built arm64** (`/home/mhaya/weko/Dockerfile.arm64`) |
| Front nginx | `weko3-nginx:arm64` | **self-built arm64** (`/home/mhaya/weko/nginx/Dockerfile`; has the Shibboleth SP = shibd + nginx-http-shibboleth). Runs nginx alone by default; `WEKO_NGINX_SHIB=yes` switches to the production mode with shibd |
| Elasticsearch | `weko-elasticsearch:6.8.23-arm64` | **self-built arm64** (`/home/mhaya/weko/elasticsearch/Dockerfile.arm64`, real kui.txt) |
| PostgreSQL | `ghcr.io/zalando/spilo-17:4.0-p2` | arm64 (operator default) |
| RabbitMQ | `rabbitmq:4.0.9-management` | multi-arch |
| Redis/Sentinel | `redis:6.2` | multi-arch |
| MinIO | `minio/minio:RELEASE.2025-04-08...` | multi-arch |
| NFS server | `registry.k8s.io/sig-storage/nfs-provisioner:v4.0.8` | arm64 (ganesha) |

> Emulation is not used (weko/ES were made arm64-native, so no qemu).

---

## 4. Storage / persistence

| StorageClass | Provisioner | Access | Purpose |
|---|---|---|---|
| `standard` (default) | rancher.io/local-path | **RWO, node-local** | Backing store for PG/ES/RabbitMQ/Redis/MinIO/NFS export |
| `nfs` | weko.example.com/nfs (ganesha) | **RWX, network shared** | For dynamic provisioning (the current per-tenant FS uses static PVs on `nfs-static`) |
| `nfs-static` | none (static PVs) | **RWX, network shared** | Per-tenant `/fs-config`, `/fs-data`, `/fs-shibboleth`, `/fs-nginx` (same layout as production) |

PVC list:
```
[local-path / RWO]
 weko3: data-elasticsearch-0/1/2, pgdata-weko-postgresql-0/1/2,
        persistence-weko-rabbitmq-server-0/1/2, minio-data
 weko3re: data-redis-0/1/2
 nfs-system: nfs-export (the NFS server's backing volume, 30Gi)
 * data-postgresql-0 is left over from the old standalone PG (unused, safe to delete)
[NFS / RWX]
 weko3: tenant1-conf, tenant1-data, tenant1-shib, tenant2-conf, tenant2-data, tenant2-shib
```

NFS shared FS (same as production's config-pvc/data-pvc):
- `<tenant>-conf` → `.../var/instance/conf` (invenio.cfg / uwsgi.ini)
- `<tenant>-data` → `.../var/instance/data` (theme `_variables.scss` / indextree, etc.) * does not hold uploaded files
- `<tenant>-shib` → `/etc/shibboleth` in the nginx container (a static PV over `/fs-shibboleth/<tenant>` on NFS; seeded from shibboleth_template by `provision-nfs.sh`)
- `<tenant>-nginx-pvc` → `/etc/nginx` in the nginx container (`/fs-nginx/<tenant>` on NFS; seeded from nginx_template by `provision-nfs.sh`)
- **Uploads go to the S3 (MinIO) Location**: the DB `files_location` is set to `type='s3'` / `uri='s3://weko-<tenant>'` (`set-s3-location.sh`). weko writes objects into the MinIO bucket with `invenio-s3`'s s3fs.
  - How it works: `invenio-s3`'s `_get_fs` connects s3fs with the location's S3 info (access_key/secret_key/s3_endpoint_url) **only when** `location.type=='s3'`. If it stays None, it falls back to PyFilesystem2 and fails with `AWS_ACCESS_KEY_ID not set`.
  - path-style and `signature_version=s3v4` are handled by invenio-s3. `gen-tenant.sh` sets `instance.cfg`'s `S3_ACCCESS_KEY_ID` etc. to read from environment variables.
  - Tested: real objects at `s3://weko-tenant1/...` for tenant1 and `s3://weko-tenant2/...` for tenant2.

---

## 5. Persistence and what happens when Pods move between nodes ★important

**local-path volumes are pinned to one node** (the PV carries `nodeAffinity: kubernetes.io/hostname In [<node>]`).

| Situation | Data |
|---|---|
| Pod deleted → remade on the **same node** (normal restart) | ✅ **Kept** (tested: PG kept 188 tables) |
| Moved to **another node** because of a node failure, etc. | ❌ That Pod's local data does not move (it stays on the first node). The PV's nodeAffinity stops it from starting on another node → Pending |
| **Cluster-wide data** | ✅ **Protected by HA replication** (PG = Patroni synchronous replication / ES = shard replicas) |

Key points:
- **A single Pod's volume (PG/ES) cannot move** (local-path).
- But **HA cluster replication** keeps the data and the service alive on other nodes when a node/Pod is lost (this is exactly why clustering was added).
- The NFS (RWX) conf/data volumes have **no nodeAffinity = they can be mounted from any node** (so you can run more than one weko web replica and move Pods between nodes).

**To really get "Pods move + data moves with them"** (not possible with local-path):
- Network / shared block storage (NFS(RWX) / cloud block (OCI Block, EBS: detach → attach) / Ceph / Longhorn)
- Production OKE does this for PG with cloud block storage + replication

---

## 6. Access information

| Item | Value |
|---|---|
| URL | `http://tenant1.localhost/` , `http://tenant2.localhost/` (`*.localhost` → loopback; open directly on host port 80) |
| Administrator (tenant1) | `admin@example.org` / `adminpass123` |
| Administrator (tenant2) | `admin@tenant2.local` / `adminpass2` |
| DB | user `weko` / pass `weko` (PG endpoint `weko-postgresql`, or `pgpool` in the current setup) |
| MinIO | `wekominio` / `wekominio-secret-key` (endpoint `http://minio:9000`) |
| RabbitMQ | user `weko` / pass `weko` (endpoint `weko-rabbitmq`, vhost `<tenant>/`) |

Port forwarding (remote): `kubectl port-forward -n ingress-nginx --address 127.0.0.1,::1 svc/ingress-nginx-controller 8080:80` → `http://tenantN.localhost:8080/`

---

## 7. Known limits / not implemented

- **ES and RabbitMQ all sit on one node (weko3-worker2)** → no real node-failure tolerance (needs more nodes or anti-affinity to spread out).
- **local-path data is lost on `kind delete cluster`** (it survives Pod restarts). Full host persistence needs remaking kind with `extraMounts` (host dir) or an external NFS server.
- **kind on one physical host** (nodes = containers). You cannot really test node failures.
- **pgpool** (connection pool + read load-balancing, in front of the Patroni PG) is now added (`62-pgpool.yaml`; data path tested on arm64). Still not deployed (production-OKE only): pgbouncer, F5 App Protect (WAF), Shibboleth / GakuNin login, fluentd, Prometheus monitoring, per-tenant TLS certificates.
- The old `data-postgresql-0` PVC is left unused (safe to delete).

---

## 8. Manifests / scripts (`k8s-weko/`)

| File | Role |
|---|---|
| `00-namespace.yaml` | namespace weko3 |
| `10/11/12/13-*.yaml` | (10 old standalone PG = unused) / (11 old standalone Redis = unused) / old RabbitMQ / **ES 3 nodes (arm64, `-E` args)** |
| `40-minio.yaml` | MinIO (S3) |
| `41-redis-sentinel.yaml` | Redis Sentinel HA (weko3re) |
| `50-rabbitmq-cluster.yaml` | RabbitmqCluster (3 nodes) for the RabbitMQ Cluster Operator |
| `51-postgresql-ha.yaml` | Zalando postgresql CR (Patroni, 3 nodes) |
| `52-postgres-pod-config.yaml` | Pod env for the PG pods (`ALLOW_NOSSL=true`, so pgpool can connect over non-SSL) |
| `60-nfs-server.yaml` | nfs-ganesha server + `nfs` StorageClass (RWX) |
| `62-pgpool.yaml` | pgpool (connection pool + read load-balancing) in front of the Patroni PG |
| `21-nginx-config.yaml` | Front nginx config (uwsgi_pass) |
| `tenants.txt` + `gen-tenant.sh` | Tenant definitions → manifest generation (has redissentinel / NFS conf,data / app fixes / seed initContainer) |
| `provision-tenants.sh` | Makes the per-tenant PG DB / RabbitMQ vhost |
| `provision-nfs.sh` | Makes the per-tenant directories under `/fs-nginx`, `/fs-shibboleth`, `/fs-config`, `/fs-data` on the shared FS (NFS) and seeds the templates (= production's `make_volumes.sh`). **Run it before you apply**; it works through a busybox helper Pod |
| `weko-init.sh` / `es-reinit.sh` | DB setup / ES index setup |
| `set-s3-location.sh` | Makes the per-tenant MinIO bucket `weko-<tenant>` + sets `files_location` to the S3 type (run after setup) |
| `deploy-arm64.sh` | **Builds the current full setup (final form) from nothing in one pass** (1) cluster … 9) connectivity. README Appendix D). The amd64 version is `../k8s-weko-amd64/deploy-amd64.sh` |
| `../build-push-weko.sh` | Builds the WEKO image from the weko source → pushes to Docker Hub (native/multiarch/manifest). Swap images with the `WEKO_IMAGE` environment variable |

> **The WEKO image**: `deploy-*.sh` **gets the newest source (RCOSDP/weko) and builds it**, using `WEKO_IMAGE` (default arm64=`weko3-web:arm64`, amd64=`weko3-web:amd64`) in all three places (web/worker/seed) at once. A prebuilt image is pulled (and the build skipped) only when you set `WEKO_IMAGE=<repo>:<tag>`. Publish to Docker Hub with `build-push-weko.sh`.

| `Dockerfile.es` | (legacy) for building the amd64 ES |
| Separately | cert-manager / postgres-operator (pgop-*.yaml) / rabbitmq cluster-operator are already installed |

Related documents: `README.en.md` (runbook) / `CONSTRUCTION.en.md` (details) / `JAIRO-CLOUD-ARCHITECTURE.en.md` (production comparison) / `COMPARE-weko-workshop.en.md`.

---

## 9. Operational commands

```bash
kubectl get pods -A                                  # overall state
kubectl exec -n weko3 weko-postgresql-0 -- patronictl list   # PG HA status
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cluster/health   # ES status
kubectl exec -n weko3 weko-rabbitmq-server-0 -c rabbitmq -- rabbitmq-diagnostics cluster_status
kind delete cluster --name weko3                     # delete everything (data is lost too)
```

---

## 10. Capacity planning (number of tenants × items per tenant)

The backends (PG/ES/RabbitMQ/MinIO/Redis) are **shared by all tenants**, while weko web and the DB/index/vhost/PVC
resources are **per tenant**. So estimate as "**T tenants × N items per tenant (total = T×N)**".

### Variables
| Symbol | Meaning | Typical value |
|---|---|---|
| `T` | Number of tenants | — |
| `N` | Items per tenant | — |
| `m` | Metadata size per item | 10–50KB in weko |
| `f` | File size per item (file count × average size) | 0 to tens of MB |

### (A) "Fixed cost" that grows with tenant count T (per tenant)
| Resource | Per tenant |
|---|---|
| weko web Pod (nginx+web+worker) | measured **~1.5–2GiB** (limits total 3.75Gi) |
| PostgreSQL DB / RabbitMQ vhost / ES index / NFS conf+data PVC | one each (light; many are fine) |
| Redis DB | **3 per tenant** (cache/session/celery) |

→ **Memory is roughly "shared backends ~10–12GiB + T × ~2GiB (web) + ES heap".**

### (B) "Capacity" that grows with total items T×N
| Layer | Rough formula |
|---|---|
| PostgreSQL (metadata) | `T×N×m×3` (with indices/overhead) |
| Elasticsearch (search index, disk) | `T×N×m×(1+replicas)` |
| Files (NFS/S3) | `T×N×f×(1+backup)` |
| **ES heap (drives speed)** | Must cover the facet working set for total docs = `T×N`. Rule of thumb: **1g heap ≈ tens of thousands of docs** |
| **Total disk** | Sum of the three layers above + 30% headroom (run below 70%) |
| **Total memory** | `shared ~12GiB + T×2GiB + ES_heap` |

### (C) What caps the tenant count T
| Factor | Limit | Workaround |
|---|---|---|
| **Shared Redis Sentinel** | `databases` (default 16 → **now set to 512**) / 3 per tenant; without the reserved DBs (3=crawler, 4=group_info) that gives **~170 tenants**. You can raise the DB count more. **The real limit is Redis memory** (cache/session data; current limit 384Mi) | Raise `databases` / raise the Redis memory limit / use per-tenant Redis |
| **web Pod memory** | `T×~2GiB` | With 64GB, T=10 is only ~20GiB. Add nodes/RAM |
| PostgreSQL DB count / RabbitMQ vhosts / NFS PVCs | Hundreds to thousands are fine | Not a real limit |

> The Redis DB count is set by `databases` in `redis.conf` (a startup setting). The default of 16 is low, but this setup
> already uses **512** (checked with `redis-cli -n 500 set ...`). An empty DB costs only a few bytes, so 512–1024 barely
> adds memory. **The real tenant limit is Redis memory, not DB count** (the sum of all tenants' cache/session data).

### Planning examples (this host: 121GB RAM / 916GB disk)
**Example 1: T=4 tenants × N=50,000 items, m=30KB, f=2MB (total 200,000)**
- Disk: metadata `200k×30KB×3≈18GB` + ES `200k×30KB×2≈12GB` + files `200k×2MB≈400GB` → **~430GB** (fits in 916GB)
- ES heap: 200k docs total → **heap 2–4g × 3** is good
- Memory: shared ~12GiB + web `4×2=8GiB` + ES heap `4×3=12GiB` → **~32GiB** (fits in 64GB)
- 4 tenants → plenty of room in the shared Redis (databases 512 allows ~170 tenants)

**Example 2: T=1 tenant × N=? upper bound (heap still at 1g)**
| Profile | Rough N | Limit |
|---|---|---|
| Metadata only | **~tens of thousands to 100k** | ES heap 1g |
| Average file 1MB | **~300k** | Disk |
| Average file 5MB | **~70k** | Disk |
| Average file 50MB | **~7k** | Disk |

### Ways to scale up
1. **Raise the ES heap** (`ES_JAVA_OPTS -Xmx` 2–4g, within 50% of node RAM, max ~30g). If needed, raise the primary shard count for the item index and reindex, and add ES nodes → total docs into the hundreds of thousands to 1M.
2. **Files already use the S3 (MinIO) Location** (`files_location.type='s3'`) → file capacity depends on the MinIO PVC, and pointing the endpoint at an external S3 makes it almost unlimited.
3. **Add disk** / **use per-tenant Redis if the tenant count grows too large**.
4. PostgreSQL metadata is light (tens of GB even at 1M records), so it is almost never the bottleneck.

### Guidelines (summary)
1. Compute **total items = T×N**.
2. **Disk** = `T×N×(m×5 + f×1.x)` + 30% headroom → compare against free space on the host.
3. Size the **ES heap** for the total T×N (1g ≈ tens of thousands of docs; raise it if too small).
4. **Memory** = `12 + T×2 + ES_heap` (GiB) → compare against server RAM.
5. Redis holds **~170 tenants** with `databases` (now 512). Beyond that, raise `databases` or add Redis memory (memory is the real limit).
→ The current setup (heap 1g, **files on the S3 (MinIO) Location**) is sized for "a few tenants × tens of thousands of items".
**Raising the heap and growing MinIO / moving to external S3** scales the same architecture to production scale: "many tenants × hundreds of thousands of items".

---

## 11. Backup / restore

**Backing up "only the node storage locations" is wrong.** Sort backups by **which data is the source of truth**, and take
**logical backups of databases, not raw PVC files**.

### What to back up
| Component | Type | Backup | Method |
|---|---|---|---|
| **PostgreSQL** | **Source of truth** (metadata / records / users / roles / workflows) | ✅ **Required** | `pg_dumpall` (logical) → S3. Or Patroni + WAL-G for continuous archiving |
| **Content files** (S3 (MinIO) bucket `weko-<tenant>`) | **Source of truth** (uploaded files, cannot be remade) | ✅ **Required** | Copy to external S3 / offsite with `mc mirror` or rclone |
| Elasticsearch (item search index) | **Derived** (can be rebuilt from PG by reindexing) | △ Optional | ES snapshot → S3 if you want fast recovery |
| ES stats/events indices (usage statistics) | Almost source-of-truth (only in ES) | ○ Recommended | ES snapshot (repository-s3 → MinIO) |
| RabbitMQ (queues/messages) | **Transient** (celery tasks) | ✕ Not needed | vhosts/users are remade by provisioning |
| Redis (cache/session) | **Transient** | ✕ Not needed | Losing it just means re-login / re-caching |
| Manifests / scripts / `SECRET_KEY`, etc. | **Configuration (code)** | ✅ **Keep in git** | Version-control it so you can reproduce the same values during recovery |

### Principles
1. **Do not copy raw PVC files directly** (a running DB gives an inconsistent copy). Always take **logical/consistent backups**: `pg_dump`, ES snapshots, file copies.
2. **Always store backups outside the cluster.** local-path data disappears on `kind delete cluster`, so keeping backups inside a node is pointless → **S3 (MinIO) / external storage / offsite**.
3. If you copy **the two sources of truth** (① the PostgreSQL dump ② the content files) to an outside place, you can recover. ES/RabbitMQ/Redis can be rebuilt from them.

### What this setup already gives you
- **MinIO** buckets: `weko-backup` (DB dumps) / `weko-content` (files) / `weko-esbackup` (ES snapshots)
- A working **pg_dumpall → MinIO** backup Job (initContainer=postgres dumps, then mc uploads)
- **ES ships with the repository-s3 plugin** (snapshots can go to MinIO)
- Production (weko-k8s) does the same: `pgdump` / `essnapshooter` / `contents-backup (rclone)` → **object storage** (node storage is never backed up directly)

### Recommended operations (three pillars)
1. **PG**: regular `pg_dumpall` (all tenant DBs) → MinIO / external S3 (daily + keep generations)
2. **Files**: sync the S3 (MinIO) bucket `weko-<tenant>` to external S3 / offsite with `mc mirror` or rclone
3. **Config**: keep the manifest set (`gen-tenant.sh` / `tenants.txt` / secret keys) in git

> Full DR steps (whole cluster lost → rebuild): ① rebuild kind and deploy the backends → ② restore each tenant DB from its dump → ③ restore files from S3 / the copy target → ④ rebuild ES with `invenio index reindex` (restore the stats indices from snapshots).
