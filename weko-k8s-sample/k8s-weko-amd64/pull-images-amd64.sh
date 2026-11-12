#!/bin/bash
# pull-images-amd64.sh — 配布元のイメージ（自前ビルドしないもの）をホストで先に pull しておく。
#   load を付けると、kind クラスタの全ノードへ読み込む（deploy-amd64.sh が手順1で呼ぶ）。
# pull-images-amd64.sh — pull the third-party images (the ones not built here) on the host ahead of time.
#   With "load", also load them into every node of the kind cluster (deploy-amd64.sh calls this in step 1).
#
# なぜ分けるか: 何もしないと kind のノードがこれらを自分で、しかも匿名で取りに行く。Docker Hub は匿名
#   pull を IP ごとに制限する（6時間で100回）ので、ワークショップ会場のように同じグローバル IP から何人も
#   pull すると、S3 (SeaweedFS) などが ErrImagePull のまま止まり、デプロイが途中の手順で timeout する。
#   ホストで先に pull しておけば、(1) 制限に当たっても deploy の前に分かり、時間をおいて再実行できる。
#   (2) docker login 済みのホストなら認証付きの枠で pull できる。(3) pull 済みは数えずに飛ばすので、
#   再実行しても枠を使わない。
# Why separate: otherwise the kind nodes fetch these themselves, anonymously. Docker Hub rate-limits
#   anonymous pulls per IP (100 per 6 hours), so at a workshop where many people share one public IP,
#   S3 (SeaweedFS) and friends stay in ErrImagePull and the deployment times out halfway. Pulling on the host first
#   means (1) a rate limit shows up before the deploy and you can simply re-run later, (2) a host that ran
#   `docker login` pulls with the authenticated allowance, and (3) images already present are skipped, so
#   a re-run does not spend the allowance again.
#
# 使い方 / Usage:
#   bash pull-images-amd64.sh          # pull だけ（クラスタ不要）。全部 OK になるまで再実行してよい
#                                      # pull only (no cluster needed); re-run until everything is OK
#   bash pull-images-amd64.sh load     # 足りない分を pull して kind クラスタへ読み込む
#                                      # pull what is missing, then load into the kind cluster
#   bash pull-images-amd64.sh list     # 対象イメージの一覧を表示するだけ / just print the image list
# 環境変数 / Environment:
#   CLUSTER_NAME   読み込み先の kind クラスタ名 (default weko3) / the kind cluster to load into
#   PULL_RETRIES   1イメージあたりの pull 試行回数 (default 3) / pull attempts per image
#
# deploy-amd64.sh と同じものを指すこと。マニフェストの URL やイメージを変えたらここも変える。
# Keep this in sync with deploy-amd64.sh: change it here too when a manifest URL or image changes there.
ARCH=amd64
MODE="${1:-pull}"
CLUSTER_NAME="${CLUSTER_NAME:-weko3}"
PULL_RETRIES="${PULL_RETRIES:-3}"
case "$MODE" in pull|load|list) ;; *) echo "usage: bash $0 [pull|load|list]"; exit 2 ;; esac

# kind ノード自体のイメージ（kind v0.30.0 の既定）。ホストの docker が使うので load はしない。
# The kind node image itself (kind v0.30.0's default). The host's docker runs it, so it is not loaded.
KIND_NODE_IMAGE="kindest/node:v1.34.0"
# deploy-amd64.sh が kubectl apply するリモートのマニフェスト。中の image: をその場で読む
# （rabbitmq の operator は latest を指すので、一覧を固定で持つとずれる）。
# Remote manifests deploy-amd64.sh applies. Their image: lines are read on the spot (the rabbitmq operator
# points at "latest", so a fixed list would drift).
MANIFEST_URLS="
https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml
https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml
"
# このディレクトリのマニフェストとスクリプトが使うもの / used by the manifests and scripts here
LOCAL_IMAGES="
ghcr.io/zalando/postgres-operator:v1.14.0
ghcr.io/zalando/spilo-17:4.0-p2
rabbitmq:4.0.9-management
redis:6.2
chrislusf/seaweedfs:4.53
public.ecr.aws/aws-cli/aws-cli:2.40.1
busybox:1.36
registry.k8s.io/sig-storage/nfs-provisioner:v4.0.8
"

# マニフェストの image: を抜き出す。digest（@sha256:...）は落とす: kind へ読み込んだイメージは digest
# では引けないので、deploy-amd64.sh も digest を落としてから apply する（タグで固定されたまま）。
# Extract image: values from a manifest. The digest (@sha256:...) is dropped: an image loaded into kind
# cannot be found by digest, so deploy-amd64.sh drops it before applying too (the tag still pins it).
manifest_images() {
  curl -fsSL "$1" | sed -nE 's/^[[:space:]-]*image:[[:space:]]*"?([^"[:space:]]+)"?.*$/\1/p' \
    | sed -E 's/@sha256:[0-9a-f]+$//'
}

images_to_load() {
  local u out
  for u in $MANIFEST_URLS; do
    out=$(manifest_images "$u") && [ -n "$out" ] \
      || { echo "ERROR: could not read the images from $u" >&2; return 1; }
    echo "$out"
  done
  printf '%s\n' $LOCAL_IMAGES
}

LOAD_LIST=$(images_to_load) || exit 1
LOAD_LIST=$(echo "$LOAD_LIST" | awk 'NF && !seen[$0]++')
ALL_LIST=$(printf '%s\n%s\n' "$KIND_NODE_IMAGE" "$LOAD_LIST")

if [ "$MODE" = "list" ]; then
  echo "$ALL_LIST"; exit 0
fi

# 1) ホストで pull。手元にあるものは pull しない（Docker Hub の枠を使わない）。
# 1) Pull on the host. Anything already present is skipped (no Docker Hub allowance spent).
echo "== pull on the host ($ARCH) =="
failed=""; limited=no
for img in $ALL_LIST; do
  if docker image inspect "$img" >/dev/null 2>&1; then
    printf '  %-70s present\n' "$img"; continue
  fi
  ok=no
  for i in $(seq 1 "$PULL_RETRIES"); do
    if out=$(docker pull --platform "linux/$ARCH" "$img" 2>&1); then ok=yes; break; fi
    echo "$out" | grep -qi 'toomanyrequests\|rate limit' && { limited=yes; break; }   # 再試行しても無駄 / retrying is pointless
    sleep $((i * 10))
  done
  if [ "$ok" = yes ]; then
    printf '  %-70s pulled\n' "$img"
  else
    printf '  %-70s FAILED\n' "$img"
    echo "$out" | tail -2 | sed 's/^/      /'
    failed="$failed $img"
  fi
done
if [ -n "$failed" ]; then
  echo
  echo "ERROR: could not pull:$failed"
  if [ "$limited" = yes ]; then
    echo "  Docker Hub の pull 制限に当たっています。'docker login' するか、時間をおいて再実行してください。"
    echo "  Hit the Docker Hub pull rate limit. Run 'docker login', or wait and re-run this script."
  fi
  echo "  pull 済みのものは再実行で飛ばされます。 / Images already pulled are skipped on a re-run."
  exit 1
fi
[ "$MODE" = "pull" ] && { echo "all images are on the host."; exit 0; }

# 2) kind の全ノードへ読み込む。ノードにすでにあるものは kind が飛ばす。
# 2) Load into every node of the kind cluster. kind skips what a node already has.
echo "== load into the kind cluster $CLUSTER_NAME =="
kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME" \
  || { echo "ERROR: kind cluster $CLUSTER_NAME not found (create it first, or run 'bash deploy-$ARCH.sh')"; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
failed=""
for img in $LOAD_LIST; do
  if kind load docker-image "$img" --name "$CLUSTER_NAME" >"$tmp/log" 2>&1; then
    printf '  %-70s ok\n' "$img"; continue
  fi
  # containerd image store の docker では、他アーキの中身がないマルチアーキイメージを kind load が
  # 読み込めないことがある。自アーキだけを書き出して読み込む。
  # With docker's containerd image store, kind load can fail on a multi-arch image whose other
  # architectures are absent. Export only this architecture and load that archive.
  if docker save --platform "linux/$ARCH" -o "$tmp/img.tar" "$img" 2>>"$tmp/log" \
     && kind load image-archive "$tmp/img.tar" --name "$CLUSTER_NAME" >>"$tmp/log" 2>&1; then
    printf '  %-70s ok (archive)\n' "$img"
  else
    printf '  %-70s FAILED\n' "$img"; tail -3 "$tmp/log" | sed 's/^/      /'
    failed="$failed $img"
  fi
  rm -f "$tmp/img.tar"
done
[ -z "$failed" ] || { echo "ERROR: could not load into $CLUSTER_NAME:$failed"; exit 1; }
echo "all images are loaded into $CLUSTER_NAME."
