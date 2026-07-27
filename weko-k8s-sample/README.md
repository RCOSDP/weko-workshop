# weko3 on kubernetes (kind) 構築ランブック

単一ホスト上に **kind** で Kubernetes クラスタ（ノード＋APIサーバ）を自前構築し、
[RCOSDP/weko-k8s](https://github.com/RCOSDP/weko-k8s) を土台に **weko3** を動かすまでの手順。

- 検証環境: arm64 / 20 core / 121GB RAM / Docker 29（sudo 不可, docker は sudo なしで実行可）
- 所要時間の目安: 初回フル構築で約 90〜120 分（大半は amd64 エミュレーション下の初期化待ち）
- 詳細な背景・落とし穴の解説は [`CONSTRUCTION.md`](./CONSTRUCTION.md) を参照

### この手順の到達点（現在の構成）
- **マルチテナント**（`tenant1.localhost` / `tenant2.localhost` が独立稼働）
- **Redis Sentinel HA** / **データ永続化(PVC)** / **S3(MinIO)** まで適用済み（本番忠実度アップ）

読み方（3ルート）:
- **ルートA（学習向け）**: **§1〜9 で単一テナント最小構成を素から** → **[マルチテナント構成](#マルチテナント構成)** →
  **[本番忠実度アップグレード](#本番忠実度アップグレードredis-sentinel--永続化--s3)** → **[HAクラスタ化](#haクラスタ化operator方式と-arm64-ネイティブ化)** → **[NFS](#nfs-共有ストレージ本番の-fs-config-fs-data-相当)** と段階的に積み上げる。
- **ルートB（本番忠実度を一気に）**: **[付録B の一括ランブック](#付録b-本番忠実度構成をゼロから構築する一括ランブック)** を上から実行すれば、最初から Sentinel＋永続化＋S3＋マルチテナントで立ち上がる（PG/RabbitMQ は**単体**）。
- **ルートD（現フル構成＝最終形を素から一発）**: **[付録D の一気通貫ランブック](#付録d-arm64-で現フル構成最終形を素から一気通貫で構築する)** = `k8s-weko/deploy-arm64.sh` 一発で、**HAクラスタ(PG Patroni3/RabbitMQ3/ES3)＋Sentinel＋永続化＋NFS＋S3(MinIO) Location＋マルチテナント**（＝実機の現構成）を素から構築。amd64 は `k8s-weko-amd64/deploy-amd64.sh`。

> **サーバが x86_64 / amd64 の場合**: 本文は arm64 前提だが、amd64 なら emulation も arm64 ビルドも不要で**より簡単**。
> 差分は **[付録C: arm64 が無い場合のランブック](#付録c-arm64-が無い場合x86_64--amd64-サーバのランブック)** を参照。

---

## 全体像（最終構成）

```
[ホスト:arm64]  kind クラスタ "weko3"
  control-plane … APIサーバ等 + ingress-nginx (host 80/443)
  worker  (nodeType=WEKO) … tenant1-web / tenant2-web  (各 nginx + web(uwsgi) + worker(celery))
  worker2 (nodeType=DATA) … 共有[全PVC]: PostgreSQL / Elasticsearch / RabbitMQ / MinIO(S3)
                            namespace weko3re … Redis master + replica×2 + sentinel×3 [全PVC]
```

| テナント別に分離 | 共有バックエンド |
|---|---|
| Web Pod + Ingress（host=FQDN）／PostgreSQL DB 名／ES インデックス接頭辞／RabbitMQ vhost／Redis DB 番号 | PostgreSQL・Elasticsearch・RabbitMQ・Redis(Sentinel)・MinIO(S3) |

| 要素 | 採用 | 備考 |
|---|---|---|
| weko 本体 | **最新ソースからビルド**（`weko3-web:arm64` / `weko3-web:amd64`） | 既成イメージを使う場合のみ `WEKO_IMAGE` を指定 |
| DB | PostgreSQL 13（arm64, PVC永続化） | テナント別 DB |
| キャッシュ/セッション | **Redis 6.2 Sentinel HA**（arm64, PVC） | `CACHE_TYPE=redissentinel`。テナントは DB 番号で分離 |
| キュー | RabbitMQ 3.13（arm64, PVC） | quorum queue。テナント別 vhost `<name>/` |
| 検索 | **Elasticsearch 6.8.23**（自前ビルド amd64 + kuromoji/icu, PVC） | weko は **ES6 系必須**（client `elasticsearch==6.1.1`） |
| オブジェクトストレージ | **MinIO**（S3互換, arm64, PVC） | バックアップ/コンテンツ用（OCI Object Storage 相当） |
| 前段 | **WEKO nginx を自前ビルド**（`weko3-nginx:<arch>`, Shibboleth SP=shibd + nginx-http-shibboleth 入り） | 設定 `/etc/nginx` は本番同様 NFS(RWX)。既定は HTTP+`uwsgi_pass`、`WEKO_NGINX_SHIB=yes` で本番 `weko.conf`(Shibboleth/TLS) を有効化 |

> 注: §1〜9 の基本手順は **Redis 単体・emptyDir・単一テナント**の最小構成で解説する（学習しやすさ優先）。
> それを **Sentinel・PVC・マルチテナント**へ発展させる差分が後半の2節。

> **重要な前提**
> - WEKO3 は**最新ソースからビルド**して使う（手順 5）。ビルドしたイメージは `kind load` で投入する（クラスタ内 containerd からの直接 pull は不安定）。
> - 既成の公開イメージ（`mhayashi55/weko3-web` 等）は **amd64 専用**。使う場合のみ `WEKO_IMAGE` で指定し、arm64 では qemu エミュレーション登録（手順 3）が必要。

---

## 1. ツール導入（kubectl / kind）

`~/.local/bin`（PATH 内）へ配置する。

```bash
mkdir -p ~/.local/bin

KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/arm64/kubectl"
chmod +x ~/.local/bin/kubectl

curl -sLo ~/.local/bin/kind "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-arm64"
chmod +x ~/.local/bin/kind

hash -r; kubectl version --client; kind version
```

## 2. kind クラスタ作成（3ノード）

```bash
cd /home/mhaya/weko-k8s-sample
kind create cluster --config kind-weko-cluster.yaml --wait 120s

kubectl get nodes -L nodeType,ingress-ready   # 3ノード Ready を確認
```

`kind-weko-cluster.yaml` … control-plane(80/443 公開) + worker(`nodeType=WEKO`) + worker2(`nodeType=DATA`)。

## 3. Ingress と amd64 エミュレーション

```bash
# ingress-nginx
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
kubectl wait -n ingress-nginx --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=150s

# amd64 エミュレーション登録（ホストカーネル＝kindノードと共有）
docker run --rm --privileged tonistiigi/binfmt --install amd64
```

## 4. Elasticsearch イメージのビルド（ES6.8.23 + kuromoji/icu）

```bash
cd /home/mhaya/weko-k8s-sample/k8s-weko
docker buildx build --platform linux/amd64 -f Dockerfile.es \
  -t weko-elasticsearch:6.8.23 --load .
kind load docker-image weko-elasticsearch:6.8.23 --name weko3
```

## 5. weko 本体イメージのビルド（最新ソースから）

WEKO3 は**既成イメージを使わず、最新ソースを取得してビルド**する（`deploy-*.sh` の 0)/2) も同じ）。

```bash
# 最新ソース取得（既に clone 済みなら pull）
git clone https://github.com/RCOSDP/weko.git /home/mhaya/weko    # 既存なら: git -C /home/mhaya/weko pull --ff-only
cd /home/mhaya/weko
# arm64 ホスト: Dockerfile.arm64 が無ければ Dockerfile（内容は同一）
docker build -f Dockerfile.arm64 -t weko3-web:arm64 .            # amd64 ホスト: -f Dockerfile -t weko3-web:amd64
kind load docker-image weko3-web:arm64 --name weko3
```

> **既成イメージ（Docker Hub 等）を使いたい場合**のみ `WEKO_IMAGE=<repo>/<name>:<tag>` を指定する（その場合ビルドはスキップされ pull される）。
> ビルド結果を Docker Hub に登録する手順は **[イメージのビルドと Docker Hub 登録・差し替え](#weko-イメージのビルドと-docker-hub-登録差し替え)** を参照。

## 6. バックエンド + weko 本体のデプロイ

```bash
cd /home/mhaya/weko-k8s-sample/k8s-weko
kubectl apply -f 00-namespace.yaml \
              -f 10-postgresql.yaml \
              -f 11-redis.yaml \
              -f 12-rabbitmq.yaml \
              -f 13-elasticsearch.yaml \
              -f 20-weko-config.yaml \
              -f 21-nginx-config.yaml \
              -f 30-weko-web.yaml

# バックエンドと weko-web が Running になるまで待つ（ES/web はエミュレーションで数分）
kubectl get pods -n weko3 -w
```

- `13-elasticsearch.yaml` には `kui.txt`（空）の ConfigMap を含み ES config にマウント（weko の item マッピングが参照するため必須）。
- `30-weko-web.yaml` の Pod = `nginx` + `web(uwsgi:5000)` + `worker(celery)`。起動時に `jinja2` で invenio.cfg を生成。

## 7. DB / ES 初期化

```bash
POD=$(kubectl get pod -n weko3 -l app=weko-web -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n weko3 $POD -c web -- bash -s < weko-init.sh
```

`weko-init.sh` の内容（weko 同梱 `populate-instance.sh` 相当）:
`invenio db init/create` → `stats/logging partition` → `index init` / `index queue init`
→ ES ILM・stats インデックス作成 → `files location` → users / roles / access 付与。

> ⚠️ エミュレーションのため各 `invenio` コマンドは 30〜60 秒。初期化全体で 30〜40 分程度かかる。

## 8. 500 対策（admin_settings シード）と再起動

初期化直後はトップページが `_adjust_shib_admin_DB`（空の `admin_settings` に `max(id)+1`）で **HTTP 500** になる。
シード行を1件入れて web を再起動する。

```bash
PG=$(kubectl get pod -n weko3 -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n weko3 $PG -- psql -U weko -d wekodb \
  -c "INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb) ON CONFLICT DO NOTHING;"

kubectl rollout restart deployment/weko-web -n weko3
kubectl rollout status deployment/weko-web -n weko3 --timeout=300s
```

## 9. 疎通確認

```bash
# 初回は before_first_request + JIT でエミュレーション下は遅い（要ウォームアップ）
curl -s -o /dev/null -w "warmup: %{http_code} (%{time_total}s)\n" -H "Host: localhost" http://localhost/ --max-time 240
curl -s -o /dev/null -w "top:    %{http_code}\n" -H "Host: localhost" http://localhost/
curl -s -o /dev/null -w "login:  %{http_code}\n" -H "Host: localhost" http://localhost/login/
curl -s -o /dev/null -w "search: %{http_code}\n" -H "Host: localhost" "http://localhost/api/records/?size=1"
```

期待値: top **200** / login **200** / admin **302** / api/records **200**。

| 項目 | 値 |
|---|---|
| URL | `http://localhost/` |
| 管理者 | `admin@example.org` / `adminpass123` |
| 名前空間 | `weko3` |

---

## 運用・後始末

```bash
kubectl get pods -n weko3                 # 状態確認
kubectl logs -n weko3 <pod> -c web        # weko ログ
docker exec -it weko3-control-plane bash  # ノード（kindはdockerコンテナ）

kind delete cluster --name weko3          # 全削除
```

## 64GB メモリ環境について

本構成は全ノード合計 **実測 ~5GiB** で動作（ES 最大 ~2.5Gi・weko-web ~1.3Gi ほか）。
既定マニフェストは 64GB 想定の資源プロファイル（ES heap 1g / uwsgi processes=2 / celery `-c 1`、limits 合計 ~8.8Gi）。
増減の指針は [`CONSTRUCTION.md` の §8bis](./CONSTRUCTION.md) を参照。

## マルチテナント構成

複数の weko3 リポジトリ（テナント）を同一クラスタで運用する。weko-k8s 本来の方式に倣い、
**バックエンド（PostgreSQL / Elasticsearch / RabbitMQ）は共有**し、テナントごとに以下を分離する。

| 分離対象 | 実現方法 |
|---|---|
| データベース | PostgreSQL の DB を分ける（`INVENIO_POSTGRESQL_DBNAME`） |
| 検索インデックス | ES インデックス接頭辞を分ける（`SEARCH_INDEX_PREFIX`） |
| メッセージング | RabbitMQ vhost を分ける（`<NAME>/`。本家 `make_rabbitmq_vhost.sh` と同一命名） |
| キャッシュ/セッション | テナント専用 Redis（`redis-<NAME>`） |
| Web/公開 | テナントごとに Deployment + Service + Ingress（`host = <W3FQDN>`） |
| 秘密鍵 | `SECRET_KEY` / `WTF_CSRF_SECRET_KEY` / `WEKO_RECORDS_UI_SECRET_KEY` を**テナント毎に別値**（テナント内は共通値）。`gen-tenant.sh` が `.secret-seed`（初回に自動生成・要バックアップ）から導出し、再生成しても同じ値になる |
| Shibboleth / nginx 設定 | NFS 上の `/fs-shibboleth/<tenant>` `/fs-nginx/<tenant>` をテナント別の静的PVで分離（`provision-nfs.sh` で投入） |

### テナント定義とデプロイ

```bash
cd k8s-weko

# 1) tenants.txt を編集（NAME  DBNAME  HOST  ADMIN_EMAIL  ADMIN_PASS  INIT）
cat tenants.txt

# 2) マニフェスト生成 → 適用
bash gen-tenant.sh                       # generated/<name>.yaml を生成
kubectl apply -f generated/

# 3) DB / RabbitMQ vhost をプロビジョニング
bash provision-tenants.sh

# 4) 各テナントを初期化（INIT=yes のテナント。約30〜40分/テナント・並列実行可）
POD=$(kubectl get pod -n weko3 -l app=<NAME>-web -o jsonpath='{.items[0].metadata.name}')
kubectl exec -i -n weko3 $POD -c web -- bash -s < weko-init.sh
#   初期化後、admin_settings シード + web 再起動（手順 8 と同じ）
kubectl exec -n weko3 <postgres-pod> -- psql -U weko -d <DBNAME> \
  -c "INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb) ON CONFLICT DO NOTHING;"
kubectl rollout restart deployment/<NAME>-web -n weko3

# 5) （MinIO をデプロイ済みの場合）ファイル保存先を S3(MinIO) Location に
bash set-s3-location.sh                   # weko-<tenant> バケット作成 + files_location を type='s3' に
```

> `tenants.txt` の `INIT=no` は既存 DB/インデックスを再利用（初期化スキップ）。
> 本構成では `tenant1` が単一テナント時の `wekodb` を再利用している。

### 動作確認（実測）

2テナント（`tenant1.localhost` / `tenant2.localhost`）が独立稼働:

```
tenant1.localhost  /  200  /login 200  /admin 302  /api/records 200
tenant2.localhost  /  200  /login 200  /admin 302  /api/records 200
```

| 分離層 | tenant1 | tenant2 |
|---|---|---|
| ES index | `wekodb-*` | `tenant2-*` |
| PostgreSQL DB | `wekodb` | `tenant2` |
| RabbitMQ vhost | `tenant1/` | `tenant2/` |
| Redis | `redis-tenant1` | `redis-tenant2` |
| 管理者 | `admin@example.org` | `admin@tenant2.local` |

- アクセス: `http://tenant1.localhost/` , `http://tenant2.localhost/`（`*.localhost` はループバックに解決）
- 2テナント合計でもホストメモリ使用は約 **14GiB**（64GB に十分収まる。テナント増加分は概ね web ~1.3Gi + redis 数十Mi/テナント）

### テナント追加

`tenants.txt` に1行足して `gen-tenant.sh` → `kubectl apply -f generated/` → `provision-tenants.sh` → 初期化、で増設できる。

### ポートフォワードでのアクセス（リモート/ブラウザ）

ホスト外（SSH 越しなど）からブラウザで両テナントを開く場合。テナントは **Host ヘッダ**で振り分けるため、
ホスト名が weko の `INVENIO_WEB_HOST_NAME` と一致している必要がある。**方式A（Ingressへ1本）を推奨**。

**方式A: Ingress に1本だけ port-forward（Host で振り分け・検証済み）★推奨**

port-forward は**常駐プロセス**なので、専用ターミナルを1つ開いて実行し、そのまま開いておく。
この環境では `*.localhost` が **IPv6(`::1`)** に解決されるため、`--address` に `::1` も含める。
```bash
# 専用ターミナルで実行(開いたまま)。Ctrl+C で停止。
kubectl port-forward -n ingress-nginx --address 127.0.0.1,::1 \
  svc/ingress-nginx-controller 8080:80
```
ブラウザで `http://tenant1.localhost:8080/` と `http://tenant2.localhost:8080/`
（Ingress はポート番号を無視しホスト名でルーティングするため、1本の port-forward で両テナントに到達）。
別ターミナルでの curl 検証:
```bash
curl -H "Host: tenant1.localhost" http://127.0.0.1:8080/   # 200
curl -H "Host: tenant2.localhost" http://127.0.0.1:8080/   # 200
```

> **補足**: 本 kind クラスタは Ingress を **ホストの 80/443 に直結公開済み**（`kind-weko-cluster.yaml` の
> `extraPortMappings`）。**このホスト上のブラウザなら port-forward 無しで**
> `http://tenant1.localhost/` `http://tenant2.localhost/` に直接アクセスできる（検証済み: 両者 200）。
> port-forward が要るのは「ポート80を使いたくない」「別ポートで出したい」場合。

**リモート（別PCのブラウザ）から使う場合:**
```bash
# サーバ側(専用ターミナル):
kubectl port-forward -n ingress-nginx svc/ingress-nginx-controller 8080:80
# 手元PC: SSH トンネルを張る
ssh -L 8080:localhost:8080 <user>@<server>
# 手元PCのブラウザ: http://tenant1.localhost:8080/  /  http://tenant2.localhost:8080/
#   （手元PCの *.localhost はローカルループバックに解決 → トンネル経由でサーバの pf へ）
```

**方式B: テナントごとに個別 port-forward（ポートで分離・検証済み）**
```bash
kubectl port-forward -n weko3 svc/tenant1-nginx 8081:80    # → http://localhost:8081/
kubectl port-forward -n weko3 svc/tenant2-nginx 8082:80    # → http://localhost:8082/
```
ページは表示される（pod 内 nginx は `server_name _`、weko の `APP_ALLOWED_HOSTS` 未設定で任意 Host 許可）。
ただし `THEME_SITEURL` が `http://<W3FQDN>` 固定のため、**絶対リンク/リダイレクトは元のホスト名を指す**。
ブラウザ運用なら方式A（ホスト名一致）が無難。

> SSH 経由なら手元PCで `ssh -L 8080:localhost:8080 <server>` 併用、または
> `kubectl port-forward --address 0.0.0.0 ...` でLAN公開（要ファイアウォール考慮）。

---

## 本番忠実度アップグレード（Redis Sentinel / 永続化 / S3）

より本番（JAIRO Cloud）に近づけるため、以下を適用済み。マニフェストは `k8s-weko/`。

### Redis Sentinel 化（`41-redis-sentinel.yaml`）
- namespace `weko3re` に **redis master + replica×2 + sentinel×3**（PVC永続化）。
  サービス名は instance.cfg 既定に合わせ `weko-sentinel-service.weko3re:26379`、master=`mymaster`。
- weko 側は `CACHE_TYPE='redissentinel'`（web/worker 起動時に instance.cfg を sed で切替）。
- テナントは **共有 Redis を DB 番号で分離**（tenant1=0/1/2, tenant2=5/6/7。`CRAWLER=3`/`GROUP_INFO=4` 予約を回避）。
- 検証: worker が sentinel 経由で `ready`、master→replica 複製、`sentinel master mymaster` が quorum=2 で認識。

### データ永続化（PVC / kind `standard` StorageClass）
- PostgreSQL / Elasticsearch / RabbitMQ / Redis(×3) / MinIO をすべて **PVC 化**（emptyDir 廃止）。
- PostgreSQL は **`pg_dumpall` → PVC版へ再デプロイ → restore** でデータ保持（再初期化を回避）。
- 検証: `postgresql-0` Pod を削除→同一 PVC で再作成後も **188 テーブル・管理者ユーザ保持**。

### S3 オブジェクトストレージ（`40-minio.yaml`）
- **MinIO**（S3互換, PVC）をデプロイ。バケット `weko-backup` / `weko-content` / `weko-esbackup` ＋ **テナント別 `weko-<tenant>`（ファイルLocation実体）**。
- 各テナントの Secret に S3 接続情報を投入（`S3_ENDPOINT_URL=http://minio:9000`, key=`wekominio`）。
- **WEKO のアップロード先＝S3(MinIO) Location**: 初期化後に `set-s3-location.sh` で各テナントDBの `files_location` を `type='s3'` / `uri='s3://weko-<tenant>'` に設定（下記「適用手順」参照）。`type` を `s3` にしないと invenio-s3 が PyFilesystem2 にフォールバックして `AWS_ACCESS_KEY_ID not set` で失敗する。
- バックアップ実演: `pg_dumpall` を `weko-backup/postgres/` へアップロード（JAIRO Cloud の Object Storage 相当）。
- コンソール: `kubectl port-forward -n weko3 svc/minio 9001:9001` → `http://localhost:9001`（wekominio / wekominio-secret-key）。

### 適用手順（要約）
```bash
cd k8s-weko
kubectl apply -f 40-minio.yaml          # S3(MinIO)
kubectl apply -f 41-redis-sentinel.yaml # Redis Sentinel(weko3re)
# PG/ES/RabbitMQ を PVC 版へ（データ保持する場合は事前に pg_dumpall → restore）
kubectl apply -f 10-postgresql.yaml -f 13-elasticsearch.yaml -f 12-rabbitmq.yaml
bash gen-tenant.sh && kubectl apply -f generated/   # redissentinel + S3配線 版テナント
bash provision-tenants.sh                            # vhost 再作成
# ES インデックス再作成(各テナントの web コンテナで es-reinit.sh)
# 初期化 + admin_settings シードの後、ファイル保存先を S3(MinIO)に:
bash set-s3-location.sh                              # weko-<tenant> バケット作成 + files_location を type='s3' に
```

### まだ本番と異なる点（さらなる忠実化の候補）
- PostgreSQL の HA（postgres-operator/Spilo + pgpool）は現フル構成（付録D / `deploy-*.sh`）で導入済み。pgbouncer は未導入。
- F5 NGINX App Protect(WAF)、Shibboleth/学認認証、flustd ログ集約、Prometheus 監視は未導入。
- Ingress のテナント別 TLS 証明書（現状は Ingress 既定の自己署名）。

---

## WEKO イメージのビルドと Docker Hub 登録・差し替え

WEKO 本体イメージを**自前ビルド → Docker Hub 登録 → デプロイで差し替え**できるようにしてある。
デプロイ側は `WEKO_IMAGE` 環境変数でイメージを指定する（未指定なら既定の自前/公開イメージ）。

- 既定イメージ: arm64=`weko3-web:arm64` / amd64=`weko3-web:amd64`（いずれも **最新ソースからのローカルビルド**）。`WEKO_IMAGE` を指定した時だけ既成イメージを pull。
- 差し替え点は1箇所: `gen-tenant.sh` / `deploy-*.sh` が読む `WEKO_IMAGE`（web・worker・seed initContainer の3箇所へ一括反映）。nginx は `WEKO_NGINX_IMAGE`。
- ソースは同一 `Dockerfile`（`python:3.6-slim-buster` はマルチアーチ。`Dockerfile.arm64` は内容が **Dockerfile と同一**）。

### ビルド & push（`build-push-weko.sh`）
```bash
cd /home/mhaya/weko-k8s-sample
# 例: Docker Hub の <user>/weko3-web:v1 として登録
DOCKERHUB_USER=<user> REPO=weko3-web ./build-push-weko.sh native v1
#   native    … 実行ホストの arch でビルド→push（推奨・確実）
#   multiarch … buildx で amd64+arm64 を1タグに（要 binfmt。arm64ホストでの amd64 ビルドは低速）
#   manifest  … 各archホストで ARCH_SUFFIX=yes native 済みの :v1-amd64/:v1-arm64 を束ねて :v1 に
```
`docker login` 未実施なら自動で促す（Docker Hub の**アクセストークン**推奨）。

**両アーキ対応イメージを作る2通り**:
| 方法 | コマンド | 備考 |
|---|---|---|
| **各archホストでネイティブ+manifest**（推奨・確実） | 各ホストで `ARCH_SUFFIX=yes ./build-push-weko.sh native v1` → いずれかで `./build-push-weko.sh manifest v1` | C拡張のビルドが確実 |
| **buildxで一発マルチアーチ** | `./build-push-weko.sh multiarch v1` | 手軽だが非ネイティブarchは qemu で低速 |

### デプロイで差し替え
```bash
# 一気通貫デプロイで使う（ビルドをスキップして push 済みイメージを pull）
WEKO_IMAGE=<user>/weko3-web:v1 bash k8s-weko/deploy-arm64.sh          # arm64
WEKO_IMAGE=<user>/weko3-web:v1 bash k8s-weko-amd64/deploy-amd64.sh    # amd64

# 既存クラスタで web だけ入れ替える（マニフェスト再生成→適用→ロールアウト）
cd k8s-weko
WEKO_IMAGE=<user>/weko3-web:v1 bash gen-tenant.sh
kubectl apply -f generated/
kubectl rollout restart -n weko3 $(awk '!/^#|^$/{print "deploy/"$1"-web"}' tenants.txt | tr '\n' ' ')
```
> kind はローカルイメージを使うため、`kind load docker-image <user>/weko3-web:v1 --name weko3` 済みか、
> ノードから pull 可能（Docker Hub public か imagePullSecret 設定）である必要がある。`deploy-*.sh` は自動で `kind load` する。

---

## 付録B: 本番忠実度構成をゼロから構築する一括ランブック

まっさらな状態から、**最初から Sentinel＋永続化(PVC)＋S3(MinIO)＋マルチテナント**で立ち上げる手順。
ルートA（段階的）と違い、簡素版バックエンドを経由せず**本番寄り構成を直接**デプロイする。
（既存クラスタを作り直す場合は先に `kind delete cluster --name weko3`）

作業ディレクトリは `cd /home/mhaya/weko-k8s-sample`。マニフェストは `k8s-weko/` を使用。

### B-1. ツール導入（kubectl / kind）
```bash
mkdir -p ~/.local/bin
KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/arm64/kubectl"
curl -sLo ~/.local/bin/kind "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-arm64"
chmod +x ~/.local/bin/kubectl ~/.local/bin/kind; hash -r
```

### B-2. クラスタ＋Ingress＋amd64エミュレーション
```bash
kind create cluster --config kind-weko-cluster.yaml --wait 120s
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
kubectl wait -n ingress-nginx --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=150s
docker run --rm --privileged tonistiigi/binfmt --install amd64
```

### B-3. イメージ準備（ESビルド＋weko本体ロード）
```bash
cd k8s-weko
docker buildx build --platform linux/amd64 -f Dockerfile.es -t weko-elasticsearch:6.8.23 --load .
kind load docker-image weko-elasticsearch:6.8.23 --name weko3
# WEKO3 は最新ソースからビルド（既成イメージは使わない）
git clone https://github.com/RCOSDP/weko.git /home/mhaya/weko 2>/dev/null || git -C /home/mhaya/weko pull --ff-only
docker build -f /home/mhaya/weko/Dockerfile -t weko3-web:arm64 /home/mhaya/weko
kind load docker-image weko3-web:arm64 --name weko3
```

### B-4. 共有基盤（namespace / nginx設定 / S3 / Sentinel / 永続化バックエンド）
```bash
kubectl apply -f 00-namespace.yaml -f 21-nginx-config.yaml
kubectl apply -f 40-minio.yaml            # S3(MinIO) + PVC
kubectl apply -f 41-redis-sentinel.yaml   # Redis Sentinel HA(weko3re) + PVC
kubectl apply -f 10-postgresql.yaml -f 13-elasticsearch.yaml -f 12-rabbitmq.yaml   # PG/ES/MQ 全PVC版
# 準備完了待ち
kubectl wait -n weko3 --for=condition=ready pod -l app=postgresql --timeout=180s
kubectl wait -n weko3 --for=condition=ready pod -l app=elasticsearch --timeout=300s
kubectl wait -n weko3 --for=condition=ready pod -l app=rabbitmq --timeout=180s
kubectl wait -n weko3re --for=condition=ready pod -l app=redis --timeout=180s
# MinIO バケット作成
kubectl run mc-init -n weko3 --rm -i --restart=Never --image=minio/mc:RELEASE.2025-04-08T15-39-49Z -- \
  sh -c 'mc alias set l http://minio:9000 wekominio wekominio-secret-key && mc mb -p l/weko-backup l/weko-content l/weko-esbackup'
```

### B-5. テナント定義 → 生成 → プロビジョニング
`k8s-weko/tenants.txt` を用意（ゼロ構築では **INIT=yes** ＝新規初期化）。例:
```
# NAME  DBNAME  HOST  ADMIN_EMAIL  ADMIN_PASS  INIT  CACHE_DB SESSION_DB CELERY_DB
tenant1  tenant1  tenant1.localhost  admin@tenant1.local  adminpass1  yes  0 1 2
tenant2  tenant2  tenant2.localhost  admin@tenant2.local  adminpass2  yes  5 6 7
```
> Redis DB は `CRAWLER=3`/`GROUP_INFO=4` 予約を避けて割当（tenant1=0/1/2, tenant2=5/6/7, …）。
```bash
bash gen-tenant.sh                    # generated/<name>.yaml を生成 (redissentinel/S3/PVC対応)
kubectl apply -f generated/           # 各テナントの config/secret/web/svc/ingress
bash provision-tenants.sh             # テナント別 PostgreSQL DB と RabbitMQ vhost を作成
# web(uwsgi)が起動するまで待つ (emulationで数分)
for t in tenant1 tenant2; do
  kubectl rollout status deploy/${t}-web -n weko3 --timeout=600s
done
```

### B-6. 各テナントの初期化（DB＋ESを一括）
`weko-init.sh` は env 駆動で `db init/create → index init/queue init → ES stats → users/roles/access` を実行。
テナントごとに web コンテナ内で実行する（**各 30〜40 分**・エミュレーション。並列実行可）。
```bash
for t in tenant1 tenant2; do
  POD=$(kubectl get pod -n weko3 -l app=${t}-web -o jsonpath='{.items[0].metadata.name}')
  # 通常のターミナルでは stdin リダイレクトでOK:
  kubectl exec -i -n weko3 $POD -c web -- bash < weko-init.sh &
  # ↑うまく流れない環境では base64 経由が確実:
  # B64=$(base64 -w0 weko-init.sh); kubectl exec -n weko3 $POD -c web -- bash -lc "echo $B64 | base64 -d | bash" &
done
wait
```

### B-7. 500 対策（admin_settings シード）＋ web 再起動
```bash
PG=$(kubectl get pod -n weko3 -l app=postgresql -o jsonpath='{.items[0].metadata.name}')
for db in tenant1 tenant2; do
  kubectl exec -n weko3 $PG -- psql -U weko -d $db \
    -c "INSERT INTO admin_settings (id,name,settings) VALUES (0,'__seed__','{}'::jsonb) ON CONFLICT DO NOTHING;"
done
kubectl rollout restart deploy/tenant1-web deploy/tenant2-web -n weko3
for t in tenant1 tenant2; do kubectl rollout status deploy/${t}-web -n weko3 --timeout=600s; done

# ファイル保存先を S3(MinIO) Location に設定（バケット作成 + files_location を type='s3' に）
bash set-s3-location.sh
```
> `set-s3-location.sh` 後、アップロードは `s3://weko-<tenant>` (MinIO) に保存される。未実行だと `files_location.type` が `None` のままで、アップロード時に invenio-s3 が PyFilesystem2 にフォールバックし `AWS_ACCESS_KEY_ID not set` で失敗する。

### B-8. 疎通確認
```bash
# 初回はウォームアップに時間がかかる
for h in tenant1.localhost tenant2.localhost; do
  curl -s -o /dev/null -w "$h -> %{http_code}\n" -H "Host: $h" http://localhost/ --max-time 240
done
# 期待: 両テナント 200 / /admin 302 / /api/records 200
```

> **確認ポイント**: Redis Sentinel（`kubectl exec -n weko3re deploy/sentinel -- redis-cli -p 26379 sentinel master mymaster`）、
> 永続化（`kubectl get pvc -A`）、S3（`weko-backup` などのバケット ＋ テナント別 `weko-<tenant>`）、
> ファイルLocation（`kubectl exec -n weko3 <PG> -- psql -U weko -d tenant1 -c "SELECT name,type,uri FROM files_location;"` が `type=s3` / `uri=s3://weko-tenant1`）。
> バックアップ例（`pg_dumpall`→MinIO）や port-forward は上記各節を参照。

---

## HAクラスタ化（operator方式）と arm64 ネイティブ化

本番（JAIRO Cloud）と同じ operator 方式でバックエンドを **3ノード HA クラスタ**にし、
weko 本体と Elasticsearch を **arm64 ネイティブ**にして emulation を排除した最終形。

### バックエンド3種のクラスタ化

| バックエンド | 方式 | マニフェスト/導入 |
|---|---|---|
| **PostgreSQL** | **Zalando postgres-operator** + Patroni 3ノード（arm64 spilo-17=PG17, 同期レプリケーション, master=`weko-postgresql` / replica=`weko-postgresql-repl`）| `51-postgresql-ha.yaml`（`postgresql` CR）+ `pgop-*.yaml`（operator）|
| **RabbitMQ** | **RabbitMQ Cluster Operator** + `RabbitmqCluster` 3ノード（rabbitmq:4.0.9）| `50-rabbitmq-cluster.yaml`（要 cert-manager）|
| **Elasticsearch** | **3ノードクラスタ**（arm64ネイティブ・本物kui.txt・kuromoji・repository-s3, zen discovery, replica=1でノード分散）| `13-elasticsearch.yaml`（`-E`引数でクラスタ設定）|

```bash
# operator 群
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml
kubectl apply -f pgop-*.yaml            # Zalando postgres-operator(ghcr.io/zalando 版=arm64)
# クラスタ本体
kubectl apply -f 50-rabbitmq-cluster.yaml 51-postgresql-ha.yaml 13-elasticsearch.yaml
```

**要点/落とし穴:**
- Zalando の `registry.opensource.zalan.do` ミラーは **amd64のみ** → **`ghcr.io/zalando`** 版を使う。spilo-13/14 は arm64 無し → **spilo-17**。
- postgres-operator は weko ユーザPWを生成値にリセットする → secret の password を `weko` に patch ＋ `ALTER ROLE weko PASSWORD 'weko'` で固定。接続先 `INVENIO_POSTGRESQL_HOST=weko-postgresql`。
- 最新 RabbitMQ operator の startup probe `/api/health/checks/reached-target-cluster-size` は **rabbitmq 4.0.9 に無く404** → `override.statefulSet` で `rabbitmq-diagnostics check_running` に置換。`additionalConfig` に `default_user` を書くと probe が壊れる。
- ES arm64 カスタムイメージは公式のような env→設定変換が無い → クラスタ設定は **`-E` コマンドライン引数**で渡す。

### weko 本体の arm64 ネイティブ化（安定性の決め手）

emulated amd64 の weko は qemu 上で**リクエスト処理時に segfault**し、そのコアダンプでディスクを食い潰す
（一度ホスト294GB→0で kind ノードのイメージ層が破損する事故が発生）。**arm64 ネイティブ化で根本解決**した。

```bash
cd /home/mhaya/weko                       # weko ソース一式が context
docker build -f Dockerfile.arm64 -t weko3-web:arm64 .
kind load docker-image weko3-web:arm64 --name weko3
# gen-tenant.sh の image を weko3-web:arm64 にして再デプロイ
```
効果: **アプリ起動 163秒→5秒（30倍速）**、qemu の segfault/コアダンプ/`listen queue full` が消滅、**200×15/15 で完全安定**。

### weko アプリ層のバグ修正（gen-tenant.sh の起動コマンドに組込・永続）

| 症状 | 原因 | 修正 |
|---|---|---|
| `/login/` が500（`RecursionError`）| `invenio_oauthclient` の before_first_request テンプレート上書きが**非冪等**で、並行リクエストで2回走ると `OAUTHCLIENT_LOGIN_USER_TEMPLATE_PARENT` が自己参照→無限 `extends` | invenio.cfg に `OAUTHCLIENT_TEMPLATE_KEY = None` を追記して上書き処理を無効化 |
| `/api/records/` が500（`KeyError: 'aggregations'`）| `RECORDS_REST_FACETS` が空でES応答に aggregations が無く、`fix_aggregations_accessrights` が**有効判定の前に** `data['aggregations']` を無条件参照 | `weko_search_ui/utils.py` を `data.get('aggregations', {})` に sed 修正 |

### 最終検証（両テナント）
```
/  → 200   /login/ → 200   /admin/ → 302   /api/records/ → 200   （すべて 200×15/15 で安定）
PostgreSQL: master+replica×2 / RabbitMQ: 3/3 / Elasticsearch: green・3ノード / Redis: Sentinel 6/6 / MinIO: 稼働
weko web: weko3-web:arm64（ネイティブ）  PVC 15本  ホストメモリ ~18GiB
```

---

## NFS 共有ストレージ（本番の `/fs-config` `/fs-data` 相当）

本番（JAIRO Cloud）は OKE File Storage=**NFS** の共有FS（`/fs-config` `/fs-data` `/fs-nginx` 等）を
`storageClassName: nfs` の PVC で weko web にマウントする。これを再現する。

### NFS サーバ（`60-nfs-server.yaml`）
- **nfs-ganesha（ユーザ空間NFS）** = `registry.k8s.io/sig-storage/nfs-provisioner`（**arm64ネイティブ・カーネルnfsd不要**）。
- 動的プロビジョナ付きで **RWX（ReadWriteMany）の StorageClass `nfs`** を提供。
```bash
kubectl apply -f 60-nfs-server.yaml
kubectl get sc nfs      # provisioner weko.example.com/nfs
```
> 落とし穴: ClusterRole に `services`/`endpoints` の `get` 権限が必要（プロビジョナが自 Service を引いて NFS IP を取得。無いと `error getting service` で ProvisioningFailed）。

### weko 共有FS を NFS(RWX) 化（`gen-tenant.sh` に組込済み）
本番の `config-pvc` / `data-pvc` 同様、テナント別に共有FSを NFS へ:

| マウント | 本番 | NFS PVC | 中身 |
|---|---|---|---|
| `.../var/instance/conf` | `/fs-config/<tenant>` | `<tenant>-conf`（静的PV, RWX 1Gi） | `invenio.cfg` / `uwsgi.ini` |
| `.../var/instance/data` | `/fs-data/<tenant>` | `<tenant>-data`（静的PV, RWX 5Gi） | テーマ `_variables.scss` / `indextree`（※アップロード実体は含まず→S3） |
| `/etc/shibboleth`（nginx） | `/fs-shibboleth/<tenant>` | `<tenant>-shib`（静的PV, RWX 1Gi） | Shibboleth SP 設定（`shibboleth2.xml` 他）。`provision-nfs.sh` が weko-k8s の `shibboleth_template` から投入し `__WEKO3_VHOST__` を FQDN に置換 |
| `/etc/nginx`（nginx） | `/fs-nginx/<tenant>` | `<tenant>-nginx-pvc`（静的PV, RWX 1Gi） | nginx 設定一式。`provision-nfs.sh` が `nginx_template` から投入（不足分は initContainer `seed-nginx` が weko nginx イメージから補完）し `server_name` をテナント FQDN に置換 |

**Pod 構成は本番 `weko-k8s/deploy/weko/manifest_template/deploy-web.yaml` と同じ形**:
initContainer `init`（jinja2 で `invenio.cfg` 生成）＋ `seed-data`／`seed-nginx` → コンテナ `nginx`(weko ビルド版・Shibboleth SP) / `web`(uwsgi) / `worker`(celery)、
`fsGroup: 1000` / `hostAliases`(自FQDN→127.0.0.1) / `RollingUpdate(maxSurge1,maxUnavailable0)` / `nodeSelector: nodeType=WEKO`、
共有FS は conf・data・shib・nginx（static は Pod ローカル emptyDir）。

実装上のポイント（`gen-tenant.sh` で自動化）:
- **conf**: NFSで空になるため起動時に `cp -f /code/scripts/uwsgi.ini` ＋ `jinja2` で `invenio.cfg` 生成（`var/instance/invenio.cfg` の絶対シンボリックリンクが NFS 上を指す）。
- **data**: 空 NFS だとイメージ内の `_variables.scss` が隠れ、CSS(sass) の `@import "../../../data/_variables"` が失敗して**トップが500**になる。→ **initContainer**（`weko3-web:arm64`）で NFS data を `/seed` にマウントし `cp -an .../data/. /seed/` でテーマファイルをシード。
- **アップロード先＝S3(MinIO) Location**（NFS共有ではない）: 初期化後に `set-s3-location.sh` で DB `files_location` を `type='s3'` / `uri='s3://weko-<tenant>'` ＋ S3接続情報（access_key/secret_key/s3_endpoint_url）に設定。weko は `invenio-s3` の s3fs 経由で MinIO バケットへ保存。
  - 注意: `location.type` が `None` のままだと invenio-s3 が PyFilesystem2 にフォールバックして `AWS_ACCESS_KEY_ID not set` で失敗する。必ず `type='s3'` にする。
  - `gen-tenant.sh` が `instance.cfg` の `S3_ACCCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_ENDPOINT_URL` を環境変数から読む配線を実施済み。path-style・`signature_version=s3v4` は invenio-s3 が処理。

### 検証（実測 2026-07-23・arm64実機で一気通貫デプロイ）
```
静的PV 8本 (conf/data/shib/nginx × 2テナント) すべて Bound・RWX・storageClass=nfs-static
NFS実体: /export/fs-config/<t>(2) /fs-data/<t>(3) /fs-shibboleth/<t>(25) /fs-nginx/<t>(13ファイル)
全エンドポイント: / 200 / /login/ 200 / /admin/ 302 / /api/records/ 200 （両テナント 200×10/10 安定）
PG: Leader + Sync Standby + Replica / ES: green 3ノード / Redis: 6/6 / RabbitMQ: weko ユーザ+vhost
files_location: type=s3, uri=s3://weko-<tenant> / 秘密鍵: テナント毎に別値
```

> **運用注意**: NFSをマウントしたPodが動いている状態で `kind delete cluster` すると、ノードコンテナ内の
> NFSマウントがハングし（NFSサーバが先に消えるため）コンテナが削除できなくなることがある。
> 先に `kubectl delete deploy -n weko3 --all` などでPodを落としてからクラスタを削除する。

### 永続化の全体像と注意
| 種別 | 対象 | 備考 |
|---|---|---|
| **local-path**（RWO） | PostgreSQL / Elasticsearch / RabbitMQ / Redis / MinIO / NFS export の裏 | Pod再起動で保持。`kind delete cluster` で消える |
| **NFS**（RWX） | テナント別 conf / data（`/fs-config` `/fs-data`） | 複数Pod/ノード共有。weko web の複数レプリカ化が可能 |

> **完全なホスト永続化**（`kind delete cluster` しても残す）にしたい場合は、NFS export の裏（現状 local-path）を
> **ホストディレクトリ**にする必要がある: kind を `extraMounts` で作り直してホスト dir をノードにマウントするか、
> ホスト上で外部 NFS サーバを常駐させる。

---

## 付録C: arm64 が無い場合（x86_64 / amd64 サーバ）のランブック

amd64（x86_64）サーバでは **emulation も arm64 ビルドも不要**で、本手順は**むしろ簡単・安定**になる。
weko 本体・Elasticsearch・Spilo・RabbitMQ の公開/公式イメージがすべて amd64 ネイティブのため、
arm64 で必要だった「qemu エミュレーション・自前 arm64 ビルド・コアダンプ対策」が**すべて不要**。
（本文の手順は arm64 前提。以下は付録B との差分。）

### なぜ amd64 が簡単か
- `tonistiigi/binfmt`（エミュレーション登録）**不要**
- weko / ES の **arm64 自前ビルド不要**（公開 amd64 イメージをそのまま使用）
- uwsgi のプロセス削減・coredump 隔離などの **emulation 回避策も不要**
- 初回リクエストが速い（arm64 エミュレーションの数分待ちが無い）。qemu segfault→コアダンプ→ディスク満杯の事故も起きない

### C-1. ツール / クラスタ / Ingress（binfmt を省略）
```bash
mkdir -p ~/.local/bin
KVER=$(curl -sL https://dl.k8s.io/release/stable.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/amd64/kubectl"
curl -sLo ~/.local/bin/kind    "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-amd64"
chmod +x ~/.local/bin/kubectl ~/.local/bin/kind; hash -r
kind create cluster --config kind-weko-cluster.yaml --wait 120s
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
# ★ docker run ... tonistiigi/binfmt の手順は不要
```

### C-2. イメージ（amd64 ネイティブ・ビルド最小）
```bash
cd k8s-weko
# weko 本体: 最新ソースを取得して amd64 native ビルド（--platform 不要）
git clone https://github.com/RCOSDP/weko.git /home/mhaya/weko 2>/dev/null || git -C /home/mhaya/weko pull --ff-only
docker build -f /home/mhaya/weko/Dockerfile -t weko3-web:amd64 /home/mhaya/weko
kind load docker-image weko3-web:amd64 --name weko3
# Elasticsearch: 公式amd64ベースの weko ES を native ビルド（本物kui.txt/kuromoji/repository-s3）
docker build -f /home/mhaya/weko/elasticsearch/Dockerfile \
  --build-arg ELASTICSEARCH_S3_ACCESS_KEY=wekominio \
  --build-arg ELASTICSEARCH_S3_SECRET_KEY=wekominio-secret-key \
  --build-arg ELASTICSEARCH_S3_ENDPOINT=http://minio:9000 \
  --build-arg ELASTICSEARCH_S3_BUCKET=weko-esbackup \
  -t weko-elasticsearch:6.8.23 /home/mhaya/weko
kind load docker-image weko-elasticsearch:6.8.23 --name weko3
```

### C-3. マニフェストの差分（amd64 向けに書き換え）
| ファイル | arm64版 | amd64版 |
|---|---|---|
| `gen-tenant.sh` | `image: weko3-web:arm64` | `image: weko3-web:amd64`（最新ソースからビルド。emulation回避策 ulimit/cores/processes=1 は削除可＝不要） |
| `13-elasticsearch.yaml` | `weko-elasticsearch:6.8.23-arm64` + `-E`引数 | `weko-elasticsearch:6.8.23`（**公式ベースは env→設定変換あり**なので `-E`引数の代わりに env `discovery.zen.*` でも可） |
| `50-rabbitmq-cluster.yaml` | rabbitmq:4.0.9（multi-arch） | **変更不要** |
| `51-postgresql-ha.yaml` | spilo-17(arm64) | **変更不要**（spilo-17 amd64で動く）。本番厳密にするなら operator の `docker_image` を `registry.opensource.zalan.do/acid/spilo-13:2.0-p6`（=本番PG13）に上書き |

```bash
sed -i 's#image: weko3-web:arm64#image: weko3-web:amd64#' gen-tenant.sh
sed -i 's#weko-elasticsearch:6.8.23-arm64#weko-elasticsearch:6.8.23#' 13-elasticsearch.yaml
```

### C-4. デプロイ〜初期化〜疎通
[本番忠実度アップグレード](#haクラスタ化operator方式と-arm64-ネイティブ化) / 付録B と同じ流れ:
operator群(cert-manager / rabbitmq / postgres-operator) → `40〜51` 適用 → `gen-tenant.sh` → `provision-tenants.sh` → 各テナント `weko-init.sh` → admin_settings シード → **`set-s3-location.sh`（ファイル保存先を S3(MinIO) Location に）** → 疎通。
（amd64 一式は `k8s-weko-amd64/deploy-amd64.sh` が 1)〜9) を一括実行。詳細は [`k8s-weko-amd64/README-amd64.md`](./k8s-weko-amd64/README-amd64.md)。）

- **アプリ層バグ(/login, /api/records)**: 公開 `mhayashi55/weko3-web:latest` では発生しない（元々 200）。ソースからビルドした場合は arm64 と同じ app 層修正が効くよう `gen-tenant.sh` の該当修正を残す（`|| true` / 設定追記のみで無害）。
- ビルドに使う Dockerfile は `/home/mhaya/weko/Dockerfile`（amd64版）。

> **まとめ**: amd64 では「emulation・arm64ビルド・coredump対策」が全部不要になり、arm64版より工程が減って安定する。
> HAクラスタ化(operator)・Sentinel・S3・永続化・マルチテナントの**構成自体は arm64版と同一**。

---

## 付録D: arm64 で「現フル構成（最終形）」を素から一気通貫で構築する

本文の HAクラスタ化・arm64ネイティブ化・NFS・S3(MinIO) Location を**段階ではなく1スクリプトで一括**構築する。
到達点は**実機で稼働中の現構成そのもの**（付録B はここまで到達しないので注意 → 下表）。

| | 付録B（ルートB） | **付録D（ルートD）** |
|---|---|---|
| PostgreSQL | 単体（`10-postgresql.yaml`） | **Patroni 3ノードHA**（operator, spilo-17 arm64）＋ **pgpool** |
| RabbitMQ | 単体（`12-rabbitmq.yaml`） | **3ノードクラスタ**（Cluster Operator） |
| Elasticsearch | 3ノード（同左） | 3ノード（arm64ネイティブ, `-E`引数） |
| weko / ES イメージ | 既存を利用 | **arm64ネイティブを自前ビルド** |
| NFS(RWX) 共有FS | 含まず | **含む**（conf/data） |
| Redis Sentinel / 永続化 / S3 Location / マルチテナント | あり | あり |

### D-0. 前提（arm64 ホスト）
- arm64 Linux ／ docker（sudoなしで実行可）／ kubectl・kind（`~/.local/bin` 等）／ 空きディスク十分。
- **weko ソース**（ES/weko の `Dockerfile.arm64` を含む）を配置。既定参照は `/home/mhaya/weko`。
- カーネル: `vm.max_map_count=262144`（ES 起動に必須）、inotify 上限を引き上げ（多Pod運用）。
- **binfmt/qemu は不要**（arm64 ネイティブのため）。

```bash
# 例: sysctl（未設定なら）
sudo sysctl -w vm.max_map_count=262144
```

### D-1. 実行（1コマンド）
```bash
cd k8s-weko
bash deploy-arm64.sh                     # 1)クラスタ →9)疎通 まで一括（ES/weko の arm64 ビルド込み、数十分）
# weko ソースが別パスなら: WEKO_SRC=/opt/weko bash deploy-arm64.sh
# 既存クラスタへ再実行し INIT 列に従わせたい時: FORCE_INIT=no bash deploy-arm64.sh
```
`deploy-arm64.sh` の流れ:
0. **weko 最新ソースの取得/更新**（未取得なら `git clone`、既存なら `git pull`。`WEKO_REPO`/`WEKO_BRANCH`/`WEKO_SRC_UPDATE` で制御）
1. kind クラスタ + ingress（**binfmt無し**）
2. イメージ: `weko3-web:arm64` / `weko3-nginx:arm64`（Shibboleth SP入り前段） / `weko-elasticsearch:6.8.23-arm64` を**最新ソースから** native ビルド → kind load。さらに `weko-pgpool:4.2.2-arm64`（公式 arm64 pgpool イメージが無いため自前ビルド）→ kind load。
   - **weko3-nginx** は `$WEKO_SRC/nginx/Dockerfile` からビルド。**arm64 固有の要点**: supervisord.conf が `shibauthorizer`/`shibresponder` のパスを `/usr/lib/x86_64-linux-gnu/shibboleth/` で決め打ちしているため、deploy-arm64.sh が RUN sed で `x86_64 → aarch64-linux-gnu` に置換してからビルドする（これを忘れると shibd が起動しない）。`.deb` 名の `focal_amd64.deb → focal_arm64.deb` 置換も行うが、現行ソースは Dockerfile が `focal_*.deb` のワイルドカードに修正済みのため実質 no-op（旧ソース互換で残置）。3イメージとも**レジストリ不要**（ローカルビルド→`kind load`、`imagePullPolicy: Never`）。既成イメージを使う時のみ `WEKO_IMAGE`/`WEKO_NGINX_IMAGE` を指定。
3. operator: cert-manager / rabbitmq / **postgres-operator を `ghcr.io/zalando`(arm64)・spilo-17 にピン留め**
4. 共有基盤: **ES3 / PG(Patroni)3 / RabbitMQ3 / Redis Sentinel / MinIO / NFS**（全PVC）＋ MinIO 共通バケット
5. PG `weko` PW を `weko` に固定（operator のリセット対策）
5.5. **pgpool** を展開（weko と PostgreSQL の間：コネクションプール＋参照負荷分散→Patroni primary/replica）
6. `gen-tenant.sh`→`provision-nfs.sh`（/fs-* にテナント別ディレクトリ作成＋nginx/Shibboleth設定投入）→apply→`provision-tenants.sh`
7. 各テナント `weko-init.sh`（既定 `FORCE_INIT=yes`＝全テナント新規初期化・並列）
8. admin_settings シード + **`set-s3-location.sh`（files_location を S3(MinIO) に）** + web 再起動
9. 疎通（`http://tenantN.localhost/`）

> 完了後の期待: 両テナント `/`200・`/login/`200・`/admin/`302・`/api/records/`200、
> PG master+replica×2 / RabbitMQ 3/3 / ES green・3ノード / Redis Sentinel 6/6 / MinIO 稼働、
> `files_location.type=s3`（`uri=s3://weko-<tenant>`）。ホストメモリ ~18GiB。

---

## 既知の注意点

- **データ永続化なし**: PostgreSQL / Elasticsearch は `emptyDir`。Pod 再起動でデータ消失 → 再初期化が必要。永続化するなら PVC（kind の `standard` StorageClass）へ変更する。
- **エミュレーションで低速**: 初回リクエストや `invenio` コマンドは時間がかかる。2回目以降のページ表示は数秒。
- **一部の本番 OKE 専用機能は不使用**: pgbouncer / WAF、および約10種のカスタムイメージは再現していない。（pgpool・Redis Sentinel・postgres-operator は現フル構成で導入済み。）
