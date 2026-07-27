#!/bin/bash
# Safely delete the weko3 cluster.
#
# Why this needs its own script:
#   `kubectl delete deploy` deletes the API objects and returns immediately; Pod termination continues
#   asynchronously. Running `kind delete cluster` before that finishes kills uwsgi/celery while they
#   still hold NFS mounts, leaving them stuck in an NFS RPC wait (D state). D state does not respond to
#   SIGKILL, so the node container can no longer be removed and its veth is orphaned on the bridge.
#   The orphan then answers ARP for the old IP and breaks the next cluster.
#   => Wait until the Pods are really gone before deleting the cluster.
#
# Run: bash teardown-arm64.sh
set -uo pipefail
cd "$(dirname "$0")"
CLUSTER_NAME="${CLUSTER_NAME:-weko3}"
WAIT_SECS="${WAIT_SECS:-300}"

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME"; then
  echo "no such cluster: $CLUSTER_NAME"; exit 0
fi

# When a previous teardown failed halfway, the nodes may linger while the API server is already gone.
# Running kubectl then only produces connection errors, so skip steps 1-3 and go straight to deletion.
if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "== API server unreachable; only deleting =="
else

echo "== 1) delete the Pods that mount NFS =="
# Only the tenant Deployments (web/nginx/worker) mount NFS; the StatefulSets do not.
kubectl delete deploy -n weko3 --all --ignore-not-found 2>&1 | sed 's/^/  /'

echo "== 2) wait until the Pods are actually gone =="
# This is the critical part: delete returns immediately, so poll until the Pods disappear.
for i in $(seq 1 "$((WAIT_SECS / 3))"); do
  LEFT=$(kubectl get pods -n weko3 --no-headers 2>/dev/null | grep -c -- '-web-')
  [ "$LEFT" = "0" ] && break
  [ $((i % 10)) = 1 ] && echo "  $LEFT left"
  sleep 3
done
LEFT=$(kubectl get pods -n weko3 --no-headers 2>/dev/null | grep -c -- '-web-')
if [ "$LEFT" != "0" ]; then
  echo "  WARNING: still $LEFT Pod(s); forcing"
  kubectl delete pod -n weko3 --all --force --grace-period=0 2>&1 | sed 's/^/  /'
  sleep 5
fi
echo "  Pods are gone"

echo "== 3) stop the NFS server =="
# Stop the server only after the clients are gone; the other order hangs the clients.
kubectl delete deploy -n nfs-system --all --ignore-not-found 2>&1 | sed 's/^/  /'
sleep 5

fi   # end of the reachable-API branch

echo "== 4) delete the cluster =="
kind delete cluster --name "$CLUSTER_NAME" 2>&1 | sed 's/^/  /'

echo "== 5) verify the cleanup =="
LEFTC=$(docker ps -a --filter "name=^${CLUSTER_NAME}-" --format '{{.Names}}')
DSTATE=$(ps -eo stat --no-headers | awk '$1 ~ /^D/' | wc -l)
if [ -n "$LEFTC" ] || [ "$DSTATE" != "0" ]; then
  echo "  !! leftover containers: ${LEFTC:-none} / D-state processes: $DSTATE"
  ps -eo pid,stat,user,comm,wchan:24 --no-headers | awk '$2 ~ /D/' | sed 's/^/     /'
  echo
  echo "  !! The teardown wedged. Recover with (needs root):"
  echo
  echo "       sudo bash $(dirname "$(readlink -f "$0")")/unwedge-arm64.sh"
  echo
  echo "  !! Left alone, the orphaned veth answers ARP and breaks the next cluster."
  exit 1
fi
echo "  no leftover containers or D-state processes"
echo "done."
