# Reaching each component with kubectl

Commands for getting into PostgreSQL / Elasticsearch / Redis / RabbitMQ / MinIO / WEKO itself /
the Shibboleth IdP after a deployment. **Every command here was run against a live cluster.**

## Where everything lives

Three namespaces are in play, so getting `-n` right matters.

| Component | Namespace | Kind | Name to address | Containers |
|---|---|---|---|---|
| PostgreSQL (Patroni ×3) | `weko3` | StatefulSet | `weko-postgresql-0` … `-2` | `postgres` |
| pgpool | `weko3` | Deployment | `deploy/weko-pgpool` | `pgpool` |
| Elasticsearch ×3 | `weko3` | StatefulSet | `elasticsearch-0` … `-2` | `elasticsearch` |
| RabbitMQ ×3 | `weko3` | StatefulSet | `weko-rabbitmq-server-0` … `-2` | `rabbitmq` |
| MinIO (S3) | `weko3` | Deployment | `deploy/minio` | `minio` |
| WEKO itself | `weko3` | Deployment | `deploy/tenant1-web` | **`nginx` / `web` / `worker`** |
| Shibboleth IdP | `weko3` | Deployment | `deploy/weko-shib-idp` | `idp` |
| attribute authority (mAP equivalent) | `weko3` | Deployment | `deploy/weko-shib-map` | `idp` |
| Redis (Sentinel) | **`weko3re`** | StatefulSet + Deployment | `redis-0` … `-2` / `deploy/sentinel` | `redis` / `sentinel` |
| NFS server | **`nfs-system`** | Deployment | `deploy/nfs-provisioner` | — |

```bash
kubectl get pods -A | grep -E 'weko|redis|nfs'    # everything at once
```

Addressing `deploy/<name>` picks a Pod of that Deployment automatically, so you never have to look up
the random suffix in `tenant1-web-896748b8d-nc6bq`. StatefulSets (PG / ES / RabbitMQ / Redis) have
stable Pod names you can type directly.

---

## Method 1: `kubectl exec` — use the client inside the Pod

The one you will reach for most; it needs nothing installed locally.

### PostgreSQL

It is a 3-node Patroni cluster, so **look up which node is the master first** — it moves on failover, so
never hardcode the Pod name.

```bash
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master \
        -o jsonpath='{.items[0].metadata.name}')

# interactive shell (the spilo image trusts the in-Pod postgres user, so no password)
kubectl exec -it -n weko3 "$PGM" -- psql -U postgres -d wekodb

# one-liners
kubectl exec -n weko3 "$PGM" -- psql -U postgres -d wekodb -c 'select count(*) from accounts_user;'
kubectl exec -n weko3 "$PGM" -- psql -U postgres -c '\l'
```

The state of the whole cluster (who leads, whether the replicas keep up):

```bash
kubectl exec -n weko3 "$PGM" -- patronictl list
```
```
+ Cluster: weko-postgresql (7667849989161820226) +-----------+----+-----------+
| Member            | Host        | Role         | State     | TL | Lag in MB |
+-------------------+-------------+--------------+-----------+----+-----------+
| weko-postgresql-0 | 10.244.3.6  | Leader       | running   |  1 |           |
| weko-postgresql-1 | 10.244.1.26 | Sync Standby | streaming |  1 |         0 |
| weko-postgresql-2 | 10.244.3.15 | Replica      | streaming |  1 |         0 |
+-------------------+-------------+--------------+-----------+----+-----------+
```

To exercise the **pgpool path** (what WEKO actually uses — connection pooling plus read load balancing)
there is a catch: **the pgpool image has no `psql`**, so connect from a PG Pod with `-h pgpool`:

```bash
kubectl exec -n weko3 weko-postgresql-0 -- \
  sh -c 'PGPASSWORD=weko psql -h pgpool -U weko -d wekodb -c "select current_user"'
```

### Elasticsearch

```bash
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cluster/health?pretty
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cat/indices?v
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cat/nodes?v
```

### Redis (namespace `weko3re`)

```bash
kubectl exec -n weko3re redis-0 -- redis-cli info replication
kubectl exec -n weko3re redis-0 -- redis-cli -n 0 dbsize          # DB 0 = tenant1's CACHE_REDIS_DB
kubectl exec -n weko3re redis-0 -- redis-cli -n 0 keys 'Shib-Session-*'   # the Shibboleth login cache
kubectl exec -n weko3re deploy/sentinel -- redis-cli -p 26379 sentinel masters
```

### RabbitMQ

```bash
kubectl exec -n weko3 weko-rabbitmq-server-0 -- rabbitmqctl list_vhosts
kubectl exec -n weko3 weko-rabbitmq-server-0 -- rabbitmqctl list_queues -p tenant1/
kubectl exec -n weko3 weko-rabbitmq-server-0 -- rabbitmqctl cluster_status
```

### MinIO (S3)

`mc` ships in the image but needs an alias. The credentials are in the environment:

```bash
kubectl exec -n weko3 deploy/minio -- sh -c \
  'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls l'
```
```
[2026-07-29 07:35:02 UTC]     0B weko-backup/
[2026-07-29 07:35:02 UTC]     0B weko-content/
[2026-07-29 07:35:02 UTC]     0B weko-esbackup/
[2026-07-29 07:52:39 UTC]     0B weko-tenant1/
```

Listing a tenant bucket:
```bash
kubectl exec -n weko3 deploy/minio -- sh -c \
  'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls --recursive l/weko-tenant1'
```

### WEKO itself (**three containers, so `-c` is mandatory**)

```bash
kubectl exec -it -n weko3 deploy/tenant1-web -c web    -- bash   # uwsgi / the invenio CLI
kubectl exec -it -n weko3 deploy/tenant1-web -c worker -- bash   # celery
kubectl exec -it -n weko3 deploy/tenant1-web -c nginx  -- bash   # nginx + shibd
```

The `invenio` CLI (from `-c web` or `-c worker`; the PATH has to be set):

```bash
kubectl exec -n weko3 deploy/tenant1-web -c web -- bash -lc \
  'export PATH=/home/invenio/.virtualenvs/invenio/bin:$PATH; invenio --help'
```
```
Commands:
  access                Account commands.
  admin_settings        Settings commands.
  db                    Database commands.
  index                 Manage search indices.
  ...
```

Inspecting the generated configuration:
```bash
kubectl exec -n weko3 deploy/tenant1-web -c web -- \
  tail -20 /home/invenio/.virtualenvs/invenio/var/instance/conf/invenio.cfg
```

Process state inside the nginx container (**this is where you check whether shibd is running**):
```bash
kubectl exec -n weko3 deploy/tenant1-web -c nginx -- supervisorctl -u dummy -p dummy status
```
```
fcgiwrap        RUNNING   pid 17, uptime 0:12:11
nginx           RUNNING   pid 18, uptime 0:12:11
php-fpm         RUNNING   pid 19, uptime 0:12:11
shibauthorizer  RUNNING   pid 20, uptime 0:12:11
shibd           RUNNING   pid 16, uptime 0:12:11
shibresponder   RUNNING   pid 21, uptime 0:12:11
```

### Shibboleth IdP / attribute authority (only with `WEKO_SHIB=yes`)

The attribute authority (`deploy/weko-shib-map`) only exists with `WEKO_SHIB_MAP=aggregation`.
The commands are the same as for the IdP - just swap the Deployment name.

```bash
kubectl exec -n weko3 deploy/weko-shib-idp -- tail -50 /opt/shibboleth-idp/logs/idp-process.log
kubectl exec -n weko3 deploy/weko-shib-idp -- ls /opt/shibboleth-idp/conf/

# check attribute resolution with the IdP's own CLI (IDP_BASE_URL must be set)
kubectl exec -n weko3 deploy/weko-shib-idp -- sh -c \
  'IDP_BASE_URL=http://localhost:8080/idp; export IDP_BASE_URL;
   cd /opt/shibboleth-idp && bash bin/aacli.sh -n admin -r https://tenant1.localhost/shibboleth-sp'

# the attribute authority: did an AttributeQuery arrive from the SP?
kubectl exec -n weko3 deploy/weko-shib-map -- \
  grep "Shibboleth-Audit.AttributeQuery" /opt/shibboleth-idp/logs/idp-process.log | tail -3

# list the users together with their groups (joins the IdP and the WEKO database)
python3 list-shib-users.py

# reload after a config change (no Pod restart needed)
kubectl exec -n weko3 deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp \
     bash bin/reload-service.sh -id shibboleth.AttributeResolverService'
```

### NFS (the shared FS behind the PVs; namespace `nfs-system`)

```bash
kubectl exec -n nfs-system deploy/nfs-provisioner -- ls -l /export
kubectl exec -n nfs-system deploy/nfs-provisioner -- ls -l /export/fs-shibboleth/tenant1
kubectl exec -n nfs-system deploy/nfs-provisioner -- ls -l /export/fs-nginx/tenant1/conf.d
```

---

## Method 2: `port-forward` — connect from local tools or a browser

For GUI clients and management consoles.

```bash
kubectl -n weko3 port-forward svc/pgpool 15432:5432 &
psql -h 127.0.0.1 -p 15432 -U weko -d wekodb        # password: weko
```

| Service | Command | Connect to |
|---|---|---|
| pgpool | `kubectl -n weko3 port-forward svc/pgpool 15432:5432` | `psql -h 127.0.0.1 -p 15432 -U weko -d wekodb` |
| PostgreSQL directly (master) | `kubectl -n weko3 port-forward weko-postgresql-0 15433:5432` | `psql -h 127.0.0.1 -p 15433 -U weko -d wekodb` |
| Elasticsearch | `kubectl -n weko3 port-forward svc/elasticsearch 9200:9200` | `curl localhost:9200/_cat/indices?v` |
| MinIO console | `kubectl -n weko3 port-forward svc/minio 9001:9001` | browser at `http://localhost:9001` |
| RabbitMQ management | `kubectl -n weko3 port-forward svc/weko-rabbitmq 15672:15672` | browser at `http://localhost:15672` |
| Redis | `kubectl -n weko3re port-forward svc/redis 16379:6379` | `redis-cli -p 16379` |
| Shibboleth IdP | `kubectl -n weko3 port-forward svc/weko-shib-idp 8080:8080` | `curl localhost:8080/idp/status` |

> **PostgreSQL is the one entry that addresses a Pod rather than a Service.** postgres-operator manages
> the Endpoints of `svc/weko-postgresql` by hand, so it has no selector and port-forward fails with
> `error: cannot attach to *v1.Service: invalid service 'weko-postgresql': Service is defined without a selector`.
> Look the master Pod up with `-l spilo-role=master` (see above).
>
> Kill a backgrounded port-forward with `kill %1` when you are done.
> If you have no local client, a container will do:
> ```bash
> docker run --rm --network host -e PGPASSWORD=weko postgres:12 \
>   psql -h 127.0.0.1 -p 15432 -U weko -d wekodb
> docker run --rm --network host redis:7.4.1 redis-cli -h 127.0.0.1 -p 16379 ping
> ```

---

## Method 3: get onto a node

kind's nodes are docker containers, so for containerd state or files on the node itself:

```bash
docker exec -it weko3-control-plane bash   # ingress-nginx
docker exec -it weko3-worker bash          # nodeType=WEKO   (weko3 itself)
docker exec -it weko3-worker2 bash         # nodeType=DATA   (PG/ES/Redis/RabbitMQ/NFS/IdP)
```

---

## Credentials

| Target | User | Password | Defined in |
|---|---|---|---|
| PostgreSQL (superuser) | `postgres` | none (trusted inside the Pod) | spilo image default |
| PostgreSQL / pgpool (application) | `weko` | `weko` | `gen-tenant.sh` → Secret `tenant1-secret` |
| RabbitMQ | `weko` | `weko` | same |
| MinIO | `wekominio` | `wekominio-secret-key` | `40-minio.yaml` |
| WEKO administrator | `admin@example.org` | `adminpass123` | `tenants.txt` |
| Shibboleth IdP demo users (institutional) | `admin` / `libadmin` / `teacher` / `commadmin` | `<login id>123` | `shib-idp-build/idp-conf/credentials/demo.htpasswd` |

Reading them straight out of the Secret:

```bash
kubectl -n weko3 get secret tenant1-secret -o jsonpath='{.data.INVENIO_POSTGRESQL_DBPASS}' | base64 -d; echo
kubectl -n weko3 get secret tenant1-secret -o go-template='{{range $k,$v := .data}}{{$k}}={{$v|base64decode}}{{"\n"}}{{end}}'
```

---

## Logs and investigation

```bash
# logs (each container of tenant1-web shows something different)
kubectl -n weko3 logs deploy/tenant1-web -c web    --tail=100   # uwsgi (app request log / tracebacks)
kubectl -n weko3 logs deploy/tenant1-web -c nginx  --tail=100   # nginx access log + shibd
kubectl -n weko3 logs deploy/tenant1-web -c worker --tail=100   # celery
kubectl -n weko3 logs -f deploy/weko-shib-idp                   # IdP (Tomcat stdout)
kubectl -n weko3 logs "$PGM" --tail=100                         # PostgreSQL / Patroni

# the log of the container that just crashed
kubectl -n weko3 logs deploy/tenant1-web -c web --previous

# when a Pod will not start / stays Pending
kubectl -n weko3 describe pod <pod>            # read the Events section
kubectl -n weko3 get events --sort-by=.lastTimestamp

# copy a file out of a Pod (-c required; the tar warning is harmless)
kubectl cp weko3/<pod>:/home/invenio/.virtualenvs/invenio/var/instance/conf/invenio.cfg -c web ./invenio.cfg

# a throwaway Pod for checking connectivity from inside the cluster
kubectl run -n weko3 dbg --rm -i --restart=Never --image=busybox:1.36 -- sh -c \
  'nc -z -w2 pgpool 5432 && echo "pgpool:5432 reachable"; wget -qO- elasticsearch:9200 | head -3'
kubectl run -it --rm dbg -n weko3 --image=busybox:1.36 --restart=Never -- sh   # interactive
```

> `kubectl get events` only keeps about an hour by default, so older incidents are already gone.

### Resource usage (`kubectl top`)

`deploy-*.sh` installs metrics-server in step 3, so this works out of the box.

```bash
kubectl top nodes
kubectl top pods -n weko3
kubectl top pods -n weko3 --containers          # break tenant1-web down per container
kubectl top pods -A --sort-by=memory | head -15 # the biggest memory consumers
```
```
NAME                  CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
weko3-control-plane   99m          0%       1839Mi          1%
weko3-worker          53m          0%       2372Mi          1%
weko3-worker2         104m         0%       7920Mi          6%
```

> Figures take **30-60 seconds after startup** to appear; before that you get
> `error: Metrics API not available`. If they never appear, check
> `kubectl -n kube-system logs deploy/metrics-server`: on kind the kubelet's serving certificate is not
> signed by the cluster CA, so scraping keeps failing without `--kubelet-insecure-tls`
> (which `deploy-*.sh` adds automatically).

---

## Gotchas

- **There are three namespaces** — Redis is in `weko3re`, NFS in `nfs-system`, everything else in
  `weko3`. Getting `-n` wrong just yields `No resources found`, which is easy to misread.
- **`tenant1-web` has three containers** — omitting `-c` prints
  `Defaulted container "nginx" out of: nginx, web, worker` and drops you into nginx. Pass `-c` to
  `exec`, `logs` and `cp` alike.
- **The PostgreSQL master is not fixed** — look it up with `-l spilo-role=master` instead of
  hardcoding a Pod name.
- **The pgpool Pod has no `psql`** — connect from a PG Pod or the web Pod with `-h pgpool`.
- **RabbitMQ and pgpool have init containers** — the informational
  `Defaulted container ... out of: rabbitmq, setup-container (init)` message is fine; the right
  container was chosen.
