# k8s-weko (amd64) — WEKO3 on kind（amd64 ネイティブ）

amd64 Linux 単一ホスト上に、本番相当の **WEKO3**をベースに構築された**JAIRO Cloud**環境を **kind**
（Kubernetes-in-Docker）で構築するマニフェスト＋スクリプト一式。すべて **amd64 ネイティブ**で、外部レジストリは不要
（weko/nginx/ES はソースからローカルビルドして kind ノードへ直接ロードする。pgpool のみ公式イメージを pull）。

対象ホスト: **amd64 (x86_64) Linux ／ RAM 64GB 以上 ／ 十分な空きディスク**（検証機は 20コア / 121GB RAM）。

> `deploy-amd64.sh` 一発で現フル構成を構築: **HAクラスタ（PG Patroni×2 / RabbitMQ×3 / ES×3）＋pgpool
> ＋Redis Sentinel＋永続化（PVC）＋NFS（RWX）＋S3（MinIO）Location＋マルチテナント**。
> （`k8s-weko/` の arm64 版に対する amd64 版。主な違いは PG が2ノード構成であることと、公式 amd64 pgpool
> イメージが使えるため pgpool をビルドせず pull する点。）

## 目次
**最短手順**: [事前準備](#前提事前準備ツール導入) → [tenants.txt を編集](#デプロイ前に-tenantstxt-を編集) →
[デプロイ](#デプロイ) → ブラウザで `https://tenant1.localhost/`

| 節 | 内容 |
|---|---|
| [本構成のポイント](#本構成のポイント) / [この一式の中身](#この一式の中身readme-と一緒に配布するファイル) | 何が build/deploy されるか、同梱ファイル |
| [前提・事前準備](#前提事前準備ツール導入) | ツール判定と導入。**まず `check-prereq-amd64.sh`** |
| [デプロイ](#デプロイ) | `bash deploy-amd64.sh`。手順0〜9の内訳、[任意機能を全部入れる例](#任意機能をすべて有効にする場合)、[作成されるユーザ](#作成されるユーザ重要) |
| [イメージの差し替え](#weko--pgpool-イメージの差し替え) | 既成イメージを使う場合。環境変数一覧もここ |
| [HTTPS 証明書の指定](#https-証明書の指定) | 既定は自動発行。持ち込み証明書／Let's Encrypt |
| [Shibboleth ログイン](#shibboleth-ログイン任意) | `WEKO_SHIB=yes` でクラスタ内に IdP を立てて学認相当の経路を試す |
| [運用・後始末](#運用後始末) | 削除は **`teardown-amd64.sh`**。一部だけ巻き戻すなら [UNDEPLOY-amd64.md](./UNDEPLOY-amd64.md) |
| [調整ポイント](#調整ポイント) / [トラブルシュート](#トラブルシュート) | 規模の増減、不具合対応 |

> **困ったら**: トラブルシュートの**最初の項目**（孤児 veth による ARP 衝突）を先に読む。
> 一見無関係な不具合が同時多発する場合、原因がそれ1つのことがある。

## 本構成のポイント
| 項目 | 設定 |
|---|---|
| weko 本体 | `weko3-web:amd64`（最新ソースから amd64 native ビルド） |
| 前段プロキシ | `weko3-nginx:amd64`（uwsgi 前段 + Shibboleth SP、ソースからビルド） |
| Elasticsearch | `weko-elasticsearch:6.8.23`（ソースからビルド）, 3ノード, `-E`引数 |
| PostgreSQL | Patroni 2ノード（Zalando postgres-operator, spilo-17 = PG17, 同期レプリケーション） |
| pgpool | 公式 `pgpool/pgpool:4.2.2`（pull）を PostgreSQL の前段に（コネクションプール＋参照負荷分散） |
| RabbitMQ | 3ノードクラスタ（RabbitMQ Cluster Operator, rabbitmq:4.0.9） |
| Redis | Sentinel（master + replica×2 + sentinel×3） |
| ファイル保存先 | **MinIO** 上の S3 Location（アップロードは s3fs 経由でテナント別バケットへ） |
| 共有FS | NFS（RWX）＝テーマ conf/data と Shibboleth SP 設定のみ |
| emulation(binfmt) | 不要（amd64 ネイティブ） |

## この一式の中身（README と一緒に配布するファイル）
デプロイは以下を読む。`deploy-amd64.sh` と kind config はこのディレクトリにある。

| 種別 | ファイル |
|---|---|
| 入口 | `deploy-amd64.sh`（0〜9 を一括実行） |
| 事前チェック | `check-prereq-amd64.sh`（ツール/環境/sysctl の導入判断。root 不要・変更なし） |
| 削除 | `teardown-amd64.sh`（Pod の終了を待ってから安全にクラスタ削除。直接 `kind delete` しない） |
| 復旧 | `unwedge-amd64.sh`（NFS ハングで消せなくなったノードの復旧。要 root）<br>`UNDEPLOY-amd64.md`（手順別アンデプロイと削除失敗時の復旧） |
| ホスト準備 | `prereq-amd64.sh`（Docker / kubectl / kind / sysctl / weko ソース。要 root） |
| クラスタ | `kind-weko-cluster.yaml`（このディレクトリ。3ノード: control-plane + WEKO + DATA） |
| バックエンド(YAML) | `00-namespace.yaml` `13-elasticsearch.yaml` `21-nginx-config.yaml` `40-minio.yaml` `41-redis-sentinel.yaml` `50-rabbitmq-cluster.yaml` `51-postgresql-ha.yaml` `52-postgres-pod-config.yaml` `60-nfs-server.yaml` `62-pgpool.yaml` |
| HTTPS(任意) | `61-tls-ca.yaml`（cert-manager のルートCA。既定 `WEKO_TLS_ISSUER=weko-ca-issuer` で展開）<br>`HTTPS-letsencrypt.md`（公開ドメインで Let's Encrypt に切り替える手順） |
| Shibboleth(任意) | `70-shibboleth-idp.yaml` `71-shibboleth-map.yaml`（クラスタ内テスト IdP と学認mAP 相当の属性認証局）<br>`shib-idp-build/`（IdP イメージ。公式 tarball + Tomcat 10.1）<br>`shib-sp-template/` `provision-shib.sh` `check-shib-login.py` `list-shib-users.py`<br>`SHIBBOLETH-IDP.md`（`WEKO_SHIB=yes` で有効化する手順） |
| COAR Notify(任意) | `72-coar-notify-inbox.yaml`（LDN の inbox）<br>`coar-notify-inbox/inbox.py`（inbox 本体。Python 標準ライブラリのみ）<br>`COAR-NOTIFY.md`（`WEKO_COAR_NOTIFY=yes` で有効化する手順） |
| アクセス方法 | `ACCESS-kubectl.md`（kubectl で PostgreSQL / ES / Redis / RabbitMQ / MinIO / WEKO / IdP に入るコマンド集） |
| テナント関連 | `gen-tenant.sh` `provision-nfs.sh` `provision-tenants.sh` `weko-init.sh` `seed-demo.sh` `set-s3-location.sh` |
| 設定 | `tenants.txt`（テナント定義。管理者メール/パスワードはここで編集） |

> `10-postgresql.yaml` / `11-redis.yaml` / `12-rabbitmq.yaml` / `20-weko-config.yaml` / `30-weko-web.yaml` /
> `Dockerfile.es` は §1〜9（`README.md`）の単一テナント学習用。フルデプロイ（`deploy-amd64.sh`）では使わない。

実行時に生成される（配布不要）: `generated/`（テナント別マニフェスト）と `.secret-seed`
（アプリ秘密鍵のシード。初回実行で作成。再実行で鍵を固定したい場合は保持）。

## 前提・事前準備（ツール導入）

要件: **amd64 Linux ／ RAM 64GB 以上 ／ 十分な空きディスク**。一括は `sudo bash prereq-amd64.sh`
（Docker / kubectl / kind / カーネル設定 / weko ソース取得をまとめて実施。要 root）。手動なら以下。
Docker とカーネル設定は root(sudo) が必要。sudo が使えない場合は (a) と (c) を管理者に依頼する。

**すでに導入済みの環境では入れ直す必要はない。** まず下の判定を実行し、`→` が出た項目だけ対処する。

### 導入判断（最初にこれを実行）
各ツールの有無とバージョン、環境、カーネル設定を見て「OK／要インストール／要更新」を表示する。
root 不要・何も変更しない。
```bash
bash check-prereq-amd64.sh
```
出力例:
```
== tools ==
  TOOL                 CURRENT    REQUIRED               VERDICT
  docker               29.1.3     20.10+ and buildx      OK
  kubectl              1.36.3     1.33-1.35 (node 1.34)  △ node(1.34)と2差。動くが非推奨
  kind                 0.30.0     0.30.0+                OK
  git                  2.43.0     any                    OK

== environment ==
  arch                 x86_64    x86_64                OK
  RAM                  121Gi      64Gi+                  OK
  disk-free            309Gi      100Gi+                 OK
  docker-group         yes        sudo なしで docker     OK

== kernel (sysctl) ==
  vm.max_map_count     262144     262144+                OK
  ...
```
終了コードは 0=すべてOK / 1=要対処(`→`)あり / 2=警告(`△`)のみ。

判定の読み方:

| 判定 | 意味 | 対処 |
|---|---|---|
| `OK` | 条件を満たしている | **何もしない**（入れ直さない） |
| `→ ... でインストール` | 未導入 | 指定された節を実行 |
| `→ ... で更新` | 古すぎて動かない可能性 | 指定された節を実行して入れ替え |
| `△` | 動くが推奨外 | 急がないが、次項の指針を読んで判断 |

**バージョン条件の根拠**:
- **docker 20.10+ / buildx** — イメージビルドに BuildKit を使うため。
- **kubectl 1.33〜1.35** — kind v0.30.0 の既定ノードイメージが `kindest/node:v1.34.0` で、kubectl は
  API サーバに対し**±1 マイナーまで**が公式サポート範囲。`△`（2マイナー差）が出たら (b) で入れ替える。
- **kind 0.30.0+** — それ未満は `kindest/node:v1.34.0` を扱えない。
- **RAM 64Gi / 空き 100Gi** — ES×3・PG×2・RabbitMQ×3 とイメージビルドの実測値から。下回ると
  テナント数を減らすか ES heap を下げる必要がある（[調整ポイント](#調整ポイント)参照）。

以降の (a)〜(d) は、判定で `→` が出た項目だけ実行すればよい。

### (a) Docker（amd64）
未導入なら次でインストール。導入済みで `→ (a) で更新` が出た場合も同じ手順で入れ替わる。
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
sudo install -m0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release; echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin

# RHEL/Rocky/AlmaLinux
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # ← 反映には再ログイン(newgrp docker)
```

### (b) kubectl / kind（amd64バイナリ）
インストールも更新も**同じ手順**（バイナリを上書きするだけ）。必要な方だけ実行してよい。
`~/.local/bin` に置くので sudo は不要。
```bash
mkdir -p ~/.local/bin
# kubectl: ノード(kindest/node:v1.34.0)に合わせて 1.34 系に固定する。マイナーだけ固定し、
#   パッチは最新に追従させる。stable.txt(その時点の最新)を使うとノードとの差が開き続け、
#   kubectl の公式サポート範囲(APIサーバに対し ±1 マイナー)を外れる。
KVER=$(curl -sL https://dl.k8s.io/release/stable-1.34.txt)
curl -sLo ~/.local/bin/kubectl "https://dl.k8s.io/release/${KVER}/bin/linux/amd64/kubectl"
curl -sLo ~/.local/bin/kind    "https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-amd64"
chmod +x ~/.local/bin/kubectl ~/.local/bin/kind
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc; export PATH=$HOME/.local/bin:$PATH
kubectl version --client; kind version
```
> すでに別の場所（`/usr/local/bin` 等）に古い kubectl / kind があると、PATH 次第でそちらが優先される。
> 更新したのに判定が変わらない場合は `which -a kubectl kind` で実際に使われる実体を確認する。

### (c) カーネルパラメータ（ES と多Pod運用に必須）
判定で3項目とも `OK` なら不要。1つでも `→` が出たら実行する（再起動後も維持される）。
```bash
sudo tee /etc/sysctl.d/99-weko.conf >/dev/null <<'EOF'
vm.max_map_count=262144
fs.inotify.max_user_watches=1048576
fs.inotify.max_user_instances=8192
EOF
sudo sysctl --system
```
> `vm.max_map_count` が小さいと ES が起動しない。inotify 上限が小さいと多Pod時に「too many open files」。

### (d) weko ソース取得（weko / nginx / ES イメージのビルドに必要）
```bash
git clone https://github.com/RCOSDP/weko.git "$HOME/weko"
```
> `deploy-amd64.sh` の 0) で自動 clone/pull されるので、この手順を先に実行しなくてもよい。
> 既定の取得先は `$HOME/weko`。別の場所に置く場合だけ `WEKO_SRC` で指定する（下記デプロイコマンド参照）。
> pgpool は weko ソースからビルドせず、公式 `pgpool/pgpool:4.2.2` を pull する。

対処が済んだら `bash check-prereq-amd64.sh` を再実行し、全項目が `OK` になったことを確認する。

### デプロイ前に `tenants.txt` を編集
管理者メールを実在のものにし、各テナントの**既定パスワードを変更**する。列:
`NAME  DBNAME  HOST  ADMIN_EMAIL  ADMIN_PASS  INIT  CACHE_DB SESSION_DB CELERY_DB`。
素からの構築では `deploy-amd64.sh` が全テナントを初期化する（既定 `FORCE_INIT=yes`。`INIT` 列が `no` でも初期化）。

```bash
$EDITOR tenants.txt
```

既定は `tenant1` の1行だけが有効になっている。最低限、`ADMIN_EMAIL` と `ADMIN_PASS` を書き換える:

```
# 既定（このままデプロイしない）
tenant1   tenant1   tenant1.localhost   admin@tenant1.example   pass-t1   yes   0  1  2
# 書き換えたあと（例）
tenant1   tenant1   tenant1.localhost   admin@example.jp        <自分で決めたパスワード>   yes   0  1  2
```

- テナントを増やすときは `tenant2` 以降のコメントを外す（バックエンドは8テナント分のキャパで確保済み）。
  `NAME` `DBNAME` `HOST` と Redis の DB 番号3つは**テナント間で重複させない**。DB 番号は `3` と `4` が
  予約済みなので避ける。
- `HOST` を `*.localhost` にしておけばループバックに解決されるので、`/etc/hosts` の設定は要らない。
  独自ドメインを使う場合は名前解決とルーティングを別途用意する。
- 編集を忘れて実行してしまった場合は、[作成されるユーザ](#作成されるユーザ重要)の手順で不要なユーザを無効化し、
  パスワードは管理画面から変更する。

> `ADMIN_PASS` は管理者だけでなく、初期化時に作られる**テストユーザ4件にも同じ値が設定される**。
> 詳細は[作成されるユーザ](#作成されるユーザ重要)を参照。

## デプロイ
実行する前に **`tenants.txt` を編集する**。管理者メールとパスワードが既定値のままデプロイされ、
初期化後に変えるには DB を触ることになるため、先に直しておく（→[デプロイ前に `tenants.txt` を編集](#デプロイ前に-tenantstxt-を編集)）。

```bash
cd k8s-weko                          # このディレクトリ
$EDITOR tenants.txt                  # 管理者メール/パスワードを変更。テナントを増やすならここで行を追加
bash deploy-amd64.sh
# 1)クラスタ→9)疎通 まで一括。weko/ES/nginx/pgpool の amd64 ビルドを含む。
# 各テナント初期化は並列で数十分。weko ソースは既定 $HOME/weko に自動取得される。
# weko ソースが別パスなら: WEKO_SRC=/opt/weko bash deploy-amd64.sh
# 既存クラスタへ再実行し INIT 列に従わせたい時: FORCE_INIT=no bash deploy-amd64.sh
# HTTPS を使わない(ingress内蔵の自己署名に戻す)時: WEKO_TLS_ISSUER= bash deploy-amd64.sh
```
### 任意機能をすべて有効にする場合

既定で `no` になっている任意機能は 4 つある。全部入れるとこうなる。

```bash
WEKO_SHIB=yes \
WEKO_SHIB_MAP=aggregation \
WEKO_SHIB_LOGIN_ONLY=yes \
WEKO_COAR_NOTIFY=yes \
bash deploy-amd64.sh
```

| 環境変数 | 入るもの |
|---|---|
| `WEKO_SHIB=yes` | クラスタ内に Shibboleth IdP（`idp.localhost`）。学認相当の SAML ログイン経路 |
| `WEKO_SHIB_MAP=aggregation` | 学認mAP 相当の属性認証局（`map.localhost`）。SP が SimpleAggregation で `isMemberOf` を取りに行き、グループがロールに反映される |
| `WEKO_SHIB_LOGIN_ONLY=yes` | `/login` 自体を IdP へ直行させる（Shibboleth 専用ログイン） |
| `WEKO_COAR_NOTIFY=yes` | COAR Notify の inbox（`inbox` Service）と、テナントの `/inbox` 中継 |

有効化後に増えるエンドポイント:

| URL | 内容 |
|---|---|
| `https://<tenant>.localhost/weko/shib/sp/login` | Shibboleth ログインの入口 |
| `https://idp.localhost/idp/status` | IdP の稼働確認（200 なら設定の読み込みまで成功） |
| `https://<tenant>.localhost/inbox` | 受信した COAR Notify 通知の一覧 |

> **`WEKO_SHIB_LOGIN_ONLY=yes` は副作用が大きい。** `/login` からローカルのログインフォームが消えるため、
> **IdP を止めるとブラウザから一切ログインできなくなる**（`tenants.txt` の管理者も含む）。
> 検証中に IdP を落とすことがあるなら、ここだけ外して残り 3 つで始めるのが扱いやすい:
>
> ```bash
> WEKO_SHIB=yes WEKO_SHIB_MAP=aggregation WEKO_COAR_NOTIFY=yes bash deploy-amd64.sh
> ```
>
> この 3 つの組み合わせは実機で確認済み。詳細は [SHIBBOLETH-IDP.md](./SHIBBOLETH-IDP.md) と
> [COAR-NOTIFY.md](./COAR-NOTIFY.md)。

> **`WEKO_NGINX_SHIB` は含めない。** これは本番の `weko.conf` をそのまま使うモードで `WEKO_SHIB` と
> 排他であり、両方 `yes` にすると `WEKO_SHIB` が優先されて警告が出るだけである。
>
> **ビルド時間が延びる。** IdP と属性認証局のイメージビルドが加わるため、初回は既定構成より
> 数分〜十数分長くかかる（2 回目以降は Docker のキャッシュが効く）。

`deploy-amd64.sh` の流れ:
0. **weko ソースの取得/更新**（`git clone` / `git pull`。`WEKO_REPO`/`WEKO_BRANCH`/`WEKO_SRC_UPDATE` で制御）
1. kind クラスタ + ingress-nginx（**binfmt無し**）
2. イメージをソースからビルド → `kind load`: `weko3-web:amd64` / `weko3-nginx:amd64` / `weko-elasticsearch:6.8.23` / `pgpool/pgpool:4.2.2`（公式イメージを pull）
3. operator: cert-manager / rabbitmq / postgres-operator（`ghcr.io/zalando` amd64・spilo-17 にピン留め）。あわせて metrics-server（`kubectl top` 用）も導入する
4. 共有基盤: **ES×3 / PG(Patroni)×2 / RabbitMQ×3 / Redis Sentinel / MinIO / NFS**（全PVC）＋ MinIO 共通バケット
5. PG `weko` PW を `weko` に固定（operator のリセット対策）
5.5. **pgpool** を展開（weko と PostgreSQL の間：コネクションプール＋参照負荷分散→Patroni primary/replica）
6. `gen-tenant.sh`→`provision-nfs.sh`（/fs-* にテナント別ディレクトリ作成＋nginx/Shibboleth設定投入）→`kubectl apply`→`provision-tenants.sh`
7. 各テナント `weko-init.sh`（並列）＝ イメージ同梱の `scripts/populate-instance.sh` をそのまま実行
   （DB/ES 初期化・言語10種・ロール・権限・widget/facet/authors 等の初期データ）
7.5. `seed-demo.sh` — weko ソースの `scripts/demo/*.sql` を投入（**アイテムタイプ・インデックスツリー・
   ワークフロー・DOI・メールテンプレート**）。weko ソースの `install.sh` 後半に相当
8. `admin_settings` シード + `set-s3-location.sh`（バケット作成＋`files_location` を S3(MinIO)タイプに）+ web再起動
9. 疎通（`https://tenantN.localhost/`）

完了後、ホスト上のブラウザで `https://tenant1.localhost/` を開く（管理者ログインは `tenants.txt` で設定した値）。

### 作成されるユーザ（重要）
手順7の `populate-instance.sh` は、`tenants.txt` の管理者に加えて**動作確認用のテストユーザ4件**を作る
（weko 本体の `sphinxdoc-create-test-data` 節）。`install.sh` で構築した場合と同じ構成。

| # | メール | ロール | 出所 |
|---|---|---|---|
| 1 | `tenants.txt` の `ADMIN_EMAIL` | System Administrator | `tenants.txt` |
| 2 | `repoadmin@example.org` | Repository Administrator | テストデータ |
| 3 | `contributor@example.org` | Contributor | テストデータ |
| 4 | `user@example.org` | （ロールなし） | テストデータ |
| 5 | `comadmin@example.org` | Community Administrator | テストデータ |

> **パスワードは5件とも `tenants.txt` の `ADMIN_PASS` を共用する**（`populate-instance.sh` が
> `--password "${INVENIO_USER_PASS}"` で作るため）。`repoadmin` と `comadmin` は管理画面に入れる
> 権限を持つ。検証用途なら問題ないが、**外部に公開する場合はそのままにしないこと**。
>
> 不要なら初期化後に無効化または削除する:
> ```bash
> PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
> # 無効化(ログイン不可にする。監査ログ等は残る)
> kubectl exec -n weko3 $PGM -- psql -U postgres -d wekodb -c \
>   "UPDATE accounts_user SET active=false WHERE email IN
>    ('repoadmin@example.org','contributor@example.org','user@example.org','comadmin@example.org');"
> # 確認
> kubectl exec -n weko3 $PGM -- psql -U postgres -d wekodb -c \
>   "SELECT id,email,active FROM accounts_user ORDER BY id;"
> ```
> 削除ではなく無効化を勧める。`accounts_user` は多くのテーブルから参照されるため、
> `DELETE` は外部キー制約で失敗するか、関連レコードごと消すことになる。

> 完了後の期待: 手順9が `http:308 https:200`（HTTPS が既定で有効なため http はリダイレクト。
> `WEKO_TLS_ISSUER=` で無効化した場合は `http:200`）。HTTPS 側で `/` 200・`/login/` 200・
> `/admin/` 302・`/api/records/` 200、
> PG master+replica×1 / RabbitMQ 3/3 / ES green・3ノード / Redis Sentinel 6/6 / MinIO 稼働、
> `files_location.type=s3`（`uri=s3://weko-<tenant>`）。ホストメモリ ~18GiB。

## 特定バージョン（タグ）をビルドする
既定は `WEKO_REPO` の既定ブランチの最新をビルドする。**リリースを固定したい**場合は `WEKO_TAG` を指定する。

```bash
WEKO_TAG=v2.0.2 bash deploy-amd64.sh
```

| 指定 | ソース | ビルドされるイメージ |
|---|---|---|
| 既定（なし） | 既定ブランチの最新（毎回 `pull`） | `weko3-web:amd64` / `weko3-nginx:amd64` / `weko-elasticsearch:6.8.23` |
| `WEKO_TAG=v2.0.2` | タグ `v2.0.2`（**pull しない**） | `weko3-web:v2.0.2` / `weko3-nginx:v2.0.2` / `weko-elasticsearch:6.8.23-v2.0.2` |
| `WEKO_BRANCH=xxx` | ブランチ `xxx` の最新（`pull` する） | 既定と同じ（`:amd64`） |

**イメージ名にタグが入るのは意図的**。同じ `:amd64` を使い回すと、別のタグでビルドし直したときに
前のイメージが上書きされて消え、切り替えのたびに再ビルドが必要になる。タグごとに名前が分かれていれば
両方がホストに残り、`WEKO_IMAGE` で明示すれば再ビルドなしに切り替えられる。

利用可能なタグの確認:
```bash
git -C "$HOME/weko" fetch --tags && git -C "$HOME/weko" tag --sort=-creatordate | head
```

> `WEKO_TAG` と `WEKO_BRANCH` を同時に指定した場合は **`WEKO_TAG` を優先**する（その旨が表示される）。
> タグは checkout すると detached HEAD になるため `git pull` は実行しない（実行すると必ず失敗する）。
> 存在しないタグを指定した場合は、利用可能なタグを一覧表示して中断する。
>
> pgpool は公式イメージを pull するため `WEKO_TAG` の影響を受けない（常に `pgpool/pgpool:4.2.2`）。

## WEKO / pgpool イメージの差し替え
既定は全イメージをホストでビルドするだけで他に何も要らない。**既成イメージ**を使う場合のみ、対応する変数を
指定すると、そのイメージはビルドせず `docker pull` して `kind load` する。変数ごとに独立しているので、
一部だけ差し替えても、全部差し替えてもよい。

| 変数 | 対象 | 既定値（ビルドされる） |
|---|---|---|
| `WEKO_IMAGE` | WEKO3 本体（web/worker） | `weko3-web:amd64` |
| `WEKO_NGINX_IMAGE` | 前段 nginx（Shibboleth SP 入り） | `weko3-nginx:amd64` |
| `WEKO_ES_IMAGE` | Elasticsearch（kuromoji/kui.txt/repository-s3 入り） | `weko-elasticsearch:6.8.23` |
| `PGPOOL_IMAGE` | pgpool-II（公式イメージを pull） | `pgpool/pgpool:4.2.2` |

一部だけ差し替える例（本体だけ既成イメージ、他はビルド）:
```bash
WEKO_IMAGE=myrepo/weko3-web:v1 WEKO_SRC=$HOME/weko bash deploy-amd64.sh
```

**全パラメータを設定した例**（イメージ4種＋ソース取得＋初期化の挙動をすべて明示）:
```bash
WEKO_IMAGE=myrepo/weko3-web:v1 \
WEKO_NGINX_IMAGE=myrepo/weko3-nginx:v1 \
WEKO_ES_IMAGE=myrepo/weko-elasticsearch:6.8.23 \
PGPOOL_IMAGE=myrepo/weko-pgpool:4.2.2 \
WEKO_SRC=$HOME/weko \
WEKO_REPO=https://github.com/RCOSDP/weko.git \
WEKO_BRANCH=develop_v2.0.0 \
WEKO_SRC_UPDATE=yes \
FORCE_INIT=yes \
CLUSTER_NAME=weko3 \
KIND_CONFIG=kind-weko-cluster.yaml \
  bash deploy-amd64.sh
```

| 変数 | 意味 | 既定値 |
|---|---|---|
| `WEKO_SRC` | weko ソースの場所 | `$HOME/weko` |
| `WEKO_REPO` | ソース取得元 | `https://github.com/RCOSDP/weko.git` |
| `WEKO_BRANCH` | 取得するブランチ | リポジトリ既定 |
| `WEKO_TAG` | 取得するタグ（例 `v2.0.2`）。**指定するとビルドするイメージのタグにもなる** | 空＝ブランチを使う |
| `WEKO_SRC_UPDATE` | 既存チェックアウトを更新するか | `yes` |
| `FORCE_INIT` | 全テナントを新規初期化するか（`no` なら `tenants.txt` の `INIT` 列に従う） | `yes` |
| `CLUSTER_NAME` | kind クラスタ名 | `weko3` |
| `KIND_CONFIG` | kind クラスタ定義 | `kind-weko-cluster.yaml` |
| `WEKO_TLS_ISSUER` | HTTPS 証明書を自動発行する ClusterIssuer（[HTTPS 証明書の指定](#https-証明書の指定)） | **`weko-ca-issuer`**（空にすると無効化） |
| `WEKO_TLS_SECRET` | HTTPS 証明書の Secret 名（手動で用意する場合） | 空（Issuer 指定時は `<tenant>-tls`） |
| `WEKO_SSL_REDIRECT` | HTTP→HTTPS リダイレクトの有無 | `yes` |
| `WEKO_SHIB` | Shibboleth IdP を立てて WEKO3 の Shibboleth ログインを有効にする（[Shibboleth ログイン](#shibboleth-ログイン任意)） | `no` |
| `WEKO_IDP_IMAGE` | Shibboleth IdP の既成イメージ | `shib-idp-build/` からビルド |
| `WEKO_IDP_HOST` | IdP の Ingress ホスト | `idp.localhost` |
| `WEKO_SHIB_LOGIN_ONLY` | `/login` 自体を IdP へ飛ばす Shibboleth 専用ログインにする（副作用は SHIBBOLETH-IDP.md 参照） | `no` |
| `WEKO_COAR_NOTIFY` | COAR Notify の inbox も立てる（詳細は COAR-NOTIFY.md 参照） | `no` |
| `WEKO_SHIB_MAP` | 学認mAP 連携（isMemberOf → ロール）の再現方法。`no`/`sso`/`aggregation` | `no` |
| `WEKO_MAP_IMAGE` | 属性認証局の既成イメージ | `shib-idp-build/` からビルド |
| `WEKO_MAP_HOST` | 属性認証局の Ingress ホスト | `map.localhost` |

> **4種すべてを既成イメージにすると、weko ソースは一切ビルドに使われない**（手順0の clone/pull は走る）。
>
> `WEKO_ES_IMAGE` を差し替える場合の注意: 既定のビルドは repository-s3（ES スナップショットの MinIO 連携）の
> 認証情報を `--build-arg` で**イメージに焼き込んでいる**。既成イメージを使うなら、同等の設定
> （`ELASTICSEARCH_S3_ACCESS_KEY` / `SECRET_KEY` / `ENDPOINT=http://minio:9000` / `BUCKET=weko-esbackup`）が
> 焼き込まれている必要がある。無いと ES は動くが、スナップショットで MinIO を使えない。

## HTTPS 証明書の指定
TLS は **ingress-nginx で終端**する（ingress → Pod の nginx は HTTP:80）。したがって証明書は
ingress-nginx に渡す。kind の `extraPortMappings` でホストの 443 が control-plane に公開済みなので、
`https://<tenant>.localhost/` はそのまま到達する。

**既定は A（cert-manager による自動発行）**。`deploy-amd64.sh` をそのまま実行すれば、同梱のルートCAが
展開され、各テナントの証明書が自動発行される。追加の指定は要らない。

| | A) cert-manager で自動発行 | B) Secret を手で作る | C) Let's Encrypt |
|---|---|---|---|
| 位置づけ | **既定** | 持ち込み証明書用 | 公開運用 |
| 用途 | 検証・開発。`.localhost` を含む任意のホスト名 | 正規の証明書（社内CA発行・ワイルドカード等） | 実 FQDN の公開サイト |
| 手数 | **不要（既定）** | テナントごとに証明書生成と Secret 作成 | Issuer 定義＋DNS/公開の準備 |
| ブラウザ警告 | ルートCAを1回信頼すれば全テナントで消える | テナントごとに登録が要る（自己署名の場合） | **出ない** |
| 更新 | 期限前に自動更新 | 手動で作り直し | 自動更新 |
| インターネット接続 | 不要 | 不要 | **必須** |

HTTPS を使わず ingress-nginx 内蔵の自己署名に戻すには、**空文字を明示**して無効化する:
```bash
WEKO_TLS_ISSUER= bash deploy-amd64.sh
# → subject=O = Acme Co, CN = Kubernetes Ingress Controller Fake Certificate
```
> `WEKO_TLS_ISSUER=` と空にする点に注意。変数を省略すると既定の `weko-ca-issuer` が使われる。

### A) cert-manager で自動発行（既定）
`61-tls-ca.yaml` が **ルートCAを1枚だけ**作り、各テナントの証明書はそのCAが署名する。CAを一度信頼すれば
全テナントが信頼される。cert-manager は手順3で導入済みなので追加インストールは不要。

```
weko-selfsigned (ClusterIssuer)  --署名-->  weko-ca (Certificate, isCA)
                                              └─> Secret cert-manager/weko-ca-key-pair
                                                    └─> weko-ca-issuer (ClusterIssuer)
                                                          --発行--> <tenant>-tls (各テナント)
```

```bash
bash deploy-amd64.sh            # 既定。WEKO_TLS_ISSUER=weko-ca-issuer と同じ
```
これだけで、CAの展開・テナント証明書の発行・Ingress への紐付けまで自動で行われる。`Certificate`
リソースを書く必要はない（Ingress の annotation から cert-manager の ingress-shim が生成する）。
SAN は Ingress の `host` から自動で設定される。

生成される Ingress:
```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: "weko-ca-issuer"
spec:
  tls:
  - hosts: [ "tenant1.localhost" ]
    secretName: tenant1-tls
```

**ブラウザの警告を消す**には、ルートCAを1回だけ信頼済みに登録する:
```bash
kubectl get secret weko-ca-key-pair -n cert-manager -o jsonpath='{.data.tls\.crt}' \
  | base64 -d > weko-ca.crt
# Ubuntu/Debian
sudo cp weko-ca.crt /usr/local/share/ca-certificates/ && sudo update-ca-certificates
# Chrome/Firefox は各ブラウザの証明書設定から「認証局」として weko-ca.crt を取り込む
```
> 発行される証明書の有効期間は既定 90 日で、期限前に cert-manager が自動更新する。
> ルートCAは 10 年（`61-tls-ca.yaml` の `duration`）。
>
> 自前の ClusterIssuer（社内CA、ACME 等）を使う場合はその名前を渡す。その場合 `61-tls-ca.yaml` は
> 展開されない（Issuer は利用者が用意済みとみなす）:
> ```bash
> WEKO_TLS_ISSUER=my-company-issuer bash deploy-amd64.sh
> ```

### B) Secret を手で作る
**1) 証明書を用意する。** 検証用に自己署名を作る場合（正規の証明書があればこの手順は不要）:
```bash
openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=tenant1.localhost/O=WEKO" \
  -addext "subjectAltName=DNS:tenant1.localhost"
```
> `subjectAltName` は必須。CN だけの証明書は最近のブラウザに拒否される。
> 複数テナントを1枚で賄うなら `-addext "subjectAltName=DNS:tenant1.localhost,DNS:tenant2.localhost"`。

**2) TLS Secret を作る**（テナントと同じ `weko3` 名前空間に置く）:
```bash
kubectl create secret tls tenant1-tls -n weko3 --cert=tls.crt --key=tls.key
```

**3) Ingress に紐付ける。** `generated/` は `gen-tenant.sh` が毎回作り直すので**手編集しない**。
`WEKO_TLS_SECRET` を指定して生成する:
```bash
# テナントごとに別の証明書（%s がテナント名に置換される → tenant1-tls, tenant2-tls ...）
WEKO_TLS_SECRET='%s-tls' bash deploy-amd64.sh

# 全テナントで1枚の証明書を共有する場合は %s を使わずそのまま指定
WEKO_TLS_SECRET='weko-tls' bash deploy-amd64.sh
```
生成される Ingress:
```yaml
spec:
  ingressClassName: nginx
  tls:
  - hosts: [ "tenant1.localhost" ]
    secretName: tenant1-tls
```

### C) Let's Encrypt に切り替える
公開ドメインで正規の証明書を使う場合。A の仕組み（cert-manager + `WEKO_TLS_ISSUER`）をそのまま使い、
**Issuer を差し替えるだけ**で移行でき、テナント側のマニフェストも `gen-tenant.sh` も変更不要。

**`*.localhost` では発行できない**（Let's Encrypt は公開DNSで解決できるドメインにのみ発行する）ため、
検証環境では A のままでよい。実 FQDN・DNS・80番の公開・staging での事前確認・DNS-01 など、
手順は分量があるので別ファイルにまとめてある。

→ **[HTTPS-letsencrypt.md](./HTTPS-letsencrypt.md)**

### HTTP の扱い（重要）
`spec.tls` を設定すると、**ingress-nginx は既定で HTTP を 308 で HTTPS へリダイレクトする**。

| 設定 | `http://` | `https://` |
|---|---|---|
| **既定（A: 自動発行）** | **308 → https** | 200 |
| ＋ `WEKO_SSL_REDIRECT=no` | 200 | 200 |
| `WEKO_TLS_ISSUER=`（HTTPS 無効化） | 200 | 200（ingress 内蔵の自己署名で警告） |

HTTP でもそのまま受けたい場合:
```bash
WEKO_SSL_REDIRECT=no bash deploy-amd64.sh
```
> 手順9の疎通確認は `http:308 https:200` のように**両方を表示**する。`http` が 308 なのは
> リダイレクトが効いている正常な状態で、失敗ではない。

### 確認
```bash
echo | openssl s_client -connect localhost:443 -servername tenant1.localhost 2>/dev/null \
  | openssl x509 -noout -subject -dates
curl -sk -o /dev/null -w '%{http_code}\n' -H 'Host: tenant1.localhost' https://localhost/
```
自己署名のままブラウザの警告を消したい場合は、`tls.crt` を OS/ブラウザの信頼済みルートに登録する。

## Shibboleth ログイン（任意）
クラスタ内に **本物の Shibboleth IdP（5.2.3）** を立て、学認相当のログイン経路を外部依存なしで試せる。

```bash
WEKO_SHIB=yes bash deploy-amd64.sh
python3 check-shib-login.py            # ブラウザの代わりに一通りたどって確認
```

入口は `https://tenant1.localhost/weko/shib/sp/login`。デモユーザは
`admin`/`admin123`（System Administrator）、`libadmin`/`libadmin123`、`teacher`/`teacher123`。

IdP イメージは公式 tarball（純 Java）と Tomcat 10.1 から自前でビルドしている（arm64 版と同一内容）。
SP（nginx 同梱の shibd）と IdP の信頼関係は `provision-shib.sh` がローカルファイルだけで張る。
**HTTPS を切ると SAML が通らない**点に注意（shibd が ACS URL を http で組み立ててしまう）。

`WEKO_SHIB_LOGIN_ONLY=yes` を足すと `/login` 自体も IdP に飛ぶ「Shibboleth 専用ログイン」になるが、
ローカルログインが消えるため IdP 停止時にブラウザから入れなくなる。副作用は SHIBBOLETH-IDP.md 参照。

→ **[SHIBBOLETH-IDP.md](./SHIBBOLETH-IDP.md)**

## 運用・後始末
各コンポーネントに入るコマンドは **[ACCESS-kubectl.md](./ACCESS-kubectl.md)** にまとめてある。

```bash
kubectl get pods -n weko3                 # 状態確認
kubectl logs -n weko3 <pod> -c web        # weko ログ
docker exec -it weko3-control-plane bash  # ノードに入る（kind のノードは docker コンテナ）
```

クラスタごと全削除する。**必ずこのスクリプトを使う**:
```bash
bash teardown-amd64.sh
```

> **`kind delete cluster` を直接叩いてはいけない。** また、次のように手で順番に消すのも**不十分**:
> ```bash
> kubectl delete deploy -n weko3 --all     # ← 即座に返る。Pod はまだ終了処理中
> kind delete cluster --name weko3         # ← ここで wedge する
> ```
> `kubectl delete deploy` は **API オブジェクトを消して即座に返り、Pod の終了は非同期に進む**。
> 終了しきる前にクラスタを消すと、NFS をマウントしたままの uwsgi/celery が killed され、
> NFS の RPC 待ち（D状態）で固まる。D状態は `SIGKILL` でも解除できないため、
> ```
> ERROR: failed to delete cluster "weko3": failed to delete nodes:
>   ... cannot remove container "weko3-worker": could not kill container:
>       tried to kill container, but did not receive an exit event
> ```
> となり、ノードコンテナが消せず **veth が孤児として残る**。孤児は旧IPの ARP に応答するので、
> 次に作るクラスタとアドレスが衝突して壊れる（[トラブルシュート](#トラブルシュート)の最初の項目）。
> 復旧には root が要るので、**手間をかけないためにスクリプトを使う**。
>
> `teardown-amd64.sh` は、Deployment を消す → **Pod が実際に消えるまでポーリングして待つ** →
> NFS サーバを止める → クラスタ削除、の順で実行し、最後に残存コンテナと D状態プロセスを検査して
> wedge していれば異常終了する。NFS を掴むのは Deployment（テナントの web/nginx/worker）だけで、
> StatefulSet（PG / ES / RabbitMQ / Redis）は掴まないため、待つ対象は前者のみでよい。

- **消えるもの**: クラスタ内の全データ。PVC は2種類あるが、**どちらも実体はノードコンテナの中**にあるため、
  クラスタ削除で失われる。登録済みアイテムも管理者ユーザも消える。

  | PVC | StorageClass | 実体 |
  |---|---|---|
  | PostgreSQL / Elasticsearch / RabbitMQ / Redis / MinIO / `nfs-export` | `standard`（local-path） | ノードコンテナ内の `/var/local-path-provisioner` |
  | テナントの `<t>-conf` `-data` `-shib` `-nginx-pvc` | `nfs-static` | NFS サーバ経由。ただしその裏は上の `nfs-export`（＝結局 local-path） |

  > テナント用の PV（`<t>-config-pv` 等）は `persistentVolumeReclaimPolicy: Retain` だが、**クラスタごと消す場合は
  > 関係ない**（PV 定義も etcd ごと消え、データもノードコンテナと一緒に消える）。`Retain` が効くのは
  > クラスタを残したまま一部だけ巻き戻す[手順別アンデプロイ](./UNDEPLOY-amd64.md)のときだけ。
- **残るもの**: ホスト上のビルド済みイメージ（`weko3-web:amd64` / `weko3-nginx:amd64` /
  `weko-elasticsearch:6.8.23` / `pgpool/pgpool:4.2.2`）と `generated/` `tenants.txt` `.secret-seed`。
  次回のデプロイはビルドキャッシュが効いて速い。
- 削除後は `~/.kube/config` が空のスタブに戻る。`kubectl` が `localhost:8080 connection refused` を返すのは
  この状態では正常（クラスタが無いだけ）。
- イメージも含めて完全に消す場合:
  ```bash
  docker image rm weko3-web:amd64 weko3-nginx:amd64 weko-elasticsearch:6.8.23 pgpool/pgpool:4.2.2
  ```
- **削除に失敗する**（`could not kill container: ... did not receive an exit event`）→
  `sudo bash unwedge-amd64.sh` で復旧する。詳細は
  [UNDEPLOY-amd64.md](./UNDEPLOY-amd64.md#削除に失敗したときの復旧nfs-ハング--孤児-veth)。

### 一部だけ巻き戻す
クラスタは残したまま特定の手順だけ元に戻す場合（テナント1つだけ作り直す、operator を入れ替える等）は
→ **[UNDEPLOY-amd64.md](./UNDEPLOY-amd64.md)**（手順 8→0 の逆順アンデプロイ）

## 調整ポイント
- **1テナントの件数を増やす**: ES heap を上げ（`13-elasticsearch.yaml` の `ES_JAVA_OPTS`）、テナント数を減らす。
- **テナント数を増やす**: `tenants.txt` に追記（Redis DB は 3,4 を避けて割当）。`gen-tenant.sh`→`kubectl apply -f generated/`→`provision-tenants.sh`→`weko-init.sh`。
- **ファイル大**: MinIO PVC 拡大／ディスク増設。限界なら `set-s3-location.sh` の `S3_ENDPOINT` を外部S3に向ける。

## トラブルシュート
- **【最重要】原因不明の不調が同時多発する（`kind create` が間欠失敗 / cert-manager が
  `leader election lost` で CrashLoopBackOff / RabbitMQ が丸ごと作られない / `postgresql` CR が
  `SyncFailed` で `weko` ロールも DB も出来ない / pgpool が PostgreSQL にタイムアウト /
  テナントが 500・504 / 手順2で `no nodes found` 以降 `localhost:8080 connection refused` の洪水）** →
  これらは**すべて単一原因**のことがある。**前回のクラスタ削除に失敗して残った孤児 veth による
  ARP 衝突**で、ノード間通信が壊れている。まず次で確認する:
  ```bash
  BR=$(ip -o link show type bridge | awk -F': ' '{print $2}' | while read b; do \
         ip -4 addr show $b 2>/dev/null | grep -q '172\.19\.' && echo $b; done | head -1)
  ip -o link show master $BR | wc -l        # ← ノード数(3)より多ければ孤児がいる
  ip neigh show dev $BR                     # ← 各ノードの実MACと突き合わせる
  docker exec weko3-worker ip -br link show eth0   # ← 実MAC
  ```
  veth 本数がノード数より多ければ確定。ARP のエントリが実 MAC と食い違い、観測のたびに MAC が
  変わることもある（複数の孤児が応答を奪い合うため）。
  → **復旧と予防は [UNDEPLOY-amd64.md](./UNDEPLOY-amd64.md#削除に失敗したときの復旧nfs-ハング--孤児-veth) を参照**
  （`sudo bash unwedge-amd64.sh` で復旧し、以後の削除は `teardown-amd64.sh` を使う）。

  孤児 veth が**無い**のに `kind create cluster` が間欠的に失敗する場合は、kind の docker ネットワークが
  デュアルスタックであることによる **IPv6 アドレス重複**が引き金のことがある（失敗時のカーネルログに
  `ICMPv6: NA: ... advertised our address ...` が残る。`sudo dmesg -T | grep ICMPv6` で確認）。
  control-plane の IP が通常の `172.19.0.2` 以外なら疑わしい。少し待って再実行するか、
  kind ネットワークを IPv4 専用で作り直す（`unwedge-amd64.sh` が自動で行う）:
  ```bash
  docker network rm kind && docker network create kind --subnet 172.19.0.0/16
  ```
  なお `deploy-amd64.sh` は `set -uo pipefail` で **`-e` を付けていない**（途中の失敗を無視して進む設計）。
  手順1で明示的に異常終了させているのはこのためで、これが無いと全手順がクラスタ不在のまま走り、
  真の原因がエラーの洪水に埋もれる。
- **手順4のPG待ちから先へ進まず、いつまでも終わらない** → クラスタや postgres-operator の異常。
  PG Patroni 2ノードの待機は最大10分で打ち切り、Pod 一覧を表示して `exit 1` する。
  `kubectl get pods -n weko3 -l cluster-name=weko-postgresql` と operator のログを確認。
  （以前はこのループに上限が無く、クラスタ不在時に永久ハングしていた）
- **手順8で `ERROR: relation "admin_settings" does not exist` / `relation "files_location" does not exist`、
  手順9が 500 や 502** → **手順7のテナント初期化が終わる前に手順8が走っている**。
  ログで手順7の見出しの直後に手順8の見出しが出て、その後に `+ invenio db drop --yes-i-know` や
  `Dropping all tables!` が現れていれば確定（手順8の最中に手順7が動いている）。
  原因は `deploy-amd64.sh` 側のシェルの不具合で**修正済み**（`grep | while` のサブシェルにより
  `wait` が空振りしていた）。この状態でデプロイしてしまった場合、テナントDBは中途半端なので、
  当該テナントを[手順別アンデプロイ](./UNDEPLOY-amd64.md)の 8→7→6 で消してから再デプロイする。
- **`tenants.txt` から外したはずのテナントが作られる** → `generated/` に前回実行時の
  `<tenant>.yaml` が残っており、`kubectl apply -f generated/` がディレクトリごと適用していた。
  そのテナントはプロビジョニングも初期化もされない「孤児」になり、PV は `Retain` なので残り続ける。
  `deploy-amd64.sh` は `tenants.txt` に載っているものだけを適用し、残骸は WARNING を出すよう修正済み。
  既に作られてしまった孤児は[手順別アンデプロイ](./UNDEPLOY-amd64.md)の手順6で消す
  （`generated/<tenant>.yaml` 自体も不要なら削除する）。
- **手順9が `http:308 https:502`（または `https:502`）で終わる** → デプロイは成功しており、
  **web pod の起動待ちに過ぎない**ことがほとんど。数十秒おいて確認すると 200 になる:
  ```bash
  curl -sk -o /dev/null -w '%{http_code}\n' -H 'Host: tenant1.localhost' https://localhost/
  ```
  `kubectl rollout status` は Pod が Ready になった時点で返るが、web コンテナの uwsgi はまだ応答
  できず、前段の nginx が 502 を返す。`deploy-amd64.sh` は 5xx の間リトライするよう修正済み。
  それでも 502 が続く場合は `kubectl logs -n weko3 -l app=<tenant>-web -c web` を確認する。
- **手順4で `mc: <ERROR> \`sh\` is not a recognized command.（Did you mean ... \`share\`）`** →
  `minio/mc` イメージは `Entrypoint=["mc"]` なので、`kubectl run ... -- sh -c '...'` と書くと args 扱いになり
  `mc sh -c ...` が実行されてしまう。**`--command` を付けて entrypoint を上書きする**のが正しい:
  ```bash
  kubectl run mc-init -n weko3 --rm -i --restart=Never --image=minio/mc:RELEASE.2025-04-08T15-39-49Z \
    --command -- /bin/sh -c 'mc alias set l http://minio:9000 wekominio wekominio-secret-key && \
                             mc mb -p l/weko-backup l/weko-content l/weko-esbackup'
  ```
  これに失敗すると共通バケット `weko-backup` / `weko-content` / **`weko-esbackup`** が作られない。
  `weko-esbackup` は Elasticsearch の `repository-s3`（スナップショット先）が参照するため、影響が出る。
  デプロイ中に見かけた場合は上のコマンドを単体で実行すれば復旧する。作成済みでも `mc mb -p` は冪等。
- **ES pod が `CrashLoopBackOff` /「max virtual memory areas」** → `vm.max_map_count` 未適用。[事前準備](#前提事前準備ツール導入)の (c) を再実行。
- **`docker: permission denied`** → docker グループがシェルに未反映。再ログインか `newgrp docker`。
- **`deploy-amd64.sh` が別パスをビルド対象にする** → 既定は `$HOME/weko`。別の場所のソースを使うなら
  `WEKO_SRC` で明示する。`sudo` 付きで実行すると `$HOME` が `/root` になる点に注意（`deploy-amd64.sh`
  は sudo 不要）。
- **pgpool pod が `backend authentication failed`** → PG pod に `ALLOW_NOSSL=true`（`52-postgres-pod-config.yaml` + operator の `pod_environment_configmap`）と `password_encryption=md5`（`51-postgresql-ha.yaml`）が必要。`deploy-amd64.sh` は両方設定する。手動デプロイ時は PG pod 起動前に適用すること。
- **`kind delete cluster` 後にノードコンテナが消せない** → この節の最初の項目（孤児 veth）を参照。
  `sudo bash unwedge-amd64.sh` で復旧し、以後の削除は `teardown-amd64.sh` を使う。
