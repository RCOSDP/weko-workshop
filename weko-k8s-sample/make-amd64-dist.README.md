# 配布用パッケージ作成 — `make-amd64-dist.sh`

`k8s-weko-amd64`（amd64 版 WEKO3 一式）を、海外の担当者などへ手渡すための配布用
tarball（`tar.gz`）に固めるスクリプト。リポジトリ直下から実行する。

## 使い方

```bash
# 日英 README 同梱の完全版
bash make-amd64-dist.sh

# 英語 README のみ（海外の人への手渡し用）
LANG_ONLY=en bash make-amd64-dist.sh

# 日本語 README のみ
LANG_ONLY=ja bash make-amd64-dist.sh

# 出力先を指定
OUT=/path/to/pkg.tar.gz bash make-amd64-dist.sh
```

## 環境変数

| 変数 | 既定 | 説明 |
|---|---|---|
| `LANG_ONLY` | `both` | 同梱するドキュメントの言語。`both` / `en` / `ja` |
| `OUT` | `weko-k8s-amd64-dist.tar.gz` | 出力ファイルパス |

## 方式（安全設計）

- **明示的な許可リスト方式**: 配布して良いファイルだけを列挙して固める。
  `generated/`（テナント別生成物）や `.secret-seed`（アプリ秘密鍵シード）などは
  原理的に混入しない。
- **存在チェック**: 許可リストの全ファイルが実在するか検証（欠けていれば中断）。
- **秘密ファイルガード**: リストに `*secret*` / `*.key` / `*.pem` / `.secret-seed` が
  紛れ込んでいれば中断。
- 展開時にトップが `k8s-weko-amd64/` で復元されるようパス整形。
- 実行後に **SHA256・同梱内容・配布メモ** を表示。

## 同梱内容（`LANG_ONLY=en` の例）

core スクリプト・マニフェスト・設定＋英語ドキュメント（計 **28 ファイル**）:

```
k8s-weko-amd64/
  # 入口・ホスト準備
  deploy-amd64.sh  prereq-amd64.sh  check-prereq-amd64.sh
  # 削除・復旧
  teardown-amd64.sh  unwedge-amd64.sh
  # クラスタ定義
  kind-weko-cluster.yaml
  # バックエンド
  00-namespace.yaml 13-elasticsearch.yaml 21-nginx-config.yaml
  40-minio.yaml 41-redis-sentinel.yaml 50-rabbitmq-cluster.yaml
  51-postgresql-ha.yaml 52-postgres-pod-config.yaml 60-nfs-server.yaml 62-pgpool.yaml
  # HTTPS(既定で使用)
  61-tls-ca.yaml
  # テナント関連
  gen-tenant.sh provision-nfs.sh provision-tenants.sh
  weko-init.sh seed-demo.sh set-s3-location.sh
  tenants.txt
  # 英語ドキュメント
  README-amd64.en.md  UNDEPLOY-amd64.en.md  HTTPS-letsencrypt.en.md
  TARGET-deploy1-capacity8-64gb.en.md
```

`both` なら日本語ドキュメント4件（`README-amd64.md` / `UNDEPLOY-amd64.md` /
`HTTPS-letsencrypt.md` / `TARGET-deploy1-capacity8-64gb.md`）も追加され、計 **32 ファイル**になる。

> スクリプトとマニフェストのコメント・メッセージは**すべて英語**。日本語は上記の日本語ドキュメント
> にのみ存在する。
>
> `pgpool-build/` は同梱しない。amd64 には公式 `pgpool/pgpool:4.2.2` があるため pull するだけでよい
> （arm64 版は公式 arm64 イメージが無いのでソースからビルドする）。

## 受け取り側の手順

```bash
tar xzf weko-k8s-amd64-dist.tar.gz     # → k8s-weko-amd64/ が復元される
cd k8s-weko-amd64
# 以降は README-amd64.en.md（単独で完結）に従う
```

- 生成物（`generated/`・`.secret-seed`）はパッケージに含まれず、相手環境で自動生成される。
- WEKO ソース（`github.com/RCOSDP/weko`）は `deploy-amd64.sh` が自動 clone するため同梱不要。
