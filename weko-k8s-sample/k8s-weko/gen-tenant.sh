#!/bin/bash
# Generate the k8s manifests for each tenant from tenants.txt into generated/<name>.yaml.
# Output: <name>-config(ConfigMap) / <name>-secret / <name>-web(Deploy: nginx+web+worker)
#         / <name>-nginx(Svc) / <name>-ingress
# The backends (PostgreSQL/ES/RabbitMQ/MinIO), Redis Sentinel (weko3re) and the nginx config
# (weko-nginx-conf) are shared by all tenants.
# Redis runs in redissentinel mode (the instance.cfg default); tenants are separated by Redis DB number.
set -euo pipefail
cd "$(dirname "$0")"
TFILE="${1:-tenants.txt}"
OUT=generated
mkdir -p "$OUT"

# Sentinel/Redis endpoint (instance.cfg refers to weko-sentinel-service.weko3re:26379)
REDIS_MASTER_HOST="redis-0.redis.weko3re.svc.cluster.local"
# MinIO(S3)
S3_KEY="wekominio"; S3_SECRET="wekominio-secret-key"; S3_ENDPOINT="http://minio:9000"
# The NFS server (the pinned ClusterIP from 60-nfs-server.yaml), referenced by the static PVs /fs-*/<tenant>.
NFS_SERVER="${NFS_SERVER:-10.96.0.99}"
#   WEKO_TLS_SECRET   name of the TLS Secret used by the Ingress. Empty (the default) emits no
#                    spec.tls, so ingress-nginx serves its built-in self-signed certificate.
#                    Use a name containing %s to get a per-tenant Secret name.
#   WEKO_SSL_REDIRECT set to no to stop redirecting HTTP to HTTPS. Once spec.tls is set, ingress-nginx
#                    answers HTTP with a 308 to HTTPS by default.
#   WEKO_TLS_ISSUER  name of a cert-manager ClusterIssuer. When set, certificates are issued
#                    automatically: the cert-manager.io/cluster-issuer annotation makes ingress-shim
#                    create the Certificate and populate the Secret, so no manual Secret is needed.
#                    The intended value is weko-ca-issuer from 61-tls-ca.yaml.
# The default is automatic issuance via cert-manager using the bundled root CA. To turn HTTPS back to
# the ingress-nginx built-in self-signed certificate, pass an explicit empty value:
#   WEKO_TLS_ISSUER= bash deploy-arm64.sh
# Use `-` and not `:-` here: with `:-` an explicitly empty value would fall back to the default and
# there would be no way to disable it.
WEKO_TLS_SECRET="${WEKO_TLS_SECRET:-}"
WEKO_TLS_ISSUER="${WEKO_TLS_ISSUER-weko-ca-issuer}"
WEKO_SSL_REDIRECT="${WEKO_SSL_REDIRECT:-yes}"
# When an issuer is set but no Secret name is given, default to a per-tenant name for the issued cert.
[ -n "$WEKO_TLS_ISSUER" ] && [ -z "$WEKO_TLS_SECRET" ] && WEKO_TLS_SECRET='%s-tls'
# instance.cfg の THEME_SITEURL は "$INVENIO_WEB_PROTOCOL://$INVENIO_WEB_HOST_NAME"。これは
# リクエストコンテキスト外 (Celery タスク / COAR Notify の通知 IRI / メール本文) で使われるので、
# TLS を張っているならスキームも合わせておく。
# instance.cfg builds THEME_SITEURL as "$INVENIO_WEB_PROTOCOL://$INVENIO_WEB_HOST_NAME". That is what
# gets used outside a request context (Celery tasks, COAR Notify IRIs, e-mail bodies), so keep the
# scheme in step with whether TLS is actually terminated in front.
if [ -n "$WEKO_TLS_SECRET" ]; then WEKO_WEB_PROTOCOL=https; else WEKO_WEB_PROTOCOL=http; fi
# WEKO application image (swappable: override with WEKO_IMAGE=<repo>/<name>:<tag>)
WEKO_IMAGE="${WEKO_IMAGE:-weko3-web:arm64}"
# The WEKO nginx image: it embeds the Shibboleth SP (shibd + the nginx-http-shibboleth module) and is
# built from the weko source's nginx/Dockerfile (step 2 of deploy-*.sh does this).
WEKO_NGINX_IMAGE="${WEKO_NGINX_IMAGE:-weko3-nginx:arm64}"
# Whether to enable the production-style weko.conf (Shibboleth/TLS/IP restrictions). Default no = use the
# simple default.conf (uwsgi_pass) suited to kind's HTTP Ingress; yes keeps weko.conf as-is.
WEKO_NGINX_SHIB="${WEKO_NGINX_SHIB:-no}"
# Shibboleth ログインのデモを有効にするか (yes/no)。yes にすると:
#   - nginx が 21-nginx-config.yaml の default-shib.conf で動く (shibauthorizer / /secure/login.py 付き)
#   - shibd を含む supervisord がそのまま起動する
#   - invenio.cfg に WEKO_ACCOUNTS_SHIB_* を追記してログイン画面に「学認/機関アカウント」導線が出る
#   - 70-shibboleth-idp.yaml の IdP と provision-shib.sh の信頼関係が前提になる
# WEKO_NGINX_SHIB (本番の weko.conf をそのまま使うモード) とは排他で、こちらが優先される。
#
# Whether to enable the Shibboleth login demo (yes/no). With yes:
#   - nginx runs default-shib.conf from 21-nginx-config.yaml (shibauthorizer / /secure/login.py)
#   - the image's supervisord starts as-is, so shibd runs
#   - WEKO_ACCOUNTS_SHIB_* is appended to invenio.cfg, exposing the institutional login path
#   - it assumes the IdP from 70-shibboleth-idp.yaml and the trust set up by provision-shib.sh
# It is mutually exclusive with WEKO_NGINX_SHIB (the raw production weko.conf mode) and takes precedence.
WEKO_SHIB="${WEKO_SHIB:-no}"
# Shibboleth 専用ログイン (instance.cfg のコメントでいう「パターン4」) にするか。
#   no  (既定): /login はローカルのログインフォームを出す。Shibboleth の入口は /weko/shib/sp/login。
#   yes       : /login が meta refresh で /secure/login.py へ飛び、そのまま IdP に行く。
#               WEKO_ACCOUNTS_SHIB_INST_LOGIN_DIRECTLY_ENABLED を True にすることで切り替わる。
# yes の副作用 (実測): ローカルログインフォームが消えるので IdP 停止時にブラウザから入れない /
# WEKO のログアウトでは SP セッションが消えないため /login で無言で再ログインされ別ユーザに変えられない /
# 失敗時の flash メッセージがログイン画面ごとリダイレクトされて表示されない。詳細は SHIBBOLETH-IDP.md。
#
# Whether to make the login Shibboleth-only ("pattern 4" in instance.cfg's comments).
#   no  (default): /login renders the local login form; the Shibboleth entry point is /weko/shib/sp/login.
#   yes          : /login meta-refreshes to /secure/login.py and goes straight to the IdP.
#                  It works by setting WEKO_ACCOUNTS_SHIB_INST_LOGIN_DIRECTLY_ENABLED to True.
# Observed side effects of yes: the local login form disappears, so a stopped IdP locks everyone out of
# the browser; WEKO's logout does not clear the SP session, so /login silently logs the same user back
# in with no way to switch accounts; and failure messages are lost because the login page that renders
# the flash is itself redirected away. See SHIBBOLETH-IDP.md.
WEKO_SHIB_LOGIN_ONLY="${WEKO_SHIB_LOGIN_ONLY:-no}"
# 学認mAP 連携 (isMemberOf によるグループ→ロール変換) をどう再現するか。
#   no          … 使わない (既定)
#   sso         … IdP が isMemberOf を SSO アサーションに載せる
#   aggregation … 本番と同じく SP が SimpleAggregation (SAML2 AttributeQuery) で取りに行く
# sso / aggregation のどちらでも WEKO から見た入力は同じで、weko-accounts の
# _assign_roles_to_user() / sync_shib_gakunin_map_groups() が動く。詳細は SHIBBOLETH-IDP.md。
#
# How the GakuNin mAP integration (group→role mapping via isMemberOf) is reproduced.
#   no          … not used (default)
#   sso         … the IdP puts isMemberOf in the SSO assertion
#   aggregation … the SP fetches it with SimpleAggregation (a SAML2 AttributeQuery), as in production
# WEKO sees the same input either way, so weko-accounts' _assign_roles_to_user() /
# sync_shib_gakunin_map_groups() run in both. See SHIBBOLETH-IDP.md.
WEKO_SHIB_MAP="${WEKO_SHIB_MAP:-no}"
WEKO_IDP_HOST="${WEKO_IDP_HOST:-idp.localhost}"
WEKO_IDP_ENTITYID="${WEKO_IDP_ENTITYID:-https://${WEKO_IDP_HOST}/idp/shibboleth}"
case "$WEKO_SHIB_MAP" in
  no|sso|aggregation) ;;
  *) echo "ERROR: WEKO_SHIB_MAP must be no|sso|aggregation (got '$WEKO_SHIB_MAP')" >&2; exit 1 ;;
esac
if [ "$WEKO_SHIB_MAP" != "no" ] && [ "$WEKO_SHIB" != "yes" ]; then
  echo "NOTE: WEKO_SHIB_MAP=$WEKO_SHIB_MAP has no effect without WEKO_SHIB=yes" >&2
fi
if [ "$WEKO_SHIB" = "yes" ] && [ "$WEKO_NGINX_SHIB" = "yes" ]; then
  echo "NOTE: WEKO_SHIB=yes overrides WEKO_NGINX_SHIB=yes (default-shib.conf is used, not weko.conf)" >&2
  WEKO_NGINX_SHIB=no
fi
# Default (no): run nginx only. shibd/shibauthorizer/shibresponder require a real IdP (GakuNin) setup
# and go FATAL without it, so they are not started in the default mode.
# yes: keep the image's supervisord CMD, i.e. the production-equivalent stack including shibd.
if [ "$WEKO_NGINX_SHIB" = "yes" ] || [ "$WEKO_SHIB" = "yes" ]; then
  NGINX_COMMAND=""
else
  NGINX_COMMAND='        command: ["/bin/sh","-c","exec nginx -g '"'"'daemon off;'"'"'"]
'
fi

# WEKO_SHIB=yes のときだけ差し込むマニフェスト断片 / manifest fragments injected only when WEKO_SHIB=yes
NGINX_CONF_SUBPATH="default.conf"
SHIB_EXTRA_MOUNTS=""
SHIB_INIT_CONTAINER=""
SHIB_CFG_APPEND=""
MAP_HOST_ALIAS=""
if [ "$WEKO_SHIB" = "yes" ]; then
  NGINX_CONF_SUBPATH="default-shib.conf"
  SHIB_EXTRA_MOUNTS='        - { name: nginx-conf, mountPath: /etc/nginx/weko_shib_params, subPath: weko_shib_params }
'
  # /etc/shibboleth は共有 FS (PVC) なので、イメージ同梱の attribute-map.xml / protocols.xml /
  # security-policy.xml などを流し込まないと shibd が起動できない。provision-shib.sh が先に置いた
  # shibboleth2.xml / 鍵 / idp-metadata.xml を潰さないよう cp -an (既存ファイルは上書きしない) を使う。
  # /etc/shibboleth lives on the shared FS (PVC), so shibd cannot start unless the image's
  # attribute-map.xml / protocols.xml / security-policy.xml etc. are seeded into it. cp -an (never
  # clobber) keeps the shibboleth2.xml / keys / idp-metadata.xml that provision-shib.sh placed first.
  # $WEKO_NGINX_IMAGE はここで展開する。ヒアドキュメントは変数の「値」を再スキャンしないので、
  # コンテナ側で評価させたい $(ls ...) はエスケープしてリテラルのまま残す。
  # $WEKO_NGINX_IMAGE is expanded here. The heredoc does not re-scan a variable's value, so the
  # $(ls ...) meant for the container's own shell is escaped to stay literal.
  # instance.cfg は Shibboleth を無効 (WEKO_ACCOUNTS_SHIB_LOGIN_ENABLED = False) で焼き込んでおり、
  # 環境変数では切り替えられないので、生成後の invenio.cfg に追記して上書きする。
  # instance.cfg bakes Shibboleth in as disabled (WEKO_ACCOUNTS_SHIB_LOGIN_ENABLED = False) and it is
  # not switchable via environment variables, so it is overridden by appending to the generated
  # invenio.cfg.
  #
  # WEKO_SHIB_LOGIN_ONLY で /login の挙動が変わる唯一の設定がこれ (True = /login も IdP へ飛ばす)。
  # This is the one setting WEKO_SHIB_LOGIN_ONLY flips (True = send /login to the IdP as well).
  if [ "$WEKO_SHIB_LOGIN_ONLY" = "yes" ]; then SHIB_INST_DIRECT=True; else SHIB_INST_DIRECT=False; fi
  SHIB_CFG_APPEND="          # ---- Shibboleth (WEKO_SHIB=yes, WEKO_SHIB_LOGIN_ONLY=$WEKO_SHIB_LOGIN_ONLY) ----
          echo \"WEKO_ACCOUNTS_SHIB_LOGIN_ENABLED = True\"                             >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_SHIB_IDP_LOGIN_ENABLED = True\"                         >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_SHIB_INST_LOGIN_DIRECTLY_ENABLED = $SHIB_INST_DIRECT\"  >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_SHIB_DP_LOGIN_DIRECTLY_ENABLED = False\"                >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_SHIB_IDP_LOGIN_URL = \\\"{}secure/login.py\\\"\"          >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_SKIP_CONFIRMATION_PAGE = False\"                        >> /conf/invenio.cfg
"
  # 学認mAP 連携。isMemberOf の入手経路 (SSO / SimpleAggregation) が何であれ、WEKO 側の設定は同じ。
  #
  # WEKO_ACCOUNTS_ATTRIBUTE_MAP を上書きしているのが要点。既定の instance.cfg のマップには
  # shib_is_member_of のエントリが無く、その場合 parse_attributes() は辞書のキー名
  # ("SHIB_ATTR_IS_MEMBER_OF") をフォームのフィールド名として探しにいく。ところが login.py が実際に
  # 送るのは /etc/nginx/shib_fastcgi_params 由来の "isMemberOf" なので、追加しないと値が
  # 黙って捨てられる (このマップは起動時に _adjust_shib_admin_DB が admin_settings へ書き込む)。
  #
  # The GakuNin mAP integration. The WEKO-side settings are the same regardless of how isMemberOf
  # arrived (SSO or SimpleAggregation).
  #
  # The key part is overriding WEKO_ACCOUNTS_ATTRIBUTE_MAP. The stock instance.cfg map has no
  # shib_is_member_of entry, and without one parse_attributes() looks for a form field named after the
  # dictionary key ("SHIB_ATTR_IS_MEMBER_OF") - whereas login.py actually posts "isMemberOf", the name
  # that comes from /etc/nginx/shib_fastcgi_params. Without this the value is silently dropped.
  # (_adjust_shib_admin_DB writes this map into admin_settings at startup.)
  # SimpleAggregation のバックチャネルは属性認証局の TLS 証明書 (CN=map.localhost) を使うので、
  # 繋ぎ先のホスト名もそろえる必要がある。Service の ClusterIP は 71-shibboleth-map.yaml で固定。
  # The SimpleAggregation back-channel uses the attribute authority's TLS certificate
  # (CN=map.localhost), so the host name connected to has to match. The Service ClusterIP is pinned in
  # 71-shibboleth-map.yaml.
  if [ "$WEKO_SHIB_MAP" = "aggregation" ]; then
    MAP_HOST_ALIAS=$(printf '\n      - { ip: "%s", hostnames: ["%s"] }' \
                       "${WEKO_MAP_CLUSTER_IP:-10.96.0.98}" "${WEKO_MAP_HOST:-map.localhost}")
  fi
  if [ "$WEKO_SHIB_MAP" != "no" ]; then
    SHIB_CFG_APPEND="${SHIB_CFG_APPEND}          # ---- GakuNin mAP (WEKO_SHIB_MAP=$WEKO_SHIB_MAP) ----
          echo \"WEKO_ACCOUNTS_SHIB_BIND_GAKUNIN_MAP_GROUPS = True\"                   >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_IDP_ENTITY_ID = \\\"$WEKO_IDP_ENTITYID\\\"\"               >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_ATTRIBUTE_MAP = {\\\"shib_eppn\\\": \\\"eppn\\\", \\\"shib_role_authority_name\\\": \\\"HTTP_WEKOSOCIETYAFFILIATION\\\", \\\"shib_mail\\\": \\\"mail\\\", \\\"shib_user_name\\\": \\\"DisplayName\\\", \\\"shib_is_member_of\\\": \\\"isMemberOf\\\", \\\"shib_organization\\\": \\\"o\\\"}\" >> /conf/invenio.cfg
          # 機関外の学認 IdP / Orthros から来たユーザのロール。組織名 (o = urn:oid:2.5.4.10) で決まる。
          # 既定の instance.cfg では organizationName が全部空リストなので、_find_organization_name()
          # は絶対に一致せず、この経路は死んだままになっている。デモ用に値を入れて生かす。
          # 一致するとグループ経路は丸ごとスキップされる (check_in() の
          #   if not self._find_organization_name(): self._assign_roles_to_user(...)
          # という構造) ので、この 3 種のユーザはロールがちょうど 1 つになる。
          # 注意: この文字列は二重引用符の中に入るので、バッククォートは書かないこと
          # (コマンド置換として解釈されて gen-tenant.sh が構文エラーになる)。
          # Roles for users arriving from an out-of-institution GakuNin IdP or from Orthros, decided by
          # the organization name (o = urn:oid:2.5.4.10). In the stock instance.cfg every
          # organizationName list is empty, so _find_organization_name() can never match and the whole
          # path is dead; these values bring it to life for the demo. On a match the group path is
          # skipped entirely - check_in() reads
          #   if not self._find_organization_name(): self._assign_roles_to_user(...)
          # - so these three kinds of user end up with exactly one role.
          # NOTE: this text sits inside a double-quoted string, so never write a backtick here; it
          # would be taken as command substitution and break gen-tenant.sh with a syntax error.
          echo \"WEKO_ACCOUNTS_GAKUNIN_ROLE = {\\\"organizationName\\\": [\\\"学認テスト機関\\\"], \\\"defaultRole\\\": \\\"Contributor\\\"}\" >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_ORTHROS_INSIDE_ROLE = {\\\"organizationName\\\": [\\\"Orthros内部\\\"], \\\"defaultRole\\\": \\\"Repository Administrator\\\"}\" >> /conf/invenio.cfg
          echo \"WEKO_ACCOUNTS_ORTHROS_OUTSIDE_ROLE = {\\\"organizationName\\\": [\\\"Orthros外部\\\"], \\\"defaultRole\\\": \\\"Community Administrator\\\"}\" >> /conf/invenio.cfg
"
  fi
  SHIB_INIT_CONTAINER="      - name: seed-shib
        image: $WEKO_NGINX_IMAGE
        imagePullPolicy: Never
        command: [\"/bin/sh\",\"-c\"]
        args:
        - |
          cp -an /etc/shibboleth/. /seed-shib/ 2>/dev/null || true
          echo \"seeded shibboleth: \$(ls /seed-shib | wc -l) entries\"
        volumeMounts:
        - { name: shib, mountPath: /seed-shib }
"
fi

# COAR Notify (LDN)。yes のとき、通知の宛先を invenio.cfg に明示する。
# weko-notifications の既定値がそもそも http://inbox:8080 + /inbox なので、72-coar-notify-inbox.yaml の
# Service 名 (inbox) と一致していれば無設定でも届く。それでも書き出しているのは、
#   - どこへ送っているかが invenio.cfg を見れば分かるようにするため
#   - WEKO_INBOX_ADDRESS で別の inbox (外部サービス) に差し替えられるようにするため
# の 2 点による。
#
# COAR Notify (LDN). With yes, the notification target is written into invenio.cfg explicitly.
# weko-notifications already defaults to http://inbox:8080 + /inbox, so as long as that matches the
# Service name (inbox) in 72-coar-notify-inbox.yaml it works with no configuration at all. It is still
# written out so that
#   - invenio.cfg alone shows where notifications are being sent, and
#   - WEKO_INBOX_ADDRESS can point at a different (external) inbox.
WEKO_COAR_NOTIFY="${WEKO_COAR_NOTIFY:-no}"
WEKO_INBOX_ADDRESS="${WEKO_INBOX_ADDRESS:-http://inbox:8080}"
COAR_CFG_APPEND=""
if [ "$WEKO_COAR_NOTIFY" = "yes" ]; then
  COAR_CFG_APPEND="          # ---- COAR Notify (WEKO_COAR_NOTIFY=yes) ----
          echo \"WEKO_NOTIFICATIONS = True\"                                           >> /conf/invenio.cfg
          echo \"WEKO_NOTIFICATIONS_INBOX_ADDRESS = \\\"$WEKO_INBOX_ADDRESS\\\"\"        >> /conf/invenio.cfg
          echo \"WEKO_NOTIFICATIONS_INBOX_ENDPOINT = \\\"/inbox\\\"\"                    >> /conf/invenio.cfg
"
fi

# Seed for the application secret keys. Per-tenant keys are derived from it and the seed is persisted
# in .secret-seed so regeneration yields the same keys. It can also be given via WEKO_SECRET_SEED.
SEED_FILE="${WEKO_SECRET_SEED_FILE:-.secret-seed}"
if [ -z "${WEKO_SECRET_SEED:-}" ]; then
  if [ -f "$SEED_FILE" ]; then
    WEKO_SECRET_SEED="$(cat "$SEED_FILE")"
  else
    WEKO_SECRET_SEED="$(head -c 32 /dev/urandom | sha256sum | cut -d' ' -f1)"
    printf '%s\n' "$WEKO_SECRET_SEED" > "$SEED_FILE"; chmod 600 "$SEED_FILE"
    echo "generated secret seed: $SEED_FILE (back this file up)"
  fi
fi

gen_one() {
  local NAME=$1 DBNAME=$2 HOST=$3 EMAIL=$4 PASS=$5 CACHE_DB=$6 SESSION_DB=$7 CELERY_DB=$8
  local f="$OUT/$NAME.yaml"
  # HTTPS: emit spec.tls on the Ingress only when WEKO_TLS_SECRET is set. A %s in the name is
  # replaced with the tenant name (e.g. "%s-tls" -> "tenant1-tls").
  local TLS_BLOCK="" TLS_ANNOTATIONS=""
  if [ -n "$WEKO_TLS_SECRET" ]; then
    local SEC; SEC=$(printf "$WEKO_TLS_SECRET" "$NAME")
    TLS_BLOCK=$(printf '\n  tls:\n  - hosts: [ "%s" ]\n    secretName: %s' "$HOST" "$SEC")
    # With an issuer, the annotation is all that is needed: cert-manager derives the SAN from
    # spec.tls hosts, writes to secretName, and renews automatically before expiry.
    [ -n "$WEKO_TLS_ISSUER" ] && TLS_ANNOTATIONS=$(printf '\n    cert-manager.io/cluster-issuer: "%s"' "$WEKO_TLS_ISSUER")
    [ "$WEKO_SSL_REDIRECT" = "no" ] && \
      TLS_ANNOTATIONS="${TLS_ANNOTATIONS}$(printf '\n    nginx.ingress.kubernetes.io/ssl-redirect: "false"')"
  fi
  # Per-tenant secret key. The three keys (SECRET_KEY / WTF_CSRF / RECORDS_UI) may share one value
  # inside a tenant, but the value must differ between tenants. If a previously generated manifest
  # exists its value is reused so that the keys are not rotated.
  local TSECRET=""
  [ -f "$f" ] && TSECRET="$(awk '$1=="SECRET_KEY:"{print $2; exit}' "$f")"
  # Do not reuse the old hardcoded values (a suffix shared by every tenant); re-derive them from the seed
  case "$TSECRET" in *-NcVV6mVZ|*-FMCjj7kG|*-BX8vwrcs) TSECRET="";; esac
  [ -n "$TSECRET" ] || TSECRET="${NAME}-$(printf '%s' "${WEKO_SECRET_SEED}:${NAME}" | sha256sum | cut -c1-32)"
  cat > "$f" <<YAML
# ===== tenant: $NAME (db=$DBNAME host=$HOST redisDB=$CACHE_DB/$SESSION_DB/$CELERY_DB) =====
apiVersion: v1
kind: ConfigMap
metadata: { name: $NAME-config, namespace: weko3 }
data:
  # WEKO connects to PG through pgpool (pooling + read load-balancing). pgpool → Patroni primary/replica.
  INVENIO_POSTGRESQL_HOST: pgpool
  INVENIO_POSTGRESQL_DBNAME: "$DBNAME"
  INVENIO_ELASTICSEARCH_HOST: elasticsearch
  INVENIO_REDIS_HOST: "$REDIS_MASTER_HOST"
  INVENIO_RABBITMQ_HOST: weko-rabbitmq
  INVENIO_RABBITMQ_VHOST: "$NAME"
  INVENIO_WEB_HOST: "127.0.0.1"
  INVENIO_WEB_HOST_NAME: "$HOST"
  INVENIO_WEB_INSTANCE: invenio
  INVENIO_WEB_VENV: invenio
  INVENIO_WEB_PROTOCOL: $WEKO_WEB_PROTOCOL
  INVENIO_WORKER_HOST: "127.0.0.1"
  INVENIO_FILES_LOCATION_NAME: local
  INVENIO_FILES_LOCATION_URI: /home/invenio/.virtualenvs/invenio/var/instance/data/files
  INVENIO_ROLE_SYSTEM: System Administrator
  INVENIO_ROLE_REPOSITORY: Repository Administrator
  INVENIO_ROLE_CONTRIBUTOR: Contributor
  INVENIO_ROLE_COMMUNITY: Community Administrator
  CACHE_REDIS_DB: "$CACHE_DB"
  ACCOUNTS_SESSION_REDIS_DB_NO: "$SESSION_DB"
  CELERY_RESULT_BACKEND_DB_NO: "$CELERY_DB"
  WEKO_AGGREGATE_EVENT_HOUR: "1"
  WEKO_AGGREGATE_EVENT_MINUTE: "0"
  SEARCH_INDEX_PREFIX: "$DBNAME"
  INVENIO_DB_POOL_CLASS: NullPool
  FLASK_DEBUG: "0"
  SHIB_IDP_LOGIN_ENABLED: "False"
  WEKO_HANDLE_ALLOW_REGISTER_CRNI: "False"
  IDENTIFIER_GRANT_SUFFIX_METHOD: "0"
  PATH: /home/invenio/.virtualenvs/invenio/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  VIRTUALENVWRAPPER_PYTHON: /home/invenio/.virtualenvs/invenio/bin/python
  TMPDIR: /home/invenio/.virtualenvs/invenio/var/instance/data/tmp
  TIKA_JAR_FILE_PATH: /code/tika/tika-app-2.6.0.jar
---
apiVersion: v1
kind: Secret
metadata: { name: $NAME-secret, namespace: weko3 }
type: Opaque
stringData:
  INVENIO_POSTGRESQL_DBUSER: weko
  INVENIO_POSTGRESQL_DBPASS: weko
  INVENIO_RABBITMQ_USER: weko
  INVENIO_RABBITMQ_PASS: weko
  INVENIO_USER_EMAIL: "$EMAIL"
  INVENIO_USER_PASS: "$PASS"
  GOOGLE_TRACKING_ID_SYSTEM: ""
  # per-tenant secret key (shared within the tenant)
  WEKO_RECORDS_UI_SECRET_KEY: ${TSECRET}
  SECRET_KEY: ${TSECRET}
  WTF_CSRF_SECRET_KEY: ${TSECRET}
  S3_ACCCESS_KEY_ID: "$S3_KEY"
  S3_SECRECT_ACCESS_KEY: "$S3_SECRET"
  S3_ENDPOINT_URL: "$S3_ENDPOINT"
---
# Equivalent to production's volume-pv.yaml / volume-pvc.yaml: /fs-config, /fs-data, /fs-shibboleth and
# /fs-nginx on the shared FS (NFS) are exposed as static PVs with a per-tenant directory
# (provision-nfs.sh creates and seeds those directories).
apiVersion: v1
kind: PersistentVolume
metadata:
  name: $NAME-config-pv
  labels: { volume: $NAME-config-nfs }
spec:
  capacity: { storage: 1Gi }
  accessModes: ["ReadWriteMany"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-static
  nfs: { server: "$NFS_SERVER", path: /export/fs-config/$NAME }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: $NAME-conf, namespace: weko3 }
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: nfs-static
  resources: { requests: { storage: 1Gi } }
  selector: { matchLabels: { volume: $NAME-config-nfs } }
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: $NAME-data-pv
  labels: { volume: $NAME-data-nfs }
spec:
  capacity: { storage: 5Gi }
  accessModes: ["ReadWriteMany"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-static
  nfs: { server: "$NFS_SERVER", path: /export/fs-data/$NAME }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: $NAME-data, namespace: weko3 }
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: nfs-static
  resources: { requests: { storage: 5Gi } }
  selector: { matchLabels: { volume: $NAME-data-nfs } }
---
# Equivalent to production's shib-pvc (/fs-shibboleth): the Shibboleth SP config (/etc/shibboleth) also
# lives on the shared FS (NFS/RWX). provision-nfs.sh seeds it from weko-k8s's shibboleth_template.
apiVersion: v1
kind: PersistentVolume
metadata:
  name: $NAME-shib-pv
  labels: { volume: $NAME-shib-nfs }
spec:
  capacity: { storage: 1Gi }
  accessModes: ["ReadWriteMany"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-static
  nfs: { server: "$NFS_SERVER", path: /export/fs-shibboleth/$NAME }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: $NAME-shib, namespace: weko3 }
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: nfs-static
  resources: { requests: { storage: 1Gi } }
  selector: { matchLabels: { volume: $NAME-shib-nfs } }
---
# Equivalent to production's nginx-pvc (/fs-nginx): the whole nginx config (/etc/nginx) lives on the
# shared FS (NFS/RWX). provision-nfs.sh seeds it from weko-k8s's nginx_template and the initContainer
# fills any gaps from the weko nginx image.
apiVersion: v1
kind: PersistentVolume
metadata:
  name: $NAME-nginx-pv
  labels: { volume: $NAME-nginx-nfs }
spec:
  capacity: { storage: 1Gi }
  accessModes: ["ReadWriteMany"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs-static
  nfs: { server: "$NFS_SERVER", path: /export/fs-nginx/$NAME }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: $NAME-nginx-pvc, namespace: weko3 }
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: nfs-static
  resources: { requests: { storage: 1Gi } }
  selector: { matchLabels: { volume: $NAME-nginx-nfs } }
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: $NAME-web, namespace: weko3 }
#   fsGroup=1000 / hostAliases / RollingUpdate / nodeSelector=WEKO。
# Same layout as production's weko-k8s/deploy/weko/manifest_template/deploy-web.yaml:
#   init (generates invenio.cfg with jinja2) + nginx + web(uwsgi) + worker(celery), shared FS
#   (conf/data/shib/static), fsGroup=1000 / hostAliases / RollingUpdate / nodeSelector=WEKO.
# Differences: nginx is stock nginx + a ConfigMap (uwsgi_pass) rather than the production image with the
#   Shibboleth SP/WAF, and TLS is terminated at the Ingress.
spec:
  replicas: 1
  strategy: { type: RollingUpdate, rollingUpdate: { maxSurge: 1, maxUnavailable: 0 } }
  selector: { matchLabels: { app: $NAME-web } }
  template:
    metadata: { labels: { app: $NAME-web, tenant: "$NAME" } }
    spec:
      nodeSelector: { nodeType: WEKO }
      restartPolicy: Always
      securityContext: { fsGroup: 1000 }
      # resolve our own FQDN to loopback, as in production
      hostAliases:
      - { ip: "127.0.0.1", hostnames: ["$HOST"] }$MAP_HOST_ALIAS
      initContainers:
      # Equivalent to production's init container: generate invenio.cfg from instance.cfg with jinja2
      # onto the shared FS (conf)
      - name: init
        image: $WEKO_IMAGE
        imagePullPolicy: Never
        command: ["/bin/bash","-c"]
        args:
        - |
          set -e
          export LANG=C.UTF-8 LC_ALL=C.UTF-8
          export PATH=/home/invenio/.virtualenvs/invenio/bin:\$PATH
          # Switch to redissentinel mode (the bundled instance.cfg hardcodes 'redis')
          sed -i "s#CACHE_TYPE = OAUTH2_CACHE_TYPE =  'redis'#CACHE_TYPE = OAUTH2_CACHE_TYPE = 'redissentinel'#" /code/scripts/instance.cfg
          # Use S3 (MinIO) as the file Location: read the S3 credentials from the Secret (env vars)
          sed -i -e "s/^S3_ACCCESS_KEY_ID = None/S3_ACCCESS_KEY_ID = os.environ.get('S3_ACCCESS_KEY_ID')/" -e "s/^S3_SECRET_ACCESS_KEY = None/S3_SECRET_ACCESS_KEY = os.environ.get('S3_SECRECT_ACCESS_KEY')/" -e "s#^S3_ENDPOINT_URL = None#S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL')#" /code/scripts/instance.cfg
          # the shared conf FS starts empty, so place uwsgi.ini
          cp -f /code/scripts/uwsgi.ini /conf/uwsgi.ini
          sed -i -e "s/^py-autoreload.*/py-autoreload = 0/" -e "s/^processes = .*/processes = 1/" -e "s/^threads = .*/threads = 1/" /conf/uwsgi.ini
          jinja2 /code/scripts/instance.cfg > /conf/invenio.cfg
          # App-layer fix: disable the non-idempotent template override causing infinite recursion on /login
          echo "OAUTHCLIENT_TEMPLATE_KEY = None" >> /conf/invenio.cfg
$SHIB_CFG_APPEND$COAR_CFG_APPEND        envFrom:
        - { configMapRef: { name: $NAME-config } }
        - { secretRef: { name: $NAME-secret } }
        volumeMounts:
        - { name: conf, mountPath: /conf }
      # Equivalent to production's data-pvc initialization: seed the empty NFS data volume with the
      # image's data (_variables.scss / indextree)
      - name: seed-data
        image: $WEKO_IMAGE
        imagePullPolicy: Never
        command: ["/bin/sh","-c"]
        args:
        - |
          cp -an /home/invenio/.virtualenvs/invenio/var/instance/data/. /seed/ 2>/dev/null || true
          echo seeded
        volumeMounts:
        - { name: data, mountPath: /seed }
      # static is Pod-local (emptyDir), so seed it with the image's static files
      # (the mount hides them, so copy from an initContainer that mounts it at a different path)
      - name: seed-static
        image: $WEKO_IMAGE
        imagePullPolicy: Never
        command: ["/bin/sh","-c"]
        args:
        - |
          cp -an /home/invenio/.virtualenvs/invenio/var/instance/static/. /seed-static/ 2>/dev/null || true
          echo "seeded static: \$(ls /seed-static | wc -l) entries"
        volumeMounts:
        - { name: static, mountPath: /seed-static }
      # Equivalent to production's /fs-nginx: seed the nginx config onto the shared FS and inject the FQDN
      - name: seed-nginx
        image: $WEKO_NGINX_IMAGE
        imagePullPolicy: Never
        command: ["/bin/bash","-c"]
        args:
        - |
          set -e
          cp -an /etc/nginx/. /seed-nginx/ 2>/dev/null || true
          # point weko.conf's server_name at the tenant FQDN
          sed -i "s/weko3\.example\.org/$HOST/g; s/__WEKO3_VHOST__/$HOST/g" /seed-nginx/conf.d/weko.conf 2>/dev/null || true
          if [ "$WEKO_NGINX_SHIB" != "yes" ]; then
            # By default disable the production weko.conf (TLS/IP allow list/Shibboleth) and serve via default.conf
            [ -f /seed-nginx/conf.d/weko.conf ] && mv -f /seed-nginx/conf.d/weko.conf /seed-nginx/conf.d/weko.conf.disabled || true
          else
            [ -f /seed-nginx/conf.d/weko.conf.disabled ] && mv -f /seed-nginx/conf.d/weko.conf.disabled /seed-nginx/conf.d/weko.conf || true
          fi
          echo seeded-nginx
        volumeMounts:
        - { name: nginx-etc, mountPath: /seed-nginx }
$SHIB_INIT_CONTAINER      containers:
      # The weko nginx with the Shibboleth SP (supervisord runs shibd + nginx)
      - name: nginx
        image: $WEKO_NGINX_IMAGE
        imagePullPolicy: Never
$NGINX_COMMAND        ports: [ { containerPort: 80 }, { containerPort: 443 } ]
        resources: { requests: { memory: "128Mi", cpu: "25m" }, limits: { memory: "512Mi", cpu: "1" } }
        volumeMounts:
        # the whole /etc/nginx comes from the shared FS, as in production
        - { name: nginx-etc, mountPath: /etc/nginx }
        # WEKO_SHIB=yes のときは default-shib.conf (shibauthorizer / /secure/login.py 付き) が入る
        # With WEKO_SHIB=yes this carries default-shib.conf (with shibauthorizer / /secure/login.py)
        - { name: nginx-conf, mountPath: /etc/nginx/conf.d/default.conf, subPath: $NGINX_CONF_SUBPATH }
$SHIB_EXTRA_MOUNTS        # As in production, the Shibboleth SP config comes from the shared FS (unused by stock nginx)
        - { name: shib, mountPath: /etc/shibboleth }
        # static and data are mounted into nginx as in production
        - { name: static, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/static }
        - { name: data, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/data }
        readinessProbe: { httpGet: { path: /ping, port: 80 }, initialDelaySeconds: 5, periodSeconds: 10 }
      - name: web
        image: $WEKO_IMAGE
        imagePullPolicy: Never
        command: ["/bin/bash","-c"]
        args:
        - |
          set -e
          ulimit -c 0 || true
          export LANG=C.UTF-8 LC_ALL=C.UTF-8
          export PATH=/home/invenio/.virtualenvs/invenio/bin:\$PATH
          INST=/home/invenio/.virtualenvs/invenio/var/instance
          # App-layer fix: avoid the KeyError on /api/records (applied on this container's filesystem)
          sed -i "s/aggs = data\['aggregations'\]/aggs = data.get('aggregations', {})/" /code/modules/weko-search-ui/weko_search_ui/utils.py 2>/dev/null || true
          # App-layer fix: avoid the 500 on /api/index/. With an empty q, get_self_list('') compares the
          # bigint index id against '' ("invalid input syntax for type bigint"). rest.py catches that,
          # but pgpool load-balances the failing SELECT to one backend only, so the next SAVEPOINT hits
          # "kind mismatch among backends" and pgpool kills the session. An empty q can never match an
          # id, so skip the query instead.
          # /api/index/ の 500 対策。q が空だと get_self_list('') が bigint の index id を '' と比較して
          # SQL エラーになる。rest.py 側は例外を握るが、pgpool ではその SELECT が片方のバックエンドに
          # だけ振られるため、続く SAVEPOINT で kind mismatch となり pgpool がセッションを切る。
          # 空の q は id に一致し得ないので、そもそもクエリを投げない。
          sed -i "s/paths = Indexes.get_self_list(q, community_id)/paths = Indexes.get_self_list(q, community_id) if q and str(q).isdigit() else []/" /code/modules/weko-search-ui/weko_search_ui/rest.py 2>/dev/null || true
          # App-layer fix: the same KeyError on 'aggregations' as above, on /api/index/. When the index id
          # in q does not exist, Elasticsearch returns no aggregations and rest.py raises KeyError -> 500.
          # /api/index/ 側の 'aggregations' KeyError 対策（上の /api/records と同種）。q のインデックス ID が
          # 存在しないと Elasticsearch が aggregations を返さず、rest.py が KeyError になり 500 になる。
          sed -i 's/agp = rd\["aggregations"\]\["path"\]\["buckets"\]/rd.setdefault("aggregations", {}).setdefault("path", {}).setdefault("buckets", []); agp = rd["aggregations"]["path"]["buckets"]/' /code/modules/weko-search-ui/weko_search_ui/rest.py 2>/dev/null || true
          # App-layer fix: avoid the 500 on /api/index/?q=<non-numeric>. The value is passed straight into a
          # bigint column ("invalid input syntax for type bigint"), which through pgpool kills the session
          # the same way as above. A non-numeric id can never match, so return an empty list.
          # 非数値の q による 500 対策。値がそのまま bigint 列に渡されて SQL エラーになり、pgpool 経由では
          # 上と同じくセッションごと切られる。数値でない ID は一致し得ないので空リストを返す。
          sed -i 's/^    def get_child_list_recursive(cls, pid, with_deleted=False):/&\n        if not str(pid).isdigit():\n            return []/' /code/modules/weko-index-tree/weko_index_tree/api.py 2>/dev/null || true
          # populate static from static.org when empty
          mkdir -p \$INST/static \$INST/data/tmp
          if [ -z "\$(ls -A \$INST/static 2>/dev/null)" ] && [ -d \$INST/static.org ]; then
            cp -r \$INST/static.org/. \$INST/static/ 2>/dev/null || true
          fi
          mkdir -p /cores && cd /cores
          exec uwsgi --ini \$INST/conf/uwsgi.ini
        envFrom:
        - { configMapRef: { name: $NAME-config } }
        - { secretRef: { name: $NAME-secret } }
        ports: [ { containerPort: 5000 } ]
        resources: { requests: { memory: "700Mi", cpu: "250m" }, limits: { memory: "2Gi", cpu: "4" } }
        readinessProbe: { tcpSocket: { port: 5000 }, initialDelaySeconds: 30, periodSeconds: 15, failureThreshold: 40 }
        volumeMounts:
        - { name: cores, mountPath: /cores }
        - { name: conf, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/conf }
        - { name: data, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/data }
        - { name: static, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/static }
      - name: worker
        image: $WEKO_IMAGE
        imagePullPolicy: Never
        command: ["/bin/bash","-c"]
        args:
        - |
          set -e
          ulimit -c 0 || true
          export LANG=C.UTF-8 LC_ALL=C.UTF-8
          export PATH=/home/invenio/.virtualenvs/invenio/bin:\$PATH
          INST=/home/invenio/.virtualenvs/invenio/var/instance
          # App-layer fix: avoid the KeyError on /api/records
          sed -i "s/aggs = data\['aggregations'\]/aggs = data.get('aggregations', {})/" /code/modules/weko-search-ui/weko_search_ui/utils.py 2>/dev/null || true
          # App-layer fix: same /api/index/ fixes as the web container, to keep both copies of the code identical
          sed -i "s/paths = Indexes.get_self_list(q, community_id)/paths = Indexes.get_self_list(q, community_id) if q and str(q).isdigit() else []/" /code/modules/weko-search-ui/weko_search_ui/rest.py 2>/dev/null || true
          sed -i 's/agp = rd\["aggregations"\]\["path"\]\["buckets"\]/rd.setdefault("aggregations", {}).setdefault("path", {}).setdefault("buckets", []); agp = rd["aggregations"]["path"]["buckets"]/' /code/modules/weko-search-ui/weko_search_ui/rest.py 2>/dev/null || true
          sed -i 's/^    def get_child_list_recursive(cls, pid, with_deleted=False):/&\n        if not str(pid).isdigit():\n            return []/' /code/modules/weko-index-tree/weko_index_tree/api.py 2>/dev/null || true
          rm -f /home/invenio/celeryd.pid
          exec celery worker --pidfile /home/invenio/celeryd.pid \
            --schedule=/home/invenio/celerybeat-schedule \
            -c 1 -A invenio_app.celery --loglevel=INFO -B
        envFrom:
        - { configMapRef: { name: $NAME-config } }
        - { secretRef: { name: $NAME-secret } }
        resources: { requests: { memory: "500Mi", cpu: "250m" }, limits: { memory: "1536Mi", cpu: "2" } }
        volumeMounts:
        - { name: conf, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/conf }
        - { name: data, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/data }
        - { name: static, mountPath: /home/invenio/.virtualenvs/invenio/var/instance/static }
      volumes:
      - { name: nginx-conf, configMap: { name: weko-nginx-conf } }
      - { name: cores, emptyDir: { sizeLimit: 2Gi } }
      # static is Pod-local (emptyDir), as in production
      - { name: static, emptyDir: {} }
      - { name: conf, persistentVolumeClaim: { claimName: $NAME-conf } }
      - { name: data, persistentVolumeClaim: { claimName: $NAME-data } }
      - { name: shib, persistentVolumeClaim: { claimName: $NAME-shib } }
      - { name: nginx-etc, persistentVolumeClaim: { claimName: $NAME-nginx-pvc } }
---
apiVersion: v1
kind: Service
metadata: { name: $NAME-nginx, namespace: weko3 }
spec:
  selector: { app: $NAME-web }
  ports: [ { port: 80, targetPort: 80 } ]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: $NAME-ingress
  namespace: weko3
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "0"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"${TLS_ANNOTATIONS}
spec:
  ingressClassName: nginx${TLS_BLOCK}
  rules:
  - host: "$HOST"
    http:
      paths:
      - path: /
        pathType: Prefix
        backend: { service: { name: $NAME-nginx, port: { number: 80 } } }
YAML
  echo "generated: $f"
}

grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$TFILE" | while read -r NAME DBNAME HOST EMAIL PASS INIT CACHE_DB SESSION_DB CELERY_DB _; do
  gen_one "$NAME" "$DBNAME" "$HOST" "$EMAIL" "$PASS" "$CACHE_DB" "$SESSION_DB" "$CELERY_DB"
done
