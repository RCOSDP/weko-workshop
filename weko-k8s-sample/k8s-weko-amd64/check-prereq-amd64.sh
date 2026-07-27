#!/bin/bash
# Decide what to install for the arm64 prerequisites: report OK / needs-install / needs-update for
# each tool, the environment and the kernel settings.
#
# Run:  bash check-prereq-amd64.sh    (no root needed; changes nothing)
#
# Only run sections (a)-(c) of README-amd64.md for the items flagged here. Leave the OK ones alone.
#
# Exit status: 0 = all OK, 1 = action needed (→), 2 = warnings only (△)
set -u

# The default node image of kind v0.30.0. It determines the acceptable kubectl range (+/-1 minor).
NODE_K8S_MINOR="1.34"
KUBECTL_MIN="1.33"; KUBECTL_TOO_NEW="1.36"
DOCKER_MIN="20.10"; KIND_MIN="0.30.0"
RAM_MIN_GI=64; DISK_MIN_GI=100

NEED=0; WARN=0
ver() { printf '%s\n' "$1" | grep -oE '[0-9]+(\.[0-9]+)+' | head -1; }
ge()  { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }
row() {
  printf '  %-20s %-10s %-22s %s\n' "$1" "${2:-none}" "$3" "$4"
  case "$4" in "→"*) NEED=1 ;; "△"*) WARN=1 ;; esac
}

echo "== tools =="
row TOOL CURRENT REQUIRED VERDICT

D=$(ver "$(docker --version 2>/dev/null)")
if   [ -z "$D" ];                             then R="→ install with (a)"
elif ! ge "$D" "$DOCKER_MIN";                 then R="→ update with (a)"
elif ! docker buildx version >/dev/null 2>&1; then R="→ add the buildx plugin"
else R="OK"; fi
row docker "$D" "${DOCKER_MIN}+ and buildx" "$R"

K=$(ver "$(kubectl version --client 2>/dev/null | head -1)")
if   [ -z "$K" ];                 then R="→ install with (b)"
elif ! ge "$K" "$KUBECTL_MIN";    then R="→ update with (b) (too old)"
elif ge "$K" "$KUBECTL_TOO_NEW";  then R="△ 2 minors from node ${NODE_K8S_MINOR}; works but unsupported"
else R="OK"; fi
row kubectl "$K" "${KUBECTL_MIN}-1.35 (node ${NODE_K8S_MINOR})" "$R"

N=$(ver "$(kind version 2>/dev/null)")
if   [ -z "$N" ];          then R="→ install with (b)"
elif ! ge "$N" "$KIND_MIN"; then R="→ update with (b)"
else R="OK"; fi
row kind "$N" "${KIND_MIN}+" "$R"

G=$(ver "$(git --version 2>/dev/null)")
row git "$G" "any" "$([ -n "$G" ] && echo OK || echo '→ install via apt/dnf')"

echo
echo "== environment =="
A=$(uname -m)
row arch "$A" x86_64 "$([ "$A" = x86_64 ] && echo OK || echo '→ wrong arch for this procedure')"
M=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}')
row RAM "${M}Gi" "${RAM_MIN_GI}Gi+" "$(ge "${M:-0}" "$RAM_MIN_GI" && echo OK || echo '△ may be short')"
F=$(df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9')
row disk-free "${F}Gi" "${DISK_MIN_GI}Gi+" "$(ge "${F:-0}" "$DISK_MIN_GI" && echo OK || echo '△ may be short')"
row docker-group "$(id -nG | grep -qw docker && echo yes || echo no)" "docker without sudo" \
    "$(docker info >/dev/null 2>&1 && echo OK || echo '→ end of (a), then re-login')"

echo
echo "== kernel (sysctl) =="
for kv in vm.max_map_count:262144 fs.inotify.max_user_watches:1048576 fs.inotify.max_user_instances:8192; do
  k=${kv%%:*}; need=${kv##*:}; cur=$(sysctl -n "$k" 2>/dev/null)
  row "$k" "$cur" "${need}+" "$(ge "${cur:-0}" "$need" && echo OK || echo '→ run (c)')"
done

echo
if [ "$NEED" = 1 ]; then
  echo "Action needed: run the referenced section of README-amd64.md for each \"→\" item."
  exit 1
elif [ "$WARN" = 1 ]; then
  echo "Warnings only: \"△\" items usually work but are outside the recommended range."
  exit 2
else
  echo "All OK - nothing to install or update."
  exit 0
fi
