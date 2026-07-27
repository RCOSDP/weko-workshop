# 手順別アンデプロイ（arm64 / k8s-weko）

`README-arm64.md` の[運用・後始末](./README-arm64.md#運用後始末)から分離した手順。
**クラスタを残したまま一部だけ巻き戻したいとき**だけ読めばよい。

> **全部消すなら、この文書は不要。** `bash teardown-arm64.sh` を実行する。
> `kind delete cluster` を直接叩くと NFS ハングでノードが消せなくなるため使わないこと
> （理由は README のトラブルシュート最初の項目）。

## 削除に失敗したときの復旧（NFS ハング → 孤児 veth）
削除まわりの障害はこれ1つに集約される。**放置すると次に作るクラスタが壊れる**ため、必ず対処する。

**症状**: `teardown-arm64.sh` や `kind delete cluster` が次で失敗する。
```
cannot remove container "weko3-worker": could not kill container:
  tried to kill container, but did not receive an exit event
```

**復旧**（要 root）:
```bash
sudo bash unwedge-arm64.sh
```
マウント切り離し → プロセス kill → コンテナ削除 → ネットワーク削除 → 孤児 veth 削除 →
IPv4専用で再作成、までを順に行う。**この順序が重要**で、D状態プロセスが残っている間は
コンテナを削除できないため、先にマウントを外す必要がある。

**1回で消えないことがある。`!! まだ D状態が残っています` と出たら、単にもう一度実行する。**
実績として、前回の事例は**2回目の実行で解消**した（再起動は不要）。RPC のタイムアウトが進むと
解けるため、数分おいて繰り返すのが有効。それでも残る場合は
`sudo systemctl restart containerd && sudo systemctl restart docker`
（ホストの再起動ではない。ただし他のコンテナも停止するので `docker ps` で影響を確認すること）。

> 孤児 veth の削除と kind ネットワークの再作成は先に済むため、D状態プロセスが残っていても
> **新しいクラスタは作れる**。残ったプロセスは CPU を消費しない。

### なぜ起きるか
1. NFS をマウントした Pod が動いたままクラスタを消すと、`celery`/`uwsgi` が NFS の RPC 待ち
   （`wchan=rpc_wait_bit_killable`）で **D状態**になり `SIGKILL` でも死ななくなる
2. その結果ノードコンテナが `docker rm -f` でも消せなくなる
3. コンテナが消えないので **veth がブリッジに残り続ける**。この孤児が旧 IP（例 `172.19.0.4`）を
   保持したまま ARP に応答し、次に作るクラスタの同 IP のノードと衝突する
4. ノード間通信が壊れ、一見無関係な不具合が同時多発する（詳細は
   [README のトラブルシュート](./README-arm64.md#トラブルシュート)の最初の項目）

### 予防
**削除は必ず `bash teardown-arm64.sh` を使う。**
`kubectl delete deploy -n weko3 --all` を実行してから `kind delete cluster` を叩くだけでは**防げない**。
`delete deploy` は即座に返り Pod の終了は非同期に進むため、終了しきる前にクラスタを消すと同じことが起きる。
**Pod が実際に消えたことを確認してから**クラスタを消す必要があり、それを行うのが `teardown-arm64.sh`。

---

## 進め方
`deploy-arm64.sh` の手順と逆に、**番号の大きい方から順に**実行する。依存関係があるため順序は守ること。
`--ignore-not-found` を付けておくと再実行しやすい。

対象は **8) から 0) まで**。除外される2つは次の理由による。

| 手順 | 巻き戻しが不要な理由 |
|---|---|
| 9) 疎通確認 | `curl` を叩くだけで何も作らない |
| 7.5) 初期データ投入 | 投入先がすべてテナントDB内。下の **7)** の `DROP DATABASE` で同時に消える |

以下の例はテナント `tenant1`（DB名 `wekodb`）を対象にしている。DB名は `tenants.txt` の2列目。

---

## 8) admin_settings シード + S3ファイルLocation
テナント別 MinIO バケットを削除する。

```bash
kubectl run mc-rm -n weko3 --rm -i --restart=Never --image=minio/mc:RELEASE.2025-04-08T15-39-49Z \
  --command -- /bin/sh -c 'mc alias set l http://minio:9000 wekominio wekominio-secret-key && mc rb --force l/weko-tenant1'
```
> `minio/mc` は `Entrypoint=["mc"]` なので **`--command` が必須**。付けないと `mc sh -c ...` が実行され
> `sh is not a recognized command` で失敗する。

## 7) テナント初期化（＋7.5 の初期データ）
テナントDBを落とす。7.5 で投入したアイテムタイプ・インデックスツリー・ワークフロー・
メールテンプレートも同時に消える。

```bash
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n weko3 $PGM -- psql -U postgres -c "DROP DATABASE wekodb;"
```
> ES 側のインデックスは DB とは別に残る。再デプロイ時に `weko-init.sh` が `index destroy` してから
> 作り直すため、手動操作は不要。

## 6) テナント展開
Deployment/Service/Ingress/PVC と、**cluster-scoped の PV**、NFS 上の実体を消す。

```bash
kubectl delete -f generated/tenant1.yaml --ignore-not-found
kubectl delete pv tenant1-config-pv tenant1-data-pv tenant1-shib-pv tenant1-nginx-pv --ignore-not-found
NFS=$(kubectl get pod -n nfs-system -l app=nfs-provisioner -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n nfs-system $NFS -- rm -rf /export/fs-nginx/tenant1 /export/fs-shibboleth/tenant1 \
                                          /export/fs-config/tenant1 /export/fs-data/tenant1
```
> テナント PV は `persistentVolumeReclaimPolicy: Retain` かつ namespace に属さないため、
> `kubectl delete ns weko3` では**消えない**。消し忘れると `Released` のまま残り、次回デプロイで
> PVC がバインドできずに web pod が `Pending` になる。
>
> 今後そのテナントを使わないなら `generated/tenant1.yaml` 自体も削除する。残しておくと
> `tenants.txt` から外しても残骸として警告が出る。

## 5.5) pgpool
```bash
kubectl delete -f 62-pgpool.yaml --ignore-not-found
```

## HTTPS のルートCA（既定構成を使った場合）
テナント証明書を消した**後**に実行する。

```bash
kubectl delete -f 61-tls-ca.yaml --ignore-not-found   # ClusterIssuer×2 と CA Certificate
```
> ClusterIssuer は cluster-scoped なので `kubectl delete ns` では消えない。CA を作り直すと
> 証明書の署名元が変わるため、信頼済みに登録した `weko-ca.crt` は入れ直しになる。

## 5) PG の weko PW 固定
巻き戻し不要（PG ごと消えるため）。

## 4) 共有基盤
適用と逆順で。PVC は namespace 削除で一緒に消える。

```bash
kubectl delete -f 50-rabbitmq-cluster.yaml -f 13-elasticsearch.yaml -f 51-postgresql-ha.yaml \
               -f 60-nfs-server.yaml -f 41-redis-sentinel.yaml -f 40-minio.yaml \
               -f 21-nginx-config.yaml -f 52-postgres-pod-config.yaml --ignore-not-found
kubectl delete ns weko3 weko3re nfs-system --ignore-not-found
kubectl delete storageclass nfs nfs-static --ignore-not-found   # cluster-scoped なので個別に
```
> NFS をマウントした Pod が残っていると削除が固まる。先に手順6を済ませること。

## 3) Operator群
`postgresql` CR（手順4）を消した**後**に。CRD を先に消すと CR が孤児になる。

```bash
for f in postgresteam.crd operatorconfiguration.crd postgresql.crd api-service postgres-operator \
         operator-service-account-rbac configmap; do
  kubectl delete -f https://raw.githubusercontent.com/zalando/postgres-operator/v1.14.0/manifests/$f.yaml --ignore-not-found
done
kubectl delete -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml --ignore-not-found
kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml --ignore-not-found
```

## 2) イメージ
ノード内に load 済みのものはクラスタ削除で消える。ホスト側を消す場合:

```bash
docker image rm weko3-web:arm64 weko3-nginx:arm64 weko-elasticsearch:6.8.23-arm64 weko-pgpool:4.2.2-arm64
```

## 1) kind クラスタ + ingress
ingress だけ消す場合と、クラスタごと消す場合。

```bash
kubectl delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/kind/deploy.yaml
bash teardown-arm64.sh      # クラスタごと消す場合。kind delete cluster は直接使わない
```

## 0) weko ソース
ホスト上のチェックアウト。他で使わないなら削除する。

```bash
rm -rf "$HOME/weko"    # = $WEKO_SRC（既定値）
```
