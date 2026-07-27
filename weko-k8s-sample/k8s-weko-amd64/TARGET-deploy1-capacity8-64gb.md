# 確定構成 — 初期1テナント・約8テナント収容可（HP ProLiant Gen9 / 64GB / 1TB）

- 対象: **HP ProLiant Gen9 / 16core / 64GB / 1TB（amd64）**
- 方針: **初期デプロイは 1テナント**。バックエンドは **約8テナント分のキャパ**で確保（増設時に再設計不要）。
- 想定: 1テナントあたり ~1万レコード（8テナントで総 ~8万件）／各テナント低〜中トラフィック。
- 実体: この `k8s-weko-amd64/` 一式。`tenants.txt` は tenant1 のみ有効（tenant2〜8 はコメントで用意済み）。

## 1. リソース配分（バックエンドは8テナント固定キャパ）

| コンポーネント | 台数 | メモリ(request→limit) | 8テナントでの十分性 |
|---|---|---|---|
| **Elasticsearch** | 2ノード | 2560Mi → **3Gi**（heap **2g**） | 総8万件は heap 2g で余裕。replica=1で冗長 |
| **PostgreSQL**(Patroni) | 2ノード | 1Gi → **2560Mi** | 8DB・メタ数GB。primary+standby |
| **RabbitMQ**(cluster) | 3ノード | → **1Gi** | 8テナント分の vhost/quorum |
| **Redis**(Sentinel) | redis3+sentinel3 | ~1.6Gi | databases=512（170テナント可） |
| **MinIO**(S3) / **NFS** | 各1 | 1Gi / 0.5Gi | **コンテンツファイル格納(S3 Location)**／テーマconf/data共有FS(RWX) |
| **weko web**（テナント毎） | 初期1（最大8） | web 0.7→**1.5Gi**(processes=1)＋worker→**1Gi**＋nginx→0.25Gi | テナント追加で線形に増える部分 |

> バックエンドは**テナント数に依らずほぼ一定**（ES/PG/MQ/Redis は共有）。増えるのは **web pod（テナント毎 ~2.75Gi）** のみ。

## 2. メモリ収支（今 と 将来）

| | 固定バックエンド | web | システム | limits合計 | 実使用目安 |
|---|---|---|---|---|---|
| **初期（1テナント）** | ~19GiB | 1×2.75=2.75 | ~9 | **~31GiB** | ~22GiB |
| **将来（8テナント）** | ~19GiB | 8×2.75=22 | ~9 | **~50GiB** | ~35GiB |

→ **8テナントでも 64GB に収まる（ヘッドルーム ~14GiB）**。初期は余裕たっぷり。

## 3. ストレージ（1TB, 8テナント想定）

| 用途 | 目安 | PVC |
|---|---|---|
| OS + イメージ + k8s | ~80GB | — |
| PostgreSQL（メタ, 総8万件） | ~20GB | 50Gi |
| Elasticsearch（索引, 2ノード） | ~40GB | 60Gi×2 |
| **コンテンツファイル**（S3 `weko-<tenant>` on MinIO＋バックアップ） | **~600GB** | MinIO 600Gi |
| NFS export（テーマ conf/data のみ, 小） | ~数GB | 30Gi |

> **ファイル保存先は S3(MinIO) Location**（`files_location.type='s3'`, `uri=s3://weko-<tenant>`）。NFS共有はテーマ由来の `conf/`(instance.cfg等) と `data/`(`_variables.scss`/indextree 等) のみで小容量。
> ファイル容量の目安（総8万件）: 平均1MB→80GB / 5MB→400GB(◎) / 10MB→800GB(要MinIO拡大 or 増設)。MinIO PVC(600Gi)超なら外部S3へ切替 or ディスク増設。

## 4. デプロイ（初期＝1テナント）
```bash
# 前提(README-amd64.md §0): docker/kubectl/kind/sysctl/weko ソース
sudo bash prereq-amd64.sh && newgrp docker
bash deploy-amd64.sh          # tenants.txt が1テナントなので tenant1 のみ構築
# → http://tenant1.localhost/  (管理者は tenants.txt 参照)
```
バックエンドは8テナント分のキャパで立つが、web は tenant1 のみ（初期メモリ ~22GiB）。

## 5. テナント増設（→ 最大8）
1. `tenants.txt` の tenant2〜（必要な数）のコメントを外す。
2. 生成・展開・プロビジョニング・初期化:
```bash
bash gen-tenant.sh
kubectl apply -f generated/
bash provision-tenants.sh                 # 追加テナントの PG DB / RabbitMQ vhost を作成
# 追加テナントのみ初期化(weko-init.sh)。base64経由で web コンテナ内実行:
for t in tenant2 tenant3 ... ; do
  POD=$(kubectl get pod -n weko3 -l app=${t}-web -o jsonpath='{.items[0].metadata.name}')
  kubectl exec -n weko3 $POD -c web -- bash -lc "echo $(base64 -w0 weko-init.sh)|base64 -d|bash"
  # 続けて admin_settings シード(deploy-amd64.sh §8 と同じ)
done
bash set-s3-location.sh    # 追加テナントのバケット作成 + files_location を S3タイプに設定
```
- バックエンド(ES/PG/MQ/Redis/MinIO/NFS)は**再設計・再デプロイ不要**（8テナント分のキャパで稼働中）。
- 増える負荷は web pod のみ（8で +~19GiB, 収支は §2 の通り 64GB 内）。

## 6. チューニングレバー
| 目的 | 操作 |
|---|---|
| 各テナントの同時アクセスが多い | web を `processes=2`・limit 2Gi に → 収容は 6〜7テナントに |
| 1テナント10万件級 | `13-elasticsearch.yaml` の heap を 4〜6g、PVC拡大 |
| 8を超えて増やす | web軽量化＋RabbitMQ/PG/ESを各1ノードに縮小（HAは低下） |
| ファイル大/多 | MinIO PVC(600Gi)拡大＋ディスク増設。限界なら外部S3(AWS/MinIO別ホスト)へ `set-s3-location.sh` の endpoint を向ける |

## 7. 前提の注意
- 単一サーバ → **サーバ故障＝全停止**（3ノードクラスタでもプロセス障害までしか守れない）。
- バックアップは **PGダンプ＋コンテンツ(MinIOバケット `weko-<tenant>`)** を外部へ複製（`../CURRENT-STATE.md` §11）。ファイルは既にS3(MinIO)上なので `mc mirror` で外部S3へ退避可能。
