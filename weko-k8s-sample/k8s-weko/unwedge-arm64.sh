#!/bin/bash
# Recover kind nodes that can no longer be removed because of a hung NFS mount, and recreate the kind
# network. Must run as root.
#
# Run:  sudo bash unwedge-arm64.sh
#
# When to use it:
#   When teardown-arm64.sh or kind delete cluster fails with:
#     cannot remove container "weko3-worker": could not kill container:
#       tried to kill container, but did not receive an exit event
#
# What is going on:
#   Killing a Pod while it still holds an NFS mount leaves uwsgi/celery stuck in an NFS RPC wait
#   (D state). D state ignores SIGKILL, so the node container cannot be removed and its veth is
#   orphaned on the bridge. The orphan answers ARP for the old IP and breaks the next cluster.
#
# The order matters:
#   detach the mounts -> kill -> remove containers -> remove the network -> delete orphan veths -> recreate
#
# Prevention: always delete with teardown-arm64.sh, which waits for the Pods before removing the cluster.
set -u

[ "$(id -u)" = "0" ] || { echo "ERROR: run as root: sudo bash $0"; exit 1; }
CLUSTER_NAME="${CLUSTER_NAME:-weko3}"
SUBNET="${SUBNET:-172.19.0.0/16}"
hr() { printf '\n===== %s =====\n' "$1"; }

dstate_pids() { ps -eo pid,stat --no-headers | awk '$2 ~ /D/ {print $1}'; }
dstate_count() { dstate_pids | grep -c .; }

hr "1) D-state processes"
ps -eo pid,stat,user,comm,wchan:24 --no-headers | awk '$2 ~ /D/' | sed 's/^/  /'
echo "  count: $(dstate_count)"

hr "2) make the pending RPCs fail fast"
# A hard NFS mount retries forever while the server is unresponsive, keeping the task in D state. The
# server Pod is already gone, so nothing ever answers. Inject a REJECT rule into the container's
# network namespace so the retries fail immediately with an ICMP error; the NFS client then errors out
# and the task leaves D state.
for p in $(dstate_pids); do
  [ -d "/proc/$p" ] || continue
  # After " - " in mountinfo come fstype, source and superopts. An NFS source is <ip>:/<path>.
  for ip in $(awk '{for(i=1;i<=NF;i++) if($i=="-"){print $(i+1), $(i+2)}}' "/proc/$p/mountinfo" 2>/dev/null \
              | awk '$1 ~ /^nfs/ {split($2,a,":"); print a[1]}' | sort -u); do
    [ -n "$ip" ] || continue
    echo "  pid=$p REJECT -> $ip"
    nsenter -t "$p" -n -- iptables -I OUTPUT -d "$ip" -j REJECT --reject-with icmp-port-unreachable \
      2>&1 | sed 's/^/    /'
  done
done

hr "3) repeat the unmount and kill"
# One pass is often not enough because the RPC timeout has to elapse. Retry a bounded number of times.
# Observed: the previous incident still had D-state tasks after pass 1 and was clean after pass 2,
# so a reboot was never needed.
ROUNDS="${ROUNDS:-6}"
for round in $(seq 1 "$ROUNDS"); do
  N=$(dstate_count)
  [ "$N" = "0" ] && { echo "  none left"; break; }
  echo "  -- pass $round/$ROUNDS ($N left) --"
  for p in $(dstate_pids); do
    [ -d "/proc/$p" ] || continue
    for m in $(awk '{for(i=1;i<=NF;i++) if($i=="-"){print $5, $(i+1)}}' "/proc/$p/mountinfo" 2>/dev/null \
               | awk '$2 ~ /^nfs/ {print $1}' | sort -u); do
      # -f first (abort pending RPCs); fall back to -l (lazy detach)
      nsenter -t "$p" -m -- umount -f  "$m" 2>/dev/null \
        || nsenter -t "$p" -m -- umount -f -l "$m" 2>/dev/null
    done
    shim=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
    kill -9 "$p" 2>/dev/null
    [ -n "$shim" ] && [ "$shim" != "1" ] && kill -9 "$shim" 2>/dev/null
  done
  sleep 10
done
echo "  left: $(dstate_count)"

hr "4) force-remove the node containers"
for c in $(docker ps -a --filter "name=^${CLUSTER_NAME}-" --format '{{.Names}}'); do
  echo "  docker rm -f $c"; docker rm -f "$c" 2>&1 | sed 's/^/    /'
done

hr "5) remove the kind network"
# A container that could not be removed keeps the network busy ("has active endpoints"). Disconnect it
# first; that alone already stops the orphan from answering ARP.
for c in $(docker network inspect kind --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null); do
  echo "  docker network disconnect -f kind $c"
  docker network disconnect -f kind "$c" 2>&1 | sed 's/^/    /'
done
docker network rm kind 2>&1 | sed 's/^/  /'

hr "6) delete orphan veths and the bridge"
BR=$(for b in $(ip -o link show type bridge | awk -F': ' '{print $2}'); do
       ip -4 addr show "$b" 2>/dev/null | grep -q "${SUBNET%%/*}" && echo "$b"; done | head -1)
if [ -n "${BR:-}" ]; then
  echo "  bridge=$BR"
  for v in $(ip -o link show master "$BR" 2>/dev/null | awk -F': ' '{print $2}' | cut -d@ -f1); do
    echo "  ip link delete $v"; ip link delete "$v" 2>&1 | sed 's/^/    /'
  done
  ip link delete "$BR" 2>&1 | sed 's/^/    /'
else
  echo "  no matching bridge (already gone)"
fi
ip neigh flush all 2>/dev/null

hr "7) recreate the kind network, IPv4 only"
# kind's default network is dual-stack; recreating right after a delete can collide with IPv6 duplicate
# address detection. Pre-create it IPv4-only (kind reuses an existing kind network).
if docker network inspect kind >/dev/null 2>&1; then
  # The old network is still there because the removal failed. If it is still dual-stack, the next
  # cluster can hit the IPv6 duplicate-address problem.
  echo "  the old kind network is still present:"
  docker network inspect kind --format '    subnet={{range .IPAM.Config}}{{.Subnet}} {{end}}'
  echo "  -> remove the remaining containers, run 'docker network rm kind', then re-run this script"
else
  docker network create kind --subnet "$SUBNET" 2>&1 | sed 's/^/  /'
fi

hr "result"
echo "-- containers --"; docker ps -a --format '  {{.Names}}  {{.Status}}'
echo "-- kind network --"
docker network inspect kind --format '  subnet={{range .IPAM.Config}}{{.Subnet}} {{end}}' 2>&1
LEFT=$(ps -eo stat --no-headers | awk '$1 ~ /^D/' | wc -l)
echo "-- remaining D-state processes: $LEFT --"
ps -eo pid,stat,user,comm,wchan:24 --no-headers | awk '$2 ~ /D/' | sed 's/^/  /'
if [ "$LEFT" -gt 0 ]; then
  cat <<'MSG'

!! D-state tasks remain. Try the following, in order - no reboot required.

  1) Run this script again (most effective).
     The RPC timeouts advance in the meantime; the previous incident cleared on the second run.
       sudo bash unwedge-arm64.sh

  2) Wait a few minutes and repeat 1).
     NFS backs off exponentially, so it can take a while to clear.

  3) Restart containerd/docker - this is NOT a host reboot. It can release the leftover shim so the
     container becomes removable.
       sudo systemctl restart containerd
       sudo systemctl restart docker
     Note: this stops other containers too; check `docker ps` first.

  4) If they still persist, the tasks are waiting on NFS inside the kernel. You can still create a
     new cluster: this script has already removed the orphan veths and recreated the kind network,
     and the stuck tasks consume no CPU. Reboot only if a later deploy actually misbehaves.

MSG
  exit 1
fi
echo
echo "OK: recovered. Next:"
echo "  cd $(dirname "$(readlink -f "$0")") && bash deploy-arm64.sh"
