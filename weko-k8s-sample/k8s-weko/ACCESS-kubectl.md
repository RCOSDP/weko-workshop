# kubectl で各コンポーネントに入る

デプロイ後に PostgreSQL / Elasticsearch / Redis / RabbitMQ / MinIO / WEKO 本体 / Shibboleth IdP へ
アクセスするためのコマンド集。**本ファイルのコマンドはすべて実機で実行して確認済み**。

## どこに何がいるか

namespace が 3 つに分かれているので `-n` の指定を間違えないこと。

| コンポーネント | namespace | 種別 | 指定に使う名前 | コンテナ |
|---|---|---|---|---|
| PostgreSQL (Patroni ×3) | `weko3` | StatefulSet | `weko-postgresql-0` 〜 `-2` | `postgres` |
| pgpool | `weko3` | Deployment | `deploy/weko-pgpool` | `pgpool` |
| Elasticsearch ×3 | `weko3` | StatefulSet | `elasticsearch-0` 〜 `-2` | `elasticsearch` |
| RabbitMQ ×3 | `weko3` | StatefulSet | `weko-rabbitmq-server-0` 〜 `-2` | `rabbitmq` |
| MinIO (S3) | `weko3` | Deployment | `deploy/minio` | `minio` |
| WEKO 本体 | `weko3` | Deployment | `deploy/tenant1-web` | **`nginx` / `web` / `worker`** |
| Shibboleth IdP | `weko3` | Deployment | `deploy/weko-shib-idp` | `idp` |
| 属性認証局 (mAP 相当) | `weko3` | Deployment | `deploy/weko-shib-map` | `idp` |
| Redis (Sentinel) | **`weko3re`** | StatefulSet + Deployment | `redis-0` 〜 `-2` / `deploy/sentinel` | `redis` / `sentinel` |
| NFS サーバ | **`nfs-system`** | Deployment | `deploy/nfs-provisioner` | — |

```bash
kubectl get pods -A | grep -E 'weko|redis|nfs'    # 全部まとめて見る
```

`deploy/<名前>` を指定すると Deployment 配下の Pod が自動で選ばれるので、
`tenant1-web-896748b8d-nc6bq` のようなランダムな suffix を毎回調べる必要はない。
StatefulSet（PG / ES / RabbitMQ / Redis）は Pod 名が固定なのでそのまま書ける。

---

## 方法 1: `kubectl exec` — Pod 内のクライアントを使う

一番よく使う方法。追加のツールは要らない。

### PostgreSQL

Patroni の 3 ノード構成なので、**まず master がどれかを引く**のがコツ
（フェイルオーバーで入れ替わるため、Pod 名を決め打ちしない）。

```bash
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master \
        -o jsonpath='{.items[0].metadata.name}')

# 対話シェル (spilo イメージは Pod 内の postgres ユーザが trust なのでパスワード不要)
kubectl exec -it -n weko3 "$PGM" -- psql -U postgres -d wekodb

# ワンライナー
kubectl exec -n weko3 "$PGM" -- psql -U postgres -d wekodb -c 'select count(*) from accounts_user;'
kubectl exec -n weko3 "$PGM" -- psql -U postgres -c '\l'
```

クラスタ全体の状態（誰が Leader か、レプリカが追随しているか）:

```bash
kubectl exec -n weko3 "$PGM" -- patronictl list
```
```
+ Cluster: weko-postgresql (7667849989161820226) +-----------+----+-----------+
| Member            | Host        | Role         | State     | TL | Lag in MB |
+-------------------+-------------+--------------+-----------+----+-----------+
| weko-postgresql-0 | 10.244.3.6  | Leader       | running   |  1 |           |
| weko-postgresql-1 | 10.244.1.26 | Sync Standby | streaming |  1 |         0 |
| weko-postgresql-2 | 10.244.3.15 | Replica      | streaming |  1 |         0 |
+-------------------+-------------+--------------+-----------+----+-----------+
```

**pgpool 経由**（WEKO が実際に使う経路。コネクションプール＋参照負荷分散の確認）を試す場合は注意点がある。
**pgpool のイメージには `psql` が入っていない**ので、PG の Pod から `-h pgpool` で繋ぐ:

```bash
kubectl exec -n weko3 weko-postgresql-0 -- \
  sh -c 'PGPASSWORD=weko psql -h pgpool -U weko -d wekodb -c "select current_user"'
```

### Elasticsearch

```bash
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cluster/health?pretty
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cat/indices?v
kubectl exec -n weko3 elasticsearch-0 -- curl -s localhost:9200/_cat/nodes?v
```

### Redis (namespace が `weko3re`)

```bash
kubectl exec -n weko3re redis-0 -- redis-cli info replication
kubectl exec -n weko3re redis-0 -- redis-cli -n 0 dbsize          # DB 0 = tenant1 の CACHE_REDIS_DB
kubectl exec -n weko3re redis-0 -- redis-cli -n 0 keys 'Shib-Session-*'   # Shibboleth のログイン中間キャッシュ
kubectl exec -n weko3re deploy/sentinel -- redis-cli -p 26379 sentinel masters
```

### RabbitMQ

```bash
kubectl exec -n weko3 weko-rabbitmq-server-0 -- rabbitmqctl list_vhosts
kubectl exec -n weko3 weko-rabbitmq-server-0 -- rabbitmqctl list_queues -p tenant1/
kubectl exec -n weko3 weko-rabbitmq-server-0 -- rabbitmqctl cluster_status
```

### MinIO (S3)

`mc` は同梱されているが alias の設定が要る。認証情報は環境変数から取れる:

```bash
kubectl exec -n weko3 deploy/minio -- sh -c \
  'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls l'
```
```
[2026-07-29 07:35:02 UTC]     0B weko-backup/
[2026-07-29 07:35:02 UTC]     0B weko-content/
[2026-07-29 07:35:02 UTC]     0B weko-esbackup/
[2026-07-29 07:52:39 UTC]     0B weko-tenant1/
```

テナントのバケットの中身を見る:
```bash
kubectl exec -n weko3 deploy/minio -- sh -c \
  'mc alias set l http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls --recursive l/weko-tenant1'
```

### WEKO 本体（**3 コンテナあるので `-c` が必須**）

```bash
kubectl exec -it -n weko3 deploy/tenant1-web -c web    -- bash   # uwsgi / invenio CLI
kubectl exec -it -n weko3 deploy/tenant1-web -c worker -- bash   # celery
kubectl exec -it -n weko3 deploy/tenant1-web -c nginx  -- bash   # nginx + shibd
```

`invenio` CLI（`-c web` か `-c worker` で。PATH を通す必要がある）:

```bash
kubectl exec -n weko3 deploy/tenant1-web -c web -- bash -lc \
  'export PATH=/home/invenio/.virtualenvs/invenio/bin:$PATH; invenio --help'
```
```
Commands:
  access                Account commands.
  admin_settings        Settings commands.
  db                    Database commands.
  index                 Manage search indices.
  ...
```

生成された設定を確認する:
```bash
kubectl exec -n weko3 deploy/tenant1-web -c web -- \
  tail -20 /home/invenio/.virtualenvs/invenio/var/instance/conf/invenio.cfg
```

nginx コンテナのプロセス状態（**shibd が動いているかはここで見る**）:
```bash
kubectl exec -n weko3 deploy/tenant1-web -c nginx -- supervisorctl -u dummy -p dummy status
```
```
fcgiwrap        RUNNING   pid 17, uptime 0:12:11
nginx           RUNNING   pid 18, uptime 0:12:11
php-fpm         RUNNING   pid 19, uptime 0:12:11
shibauthorizer  RUNNING   pid 20, uptime 0:12:11
shibd           RUNNING   pid 16, uptime 0:12:11
shibresponder   RUNNING   pid 21, uptime 0:12:11
```

### Shibboleth IdP / 属性認証局（`WEKO_SHIB=yes` のときのみ）

属性認証局 (`deploy/weko-shib-map`) は `WEKO_SHIB_MAP=aggregation` のときだけ立つ。
コマンドは IdP と同じで、Deployment 名を差し替えるだけ。

```bash
kubectl exec -n weko3 deploy/weko-shib-idp -- tail -50 /opt/shibboleth-idp/logs/idp-process.log
kubectl exec -n weko3 deploy/weko-shib-idp -- ls /opt/shibboleth-idp/conf/

# 属性が正しく解決されるかを IdP 自身の CLI で確認する (IDP_BASE_URL の指定が必要)
kubectl exec -n weko3 deploy/weko-shib-idp -- sh -c \
  'IDP_BASE_URL=http://localhost:8080/idp; export IDP_BASE_URL;
   cd /opt/shibboleth-idp && bash bin/aacli.sh -n admin -r https://tenant1.localhost/shibboleth-sp'

# 属性認証局: SP から AttributeQuery が届いたか
kubectl exec -n weko3 deploy/weko-shib-map -- \
  grep "Shibboleth-Audit.AttributeQuery" /opt/shibboleth-idp/logs/idp-process.log | tail -3

# ユーザとグループをまとめて一覧 (IdP + WEKO DB を突き合わせる)
python3 list-shib-users.py

# 設定を変えたあとの再読込 (Pod 再起動なしで反映)
kubectl exec -n weko3 deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp \
     bash bin/reload-service.sh -id shibboleth.AttributeResolverService'
```

### NFS（共有 FS の実体。namespace が `nfs-system`）

```bash
kubectl exec -n nfs-system deploy/nfs-provisioner -- ls -l /export
kubectl exec -n nfs-system deploy/nfs-provisioner -- ls -l /export/fs-shibboleth/tenant1
kubectl exec -n nfs-system deploy/nfs-provisioner -- ls -l /export/fs-nginx/tenant1/conf.d
```

---

## 方法 2: `port-forward` — 手元のツール / ブラウザから繋ぐ

GUI クライアントや管理画面を使いたいときはこちら。

```bash
kubectl -n weko3 port-forward svc/pgpool 15432:5432 &
psql -h 127.0.0.1 -p 15432 -U weko -d wekodb        # パスワードは weko
```

| サービス | コマンド | 手元での接続先 |
|---|---|---|
| pgpool | `kubectl -n weko3 port-forward svc/pgpool 15432:5432` | `psql -h 127.0.0.1 -p 15432 -U weko -d wekodb` |
| PostgreSQL 直（master） | `kubectl -n weko3 port-forward weko-postgresql-0 15433:5432` | `psql -h 127.0.0.1 -p 15433 -U weko -d wekodb` |
| Elasticsearch | `kubectl -n weko3 port-forward svc/elasticsearch 9200:9200` | `curl localhost:9200/_cat/indices?v` |
| MinIO コンソール | `kubectl -n weko3 port-forward svc/minio 9001:9001` | ブラウザ `http://localhost:9001` |
| RabbitMQ 管理画面 | `kubectl -n weko3 port-forward svc/weko-rabbitmq 15672:15672` | ブラウザ `http://localhost:15672` |
| Redis | `kubectl -n weko3re port-forward svc/redis 16379:6379` | `redis-cli -p 16379` |
| Shibboleth IdP | `kubectl -n weko3 port-forward svc/weko-shib-idp 8080:8080` | `curl localhost:8080/idp/status` |

> **PostgreSQL だけ Service ではなく Pod を指定している。** `svc/weko-postgresql` は postgres-operator が
> Endpoints を手動管理していて selector を持たないため、port-forward すると
> `error: cannot attach to *v1.Service: invalid service 'weko-postgresql': Service is defined without a selector`
> で失敗する。master の Pod 名は `-l spilo-role=master` で引く（上記参照）。
>
> `&` でバックグラウンドに回した port-forward は、用が済んだら `kill %1` で止める。
> 手元にクライアントが無ければコンテナで代用できる:
> ```bash
> docker run --rm --network host -e PGPASSWORD=weko postgres:12 \
>   psql -h 127.0.0.1 -p 15432 -U weko -d wekodb
> docker run --rm --network host redis:7.4.1 redis-cli -h 127.0.0.1 -p 16379 ping
> ```

---

## 方法 3: ノードに入る

kind のノードは docker コンテナなので、containerd の状態やノード側のファイルを見たいときは:

```bash
docker exec -it weko3-control-plane bash   # ingress-nginx
docker exec -it weko3-worker bash          # nodeType=WEKO   (weko3 本体)
docker exec -it weko3-worker2 bash         # nodeType=DATA   (PG/ES/Redis/RabbitMQ/NFS/IdP)
```

---

## 認証情報

| 対象 | ユーザ | パスワード | 定義場所 |
|---|---|---|---|
| PostgreSQL (superuser) | `postgres` | 不要（Pod 内は trust） | spilo イメージ既定 |
| PostgreSQL / pgpool（アプリ用） | `weko` | `weko` | `gen-tenant.sh` → Secret `tenant1-secret` |
| RabbitMQ | `weko` | `weko` | 同上 |
| MinIO | `wekominio` | `wekominio-secret-key` | `40-minio.yaml` |
| WEKO 管理者 | `admin@example.org` | `adminpass123` | `tenants.txt` |
| Shibboleth IdP デモユーザ（機関） | `admin` / `libadmin` / `teacher` / `commadmin` | `<ログインID>123` | `shib-idp-build/idp-conf/credentials/demo.htpasswd` |

Secret から直接取り出す:

```bash
kubectl -n weko3 get secret tenant1-secret -o jsonpath='{.data.INVENIO_POSTGRESQL_DBPASS}' | base64 -d; echo
kubectl -n weko3 get secret tenant1-secret -o go-template='{{range $k,$v := .data}}{{$k}}={{$v|base64decode}}{{"\n"}}{{end}}'
```

---

## ログと調査

```bash
# ログ (tenant1-web はコンテナごとに内容が違う)
kubectl -n weko3 logs deploy/tenant1-web -c web    --tail=100   # uwsgi (アプリのリクエストログ / トレースバック)
kubectl -n weko3 logs deploy/tenant1-web -c nginx  --tail=100   # nginx アクセスログ + shibd
kubectl -n weko3 logs deploy/tenant1-web -c worker --tail=100   # celery
kubectl -n weko3 logs -f deploy/weko-shib-idp                   # IdP (Tomcat 標準出力)
kubectl -n weko3 logs "$PGM" --tail=100                         # PostgreSQL / Patroni

# 直前に落ちたコンテナのログ
kubectl -n weko3 logs deploy/tenant1-web -c web --previous

# Pod が起動しない / Pending のとき
kubectl -n weko3 describe pod <pod>            # Events 欄を見る
kubectl -n weko3 get events --sort-by=.lastTimestamp

# Pod からファイルを取り出す (-c が必要。tar の警告は無害)
kubectl cp weko3/<pod>:/home/invenio/.virtualenvs/invenio/var/instance/conf/invenio.cfg -c web ./invenio.cfg

# 使い捨ての調査用 Pod (クラスタ内からの疎通確認)
kubectl run -n weko3 dbg --rm -i --restart=Never --image=busybox:1.36 -- sh -c \
  'nc -z -w2 pgpool 5432 && echo "pgpool:5432 reachable"; wget -qO- elasticsearch:9200 | head -3'
kubectl run -it --rm dbg -n weko3 --image=busybox:1.36 --restart=Never -- sh   # 対話シェル
```

> `kubectl get events` は既定で 1 時間程度しか保持されないので、古い事象は残っていない。

### リソース使用量（`kubectl top`）

`deploy-*.sh` の手順3で metrics-server を入れているので、そのまま使える。

```bash
kubectl top nodes
kubectl top pods -n weko3
kubectl top pods -n weko3 --containers          # tenant1-web をコンテナ別に見る
kubectl top pods -A --sort-by=memory | head -15 # メモリ食い上位
```
```
NAME                  CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
weko3-control-plane   99m          0%       1839Mi          1%
weko3-worker          53m          0%       2372Mi          1%
weko3-worker2         104m         0%       7920Mi          6%
```

> 値が出るまで**起動後 30〜60 秒**かかる。それより前は `error: Metrics API not available` になる。
> いつまでも出ない場合は `kubectl -n kube-system logs deploy/metrics-server` を見る。kind では
> kubelet のサービング証明書をクラスタ CA が署名していないため、`--kubelet-insecure-tls` が
> 付いていないと収集に失敗し続ける（`deploy-*.sh` が自動で付けている）。

---

## ハマりどころ

- **namespace が 3 つある** — Redis は `weko3re`、NFS は `nfs-system`、それ以外が `weko3`。
  `-n` を間違えると `No resources found` になるだけで、原因が分かりにくい。
- **`tenant1-web` は 3 コンテナ** — `-c` を省くと `Defaulted container "nginx" out of: nginx, web, worker`
  と出て nginx に入ってしまう。`exec` も `logs` も `cp` も `-c` を付ける。
- **PostgreSQL の master は固定ではない** — Pod 名を決め打ちせず `-l spilo-role=master` で引く。
- **pgpool の Pod に `psql` は無い** — PG Pod か web Pod から `-h pgpool` で繋ぐ。
- **RabbitMQ / pgpool は init コンテナを持つ** — `Defaulted container ... out of: rabbitmq, setup-container (init)`
  という情報メッセージが出るが、既定のコンテナが選ばれているので無視してよい。
