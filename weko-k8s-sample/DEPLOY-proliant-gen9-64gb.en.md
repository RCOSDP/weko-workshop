# Deployment Design — HP ProLiant Gen9 (16 cores / 64GB / 1TB)

Target server: **HP ProLiant Gen9 / 16 cores / 64GB RAM / 1TB storage**

## 0. Most important point: this server is amd64 (x86_64)

ProLiant Gen9 uses an Intel Xeon = **x86_64/amd64**. This is different from the current dev machine (arm64):
- **You do not need emulation** (no qemu segfault or core dump problems).
- **You do not need arm64 builds.** WEKO3 and ES are both **built for amd64 from the newest source** (steps 0 and 2 of `deploy-amd64.sh` do this for you).
- The steps come from [`README.en.md` Appendix C (amd64 runbook)](./README.en.md#appendix-c-runbook-when-arm64-is-not-involved-x86_64--amd64-servers).

| Component | What to use on amd64 |
|---|---|
| weko application | **amd64 build from the newest source (RCOSDP/weko)** → `weko3-web:amd64` (set `WEKO_IMAGE` only to use a prebuilt image) |
| Elasticsearch | weko ES on the official `docker.elastic.co/.../6.8.23` base (`/home/mhaya/weko/elasticsearch/Dockerfile`) |
| PostgreSQL | Zalando `spilo-13` (production PG13, amd64) or spilo-17. The operator is amd64. |
| RabbitMQ / Redis / MinIO / nginx / NFS | All official amd64 |

## 1. Choosing the platform

This is **one physical server**. So "node-failure HA" does not really help (the server itself is the single
weak point). A 3-node cluster is still useful for **surviving process crashes and copying the production shape**,
but on one machine it uses 3× the memory and gives no real HA.
→ **We suggest fewer instances (1–2) with more resources each.** Keep 3 nodes only if you want a staging system
that looks like production.

- k8s: the current **kind** (one host, containers act as nodes) works. If you want something closer to production,
  **k3s** (single-node k8s, light) is another choice.
- Node layout (kind): control-plane 1 + worker 2 (WEKO/DATA labels), same as now.

## 2. Memory plan (64GB)

Keep **about 14GB** for the OS, k8s, and page cache. This leaves about 50GB for the workloads.
(ES and PG use the OS page cache, so it is important not to use all the RAM.)

| Group | Component | Size (limit) | Notes |
|---|---|---|---|
| System | OS + containerd + kubelet | about 4GB | |
| ″ | kind control-plane + ingress + coredns | about 3GB | |
| ″ | Operators (postgres/rabbitmq/cert-manager/nfs) | about 2GB | |
| Data | **Elasticsearch, 2 nodes** (heap 6GB × 2) | 8GB × 2 = **16GB** | replica=1 spreads over the 2 nodes. This drives how many items you can hold |
| ″ | **PostgreSQL, 2 nodes** (Patroni primary + standby) | 3GB × 2 = **6GB** | shared_buffers about 1GB |
| ″ | **RabbitMQ, 3 nodes** (quorum queue) | 1.2GB × 3 = **3.6GB** | 1.5GB if you use one node |
| ″ | Redis Sentinel (master + 2 replicas + 3 sentinels) | **about 1.5GB** total | |
| ″ | MinIO (S3) | **1GB** | |
| App | **weko web × T tenants** (nginx+web+worker) | **about 3.5GB/tenant** | processes=2 / threads=2 (native) |
| Reserve | Page cache / buffers / avoid OOM | **about 10GB or more** | Important for ES/PG speed |

**Rough tenant count (from memory)**:
`memory for weko web ≈ 64 − 14 (system + part of the reserve) − 28 (data) ≈ 22GB` → **about 5–6 tenants** (3.5GB per tenant).
With fewer tenants, you can make the ES heap bigger and hold more items per tenant (a trade-off).

## 3. Disk plan (1TB)

| Use | Rough size | Notes |
|---|---|---|
| OS + images + k8s | about 80GB | |
| PostgreSQL data | about 50GB | Metadata (tens of GB even at 1M records) |
| Elasticsearch data | about 100GB | Indices (depends on item count) |
| Redis/RabbitMQ | about 20GB | |
| **Content files (S3 = MinIO Location)** | **about 700GB** | Most of the data. This is the main use of the 1TB. MinIO PVC |
| NFS export (theme conf/data only) | about tens of GB | Small: `_variables.scss` / indextree, and so on |

> PVC requests on local-path are not hard limits. Still, we suggest you **set clear sizes and watch them** in operation.
> The files are all kept in the **S3 (MinIO) Location** (`files_location.type='s3'`, `uri=s3://weko-<tenant>`) → give 700GB to MinIO.
> NFS holds only the small theme data. If disk gets tight, point the endpoint in `set-s3-location.sh` to an outside S3.

## 4. Capacity (rough numbers for this design)

The limits are the **ES heap (12GB)** and the **file disk (about 700GB)**.

| Profile | Total items (all tenants) | Example |
|---|---|---|
| Mostly metadata (small files) | **about 300k–500k** | ES heap 12GB. e.g. 5 tenants × 60k–100k |
| Average file 2MB | **about 350k** (700GB ÷ 2MB) | Limited by disk |
| Average file 5MB | **about 140k** | e.g. 5 tenants × 28k |
| Average file 50MB | **about 14k** | e.g. 5 tenants × 2,800 |

> Redis can hold **about 170 tenants** with `databases` (already set to 512) plus memory. So **Redis is not the limit on tenant count**.
> The real limits are **web pod memory (tenant count)** and **ES heap + disk (item count)**.

## 5. How to deploy (main points)

1. **Follow Appendix C (amd64)**: no binfmt, no arm64 builds. Build WEKO3 for amd64 from the newest source, then load it. Build ES from the official base too.
2. **Set the resources to the values in this design** (what changes from the arm64 version):
   - `13-elasticsearch.yaml`: **2 nodes**, `ES_JAVA_OPTS=-Xms6g -Xmx6g`, limit 8Gi, keep replicas
   - `51-postgresql-ha.yaml`: `numberOfInstances: 2`, resources 3Gi
   - `50-rabbitmq-cluster.yaml`: `replicas: 3` (or 1), mem 1.2Gi
   - `gen-tenant.sh`: web with `processes=2/threads=2` (native, so no need to cut it), image=`weko3-web:amd64` (built from the newest source). You can remove the emulation workarounds (ulimit/cores/processes=1)
   - `40-minio.yaml`: it holds the **file Location itself**, so make it big (600–700GB). The export in `60-nfs-server.yaml` can stay small because it is only for themes
   - After the deploy, run `set-s3-location.sh` to set each tenant's `files_location` to the S3 (MinIO) type (`deploy-amd64.sh §8` does this for you)
3. **Start with about 5 tenants** (`tenants.txt`). Watch the ES heap and disk, and stop growing when needed.

## 6. HA on one server (an honest note)

- With one machine, **if the server dies, everything stops**. Even a 3-node cluster only protects against **process/Pod failures**.
- If you really need high availability, use **more than one server** and spread the backends over the hosts (= the production OKE shape).
- One 64GB server is good for **staging that looks like production, or small-to-medium production**. Handle disaster recovery with backups (pg_dump / ES snapshot to MinIO).

## 7. Quick sizing guide (when you want to change something)

- **More items per tenant** → use fewer tenants and make the ES heap bigger (e.g. 2 tenants, ES heap 20GB → over 100k items each).
- **More tenants** → make the web pod lighter (processes=1); Redis/PG have room. The ES heap depends on total item count, so keep counts low.
- **Many files** → the files are already in the S3 (MinIO) Location. Grow the disk behind MinIO, or point the endpoint in `set-s3-location.sh` to an outside S3.
