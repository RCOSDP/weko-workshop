#!/bin/bash
# WEKO 本体イメージを weko ソースからビルドして Docker Hub に push する。
# Build the WEKO application image from the weko source and push it to Docker Hub.
# 目的: デプロイで使う WEKO イメージを差し替え可能にする（自前ビルド→Docker Hub登録→WEKO_IMAGEで指定）。
# Purpose: make the WEKO image used at deploy time swappable (build it yourself → publish on Docker
#          Hub → select it with WEKO_IMAGE).
#
# 使い方 / Usage:
#   ./build-push-weko.sh native    [TAG]   # 実行ホストのarchでビルド→ $USER/$REPO:TAG を push（推奨・確実）
#                                          # build for the host arch → push $USER/$REPO:TAG (recommended, reliable)
#   ./build-push-weko.sh multiarch [TAG]   # buildxで amd64+arm64 を1タグ(マルチアーチ)で push（要 binfmt）
#                                          # push amd64+arm64 under one multi-arch tag via buildx (needs binfmt)
#   ./build-push-weko.sh manifest  [TAG]   # 既存の :TAG-amd64 と :TAG-arm64 を束ねて :TAG を作る
#                                          # combine the existing :TAG-amd64 and :TAG-arm64 into :TAG
#
# 環境変数 / Environment variables:
#   DOCKERHUB_USER  Docker Hub ユーザ名           (既定 mhayashi55)
#                   Docker Hub user name          (default mhayashi55)
#   REPO            リポジトリ名                  (既定 weko3-web)
#                   repository name               (default weko3-web)
#   TAG             タグ (第2引数優先)            (既定 latest)
#                   tag (2nd argument wins)       (default latest)
#   WEKO_SRC        weko ソースの場所             (既定 /home/mhaya/weko)
#                   location of the weko source   (default /home/mhaya/weko)
#   DOCKERFILE      使う Dockerfile               (既定 Dockerfile。arm64ホストは Dockerfile.arm64 と同一内容)
#                   Dockerfile to use             (default Dockerfile; on arm64 hosts Dockerfile.arm64 is identical)
#   ARCH_SUFFIX     native時にタグへarch接尾辞を付ける (yes/no。既定 no。manifest運用時は yes)
#                   append the arch suffix to the tag in native mode (yes/no; default no, use yes for manifest mode)
set -euo pipefail

MODE="${1:-native}"
DOCKERHUB_USER="${DOCKERHUB_USER:-mhayashi55}"
REPO="${REPO:-weko3-web}"
TAG="${2:-${TAG:-latest}}"
WEKO_SRC="${WEKO_SRC:-/home/mhaya/weko}"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
ARCH_SUFFIX="${ARCH_SUFFIX:-no}"
IMAGE="${DOCKERHUB_USER}/${REPO}"
HOST_ARCH="$(uname -m)"   # aarch64=arm64 / x86_64=amd64
case "$HOST_ARCH" in aarch64|arm64) GOARCH=arm64;; x86_64|amd64) GOARCH=amd64;; *) GOARCH="$HOST_ARCH";; esac

echo "== WEKO image build/push =="
echo "  image=${IMAGE}:${TAG}  mode=${MODE}  host_arch=${GOARCH}  src=${WEKO_SRC}  dockerfile=${DOCKERFILE}"

# Docker Hub ログイン確認（未ログインなら促す）
# Check the Docker Hub login (prompt when not logged in)
if ! docker system info 2>/dev/null | grep -q "Username:"; then
  echo "-- Docker Hub にログインしてください（トークン推奨） / please log in to Docker Hub (an access token is recommended) --"
  docker login -u "$DOCKERHUB_USER"
fi

case "$MODE" in
  native)
    TAGNAME="${TAG}"; [ "$ARCH_SUFFIX" = "yes" ] && TAGNAME="${TAG}-${GOARCH}"
    echo "-- build (native ${GOARCH}) → ${IMAGE}:${TAGNAME} --"
    docker build -f "${WEKO_SRC}/${DOCKERFILE}" -t "${IMAGE}:${TAGNAME}" "${WEKO_SRC}"
    docker push "${IMAGE}:${TAGNAME}"
    echo "done: ${IMAGE}:${TAGNAME}"
    echo "→ デプロイで使うには / to use it at deploy time: WEKO_IMAGE=${IMAGE}:${TAGNAME} bash gen-tenant.sh (または/or deploy-*.sh)"
    ;;

  multiarch)
    echo "-- buildx multi-arch (linux/amd64,linux/arm64) → ${IMAGE}:${TAG} --"
    echo "   ※ 非ネイティブarchは qemu エミュレーションでビルド（arm64ホストでの amd64 ビルドは低速）。"
    echo "   * Non-native architectures build under qemu emulation (amd64 builds on an arm64 host are slow)."
    docker run --rm --privileged tonistiigi/binfmt --install amd64,arm64 >/dev/null 2>&1 || true
    docker buildx inspect wekobuilder >/dev/null 2>&1 || docker buildx create --name wekobuilder --use
    docker buildx use wekobuilder
    docker buildx build --platform linux/amd64,linux/arm64 \
      -f "${WEKO_SRC}/${DOCKERFILE}" -t "${IMAGE}:${TAG}" --push "${WEKO_SRC}"
    echo "done (multi-arch): ${IMAGE}:${TAG}"
    echo "→ arm64/amd64 どちらのデプロイからも同じ WEKO_IMAGE=${IMAGE}:${TAG} で参照可能"
    echo "→ Both the arm64 and amd64 deployments can use the same WEKO_IMAGE=${IMAGE}:${TAG}"
    ;;

  manifest)
    echo "-- manifest 束ね / combining manifests: ${IMAGE}:${TAG} = ${TAG}-amd64 + ${TAG}-arm64 --"
    echo "   前提: 各archホストで先に 'ARCH_SUFFIX=yes ./build-push-weko.sh native ${TAG}' 実行済み"
    echo "   Prerequisite: 'ARCH_SUFFIX=yes ./build-push-weko.sh native ${TAG}' has already been run on each arch host"
    docker manifest create "${IMAGE}:${TAG}" \
      --amend "${IMAGE}:${TAG}-amd64" --amend "${IMAGE}:${TAG}-arm64"
    docker manifest push "${IMAGE}:${TAG}"
    echo "done (manifest): ${IMAGE}:${TAG}"
    echo "→ arm64/amd64 どちらのデプロイからも同じ WEKO_IMAGE=${IMAGE}:${TAG} で参照可能"
    echo "→ Both the arm64 and amd64 deployments can use the same WEKO_IMAGE=${IMAGE}:${TAG}"
    ;;

  *)
    echo "unknown mode: $MODE (native | multiarch | manifest)"; exit 1;;
esac
