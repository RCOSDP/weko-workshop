# JAIRO Cloud (weko-k8s) Production Deployment Architecture — Summary

A summary of the **production deployment architecture like JAIRO Cloud**, read from the structure of the
[RCOSDP/weko-k8s](https://github.com/RCOSDP/weko-k8s) repository.
(Note: this is read from the manifests/scripts in the public repository; the versions are the ones in the repository.
Real operational settings and details may be different. A comparison with the simplified kind setup built here is at the end.)

---

## 1. Platform

| Item | Details |
|---|---|
| Cloud | Oracle Cloud Infrastructure (OCI) |
| Kubernetes | **OKE** (Oracle Kubernetes Engine, managed) |
| Nodes | Several node pools (`nodepool-cloud-init`). Roles are split with `nodeType` labels (`WEKO`/`DATA`, etc.) |
| Image pull | **OCIR** (Oracle Container Registry). `imagePullSecrets: ocir-secret` |
| Shared storage | **OKE File Storage (FSS / NFS)**. `config`/`data`/`static`/`nginx`/`shibboleth` are mounted per tenant with PVs that use `storageClassName: nfs` |
| Object storage | **OCI Object Storage (S3-compatible)**. Holds backups. Versioned buckets managed by `scripts/as` (boto3) |
| Manifest management | `kustomize` (each component is `base` / `components` / `overlay`) |

---

## 2. Namespaces and components

| Namespace | Role | Main components (images as in the repository) |
|---|---|---|
| `weko3` | **weko itself (per-tenant web)** | init(jinja2) + nginx (Shibboleth SP + SSL + WAF) + web(uwsgi) + worker(celery) |
| `weko3pg` | **PostgreSQL (HA)** | Zalando **postgres-operator v1.13.0** + **Spilo-13**(2.0-p6) + **pgpool2 4.2.2** + **pgbouncer**(master-16) + exporters (`pgpool2_exporter`, `postgres-exporter`) + `weko-pgdump` + `weko-stats-rotate` |
| `weko3es` | **Elasticsearch** | `weko_elasticsearch:v6.8.23` (ES6 + kuromoji) + snapshots (`essnapshooter`) |
| `weko3re` | **Redis (HA)** | `weko_redis:v1.0` + `weko_sentinel:v1.0` (Sentinel setup) + `redis_exporter` |
| `weko3ra` | **RabbitMQ** | `rabbitmq:4.0.9` (quorum queue) |
| `nginx-ingress` / `nginx-ingress-internal` | **Ingress + WAF (external/internal, two paths)** | **F5 NGINX Plus Ingress** (`nginx-plus-ingress`) + **NGINX App Protect** (`appprotect.f5.com` CRDs, `weko-policy`/`nothreat-policy`/apdos) |
| `logging` | **Log collection** | `weko_fluentd:v0.0.1` + fluentd-celery + Elasticsearch/Kibana 7.16.2 (for logs; separate from the ES6 the app uses) + `kubernetes-event-exporter` |
| `monitoring` | **Monitoring** | **kube-prometheus-stack** (Prometheus/Grafana/Alertmanager) + `k8s-sidecar` + `dcgm-exporter` (GPU) + `oauth2-proxy`/`keycloak-proxy` (UI login) |
| `maintenance` / `maintenance-pod` | Pods for operational work | `maintenance_pod:latest` |
| `contents-backup` | **Content backup** | `rclone:1.69` → Object Storage |
| `metrics-server` | For HPA / `kubectl top` | metrics-server |

---

## 3. The weko application Pod (one tenant = one Deployment)

```
Pod (nodeType=WEKO)
 ├ initContainer: makes invenio.cfg from instance.cfg with jinja2
 ├ nginx : Shibboleth SP + TLS termination + NGINX App Protect (WAF) + static serving + uwsgi_pass
 ├ web   : uwsgi (invenio_app.wsgi, socket:5000)
 └ worker: celery worker (-B, beat embedded)
volumes: nginx / shibboleth / config / data / static on OKE FSS (NFS) (+PVC)
imagePullSecrets: ocir-secret
```

- Config comes from `configmap` (endpoints, feature flags) + `secret` (credentials, keys) via `envFrom`.
- Redis runs in **redissentinel** mode (`CACHE_TYPE=redissentinel`, `CACHE_REDIS_SENTINELS=[("weko-sentinel-service.weko3re",26379)]`).
- Login uses **Shibboleth / GakuNin SAML** (`SHIB_IDP_LOGIN_URL`, etc.).

---

## 4. Multi-tenancy in production

A tenant file `repositories_file` (one line = one repository) is given to scripts that make and deploy everything at once.

| Column (part) | Purpose |
|---|---|
| W2FQDN / W3FQDN | Repository ID / public FQDN |
| account / passwd | First administrator |
| CNRI / DOIFREE | Handle / DOI method |
| memory req/limit, uwsgi rss/process | Resource tuning |
| redis DB numbers (cache/session/celery) | Per-tenant Redis DB split |
| Aggregation event times | Statistics batch |

**Script chain from making to deploying:**
```
make_volumes.sh          … makes per-tenant nginx/shib/config/data directories on FSS
make_weko_manifests.sh   … makes per-tenant manifests from templates + SSL certificates (openssl)
make_rabbitmq_vhost.sh   … rabbitmqctl add_vhost "<DOMAIN>/" + set_permissions
deploy_weko.sh           … kubectl apply + makes the tls secret (<domain>-cert); rolls out step by step based on node count
```

**What is split per tenant:**

| Split resource | Key |
|---|---|
| Database | `INVENIO_POSTGRESQL_DBNAME = REPNAME` (a DB inside PostgreSQL) |
| Search index | `SEARCH_INDEX_PREFIX = REPNAME` (a prefix split inside one ES cluster) |
| Messaging | RabbitMQ vhost `<DOMAIN>/` |
| Cache/session | DB number inside the shared Sentinel Redis (different numbers for cache/session/celery) |
| Publication/TLS | FQDN + per-tenant SSL certificate (tls secret) + WAF policy |
| Storage | Per-tenant directory on FSS |

> Note: the backends (PostgreSQL / Elasticsearch / Redis / RabbitMQ) are **shared by all tenants** and split
> logically by the keys above. This is the same idea as the kind setup here (here, only Redis started as a per-tenant instance).

---

## 5. Backup / operations

- **DB**: `weko-pgdump` (`pg_dump`, without alembic_version) → Object Storage. Restore with `restore_db*.sh`.
- **ES**: snapshots (`essnapshooter`) → Object Storage. Restore with `restore_es*.sh`.
- **Content**: `rclone` (`contents-backup`) → Object Storage.
- **Bucket management**: `scripts/as` (boto3, versioning + lifecycle / expiring old versions).
- **Maintenance**: `scripts/maintenance/` has OKE node pool drain/upgrade, redeploy of each backend, log format changes, queue purges, etc.
- **WAF management**: `scripts/waf_management/` (bulk loading of certificates and access/protection rules; OCI/F5 integration).

---

## 6. Comparison with the simplified kind setup built here

| Item | JAIRO Cloud (OKE production) | This setup (kind) |
|---|---|---|
| Platform | Oracle OKE (managed, several node pools) | kind (one host, 3 nodes) |
| Architecture | x86_64 (amd64 native) | **arm64 native** (weko and ES built for arm64; no emulation used) |
| Multi-tenancy | `repositories_file` → script generation (many tenants) | `tenants.txt` → `gen-tenant.sh` (2 tenants) |
| PostgreSQL | postgres-operator (Spilo) HA + pgpool + pgbouncer | **Zalando postgres-operator + Patroni 3-node HA** (spilo-17, arm64) + **pgpool** (no pgbouncer) |
| Elasticsearch | `weko_elasticsearch:v6.8.23` (+ snapshots) | **3-node cluster of arm64-native 6.8.23** (real kui.txt / kuromoji / repository-s3) |
| Redis | `weko_redis` + `weko_sentinel` (Sentinel HA, redissentinel) | **Redis Sentinel HA** (master + 2 replicas + 3 sentinels, redissentinel) |
| RabbitMQ | `4.0.9` cluster | **3-node 4.0.9 cluster via RabbitMQ Cluster Operator** |
| Ingress/WAF | **F5 NGINX Plus + App Protect** (external/internal) | `ingress-nginx` (OSS; no WAF) |
| Front nginx | Shibboleth SP + SSL + WAF | Stock nginx with `uwsgi_pass` only |
| Shared FS | OKE File Storage (NFS) | NFS (RWX) for per-tenant conf/data + PVC (kind local-path) for the backends |
| Backup | Object Storage (pgdump/snapshot/rclone) | **MinIO (S3)** + a working pg_dumpall backup |
| Logging | fluentd → ES/Kibana 7.16 | `kubectl logs` |
| Monitoring | kube-prometheus-stack + Grafana + exporters | None (metrics-server optional) |
| Authentication | Shibboleth / GakuNin SAML | Local accounts |
| Image pull | OCIR (`ocir-secret`) | Docker Hub + self-built arm64 images + `kind load` |

> **Key point**: the application layer, plus **HA clustering (operator-based), Sentinel, pgpool, S3, and persistence**, copy the
> same structure as production. The main things still missing are operational extras — **pgbouncer, WAF,
> monitoring/logging, authentication (GakuNin)** — and the platform difference
> **OKE (x86) → kind (arm64 native)** (emulation is gone).
