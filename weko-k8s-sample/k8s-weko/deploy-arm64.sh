#!/bin/bash
# End-to-end deployment script for the "current full configuration" of weko3 on a single arm64 host
#   Result = HA clusters (PG Patroni ×3 / RabbitMQ ×3 / ES ×3) + Redis Sentinel + persistence (PVC)
#            + NFS (RWX) + S3 (MinIO) file Location + multi-tenancy (the production-fidelity final form)
# Design/background: the "HA clustering" section of ../README.md / ../CONSTRUCTION.md.
#                    The amd64 version is ../k8s-weko-amd64/deploy-amd64.sh.
# Prerequisites: arm64 Linux / docker (usable without sudo) / kubectl / kind / the weko source (=$HOME/weko).
#   * Everything is arm64 native, so qemu emulation (binfmt) is not needed.
# WEKO3 is built from the latest source instead of using a prebuilt image (see steps 0 and 2).
#
# Environment variables:
#   WEKO_SRC          location of the weko source                (default $HOME/weko)
#   WEKO_REPO         source repository                          (default https://github.com/RCOSDP/weko.git)
#   WEKO_BRANCH       branch to check out                        (default: the repository default)
#   WEKO_TAG          tag to build (e.g. v2.0.2); no pull, and it is also used as the built image tag
#   WEKO_SRC_UPDATE   update an existing checkout (yes/no)       (default yes)
#   WEKO_IMAGE        set to use a prebuilt image instead of building
#   WEKO_NGINX_IMAGE  same, for the WEKO nginx image
#   WEKO_ES_IMAGE     same, for the Elasticsearch image
#   PGPOOL_IMAGE      same, for the pgpool image
#   WEKO_TLS_ISSUER   ClusterIssuer used to auto-issue the HTTPS certificates (default weko-ca-issuer)
#   WEKO_TLS_SECRET   TLS Secret name (for a manually created certificate)
#   WEKO_SSL_REDIRECT no = do not redirect HTTP to HTTPS
#   CLUSTER_NAME      kind cluster name                          (default weko3)
#   KIND_CONFIG       kind cluster config                        (default ../kind-weko-cluster.yaml)
#   FORCE_INIT        yes = fresh initialization for every tenant (default yes)
#   WEKO_SHIB         yes = also deploy the Shibboleth IdP and enable the WEKO3 Shibboleth login
#                     (default no). See SHIBBOLETH-IDP.md.
#   WEKO_IDP_IMAGE    same as WEKO_IMAGE, for the Shibboleth IdP image
#   WEKO_IDP_HOST     Ingress host of the IdP                    (default idp.localhost)
#   WEKO_SHIB_LOGIN_ONLY yes = make /login itself go to the IdP (Shibboleth-only login)
#                     (default no). Only meaningful together with WEKO_SHIB=yes.
#   WEKO_SHIB_MAP     no|sso|aggregation - how the GakuNin mAP group mapping (isMemberOf)
#                     is reproduced (default no). See SHIBBOLETH-IDP.md.
#   WEKO_MAP_IMAGE    same as WEKO_IMAGE, for the mAP-equivalent attribute authority image
#   WEKO_MAP_HOST     Ingress host of the attribute authority (default map.localhost)
#   WEKO_COAR_NOTIFY  yes = also deploy the COAR Notify (LDN) inbox that weko-notifications posts to
#                     (default no). See COAR-NOTIFY.md.
#   WEKO_INBOX_IMAGE  base image for the inbox                   (default python:3.12-alpine)
set -uo pipefail
cd "$(dirname "$0")"
WEKO_SRC="${WEKO_SRC:-$HOME/weko}"
WEKO_REPO="${WEKO_REPO:-https://github.com/RCOSDP/weko.git}"
WEKO_BRANCH="${WEKO_BRANCH:-}"
# Set this to build a specific release (e.g. WEKO_TAG=v1.0.7). A tag is immutable, so the source is
# never pulled and the build always reproduces that exact code.
WEKO_TAG="${WEKO_TAG:-}"
# Tag used for the images built here (default -> weko3-web:arm64, WEKO_TAG=v1.0.7 -> weko3-web:v1.0.7).
# With WEKO_TAG it follows that tag so images do not collide:
# reusing one name would silently overwrite the previously built image when switching tags.
IMG_TAG="${WEKO_TAG:-arm64}"
WEKO_SRC_UPDATE="${WEKO_SRC_UPDATE:-yes}"
FORCE_INIT="${FORCE_INIT:-yes}"
# HTTPS defaults to automatic issuance by cert-manager with the bundled root CA (61-tls-ca.yaml);
# the value is inherited by gen-tenant.sh. To disable it (back to the ingress-nginx built-in
# self-signed certificate) pass an explicit empty value: WEKO_TLS_ISSUER= bash deploy-arm64.sh
# `-` is used instead of `:-` so that an explicitly empty value really disables it.
export WEKO_TLS_ISSUER="${WEKO_TLS_ISSUER-weko-ca-issuer}"
# WEKO application image. The default is a local build from the latest source. To use a prebuilt image
# (e.g. from Docker Hub), set WEKO_IMAGE=<repo>/<name>:<tag> and it is pulled instead of built.
# The value is inherited by gen-tenant.sh.
export WEKO_IMAGE="${WEKO_IMAGE:-weko3-web:$IMG_TAG}"
# Shibboleth ログインのデモ。yes にすると IdP (70-shibboleth-idp.yaml) を立て、SP 側 (nginx+shibd) と
# WEKO の設定も Shibboleth 有効で生成する。gen-tenant.sh / provision-shib.sh に引き継がれる。
# The Shibboleth login demo. With yes the IdP (70-shibboleth-idp.yaml) is deployed and both the SP side
# (nginx+shibd) and the WEKO configuration are generated with Shibboleth enabled. Inherited by
# gen-tenant.sh / provision-shib.sh.
export WEKO_SHIB="${WEKO_SHIB:-no}"
export WEKO_IDP_HOST="${WEKO_IDP_HOST:-idp.localhost}"
export WEKO_IDP_IMAGE="${WEKO_IDP_IMAGE:-weko3-shib-idp:$IMG_TAG}"
# /login をローカルフォームのままにするか、IdP へ直行させるか (gen-tenant.sh が読む)。
# Whether /login keeps the local form or goes straight to the IdP (read by gen-tenant.sh).
export WEKO_SHIB_LOGIN_ONLY="${WEKO_SHIB_LOGIN_ONLY:-no}"
# 学認mAP 連携 (isMemberOf) の再現方法。gen-tenant.sh と provision-shib.sh の両方が読む。
# How the GakuNin mAP integration (isMemberOf) is reproduced; read by both gen-tenant.sh
# and provision-shib.sh.
export WEKO_SHIB_MAP="${WEKO_SHIB_MAP:-no}"
# 属性認証局 (学認mAP 相当)。WEKO_SHIB_MAP=aggregation のときだけ立てる。
# The attribute authority (GakuNin mAP equivalent); only deployed with WEKO_SHIB_MAP=aggregation.
export WEKO_MAP_HOST="${WEKO_MAP_HOST:-map.localhost}"
export WEKO_MAP_IMAGE="${WEKO_MAP_IMAGE:-weko3-shib-map:$IMG_TAG}"
# COAR Notify のデモ。yes にすると LDN の inbox (72-coar-notify-inbox.yaml) を立てる。
# WEKO3 の weko-notifications は「送信」と「閲覧」しか持たず inbox 本体は外部サービスなので、
# 既定の宛先 http://inbox:8080/inbox に一致する Service をクラスタ内に用意する、というだけ。
#
# no (既定) のときの挙動は従来どおり: 通知の送信は試みられるが接続に失敗し、weko-workflow の
# _notify_about_activity_wiht_case が Exception を握ってログに残すだけでワークフローは通る。
#
# The COAR Notify demo. With yes the LDN inbox (72-coar-notify-inbox.yaml) is deployed.
# weko-notifications only implements the sending and reading sides - the inbox itself is an external
# service - so this simply provides a Service inside the cluster matching its default target
# http://inbox:8080/inbox.
#
# With no (the default) nothing changes from before: sending is attempted, the connection fails, and
# weko-workflow's _notify_about_activity_wiht_case swallows the exception and logs it, so the
# workflow itself still completes.
export WEKO_COAR_NOTIFY="${WEKO_COAR_NOTIFY:-no}"
# inbox のベースイメージ。inbox.py は Python 標準ライブラリだけで動くので、素の python イメージでよい。
# The inbox base image. inbox.py only uses the Python standard library, so a stock python image is enough.
export WEKO_INBOX_IMAGE="${WEKO_INBOX_IMAGE:-python:3.12-alpine}"
KIND_CONFIG="${KIND_CONFIG:-../kind-weko-cluster.yaml}"
# kind cluster name (default weko3; override it e.g. for a parallel verification run)
CLUSTER_NAME="${CLUSTER_NAME:-weko3}"
SPILO_IMAGE="ghcr.io/zalando/spilo-17:4.0-p2"          # arm64-native spilo-17 (PG17)
PGOP_IMAGE="ghcr.io/zalando/postgres-operator:v1.14.0"  # arm64-capable operator

echo "########## 0) fetch or update the latest weko source ##########"
# WEKO_TAG selects an immutable tag, WEKO_BRANCH a moving branch; the tag wins if both are set.
# Checking out a tag leaves a detached HEAD, so `git pull` must not run (it would always fail).
if [ -n "$WEKO_TAG" ] && [ -n "$WEKO_BRANCH" ]; then
  echo "-- WEKO_TAG=$WEKO_TAG wins; WEKO_BRANCH=$WEKO_BRANCH ignored --"
fi
if [ ! -d "$WEKO_SRC/.git" ]; then
  if [ -d "$WEKO_SRC" ] && [ -n "$(ls -A "$WEKO_SRC" 2>/dev/null)" ]; then
    echo "-- $WEKO_SRC is not a git checkout, using as-is --"
  else
    # `git clone -b` accepts either a branch or a tag name (a tag yields a detached HEAD)
    CLONE_REF="${WEKO_TAG:-$WEKO_BRANCH}"
    git clone ${CLONE_REF:+-b "$CLONE_REF"} "$WEKO_REPO" "$WEKO_SRC" \
      || { echo "ERROR: clone failed (ref=${CLONE_REF:-default})"; exit 1; }
  fi
elif [ "$WEKO_SRC_UPDATE" = "yes" ]; then
  # Fetch tags explicitly; --all alone does not always bring in newly created tags
  git -C "$WEKO_SRC" fetch --all --prune --tags
  if [ -n "$WEKO_TAG" ]; then
    # Verify first: checking out a missing ref makes git treat it as a path and emit the
    # confusing "--detach does not take a path argument" message.
    if ! git -C "$WEKO_SRC" rev-parse -q --verify "refs/tags/$WEKO_TAG^{commit}" >/dev/null; then
      echo "ERROR: tag '$WEKO_TAG' not found. Recent tags:"
      git -C "$WEKO_SRC" tag --sort=-creatordate | head -10 | sed 's/^/  /'
      exit 1
    fi
    git -C "$WEKO_SRC" checkout --detach "refs/tags/$WEKO_TAG" || exit 1
    echo "-- checked out tag $WEKO_TAG (detached); no pull --"
  else
    [ -n "$WEKO_BRANCH" ] && { git -C "$WEKO_SRC" checkout "$WEKO_BRANCH" \
      || { echo "ERROR: branch $WEKO_BRANCH not found"; exit 1; }; }
    git -C "$WEKO_SRC" pull --ff-only || echo "-- pull skipped (local changes) --"
  fi
fi
git -C "$WEKO_SRC" submodule update --init --recursive 2>/dev/null || true
echo "-- source: $(git -C "$WEKO_SRC" log -1 --oneline 2>/dev/null || echo "$WEKO_SRC (no git)") --"
# Use the arm64-specific Dockerfile when present, otherwise the normal one (identical content)
WEKO_DOCKERFILE="$WEKO_SRC/Dockerfile.arm64"; [ -f "$WEKO_DOCKERFILE" ] || WEKO_DOCKERFILE="$WEKO_SRC/Dockerfile"
ES_DOCKERFILE="$WEKO_SRC/elasticsearch/Dockerfile.arm64"; [ -f "$ES_DOCKERFILE" ] || ES_DOCKERFILE="$WEKO_SRC/elasticsearch/Dockerfile"

echo "########## 1) kind cluster + Ingress (arm64 native, no binfmt) ##########"
# kind cluster creation fails intermittently (the workers cannot join the control-plane API and report
# "dial tcp <cp-ip>:6443: connect: connection refused"). One cause is recreating right after a delete:
# the docker network reassigns addresses before they are released, colliding with IPv6 duplicate
# address detection. So retry. And abort on failure — without this gate every later step runs against
# a missing cluster and the real cause is buried under "no nodes found" /
# "localhost:8080 connection refused" noise.
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER_NAME" \
   && kubectl --context "kind-$CLUSTER_NAME" cluster-info >/dev/null 2>&1; then
  echo "-- reusing the existing cluster $CLUSTER_NAME --"
  kubectl config use-context "kind-$CLUSTER_NAME" >/dev/null
else
  for attempt in 1 2 3; do
    kind create cluster --config "$KIND_CONFIG" --name "$CLUSTER_NAME" --wait 120s && break
    echo "-- creation failed (attempt $attempt/3); cleaning up and retrying --"
    kind delete cluster --name "$CLUSTER_NAME" >/dev/null 2>&1
    sleep 10   # let docker release the addresses
    if [ "$attempt" = 3 ]; then
      echo "ERROR: cannot create the kind cluster"; exit 1
    fi
  done
fi
kubectl cluster-info >/dev/null 2>&1 || {
  echo "ERROR: cannot reach the cluster"; exit 1; }
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
kubectl wait -n ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=180s

echo "########## 2) build arm64-native images from the source ##########"
# weko application: built from the latest source. Only when WEKO_IMAGE names a prebuilt image is it pulled.
if [ "$WEKO_IMAGE" = "weko3-web:$IMG_TAG" ]; then
  docker build -f "$WEKO_DOCKERFILE" -t "$WEKO_IMAGE" "$WEKO_SRC"
else
  echo "-- pulling WEKO_IMAGE=$WEKO_IMAGE (skipping the source build) --"
  docker pull "$WEKO_IMAGE"
fi
kind load docker-image "$WEKO_IMAGE" --name "$CLUSTER_NAME"
# Elasticsearch: arm64 native (real kui.txt / kuromoji / repository-s3 pointing at MinIO)
export WEKO_ES_IMAGE="${WEKO_ES_IMAGE:-weko-elasticsearch:6.8.23-$IMG_TAG}"
if [ "$WEKO_ES_IMAGE" = "weko-elasticsearch:6.8.23-$IMG_TAG" ]; then
  docker build -f "$ES_DOCKERFILE" \
    --build-arg ELASTICSEARCH_S3_ACCESS_KEY=wekominio \
    --build-arg ELASTICSEARCH_S3_SECRET_KEY=wekominio-secret-key \
    --build-arg ELASTICSEARCH_S3_ENDPOINT=http://minio:9000 \
    --build-arg ELASTICSEARCH_S3_BUCKET=weko-esbackup \
    -t "$WEKO_ES_IMAGE" "$WEKO_SRC"
else
  # A prebuilt image must already have the repository-s3 keystore baked in (the --build-arg values
  # above); otherwise ES snapshots cannot use MinIO.
  echo "-- pulling WEKO_ES_IMAGE=$WEKO_ES_IMAGE (skipping the source build) --"
  docker pull "$WEKO_ES_IMAGE"
fi
kind load docker-image "$WEKO_ES_IMAGE" --name "$CLUSTER_NAME"
# The WEKO nginx: built from the weko source with the Shibboleth SP (shibd + the nginx-http-shibboleth
# module). nginx/Dockerfile hardcodes the .deb architecture, so it is rewritten for this host first.
export WEKO_NGINX_IMAGE="${WEKO_NGINX_IMAGE:-weko3-nginx:$IMG_TAG}"
if [ "$WEKO_NGINX_IMAGE" = "weko3-nginx:$IMG_TAG" ]; then
  NGINX_DF="$(mktemp -d)/Dockerfile.nginx"
  sed "s/focal_arm64\.deb/focal_arm64.deb/g; s/focal_amd64\.deb/focal_arm64.deb/g" \
    "$WEKO_SRC/nginx/Dockerfile" > "$NGINX_DF"
  # supervisord.conf hardcodes the x86_64 paths of shibauthorizer/shibresponder; rewrite them for arm64
  printf 'RUN sed -i "s#/usr/lib/x86_64-linux-gnu/shibboleth#/usr/lib/aarch64-linux-gnu/shibboleth#g" /etc/supervisor/supervisord.conf\n' >> "$NGINX_DF"
  # weko/nginx/Dockerfile は login.php しか入れず fcgiwrap も入れないが、weko-accounts が実際に
  # 使うのは /secure/login.py の方 (AdminSettings の attribute_mapping が eppn/mail/DisplayName/
  # HTTP_WEKOSOCIETYAFFILIATION というフィールド名を要求するため、SHIB_ATTR_* を送る login.php では
  # 属性が空になる)。supervisord.conf には fcgiwrap の定義が既にあるので、実体と login.py を足す。
  # weko/nginx/Dockerfile only ships login.php and does not install fcgiwrap, but what weko-accounts
  # actually uses is /secure/login.py (AdminSettings' attribute_mapping asks for the field names
  # eppn/mail/DisplayName/HTTP_WEKOSOCIETYAFFILIATION, so login.php - which posts SHIB_ATTR_* - yields
  # empty attributes). supervisord.conf already defines the fcgiwrap program, so add the binary and
  # login.py to match.
  {
    printf 'RUN apt-get update && apt-get install -y fcgiwrap python3-requests && rm -rf /var/lib/apt/lists/*\n'
    printf 'RUN mkdir -p /usr/lib/systemd/system\n'
    printf 'ADD ./login.py /usr/share/nginx/html/secure/login.py\n'
    printf 'RUN chmod 755 /usr/share/nginx/html/secure/login.py\n'
    # login.py はステータス行を "HTTP/1.1 302 Found" として出力するが、これは NPH スクリプトの書式で、
    # fcgiwrap 経由では単なる不正なヘッダ行になり nginx が 502 を返す。CGI 本来の "Status:" に直す。
    # login.py emits its status line as "HTTP/1.1 302 Found", which is the NPH-script form; through
    # fcgiwrap it is just a malformed header line and nginx answers 502. Rewrite it to CGI's "Status:".
    printf 'RUN sed -i "s#%s#%s#; s#%s#%s#" /usr/share/nginx/html/secure/login.py\n' \
      "print('HTTP/1.1 302 Found')" "print('Status: 302 Found')" \
      "print('HTTP/1.1 200 OK')"    "print('Status: 200 OK')"
  } >> "$NGINX_DF"
  docker build -f "$NGINX_DF" -t "$WEKO_NGINX_IMAGE" "$WEKO_SRC/nginx"
else
  echo "-- pulling WEKO_NGINX_IMAGE=$WEKO_NGINX_IMAGE --"
  docker pull "$WEKO_NGINX_IMAGE"
fi
kind load docker-image "$WEKO_NGINX_IMAGE" --name "$CLUSTER_NAME"
# pgpool: the official pgpool/pgpool is amd64-only → build the arm64-native image from pgpool-build/
export PGPOOL_IMAGE="${PGPOOL_IMAGE:-weko-pgpool:4.2.2-arm64}"
if [ "$PGPOOL_IMAGE" = "weko-pgpool:4.2.2-arm64" ]; then
  docker build -f pgpool-build/Dockerfile.arm64 -t "$PGPOOL_IMAGE" pgpool-build
else
  echo "-- pulling PGPOOL_IMAGE=$PGPOOL_IMAGE --"
  docker pull "$PGPOOL_IMAGE"
fi
kind load docker-image "$PGPOOL_IMAGE" --name "$CLUSTER_NAME"
# Shibboleth IdP: 公式 tarball (純 Java) + Tomcat 10.1 から自前ビルドするのでアーキ非依存。
# WEKO_SHIB=yes のときだけ作る (ビルドに数分かかるため)。
# Shibboleth IdP: built from the official tarball (pure Java) + Tomcat 10.1, so it is arch independent.
# Only built with WEKO_SHIB=yes (the build takes a few minutes).
if [ "$WEKO_SHIB" = "yes" ]; then
  # aggregation のときは isMemberOf を SSO で配らない (属性認証局から取らせるため)。
  # With aggregation, the institutional IdP does not hand out isMemberOf over SSO - the attribute
  # authority supplies it instead.
  if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then IDP_ISMEMBEROF=no; else IDP_ISMEMBEROF=yes; fi
  if [ "$WEKO_IDP_IMAGE" = "weko3-shib-idp:$IMG_TAG" ]; then
    docker build \
      --build-arg IDP_HOST="$WEKO_IDP_HOST" \
      --build-arg IDP_ENTITYID="https://$WEKO_IDP_HOST/idp/shibboleth" \
      --build-arg IDP_RELEASE_ISMEMBEROF="$IDP_ISMEMBEROF" \
      -t "$WEKO_IDP_IMAGE" shib-idp-build || { echo "ERROR: failed to build the Shibboleth IdP image"; exit 1; }
  else
    echo "-- pulling WEKO_IDP_IMAGE=$WEKO_IDP_IMAGE --"
    docker pull "$WEKO_IDP_IMAGE"
  fi
  kind load docker-image "$WEKO_IDP_IMAGE" --name "$CLUSTER_NAME"
  # 属性認証局。同じイメージだが entityID が別で、グループ名には機関 IdP の FQDN を埋める。
  # The attribute authority: same image, a different entityID, and the institutional IdP's FQDN baked
  # into the group names.
  if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then
    if [ "$WEKO_MAP_IMAGE" = "weko3-shib-map:$IMG_TAG" ]; then
      docker build \
        --build-arg IDP_HOST="$WEKO_MAP_HOST" \
        --build-arg IDP_ENTITYID="https://$WEKO_MAP_HOST/idp/shibboleth" \
        --build-arg IDP_GROUP_FQDN_HOST="$WEKO_IDP_HOST" \
        -t "$WEKO_MAP_IMAGE" shib-idp-build || { echo "ERROR: failed to build the attribute authority image"; exit 1; }
    else
      echo "-- pulling WEKO_MAP_IMAGE=$WEKO_MAP_IMAGE --"
      docker pull "$WEKO_MAP_IMAGE"
    fi
    kind load docker-image "$WEKO_MAP_IMAGE" --name "$CLUSTER_NAME"
  fi
fi
# COAR Notify の inbox はビルド不要 (素の python イメージ + ConfigMap の inbox.py)。
# The COAR Notify inbox needs no build: a stock python image plus inbox.py from a ConfigMap.
if [ "$WEKO_COAR_NOTIFY" = "yes" ]; then
  echo "-- pulling WEKO_INBOX_IMAGE=$WEKO_INBOX_IMAGE --"
  docker pull "$WEKO_INBOX_IMAGE"
  kind load docker-image "$WEKO_INBOX_IMAGE" --name "$CLUSTER_NAME"
fi

echo "########## 3) operators (cert-manager / rabbitmq / postgres) ##########"
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
# metrics-server: kubectl top を使えるようにする。kind の kubelet はクラスタ CA が署名していない
# サービング証明書を使うので、--kubelet-insecure-tls を足さないと収集に失敗し続ける
# ("Metrics API not available" のまま)。マルチアーキイメージなので arm64/amd64 とも同じもので動く。
# metrics-server, so that kubectl top works. kind's kubelet serves a certificate that the cluster CA did
# not sign, so without --kubelet-insecure-tls scraping keeps failing and kubectl top stays stuck on
# "Metrics API not available". The image is multi-arch, so the same one works on arm64 and amd64.
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml
kubectl -n kube-system patch deploy metrics-server --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' \
  >/dev/null 2>&1 || echo "WARNING: could not patch metrics-server (kubectl top may not work)"
kubectl wait -n cert-manager --for=condition=ready pod --all --timeout=180s
kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml
# Applying the RabbitmqCluster before the operator's webhook is up fails the webhook call, so wait for it
kubectl -n rabbitmq-system rollout status deploy/rabbitmq-cluster-operator --timeout=300s
# Zalando postgres-operator: apply the upstream manifests → pin to the arm64 images
base="https://raw.githubusercontent.com/zalando/postgres-operator/v1.14.0/manifests"
for f in configmap operator-service-account-rbac postgres-operator api-service \
         postgresql.crd operatorconfiguration.crd postgresteam.crd; do
  # On a re-run the operator owns .spec.versions of the postgresqls CRD, so a plain --server-side apply
  # fails with "Apply failed with 1 conflict" and the CRD is left un-updated. Take ownership.
  kubectl apply --server-side --force-conflicts -f "$base/$f.yaml"
done
# arm64: registry.opensource.zalan.do is amd64 only → pin operator/spilo to ghcr.io/zalando (arm64)
kubectl set image deployment/postgres-operator postgres-operator=$PGOP_IMAGE -n default 2>/dev/null || true
# pin docker_image to the arm64 spilo + point pod_environment_configmap at the ALLOW_NOSSL configmap (for pgpool)
kubectl patch configmap postgres-operator -n default --type merge \
  -p "{\"data\":{\"docker_image\":\"$SPILO_IMAGE\",\"pod_environment_configmap\":\"weko3/postgres-pod-config\"}}"
kubectl rollout restart deployment/postgres-operator -n default
kubectl wait -n default --for=condition=ready pod -l name=postgres-operator --timeout=180s

echo "########## 4) deploy the shared platform (HA/persistence/NFS/S3) ##########"
# Apply 52 (ALLOW_NOSSL configmap) BEFORE 51 (the postgresql CR) so the operator injects the env at PG pod creation.
kubectl apply -f 00-namespace.yaml -f 52-postgres-pod-config.yaml -f 21-nginx-config.yaml \
              -f 40-minio.yaml -f 41-redis-sentinel.yaml -f 60-nfs-server.yaml \
              -f 51-postgresql-ha.yaml
# Deploy the bundled root CA (61-tls-ca.yaml) when automatic issuance uses it. If WEKO_TLS_ISSUER
# names a different ClusterIssuer, skip it - that issuer is expected to exist already.
if [ "$WEKO_TLS_ISSUER" = "weko-ca-issuer" ]; then
  kubectl apply -f 61-tls-ca.yaml
  kubectl wait --for=condition=ready clusterissuer/weko-ca-issuer --timeout=120s \
    || echo "WARNING: weko-ca-issuer did not become ready"
fi
# Elasticsearch can be overridden with WEKO_ES_IMAGE, so substitute the image in the manifest before
# applying it, the same way pgpool is handled.
# The manifest hardcodes the image, so always substitute the image actually in use before applying.
# It is a no-op when they match. With WEKO_TAG the built name changes, and without this the manifest
# would still point at the old name and the pod would end up in ImagePullBackOff.
sed "s#image: weko-elasticsearch:6.8.23-arm64#image: $WEKO_ES_IMAGE#" 13-elasticsearch.yaml \
  | kubectl apply -f -
# the RabbitmqCluster goes through a webhook, so retry on failure
for i in 1 2 3 4 5 6; do kubectl apply -f 50-rabbitmq-cluster.yaml && break || sleep 10; done
echo "-- waiting until ready --"
kubectl -n weko3 wait --for=condition=ready pod -l app=elasticsearch --timeout=300s
kubectl -n weko3 wait --for=condition=ready pod -l app.kubernetes.io/name=weko-rabbitmq --timeout=300s
kubectl -n weko3re wait --for=condition=ready pod -l app=redis --timeout=180s
# Always cap the wait: an unbounded loop hangs forever when the cluster is broken.
pg_ready() { kubectl get pods -n weko3 -l cluster-name=weko-postgresql,application=spilo --no-headers 2>/dev/null | grep -c '1/1'; }
for _ in $(seq 1 75); do [ "$(pg_ready)" -ge 3 ] && break; sleep 8; done
if [ "$(pg_ready)" -lt 3 ]; then
  echo "ERROR: the three PG Patroni nodes did not come up"
  kubectl get pods -n weko3 -l cluster-name=weko-postgresql,application=spilo
  exit 1
fi
# minio/mc has Entrypoint=["mc"], so `-- sh -c ...` without --command is passed as args and runs
# `mc sh -c ...`, failing with "sh is not a recognized command". Use --command to override the entrypoint.
kubectl run mc-init -n weko3 --rm -i --restart=Never --image=minio/mc:RELEASE.2025-04-08T15-39-49Z \
  --command -- /bin/sh -c 'mc alias set l http://minio:9000 wekominio wekominio-secret-key && mc mb -p l/weko-backup l/weko-content l/weko-esbackup' \
  || echo "WARNING: failed to create the shared buckets"

echo "########## 5) pin the PostgreSQL weko password ##########"
# The operator resets the weko password to a generated value, so pin it back to 'weko'
kubectl patch secret -n weko3 weko.weko-postgresql.credentials.postgresql.acid.zalan.do \
  -p "{\"data\":{\"password\":\"$(echo -n weko | base64)\"}}"
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n weko3 "$PGM" -- psql -U postgres -c "ALTER ROLE weko WITH PASSWORD 'weko';"

echo "########## 5.5) pgpool (pooling + read load-balancing) ##########"
# Deploy pgpool AFTER the password is pinned (pgpool imports the Secret password into pool_passwd at startup)
if [ "$PGPOOL_IMAGE" = "weko-pgpool:4.2.2-arm64" ]; then
  kubectl apply -f 62-pgpool.yaml
else
  sed "s#image: weko-pgpool:4.2.2-arm64#image: $PGPOOL_IMAGE#" 62-pgpool.yaml | kubectl apply -f -
fi
kubectl -n weko3 rollout status deploy/weko-pgpool --timeout=180s
# `rollout status` only proves the readinessProbe passed, and that probe is a bare tcpSocket check on
# 5432 - pgpool accepts TCP well before its backend connections are usable. Step 7's first statement
# then dies with "FATAL: unable to read data from DB node 0 / DETAIL: EOF encountered with backend".
# Gate on a real query instead. Three in a row, because load balancing spreads them over both backends
# and a single one could be answered by the primary while the replica is still unusable.
# Non-fatal: step 7 reports a far clearer error than this loop can if pgpool is genuinely broken.
echo "-- waiting until a query goes through pgpool --"
PGPOOL_OK=no
for _ in $(seq 1 30); do
  if kubectl exec -n weko3 "$PGM" -- sh -c \
       'for _ in 1 2 3; do PGPASSWORD=weko psql -h pgpool -U weko -d postgres -tAc "SELECT 1" >/dev/null || exit 1; done' \
       >/dev/null 2>&1; then
    PGPOOL_OK=yes; break
  fi
  sleep 5
done
[ "$PGPOOL_OK" = yes ] && echo "   pgpool is answering queries" \
  || echo "WARNING: pgpool did not answer a query within 150s, continuing anyway"

echo "########## 6) generate, deploy and provision tenants ##########"
bash gen-tenant.sh
# Create the per-tenant directories (/fs-nginx /fs-shibboleth /fs-config /fs-data) on the shared FS and
# seed the nginx / Shibboleth templates. Required before the Pods mount them (= production's make_volumes.sh)
bash provision-nfs.sh
# Shibboleth: SP 鍵の生成、IdP メタデータの取り出し、SP メタデータ (ConfigMap) の登録、
# 各テナントの /fs-shibboleth への配置。Pod が /etc/shibboleth をマウントする前に済ませる必要がある。
# Shibboleth: generate the SP key, extract the IdP metadata, register the SP metadata (ConfigMap) and
# place everything into each tenant's /fs-shibboleth. Must happen before the Pods mount /etc/shibboleth.
if [ "$WEKO_SHIB" = "yes" ]; then
  bash provision-shib.sh || { echo "ERROR: provision-shib.sh failed"; exit 1; }
  # ConfigMap weko-idp-sp-metadata が無いと Pod が起動しないので、必ず provision-shib.sh の後に適用する
  # The Pod will not start without the ConfigMap weko-idp-sp-metadata, so apply this after provision-shib.sh
  sed -e "s#image: weko3-shib-idp:arm64#image: $WEKO_IDP_IMAGE#" \
      -e "s#idp\.localhost#$WEKO_IDP_HOST#g" 70-shibboleth-idp.yaml | kubectl apply -f -
  if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then
    sed -e "s#image: weko3-shib-map:arm64#image: $WEKO_MAP_IMAGE#" \
        -e "s#map\.localhost#$WEKO_MAP_HOST#g" 71-shibboleth-map.yaml | kubectl apply -f -
  fi
  # イメージタグが固定 (weko3-shib-idp:arm64) で imagePullPolicy: Never なので、既存クラスタに
  # 再デプロイすると Deployment の spec が 1 バイトも変わらない。すると kubectl apply は
  # "unchanged" を返して Pod を作り直さず、kind に読み込んだ新しいイメージが使われないまま
  # 古い Pod が動き続ける。attribute-resolver.xml や demo.htpasswd はイメージに焼き込まれるので、
  # デモユーザやグループを増やしても反映されない (この後の rollout status は変更が無ければ
  # 即座に成功を返すため、ログ上は正常に見えてしまう)。明示的に作り直す。
  # The image tag is fixed (weko3-shib-idp:arm64) and imagePullPolicy is Never, so redeploying onto an
  # existing cluster leaves the Deployment spec byte-for-byte identical. kubectl apply then reports
  # "unchanged", no Pod is recreated, and the freshly loaded image is never used - the old Pod keeps
  # running. Since attribute-resolver.xml and demo.htpasswd are baked into the image, added demo users
  # or groups simply do not appear (and the later rollout status returns success immediately when
  # nothing changed, so the log still looks clean). Force the recreation.
  kubectl -n weko3 rollout restart deploy/weko-shib-idp
  if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then
    kubectl -n weko3 rollout restart deploy/weko-shib-map
  fi
fi
# COAR Notify の inbox。inbox.py は ConfigMap 経由で渡す (同じコードを manifest 側に複製しないため)。
# テナントの Pod より先に立てておくと、初回のワークフロー操作から通知が届く。
# The COAR Notify inbox. inbox.py is handed over through a ConfigMap so the same code is not duplicated
# into the manifest. Bringing it up before the tenant Pods means notifications land from the very first
# workflow action.
if [ "$WEKO_COAR_NOTIFY" = "yes" ]; then
  kubectl create configmap coar-notify-inbox-src -n weko3 \
    --from-file=inbox.py=coar-notify-inbox/inbox.py --dry-run=client -o yaml | kubectl apply -f - \
    || { echo "ERROR: failed to apply the ConfigMap coar-notify-inbox-src"; exit 1; }
  sed -e "s#image: python:3.12-alpine#image: $WEKO_INBOX_IMAGE#" \
      72-coar-notify-inbox.yaml | kubectl apply -f -
fi
# Applying the whole generated/ directory also applies stale manifests of tenants that were removed
# from tenants.txt, creating orphan tenants that are never provisioned or initialized (and whose PVs
# are Retain, so they linger). Apply only what tenants.txt lists, and just warn about leftovers.
for t in $(grep -vE '^\s*#|^\s*$' tenants.txt | awk '{print $1}'); do
  kubectl apply -f "generated/${t}.yaml"
done
for f in generated/*.yaml; do
  [ -e "$f" ] || continue
  t=$(basename "$f" .yaml)
  grep -qE "^\s*${t}\s" tenants.txt || \
    echo "WARNING: $f is not in tenants.txt, skipped"
done
bash provision-tenants.sh
for t in $(grep -vE '^\s*#|^\s*$' tenants.txt | awk '{print $1}'); do
  kubectl rollout status deploy/${t}-web -n weko3 --timeout=600s
done

echo "########## 7) initialize each tenant, in parallel (FORCE_INIT=$FORCE_INIT) ##########"
# A from-scratch build initializes every tenant. When re-running against an existing cluster,
# use FORCE_INIT=no to honor the INIT column instead.
# IMPORTANT: with `grep ... | while`, the loop body runs in a subshell, so the `&` jobs belong to that
# subshell and the `wait` after the loop runs in the parent with no children - it returns immediately.
# Step 8 then runs before initialization finishes and fails with "relation admin_settings does not exist".
# Use process substitution to keep the loop in the current shell, collect the PIDs and wait on each.
# Step 8 depends on this, so abort on failure.
INIT_JOBS=""
while read -r NAME DB HOST EMAIL PASS INIT _; do
  [ "$FORCE_INIT" = "yes" ] || [ "$INIT" = "yes" ] || continue
  POD=$(kubectl get pod -n weko3 -l app=${NAME}-web -o jsonpath='{.items[0].metadata.name}')
  B64=$(base64 -w0 weko-init.sh)
  kubectl exec -n weko3 "$POD" -c web -- bash -lc "echo $B64 | base64 -d | bash" &
  INIT_JOBS="$INIT_JOBS $!:$NAME"
done < <(grep -vE '^\s*#|^\s*$' tenants.txt)
INIT_FAILED=""
for job in $INIT_JOBS; do
  wait "${job%%:*}" || INIT_FAILED="$INIT_FAILED ${job##*:}"
done
if [ -n "$INIT_FAILED" ]; then
  echo "ERROR: tenant initialization failed for:$INIT_FAILED"
  exit 1
fi

echo "########## 7.5) seed the demo data (item types, index tree, workflows, ...) ##########"
echo "##########      seed the demo data (item types, index tree, workflows, ...)      ##########"
# The weko source's install.sh loads these after populate-instance.sh. Without them the item types,
# index tree and workflows are empty and nothing can be registered.
bash seed-demo.sh || exit 1

echo "########## 8) seed admin_settings + set the S3 file Location + restart web ##########"
echo "##########    seed admin_settings + set the S3 file Location + restart web        ##########"
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
grep -vE '^\s*#|^\s*$' tenants.txt | while read -r NAME DB HOST EMAIL PASS INIT _; do
  kubectl exec -n weko3 $PGM -- psql -U postgres -d $DB \
    -c "INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb) ON CONFLICT DO NOTHING;"
done
# Point file storage at S3 (MinIO): create the per-tenant bucket + set files_location to the S3 type
bash set-s3-location.sh
kubectl rollout restart -n weko3 $(grep -vE '^\s*#|^\s*$' tenants.txt | awk '{print "deploy/"$1"-web"}' | tr '\n' ' ')
for t in $(grep -vE '^\s*#|^\s*$' tenants.txt | awk '{print $1}'); do
  kubectl rollout status deploy/${t}-web -n weko3 --timeout=600s
done

echo "########## 9) connectivity check ##########"
# `rollout status` returns as soon as the Pod is Ready, but uwsgi in the web container is not serving
# yet and nginx answers 502. A single request would report 502 for a perfectly good deployment, so
# retry while the code is 5xx and print the settled value (up to ~5 minutes).
# HTTPS is on by default, so http answers 308 (redirect to https). Showing only http would look like a
# failure, so report both. https uses our own CA, hence curl -k (inspect the cert with openssl below).
# Probe with whichever request actually reaches the backend. With TLS on, http is answered by the
# ingress with a 308 without touching the backend, so retrying on http exits immediately and reports a
# 502 for https while the app is still starting.
if [ -n "$WEKO_TLS_ISSUER" ] || [ -n "${WEKO_TLS_SECRET:-}" ]; then PROBE=https; else PROBE=http; fi
grep -vE '^\s*#|^\s*$' tenants.txt | while read -r NAME DB HOST _; do
  for _ in $(seq 1 30); do
    if [ "$PROBE" = https ]; then
      CODE=$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: $HOST" https://localhost/ --max-time 60)
    else
      CODE=$(curl -s  -o /dev/null -w '%{http_code}' -H "Host: $HOST" http://localhost/  --max-time 60)
    fi
    case "$CODE" in 5*|000) sleep 10 ;; *) break ;; esac
  done
  HCODE=$(curl -s  -o /dev/null -w '%{http_code}' -H "Host: $HOST" http://localhost/  --max-time 60)
  SCODE=$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: $HOST" https://localhost/ --max-time 60)
  echo "  $HOST -> http:$HCODE https:$SCODE"
done
if [ "$WEKO_SHIB" = "yes" ]; then
  kubectl -n weko3 rollout status deploy/weko-shib-idp --timeout=300s \
    || echo "WARNING: the Shibboleth IdP did not become ready"
  if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then
    kubectl -n weko3 rollout status deploy/weko-shib-map --timeout=300s \
      || echo "WARNING: the attribute authority did not become ready"
  fi
  # /idp/status は 200 を返せば設定の読み込みまで成功している (403 なら access-control.xml の許可漏れ)
  # A 200 from /idp/status means the configuration loaded successfully (403 = access-control.xml gap)
  ICODE=$(curl -sk -o /dev/null -w '%{http_code}' -H "Host: $WEKO_IDP_HOST" \
            "https://localhost/idp/status" --max-time 60)
  echo "  $WEKO_IDP_HOST/idp/status -> https:$ICODE"
fi
if [ "$WEKO_COAR_NOTIFY" = "yes" ]; then
  echo "-- COAR Notify inbox --"
  kubectl -n weko3 rollout status deploy/coar-notify-inbox --timeout=300s \
    || echo "WARNING: the COAR Notify inbox did not become ready"
  # テナントの nginx が /inbox を中継できているかまで見る。weko-notifications が返す通知 IRI は
  # この URL なので、ここが 200 でないと通知一覧のリンクが開けない。
  # Check that the tenant's nginx really relays /inbox: the notification IRIs weko-notifications hands
  # out are these URLs, so anything other than 200 here means the links in the list cannot be opened.
  NHOST=$(grep -vE '^\s*#|^\s*$' tenants.txt | awk 'NR==1{print $3}')
  NCODE=$(curl -sk -o /dev/null -w '%{http_code}' -H 'accept: application/ld+json' \
            -H "Host: $NHOST" "https://localhost/inbox" --max-time 60)
  echo "  https://$NHOST/inbox -> $NCODE (200 = nginx が inbox に到達 / nginx reaches the inbox)"
fi
if [ -n "$WEKO_TLS_ISSUER" ]; then
  echo "-- certificate ($WEKO_TLS_ISSUER) --"
  echo | openssl s_client -connect localhost:443 \
      -servername "$(grep -vE '^\s*#|^\s*$' tenants.txt | awk 'NR==1{print $3}')" 2>/dev/null \
    | openssl x509 -noout -issuer -ext subjectAltName -enddate 2>/dev/null | sed 's/^/  /'
fi
echo "done. (browser: http://<tenant>.localhost/ ; see tenants.txt for the administrator)"
if [ "$WEKO_SHIB" = "yes" ]; then
  if [ "$WEKO_SHIB_LOGIN_ONLY" = "yes" ]; then
    echo "shibboleth login: https://<tenant>.localhost/login/ (goes straight to the IdP)"
  else
    echo "shibboleth login: https://<tenant>.localhost/weko/shib/sp/login"
  fi
  echo "  IdP demo users: admin/admin123  libadmin/libadmin123  teacher/teacher123  commadmin/commadmin123 (see SHIBBOLETH-IDP.md)"
fi
if [ "$WEKO_COAR_NOTIFY" = "yes" ]; then
  echo "coar notify inbox: https://<tenant>.localhost/inbox (browser: 受信一覧 / the received list)"
  echo "  kubectl -n weko3 logs -f deploy/coar-notify-inbox   # 受信した通知がそのまま出る / dumps each notification"
fi
