#!/bin/bash
# Prerequisites for HP ProLiant Gen9 (amd64): Docker / kubectl / kind / kernel parameters / source code
# Run: sudo bash prereq-amd64.sh    (the target user is taken from SUDO_USER)
set -euo pipefail
TARGET_USER="${SUDO_USER:-$USER}"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
# This runs under sudo, so $HOME would be /root; use the target user's home instead.
WEKO_SRC="${WEKO_SRC:-$TARGET_HOME/weko}"
KIND_VER="v0.30.0"

echo "== verify the architecture is amd64 =="
[ "$(uname -m)" = "x86_64" ] || { echo "ERROR: this script is for amd64 (x86_64). current: $(uname -m)"; exit 1; }

echo "== (a) Docker =="
if ! command -v docker >/dev/null; then
  if command -v apt-get >/dev/null; then
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg git
    install -m0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    . /etc/os-release
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  elif command -v dnf >/dev/null; then
    dnf install -y dnf-plugins-core git
    dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  else
    echo "ERROR: neither apt-get nor dnf found; install docker manually"; exit 1
  fi
  systemctl enable --now docker
fi
usermod -aG docker "$TARGET_USER" || true
echo "  docker: $(docker --version)"

echo "== (b) kubectl / kind (amd64) =="
mkdir -p "$TARGET_HOME/.local/bin"
# Pin kubectl to the 1.34 line, matching kind's node image (kindest/node:v1.34.0). Using stable.txt
# (whatever is newest) drifts away from the node and leaves the supported skew of +/-1 minor against
# the API server. The minor is pinned; the patch level still follows the latest release.
KVER=$(curl -sL https://dl.k8s.io/release/stable-1.34.txt)
curl -sLo "$TARGET_HOME/.local/bin/kubectl" "https://dl.k8s.io/release/${KVER}/bin/linux/amd64/kubectl"
curl -sLo "$TARGET_HOME/.local/bin/kind"    "https://kind.sigs.k8s.io/dl/${KIND_VER}/kind-linux-amd64"
chmod +x "$TARGET_HOME/.local/bin/kubectl" "$TARGET_HOME/.local/bin/kind"
chown -R "$TARGET_USER":"$TARGET_USER" "$TARGET_HOME/.local"
grep -q '.local/bin' "$TARGET_HOME/.bashrc" 2>/dev/null || echo 'export PATH=$HOME/.local/bin:$PATH' >> "$TARGET_HOME/.bashrc"

echo "== (c) kernel parameters (for ES and many Pods) =="
cat > /etc/sysctl.d/99-weko.conf <<'EOF'
vm.max_map_count=262144
fs.inotify.max_user_watches=1048576
fs.inotify.max_user_instances=8192
EOF
sysctl --system >/dev/null

echo "== (d) fetch the weko source (used to build WEKO3 and ES) =="
# Both WEKO3 and ES are built from the latest source, so fetch it here (deploy updates it again)
if [ ! -d "$WEKO_SRC/.git" ]; then
  git clone https://github.com/RCOSDP/weko.git "$WEKO_SRC"
else
  git -C "$WEKO_SRC" pull --ff-only || true
fi
chown -R "$TARGET_USER":"$TARGET_USER" "$WEKO_SRC" || true

echo
echo "== done =="
echo "  1) Re-login (or run 'newgrp docker') so the docker group takes effect"
echo "  2) Check that 'docker run --rm hello-world' works without sudo"
echo "  3) Deploy with 'cd k8s-weko-amd64 && bash deploy-amd64.sh' (WEKO_SRC=$WEKO_SRC)"
