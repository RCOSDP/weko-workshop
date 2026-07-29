# Leaving kind behind: a roadmap for building the production environment

This document lays out **the order in which to build a real Kubernetes environment**, starting from
`weko-k8s-sample` (the kind verification environment).

For *what* is different, see [COMPARE-production.en.md](COMPARE-production.en.md). This document
covers only **in what order, and with what decisions**, those differences get resolved.
Japanese version: [PRODUCTION-ROADMAP.md](PRODUCTION-ROADMAP.md)

---

## 0. Guiding principles

### 0-1. Fork the kind version rather than modifying it

Rather than rewriting `k8s-weko-amd64`, **fork it into a separate directory**.

The reason is that choices such as `imagePullPolicy: Never`, a hardcoded ClusterIP, and
`FORCE_INIT=yes` are **correct for a verification environment and wrong for production**. Trying to
satisfy both in one file produces a mass of conditionals in which neither environment is legible.

The kind version is a genuinely good "reproduce the production topology on one server" verification
environment, and **that value is worth preserving**.

### 0-2. The destination is convergence with the production IaC

The goal should be to converge on the `RCOSDP/weko-k8s` structure (kustomize
`base`/`components`/`overlay`). Building a separate system from scratch means maintaining two
codebases forever.

The roadmap therefore runs: **make the kind version kustomize-based → swap the overlay for production
values → align with the production IaC structure → build the operations layer.**

### 0-3. The ordering principle

**Things that prevent startup first; things that merely fall short later.**

In the terms of [COMPARE-production.en.md](COMPARE-production.en.md):

| Order | Target | Why |
|---|---|---|
| First | 🟡 **Stand-ins** | While these remain **nothing starts**, so you get no feedback |
| Second | 🔵 **Simplifications** | It starts; bring it to production spec before applying real load |
| Third | 🔴 **Absent** | Build once it runs — but required before going live |

---

## Overview

```
Phase 0  Decide the premises        ← skipping this guarantees rework later
   ↓
Phase 1  Adopt kustomize            change only structure; kind keeps working
   ↓
Phase 2  Build the production overlay   replace 🟡 stand-ins → start on a real cluster
   ↓
Phase 3  Converge on production structure   resolve 🔵 → align with weko-k8s
   ↓
Phase 4  Build the operations layer     add 🔴
   ↓
Phase 5  Prepare to go live         data migration, rehearsal, cutover
```

Each phase begins only once the previous phase's exit criteria are met. In particular, doing Phases 1
and 2 together makes it impossible to tell whether a failure came from the structural change or from
the value substitution.

---

## Phase 0 — Decide the premises

**Goal**: settle the choices that determine all later work, before starting.

Leaving these vague guarantees rework from Phase 2 onward.

### What has to be decided

| # | Decision | Options | Blocked without it |
|---|---|---|---|
| 1 | **Platform** | OKE / EKS / GKE / on-prem kubeadm | neither StorageClass nor LB can be chosen |
| 2 | **Kubernetes version** | production IaC is v1.32.1 | API incompatibilities stay hidden |
| 3 | **Block StorageClass** | `oci-bv` / `gp3` / Ceph RBD … | every PVC stays Pending |
| 4 | **What backs the shared FS** | OCI FSS / EFS / campus NAS / CephFS | tenant Pods never start |
| 5 | **Ingress controller** | **NGINX Plus + App Protect (commercial)** / ingress-nginx OSS | WAF requirements and cost undecided |
| 6 | **Exposure method** | LoadBalancer / MetalLB / external LB + NodePort | neither DNS nor certificates can be settled |
| 7 | **Registry** | OCIR / Harbor / GHCR / ECR | the image supply chain cannot be designed |
| 8 | **Whether production data is migrated** | yes / no (greenfield) | **the PostgreSQL major version cannot be chosen** |
| 9 | **What to do about TLS hop 2** | follow production (encryption only) / valid certificate + verification | whether a custom nginx image is needed |

### The two that matter most

**① The ingress controller is a procurement decision (#5)**

The production IaC uses **NGINX Plus + App Protect**, both of which require commercial licences. If
you stay on OSS ingress-nginx, the WAF must be redesigned (ModSecurity or similar) or dropped from
scope. This is a purchasing decision rather than a technical one, so start on it first.

**② The PostgreSQL major version follows from whether data is migrated (#8)**

The sample runs PG17; the production IaC declares PG12 (on the `spilo-13` image). Migrating
production data means either aligning the versions or planning a `pg_upgrade` / dump-and-restore.
Note that the comment at `51-postgresql-ha.yaml:5` says production is PG13 while the current IaC says
`version: "12"`, so **check the actual version on the production system.**

### Exit criteria
- [ ] All nine items have answers
- [ ] For #5, licensing feasibility and the WAF requirement are settled
- [ ] For #8, the source PostgreSQL version has been confirmed on the real system

---

## Phase 1 — Adopt kustomize without changing behaviour

**Goal**: keep kind working while reshaping the structure to match the production IaC.

### Why this comes first

Without a structure in which values can be substituted, Phase 2 produces a pile of
"copied-for-production" files and the two versions drift apart. **Build the container first.**

### Work

Split into `base` and `overlay/kind`. At this point only **the four items** already known to be
swapped in Phase 2 belong in the overlay:

| # | Item to lift into the overlay | kind value |
|---|---|---|
| 1 | StorageClass names | `standard` / `nfs-static` |
| 2 | Image names, `imagePullPolicy`, `imagePullSecrets` | local build names / `Never` / none |
| 3 | NFS server address | `10.96.0.99` |
| 4 | Ingress hostnames and TLS issuance | `*.localhost` / `weko-ca-issuer` |

Resist the urge to also split namespaces or resize anything. **The value of this phase is that
behaviour does not change.**

### Exit criteria
- [ ] `kubectl kustomize overlay/kind` output is **semantically identical** to the current manifests
- [ ] `overlay/kind` still builds the kind environment and tenants are reachable over HTTPS
- [ ] The four items above can be switched purely from the overlay

---

## Phase 2 — Build the production overlay (replace 🟡 stand-ins)

**Goal**: replace the stand-ins with the real components and **get everything running on a real
cluster**.

### Why this is the crux

The 🟡 entries in [COMPARE-production.en.md](COMPARE-production.en.md) are the ones that look like
they work but do not transfer, and **a single one left in place prevents startup**. Conversely, once
past this phase you can iterate with real feedback.

### Order of work

**2-1. Image supply (nothing starts until this works)**
1. Stand up a registry and push the three images (WEKO / ES / nginx)
2. Delete all four `kind load docker-image` calls
3. Fix all nine `imagePullPolicy: Never` occurrences
4. Add `imagePullSecrets` to every Pod spec

**2-2. Storage**
1. Replace `storageClassName: standard` in all six places
2. **Delete `60-nfs-server.yaml` entirely** and provide external NFS
3. Point `NFS_SERVER` at the real NFS; remove the dependency on `clusterIP: 10.96.0.99`
4. Remove MinIO and point the S3 endpoint at real object storage (rewrite `set-s3-location.sh`)

**2-3. Placement**
1. Apply `nodeType` labels to the nodes (the two-value `WEKO`/`DATA` scheme is fine for now)
2. Remove the privileged initContainer from `13-elasticsearch.yaml` and set the sysctl on the nodes

**2-4. Network and exposure**
1. Install the ingress controller chosen in Phase 0 #5
2. Configure LoadBalancer / MetalLB / external LB
3. Replace `*.localhost` in `tenants.txt` with real FQDNs and configure DNS
4. Delete `61-tls-ca.yaml` and move to real certificate Secrets
5. Rewrite the connectivity check (`deploy-amd64.sh:328-355`) for real FQDNs

**2-5. Safety catches**
1. Change the `FORCE_INIT` default to `no` (or split initialization into its own command)
2. Exclude `teardown-*.sh` from the production directory

### What not to do in this phase
- Namespace splitting (Phase 3)
- Production sizing (Phase 3)
- Monitoring, logging, backup (Phase 4)

**Keep the diff small.** Over-reaching here makes failures impossible to diagnose.

### Exit criteria
- [ ] Every Pod is Running on a **real, non-production Kubernetes cluster** representative of production
- [ ] Tenants are reachable over HTTPS with real FQDNs and real certificates
- [ ] Item registration and search work (proving ES / PG / RabbitMQ / Redis / object storage connectivity)
- [ ] Every 🟡 entry is resolved

---

## Phase 3 — Converge on the production structure (resolve 🔵)

**Goal**: match the structure and scale of the production IaC (`weko-k8s`).

### 3-1. Namespace split ← **the widest blast radius**

Split out `weko3pg` / `weko3es` / `weko3ra`. Every Service FQDN changes as a result
(`elasticsearch` → `elasticsearch.weko3es.svc.cluster.local`, and so on).

Revisit every connection setting `gen-tenant.sh` writes into the ConfigMap.
**Do this as its own step, not mixed with other changes.**

### 3-2. Break out the node-type labels

Go from two values (`WEKO`/`DATA`) to production's eight (`WEKO` `PGO` `PGPOOL` `ES` `RA` `RE` `SE`
`LOG`). At the same time, move from inline `nodeSelector` to production's approach of **injecting
`nodeAffinity` via a kustomize component**.

### 3-3. Unify tenant management

| Option | Approach | Assessment |
|---|---|---|
| **(A) Converge on the production scripts** | Drop `gen-tenant.sh`; use `make_weko_manifests.sh` with `deploy/weko/manifest_template/`, and move tenant definitions to the `repositories_file` format | **Recommended.** The duplicate maintenance burden disappears |
| (B) Extend `gen-tenant.sh` | Widen to the production 20-column format and add memory, uwsgi process count and WAF annotations | Keeps "one command does everything", but a template to keep in sync remains |

The Deployment structures already match almost exactly, so (A) is realistic
(see [COMPARE-production.en.md §6](COMPARE-production.en.md)).

### 3-4. Production sizing

Use the `oci-pr` values as a reference and **recalculate for the real node count and tenant count**.
Copying `oci-pr` verbatim will not fit — it requests 25 CPU and 32Gi for PostgreSQL alone.

At the same time, resolve the pgpool single point of failure (1 → several) and the object-storage SPOF.

### 3-5. Secret management

Move to production's `secret.properties` + `secretFromProperties` generator pattern. Ideally adopt
External Secrets Operator / Sealed Secrets / OCI Vault. **Remove `tenants.txt` from version control.**

### 3-6. The nginx container and TLS hop 2 (per the Phase 0 #9 decision)

Matching production requires all three together:
1. An nginx image containing the Shibboleth SP
2. `server.crt` / `server.key` placed on the shared filesystem
3. `backend-protocol: HTTPS` / `ssl-services` annotations on the Ingress

### Exit criteria
- [ ] Namespaces match production and every Service resolves
- [ ] Node labels follow the production scheme
- [ ] The tenant generation approach is decided and works
- [ ] Sizing has been recalculated for the real layout and passes a load test

---

## Phase 4 — Build the operations layer (add 🔴)

**Goal**: put in place the operational foundation required to run in production.

If the structure matches the production IaC after Phase 3, the corresponding `weko-k8s` directories
are **likely reusable by adding an overlay**.

### Priority

| Priority | Item | Location in the production IaC |
|---|---|---|
| **Highest** | **Backup and restore** | `postgresql/components/{backup_s3,pgdump_s3}`, `elasticsearch/components/backup_s3`, `contents-backup/`, `scripts/restore_*.sh` |
| **Highest** | **Monitoring** | `deploy/monitoring/` (kube-prometheus-stack + ServiceMonitors + alert rules) |
| High | **Log aggregation** | `deploy/logging/` (fluentd → ES → Kibana, Slack notifications) |
| Medium | Maintenance page and maintenance pod | `deploy/maintenance/`, `deploy/maintenance-pod/` |
| Medium | Node maintenance procedures | `scripts/maintenance/` |
| As required | WAF | `ingress/components/ap-config/`, `scripts/waf_management/` |
| As required | Internal ingress | `deploy/ingress-nginx-internal/` |
| Already done | metrics-server (installed in the sample too; required if HPA is used) | `deploy/metrics-server/` |

> **Why backup ranks above monitoring**: monitoring tells you something broke; backup lets you undo
> it. Do not invert the order. **And actually perform a restore.** A backup you cannot restore from
> is no backup at all.

### Deciding on HA hardening (an area production has not covered either)

PDBs, NetworkPolicies and topology spread constraints are **also absent from the production IaC**.
Decide deliberately here whether "as good as production" suffices or whether production should
improve too. If the latter, consider feeding the change back upstream.

### Exit criteria
- [ ] Backups are being taken and **a restore has been demonstrated successfully**
- [ ] Monitoring dashboards and alerts are working
- [ ] Logs are aggregated and searchable
- [ ] Node drain and upgrade procedures are documented and have been exercised

---

## Phase 5 — Prepare to go live

**Goal**: load real data and cut over.

1. **Migration rehearsal** — exercise the migration procedure with production-scale data, accounting for the PostgreSQL version gap (Phase 0 #8)
2. **Load testing** — validate the Phase 3–4 sizing at the expected tenant count and concurrency
3. **Failure testing** — node loss, PostgreSQL failover, pgpool outage behaviour
4. **Cutover rehearsal** — DNS switch and rollback procedure
5. **Operations documentation** — routine operations, incident response, scheduled maintenance

### Exit criteria
- [ ] Migration succeeds with production-scale data
- [ ] The expected load is handled, measured rather than assumed
- [ ] Recovery from the main failure scenarios has been verified
- [ ] A rollback procedure is established

---

## Where rework tends to happen

| Cause of rework | Prevention |
|---|---|
| Starting without Phase 0 | **Settle all nine items first**, especially #5 (ingress procurement) and #8 (PostgreSQL version) |
| Doing Phases 1 and 2 together | Separate structural change from value substitution so failures can be isolated |
| Splitting namespaces during Phase 2 | Defer to Phase 3; keep the diff minimal until it starts |
| Missing a Service FQDN during the namespace split | Enumerate **every** ConfigMap connection setting before starting |
| Copying `oci-pr` sizing verbatim | Recalculate for the real node layout |
| Treating "the backup ran" as done | **Demonstrate a restore** |
| Going live with `FORCE_INIT=yes` | Change the default in Phase 2-5 and split initialization out |

---

## Progress checklist

### Phase 0 — Premises
- [ ] Platform and Kubernetes version decided
- [ ] Block StorageClass and shared-FS backing decided
- [ ] Ingress controller and WAF requirement decided (**procurement**)
- [ ] Exposure method decided
- [ ] Registry decided
- [ ] Data migration and PostgreSQL version confirmed (**checked on the source system**)
- [ ] TLS hop 2 approach decided

### Phase 1 — kustomize
- [ ] Split into `base` / `overlay/kind`
- [ ] The four items are overlay-switchable
- [ ] kind still works as before

### Phase 2 — Replace 🟡 stand-ins
- [ ] Registry push done; all `kind load` calls removed
- [ ] 9 `imagePullPolicy: Never` fixed; `imagePullSecrets` added
- [ ] 6 `storageClassName: standard` replaced
- [ ] `60-nfs-server.yaml` deleted, external NFS in use, hardcoded ClusterIP dependency gone
- [ ] MinIO removed, real object storage in use
- [ ] `nodeType` labels applied
- [ ] Privileged initContainer removed, sysctl set on nodes
- [ ] Ingress controller and exposure path configured
- [ ] Real FQDNs, DNS and real certificates
- [ ] `FORCE_INIT` default changed, `teardown-*.sh` isolated
- [ ] **All Pods Running on a real cluster; item registration and search work**

### Phase 3 — Resolve 🔵 simplifications
- [ ] Namespaces split and Service FQDNs fixed
- [ ] Node labels moved to the eight-value scheme
- [ ] Tenant generation approach decided ((A) or (B))
- [ ] Sizing recalculated
- [ ] Secrets moved to the `secret.properties` pattern; `tenants.txt` untracked
- [ ] nginx / TLS hop 2 approach implemented

### Phase 4 — Build 🔴
- [ ] Backups built and **restore demonstrated**
- [ ] Monitoring and alerting
- [ ] Log aggregation
- [ ] Maintenance procedures
- [ ] HA hardening decision made

### Phase 5 — Go live
- [ ] Migration rehearsal
- [ ] Load testing
- [ ] Failure testing
- [ ] Cutover and rollback procedures

---

## Related documents

| Document | Contents |
|---|---|
| [COMPARE-production.en.md](COMPARE-production.en.md) | Full layer-by-layer difference catalogue |
| [README.en.md](README.en.md) | Overall design of the sample |
| [CONSTRUCTION.en.md](CONSTRUCTION.en.md) | How it was built and the HA design decisions |
| [JAIRO-CLOUD-ARCHITECTURE.en.md](JAIRO-CLOUD-ARCHITECTURE.en.md) | JAIRO Cloud production architecture |
| [k8s-weko-amd64/HTTPS-letsencrypt.en.md](k8s-weko-amd64/HTTPS-letsencrypt.en.md) | Switching to Let's Encrypt |
| `~/weko-k8s` (`RCOSDP/weko-k8s`) | the production IaC itself |
