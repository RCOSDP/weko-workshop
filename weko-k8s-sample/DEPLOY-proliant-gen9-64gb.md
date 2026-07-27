# デプロイ構成設計 — HP ProLiant Gen9（16core / 64GB / 1TB）

対象サーバ: **HP ProLiant Gen9 / 16 core / 64GB RAM / 1TB Storage**

## 0. 最重要ポイント：このサーバは amd64（x86_64）

ProLiant Gen9 は Intel Xeon = **x86_64/amd64**。現行の開発環境（arm64）と違い:
- **エミュレーション不要**（qemu の segfault/コアダンプ事故が起きない）
- **arm64 用の自前ビルドは不要** → WEKO3/ES とも**最新ソースから amd64 native ビルド**（`deploy-amd64.sh` の 0)/2) が自動実行）
- 手順は [`README.md` 付録C（amd64ランブック）](./README.md#付録c-arm64-が無い場合x86_64--amd64-サーバのランブック) がベース

| コンポーネント | amd64で使うもの |
|---|---|
| weko 本体 | **最新ソース(RCOSDP/weko)から amd64 native ビルド** → `weko3-web:amd64`（既成イメージを使う場合のみ `WEKO_IMAGE` 指定） |
| Elasticsearch | 公式 `docker.elastic.co/.../6.8.23` ベースの weko ES（`/home/mhaya/weko/elasticsearch/Dockerfile`） |
| PostgreSQL | Zalando `spilo-13`(本番PG13, amd64) or spilo-17。operator は amd64 |
| RabbitMQ / Redis / MinIO / nginx / NFS | いずれも公式 amd64 |

## 1. 基盤の選択

**単一物理サーバ**なので「ノード障害HA」は本質的に効かない（サーバ自体が単一障害点）。3ノードクラスタは
**プロセスクラッシュ耐性＋本番トポロジ再現**の価値はあるが、1台では 3× のメモリを食う割に真のHAにはならない。
→ **右サイズ化（1〜2インスタンス＋潤沢リソース）を推奨**。本番同等トポロジで staging したい場合のみ 3ノードを維持。

- k8s: 既存の **kind**（単一ホスト・複数コンテナ=ノード）で可。より本番寄りにするなら **k3s**（単一ノード k8s、軽量）も選択肢。
- ノード構成（kind）: control-plane 1 + worker 2（WEKO/DATA ラベル）で現行同様。

## 2. メモリ配分設計（64GB）

OS・k8s・page cache 用に **~14GB を確保**し、残り ~50GB をワークロードへ。
（ES/PG は OS ページキャッシュを使うため、RAM を使い切らないのが重要）

| 区分 | コンポーネント | 割当(limit) | 備考 |
|---|---|---|---|
| システム | OS + containerd + kubelet | ~4GB | |
| 〃 | kind control-plane + ingress + coredns | ~3GB | |
| 〃 | operator類(postgres/rabbitmq/cert-manager/nfs) | ~2GB | |
| データ | **Elasticsearch 2ノード**（heap 6GB×2） | 8GB×2 = **16GB** | replica=1で2ノードに分散。件数の要 |
| 〃 | **PostgreSQL 2ノード**（Patroni primary+standby） | 3GB×2 = **6GB** | shared_buffers ~1GB |
| 〃 | **RabbitMQ 3ノード**（quorum queue） | 1.2GB×3 = **3.6GB** | 1ノードに減らせば1.5GB |
| 〃 | Redis Sentinel(master+replica×2+sentinel×3) | 合計 **~1.5GB** | |
| 〃 | MinIO(S3) | **1GB** | |
| アプリ | **weko web × T テナント**(nginx+web+worker) | **~3.5GB/テナント** | processes=2/threads=2(ネイティブ) |
| 予備 | ページキャッシュ/バッファ/OOM回避 | **~10GB以上** | ES/PG性能に重要 |

**テナント数の目安（メモリ基準）**:
`weko web に使える ≈ 64 − 14(システム+予備の一部) − 28(データ) ≈ 22GB` → **T ≈ 5〜6 テナント**（3.5GB/テナント）。
テナントを減らせば ES heap をさらに増やして 1テナントの件数を伸ばせる（トレードオフ）。

## 3. ストレージ配分設計（1TB）

| 用途 | 割当目安 | 備考 |
|---|---|---|
| OS + イメージ + k8s | ~80GB | |
| PostgreSQL データ | ~50GB | メタデータ（100万件でも数十GB） |
| Elasticsearch データ | ~100GB | 索引（件数依存） |
| Redis/RabbitMQ | ~20GB | |
| **コンテンツファイル（S3=MinIO Location）** | **~700GB** | 実体の大半。1TBの主用途。MinIO PVC |
| NFS export（テーマ conf/data のみ） | ~数十GB | `_variables.scss`/indextree 等の小容量 |

> local-path の PVC request は上限強制されないが、**運用では明示サイズ＋監視**推奨。
> ファイルは **S3(MinIO) Location**（`files_location.type='s3'`, `uri=s3://weko-<tenant>`）に集約 → 700GB を MinIO に確保。NFS はテーマ由来の小容量のみ。ディスク逼迫時は `set-s3-location.sh` の endpoint を外部S3へ。

## 4. キャパシティ（この設計での目安）

律速は **ES heap（12GB）** と **ファイル用ディスク（~700GB）**。

| プロファイル | 総アイテム(全テナント) | 内訳例 |
|---|---|---|
| メタデータ中心（ファイル小） | **~30〜50万件** | ES heap 12GB。例: 5テナント×6〜10万件 |
| ファイル平均 2MB | **~35万件**（700GB÷2MB） | ディスク律速 |
| ファイル平均 5MB | **~14万件** | 例: 5テナント×2.8万件 |
| ファイル平均 50MB | **~1.4万件** | 例: 5テナント×2,800件 |

> Redis は `databases`(512設定済み)＋メモリで **~170テナント**まで可＝**テナント数の律速にならない**。
> 実質の律速は「**web pod メモリ（テナント数）**」と「**ES heap＋ディスク（アイテム数）**」。

## 5. 推奨デプロイ手順（要点）

1. **付録C（amd64）** に沿う: binfmt/arm64ビルド無し。WEKO3 は最新ソースから amd64 native ビルド→load。ES も公式ベースを amd64 native ビルド。
2. **リソースを本設計値に調整**（arm64版からの差分）:
   - `13-elasticsearch.yaml`: **2ノード**、`ES_JAVA_OPTS=-Xms6g -Xmx6g`、limit 8Gi、replica維持
   - `51-postgresql-ha.yaml`: `numberOfInstances: 2`、resources 3Gi
   - `50-rabbitmq-cluster.yaml`: `replicas: 3`(または1)、mem 1.2Gi
   - `gen-tenant.sh`: web の `processes=2/threads=2`(ネイティブなので削減不要)、image=`weko3-web:amd64`(最新ソースからビルド)。emulation回避策(ulimit/cores/processes=1)は撤去可
   - `40-minio.yaml`: **ファイルLocation実体**なので容量大きめ（600〜700GB）。`60-nfs-server.yaml` の export はテーマ用に小容量でよい
   - デプロイ後 `set-s3-location.sh` で各テナントの `files_location` を S3(MinIO)タイプに設定（`deploy-amd64.sh §8` が自動実行）
3. **テナントは 5 程度から**開始（`tenants.txt`）。監視しつつ ES heap/ディスクで上限管理。

## 6. 単一サーバHAの注意（正直な前提）

- 1台構成では **サーバ故障＝全停止**。3ノードクラスタでも守れるのは「プロセス/Pod障害」まで。
- 本当の可用性が必要なら **サーバを複数台**にして、各バックエンドを別ホストへ分散（＝本番OKEの姿）。
- 単一64GBサーバは「**本番同等トポロジの staging／中小規模の本番**」に適する。バックアップ（MinIOへ pg_dump / ES snapshot）で災害復旧を担保。

## 7. サイジング早見（変えたい時）

- **1テナントの件数を増やしたい** → テナント数を減らし ES heap を増やす（例: 2テナント・ES heap 20GB → 各10万件超）。
- **テナント数を増やしたい** → web pod を軽く（processes=1）＋ Redis/PG は余裕。ES heap は総件数で決まるので件数を抑える。
- **ファイルが多い** → ファイルは既に S3(MinIO) Location。MinIO の裏ディスクを増設、または `set-s3-location.sh` の endpoint を外部S3へ向けて外部化。
