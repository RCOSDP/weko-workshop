# Final Setup — 1 tenant at first, room for about 8 (amd64 / 64GB / 1TB)

- Target host: **amd64 Linux / 16 cores / 64GB / 1TB**
- Plan: **start with 1 tenant**, but make the backends big enough for **about 8 tenants**. This way you do not need to redesign when you add tenants.
- Assumption: about 10,000 records per tenant (about 80,000 in total at 8 tenants). Low to medium traffic per tenant.
- This is done by the `k8s-weko-amd64/` set. Only tenant1 is on in `tenants.txt`. tenant2–8 are already written, but as comments.

## 1. Resources (backends are fixed at 8-tenant size)

| Component | Instances | Memory (request → limit) | Is it enough at 8 tenants? |
|---|---|---|---|
| **Elasticsearch** | 2 nodes | 2560Mi → **3Gi** (heap **2g**) | 80k docs still leaves room at heap 2g. replica=1 for backup |
| **PostgreSQL** (Patroni) | 2 nodes | 1Gi → **2560Mi** | 8 DBs, a few GB of metadata. primary + standby |
| **RabbitMQ** (cluster) | 3 nodes | → **1Gi** | vhosts/quorum for 8 tenants |
| **Redis** (Sentinel) | redis ×3 + sentinel ×3 | about 1.6Gi | databases=512 (up to 170 tenants) |
| **MinIO** (S3) / **NFS** | 1 each | 1Gi / 0.5Gi | **Keeps the content files (S3 Location)** / shared FS (RWX) for theme conf/data |
| **weko web** (per tenant) | 1 at first (up to 8) | web 0.7 → **1.5Gi** (processes=1) + worker → **1Gi** + nginx → 0.25Gi | This is the part that grows with each tenant |

> The backends stay **almost the same no matter how many tenants** you have (ES/PG/MQ/Redis are shared). Only the **web pod (about 2.75Gi per tenant)** grows.

## 2. Memory plan (now and later)

| | Fixed backends | web | System | Total limits | Real usage we expect |
|---|---|---|---|---|---|
| **At first (1 tenant)** | about 19GiB | 1×2.75=2.75 | about 9 | **about 31GiB** | about 22GiB |
| **Later (8 tenants)** | about 19GiB | 8×2.75=22 | about 9 | **about 50GiB** | about 35GiB |

→ **Even 8 tenants fit in 64GB (about 14GiB free).** The first deploy has a lot of room.

## 3. Disk (1TB, for 8 tenants)

| Use | Size | PVC |
|---|---|---|
| OS + images + k8s | about 80GB | — |
| PostgreSQL (metadata, 80k total) | about 20GB | 50Gi |
| Elasticsearch (indices, 2 nodes) | about 40GB | 60Gi × 2 |
| **Content files** (S3 `weko-<tenant>` on MinIO + backups) | **about 600GB** | MinIO 600Gi |
| NFS export (theme conf/data only, small) | about a few GB | 30Gi |

> **The files are kept on the S3 (MinIO) Location** (`files_location.type='s3'`, `uri=s3://weko-<tenant>`). The NFS share keeps only the theme `conf/` (instance.cfg and so on) and `data/` (`_variables.scss`, indextree, and so on). These are small.
> File size guide (80k items in total): average 1MB → 80GB / 5MB → 400GB (good) / 10MB → 800GB (you need a bigger MinIO PVC or more disk). If you go over the MinIO PVC (600Gi), use an outside S3 or add disk.

## 4. Deploy (1 tenant at first)
```bash
# first do the setup (README-amd64.en.md §0): docker / kubectl / kind / sysctl / weko source
sudo bash prereq-amd64.sh && newgrp docker
bash deploy-amd64.sh          # tenants.txt has one tenant, so it builds only tenant1
# → http://tenant1.localhost/  (see tenants.txt for the admin)
```
The backends come up with room for 8 tenants, but web runs only for tenant1 (memory about 22GiB at first).

## 5. Adding tenants (→ up to 8)
1. Remove the `#` on tenant2 and later in `tenants.txt` (as many as you need).
2. Generate, deploy, provision, and set up:
```bash
bash gen-tenant.sh
kubectl apply -f generated/
bash provision-tenants.sh                 # make the PG DB / RabbitMQ vhost for the new tenants
# set up only the new tenants (weko-init.sh). Run it inside the web container with base64:
for t in tenant2 tenant3 ... ; do
  POD=$(kubectl get pod -n weko3 -l app=${t}-web -o jsonpath='{.items[0].metadata.name}')
  kubectl exec -n weko3 $POD -c web -- bash -lc "echo $(base64 -w0 weko-init.sh)|base64 -d|bash"
  # then seed admin_settings (same as deploy-amd64.sh §8)
done
bash set-s3-location.sh    # make buckets for the new tenants + set files_location to the S3 type
```
- The backends (ES/PG/MQ/Redis/MinIO/NFS) need **no redesign and no redeploy** (they already run with 8-tenant size).
- Only the web pods add load (+about 19GiB at 8; the plan still fits in 64GB, see §2).

## 6. How to tune
| Goal | What to do |
|---|---|
| Heavy access on one tenant | Set web to `processes=2` and limit 2Gi → now it fits 6–7 tenants |
| 100k records for one tenant | Make the heap in `13-elasticsearch.yaml` 4–6g and grow the PVC |
| More than 8 tenants | Make web smaller + drop RabbitMQ/PG/ES to one node each (this gives up HA) |
| Big or many files | Grow the MinIO PVC (600Gi) + add disk. If that is not enough, point the endpoint in `set-s3-location.sh` to an outside S3 (AWS / MinIO on another host) |

## 7. Things to keep in mind
- One server → **if the server dies, everything stops** (a 3-node cluster only protects against process failures).
- For backups, copy **the PG dump + the content (MinIO bucket `weko-<tenant>`)** to another place (`../CURRENT-STATE.en.md` §11). The files are already on S3 (MinIO), so `mc mirror` can copy them to an outside S3.
