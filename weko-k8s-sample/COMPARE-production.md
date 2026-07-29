# kind 検証環境と JAIRO Cloud 本番環境の差異カタログ

`weko-k8s-sample`（kind 上の検証環境）と **JAIRO Cloud 本番環境**
（[`RCOSDP/weko-k8s`](https://github.com/RCOSDP/weko-k8s)、ローカル: `~/weko-k8s`）の差異を、
**全レイヤについて**対照する。「どこが同じで、どこが違い、なぜ違うのか」を確認するための参照用ドキュメント。

移行の作業順序については [PRODUCTION-ROADMAP.md](PRODUCTION-ROADMAP.md) を参照。
英語版: [COMPARE-production.en.md](COMPARE-production.en.md)

---

## 凡例

各項目の差異を次の4種に分類する。**この分類が本ドキュメントの主眼**である。

| 記号 | 分類 | 意味 | 本番構築時 |
|---|---|---|---|
| ✅ | **一致** | 本番と同じものを使っている | 変更不要 |
| 🔵 | **簡略化** | 検証に不要なため意図的に簡略化した | 本番仕様に戻す |
| 🟡 | **代替物** | kind の制約により別物で代用している | **必ず本物に置換**（放置すると起動しない／破綻する） |
| 🔴 | **未実装** | 本番にあるがサンプルに無い | 新規に構築 |

🟡 が最も危険である。「動いているように見えるが本番では通用しない」ものだからである。

---

## 0. 比較対象の定義

| | kind 検証環境 | JAIRO Cloud 本番環境 |
|---|---|---|
| リポジトリ | `weko-workshop/weko-k8s-sample` | `RCOSDP/weko-k8s` |
| ディレクトリ | `k8s-weko-amd64`（amd64）/ `k8s-weko`（arm64） | `deploy/` + `scripts/` |
| 構成管理 | 素の manifest + 命令的スクリプト1本 | kustomize `base` / `components` / `overlay` |
| 環境の面数 | 1（kind） | 6（`oci-af` `oci-ams` `oci-at` `oci-it` `oci-pr` `oci-st`） |
| 想定規模 | 1台のサーバ、テナント1〜8 | 商用リポジトリ多数 |
| 本書での「本番」 | — | 特記なき限り `oci-pr` overlay の値 |

---

## 1. クラスタ基盤層

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| 実行基盤 | kind（Docker in Docker） | OCI **OKE**（マネージド k8s） | 🟡 |
| クラスタ作成 | `deploy-amd64.sh:96-119`（`kind create cluster`、3回リトライ） | OCI CLI / Terraform、`scripts/maintenance/upgrade_oke_*.sh` | 🟡 |
| k8s バージョン | **v1.34**（`kindest/node:v1.34.0`、`prereq-amd64.sh:39-42`） | **v1.32.1**（`scripts/maintenance/oke_param_env.sh` の `K8S_VERSION`） | 🟡 検証環境の方が新しい |
| kind バージョン | v0.30.0（`prereq-amd64.sh:9`） | — | 🟡 |
| ノード構成 | 1 control-plane + 2 worker（`kind-weko-cluster.yaml`） | OKE ノードプール、shape `VM.Standard.E4.Flex` | 🟡 |
| ノード種別ラベル | **2種**: `nodeType=WEKO` / `DATA` | **8種**: `WEKO` `PGO` `PGPOOL` `ES` `RA` `RE` `SE` `LOG`（`scripts/k8s_command.sh:29-44`） | 🔵 |
| 配置指定の方式 | Pod spec に `nodeSelector` 直書き（7箇所） | kustomize component で `nodeAffinity` を注入（`elasticsearch/components/oci/elasticsearch_patch.yaml:10-20`） | 🔵 |
| CNI | kindnet（kind 既定） | OKE の CNI | 🟡 |
| ホスト準備 | `prereq-amd64.sh`（docker / kubectl / kind / sysctl） | ノードイメージと shape で吸収 | 🟡 |
| sysctl `vm.max_map_count` | ホスト（`prereq-amd64.sh:56-62`）**＋ privileged initContainer**（`13-elasticsearch.yaml:46-49`） | ノード側のみ（initContainer は**存在しない**） | 🟡 |
| metrics-server | **あり**（v0.9.0、`deploy-amd64.sh:266-269`）。kind の kubelet 証明書はクラスタ CA 署名ではないため `--kubelet-insecure-tls` を後付けパッチで注入 | `deploy/metrics-server/` | ✅ **一致**（起動オプションのみ差） |

> **🟡 の核心**: `kind create cluster` と `extraPortMappings` に依存した設計なので、
> クラスタ作成ステップは本番では**丸ごと不要**になる。また k8s バージョンが検証(1.34) > 本番(1.32) で
> 逆転しているため、サンプルで動いた API が本番で使えない可能性がある。

---

## 2. イメージ供給層

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| イメージの入手 | ローカルで `docker build`（WEKO / ES / nginx の3種、`deploy-amd64.sh:126-163`） | CI でビルド → **OCIR** に push | 🟡 |
| ノードへの配布 | **`kind load docker-image`**（4回、`deploy-amd64.sh:131,149,163,168`） | kubelet が registry から pull | 🟡 |
| `imagePullPolicy` | **`Never`**（9箇所: `13-elasticsearch.yaml:53`, `62-pgpool.yaml:80`, `gen-tenant.sh`×7） | `Always`（`deploy-web.yaml:44,74,90`） | 🟡 |
| `imagePullSecrets` | なし | `ocir-secret`（全 Pod、`deploy-web.yaml:113-114`） | 🟡 |
| イメージ名の管理 | シェル変数に直書き（`WEKO_IMAGE` 等） | kustomize `images:` で overlay ごとに置換（`postgresql/overlay/oci-pr/kustomization.yaml:19-30`） | 🔵 |
| WEKO 本体 | **ソースから毎回ビルド**（`WEKO_SRC` を git clone / pull） | ビルド済みイメージをタグ指定で pull | 🔵 |

> **🟡 の核心**: `kind load` + `imagePullPolicy: Never` は「レジストリを使わない」ための代替物である。
> マルチノードの本番では kubelet が pull できず、**全 Pod が ImagePullBackOff になる**。

---

## 3. ストレージ層

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| ブロック用 StorageClass | **`standard`**（kind 同梱 local-path、**ノードローカル**）<br>6箇所で使用 | **`oci-bv`**（OCI Block Volume）<br>`elasticsearch/components/oci/elasticsearch_patch.yaml:24` | 🟡 |
| 共有 FS の実体 | **クラスタ内 nfs-ganesha Pod**（`60-nfs-server.yaml`） | **外部 NFS**（OCI File Storage） | 🟡 |
| NFS サーバの指定 | `clusterIP: 10.96.0.99` を**ハードコード**（`60-nfs-server.yaml:61`）<br>`NFS_SERVER` 既定値も同じ（`gen-tenant.sh:19`） | `nfs.server: 10.76.0.12`（`weko/manifest_template/volume-pv.yaml:17,36,70,88`） | 🟡 |
| 共有 FS の accessModes | **ReadWriteMany**（`gen-tenant.sh:163,184,207,231`） | **ReadWriteOnce**（`volume-pv.yaml:11,30,64,82`） | 🔵 |
| 共有 FS の容量 | config 1Gi / data 5Gi / shib 1Gi / nginx 1Gi | **各 50Gi** | 🔵 |
| 静的 PV の SC 名 | `nfs-static`（`no-provisioner`） | `nfs` | 🔵 |
| PV の reclaimPolicy | `Retain` | `Retain` | ✅ |
| 共有 FS のディレクトリ構成 | `/fs-nginx` `/fs-shibboleth` `/fs-config` `/fs-data` | 同一 | ✅ |
| 共有 FS の可用性 | `replicas: 1` + `Recreate` = **SPOF** | マネージド NFS（冗長） | 🟡 |
| NFS Pod の特権 | `capabilities: [DAC_READ_SEARCH, SYS_ADMIN]`（`60-nfs-server.yaml:117-119`） | 不要 | 🟡 |
| ディレクトリ作成方法 | busybox seed Pod 経由（`provision-nfs.sh:38-60`） | ホストから直接 `mkdir`（`scripts/make_volumes.sh`） | 🔵 |
| オブジェクトストレージ | **MinIO**（`40-minio.yaml`、`replicas: 1`、600Gi RWO） | **OCI Object Storage**（S3互換、クラスタ外） | 🟡 |

> **🟡 の核心**: 共有 FS が最大の差異である。`60-nfs-server.yaml` は
> 「本番の OKE File Storage をクラスタ内で模擬するための代替物」であり、
> Service CIDR が `10.96.0.0/16` でない本番クラスタでは**そもそも作成に失敗する**。

---

## 4. ネットワーク・外部公開層

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| Ingress Controller | **ingress-nginx OSS** v1.12.1、`provider/kind` マニフェスト（`deploy-amd64.sh:120`） | **NGINX Plus IC**（商用）+ **App Protect**<br>`ingress/base/deployment/nginx-plus-ingress.yaml`<br>イメージ: `nginx-plus-ingress-nap:5.3.4-SNAPSHOT` | 🟡 |
| Ingress Controller の冗長化 | 1（provider/kind 既定） | **replicas: 2**（`ingress/overlay/oci-pr/kustomization.yaml`） | 🔵 |
| 外部公開の方式 | kind の **`extraPortMappings`** でホストの 80/443 を借用（`kind-weko-cluster.yaml:15-21`） | **`type: LoadBalancer`** + `loadBalancerIP: 158.101.66.16` + `externalTrafficPolicy: Local`（`ingress/base/nginx-plus-lb.yaml`） | 🟡 |
| WAF | **なし** | App Protect ポリシー（`ingress/components/ap-config/`）+ `scripts/waf_management/` | 🔴 |
| ホスト名 | `tenant1.localhost`（`tenants.txt:7`） | 実 FQDN（`*.repo.nii.ac.jp` 等） | 🟡 |
| 内部向け Ingress | なし | `deploy/ingress-nginx-internal/` | 🔴 |
| ingressClassName | `nginx` | `nginx` | ✅ |
| Ingress annotation | `proxy-body-size: "0"`, `proxy-read-timeout: "3600"`（`gen-tenant.sh:430-431`） | `rewrite-target`, `backend-protocol: HTTPS`, `ssl-services`, `appprotect.f5.com/*` 一式（`weko/manifest_template/ingress.yaml`） | 🔵 |

### 4-1. TLS の構成 — ホップ数が違う

**検証環境は1ホップ、本番は2ホップ**である。

| | kind 検証環境 | 本番環境 |
|---|---|---|
| ホップ1 終端 | Ingress（ingress-nginx） | **NGINX Plus IC**（App Protect の検査もここ） |
| ホップ1 証明書 | cert-manager が自己署名 root CA から自動発行（`61-tls-ca.yaml`） | **実証明書**。テナント毎 Secret `<domain>-cert`（`scripts/deploy_weko.sh:64-66` で投入）。`make_weko_manifests.sh` の `openssl req -x509` は雛形のプレースホルダで、運用時に実証明書へ差し替えている |
| ホップ2 | **なし**（backend へは平文 HTTP:80） | **あり**。`backend-protocol: "HTTPS"` + `nginx.org/ssl-services` で再暗号化、backend Service ポートは 443 |
| ホップ2 終端 | — | テナントの nginx コンテナ（`weko.conf:11` `listen 443`） |
| ホップ2 証明書 | — | `weko/nginx_template/server.crt` / `server.key`（`weko.conf:14-15`）<br>**自己署名**（`CN=*`, `O=Internet Widgits Pty Ltd`）、**2017-01-21 失効済み**、`make_volumes.sh:43` が全テナントに同じファイルを配るため**全テナント共通** |
| ホップ2 の検証 | — | **していない**（`proxy_ssl_verify` 相当の設定なし） |

判定: ホップ1 の証明書方式は 🟡（自己署名 CA → 実証明書）、ホップ2 の存在自体が 🔴（未実装）。

> 本番のホップ2 は「WAF より内側の経路を平文にしないための暗号化」であって、
> 証明書による相手認証は行っていない。移行時に**この設計を継承するか、内部経路にも正しい証明書を配って
> 検証を有効にするか**の判断が要る。

---

## 5. ミドルウェア層

### 5-1. バージョンの一致状況

| ミドルウェア | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| PostgreSQL | **17**（`51-postgresql-ha.yaml:16`）<br>spilo `ghcr.io/zalando/spilo-17:4.0-p2`（`deploy-amd64.sh:53`） | **12**（`postgresql/base/postgresql.yaml:15`）<br>spilo `spilo-13:2.0-p6`（`postgres-operator-config.yaml:16`） | 🟡 **メジャー5世代差** |
| postgres-operator | v1.14.0（`deploy-amd64.sh:54,177`） | v1.13.0（`postgres-operator.yaml:23`） | 🔵 |
| pgpool | `pgpool/pgpool:4.2.2` | `pgpool/pgpool:4.2.2` | ✅ **完全一致** |
| Elasticsearch | `weko-elasticsearch:6.8.23`（weko ソースからビルド） | `weko_elasticsearch:v6.8.23`（OCIR） | ✅ **バージョン一致**（入手方法のみ差） |
| RabbitMQ | `rabbitmq:4.0.9-management` | `rabbitmq:4.0.9` | ✅ **バージョン一致** |
| RabbitMQ operator | cluster-operator **latest**（`deploy-amd64.sh:173`） | cluster-operator（バージョン固定） | 🔵 バージョン固定していない点が差 |
| Redis | `redis:6.2`（公式イメージ） | `weko_redis:v1.0` / `weko_sentinel:v1.0`（独自イメージ） | 🔵 |
| cert-manager | v1.16.2（`deploy-amd64.sh:171`） | **使用していない** | 🟡 |
| MinIO | `minio/minio:RELEASE.2025-04-08...` | **使用していない**（OCI Object Storage） | 🟡 |

> **⚠️ 要注意**: `51-postgresql-ha.yaml:5` のコメントは「本番の **PG13** に合わせるなら spilo-13 を指定」と
> 書いているが、現行の本番 IaC は CR で `version: "12"` を指定している
> （Spilo イメージは複数メジャーを内包するため、`spilo-13` イメージ上で PG12 が起動する）。
> **サンプルのコメントが本番の現状と食い違っている**ので、データ移行を伴う場合は本番の実機で要確認。

### 5-2. 台数・サイジング

| コンポーネント | kind 検証環境 | 本番 `base` | 本番 `oci-pr` | 判定 |
|---|---|---|---|---|
| PostgreSQL | 2 inst / 50Gi<br>shared_buffers 1GB / max_conn 200<br>req 500m-1Gi, lim 4-2560Mi | 1 inst / 10Gi<br>500MB / 50 | **3 inst / 2500Gi**<br>12000MB / **11500**<br>req **25cpu-32Gi**, lim **30cpu-60Gi** | 🔵 |
| pgpool | **1**（SPOF） | 1 | **3** | 🔵 |
| Elasticsearch | 2 | 1 | **13** | 🔵 |
| RabbitMQ | 3 | 1 / 2Gi | **3 / 50Gi**<br>req 6cpu-24Gi, lim 7cpu-30Gi | 🔵 |
| Redis | 3 + Sentinel 3 | Sentinel 構成 | **2 + Sentinel 3** | 🔵 |
| MinIO | 1 / 600Gi（SPOF） | — | — | 🟡 |
| WEKO web | テナント毎 **1** | 1 | 1（メモリは `repositories_file` で個別指定） | ✅ |
| Ingress Controller | 1 | — | 2 | 🔵 |

### 5-3. HA を成立させる仕組み

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| `PodDisruptionBudget` | **なし** | **なし**（WEKO 本体には未設定。kube-prometheus-stack の同梱分のみ） | ✅ 同条件 |
| `podAntiAffinity` | **なし** | **Redis のみ**（`redis/components/oci/redis_patch.yaml`） | 🔵 |
| `topologySpreadConstraints` | なし | なし | ✅ 同条件 |
| `NetworkPolicy` | **なし** | **なし**（WEKO 本体には未設定） | ✅ 同条件 |
| `HorizontalPodAutoscaler` | なし | なし（metrics-server は導入済み） | ✅ 同条件 |
| PG の同期レプリケーション | `synchronous_mode: true` | `synchronous_mode: true` | ✅ |
| `password_encryption` | `md5`（pgpool 4.2.2 の制約、`51-postgresql-ha.yaml:19-20`） | 同じ制約（pgpool 4.2.2） | ✅ **同じ技術的負債** |

> **重要**: PDB / NetworkPolicy / topologySpread の不在は「サンプルの手抜き」ではなく
> **本番も同じ状態**である。「本番と同等でよい」のか「本番ごと改善する」のかは別の判断になる。

### 5-4. チューニング値・タイムアウトの差

サイジング（CPU / メモリ / 台数）は 5-2 に譲り、ここでは **「規模を揃えても残る設定差」** を見る。
🔵 は数を増やせば済むもの、**🟡 は値の意味が違うもの**（規模を合わせても挙動が変わる）。

#### PostgreSQL（`postgresql.spec.postgresql.parameters`）

| パラメータ | kind 検証環境 | 本番 `base` | 本番 `oci-pr` | 判定 |
|---|---|---|---|---|
| `wal_sender_timeout` | **未指定**（既定 60s） | **`0`**（無効化） | 同左 | 🟡 |
| `wal_receiver_timeout` | **未指定**（既定 60s） | **`0`**（無効化） | 同左 | 🟡 |
| `max_standby_streaming_delay` | **未指定**（既定 30s） | **`-1`**（無制限） | 同左 | 🟡 |
| `shared_buffers` | `1GB` | `500MB` | `12000MB` | 🔵 |
| `max_connections` | `200` | `50` | `11500` | 🔵 |
| `work_mem` | `16MB` | `8MB` | 同左 | 🔵 |
| `temp_file_limit` | 未指定（無制限） | `1000000`（≒1GB） | 同左 | 🟡 |
| `wal_keep_segments` / `wal_buffers` / `max_wal_senders` | 未指定 | `8` / `16MB` / `10` | 同左 | 🔵 |
| `max_wal_size` | 未指定（既定 1GB） | `1GB` | `4GB` | 🔵 |
| `max_worker_processes` / `max_parallel_workers` / `_per_gather` | 未指定 | `2` / `2` / `2` | `14` / `8` / `8` | 🔵 |
| `log_statement` 等のログ系 | 未指定（spilo 既定） | 全て `off` / `none` | 同左 | 🔵 |
| `password_encryption` | `md5` | （pgpool 4.2.2 の制約により同じ） | 同左 | ✅ |

> **🟡 の核心**: 本番は **レプリケーション系のタイムアウトを軒並み無効化**している
> （`wal_sender_timeout=0` / `wal_receiver_timeout=0` / `max_standby_streaming_delay=-1`）。
> 大量データの初期同期や長時間クエリでレプリカが切り離されるのを避けるためであり、
> **サンプルは既定値のまま**なので「サンプルでは起きない切断が本番では起きる／その逆」が発生し得る。
> `temp_file_limit` も同様で、本番は暴走クエリを 1GB で打ち切るがサンプルは無制限。

#### pgpool（`PGPOOL_PARAMS_*` 形式の ConfigMap）

| パラメータ | kind 検証環境 | 本番 | 判定 |
|---|---|---|---|
| `NUM_INIT_CHILDREN` / `MAX_POOL` | `32` / `4` | `32` / `4` | ✅ |
| `CHILD_LIFE_TIME` / `CHILD_MAX_CONNECTIONS` | `300` / `0` | `300` / `0` | ✅ |
| `CONNECTION_LIFE_TIME` | `0`（無期限） | `0` | ✅ |
| `CLIENT_IDLE_LIMIT` | `900`（15分で切断） | `900` | ✅ |
| `CONNECTION_CACHE` / `LOAD_BALANCE_MODE` | `on` / `on` | `on` / `on` | ✅ |
| `SR_CHECK_PERIOD` | `0`（ストリーミングレプリケーションチェック無効） | `0` | ✅ |
| `BACKEND_FLAG0` | `ALWAYS_PRIMARY\|DISALLOW_TO_FAILOVER` | 同左 | ✅ |
| `FAILOVER_ON_BACKEND_ERROR` | `off` | `off` | ✅ |
| `ENABLE_POOL_HBA` | `on` | `on` | ✅ |
| バックエンドのホスト名 | `weko-postgresql` / `weko-postgresql-repl` | 同名（namespace が `weko3pg`） | 🔵 |
| `RELCACHE_SIZE` / `DEBUG_LEVEL` | `256` / `0` | 未指定（既定） | 🔵 |

> **pgpool はほぼ完全一致である。** 接続プール周りの設定差は事実上存在せず、
> 台数（1 → 3）と接続先 namespace だけを直せばよい。

#### Elasticsearch（`elasticsearch-configmap`）

| 設定 | kind 検証環境 | 本番 `base` | 本番 `oci-pr` | 判定 |
|---|---|---|---|---|
| `ES_JAVA_OPTS` ヒープ | `-Xms2g -Xmx2g` | `-Xms1g -Xmx1g` | **`-Xms30g -Xmx30g`** | 🔵 |
| 新世代サイズ | **未指定**（JVM 既定） | `-XX:NewSize=300m -XX:MaxNewSize=300m` | `-XX:NewSize=16g -XX:MaxNewSize=16g` | 🟡 |
| `-Dlog4j2.formatMsgNoLookups=true` | **なし** | **あり** | あり | 🟡 **Log4Shell 緩和策** |
| `discovery.zen.minimum_master_nodes` | `2`（2台構成） | `1` | `7`（13台構成） | 🔵 |
| `discovery.zen.ping.unicast.hosts` | Service 名 1件 | 1件 | **13件を列挙** | 🔵 |
| `cluster.name` | 既定 | `k8s-cluster` | 同左 | 🔵 |

> **🟡 の核心**: ES 6.8.23 は Log4j 2.x を同梱しており、本番は
> **`-Dlog4j2.formatMsgNoLookups=true` を必ず付けている**が、サンプルには無い。
> 検証環境は外部公開しないので実害は無いが、**本番仕様として移す際は必須**である。
> 新世代サイズの固定も本番の意図的なチューニング（GC 挙動の安定化）で、サンプルには入っていない。

#### RabbitMQ（`RabbitmqCluster.spec.rabbitmq.additionalConfig`）

| 設定 | kind 検証環境 | 本番 | 判定 |
|---|---|---|---|
| `consumer_timeout` | **未指定**（既定 **30分**） | **`10800000`（3時間）** | 🟡 **最重要** |
| `log.console.level` | `warning` | 未指定（既定 `info`） | 🔵 |
| startupProbe | **独自に差し替え**（operator 最新版の `reached-target-cluster-size` API が 4.0.9 に無く 404 になるため `rabbitmq-diagnostics` ベースに変更） | operator のバージョンを固定しているため既定のまま | 🟡 |

> **🟡 の核心（実害あり）**: RabbitMQ 3.8.15 以降、**ack されないまま
> `consumer_timeout`（既定30分）を超えたメッセージはチャネルごと切断**される。
> WEKO の Celery タスクにはインデクシングや一括更新など30分を超えるものがあるため、
> 本番は **3時間**に延長している。**サンプルには入っていない**ので、
> 大きなデータを扱うと「サンプルでは再現しない `PreconditionFailed - consumer ack timed out`」が本番で出る。
> 本番相当にするなら `50-rabbitmq-cluster.yaml` の `additionalConfig` に
> `consumer_timeout = 10800000` を足すだけでよい。

#### Redis / Sentinel

| 設定 | kind 検証環境 | 本番 `base` | 本番 `oci-pr` | 判定 |
|---|---|---|---|---|
| 永続化方式 | **`appendonly yes`**（AOF） | **RDB のみ**（`save 3600 1` / `300 100` / `60 10000`） | 同左 | 🟡 **方式が違う** |
| `databases` | `512` | **`40000`** | `40000` | 🟡 |
| `maxmemory` | **未指定**（無制限＝ Pod の limit で OOM Kill） | `300mb` | **`52gb`** | 🟡 |
| `maxclients` | 未指定（既定 10000） | `150000` | `60000` | 🔵 |
| `client-output-buffer-limit slave` | 未指定（既定 256mb/64mb/60） | **`0 0 0`**（無制限） | 同左 | 🟡 |
| `sentinel monitor` の quorum | `2` | `1` | `2` | 🔵 |
| `sentinel down-after-milliseconds` | **`5000`** | **`3000`** | `3000` | 🔵 |
| `sentinel failover-timeout` | `10000` | 未指定（既定 180000） | 同左 | 🟡 |
| `sentinel parallel-syncs` | `1` | 未指定（既定 1） | 同左 | ✅ 実質同じ |
| `sentinel resolve-hostnames` | **`yes`**（Pod FQDN を使うため必須） | 未指定（IP で運用） | 同左 | 🟡 |
| `sentinel notification-script` | **なし** | **あり**（`/data/conf/notify-sentinel.sh`） | 同左 | 🔴 |

> **🟡 の核心が3つある**:
> 1. **`databases 512` vs `40000`** — WEKO はテナント毎に cache / session / celery で
>    Redis の DB 番号を消費する（`tenants.txt` の `CACHE_DB` `SESSION_DB` `CELERY_DB`）。
>    サンプルは 8 テナント程度を想定して 512 だが、**本番規模では 512 では足りない**。
>    `tenants.txt` の DB 番号が 512 を超えた瞬間に接続エラーになる。
> 2. **AOF vs RDB** — サンプルは AOF（追記ログ）、本番はスナップショットのみ。
>    復旧特性もディスク I/O 特性も違うので、性能試験の結果はそのまま持ち込めない。
> 3. **`maxmemory` 未指定** — サンプルは上限が無く、溢れると Pod ごと OOM Kill される。
>    本番は `maxmemory` で頭打ちにしている（＝ Redis 自身が eviction / エラーで応答する）。
>
> `down-after-milliseconds` はサンプルの方が鈍い（5秒 vs 3秒）。kind の Docker ネットワークで
> 誤検知フェイルオーバーを避けるための緩和であり、本番仕様では 3000 に戻すのが素直である。

---

## 6. アプリケーション層（WEKO 本体）

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| Deployment 構造 | init（jinja2）+ nginx + web(uwsgi) + worker(celery) | 同一（`weko/manifest_template/deploy-web.yaml`） | ✅ |
| `hostAliases` で自 FQDN → 127.0.0.1 | あり | あり | ✅ |
| `securityContext.fsGroup: 1000` | あり | あり | ✅ |
| ローリング更新 | `maxSurge:1 / maxUnavailable:0` | 同一 | ✅ |
| マウント構成 | conf / data / shib / static | 同一 | ✅ |
| `static` ボリューム | PVC | **emptyDir**（起動時に `static.org/*` からコピー、`deploy-web.yaml:118`） | 🔵 |
| nginx コンテナの中身 | **weko ソースからビルドした Shibboleth SP 入りイメージ**（`deploy-amd64.sh:180-212`）＋ ConfigMap（`21-nginx-config.yaml`）。TLS は Ingress で終端し、Pod へは平文 80 | 同じ独自イメージ。**Pod 内で TLS 443 を終端** | 🟡 TLS ホップ数のみ差 |
| SP 用 `/secure/login.py` と fcgiwrap | **ビルド時に追加**（weko の `nginx/Dockerfile` は `login.php` しか入れず fcgiwrap も無いが、weko-accounts が使うのは `login.py`。`Status:` 行の NPH 書式も修正） | イメージに同梱済み | 🟡 **サンプル側で補っている** |
| Shibboleth SP の有効化 | `WEKO_SHIB=yes` のときだけ設定を配布（既定 `no`、`deploy-amd64.sh:65`） | 常に有効（`shibboleth_template` を配布） | 🔵 |
| WAF | なし | App Protect（nginx ではなく Ingress 側） | 🔴 |
| uwsgi プロセス数 | 固定 | テナント毎に指定（`repositories_file` の列） | 🔵 |
| メモリ requests/limits | init/web/worker のみ（`gen-tenant.sh:345,378,403`） | テナント毎に指定、nginx は FQDN で個別分岐（`make_weko_manifests.sh`） | 🔵 |

### 6-1. 学認（GakuNin）連携 — IdP と mAP

サンプルは `WEKO_SHIB=yes` で **本物の Shibboleth IdP 5.2.3 を自前ビルドして立てる**。
`WEKO_SHIB_MAP=aggregation` を足すと、**学認mAP に相当する属性認証局（AA）をもう1エンティティ**立てて
SimpleAggregation で `isMemberOf` を取りに行く。詳細は
[SHIBBOLETH-IDP.md](k8s-weko-amd64/SHIBBOLETH-IDP.md)。

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| IdP | クラスタ内に自前ビルド（`70-shibboleth-idp.yaml`、Shibboleth IdP 5.2.3 / Tomcat 10.1）、`idp.localhost` | **JAIRO Cloud の IdP**（`https://idp.repo.nii.ac.jp/idp/shibboleth`、`shibboleth2.xml:46`）＋ 各機関の IdP | 🟡 |
| IdP のユーザ DB | **htpasswd 3人**（admin / libadmin / teacher、`credentials/demo.htpasswd`） | 機関のディレクトリ | 🟡 |
| メタデータの入手 | `provision-shib.sh` がイメージから取り出し ConfigMap 化（署名検証なし） | `MetadataProvider type="XML"` で `https://idp.repo.nii.ac.jp/metadata/irjaya.xml` を 7200秒毎に取得（`shibboleth2.xml:86-92`） | 🟡 |
| メタデータの署名検証 | **なし**（クラスタ内で完結するため） | テンプレートでは `MetadataFilter type="Signature"` は**コメントアウト**（`shibboleth2.xml:88-90`） | 🟡 **本番テンプレートも未有効** |
| SP の設定配布 | `shib-sp-template/` を sed 置換して NFS へ | `deploy/weko/shibboleth_template/` をテナント毎に配布 | ✅ **同じ思想** |
| `isMemberOf` の取得元 | **第2のエンティティ** `map.localhost`（`71-shibboleth-map.yaml`）へ SimpleAggregation | **学認mAP**（`https://sptest.cg.gakunin.jp/idp/shibboleth`）へ SimpleAggregation | 🟡 **仕組みは同一、相手だけ違う** |
| `isMemberOf` の値の形 | `https://map.localhost/gr/<グループ>` と `.../admin` | `https://cg.gakunin.jp/gr/<グループ>` と `.../admin` | ✅ **形は一致**（ホスト名のみ差） |
| バックチャネル | 8443 / `idp-backchannel.p12` を**メタデータの KeyDescriptor で信頼**（ExplicitKey） | 学認の実サーバ証明書（公的 CA） | 🟡 |
| `attribute-map.xml` の `isMemberOf` | あり（`urn:oid:1.3.6.1.4.1.5923.1.5.1.1`） | **IaC のテンプレートには無い**（`attribute-map.xml` に該当行なし）。運用側で追記している | 🟡 **IaC 外の手作業** |
| SimpleAggregation の設定 | `shib-sp-template/simple-aggregation.xml` として**構成管理下** | **`~/weko-k8s` のテンプレートには含まれない**。実機に手で入れている | 🟡 **IaC 外の手作業** |
| 既定の有効/無効 | 既定 **無効**（`WEKO_SHIB=no` / `WEKO_SHIB_MAP=no`） | 常に有効 | 🔵 |

> **設計上の注意（実機で確認済み）**: SimpleAggregation は **ログインした IdP と同じエンティティには
> AttributeQuery を投げない**（shibd が `skipping previously queried attribute source` で捨てる）。
> したがって「IdP に isMemberOf も出させる」構成では SimpleAggregation の検証にならず、
> **属性認証局を別エンティティとして立てるしかない**。サンプルが IdP と AA を分けているのはこのためで、
> 本番が IdP（機関）と mAP（`cg.gakunin.jp`）に分かれているのと同じ構造になっている。

> **🟡 の核心**: **学認連携の設定が本番では IaC の外にある。**
> `~/weko-k8s/deploy/weko/shibboleth_template/` の `shibboleth2.xml` / `attribute-map.xml` には
> SimpleAggregation も `isMemberOf` も入っておらず、実機で追記されている。
> 本番構築時に「テンプレートを配れば学認mAP 連携が動く」と考えると**必ず取りこぼす**。
> サンプル側はこれを構成管理下に置いているので、**移植時はサンプルの方を正とするのが良い**。

---

## 7. テナント管理層

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| テナント定義ファイル | `tenants.txt`（**9列**） | `repositories_file`（**20列**） | 🔵 |
| 列の内容 | `NAME DB HOST EMAIL PASS INIT CACHE_DB SESSION_DB CELERY_DB` | `W2FQDN W3FQDN ACCOUNT PASSWD GOOGLE_ANA CNRI_FLAG DOIFREE MEM_REQ MEM_LIMIT UWSGI_RSS UWSGI_PROC … CACHE_DB SESSION_DB CELERY_DB AGG_HOUR AGG_MIN` | 🔵 |
| manifest 生成 | `gen-tenant.sh`（manifest + PV + Ingress を1本で） | `scripts/make_weko_manifests.sh`（manifest のみ） | 🔵 |
| 共有 FS の初期化 | `provision-nfs.sh` | `scripts/make_volumes.sh` | 🔵 |
| 配備 | `deploy-amd64.sh:261-281` | `scripts/deploy_weko.sh`（**ノード数に応じてスロットリング**） | 🔵 |
| 生成方式 | 雛形の sed 置換 | 雛形の sed 置換 | ✅ **同じ思想** |
| 証明書の用意 | cert-manager が自動発行 | テナント毎の実証明書ファイルを Secret 化 | 🟡 |
| DB 初期化 | `weko-init.sh` + `seed-demo.sh` | （移行データ投入で代替） | 🔵 |

---

## 8. 名前空間・構成管理層

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| WEKO アプリ | `weko3` | `weko3` | ✅ |
| PostgreSQL | `weko3`（operator は `default`） | **`weko3pg`** | 🔵 |
| Elasticsearch | `weko3` | **`weko3es`** | 🔵 |
| RabbitMQ | `weko3` | **`weko3ra`** | 🔵 |
| Redis | `weko3re` | `weko3re` | ✅ |
| Ingress | `ingress-nginx` | `nginx-ingress` / `nginx-ingress-internal` | 🔵 |
| 監視・ログ・保守 | なし | `monitoring` / `logging` / `maintenance` | 🔴 |
| NFS | `nfs-system` | （クラスタ外） | 🟡 |
| 構成管理方式 | 素の manifest + `sed \| kubectl apply -f -` | kustomize `base`/`components`/`overlay` | 🔵 |
| 環境差分の吸収 | 環境変数 | overlay | 🔵 |
| デプロイ方式 | 命令的スクリプト1本（357行） | 宣言的 kustomize + 用途別スクリプト | 🔵 |

> **影響範囲に注意**: namespace を分割すると Service の FQDN が変わる
> （`elasticsearch` → `elasticsearch.weko3es.svc.cluster.local` 等）。
> `gen-tenant.sh` が ConfigMap に書き込む接続先を**全て**見直す必要がある。

---

## 9. 秘密情報の管理

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| 管理方式 | manifest / スクリプトに直書き | `deploy/secret.properties` に集約 → kustomize `secretFromProperties` generator | 🟡 |
| MinIO / S3 キー | **平文**（`40-minio.yaml:10-11`, `deploy-amd64.sh:138-141,228`） | `weko3pg.postgres-pod-secrets.AWS_*` 等 | 🟡 |
| PG パスワード | `weko` に**強制上書き**（`deploy-amd64.sh:231-236`） | `weko3pg.postgresql-infrastructure-roles.invenio` | 🟡 |
| 管理者パスワード | `tenants.txt` に平文（Git 管理下） | `repositories_file`（平文だが Git 管理外） | 🟡 |
| レジストリ資格情報 | 不要 | `ocir-secret`（namespace 毎） | 🔴 |
| TLS 秘密鍵 | cert-manager が管理 | `secret.properties` / 証明書ファイル | 🔵 |
| Slack Webhook | なし | `logging.slack-config.*` | 🔴 |

---

## 10. 運用層

| 項目 | kind 検証環境 | 本番環境 | 判定 |
|---|---|---|---|
| **監視** | **なし** | kube-prometheus-stack + ServiceMonitor（pg / pgpool / redis / rabbitmq / es / ingress）+ Grafana ダッシュボード + アラートルール（`deploy/monitoring/`） | 🔴 |
| **ログ集約** | **なし** | fluentd → Elasticsearch → Kibana、kubernetes-event-exporter、Slack 通知（`deploy/logging/`） | 🔴 |
| **DB バックアップ** | **なし** | operator の WAL / logical backup（`components/backup_s3`）+ pgdump の rclone → Object Storage（`components/pgdump_s3`） | 🔴 |
| **ES バックアップ** | MinIO への snapshot 設定のみ（実行 Job なし） | `essnapshot-job`（`elasticsearch/components/backup_s3/`） | 🔴 |
| **コンテンツバックアップ** | **なし** | rclone CronJob（`deploy/contents-backup/`） | 🔴 |
| **リストア手順** | **なし** | `scripts/restore_db*.sh` / `restore_es*.sh` / `overlay/*/restore-pv*.yaml` | 🔴 |
| **メンテナンス画面** | **なし** | `deploy/maintenance/` | 🔴 |
| **保守用 Pod** | **なし** | `deploy/maintenance-pod/` | 🔴 |
| **ノード保守** | **なし** | `scripts/maintenance/`（drain / delete_old_nodes / OKE アップグレード） | 🔴 |
| **統計ローテート** | **なし** | `postgresql/components/stats_rotate` | 🔴 |
| **撤去** | `teardown-amd64.sh`（**クラスタごと削除**） | `scripts/maintenance/delete_*.sh`（個別削除） | 🟡 |
| **強制復旧** | `unwedge-amd64.sh` | なし | 🔵 |
| 再実行時の初期化 | **`FORCE_INIT=yes` が既定**（`deploy-amd64.sh:40`）＝ 再実行で全テナント初期化 | 該当なし | 🟡 **本番では破壊的** |

> **🟡 の核心**: `teardown-*.sh` はクラスタ削除、`FORCE_INIT=yes` は全テナント初期化。
> どちらも使い捨ての kind 環境では正しい既定だが、**本番に持ち込むとデータを失う**。

---

## 11. サマリ — 分類別の集計

| 分類 | 主な該当項目 |
|---|---|
| ✅ **一致**（変更不要） | Deployment 構造・マウント構成・`fsGroup`・ローリング更新方式／共有 FS のディレクトリ構成／pgpool 4.2.2 と**そのチューニング値ほぼ全て**／ES 6.8.23／RabbitMQ 4.0.9／PG 同期レプリケーション／`md5` 制約／テナント生成の思想（sed 置換）／`weko3`・`weko3re` namespace／PDB・NetworkPolicy 不在（本番も同じ）／metrics-server／Shibboleth SP 設定の配布方式／`isMemberOf` の値の形 |
| 🔵 **簡略化**（本番仕様に戻す） | ノード種別ラベル 2種→8種／namespace 分割／サイジング全般／台数（PG 2→3、ES 2→13、pgpool 1→3 等）／PG の並列度・WAL 関連の各値／ES のヒープと `minimum_master_nodes`／Redis の `maxclients`／Sentinel の `down-after-milliseconds`（5000→3000）／テナント定義の列数 9→20／Redis 独自イメージ／`static` の emptyDir 化／kustomize 化／学認連携の既定 OFF |
| 🟡 **代替物**（**必ず置換**） | kind クラスタ／`kind load` + `imagePullPolicy: Never`／`standard` SC／**クラスタ内 NFS と固定 ClusterIP**／MinIO／ingress-nginx OSS + `extraPortMappings`／cert-manager 自己署名 CA／`*.localhost`／秘密情報の平文／`FORCE_INIT=yes`／`teardown-*.sh`／PG メジャーバージョン／**PG のレプリケーション系タイムアウト無効化の未適用**／**RabbitMQ `consumer_timeout`（3時間）の未設定**／**ES の `-Dlog4j2.formatMsgNoLookups=true` 欠落**／**Redis の永続化方式（AOF vs RDB）・`databases 512`・`maxmemory` 未指定**／自前 IdP と AA（学認 / mAP の代替） |
| 🔴 **未実装**（新規構築） | 監視／ログ集約／バックアップ全般／リストア手順／WAF／TLS ホップ2／メンテナンス画面・保守 Pod／ノード保守手順／内部向け Ingress／レジストリ資格情報／Sentinel の `notification-script` |

### 一言でまとめると

- **アプリケーション層（WEKO 本体の構造）は本番とほぼ一致している。** ここは移植の心配が要らない。
- **インフラ層は 🟡 代替物の塊である。** kind の制約を回避するための仕組みが随所に埋まっており、
  そのまま本番に持ち込むと起動しないか、静かに破綻する。
- **運用層は丸ごと 🔴 未実装である。** 検証環境に不要だったため、本番構築では新規に積み上げる必要がある。
- **ミドルウェアは「バージョンは合っているが値が違う」。**（5-4）
  pgpool はほぼ完全一致だが、PG / RabbitMQ / ES / Redis には**規模を揃えても残る設定差**がある。
  中でも **RabbitMQ の `consumer_timeout`（本番3時間、サンプル既定30分）**と
  **Redis の `databases`（本番 40000、サンプル 512）**は、
  データ量が増えて初めて表面化する種類の差なので注意が要る。
- **学認mAP 連携は本番でも IaC の外にある。**（6-1）
  サンプルの方が構成管理としては進んでいるので、移植時はサンプルを正とするのが良い。

---

## 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| [PRODUCTION-ROADMAP.md](PRODUCTION-ROADMAP.md) | 本ドキュメントの差異を、どの順序で解消していくか |
| [README.md](README.md) | サンプル全体の設計 |
| [CONSTRUCTION.md](CONSTRUCTION.md) | 構築の経緯と HA クラスタ化の設計判断 |
| [COMPARE-weko-workshop.md](COMPARE-weko-workshop.md) | docker-compose 版との比較 |
| [JAIRO-CLOUD-ARCHITECTURE.md](JAIRO-CLOUD-ARCHITECTURE.md) | JAIRO Cloud 本番アーキテクチャ |
| `~/weko-k8s`（`RCOSDP/weko-k8s`） | 本番 IaC 本体 |
