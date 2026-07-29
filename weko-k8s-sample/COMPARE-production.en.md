# Differences between the kind verification environment and the JAIRO Cloud production environment

A layer-by-layer comparison of `weko-k8s-sample` (the verification environment on kind) against the
**JAIRO Cloud production environment**
([`RCOSDP/weko-k8s`](https://github.com/RCOSDP/weko-k8s), local checkout: `~/weko-k8s`).
This is a reference document for answering "what is the same, what is different, and why".

For the order in which to resolve these differences, see
[PRODUCTION-ROADMAP.en.md](PRODUCTION-ROADMAP.en.md).
Japanese version: [COMPARE-production.md](COMPARE-production.md)

---

## Legend

Every entry is classified into one of four kinds. **This classification is the point of the document.**

| Mark | Class | Meaning | When building production |
|---|---|---|---|
| ✅ | **Match** | The same thing as production | no change needed |
| 🔵 | **Simplified** | Deliberately simplified because verification does not need it | restore the production form |
| 🟡 | **Stand-in** | Substituted because of a kind limitation | **must be replaced** — leaving it in means it will not start, or will fail silently |
| 🔴 | **Absent** | Exists in production, missing from the sample | build it new |

🟡 is the dangerous class: it looks like it works, but it does not transfer to production.

---

## 0. What is being compared

| | kind verification environment | JAIRO Cloud production |
|---|---|---|
| Repository | `weko-workshop/weko-k8s-sample` | `RCOSDP/weko-k8s` |
| Directory | `k8s-weko-amd64` (amd64) / `k8s-weko` (arm64) | `deploy/` + `scripts/` |
| Configuration management | plain manifests + one imperative script | kustomize `base` / `components` / `overlay` |
| Number of environments | 1 (kind) | 6 (`oci-af` `oci-ams` `oci-at` `oci-it` `oci-pr` `oci-st`) |
| Intended scale | one server, 1–8 tenants | many production repositories |
| "Production" in this doc | — | the `oci-pr` overlay values unless stated otherwise |

---

## 1. Cluster platform layer

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| Platform | kind (Docker in Docker) | OCI **OKE** (managed Kubernetes) | 🟡 |
| Cluster creation | `deploy-amd64.sh:96-119` (`kind create cluster`, 3 retries) | OCI CLI / Terraform, `scripts/maintenance/upgrade_oke_*.sh` | 🟡 |
| Kubernetes version | **v1.34** (`kindest/node:v1.34.0`, `prereq-amd64.sh:39-42`) | **v1.32.1** (`K8S_VERSION` in `scripts/maintenance/oke_param_env.sh`) | 🟡 verification is *newer* |
| kind version | v0.30.0 (`prereq-amd64.sh:9`) | — | 🟡 |
| Node layout | 1 control-plane + 2 workers (`kind-weko-cluster.yaml`) | OKE node pools, shape `VM.Standard.E4.Flex` | 🟡 |
| Node type labels | **2**: `nodeType=WEKO` / `DATA` | **8**: `WEKO` `PGO` `PGPOOL` `ES` `RA` `RE` `SE` `LOG` (`scripts/k8s_command.sh:29-44`) | 🔵 |
| How placement is expressed | `nodeSelector` inline in the Pod spec (7 places) | `nodeAffinity` injected by a kustomize component (`elasticsearch/components/oci/elasticsearch_patch.yaml:10-20`) | 🔵 |
| CNI | kindnet (kind default) | the OKE CNI | 🟡 |
| Host preparation | `prereq-amd64.sh` (docker / kubectl / kind / sysctl) | absorbed by the node image and shape | 🟡 |
| `vm.max_map_count` sysctl | on the host (`prereq-amd64.sh:56-62`) **plus a privileged initContainer** (`13-elasticsearch.yaml:46-49`) | node side only (**no** initContainer) | 🟡 |
| metrics-server | **installed** (v0.9.0, `deploy-amd64.sh:266-269`). kind's kubelet serves a certificate the cluster CA did not sign, so `--kubelet-insecure-tls` is patched in afterwards | `deploy/metrics-server/` | ✅ **match** (only the startup flag differs) |

> **Why 🟡 matters here**: the design leans on `kind create cluster` and `extraPortMappings`, so the
> whole cluster-creation step is simply **unnecessary** in production. Note also that the Kubernetes
> version is inverted — verification (1.34) is ahead of production (1.32) — so an API that works in
> the sample may not exist in production.

---

## 2. Image supply layer

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| Where images come from | local `docker build` (WEKO / ES / nginx, `deploy-amd64.sh:126-163`) | built in CI, pushed to **OCIR** |🟡 |
| How they reach the nodes | **`kind load docker-image`** (4 calls, `deploy-amd64.sh:131,149,163,168`) | kubelet pulls from the registry | 🟡 |
| `imagePullPolicy` | **`Never`** (9 places: `13-elasticsearch.yaml:53`, `62-pgpool.yaml:80`, `gen-tenant.sh` ×7) | `Always` (`deploy-web.yaml:44,74,90`) | 🟡 |
| `imagePullSecrets` | none | `ocir-secret` on every Pod (`deploy-web.yaml:113-114`) | 🟡 |
| How image names are managed | inline shell variables (`WEKO_IMAGE` etc.) | kustomize `images:` per overlay (`postgresql/overlay/oci-pr/kustomization.yaml:19-30`) | 🔵 |
| WEKO itself | **rebuilt from source every run** (`WEKO_SRC` cloned/pulled) | a prebuilt image pulled by tag | 🔵 |

> **Why 🟡 matters here**: `kind load` plus `imagePullPolicy: Never` is a stand-in for not having a
> registry. On a multi-node production cluster the kubelet cannot pull, and **every Pod ends up in
> ImagePullBackOff**.

---

## 3. Storage layer

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| Block StorageClass | **`standard`** (kind's bundled local-path, **node-local**), 6 usages | **`oci-bv`** (OCI Block Volume), `elasticsearch/components/oci/elasticsearch_patch.yaml:24` | 🟡 |
| What the shared FS is | **an in-cluster nfs-ganesha Pod** (`60-nfs-server.yaml`) | **external NFS** (OCI File Storage) | 🟡 |
| How the NFS server is addressed | **hardcoded** `clusterIP: 10.96.0.99` (`60-nfs-server.yaml:61`); same default for `NFS_SERVER` (`gen-tenant.sh:19`) | `nfs.server: 10.76.0.12` (`weko/manifest_template/volume-pv.yaml:17,36,70,88`) | 🟡 |
| Shared FS accessModes | **ReadWriteMany** (`gen-tenant.sh:163,184,207,231`) | **ReadWriteOnce** (`volume-pv.yaml:11,30,64,82`) | 🔵 |
| Shared FS capacity | config 1Gi / data 5Gi / shib 1Gi / nginx 1Gi | **50Gi each** | 🔵 |
| Static PV StorageClass name | `nfs-static` (`no-provisioner`) | `nfs` | 🔵 |
| PV reclaimPolicy | `Retain` | `Retain` | ✅ |
| Shared FS directory layout | `/fs-nginx` `/fs-shibboleth` `/fs-config` `/fs-data` | identical | ✅ |
| Shared FS availability | `replicas: 1` + `Recreate` = **SPOF** | managed, redundant NFS | 🟡 |
| NFS Pod privileges | `capabilities: [DAC_READ_SEARCH, SYS_ADMIN]` (`60-nfs-server.yaml:117-119`) | not needed | 🟡 |
| How directories are created | via a busybox seed Pod (`provision-nfs.sh:38-60`) | `mkdir` straight from the host (`scripts/make_volumes.sh`) | 🔵 |
| Object storage | **MinIO** (`40-minio.yaml`, `replicas: 1`, 600Gi RWO) | **OCI Object Storage** (S3-compatible, outside the cluster) | 🟡 |

> **Why 🟡 matters here**: the shared filesystem is the single largest difference.
> `60-nfs-server.yaml` exists to emulate the production OKE File Storage inside the cluster, and on
> any production cluster whose Service CIDR is not `10.96.0.0/16` it **fails to create at all**.

---

## 4. Network and external exposure layer

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| Ingress controller | **ingress-nginx OSS** v1.12.1, the `provider/kind` manifest (`deploy-amd64.sh:120`) | **NGINX Plus IC** (commercial) + **App Protect**, `ingress/base/deployment/nginx-plus-ingress.yaml`, image `nginx-plus-ingress-nap:5.3.4-SNAPSHOT` | 🟡 |
| Ingress controller redundancy | 1 (provider/kind default) | **replicas: 2** (`ingress/overlay/oci-pr/kustomization.yaml`) | 🔵 |
| Exposure method | kind **`extraPortMappings`** borrowing host 80/443 (`kind-weko-cluster.yaml:15-21`) | **`type: LoadBalancer`** + `loadBalancerIP: 158.101.66.16` + `externalTrafficPolicy: Local` (`ingress/base/nginx-plus-lb.yaml`) | 🟡 |
| WAF | **none** | App Protect policies (`ingress/components/ap-config/`) + `scripts/waf_management/` | 🔴 |
| Hostnames | `tenant1.localhost` (`tenants.txt:7`) | real FQDNs (`*.repo.nii.ac.jp` etc.) | 🟡 |
| Internal ingress | none | `deploy/ingress-nginx-internal/` | 🔴 |
| ingressClassName | `nginx` | `nginx` | ✅ |
| Ingress annotations | `proxy-body-size: "0"`, `proxy-read-timeout: "3600"` (`gen-tenant.sh:430-431`) | `rewrite-target`, `backend-protocol: HTTPS`, `ssl-services`, the `appprotect.f5.com/*` set (`weko/manifest_template/ingress.yaml`) | 🔵 |

### 4-1. TLS topology — the number of hops differs

**Verification is one hop; production is two.**

| | kind verification environment | Production |
|---|---|---|
| Hop 1 terminated by | the Ingress (ingress-nginx) | **NGINX Plus IC** (App Protect inspects here too) |
| Hop 1 certificate | issued automatically by cert-manager from a self-signed root CA (`61-tls-ca.yaml`) | a **real certificate**: per-tenant Secret `<domain>-cert`, loaded by `scripts/deploy_weko.sh:64-66`. The `openssl req -x509` call in `make_weko_manifests.sh` only writes a placeholder, which is replaced with the real certificate during rollout |
| Hop 2 | **none** — plaintext HTTP:80 to the backend | **present**: re-encrypted via `backend-protocol: "HTTPS"` + `nginx.org/ssl-services`, backend Service port 443 |
| Hop 2 terminated by | — | the tenant's nginx container (`weko.conf:11` `listen 443`) |
| Hop 2 certificate | — | `weko/nginx_template/server.crt` / `server.key` (`weko.conf:14-15`): **self-signed** (`CN=*`, `O=Internet Widgits Pty Ltd`), **expired 2017-01-21**, and **shared by every tenant** because `make_volumes.sh:43` copies the same file everywhere |
| Hop 2 verification | — | **none** (no `proxy_ssl_verify` equivalent configured) |

Classification: the hop-1 certificate scheme is 🟡 (self-signed CA → real certificate); the existence
of hop 2 at all is 🔴 (absent from the sample).

> Production's hop 2 exists to keep the path behind the WAF from being plaintext; it does not
> authenticate the peer by certificate. Migration requires an explicit decision: **inherit this
> design, or give the internal hop a valid certificate and enable verification.**

---

## 5. Middleware layer

### 5-1. Version alignment

| Middleware | kind verification environment | Production | Class |
|---|---|---|---|
| PostgreSQL | **17** (`51-postgresql-ha.yaml:16`), spilo `ghcr.io/zalando/spilo-17:4.0-p2` (`deploy-amd64.sh:53`) | **12** (`postgresql/base/postgresql.yaml:15`), spilo `spilo-13:2.0-p6` (`postgres-operator-config.yaml:16`) | 🟡 **five majors apart** |
| postgres-operator | v1.14.0 (`deploy-amd64.sh:54,177`) | v1.13.0 (`postgres-operator.yaml:23`) | 🔵 |
| pgpool | `pgpool/pgpool:4.2.2` | `pgpool/pgpool:4.2.2` | ✅ **exact match** |
| Elasticsearch | `weko-elasticsearch:6.8.23` (built from the weko source) | `weko_elasticsearch:v6.8.23` (OCIR) | ✅ **same version**, only the sourcing differs |
| RabbitMQ | `rabbitmq:4.0.9-management` | `rabbitmq:4.0.9` | ✅ **same version** |
| RabbitMQ operator | cluster-operator **latest** (`deploy-amd64.sh:173`) | cluster-operator (pinned) | 🔵 not pinning is the difference |
| Redis | `redis:6.2` (upstream image) | `weko_redis:v1.0` / `weko_sentinel:v1.0` (custom images) | 🔵 |
| cert-manager | v1.16.2 (`deploy-amd64.sh:171`) | **not used** | 🟡 |
| MinIO | `minio/minio:RELEASE.2025-04-08…` | **not used** (OCI Object Storage) | 🟡 |

> **⚠️ Note the discrepancy**: the comment at `51-postgresql-ha.yaml:5` says production is **PG13**
> and to pin `spilo-13` to match, but the current production IaC declares `version: "12"` in the CR
> (Spilo images bundle several majors, so PG12 runs on the `spilo-13` image). **The sample's comment
> does not match the current production IaC** — verify the actual version on the production system if
> data migration is involved.

### 5-2. Replica counts and sizing

| Component | kind verification environment | Production `base` | Production `oci-pr` | Class |
|---|---|---|---|---|
| PostgreSQL | 2 inst / 50Gi, shared_buffers 1GB / max_conn 200, req 500m-1Gi, lim 4-2560Mi | 1 inst / 10Gi, 500MB / 50 | **3 inst / 2500Gi**, 12000MB / **11500**, req **25cpu-32Gi**, lim **30cpu-60Gi** | 🔵 |
| pgpool | **1** (SPOF) | 1 | **3** | 🔵 |
| Elasticsearch | 2 | 1 | **13** | 🔵 |
| RabbitMQ | 3 | 1 / 2Gi | **3 / 50Gi**, req 6cpu-24Gi, lim 7cpu-30Gi | 🔵 |
| Redis | 3 + 3 Sentinel | Sentinel setup | **2 + 3 Sentinel** | 🔵 |
| MinIO | 1 / 600Gi (SPOF) | — | — | 🟡 |
| WEKO web | **1** per tenant | 1 | 1 (memory set per tenant in `repositories_file`) | ✅ |
| Ingress controller | 1 | — | 2 | 🔵 |

### 5-3. What actually makes the HA work

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| `PodDisruptionBudget` | **none** | **none** for the WEKO workloads (only what kube-prometheus-stack ships) | ✅ same situation |
| `podAntiAffinity` | **none** | **Redis only** (`redis/components/oci/redis_patch.yaml`) | 🔵 |
| `topologySpreadConstraints` | none | none | ✅ same situation |
| `NetworkPolicy` | **none** | **none** for the WEKO workloads | ✅ same situation |
| `HorizontalPodAutoscaler` | none | none (metrics-server is installed) | ✅ same situation |
| PostgreSQL synchronous replication | `synchronous_mode: true` | `synchronous_mode: true` | ✅ |
| `password_encryption` | `md5`, forced by pgpool 4.2.2 (`51-postgresql-ha.yaml:19-20`) | the same constraint (pgpool 4.2.2) | ✅ **the same technical debt** |

> **Important**: the absence of PDBs, NetworkPolicies and topology spread is not sloppiness in the
> sample — **production is in the same state**. Whether "as good as production" is acceptable, or
> whether production should improve too, is a separate decision.

### 5-4. Tuning values and timeouts

Sizing (CPU / memory / replica counts) is covered in 5-2. This section is about the
**differences that remain even after the sizing is matched**. 🔵 is "raise the number";
**🟡 means the value means something different**, so behaviour changes even at equal scale.

#### PostgreSQL (`postgresql.spec.postgresql.parameters`)

| Parameter | kind verification environment | Production `base` | Production `oci-pr` | Class |
|---|---|---|---|---|
| `wal_sender_timeout` | **unset** (default 60s) | **`0`** (disabled) | same | 🟡 |
| `wal_receiver_timeout` | **unset** (default 60s) | **`0`** (disabled) | same | 🟡 |
| `max_standby_streaming_delay` | **unset** (default 30s) | **`-1`** (unlimited) | same | 🟡 |
| `shared_buffers` | `1GB` | `500MB` | `12000MB` | 🔵 |
| `max_connections` | `200` | `50` | `11500` | 🔵 |
| `work_mem` | `16MB` | `8MB` | same | 🔵 |
| `temp_file_limit` | unset (unlimited) | `1000000` (≈1GB) | same | 🟡 |
| `wal_keep_segments` / `wal_buffers` / `max_wal_senders` | unset | `8` / `16MB` / `10` | same | 🔵 |
| `max_wal_size` | unset (default 1GB) | `1GB` | `4GB` | 🔵 |
| `max_worker_processes` / `max_parallel_workers` / `_per_gather` | unset | `2` / `2` / `2` | `14` / `8` / `8` | 🔵 |
| `log_statement` and friends | unset (spilo defaults) | all `off` / `none` | same | 🔵 |
| `password_encryption` | `md5` | same, forced by pgpool 4.2.2 | same | ✅ |

> **The heart of the 🟡**: production **disables the replication timeouts across the board**
> (`wal_sender_timeout=0` / `wal_receiver_timeout=0` / `max_standby_streaming_delay=-1`) so that a
> bulk initial sync or a long-running query does not get the replica torn off. **The sample leaves
> the defaults in place**, so disconnects can happen in production that never happen in the sample,
> and vice versa. `temp_file_limit` is the same story: production kills a runaway query at 1GB,
> the sample lets it run.

#### pgpool (a ConfigMap of `PGPOOL_PARAMS_*`)

| Parameter | kind verification environment | Production | Class |
|---|---|---|---|
| `NUM_INIT_CHILDREN` / `MAX_POOL` | `32` / `4` | `32` / `4` | ✅ |
| `CHILD_LIFE_TIME` / `CHILD_MAX_CONNECTIONS` | `300` / `0` | `300` / `0` | ✅ |
| `CONNECTION_LIFE_TIME` | `0` (never expires) | `0` | ✅ |
| `CLIENT_IDLE_LIMIT` | `900` (disconnect after 15 min) | `900` | ✅ |
| `CONNECTION_CACHE` / `LOAD_BALANCE_MODE` | `on` / `on` | `on` / `on` | ✅ |
| `SR_CHECK_PERIOD` | `0` (streaming replication check off) | `0` | ✅ |
| `BACKEND_FLAG0` | `ALWAYS_PRIMARY\|DISALLOW_TO_FAILOVER` | same | ✅ |
| `FAILOVER_ON_BACKEND_ERROR` | `off` | `off` | ✅ |
| `ENABLE_POOL_HBA` | `on` | `on` | ✅ |
| Backend host names | `weko-postgresql` / `weko-postgresql-repl` | same names, in the `weko3pg` namespace | 🔵 |
| `RELCACHE_SIZE` / `DEBUG_LEVEL` | `256` / `0` | unset (defaults) | 🔵 |

> **pgpool is essentially an exact match.** There is no meaningful connection-pool tuning
> difference; only the replica count (1 → 3) and the backend namespace need changing.

#### Elasticsearch (`elasticsearch-configmap`)

| Setting | kind verification environment | Production `base` | Production `oci-pr` | Class |
|---|---|---|---|---|
| `ES_JAVA_OPTS` heap | `-Xms2g -Xmx2g` | `-Xms1g -Xmx1g` | **`-Xms30g -Xmx30g`** | 🔵 |
| Young generation size | **unset** (JVM default) | `-XX:NewSize=300m -XX:MaxNewSize=300m` | `-XX:NewSize=16g -XX:MaxNewSize=16g` | 🟡 |
| `-Dlog4j2.formatMsgNoLookups=true` | **absent** | **present** | present | 🟡 **Log4Shell mitigation** |
| `discovery.zen.minimum_master_nodes` | `2` (2 nodes) | `1` | `7` (13 nodes) | 🔵 |
| `discovery.zen.ping.unicast.hosts` | one Service name | one entry | **13 entries listed** | 🔵 |
| `cluster.name` | default | `k8s-cluster` | same | 🔵 |

> **The heart of the 🟡**: ES 6.8.23 bundles Log4j 2.x, and production **always sets
> `-Dlog4j2.formatMsgNoLookups=true`** — the sample does not. The verification environment is never
> exposed, so there is no real risk there, but **it is mandatory when moving to production spec**.
> Pinning the young generation size is likewise a deliberate production tuning (steadier GC
> behaviour) that the sample lacks.

#### RabbitMQ (`RabbitmqCluster.spec.rabbitmq.additionalConfig`)

| Setting | kind verification environment | Production | Class |
|---|---|---|---|
| `consumer_timeout` | **unset** (default **30 minutes**) | **`10800000`** (3 hours) | 🟡 **most important** |
| `log.console.level` | `warning` | unset (default `info`) | 🔵 |
| startupProbe | **replaced** — the latest operator probes a `reached-target-cluster-size` API that does not exist in 4.0.9 (404), so a `rabbitmq-diagnostics` based probe is used instead | left at the operator default, since the operator version is pinned | 🟡 |

> **The heart of the 🟡 (this one bites)**: since RabbitMQ 3.8.15, **a message left unacked past
> `consumer_timeout` (30 minutes by default) tears down the whole channel**. Some WEKO Celery tasks
> — indexing, bulk updates — run longer than that, which is why production extends it to **3 hours**.
> **The sample does not set it**, so with large data you get a `PreconditionFailed - consumer ack
> timed out` in production that never reproduces in the sample. Matching production is a one-line
> change: add `consumer_timeout = 10800000` to `additionalConfig` in `50-rabbitmq-cluster.yaml`.

#### Redis / Sentinel

| Setting | kind verification environment | Production `base` | Production `oci-pr` | Class |
|---|---|---|---|---|
| Persistence | **`appendonly yes`** (AOF) | **RDB only** (`save 3600 1` / `300 100` / `60 10000`) | same | 🟡 **different mechanism** |
| `databases` | `512` | **`40000`** | `40000` | 🟡 |
| `maxmemory` | **unset** (unbounded — the Pod limit OOM-kills it) | `300mb` | **`52gb`** | 🟡 |
| `maxclients` | unset (default 10000) | `150000` | `60000` | 🔵 |
| `client-output-buffer-limit slave` | unset (default 256mb/64mb/60) | **`0 0 0`** (unlimited) | same | 🟡 |
| `sentinel monitor` quorum | `2` | `1` | `2` | 🔵 |
| `sentinel down-after-milliseconds` | **`5000`** | **`3000`** | `3000` | 🔵 |
| `sentinel failover-timeout` | `10000` | unset (default 180000) | same | 🟡 |
| `sentinel parallel-syncs` | `1` | unset (default 1) | same | ✅ effectively the same |
| `sentinel resolve-hostnames` | **`yes`** (required, since Pod FQDNs are used) | unset (operated by IP) | same | 🟡 |
| `sentinel notification-script` | **none** | **present** (`/data/conf/notify-sentinel.sh`) | same | 🔴 |

> **Three things matter here**:
> 1. **`databases 512` vs `40000`** — WEKO consumes a Redis database number per tenant for cache,
>    session and celery (the `CACHE_DB` `SESSION_DB` `CELERY_DB` columns of `tenants.txt`). The
>    sample assumes ~8 tenants and sets 512; **512 is nowhere near enough at production scale**, and
>    connections fail the moment a tenant's DB number exceeds it.
> 2. **AOF vs RDB** — the sample appends to a log, production only snapshots. Recovery behaviour and
>    disk I/O profile both differ, so performance results do not transfer as-is.
> 3. **`maxmemory` unset** — the sample has no ceiling and gets OOM-killed as a Pod when it overflows.
>    Production caps it, so Redis itself evicts or errors instead.
>
> `down-after-milliseconds` is *slower* in the sample (5s vs 3s), relaxed to avoid spurious failovers
> on kind's Docker network. Restoring 3000 is the natural move for production spec.

---

## 6. Application layer (WEKO itself)

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| Deployment structure | init (jinja2) + nginx + web (uwsgi) + worker (celery) | identical (`weko/manifest_template/deploy-web.yaml`) | ✅ |
| `hostAliases` mapping own FQDN to 127.0.0.1 | yes | yes | ✅ |
| `securityContext.fsGroup: 1000` | yes | yes | ✅ |
| Rolling update | `maxSurge:1 / maxUnavailable:0` | identical | ✅ |
| Mount layout | conf / data / shib / static | identical | ✅ |
| `static` volume | PVC | **emptyDir**, populated from `static.org/*` at startup (`deploy-web.yaml:118`) | 🔵 |
| What the nginx container is | **an image built from the weko source with the Shibboleth SP** (`deploy-amd64.sh:180-212`) plus a ConfigMap (`21-nginx-config.yaml`). TLS terminates at the Ingress, so the Pod speaks plaintext 80 | the same custom image, but **terminating TLS on 443 inside the Pod** | 🟡 only the TLS hop count differs |
| `/secure/login.py` and fcgiwrap for the SP | **added at build time** — weko's `nginx/Dockerfile` ships only `login.php` and no fcgiwrap, but weko-accounts uses `login.py`; the NPH-style `Status:` line is fixed up too | already in the image | 🟡 **compensated for on the sample side** |
| Enabling the Shibboleth SP | config distributed only with `WEKO_SHIB=yes` (default `no`, `deploy-amd64.sh:65`) | always enabled (`shibboleth_template` distributed) | 🔵 |
| WAF | none | App Protect (on the Ingress, not in nginx) | 🔴 |
| uwsgi process count | fixed | set per tenant (a `repositories_file` column) | 🔵 |
| Memory requests/limits | init/web/worker only (`gen-tenant.sh:345,378,403`) | per tenant, with nginx branching by FQDN (`make_weko_manifests.sh`) | 🔵 |

### 6-1. GakuNin federation — the IdP and mAP

With `WEKO_SHIB=yes` the sample **builds and runs a real Shibboleth IdP 5.2.3**. Adding
`WEKO_SHIB_MAP=aggregation` stands up **a second entity acting as the attribute authority (AA)**,
the stand-in for GakuNin mAP, and fetches `isMemberOf` from it via SimpleAggregation. See
[SHIBBOLETH-IDP.en.md](k8s-weko-amd64/SHIBBOLETH-IDP.en.md).

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| IdP | built in-house and run in-cluster (`70-shibboleth-idp.yaml`, Shibboleth IdP 5.2.3 / Tomcat 10.1) at `idp.localhost` | **the JAIRO Cloud IdP** (`https://idp.repo.nii.ac.jp/idp/shibboleth`, `shibboleth2.xml:46`) plus each institution's IdP | 🟡 |
| The IdP's user store | **htpasswd, 3 users** (admin / libadmin / teacher, `credentials/demo.htpasswd`) | the institution's directory | 🟡 |
| Where metadata comes from | `provision-shib.sh` extracts it from the image into a ConfigMap (no signature check) | `MetadataProvider type="XML"` polling `https://idp.repo.nii.ac.jp/metadata/irjaya.xml` every 7200s (`shibboleth2.xml:86-92`) | 🟡 |
| Metadata signature verification | **none** (everything stays inside the cluster) | `MetadataFilter type="Signature"` is **commented out** in the template (`shibboleth2.xml:88-90`) | 🟡 **not enabled in production's template either** |
| Distributing the SP config | `shib-sp-template/` substituted with sed onto NFS | `deploy/weko/shibboleth_template/` distributed per tenant | ✅ **same idea** |
| Where `isMemberOf` comes from | **a second entity**, `map.localhost` (`71-shibboleth-map.yaml`), queried by SimpleAggregation | **GakuNin mAP** (`https://sptest.cg.gakunin.jp/idp/shibboleth`), queried by SimpleAggregation | 🟡 **same mechanism, different peer** |
| Shape of the `isMemberOf` values | `https://map.localhost/gr/<group>` and `.../admin` | `https://cg.gakunin.jp/gr/<group>` and `.../admin` | ✅ **shape matches** (only the host differs) |
| Back channel | 8443 with `idp-backchannel.p12`, **trusted via the KeyDescriptor in the metadata** (ExplicitKey) | GakuNin's real server certificate (public CA) | 🟡 |
| `isMemberOf` in `attribute-map.xml` | present (`urn:oid:1.3.6.1.4.1.5923.1.5.1.1`) | **not in the IaC template** — added by hand on the running systems | 🟡 **outside the IaC** |
| The SimpleAggregation config | `shib-sp-template/simple-aggregation.xml`, **under configuration management** | **not present in the `~/weko-k8s` template** — applied by hand | 🟡 **outside the IaC** |
| Default state | **disabled** (`WEKO_SHIB=no` / `WEKO_SHIB_MAP=no`) | always enabled | 🔵 |

> **A design note, confirmed on the running cluster**: SimpleAggregation **will not send an
> AttributeQuery to the same entity the user logged in through** — shibd drops it with
> `skipping previously queried attribute source`. So a setup where the IdP also releases
> `isMemberOf` does not exercise SimpleAggregation at all, and **the attribute authority has to be a
> separate entity**. That is why the sample splits the IdP from the AA, which mirrors production's
> split between the institutional IdP and mAP at `cg.gakunin.jp`.

> **The heart of the 🟡**: **in production the GakuNin integration lives outside the IaC.**
> Neither `shibboleth2.xml` nor `attribute-map.xml` under
> `~/weko-k8s/deploy/weko/shibboleth_template/` contains SimpleAggregation or `isMemberOf`; both are
> added on the running systems. Assuming "distributing the template makes mAP integration work"
> **will lose that configuration**. The sample keeps it under configuration management, so
> **the sample is the better source of truth when porting**.

---

## 7. Tenant management layer

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| Tenant definition file | `tenants.txt` (**9 columns**) | `repositories_file` (**20 columns**) | 🔵 |
| Columns | `NAME DB HOST EMAIL PASS INIT CACHE_DB SESSION_DB CELERY_DB` | `W2FQDN W3FQDN ACCOUNT PASSWD GOOGLE_ANA CNRI_FLAG DOIFREE MEM_REQ MEM_LIMIT UWSGI_RSS UWSGI_PROC … CACHE_DB SESSION_DB CELERY_DB AGG_HOUR AGG_MIN` | 🔵 |
| Manifest generation | `gen-tenant.sh` (manifests + PVs + Ingress in one) | `scripts/make_weko_manifests.sh` (manifests only) | 🔵 |
| Shared-FS initialization | `provision-nfs.sh` | `scripts/make_volumes.sh` | 🔵 |
| Rollout | `deploy-amd64.sh:261-281` | `scripts/deploy_weko.sh` (**throttled by node count**) | 🔵 |
| Generation technique | sed substitution into a template | sed substitution into a template | ✅ **same idea** |
| Certificate provisioning | cert-manager issues automatically | a real certificate file per tenant, turned into a Secret | 🟡 |
| DB initialization | `weko-init.sh` + `seed-demo.sh` | (replaced by loading migrated data) | 🔵 |

---

## 8. Namespace and configuration-management layer

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| WEKO application | `weko3` | `weko3` | ✅ |
| PostgreSQL | `weko3` (operator lands in `default`) | **`weko3pg`** | 🔵 |
| Elasticsearch | `weko3` | **`weko3es`** | 🔵 |
| RabbitMQ | `weko3` | **`weko3ra`** | 🔵 |
| Redis | `weko3re` | `weko3re` | ✅ |
| Ingress | `ingress-nginx` | `nginx-ingress` / `nginx-ingress-internal` | 🔵 |
| Monitoring / logging / maintenance | none | `monitoring` / `logging` / `maintenance` | 🔴 |
| NFS | `nfs-system` | (outside the cluster) | 🟡 |
| Configuration management | plain manifests + `sed \| kubectl apply -f -` | kustomize `base`/`components`/`overlay` | 🔵 |
| How environment differences are absorbed | environment variables | overlays | 🔵 |
| Deployment style | one imperative script (357 lines) | declarative kustomize + purpose-specific scripts | 🔵 |

> **Watch the blast radius**: splitting namespaces changes every Service FQDN
> (`elasticsearch` → `elasticsearch.weko3es.svc.cluster.local`, and so on). **Every** connection
> setting that `gen-tenant.sh` writes into the ConfigMap has to be revisited.

---

## 9. Secret management

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| Approach | inlined in manifests and scripts | consolidated in `deploy/secret.properties`, turned into Secrets by the kustomize `secretFromProperties` generator | 🟡 |
| MinIO / S3 keys | **plaintext** (`40-minio.yaml:10-11`, `deploy-amd64.sh:138-141,228`) | `weko3pg.postgres-pod-secrets.AWS_*` etc. | 🟡 |
| PostgreSQL password | **force-overwritten** to `weko` (`deploy-amd64.sh:231-236`) | `weko3pg.postgresql-infrastructure-roles.invenio` | 🟡 |
| Admin passwords | plaintext in `tenants.txt` (tracked in Git) | `repositories_file` (plaintext, but untracked) | 🟡 |
| Registry credentials | not needed | `ocir-secret` per namespace | 🔴 |
| TLS private keys | managed by cert-manager | `secret.properties` / certificate files | 🔵 |
| Slack webhooks | none | `logging.slack-config.*` | 🔴 |

---

## 10. Operations layer

| Item | kind verification environment | Production | Class |
|---|---|---|---|
| **Monitoring** | **none** | kube-prometheus-stack + ServiceMonitors (pg / pgpool / redis / rabbitmq / es / ingress) + Grafana dashboards + alert rules (`deploy/monitoring/`) | 🔴 |
| **Log aggregation** | **none** | fluentd → Elasticsearch → Kibana, kubernetes-event-exporter, Slack notifications (`deploy/logging/`) | 🔴 |
| **DB backup** | **none** | operator WAL / logical backup (`components/backup_s3`) plus pgdump via rclone to Object Storage (`components/pgdump_s3`) | 🔴 |
| **ES backup** | snapshot config pointing at MinIO only (no job) | `essnapshot-job` (`elasticsearch/components/backup_s3/`) | 🔴 |
| **Content backup** | **none** | rclone CronJob (`deploy/contents-backup/`) | 🔴 |
| **Restore procedures** | **none** | `scripts/restore_db*.sh` / `restore_es*.sh`, `overlay/*/restore-pv*.yaml` | 🔴 |
| **Maintenance page** | **none** | `deploy/maintenance/` | 🔴 |
| **Maintenance pod** | **none** | `deploy/maintenance-pod/` | 🔴 |
| **Node maintenance** | **none** | `scripts/maintenance/` (drain / delete_old_nodes / OKE upgrade) | 🔴 |
| **Stats rotation** | **none** | `postgresql/components/stats_rotate` | 🔴 |
| **Teardown** | `teardown-amd64.sh` (**deletes the whole cluster**) | `scripts/maintenance/delete_*.sh` (targeted) | 🟡 |
| **Forced recovery** | `unwedge-amd64.sh` | none | 🔵 |
| Re-run initialization | **`FORCE_INIT=yes` by default** (`deploy-amd64.sh:40`) — a re-run re-initializes every tenant | not applicable | 🟡 **destructive in production** |

> **Why 🟡 matters here**: `teardown-*.sh` deletes the cluster and `FORCE_INIT=yes` re-initializes
> every tenant. Both are correct defaults for a disposable kind environment and **both destroy data
> if carried into production**.

---

## 11. Summary by class

| Class | Main entries |
|---|---|
| ✅ **Match** (no change needed) | Deployment structure, mount layout, `fsGroup`, rolling-update strategy / shared-FS directory layout / pgpool 4.2.2 and **almost all of its tuning values** / ES 6.8.23 / RabbitMQ 4.0.9 / PostgreSQL synchronous replication / the `md5` constraint / the sed-substitution approach to tenant generation / the `weko3` and `weko3re` namespaces / the absence of PDBs and NetworkPolicies (production is the same) / metrics-server / how the Shibboleth SP config is distributed / the shape of the `isMemberOf` values |
| 🔵 **Simplified** (restore production form) | 2 node-type labels → 8 / namespace split / sizing throughout / replica counts (PG 2→3, ES 2→13, pgpool 1→3, …) / PostgreSQL parallelism and WAL values / the ES heap and `minimum_master_nodes` / Redis `maxclients` / Sentinel `down-after-milliseconds` (5000→3000) / tenant definition 9 → 20 columns / custom Redis images / `static` as emptyDir / adopting kustomize / GakuNin integration being off by default |
| 🟡 **Stand-in** (**must be replaced**) | the kind cluster / `kind load` + `imagePullPolicy: Never` / the `standard` StorageClass / **the in-cluster NFS and its hardcoded ClusterIP** / MinIO / ingress-nginx OSS + `extraPortMappings` / the cert-manager self-signed CA / `*.localhost` / plaintext secrets / `FORCE_INIT=yes` / `teardown-*.sh` / the PostgreSQL major version / **the replication timeouts production disables but the sample does not** / **the missing RabbitMQ `consumer_timeout` (3 hours)** / **the missing ES `-Dlog4j2.formatMsgNoLookups=true`** / **Redis persistence (AOF vs RDB), `databases 512`, and the unset `maxmemory`** / the in-house IdP and AA standing in for GakuNin and mAP |
| 🔴 **Absent** (build new) | monitoring / log aggregation / all backups / restore procedures / WAF / TLS hop 2 / maintenance page and maintenance pod / node maintenance procedures / internal ingress / registry credentials / the Sentinel `notification-script` |

### In one paragraph

- **The application layer — the structure of WEKO itself — already matches production.** Porting it
  is not a concern.
- **The infrastructure layer is full of 🟡 stand-ins.** Mechanisms for working around kind's limits
  are embedded throughout; carried into production they either fail to start or break quietly.
- **The operations layer is entirely 🔴 absent.** It was unnecessary for verification and has to be
  built from scratch for production.
- **For the middleware, the versions line up but the values do not** (see 5-4). pgpool is essentially
  an exact match, but PostgreSQL, RabbitMQ, ES and Redis all carry **differences that survive
  matching the sizing**. The two to watch are **RabbitMQ's `consumer_timeout`** (3 hours in
  production, a 30-minute default in the sample) and **Redis's `databases`** (40000 vs 512) —
  both surface only once the data grows.
- **The GakuNin mAP integration lives outside the IaC in production too** (see 6-1). The sample is
  further along as configuration management, so treat the sample as the source of truth when porting.

---

## Related documents

| Document | Contents |
|---|---|
| [PRODUCTION-ROADMAP.en.md](PRODUCTION-ROADMAP.en.md) | The order in which to resolve these differences |
| [README.en.md](README.en.md) | Overall design of the sample |
| [CONSTRUCTION.en.md](CONSTRUCTION.en.md) | How it was built and the HA design decisions |
| [COMPARE-weko-workshop.en.md](COMPARE-weko-workshop.en.md) | Comparison with the docker-compose version |
| [JAIRO-CLOUD-ARCHITECTURE.en.md](JAIRO-CLOUD-ARCHITECTURE.en.md) | JAIRO Cloud production architecture |
| `~/weko-k8s` (`RCOSDP/weko-k8s`) | the production IaC itself |
