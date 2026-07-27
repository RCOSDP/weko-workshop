# weko3 on kind — 現状記録（スナップショット）

- 記録日: 2026-07-21（**2026-07-23 に arm64 実機で一気通貫デプロイを再検証**: `deploy-arm64.sh` で素から構築し全項目パス）
- クラスタ: kind `weko3`（context `kind-weko3`）／ホスト: **arm64** 単一サーバ（20core/121GB RAM）
- 総合ステータス: **マルチテナント2件が本番同等HAクラスタ上で安定稼働**（全エンドポイント 200/302）

疎通（実測）:
```
tenant1.localhost : / 200  /login 200  /admin 302  /api/records 200
tenant2.localhost : / 200  /login 200  /admin 302  /api/records 200
ホストメモリ使用: 18GiB / 121GiB
```

---

## 1. 全体構成

```
kind クラスタ "weko3"（1物理ホスト上の3コンテナ=ノード）
├ weko3-control-plane           : APIサーバ等 + ingress-nginx(host 80/443)
├ weko3-worker  (nodeType=WEKO) : tenant1-web / tenant2-web
└ weko3-worker2 (nodeType=DATA) : ES / RabbitMQ / MinIO / PG一部 / NFS / Redis(weko3re)

アプリ: weko3-web:arm64（ネイティブ）= nginx + web(uwsgi) + worker(celery) を各テナントに
共有バックエンド(HAクラスタ):
  PostgreSQL : Zalando postgres-operator + Patroni 3ノード(spilo-17=PG17, 同期レプリケーション)
  RabbitMQ   : RabbitMQ Cluster Operator + 3ノード(rabbitmq:4.0.9)
  Elasticsearch : 3ノードクラスタ(arm64ネイティブ 6.8.23, kuromoji/kui.txt/repository-s3)
  Redis      : Sentinel HA(master+replica×2 + sentinel×3) @ namespace weko3re
  MinIO(S3)  : weko-backup / weko-content / weko-esbackup ＋ テナント別 weko-<tenant>（ファイルLocation実体）
共有FS(NFS/RWX): nfs-ganesha → テナント別 conf(/fs-config) / data(/fs-data)
```

---

## 2. Pod 一覧と配置ノード

| 種別 | Pod | ノード | 状態 |
|---|---|---|---|
| tenant1 web | `tenant1-web-*`(nginx/web/worker) | weko3-worker | 3/3 Running |
| tenant2 web | `tenant2-web-*`(nginx/web/worker) | weko3-worker | 3/3 Running |
| PostgreSQL | `weko-postgresql-0`(master) | weko3-worker | Running |
| 〃 | `weko-postgresql-1`(replica) | weko3-worker2 | Running |
| 〃 | `weko-postgresql-2`(replica) | weko3-worker | Running |
| RabbitMQ | `weko-rabbitmq-server-0/1/2` | **全て weko3-worker2** | 3/3 Running |
| Elasticsearch | `elasticsearch-0/1/2` | **全て weko3-worker2** | 3/3 Running |
| Redis(weko3re) | `redis-0/1/2` + `sentinel-*`×3 | — | 6/6 Running |
| MinIO | `minio-*` | weko3-worker2 | Running |
| operator類 | postgres-operator(default) / rabbitmq-cluster-operator / cert-manager×3 / nfs-provisioner | — | Running |

> ⚠️ **ES と RabbitMQ は3ノードとも weko3-worker2 に集中**（`nodeSelector: nodeType: DATA` が該当1ノードのみ）。
> → そのノードが落ちるとクラスタ全滅の**単一障害点**。PG は2ノードに分散。詳細は §5。

---

## 3. 使用イメージ

| 用途 | イメージ | 種別 |
|---|---|---|
| weko 本体(web/worker) | `weko3-web:arm64` | **arm64自前ビルド**（`/home/mhaya/weko/Dockerfile.arm64`） |
| 前段 nginx | `weko3-nginx:arm64` | **arm64自前ビルド**（`/home/mhaya/weko/nginx/Dockerfile`, Shibboleth SP=shibd + nginx-http-shibboleth 入り。既定は nginx 単体起動、`WEKO_NGINX_SHIB=yes` で shibd 込みの本番モード） |
| Elasticsearch | `weko-elasticsearch:6.8.23-arm64` | **arm64自前ビルド**（`/home/mhaya/weko/elasticsearch/Dockerfile.arm64`, 本物kui.txt） |
| PostgreSQL | `ghcr.io/zalando/spilo-17:4.0-p2` | arm64(operator既定) |
| RabbitMQ | `rabbitmq:4.0.9-management` | multi-arch |
| Redis/Sentinel | `redis:6.2` | multi-arch |
| MinIO | `minio/minio:RELEASE.2025-04-08...` | multi-arch |
| NFSサーバ | `registry.k8s.io/sig-storage/nfs-provisioner:v4.0.8` | arm64(ganesha) |

> emulation は不使用（weko/ES を arm64 ネイティブ化して qemu を排除）。

---

## 4. ストレージ / 永続化

| StorageClass | Provisioner | アクセス | 用途 |
|---|---|---|---|
| `standard`（既定） | rancher.io/local-path | **RWO・ノードローカル** | PG/ES/RabbitMQ/Redis/MinIO/NFS export の裏 |
| `nfs` | weko.example.com/nfs（ganesha） | **RWX・ネットワーク共有** | 動的プロビジョニング用（現構成のテナント別FSは `nfs-static` の静的PV） |
| `nfs-static` | なし（静的PV） | **RWX・ネットワーク共有** | テナント別 `/fs-config` `/fs-data` `/fs-shibboleth` `/fs-nginx`（本番と同じレイアウト） |

PVC 一覧:
```
[local-path / RWO]
 weko3: data-elasticsearch-0/1/2, pgdata-weko-postgresql-0/1/2,
        persistence-weko-rabbitmq-server-0/1/2, minio-data
 weko3re: data-redis-0/1/2
 nfs-system: nfs-export (NFSサーバの実体, 30Gi)
 ※ data-postgresql-0 は旧単体PG時代の残骸(未使用・削除可)
[NFS / RWX]
 weko3: tenant1-conf, tenant1-data, tenant1-shib, tenant2-conf, tenant2-data, tenant2-shib
```

NFS 共有FS（本番の config-pvc/data-pvc 相当）:
- `<tenant>-conf` → `.../var/instance/conf`（invenio.cfg / uwsgi.ini）
- `<tenant>-data` → `.../var/instance/data`（テーマ`_variables.scss` / indextree など）※アップロード実体は含まない
- `<tenant>-shib` → nginx コンテナの `/etc/shibboleth`（NFS 上の `/fs-shibboleth/<tenant>` を静的PVで。`provision-nfs.sh` が shibboleth_template を投入）
- `<tenant>-nginx-pvc` → nginx コンテナの `/etc/nginx`（NFS 上の `/fs-nginx/<tenant>`。`provision-nfs.sh` が nginx_template を投入）
- **アップロード先＝S3(MinIO) Location**: DB `files_location` を `type='s3'` / `uri='s3://weko-<tenant>'` に設定（`set-s3-location.sh`）。weko は `invenio-s3` の s3fs 経由で MinIO バケットへ保存。
  - 仕組み: `invenio-s3` の `_get_fs` は `location.type=='s3'` の時だけ location の S3情報(access_key/secret_key/s3_endpoint_url)で s3fs 接続。None のままだと PyFilesystem2 にフォールバックして `AWS_ACCESS_KEY_ID not set` で失敗する。
  - path-style / `signature_version=s3v4` は invenio-s3 が処理。`instance.cfg` の `S3_ACCCESS_KEY_ID` 等を環境変数から読む配線を `gen-tenant.sh` が実施。
  - 検証済: tenant1→`s3://weko-tenant1/...`, tenant2→`s3://weko-tenant2/...` に実オブジェクト確認。

---

## 5. データ永続化とノード移動時の挙動 ★重要

**local-path は特定ノードに固定**される（PVに `nodeAffinity: kubernetes.io/hostname In [<node>]`）。

| 状況 | データ |
|---|---|
| Pod削除→**同一ノード**で再作成（通常の再起動） | ✅ **保持**（PG 188テーブル保持を検証済み） |
| ノード障害等で**別ノードへ移動** | ❌ その Pod のローカルデータは移動しない（元ノードに残る）。PVの nodeAffinity で別ノードでは起動できず Pending |
| **クラスタ全体のデータ** | ✅ **HA複製で保全**（PG=Patroni同期レプリケーション／ES=シャードreplica） |

要点:
- **個々の Pod ボリューム（PG/ES）は可搬ではない**（local-path）。
- ただし **HAクラスタの複製**により、ノード/Pod喪失時も他ノードの複製でデータとサービスは生存（これがクラスタ化の狙い）。
- NFS(RWX) の conf/data は **nodeAffinity 無し＝どのノードからでも接続可**（weko web の複数レプリカ化・ノード移動が可能）。

**真に「Pod移動＋データ可搬」にするには**（local-pathでは不可）:
- ネットワーク/共有ブロックストレージ（NFS(RWX)／クラウドBlock(OCI Block/EBS, detach→attach)／Ceph/Longhorn）
- 本番OKEのPGはクラウドBlock＋複製で実現

---

## 6. アクセス情報

| 項目 | 値 |
|---|---|
| URL | `http://tenant1.localhost/` , `http://tenant2.localhost/`（`*.localhost`→ループバック。host 80直結公開） |
| 管理者(tenant1) | `admin@example.org` / `adminpass123` |
| 管理者(tenant2) | `admin@tenant2.local` / `adminpass2` |
| DB | user `weko` / pass `weko`（PG接続先 `weko-postgresql`、現構成では `pgpool`） |
| MinIO | `wekominio` / `wekominio-secret-key`（endpoint `http://minio:9000`） |
| RabbitMQ | user `weko` / pass `weko`（接続先 `weko-rabbitmq`, vhost `<tenant>/`） |

ポートフォワード（リモート）: `kubectl port-forward -n ingress-nginx --address 127.0.0.1,::1 svc/ingress-nginx-controller 8080:80` → `http://tenantN.localhost:8080/`

---

## 7. 既知の制約 / 未対応

- **ES・RabbitMQ が単一ノード(weko3-worker2)集中** → 実ノード障害耐性なし（要: ノード追加 or anti-affinity で分散）。
- **local-path は `kind delete cluster` で消える**（Pod再起動では残る）。完全ホスト永続化には kind `extraMounts`(ホストdir) 再作成 or 外部NFSが必要。
- **単一物理ホスト上の kind**（ノード=コンテナ）。真のノード障害試験は不可。
- **pgpool**（コネクションプール＋参照負荷分散。Patroni PG の前段）は導入済み（`62-pgpool.yaml`、arm64 でデータパス検証済）。未導入（本番OKE専用）: pgbouncer, F5 App Protect(WAF), Shibboleth/学認認証, fluentd, Prometheus監視, テナント別TLS証明書。
- 旧 `data-postgresql-0` PVC が未使用のまま残存（削除可）。

---

## 8. マニフェスト / スクリプト一覧（`k8s-weko/`）

| ファイル | 役割 |
|---|---|
| `00-namespace.yaml` | namespace weko3 |
| `10/11/12/13-*.yaml` | (10 旧単体PG=未使用) / (11 旧単体Redis=未使用) / RabbitMQ旧 / **ES 3ノード(arm64,-E引数)** |
| `40-minio.yaml` | MinIO(S3) |
| `41-redis-sentinel.yaml` | Redis Sentinel HA(weko3re) |
| `50-rabbitmq-cluster.yaml` | RabbitMQ Cluster Operator の RabbitmqCluster(3ノード) |
| `51-postgresql-ha.yaml` | Zalando postgresql CR(Patroni 3ノード) |
| `52-postgres-pod-config.yaml` | PG pod 用 env（`ALLOW_NOSSL=true`。pgpool が非SSL接続できるように） |
| `60-nfs-server.yaml` | nfs-ganesha サーバ + `nfs` StorageClass(RWX) |
| `62-pgpool.yaml` | pgpool（コネクションプール＋参照負荷分散）を Patroni PG の前段に配置 |
| `21-nginx-config.yaml` | 前段 nginx 設定(uwsgi_pass) |
| `tenants.txt` + `gen-tenant.sh` | テナント定義→マニフェスト生成(redissentinel/NFS conf,data/app修正/seed initContainer 込み) |
| `provision-tenants.sh` | テナント別 PG DB / RabbitMQ vhost 作成 |
| `provision-nfs.sh` | 共有FS(NFS)の `/fs-nginx` `/fs-shibboleth` `/fs-config` `/fs-data` にテナント別ディレクトリを作成＋テンプレート投入（本番 `make_volumes.sh` 相当）。**apply の前に実行**。busybox ヘルパーPod経由 |
| `weko-init.sh` / `es-reinit.sh` | DB初期化 / ESインデックス初期化 |
| `set-s3-location.sh` | テナント別 MinIO バケット `weko-<tenant>` 作成 + `files_location` を S3タイプに設定（init後に実行） |
| `deploy-arm64.sh` | **現フル構成（最終形）を素から一気通貫**構築（1)クラスタ〜9)疎通。README 付録D）。amd64版は `../k8s-weko-amd64/deploy-amd64.sh` |
| `../build-push-weko.sh` | WEKO イメージを weko ソースからビルド→Docker Hub push（native/multiarch/manifest）。差し替えは `WEKO_IMAGE` 環境変数 |

> **WEKO イメージ**: `deploy-*.sh` は **最新ソース（RCOSDP/weko）を取得してビルド**し、`WEKO_IMAGE`（既定 arm64=`weko3-web:arm64`, amd64=`weko3-web:amd64`）で web/worker/seed の3箇所へ一括適用する。`WEKO_IMAGE=<repo>:<tag>` を指定した時だけ既成イメージを pull（ビルドをスキップ）。Docker Hub への登録は `build-push-weko.sh`。
| `Dockerfile.es` | (旧)amd64 ES ビルド用 |
| 別途 | cert-manager / postgres-operator(pgop-*.yaml) / rabbitmq cluster-operator を導入済み |

関連ドキュメント: `README.md`(ランブック) / `CONSTRUCTION.md`(詳細) / `JAIRO-CLOUD-ARCHITECTURE.md`(本番比較) / `COMPARE-weko-workshop.md`。

---

## 9. 運用コマンド

```bash
kubectl get pods -A                                  # 全体状態
kubectl exec -n weko3 weko-postgresql-0 -- patronictl list   # PG HA状態
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cluster/health   # ES状態
kubectl exec -n weko3 weko-rabbitmq-server-0 -c rabbitmq -- rabbitmq-diagnostics cluster_status
kind delete cluster --name weko3                     # 全削除(データも消える)
```

---

## 10. キャパシティプランニング（テナント数 × 1テナントあたりアイテム数）

バックエンド（PG/ES/RabbitMQ/MinIO/Redis）は**全テナント共有**、weko web と各種DB/index/vhost/PVC は**テナント別**。
そこで「**T テナント × 1テナント N アイテム（総 = T×N）**」で見積もる。

### 変数
| 記号 | 意味 | 目安 |
|---|---|---|
| `T` | テナント数 | — |
| `N` | 1テナントあたりアイテム数 | — |
| `m` | 1アイテムのメタデータサイズ | weko で 10〜50KB |
| `f` | 1アイテムのファイル容量（ファイル数×平均サイズ） | 0〜数十MB |

### (A) テナント数 T に比例する「固定コスト」（1テナントあたり）
| 資源 | 1テナントあたり |
|---|---|
| weko web Pod（nginx+web+worker） | 実測 **~1.5〜2GiB**（limit 合計 3.75Gi） |
| PostgreSQL DB / RabbitMQ vhost / ES index / NFS conf+data PVC | 各1（軽量、多数OK） |
| Redis DB | **3個/テナント**（cache/session/celery） |

→ **メモリは概ね「共有バックエンド ~10〜12GiB ＋ T × ~2GiB（web）＋ ES heap」**。

### (B) 総アイテム T×N に比例する「容量」
| 層 | 概算式 |
|---|---|
| PostgreSQL（メタデータ） | `T×N×m×3`（索引/オーバーヘッド込み） |
| Elasticsearch（検索索引・ディスク） | `T×N×m×(1+複製数)` |
| ファイル（NFS/S3） | `T×N×f×(1+バックアップ)` |
| **ES heap（性能の要）** | 総doc=`T×N` のファセット working set をカバー。目安 **1g heap ≒ 数万doc** |
| **総ディスク** | 上記3層の合計 ＋ 3割の余裕（70%以下運用） |
| **総メモリ** | `共有~12GiB + T×2GiB + ES_heap` |

### (C) テナント数 T の上限要因
| 要因 | 制約 | 回避策 |
|---|---|---|
| **共有 Redis Sentinel** | `databases`（既定16 → **現在512に設定済み**）／3per tenant、予約DB(3=crawler,4=group_info)除き **~170テナント**。DB数はさらに増設可。**真の律速は Redis メモリ**（cache/session データ量、現 limit 384Mi） | `databases` を増やす／Redis メモリ(limit)を増やす／テナント別 Redis |
| **web Pod メモリ** | `T×~2GiB` | 64GBなら T=10 でも ~20GiB。ノード/RAM 追加 |
| PostgreSQL DB数 / RabbitMQ vhost / NFS PVC | 数百〜数千まで可 | 実質制約にならない |

> Redis の DB 数は `redis.conf` の `databases`（起動時設定）で決まる。デフォルト16は少ないが、本構成では **512** に設定済み（`redis-cli -n 500 set ...` 動作確認済み）。DB は空でも数バイトなので 512〜1024 でもメモリ増はごくわずか。**テナント数の実質上限は DB 数ではなく Redis のメモリ容量**（全テナントの cache/session の合計）。

### プランニング例（このホスト: 121GB RAM / 916GB disk）
**例1: T=4テナント × N=5万アイテム、m=30KB、f=2MB（総20万）**
- ディスク: メタ `20万×30KB×3≈18GB` ＋ ES `20万×30KB×2≈12GB` ＋ ファイル `20万×2MB≈400GB` → **~430GB**（916GB内OK）
- ES heap: 総20万doc → **heap 2〜4g×3** 推奨
- メモリ: 共有~12GiB ＋ web `4×2=8GiB` ＋ ES heap `4×3=12GiB` → **~32GiB**（64GB内OK）
- テナント数4 → 共有Redis(databases 512)で余裕（~170テナントまで可）

**例2: T=1テナント × N=? の上限（現状 heap 1g のまま）**
| プロファイル | N の目安 | 律速 |
|---|---|---|
| メタデータのみ | **〜数万〜10万** | ES heap 1g |
| ファイル平均 1MB | **〜30万** | ディスク |
| ファイル平均 5MB | **〜7万** | ディスク |
| ファイル平均 50MB | **〜7千** | ディスク |

### 拡張レバー
1. **ES heap 増強**（`ES_JAVA_OPTS -Xmx` 2〜4g、ノードRAMの50%以内・最大~30g）＋ 必要なら item index の主シャード増やして reindex、ESノード追加 → 総doc 数十万〜100万へ。
2. **ファイルは既に S3(MinIO) Location**（`files_location.type='s3'`）→ ファイル容量は MinIO PVC 次第で、外部S3に endpoint を向ければ実質無制限にスケール。
3. **ディスク増設** / **テナント数超過時はテナント別 Redis 化**。
4. PostgreSQL はメタデータが軽く（100万件でも数十GB）ほぼ律速にならない。

### 指針（まとめ）
1. **総アイテム = T×N** を出す。
2. **ディスク** = `T×N×(m×5 + f×1.x)` ＋ 3割余裕 → ホスト空きと比較。
3. **ES heap** を 総 T×N に合わせる（1g≒数万doc。足りなければ増強）。
4. **メモリ** = `12 + T×2 + ES_heap`(GiB) → サーバRAMと比較。
5. Redis は `databases`(現512)で **~170テナント**まで可。それ以上は `databases` 増設 or Redis メモリ増強（真の律速はメモリ）。
→ 現状（heap 1g・**ファイルはS3(MinIO) Location**）は「数テナント × 数万アイテム」規模。**heap増強＋MinIO拡大/外部S3化**で「多テナント × 数十万アイテム」の本番規模まで同構成で拡張可能。

---

## 11. バックアップ / リストア

**「ノードのストレージ箇所だけ」を対象にするのは誤り**。バックアップは **「どのデータが原本(source of truth)か」で区別**し、**DBは生のPVCファイルではなく論理バックアップ**を取る。

### 対象の区別
| コンポーネント | 種別 | バックアップ | 方法 |
|---|---|---|---|
| **PostgreSQL** | **原本**（メタデータ/レコード/ユーザ/ロール/ワークフロー） | ✅ **必須** | `pg_dumpall`（論理）→ S3。または Patroni＋WAL-G で継続アーカイブ |
| **コンテンツファイル**（S3(MinIO) バケット `weko-<tenant>`） | **原本**（アップロード実体、再生成不可） | ✅ **必須** | `mc mirror`/rclone で外部S3・オフサイトへ複製 |
| Elasticsearch（item検索索引） | **派生**（PGから再indexで復元可） | △ 任意 | 急ぐなら ES snapshot→S3 |
| ES stats/events 索引（利用統計） | 準原本（ESにしか無い） | ○ 推奨 | ES snapshot（repository-s3→MinIO） |
| RabbitMQ（キュー/メッセージ） | **一時的**（celeryタスク） | ✕ 不要 | vhost/user は provision で再作成 |
| Redis（cache/session） | **一時的** | ✕ 不要 | 失っても再ログイン/再キャッシュ |
| マニフェスト/スクリプト/`SECRET_KEY`等 | **設定（コード）** | ✅ **git管理** | 復旧時に同じ値を再現できるよう版管理 |

### 原則
1. **生のPVCファイルを直接コピーしない**（稼働中DBは不整合になる）。必ず **`pg_dump`／ESスナップショット／ファイルコピー**の**論理/整合バックアップ**。
2. **バックアップは必ずクラスタの外へ**。local-path は `kind delete cluster` で消えるため、ノード内保管は無意味 → **S3(MinIO)／外部ストレージ／オフサイト**。
3. **原本の2つ**（① PostgreSQL ダンプ ② コンテンツファイル）を外部退避すれば復旧可能。ES/RabbitMQ/Redis は原本から作り直せる。

### この構成で既にある基盤
- **MinIO** バケット: `weko-backup`（DBダンプ）/`weko-content`（ファイル）/`weko-esbackup`（ESスナップショット）
- **pg_dumpall → MinIO** のバックアップ Job 実演済み（initContainer=postgres で dump → mc upload）
- **ES に repository-s3 プラグイン内蔵**（MinIO へスナップショット可）
- 本番（weko-k8s）も同方式: `pgdump` / `essnapshooter` / `contents-backup(rclone)` → **オブジェクトストレージ**（ノードストレージは直接バックアップしない）

### 推奨運用（3点セット）
1. **PG**: 定期 `pg_dumpall`（全テナントDB）→ MinIO/外部S3（日次＋世代管理）
2. **ファイル**: S3(MinIO) バケット `weko-<tenant>` → 外部S3/オフサイトへ `mc mirror`/rclone 同期
3. **設定**: マニフェスト一式（`gen-tenant.sh`/`tenants.txt`/Secret鍵）を git 管理

> 完全なDR（クラスタ全損→再構築）手順: ①kind再構築＋バックエンド展開 → ②各テナントDBを dump からリストア → ③ファイルを S3/退避先から戻す → ④ES を `invenio index reindex` で再構築（stats索引はスナップショットから復元）。
