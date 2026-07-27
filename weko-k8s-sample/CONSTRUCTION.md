# weko3 k8s 環境 構築手順書

[RCOSDP/weko-k8s](https://github.com/RCOSDP/weko-k8s) を用いて、単一ホスト上に **kind** で本物の Kubernetes クラスタ（ノード＋APIサーバ一式）を構築する手順。

- 作成日: 2026-07-20（更新: 2026-07-21 マルチテナント→本番忠実度→**HAクラスタ化＋arm64ネイティブ化**）
- 対象ホスト: `/home/mhaya/weko-k8s-sample`
- ステータス: **PostgreSQL/RabbitMQ/Elasticsearch を3ノードHAクラスタ化 ＋ weko本体をarm64ネイティブ化まで完了**
  - `http://tenant1.localhost/` / `http://tenant2.localhost/` とも `/`200・`/login/`200・`/admin/`302・`/api/records/`200（**200×15/15で安定**）
  - HAクラスタ化・arm64ネイティブ化・アプリ層バグ修正の詳細は [`README.md` の「HAクラスタ化と arm64 ネイティブ化」節](./README.md)
- マニフェスト一式: `/home/mhaya/weko-k8s-sample/k8s-weko/`
- **コピペで再現できるランブックは [`README.md`](./README.md)**（本書は背景・詳細・落とし穴の解説）

> この手順書は §1〜9 で **単一テナントの最小構成**を素から積み上げて解説し、
> §10 でその上に重ねた **マルチテナント化**と **本番忠実度アップグレード（Sentinel/永続化/S3）**をまとめる。

---

## 0. 現在の最終構成（サマリ）

```
[ホスト:arm64] kind クラスタ "weko3"
  control-plane … APIサーバ等 + ingress-nginx(host 80/443)
  worker (nodeType=WEKO) … tenant1-web / tenant2-web (各 nginx+web+worker)
  worker2(nodeType=DATA) … 共有: PostgreSQL / Elasticsearch / RabbitMQ / MinIO(S3)  ※全PVC永続化
                            namespace weko3re … Redis master+replica×2 + sentinel×3 ※全PVC
```

| 層 | 構成 | 分離キー(テナント別) |
|---|---|---|
| Web | `<tenant>-web`(nginx+uwsgi+celery) + Ingress(host=FQDN) | FQDN |
| DB | 共有 PostgreSQL（PVC） | DB 名 |
| 検索 | 共有 Elasticsearch 6.8.23（PVC） | インデックス接頭辞 |
| MQ | 共有 RabbitMQ（PVC） | vhost `<name>/` |
| キャッシュ | 共有 Redis **Sentinel HA**（PVC） | Redis DB 番号 |
| オブジェクトストレージ | 共有 MinIO(S3)（PVC） | バケット/プレフィックス |

**マニフェスト対応表:**

| ファイル | 役割 | 備考 |
|---|---|---|
| `00-namespace.yaml` | namespace weko3 | |
| `10-postgresql.yaml` | PostgreSQL（PVC版） | StatefulSet |
| `12-rabbitmq.yaml` | RabbitMQ（PVC版） | StatefulSet |
| `13-elasticsearch.yaml` | Elasticsearch 6.8.23＋kui.txt（PVC版） | StatefulSet |
| `40-minio.yaml` | MinIO（S3, PVC） | バケット3種＋テナント別 `weko-<tenant>` |
| `41-redis-sentinel.yaml` | Redis Sentinel HA（weko3re, PVC） | master+replica2+sentinel3 |
| `21-nginx-config.yaml` | 前段 nginx 設定（全テナント共有） | uwsgi_pass |
| `tenants.txt` + `gen-tenant.sh` | テナント定義→マニフェスト生成 | redissentinel対応。秘密鍵(`SECRET_KEY`等)は `.secret-seed` からテナント毎に導出 |
| `provision-tenants.sh` | テナント別 PG DB / RabbitMQ vhost 作成 | |
| `provision-nfs.sh` | 共有FS(NFS)に `/fs-nginx` `/fs-shibboleth` `/fs-config` `/fs-data` のテナント別ディレクトリを作成し、nginx/Shibboleth のテンプレートを投入 | 本番 `make_volumes.sh` 相当。静的PVの実体を用意するので apply 前に実行 |
| `weko-init.sh` / `es-reinit.sh` | DB初期化 / ESインデックス初期化 | env駆動 |
| `set-s3-location.sh` | テナント別バケット作成＋`files_location`をS3タイプに | init後に実行 |
| `deploy-arm64.sh` | 現フル構成(HA/Sentinel/永続化/NFS/S3/マルチテナント)を素から一括 | README 付録D。amd64は`k8s-weko-amd64/deploy-amd64.sh` |
| `build-push-weko.sh`(直下) | WEKO イメージをビルド→Docker Hub push（native/multiarch/manifest） | 差し替えは `WEKO_IMAGE` 環境変数。`Dockerfile`と`Dockerfile.arm64`は同一内容 |
| `Dockerfile.es` | ES 6.8.23＋kuromoji/icu ビルド | amd64 |
| ~~`11-redis.yaml` / `20-weko-config.yaml` / `30-weko-web.yaml`~~ | 単一テナント時代の旧版 | §10 以降は未使用 |

---

## 1. 前提・環境

| 項目 | 値 | 備考 |
|---|---|---|
| アーキテクチャ | **arm64 (aarch64)** | weko 公式イメージは amd64 のみ → エミュレーション必須 |
| CPU / RAM / Disk | 20コア / 121GB / 294GB 空き | 潤沢 |
| Docker | 29.1.3 | **sudo なしで実行可**（docker グループ所属） |
| sudo | **パスワード必須で使用不可** | バイナリは `~/.local/bin` に配置する |
| OS | Linux 6.17（Ubuntu系） | — |

### なぜ kind を使うか

`weko-k8s` は本来 **Oracle Kubernetes Engine (OKE)** 上のマルチテナント本番運用を想定している。
単一ホストで「ノードもAPIサーバも自分で立てる」ため、Docker コンテナを k8s ノードとして扱う **kind (Kubernetes in Docker)** を採用し、本物の control-plane / worker / API サーバを構築する。

---

## 2. ツールの導入

`sudo` が使えないため、PATH に含まれる `~/.local/bin` へ配置する。

```bash
mkdir -p ~/.local/bin

# kubectl (arm64)
KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/arm64/kubectl"
chmod +x ~/.local/bin/kubectl

# kind (arm64)
curl -sLo ~/.local/bin/kind "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-arm64"
chmod +x ~/.local/bin/kind

# 確認
hash -r
kubectl version --client
kind version    # kind v0.30.0
```

導入済みバージョン: kubectl **v1.36.2** / kind **v0.30.0**。

---

## 3. リポジトリの取得

```bash
cd /home/mhaya/weko-k8s-sample
git clone --depth 1 https://github.com/RCOSDP/weko-k8s.git
```

主要なディレクトリ:

| パス | 内容 |
|---|---|
| `weko-k8s/deploy/weko/manifest_template/` | weko 本体の Deployment/Service/Ingress/ConfigMap テンプレート |
| `weko-k8s/deploy/{postgresql,elasticsearch,redis,rabbitmq,...}` | 各バックエンドのマニフェスト（OKE前提） |
| `weko-k8s/scripts/make_weko_manifests.sh` | テンプレートから実マニフェストを生成 |
| `weko-k8s/scripts/deploy_weko.sh` | 生成したマニフェストを apply |

---

## 4. kind クラスタ構成ファイル

`kind-weko-cluster.yaml`（control-plane 1 + worker 2）。
weko-k8s のノードセレクタ `nodeType=WEKO` に合わせ、worker にラベルを付与する。

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: weko3
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:            # ingress を host の 80/443 に公開
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
  - role: worker
    labels:
      nodeType: WEKO              # weko 本体(web/nginx/worker)を載せる
  - role: worker
    labels:
      nodeType: DATA             # バックエンド(DB/ES/Redis/MQ)を載せる
```

---

## 5. クラスタ作成

```bash
cd /home/mhaya/weko-k8s-sample
kind create cluster --config kind-weko-cluster.yaml --wait 120s
```

### 検証

```bash
kubectl cluster-info
kubectl get nodes -L nodeType,ingress-ready
kubectl get pods -n kube-system
```

期待される状態（3ノードすべて Ready）:

```
NAME                  STATUS   ROLES           NODETYPE   INGRESS-READY
weko3-control-plane   Ready    control-plane              true
weko3-worker          Ready    <none>          WEKO
weko3-worker2         Ready    <none>          DATA
```

control-plane 上で `kube-apiserver / etcd / kube-scheduler / kube-controller-manager / coredns / kube-proxy / kindnet(CNI)` がすべて Running であること。

---

## 6. Ingress コントローラ導入

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml

# Ready 待ち
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=150s
```

### 疎通確認

```bash
curl -s  -o /dev/null -w "HTTP %{http_code}\n" http://localhost:80/
curl -sk -o /dev/null -w "HTTP %{http_code}\n" https://localhost:443/
# → いずれも 404（コントローラ稼働・ルート未定義の正常応答）
```

---

## 7. amd64 エミュレーション有効化

weko 本体イメージ（`mhayashi55/weko3-web` / `mhayashi55/weko3-nginx`）は **amd64 のみ**。
arm64 ホストで実行するため qemu の binfmt を登録する（ホストカーネルは kind ノードと共有）。

```bash
docker run --rm --privileged tonistiigi/binfmt --install amd64
```

### 検証（クラスタ内で amd64 コンテナを実行）

```bash
docker pull --platform linux/amd64 amd64/alpine:latest
docker tag amd64/alpine:latest amd64-emu-test:local
kind load docker-image amd64-emu-test:local --name weko3

kubectl run amd64-test --restart=Never --image=amd64-emu-test:local \
  --image-pull-policy=Never \
  --overrides='{"spec":{"nodeSelector":{"nodeType":"WEKO"}}}' \
  -- sh -c 'echo ARCH=$(uname -m)'
kubectl logs amd64-test    # → ARCH=x86_64 なら成功
kubectl delete pod amd64-test
```

> ⚠️ **重要な注意**: クラスタ内 containerd から amd64 イメージを **直接 pull すると失敗しやすい**。
> **ホストで `docker pull --platform linux/amd64` → `kind load docker-image` で投入**するのが確実。
> weko 本体イメージも必ずこの方式で投入すること。

---

## 8. weko3 本体のデプロイ（簡素化構成・実施済み）

`weko-k8s` は OKE 本番向けで、`postgres-operator(Spilo)` / `pgpool` / `Redis Sentinel` /
カスタム ES / WAF / Oracle オブジェクトストレージなどに依存し、リポジトリに含まれない
カスタムイメージが約10種ある。単一ホストでは**簡素化構成**で再現した。

マニフェストは `k8s-weko/` に格納。適用順に説明する。

### 8.0 重要な前提（weko 本体イメージの解析結果）

`mhayashi55/weko3-web:latest` の中身を調査して判明した必須事項:

| 事項 | 内容 |
|---|---|
| ES バージョン | **Elasticsearch 6.x 必須**（クライアント `elasticsearch==6.1.1`）。ES7 不可 |
| ES プラグイン | `analysis-kuromoji`, `analysis-icu` が必要 |
| ES 辞書ファイル | item マッピングが char_filter `mappings_path: kui.txt` を参照 → `kui.txt` を ES config に配置 |
| 設定生成 | `jinja2 /code/scripts/instance.cfg > var/instance/conf/invenio.cfg`（`environ()` で env 展開）。同梱 instance.cfg は既に `CACHE_TYPE='redis'` |
| uwsgi | `socket = 0.0.0.0:5000`（**uwsgi プロトコル**）→ 前段に `uwsgi_pass` する nginx が必須 |
| 初期化 | `/code/scripts/populate-instance.sh` に全手順（`db init/create` → `index init` → users/roles/access） |

### 8.1 バックエンド（`k8s-weko/10〜13`）

- **PostgreSQL 13**（`postgres:13`, arm64）… `10-postgresql.yaml`
- **Redis 6.2**（`redis:6.2`, arm64）… `11-redis.yaml`（Sentinel ではなく単体。`CACHE_TYPE=redis`）
- **RabbitMQ 3.13**（`rabbitmq:3.13-management`, arm64）… `12-rabbitmq.yaml`（quorum queue 対応。default vhost `/`）
- **Elasticsearch 6.8.23 + kuromoji/icu**（自前ビルド amd64・エミュレーション）… `13-elasticsearch.yaml`

ES イメージのビルドと投入:
```bash
cd k8s-weko
docker buildx build --platform linux/amd64 -f Dockerfile.es -t weko-elasticsearch:6.8.23 --load .
kind load docker-image weko-elasticsearch:6.8.23 --name weko3

kubectl apply -f 00-namespace.yaml -f 10-postgresql.yaml -f 11-redis.yaml \
               -f 12-rabbitmq.yaml -f 13-elasticsearch.yaml
```
> `13-elasticsearch.yaml` には `kui.txt`（空ファイル = 文字マッピング無し）の ConfigMap を含み、
> `/usr/share/elasticsearch/config/kui.txt` に subPath マウントしている。
> 本来の weko ES イメージには文字正規化用の kui.txt が同梱されるが、無くても空で index 作成は通る。

### 8.2 weko 設定と本体（`k8s-weko/20〜30`）

```bash
docker pull --platform linux/amd64 mhayashi55/weko3-web:latest
kind load docker-image mhayashi55/weko3-web:latest --name weko3

kubectl apply -f 20-weko-config.yaml   # ConfigMap + Secret（接続先・管理者情報）
kubectl apply -f 21-nginx-config.yaml  # 前段 nginx(uwsgi_pass) 設定
kubectl apply -f 30-weko-web.yaml      # Deployment(nginx+web+worker) + Service + Ingress
```
- Pod 構成 = `nginx(標準nginx:alpine)` + `web(uwsgi:5000)` + `worker(celery)`（1 Pod・`nodeType=WEKO`）
- web/worker は起動時に `jinja2` で invenio.cfg を再生成してから uwsgi / celery を起動
- 本番の複雑な nginx（Shibboleth/SSL/AppProtect）は使わず、標準 nginx + `uwsgi_pass 127.0.0.1:5000` に置換

### 8.3 DB / ES 初期化

`populate-instance.sh` 相当を web コンテナ内で実行（`scripts/` の内容と同一）:
```bash
POD=$(kubectl get pod -n weko3 -l app=weko-web -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n weko3 $POD -c web -- bash -s < scratchpad/weko-init.sh
# 内容: invenio db init/create → stats/logging partition → index init/queue init
#       → ES ILM/stats インデックス作成 → files location → users/roles/access 付与
```
> ⚠️ **エミュレーションのため各 `invenio` コマンドは 30〜60 秒**かかる。初期化全体で 30〜40 分程度。

### 8.4 既知の落とし穴と対処（実際に踏んだもの）

| 症状 | 原因 | 対処 |
|---|---|---|
| `index init` で `IOException ... kui.txt` | ES に `kui.txt` が無い | `es-kui` ConfigMap を config にマウント（8.1） |
| トップページが **HTTP 500**（`_adjust_shib_admin_DB` で `None + int`） | 空の `admin_settings` に対し `max(id)+1` が失敗（`demo init` 省略のため） | `admin_settings` にシード行を1件投入:<br>`INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb);` 後に web を再起動 |
| 初回リクエストがタイムアウト | `before_first_request` + JIT がエミュレーション下で低速 | 初回は `--max-time 240` 程度で待つ。2回目以降は数秒 |

### 8.5 アクセス情報

| 項目 | 値 |
|---|---|
| URL | `http://localhost/`（Ingress host = `localhost`） |
| 管理者 | `admin@example.org` / `adminpass123` |
| 名前空間 | `weko3` |
| DB | `wekodb` / user `weko` / pass `weko` |

疎通確認結果（実測）:
```
トップ /            → HTTP 200 (<title>WEKO3</title>)
/login/            → HTTP 200
/admin/            → HTTP 302 (未認証→ログイン)
/api/records/      → HTTP 200 (ES 連携 OK)
/static/favicon.ico→ HTTP 200
```

---

## 8bis. 64GB メモリ環境向けデプロイプラン

本構成は **64GB どころか実測 ~5GiB** で全体が動作する（下記実測）。64GB 環境でも十分な余裕があるが、
安全側に倒すための資源プロファイルを示す。

### 実測メモリ（全部込み・この構成そのまま）

| ノード（kind コンテナ） | 役割 | 実測 |
|---|---|---|
| `weko3-control-plane` | APIサーバ等 + ingress | ~1.1 GiB |
| `weko3-worker`（WEKO） | weko-web（nginx+web+worker） | ~1.3 GiB |
| `weko3-worker2`（DATA） | ES + PG + Redis + RabbitMQ | ~2.5 GiB |
| **合計** | | **~5 GiB** |

### 64GB 向け資源プロファイル（本マニフェストの既定値）

| コンポーネント | requests | limits | 調整ポイント |
|---|---|---|---|
| Elasticsearch | 1.5Gi | 2.5Gi | `ES_JAVA_OPTS=-Xms1g -Xmx1g`（heap 1g） |
| PostgreSQL | 256Mi | 1Gi | — |
| Redis | 128Mi | 512Mi | 単体構成 |
| RabbitMQ | 256Mi | 1Gi | — |
| weko web(uwsgi) | 700Mi | 2Gi | `uwsgi processes=2` |
| weko worker(celery) | 500Mi | 1.5Gi | `celery -c 1`（並列度1） |
| nginx | 64Mi | 256Mi | — |
| **limits 合計** | — | **~8.8Gi** | 64GB に対し十分小さい |

### さらに絞る場合（例: 他ワークロードと同居／16〜32GB 級）

- ES heap を `-Xms512m -Xmx512m`、limit 1.5Gi に
- uwsgi `processes=1`、celery `-c 1`
- ノードを control-plane + worker 1 の**2ノード**に減らし、`nodeType` セレクタを1ノードへ集約
- ES を単一ノード・`index.number_of_replicas=0`（既定で単一ノードなら黄でも可）

> 逆に **潤沢メモリ(64GB+)で性能を上げる**なら: ES heap 2〜4g、uwsgi `processes=4`、celery `-c 2〜4`、
> weko-web を `replicas` 複数へ（ただし static/session の共有に注意）。

---

## 10. マルチテナント化と本番忠実度アップグレード

§1〜9 の単一テナント最小構成の上に、以下を重ねて **JAIRO Cloud 本番に近づけた**。
実行コマンドは [`README.md`](./README.md)（マルチテナント構成 / 本番忠実度アップグレード の各節）を参照。

### 10.1 マルチテナント（バックエンド共有・テナント別分離）
- `tenants.txt`（NAME/DBNAME/HOST/管理者/INIT/RedisDB）を入力に `gen-tenant.sh` が
  テナント別 ConfigMap/Secret/Deployment(web)/Service/Ingress を `generated/` へ生成。
- テナント別に分離: **PostgreSQL DB名 / ES インデックス接頭辞 / RabbitMQ vhost(`<name>/`) / Redis DB番号 / FQDN**。
- `provision-tenants.sh` が PG DB と RabbitMQ vhost を作成、`weko-init.sh`（＝`populate-instance.sh` 相当）で初期化。
- 検証: `tenant1.localhost` / `tenant2.localhost` が各自の Pod にルーティングされ 200。

### 10.2 Redis Sentinel 化（`41-redis-sentinel.yaml`, namespace `weko3re`）
- redis **master + replica×2 + sentinel×3**。サービス名は instance.cfg 既定 `weko-sentinel-service.weko3re:26379`、master=`mymaster`。
- weko を `CACHE_TYPE='redissentinel'` に（web/worker 起動時に instance.cfg を sed 置換）。
- テナントは **共有 Redis を DB 番号で分離**（tenant1=0/1/2, tenant2=5/6/7。`CRAWLER=3`/`GROUP_INFO=4` 予約を回避）。
- 検証: worker が sentinel 経由で `ready`、master→replica 複製、`sentinel master mymaster` quorum=2。

### 10.3 データ永続化（PVC / kind `standard` StorageClass）
- PostgreSQL / Elasticsearch / RabbitMQ / Redis×3 / MinIO をすべて PVC 化（emptyDir 廃止）。
- **PG はデータ保持**: `pg_dumpall` → PVC 版へ再デプロイ → restore（再初期化を回避）。ES は再デプロイ後に index 再作成。
- 検証: `postgresql-0` Pod 削除→再作成後も 188 テーブル・管理者ユーザ保持。

### 10.4 S3 オブジェクトストレージ（`40-minio.yaml`）＋ ファイルLocation化
- **MinIO**（S3互換, PVC）＋バケット `weko-backup`/`weko-content`/`weko-esbackup` ＋ **テナント別 `weko-<tenant>`**。
- テナント Secret の `S3_*` に接続情報（`http://minio:9000`, key=`wekominio`）。
- **WEKO のアップロード先＝S3(MinIO) Location**（`set-s3-location.sh`）: 各テナントDBの `files_location` を `type='s3'` / `uri='s3://weko-<tenant>'` ＋ `access_key`/`secret_key`/`s3_endpoint_url`/`s3_send_file_directly=true`/`s3_default_block_size=5242880`/`s3_signature_version='s3v4'` に UPDATE。weko は `invenio-s3` の s3fs 経由で MinIO バケットへ保存。
  - **核心の落とし穴**: `invenio-s3` `storage.py _get_fs` は `location.type=='s3'` の時だけ location の S3情報で s3fs 接続する。`type` が `None` のままだと PyFilesystem2 にフォールバックし `AWS_ACCESS_KEY_ID not set` で失敗。→ 必ず `type='s3'` に設定。path-style・`signature_version=s3v4` は invenio-s3 が処理。
  - `gen-tenant.sh` が `instance.cfg` の `S3_ACCCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_ENDPOINT_URL`（web/worker 両方）を環境変数から読む配線を実施。
  - 検証済（arm64実機）: tenant1→`s3://weko-tenant1/...`, tenant2→`s3://weko-tenant2/...` に実オブジェクト確認。NFS共有(RWX)はテーマ由来 conf/data のみ（アップロード実体は含まない）。
- 検証: `pg_dumpall` → `weko-backup/postgres/` へバックアップ（initContainer で dump→mc upload の2段 Job）。

### 10.5 実装上の落とし穴（実際に踏んだもの）
| 症状 | 原因 | 対処 |
|---|---|---|
| ES `index init` 失敗 `kui.txt` | ES に辞書ファイル無し | `es-kui` ConfigMap をマウント |
| トップ 500 `_adjust_shib_admin_DB` | 空 `admin_settings` の `max(id)+1` | シード行 1 件 INSERT ＋ web 再起動 |
| `bash -s < file` / パイプが空実行 | `nohup` の stdin が /dev/null | スクリプトを `base64` 化し pod 内で `base64 -d \| bash` |
| `pkill -f port-forward` が exit 144 | 自コマンド行に自己マッチし自己 kill | その文字列を含む pkill を避ける |
| S3アップロード `AWS_ACCESS_KEY_ID not set` | `files_location.type` が `None` で invenio-s3 が PyFilesystem2 にフォールバック | `set-s3-location.sh` で `type='s3'`＋S3情報を UPDATE |
| mc の Job が起動しない | mc イメージの entrypoint | Job で `command:["/bin/sh","-c"]` に上書き（`kubectl run -- sh -c` は不可） |
| 初回リクエストが遅い/タイムアウト | emulation ＋ JIT | 初回は `--max-time 240`。2回目以降は数秒 |

### 10.6 実機検証(2026-07-23)で判明した落とし穴と修正
| 症状 | 原因 | 対処（反映済み） |
|---|---|---|
| `RabbitmqCluster` 適用が webhook 呼び出し失敗 | Cluster Operator の webhook 起動前に CR を適用 | `deploy-*.sh` で operator の `rollout status` 待ち＋CR適用リトライ |
| 静的PVのNFSマウントが `access denied by server` | 動的プロビジョナ(ganesha)は自分が作った volume しかエクスポートしない | `60-nfs-server.yaml` の postStart で `/export` 全体の静的EXPORTを dbus 追加 |
| ganesha が起動しなくなる | `/export/vfs.conf` を直接追記すると provisioner の再生成と競合して破損 | EXPORT は**別ファイル**(`/export/static-export.conf`)に書き dbus `AddExport` で追加 |
| テンプレート投入が無言で失敗 | `nfs-provisioner` イメージに `tar` が無い／busybox の `cp -an` がコピーしない | busybox ヘルパーPod経由＋**tarを宛先へ直接展開**(`-k` で非破壊) |
| celery が `ACCESS_REFUSED` でCrashLoop | RabbitMQ に `weko` ユーザが存在しない（operatorは生成ユーザのみ） | `provision-tenants.sh` で `add_user`/`set_user_tags`/`set_permissions` |
| arm64 で `shibauthorizer`/`shibresponder` が起動しない | `supervisord.conf` が `/usr/lib/x86_64-linux-gnu/shibboleth/` を決め打ち | nginx イメージビルド時に `aarch64-linux-gnu` へ置換（`deploy-arm64.sh`） |
| トップが500 `styles.scss` が無い | `static` を emptyDir 化したことでイメージ同梱の静的ファイルが隠れる | `seed-static` initContainer でイメージから静的ファイルをシード |
| nginx が `unknown "shib_mail" variable` で起動不可 | 本番 `weko.conf`(shib変数を定義)と `nginx.conf`(log_formatで参照)は不可分。片方だけ無効化すると壊れる | 既定は**イメージ同梱の /etc/nginx 一式**を使用し、`WEKO_NGINX_SHIB=yes` の時だけ本番テンプレートを投入 |
| NFSマウント中に `kind delete cluster` するとノードが削除不能 | NFSサーバ消滅でマウントがハング（D状態） | Podを先に削除してからクラスタ削除。詰まった場合は root 権限で `docker rm -f` |

---

## 9. 運用コマンド early reference

```bash
# クラスタ一覧 / 削除
kind get clusters
kind delete cluster --name weko3

# コンテキスト
kubectl config current-context          # kind-weko3
kubectl config use-context kind-weko3

# 状態確認
kubectl get nodes -o wide
kubectl get pods -A

# ノードへの入りかた（kind ノードは docker コンテナ）
docker exec -it weko3-control-plane bash
```

---

## 付録: 構築済みの状態サマリ

| コンポーネント | 状態 |
|---|---|
| kind クラスタ `weko3` | ✅ 稼働中（context: `kind-weko3`） |
| ノード | ✅ control-plane 1 + worker 2（`nodeType=WEKO`/`DATA`） |
| APIサーバ等コントロールプレーン | ✅ すべて Running |
| ingress-nginx | ✅ Running（host 80/443） |
| amd64 エミュレーション | ✅ 有効（クラスタ内 `uname -m`→`x86_64` 確認済み） |
| PostgreSQL | ✅ **Patroni 3ノードHA**（Zalando operator, arm64 spilo-17, master+replica×2） |
| RabbitMQ | ✅ **3ノードクラスタ**（Cluster Operator, rabbitmq:4.0.9） |
| Elasticsearch | ✅ **3ノードクラスタ**（**arm64ネイティブ**, 本物kui.txt/kuromoji/repository-s3, green・シャード分散） |
| Redis | ✅ Sentinel HA（`weko3re`: master+replica×2+sentinel×3） |
| MinIO(S3) | ✅ 稼働（バケット3種＋テナント別 `weko-<tenant>`, pg_dumpall バックアップ実演済み） |
| ファイルLocation | ✅ **S3(MinIO)**（`files_location.type='s3'`, `uri=s3://weko-<tenant>`）。両テナント アップロード→MinIO 確認済み |
| weko 本体 | ✅ **arm64ネイティブ**（`weko3-web:arm64`）。起動5秒・qemu不安定性ゼロ・両テナント 3/3 |
| マルチテナント | ✅ tenant1 / tenant2 独立稼働 |
| サイト疎通 | ✅ 両テナントとも `/`200・`/login/`200・`/admin/`302・`/api/records/`200（**200×15/15安定**） |
| 　　管理者 | tenant1: `admin@example.org`/`adminpass123`、tenant2: `admin@tenant2.local`/`adminpass2` |
| データ永続化 | ✅ PVC 15本。Pod 再起動でデータ保持を確認 |
| 実測メモリ | ✅ 全体 ~18 GiB（64GB に収まる） |
