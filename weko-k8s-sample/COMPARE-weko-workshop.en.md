# This Setup vs. weko-workshop (Official Tutorial) — Comparison

[RCOSDP/weko-workshop](https://github.com/RCOSDP/weko-workshop) is the **official WEKO3 tutorial (GitBook)**.
Besides how to use it (roles / items / item types / workflows), it shows **two ways to build the environment**.

> Note: this comparison describes the early **simplified** single-host build. The setup has since been upgraded to
> **HA clusters + Redis Sentinel + pgpool + persistence + NFS + S3** (see `CURRENT-STATE.en.md`). "(now added)" marks
> the points that changed.

## The two build methods in weko-workshop

| | Method A: Vagrant + docker-compose | Method B: Kubernetes (weko-k8s) |
|---|---|---|
| Role | **Development environment** (one VM, Windows assumed) | **Production/staging** (like JAIRO Cloud) |
| Source repository | `RCOSDP/weko` (`install2.sh` / `docker-compose2.yml`) | `RCOSDP/weko-k8s` (deploy/ manifests) |
| Cluster | Not needed (docker-compose) | **Assumes a cluster already exists** ("Connecting k8s cluster" is left blank = OKE or similar is assumed ready) |
| Components | 8–9 containers: nginx / web / worker / elasticsearch / redis / rabbitmq / postgresql / **pgpool** / flower | ingress (F5) + ES + PG (operator) + Redis Sentinel + RabbitMQ + weko, plus **NFS shared FS** (/fs-config etc.) |
| Tenancy | Single | **Multi-tenant** (repositories_file) |
| Storage | Local | Mounts **OKE File Storage (NFS)** |

> So the K8s chapter of weko-workshop treats **building the cluster itself (nodes / API server) as out of scope**
> (it assumes you connect to a managed cloud K8s such as OKE). It is an operations guide for mounting an NFS shared FS
> and deploying the weko-k8s manifests.

## What was built here

**A real K8s cluster (nodes + API server) built from nothing with kind**, running weko3 as a **multi-tenant** setup
with **simplified** weko-k8s manifests (running amd64 on arm64 with emulation).

## Three-way comparison

| Item | weko-workshop A (compose) | weko-workshop B (K8s/OKE) | **This setup (kind)** |
|---|---|---|---|
| K8s cluster | None | **Assumed** (not built by you / OKE) | **Built from nothing with kind (nodes + API server)** |
| Platform | 1 VM | OKE (x86) | One host (arm64 + **emulation**) |
| Tenancy | Single | Multi | **Multi** (tenant1/tenant2) |
| web/nginx image | `docker-compose build` (weko3_web/nginx) | Same, shared via registry | **Same images** (mhayashi55/weko3-* = same as weko3_web) |
| PostgreSQL | postgres + **pgpool** | postgres-operator (HA) + pgpool + pgbouncer | Standalone postgres:13 (now added: operator HA + pgpool) |
| Elasticsearch | Standalone (ES6+kuromoji) | weko_elasticsearch 6.8.23 | **Self-built 6.8.23 + kuromoji/icu** |
| Redis | Standalone | **Sentinel (HA)** | Standalone per tenant (now added: Sentinel HA) |
| RabbitMQ | Standalone | Cluster | Standalone 3.13 (now added: 3-node cluster) |
| Front proxy / WAF | nginx (Shib+SSL) | F5 NGINX + App Protect | Stock nginx (uwsgi_pass) |
| Shared FS | Local | NFS (FSS) | emptyDir (now added: NFS RWX) |
| Initialization | `install2.sh` (create/populate) | Same | **Same populate** (weko-init.sh) |
| Access | port forward | Ingress/FQDN | Ingress + host (80/443) / port-forward |

## Assessment

- **The application layer is the same as the official setup**: the images (weko3_web/nginx), the initialization flow
  (create/populate-instance), ES6+kuromoji, uwsgi + nginx, and the multi-tenant separation keys (DB name / index prefix /
  vhost / redis) are **the same as weko-workshop (that is, weko-k8s)**. What was built here is not an "unofficial one-off" —
  it sits **on top of the official steps**.

- **Where this setup goes further than the official docs**: it **does the cluster build that the K8s chapter of
  weko-workshop leaves blank** (control-plane + worker + API server on kind). Without a managed platform
  such as OKE, **weko3 on K8s is finished on one machine**. On top of that, **arm64** — an unsupported
  environment — is handled with amd64 emulation (the official docs assume x86).

- **Where this setup is simpler (that is, different from production)**: at first, HA (postgres-operator / Redis Sentinel / pgpool),
  F5 App Protect (WAF), NFS shared FS, backup/monitoring/logging, and Shibboleth login were left out.
  (HA clusters, Redis Sentinel, pgpool, NFS, and S3 have since been added.) That early simplified **backend layout
  (standalone PG/ES/Redis/RabbitMQ) was actually closer to the docker-compose development version (A) of weko-workshop**
  (minus pgpool/flower).

- **Conclusion on role**: what was achieved here is
  **"a hybrid: the Method B (K8s) architecture of weko-workshop, first with backends simplified to Method A (compose) level,
  running on a self-built kind cluster with arm64 support and multi-tenancy"** (later brought up to HA level).
  As a way to learn, test, and run weko3-on-K8s on one machine, it takes the best of both official methods.

## If you want to get closer to the official steps (optional next steps)

1. **For easy development** → weko-workshop A (`RCOSDP/weko` + `docker-compose2.yml`). Fastest, no K8s needed.
2. **For production fidelity** → move toward weko-workshop B, even on kind:
   - Switch Redis to a **Sentinel** setup (go back to the `redissentinel` default in instance.cfg) — **done**
   - Send PostgreSQL through **pgpool** — **done** (`62-pgpool.yaml`)
   - Move the shared FS to **PVC/NFS** (drop emptyDir = keep data) — **done**
   - Add **per-tenant TLS certificates** to the Ingress (now self-signed = browser warnings)
3. **Backup / monitoring** → add weko-k8s's `contents-backup` / `monitoring` / `logging`.
