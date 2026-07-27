# 今回の構成 vs weko-workshop（公式チュートリアル）比較

[RCOSDP/weko-workshop](https://github.com/RCOSDP/weko-workshop) は WEKO3 の**公式チュートリアル（GitBook）**。
利用方法（ロール／アイテム／アイテムタイプ／ワークフロー）に加え、**2通りの構築方式**を解説している。

## weko-workshop が示す2つの構築方式

| | 方式A: Vagrant + docker-compose | 方式B: Kubernetes（weko-k8s） |
|---|---|---|
| 位置づけ | **開発環境**（1台のVM, Windows想定） | **本番/ステージング**（JAIRO Cloud 相当） |
| 元リポジトリ | `RCOSDP/weko`（`install2.sh` / `docker-compose2.yml`） | `RCOSDP/weko-k8s`（deploy/ マニフェスト） |
| クラスタ | 不要（docker-compose） | **既存クラスタ前提**（"Connecting k8s cluster" は空欄＝OKE 等を用意済みとする） |
| 構成 | 8〜9コンテナ: nginx / web / worker / elasticsearch / redis / rabbitmq / postgresql / **pgpool** / flower | ingress(F5) + ES + PG(operator) + Redis Sentinel + RabbitMQ + weko、**NFS共有FS**(/fs-config 等) |
| テナント | 単一 | **マルチテナント**（repositories_file） |
| ストレージ | ローカル | **OKE File Storage(NFS)** をマウント |

> つまり weko-workshop の K8s 章は、**クラスタ本体（ノード/APIサーバ）の構築は範囲外**（クラウドの
> マネージドK8s＝OKE に接続する前提）で、NFS 共有FSを張って weko-k8s マニフェストを展開する運用ガイド。

## 今回構築したもの

**kind で本物のK8sクラスタ（ノード＋APIサーバ）を自前構築**し、weko-k8s マニフェストを**簡素化**して
**マルチテナント**で weko3 を動かした（arm64 上で amd64 をエミュレーション）。

## 三者比較

| 項目 | weko-workshop A (compose) | weko-workshop B (K8s/OKE) | **今回 (kind)** |
|---|---|---|---|
| K8s クラスタ | なし | **前提**（自分では作らない/OKE） | **kind で自前構築（ノード＋APIサーバ）** |
| 実行基盤 | 1VM | OKE (x86) | 単一ホスト (arm64+**エミュレーション**) |
| テナント | 単一 | マルチ | **マルチ**（tenant1/tenant2） |
| web/nginx イメージ | `docker-compose build`（weko3_web/nginx） | 同左をレジストリ配布 | **同じイメージ**（mhayashi55/weko3-* = weko3_web相当） |
| PostgreSQL | postgres + **pgpool** | postgres-operator(HA)+pgpool+pgbouncer | 単体 postgres:13（現在は operator HA + pgpool を追加） |
| Elasticsearch | 単体(ES6+kuromoji) | weko_elasticsearch 6.8.23 | **自前ビルド 6.8.23+kuromoji/icu** |
| Redis | 単体 | **Sentinel(HA)** | テナント毎 単体（現在は Sentinel HA を追加） |
| RabbitMQ | 単体 | クラスタ | 単体 3.13（現在は3ノードクラスタを追加） |
| 前段/WAF | nginx(Shib+SSL) | F5 NGINX+App Protect | 標準nginx(uwsgi_pass) |
| 共有FS | ローカル | NFS(FSS) | emptyDir（現在は NFS RWX を追加） |
| 初期化 | `install2.sh`(create/populate) | 同左 | **同じ populate 相当**(weko-init.sh) |
| アクセス | port forward | Ingress/FQDN | Ingress + host(80/443) / port-forward |

## 評価（どうか）

- **アプリ層は公式と同一**: 使用イメージ（weko3_web/nginx）、初期化フロー（create/populate-instance）、
  ES6+kuromoji、uwsgi＋nginx、マルチテナントの分離キー（DB名/インデックス接頭辞/vhost/redis）は
  **weko-workshop（＝weko-k8s）と同じ**。作ったものは“非公式な独自物”ではなく、**公式手順の土台の上**にある。

- **今回が公式より踏み込んでいる点**: weko-workshop の K8s 章が**空欄にしている「クラスタ構築」を自前で実施**
  （kind で control-plane＋worker＋APIサーバ）。OKE のようなマネージド基盤なしに、
  **単一マシンで weko3 on K8s を完結**させた。さらに **arm64** という非対応環境に
  amd64 エミュレーションで対応した（公式は x86 前提）。

- **当初 簡素化していた点（＝本番との差）**: 当初は HA（postgres-operator/Redis Sentinel/pgpool）、
  F5 App Protect(WAF)、NFS 共有FS、バックアップ/監視/ログ、Shibboleth 認証を省略していた。
  （その後 HAクラスタ・Redis Sentinel・pgpool・NFS・S3 は導入済み。）当初の簡素化した**バックエンド構成
  （単体 PG/ES/Redis/RabbitMQ）は、むしろ weko-workshop の docker-compose 開発版(A)に近い**形だった（そこから pgpool/flower を省いた形）。

- **位置づけの結論**: 今回の成果は
  **「weko-workshop 方式B（K8s）の構成を、方式A（compose）並みに簡素化したバックエンドで、
  自前 kind クラスタ上に arm64 対応で載せ、マルチテナント化したハイブリッド」**。
  学習・検証・単一マシンでの weko3 on K8s 体験としては、公式2方式の“いいとこ取り”になっている。

## もし公式手順に寄せるなら（次の一手・任意）

1. **開発の手軽さ重視** → weko-workshop A（`RCOSDP/weko` + `docker-compose2.yml`）。K8s不要で最速。
2. **本番忠実度重視** → weko-workshop B に寄せ、kind 上でも
   - Redis を **Sentinel** 構成に（instance.cfg 既定の `redissentinel` に戻す）— **実施済み**
   - PostgreSQL を **pgpool** 経由に — **実施済み**（`62-pgpool.yaml`）
   - 共有FSを **PVC/NFS** 化（emptyDir 廃止＝データ永続化）— **実施済み**
   - Ingress に**テナント別 TLS 証明書**（現在は自己署名＝ブラウザ警告あり）
3. **バックアップ/監視** → weko-k8s の `contents-backup`/`monitoring`/`logging` を追加。
