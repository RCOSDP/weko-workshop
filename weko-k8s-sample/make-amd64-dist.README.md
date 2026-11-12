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

core スクリプト・マニフェスト・設定（26）＋Shibboleth IdP 一式（22）＋COAR Notify 一式（2）＋英語ドキュメント（7）、
計 **57 ファイル**:

```
k8s-weko-amd64/
  # 入口・ホスト準備
  deploy-amd64.sh  prereq-amd64.sh  check-prereq-amd64.sh
  # 配布元イメージの事前 pull（デプロイ前に実行。deploy-amd64.sh の手順1も load で呼ぶ）
  pull-images-amd64.sh
  # 削除・復旧
  teardown-amd64.sh  unwedge-amd64.sh
  # クラスタ定義
  kind-weko-cluster.yaml
  # バックエンド（40-s3.yaml = S3 の SeaweedFS）
  00-namespace.yaml 13-elasticsearch.yaml 21-nginx-config.yaml
  40-s3.yaml 41-redis-sentinel.yaml 50-rabbitmq-cluster.yaml
  51-postgresql-ha.yaml 52-postgres-pod-config.yaml 60-nfs-server.yaml 62-pgpool.yaml
  # HTTPS(既定で使用)
  61-tls-ca.yaml
  # テナント関連・S3 バケット作成
  gen-tenant.sh provision-nfs.sh provision-tenants.sh
  weko-init.sh seed-demo.sh set-s3-location.sh s3-create-buckets.sh
  tenants.txt
  # Shibboleth IdP（任意機能: WEKO_SHIB=yes）
  70-shibboleth-idp.yaml 71-shibboleth-map.yaml
  provision-shib.sh check-shib-login.py list-shib-users.py
  shib-idp-build/Dockerfile
  shib-idp-build/idp-conf/conf/{access-control,attribute-filter,attribute-resolver,
                                metadata-providers,relying-party}.xml
  shib-idp-build/idp-conf/conf/c14n/subject-c14n.xml
  shib-idp-build/idp-conf/conf/authn/password-authn-config.xml
  shib-idp-build/idp-conf/conf/attributes/custom/{weko,weko-society-affiliation,is-member-of}.properties
  shib-idp-build/idp-conf/credentials/demo.htpasswd
  shib-idp-build/idp-conf/metadata/sp-metadata.xml
  shib-sp-template/{shibboleth2,attribute-map-weko,simple-aggregation,map-metadata-provider}.xml
  # COAR Notify（任意機能: WEKO_COAR_NOTIFY=yes）
  72-coar-notify-inbox.yaml coar-notify-inbox/inbox.py
  # 英語ドキュメント
  README-amd64.en.md  UNDEPLOY-amd64.en.md  HTTPS-letsencrypt.en.md
  TARGET-deploy1-capacity8-64gb.en.md  SHIBBOLETH-IDP.en.md  ACCESS-kubectl.en.md
  COAR-NOTIFY.en.md
```

`both` なら日本語ドキュメント7件（`README-amd64.md` / `UNDEPLOY-amd64.md` / `HTTPS-letsencrypt.md` /
`TARGET-deploy1-capacity8-64gb.md` / `SHIBBOLETH-IDP.md` / `ACCESS-kubectl.md` / `COAR-NOTIFY.md`）も追加され、
計 **64 ファイル**になる。正確な一覧は `make-amd64-dist.sh` の `CORE` / `SHIB` / `COAR` / `DOCS_EN` / `DOCS_JA`。

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
# （デプロイ前に bash pull-images-amd64.sh で配布元イメージを pull しておく）
```

- 生成物（`generated/`・`.secret-seed`）はパッケージに含まれず、相手環境で自動生成される。
- WEKO ソース（`github.com/RCOSDP/weko`）は `deploy-amd64.sh` が自動 clone するため同梱不要。
