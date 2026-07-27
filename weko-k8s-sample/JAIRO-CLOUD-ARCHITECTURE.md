# JAIRO Cloud（weko-k8s）本番デプロイ構成まとめ

[RCOSDP/weko-k8s](https://github.com/RCOSDP/weko-k8s) リポジトリの構造から読み取れる
**JAIRO Cloud 相当の本番デプロイ構成**の要約。
（※ 公開リポジトリのマニフェスト／スクリプトからの推定。バージョンはリポジトリ記載値。
実運用の設定と細部は異なりうる。本書末尾に今回の kind 簡素化構成との対比を付す。）

---

## 1. 実行基盤

| 項目 | 内容 |
|---|---|
| クラウド | Oracle Cloud Infrastructure（OCI） |
| Kubernetes | **OKE**（Oracle Kubernetes Engine, マネージド） |
| ノード | 複数ノードプール（`nodepool-cloud-init`）。`nodeType` ラベル（`WEKO`/`DATA` 等）で用途分離 |
| イメージ取得 | **OCIR**（Oracle Container Registry）。`imagePullSecrets: ocir-secret` |
| 共有ストレージ | **OKE File Storage（FSS / NFS）**。`storageClassName: nfs` の PV で `config`/`data`/`static`/`nginx`/`shibboleth` をテナント別にマウント |
| オブジェクトストレージ | **OCI Object Storage（S3互換）**。バックアップ格納。`scripts/as`（boto3）でバージョニングバケット管理 |
| マニフェスト管理 | `kustomize`（各コンポーネント `base` / `components` / `overlay` 構成） |

---

## 2. 名前空間とコンポーネント

| Namespace | 役割 | 主なコンポーネント（リポジトリ記載イメージ） |
|---|---|---|
| `weko3` | **weko 本体（テナントごとの Web）** | init(jinja2) + nginx(Shibboleth SP + SSL + WAF) + web(uwsgi) + worker(celery) |
| `weko3pg` | **PostgreSQL（HA）** | Zalando **postgres-operator v1.13.0** + **Spilo-13**(2.0-p6) + **pgpool2 4.2.2** + **pgbouncer**(master-16) + exporter(`pgpool2_exporter`, `postgres-exporter`) + `weko-pgdump` + `weko-stats-rotate` |
| `weko3es` | **Elasticsearch** | `weko_elasticsearch:v6.8.23`（ES6 + kuromoji）+ スナップショット取得（`essnapshooter`） |
| `weko3re` | **Redis（HA）** | `weko_redis:v1.0` + `weko_sentinel:v1.0`（Sentinel 構成）+ `redis_exporter` |
| `weko3ra` | **RabbitMQ** | `rabbitmq:4.0.9`（quorum queue） |
| `nginx-ingress` / `nginx-ingress-internal` | **Ingress + WAF（外部/内部の2系統）** | **F5 NGINX Plus Ingress**（`nginx-plus-ingress`）+ **NGINX App Protect**（`appprotect.f5.com` CRD, `weko-policy`/`nothreat-policy`/apdos） |
| `logging` | **ログ集約** | `weko_fluentd:v0.0.1` + fluentd-celery + Elasticsearch/Kibana 7.16.2（ログ用・本体ES6とは別）+ `kubernetes-event-exporter` |
| `monitoring` | **監視** | **kube-prometheus-stack**（Prometheus/Grafana/Alertmanager）+ `k8s-sidecar` + `dcgm-exporter`(GPU) + `oauth2-proxy`/`keycloak-proxy`(画面認証) |
| `maintenance` / `maintenance-pod` | 運用作業用 Pod | `maintenance_pod:latest` |
| `contents-backup` | **コンテンツ backup** | `rclone:1.69` → Object Storage |
| `metrics-server` | HPA/`kubectl top` 用 | metrics-server |

---

## 3. weko 本体 Pod（テナント1つ＝1 Deployment）

```
Pod (nodeType=WEKO)
 ├ initContainer: jinja2 で instance.cfg → invenio.cfg 生成
 ├ nginx : Shibboleth SP + TLS終端 + NGINX App Protect(WAF) + 静的配信 + uwsgi_pass
 ├ web   : uwsgi (invenio_app.wsgi, socket:5000)
 └ worker: celery worker (-B, ビート内包)
volumes: OKE FSS(NFS) の nginx / shibboleth / config / data / static(+PVC)
imagePullSecrets: ocir-secret
```

- 設定は `configmap`(接続先・機能フラグ) + `secret`(認証情報・鍵) を `envFrom`。
- Redis は **redissentinel** モード（`CACHE_TYPE=redissentinel`, `CACHE_REDIS_SENTINELS=[("weko-sentinel-service.weko3re",26379)]`）。
- 認証は **Shibboleth / 学認（GakuNin）SAML** 連携（`SHIB_IDP_LOGIN_URL` 等）。

---

## 4. マルチテナント方式（本番）

テナント定義ファイル `repositories_file`（1行＝1リポジトリ）を入力に、スクリプトで一括生成・展開する。

| 列（抜粋） | 用途 |
|---|---|
| W2FQDN / W3FQDN | リポジトリ識別子 / 公開 FQDN |
| account / passwd | 初期管理者 |
| CNRI / DOIFREE | ハンドル・DOI 付与方式 |
| memory req/limit, uwsgi rss/process | リソース調整 |
| redis DB番号（cache/session/celery） | テナント別 Redis DB 分離 |
| 集計イベント時刻 | 統計バッチ |

**生成〜展開のスクリプト連携:**
```
make_volumes.sh          … FSS 上にテナント別 nginx/shib/config/data ディレクトリを生成
make_weko_manifests.sh   … テンプレ→テナント別マニフェスト + SSL証明書(openssl) を生成
make_rabbitmq_vhost.sh   … rabbitmqctl add_vhost "<DOMAIN>/" + set_permissions
deploy_weko.sh           … kubectl apply + tls secret(<domain>-cert) 作成、ノード数に応じ逐次展開
```

**テナントごとに分離されるもの:**

| 分離対象 | キー |
|---|---|
| DB | `INVENIO_POSTGRESQL_DBNAME = REPNAME`（PostgreSQL 内の DB） |
| 検索インデックス | `SEARCH_INDEX_PREFIX = REPNAME`（同一 ES クラスタ内で接頭辞分離） |
| メッセージング | RabbitMQ vhost `<DOMAIN>/` |
| キャッシュ/セッション | Sentinel 共有 Redis の DB 番号（cache/session/celery を別番号） |
| 公開/TLS | FQDN + テナント別 SSL 証明書（tls secret）+ WAF ポリシー |
| ストレージ | FSS 上のテナント別ディレクトリ |

> ※ バックエンド（PostgreSQL / Elasticsearch / Redis / RabbitMQ）は**全テナントで共有**し、
> 上記キーで論理分離する。これは今回の kind 構成と同じ考え方（今回は Redis のみテナント別インスタンス）。

---

## 5. バックアップ / 運用

- **DB**: `weko-pgdump`（`pg_dump`, alembic_version 除外）→ Object Storage。復元は `restore_db*.sh`。
- **ES**: スナップショット（`essnapshooter`）→ Object Storage。復元は `restore_es*.sh`。
- **コンテンツ**: `rclone`（`contents-backup`）→ Object Storage。
- **バケット管理**: `scripts/as`（boto3, バージョニング + ライフサイクル/非現行世代の失効）。
- **メンテナンス**: `scripts/maintenance/` に OKE ノードプールの drain / upgrade、各バックエンドの再デプロイ、ログ形式変更、キュー purge 等。
- **WAF 管理**: `scripts/waf_management/`（証明書・アクセス/保護ルールの一括投入。OCI/F5 連携）。

---

## 6. 今回の kind 簡素化構成との対比

| 項目 | JAIRO Cloud（OKE 本番） | 今回（kind） |
|---|---|---|
| 基盤 | Oracle OKE（マネージド・複数ノードプール） | kind（単一ホスト・3ノード） |
| アーキ | x86_64（amd64 ネイティブ） | **arm64 ネイティブ**（weko本体/ES も arm64 ビルド。emulation は不使用） |
| マルチテナント | `repositories_file` → スクリプト生成（多数） | `tenants.txt` → `gen-tenant.sh`（2テナント） |
| PostgreSQL | postgres-operator(Spilo) HA + pgpool + pgbouncer | **Zalando postgres-operator + Patroni 3ノードHA**（spilo-17, arm64）＋ **pgpool**（pgbouncer は未） |
| Elasticsearch | `weko_elasticsearch:v6.8.23`（+スナップショット） | **arm64ネイティブ 6.8.23 の3ノードクラスタ**（本物kui.txt/kuromoji/repository-s3） |
| Redis | `weko_redis`+`weko_sentinel`（Sentinel HA, redissentinel） | **Redis Sentinel HA**（master+replica×2+sentinel×3, redissentinel） |
| RabbitMQ | `4.0.9` クラスタ | **RabbitMQ Cluster Operator で 4.0.9 の3ノードクラスタ** |
| Ingress/WAF | **F5 NGINX Plus + App Protect**（外部/内部） | `ingress-nginx`（OSS。WAFは未） |
| 前段 nginx | Shibboleth SP + SSL + WAF | 標準 nginx + `uwsgi_pass` のみ |
| 共有 FS | OKE File Storage（NFS） | テナント別 conf/data に NFS(RWX)、バックエンドは PVC（kind local-path） |
| バックアップ | Object Storage（pgdump/snapshot/rclone） | **MinIO(S3)** + pg_dumpall バックアップ実演 |
| ログ | fluentd → ES/Kibana 7.16 | `kubectl logs` |
| 監視 | kube-prometheus-stack + Grafana + 各 exporter | なし（metrics-server 任意） |
| 認証 | Shibboleth / 学認（GakuNin）SAML | ローカルアカウント |
| イメージ取得 | OCIR（`ocir-secret`） | Docker Hub + 自前arm64ビルド + `kind load` |

> **要点**: アプリ層・**HAクラスタ化(operator方式)・Sentinel・pgpool・S3・永続化**まで本番と同じ構造を再現。
> 残る主な差分は **pgbouncer・WAF・監視/ログ・認証(学認)** といった運用周辺と、
> **OKE(x86) → kind(arm64ネイティブ)** の基盤差（emulation は排除済み）。
