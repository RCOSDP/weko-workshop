# The COAR Notify inbox, on Kubernetes

WEKO turns workflow events into COAR Notify messages and POSTs them to an
LDN inbox, reads them back for the person they were addressed to, and
registers Web Push subscriptions with it. The inbox is a separate service
with a MongoDB of its own; the docker-compose stack has both, and a
cluster needs them deployed.

Written against the `repository-ren-ng-web` deployment in namespace
`weko3`: one pod with `nginx`, `web` and `worker` in it, instance
configuration rendered by an init container from
`/conf/instance.cfg`. Change the names to suit another deployment.

## What is here

| | |
| --- | --- |
| `Dockerfile` | the inbox image, to build and push once |
| `mongo.yaml` | MongoDB: a Service and a StatefulSet with a 10Gi volume |
| `inbox.yaml` | the inbox: a ConfigMap, a Service and a Deployment |
| `secret.example.yaml` | the credentials and the VAPID pair, to copy and fill in |
| `nginx-inbox.conf` | the two rules nginx needs, so senders outside can reach it |
| `weko-settings.cfg` | what WEKO needs to know, for the instance configuration |

## Putting it up

**1. Build the image** and push it where the cluster pulls from:

```bash
docker build -t <registry>/weko3-inbox:pre .
docker push    <registry>/weko3-inbox:pre
```

Then set that name in `inbox.yaml`.

**2. The secret.** Copy, fill in, apply -- and keep it out of git:

```bash
cp secret.example.yaml secret.yaml
$EDITOR secret.yaml
kubectl apply -f secret.yaml
```

The password appears twice, in `MONGO_INITDB_ROOT_PASSWORD` and inside
`MONGO_DB_URI`; they have to agree. The VAPID pair may be left empty --
notifications still work, the inbox simply sends no Web Push -- and
`secret.example.yaml` has the command that makes one.

**3. MongoDB and the inbox:**

```bash
kubectl apply -f mongo.yaml
kubectl apply -f inbox.yaml
kubectl -n weko3 rollout status deployment/repository-ren-ng-inbox
```

**4. nginx.** Add the two rules in `nginx-inbox.conf` to the
configuration on the `repository-ren-ng-nginx-pvc` volume, and reload.
Without them WEKO still sends and reads its notifications -- it reaches
the inbox inside the cluster -- but the address it *announces* to the
world answers nothing, which is the half that makes it an LDN inbox.

**5. WEKO.** Add `weko-settings.cfg` to the instance configuration, then:

```bash
kubectl rollout restart deployment/repository-ren-ng-web -n weko3
```

That re-runs the init container, which renders `invenio.cfg` again.

## Checking it

```bash
# The inbox answers in the cluster
kubectl -n weko3 exec deploy/repository-ren-ng-web -c web -- \
    python -c "import urllib.request; print(urllib.request.urlopen(
    'http://repository-ren-ng-inbox:8080/health').status)"

# WEKO announces it to the world
curl -sI https://repository.ren.ng/ | grep -i '^link:'
```

The second should name `.../inbox`, and that URL should answer rather
than 404 -- if it 404s, step 4 did not take.

Then the e2e suite has a `coarnotify` suite that walks the whole loop:

```bash
cd e2e
../.venv-e2e/bin/python -m pytest --suite coarnotify
```

Expect **10 passed, 4 skipped** on a cluster. The four skips are the Web
Push steps: they need a stand-in subscription that only the
docker-compose stack can set up, so they skip with the reason rather than
fail. The other ten check what matters -- that the approval request and
the approval reach the accounts they are meant to.

## What this does not do

- **No replicas.** One inbox, one MongoDB. The inbox holds no state of
  its own, so it would scale; MongoDB here is a single node with a single
  volume, which is what the compose stack has and no more.
- **No backup of the MongoDB volume.** Notifications are not the
  repository's record of anything -- the items and the workflow are in
  PostgreSQL -- but the subscriptions and the read/unread state live
  here, and nothing in these files protects them.
- **`ALLOWED_ORIGINS` is narrower than the compose stack's.** That one
  allows every origin because it is a laptop; `inbox.yaml` names the site
  instead. If registering a Web Push subscription from the notification
  settings screen starts failing in the browser console with a CORS
  error, that is the setting to widen -- it is the one value here that is
  deliberately not what the working stack has.
- **Not verified on a cluster.** These are derived, service by service,
  from the docker-compose definitions that this repository's e2e suite
  runs against, and the YAML parses; but we have no cluster to apply them
  to. Read them before applying them.
