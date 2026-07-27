# Undeploying step by step (arm64 / k8s-weko)

Split out of [Day-to-day operation and teardown](./README-arm64.en.md#day-to-day-operation-and-teardown)
in `README-arm64.en.md`. Read this **only when you want to roll back part of the deployment while
keeping the cluster**.

> **If you want to delete everything, you do not need this document.** Run `bash teardown-arm64.sh`.
> Never call `kind delete cluster` directly: a hung NFS mount then makes the nodes impossible to
> remove (see the first item of the README's troubleshooting section).

## Recovering from a failed deletion (NFS hang -> orphaned veth)
Every teardown problem collapses into this one. **Left alone it breaks the next cluster you create**,
so always deal with it.

**Symptom**: `teardown-arm64.sh` or `kind delete cluster` fails with
```
cannot remove container "weko3-worker": could not kill container:
  tried to kill container, but did not receive an exit event
```

**Recovery** (needs root):
```bash
sudo bash unwedge-arm64.sh
```
It detaches the mounts, kills the processes, removes the containers, removes the network, deletes the
orphaned veths and recreates the network IPv4-only, in that order. **The order matters**: the
containers cannot be removed while the D-state processes are alive, so the mounts have to go first.

**One pass is often not enough. If it prints `D-state tasks remain`, simply run it again.**
The previous incident cleared on the **second run** - no reboot was needed. The RPC timeouts advance
in the meantime, so repeating after a few minutes is effective. If they still persist, use
`sudo systemctl restart containerd && sudo systemctl restart docker`
(this is not a host reboot, but it does stop other containers - check `docker ps` first).

> The orphaned veths are removed and the kind network is recreated before that point, so **you can
> create a new cluster even if D-state processes remain**. They consume no CPU.

### Why it happens
1. Deleting a cluster while Pods still mount NFS leaves `celery`/`uwsgi` in an NFS RPC wait
   (`wchan=rpc_wait_bit_killable`), i.e. **D state**, where `SIGKILL` has no effect.
2. The node container can then no longer be removed, not even with `docker rm -f`.
3. Because the container survives, **its veth stays on the bridge**. That orphan keeps the old IP
   (e.g. `172.19.0.4`), answers ARP for it and collides with the node that gets the same IP next time.
4. Node-to-node traffic breaks and a range of unrelated-looking failures appear at once (see the first
   item of [the README's troubleshooting](./README-arm64.en.md#if-something-goes-wrong)).

### Prevention
**Always delete with `bash teardown-arm64.sh`.**
Running `kubectl delete deploy -n weko3 --all` and then `kind delete cluster` is **not enough**:
`delete deploy` returns immediately while Pod termination continues asynchronously, so deleting the
cluster before that finishes reproduces the same problem. The cluster must only be removed **after the
Pods are confirmed gone**, which is exactly what `teardown-arm64.sh` does.

---

## How to proceed
Work **from the highest step number down**, the reverse of `deploy-arm64.sh`. The steps depend on each
other, so keep the order. Adding `--ignore-not-found` makes the commands safe to re-run.

The range is **8) down to 0)**. Two steps are excluded, for these reasons.

| Step | Why no rollback is needed |
|---|---|
| 9) connectivity check | It only runs `curl`; nothing is created |
| 7.5) seed the demo data | Everything lands in the tenant database and goes with the `DROP DATABASE` in **7)** below |

The examples target tenant `tenant1` (database `wekodb`). The database name is column 2 of `tenants.txt`.

---

## 8) admin_settings seed + the S3 file Location
Remove the per-tenant MinIO bucket.

```bash
kubectl run mc-rm -n weko3 --rm -i --restart=Never --image=minio/mc:RELEASE.2025-04-08T15-39-49Z \
  --command -- /bin/sh -c 'mc alias set l http://minio:9000 wekominio wekominio-secret-key && mc rb --force l/weko-tenant1'
```
> `minio/mc` has `Entrypoint=["mc"]`, so **`--command` is mandatory**. Without it the container runs
> `mc sh -c ...` and fails with `sh is not a recognized command`.

## 7) Tenant initialization (and the 7.5 seed data)
Drop the tenant database. The item types, index tree, workflows and mail templates loaded by 7.5 go
with it.

```bash
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n weko3 $PGM -- psql -U postgres -c "DROP DATABASE wekodb;"
```
> The Elasticsearch indices are separate from the database and survive. No manual step is needed:
> on the next deploy `weko-init.sh` runs `index destroy` and rebuilds them.

## 6) Tenant deployment
The Deployment/Service/Ingress/PVCs, the **cluster-scoped PVs**, and the data on NFS.

```bash
kubectl delete -f generated/tenant1.yaml --ignore-not-found
kubectl delete pv tenant1-config-pv tenant1-data-pv tenant1-shib-pv tenant1-nginx-pv --ignore-not-found
NFS=$(kubectl get pod -n nfs-system -l app=nfs-provisioner -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n nfs-system $NFS -- rm -rf /export/fs-nginx/tenant1 /export/fs-shibboleth/tenant1 \
                                          /export/fs-config/tenant1 /export/fs-data/tenant1
```
> The tenant PVs use `persistentVolumeReclaimPolicy: Retain` and are not namespaced, so
> `kubectl delete ns weko3` does **not** remove them. Leave them behind and they stay `Released`; the
> next deploy cannot bind its PVCs and the web pod sits in `Pending`.
>
> If the tenant is gone for good, delete `generated/tenant1.yaml` as well. Otherwise it stays behind as
> a leftover and is reported with a warning once you remove the tenant from `tenants.txt`.

## 5.5) pgpool
```bash
kubectl delete -f 62-pgpool.yaml --ignore-not-found
```

## The HTTPS root CA (when the default setup was used)
Run this **after** the tenant certificates are gone.

```bash
kubectl delete -f 61-tls-ca.yaml --ignore-not-found   # the two ClusterIssuers and the CA Certificate
```
> ClusterIssuers are cluster-scoped, so `kubectl delete ns` does not remove them. Recreating the CA
> changes the signer, which means any `weko-ca.crt` added to a trust store has to be replaced.

## 5) Pinning the PG weko password
Nothing to roll back (it goes with PostgreSQL).

## 4) Shared platform
Reverse of the apply order. The PVCs go with the namespaces.

```bash
kubectl delete -f 50-rabbitmq-cluster.yaml -f 13-elasticsearch.yaml -f 51-postgresql-ha.yaml \
               -f 60-nfs-server.yaml -f 41-redis-sentinel.yaml -f 40-minio.yaml \
               -f 21-nginx-config.yaml -f 52-postgres-pod-config.yaml --ignore-not-found
kubectl delete ns weko3 weko3re nfs-system --ignore-not-found
kubectl delete storageclass nfs nfs-static --ignore-not-found   # cluster-scoped, so delete separately
```
> Pods still mounting NFS make this hang. Do step 6 first.

## 3) Operators
Only **after** the `postgresql` CR (step 4) is gone; deleting the CRD first orphans the CR.

```bash
for f in postgresteam.crd operatorconfiguration.crd postgresql.crd api-service postgres-operator \
         operator-service-account-rbac configmap; do
  kubectl delete -f https://raw.githubusercontent.com/zalando/postgres-operator/v1.14.0/manifests/$f.yaml --ignore-not-found
done
kubectl delete -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml --ignore-not-found
kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml --ignore-not-found
```

## 2) Images
The copies loaded into the nodes go with the cluster. To remove them from the host:

```bash
docker image rm weko3-web:arm64 weko3-nginx:arm64 weko-elasticsearch:6.8.23-arm64 weko-pgpool:4.2.2-arm64
```

## 1) kind cluster + ingress
The ingress alone, or the whole cluster.

```bash
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
bash teardown-arm64.sh      # to remove the cluster; never use kind delete cluster directly
```

## 0) weko source
The checkout on the host. If nothing else uses it:

```bash
rm -rf "$HOME/weko"    # = $WEKO_SRC (the default)
```
