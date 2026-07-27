#!/bin/bash
# make-amd64-dist.sh — k8s-weko-amd64 の配布用パッケージ(tar.gz)を作成する
#   Build a distribution tarball of the k8s-weko-amd64 set.
#
# 明示的な許可リスト方式: 配布して良いファイルだけを列挙して固める。
#   generated/ や .secret-seed などの生成物・秘密情報は原理的に混入しない。
# Allowlist-based: only the files listed below are packaged, so runtime/secret
#   artifacts (generated/, .secret-seed, …) can never leak in.
#
# 使い方 / Usage:
#   bash make-amd64-dist.sh                 # 日英 README 同梱の完全版 / full set (JA+EN docs)
#   LANG_ONLY=en bash make-amd64-dist.sh    # 英語 README のみ / EN docs only
#   LANG_ONLY=ja bash make-amd64-dist.sh    # 日本語 README のみ / JA docs only
#   OUT=/path/pkg.tar.gz bash make-amd64-dist.sh   # 出力先を指定 / set output path
set -euo pipefail
cd "$(dirname "$0")"

SRC_DIR="k8s-weko-amd64"          # 固める対象ディレクトリ(アーカイブ内のトップ)
LANG_ONLY="${LANG_ONLY:-both}"    # both | en | ja
OUT="${OUT:-weko-k8s-amd64-dist.tar.gz}"

[ -d "$SRC_DIR" ] || { echo "ERROR: $SRC_DIR がありません / not found (run from repo root)"; exit 1; }

# --- 配布対象(許可リスト) / distribution allowlist ---------------------------
# 実行に必須のスクリプト・マニフェスト・設定
CORE=(
  deploy-amd64.sh
  prereq-amd64.sh
  kind-weko-cluster.yaml
  00-namespace.yaml
  13-elasticsearch.yaml
  21-nginx-config.yaml
  40-minio.yaml
  41-redis-sentinel.yaml
  50-rabbitmq-cluster.yaml
  51-postgresql-ha.yaml
  52-postgres-pod-config.yaml
  60-nfs-server.yaml
  62-pgpool.yaml
  61-tls-ca.yaml
  gen-tenant.sh
  provision-nfs.sh
  provision-tenants.sh
  weko-init.sh
  seed-demo.sh
  set-s3-location.sh
  check-prereq-amd64.sh
  teardown-amd64.sh
  unwedge-amd64.sh
  tenants.txt
)
# 言語別ドキュメント / per-language docs
DOCS_EN=( README-amd64.en.md UNDEPLOY-amd64.en.md HTTPS-letsencrypt.en.md TARGET-deploy1-capacity8-64gb.en.md )
DOCS_JA=( README-amd64.md    UNDEPLOY-amd64.md    HTTPS-letsencrypt.md    TARGET-deploy1-capacity8-64gb.md )

FILES=( "${CORE[@]}" )
case "$LANG_ONLY" in
  both) FILES+=( "${DOCS_EN[@]}" "${DOCS_JA[@]}" ) ;;
  en)   FILES+=( "${DOCS_EN[@]}" ) ;;
  ja)   FILES+=( "${DOCS_JA[@]}" ) ;;
  *) echo "ERROR: LANG_ONLY は both|en|ja / must be both|en|ja"; exit 1 ;;
esac

# --- 存在チェック / verify every listed file exists --------------------------
missing=0
for f in "${FILES[@]}"; do
  [ -f "$SRC_DIR/$f" ] || { echo "MISSING: $SRC_DIR/$f"; missing=1; }
done
[ "$missing" -eq 0 ] || { echo "ERROR: 配布対象ファイルが不足 / some files are missing"; exit 1; }

# --- 秘密ファイル混入ガード / guard against packaging secrets ----------------
for f in "${FILES[@]}"; do
  case "$f" in
    .secret-seed|*/.secret-seed|*secret*|*.key|*.pem)
      echo "ERROR: 秘密の疑いのあるファイルが許可リストに含まれています / suspicious file in list: $f"; exit 1 ;;
  esac
done

# --- tar 作成(アーカイブ内トップを $SRC_DIR/ にする) / build the tarball ------
# パスに $SRC_DIR/ を付けて固めるとアーカイブ展開時に k8s-weko-amd64/ が復元される
PREFIXED=(); for f in "${FILES[@]}"; do PREFIXED+=( "$SRC_DIR/$f" ); done
tar -czf "$OUT" "${PREFIXED[@]}"

# --- 結果表示 / report -------------------------------------------------------
echo "=================================================================="
echo "作成 / created : $OUT"
echo "サイズ / size  : $(du -h "$OUT" | cut -f1)"
echo "言語 / docs    : $LANG_ONLY"
echo "ファイル数     : ${#FILES[@]}"
if command -v sha256sum >/dev/null 2>&1; then
  echo "SHA256         : $(sha256sum "$OUT" | cut -d' ' -f1)"
fi
echo "------------------------------------------------------------------"
echo "同梱内容 / contents:"
tar -tzf "$OUT" | sed 's/^/  /'
echo "=================================================================="
echo "配布メモ / handover notes:"
echo "  - 展開: tar xzf $(basename "$OUT")  → k8s-weko-amd64/ が復元される"
echo "  - 手順: k8s-weko-amd64/README-amd64.en.md を参照(単独で完結)"
echo "  - 生成物(generated/ .secret-seed)は含めていません(相手環境で自動生成)"
