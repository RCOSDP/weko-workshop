# HTTPS を Let's Encrypt に切り替える（amd64 / k8s-weko）

`README-amd64.md` の[HTTPS 証明書の指定](./README-amd64.md#https-証明書の指定)から分離した手順。
**公開運用に移すとき**だけ読めばよい。検証環境（`*.localhost`）では Let's Encrypt を使えないため、
既定の自動発行（同梱ルートCA `weko-ca-issuer`）をそのまま使う。

A の仕組み（cert-manager + `WEKO_TLS_ISSUER`）をそのまま使い、**Issuer を差し替えるだけ**で移行できる。
テナント側のマニフェストも `gen-tenant.sh` も変更不要。


> **前提条件（満たせないと発行できない）**
> - **実在の FQDN が必要**。`*.localhost` では**発行できない**。Let's Encrypt は公開DNSで名前解決できる
>   ドメインにしか証明書を出さない。
> - **HTTP-01 を使う場合**: そのFQDNがこのホストのグローバルIPに向いており、インターネットから
>   **80/tcp** に到達できること（ACME の検証リクエストが来る）。
> - 到達させられない、またはワイルドカード証明書が要る場合は **DNS-01** を使う（後述）。
> - kind の `extraPortMappings` でホストの 80/443 は既に公開済み。あとはルータ/FWの開放とDNS設定。

**1) 実 FQDN に変更する。** `tenants.txt` の HOST 列を実ドメインにし、DNS の A/AAAA レコードを
このホストのグローバルIPに向ける。
```
# NAME    DBNAME   HOST                    ADMIN_EMAIL           ...
tenant1   wekodb   repo.example.ac.jp      admin@example.ac.jp   ...
```

**2) ClusterIssuer を作る。** まず **staging** で通すこと（本番はレート制限が厳しく、
失敗を繰り返すと締め出される。同一ドメイン週50枚、失敗は1時間5回まで）。
```bash
cat <<'YAML' | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-staging
spec:
  acme:
    server: https://acme-staging-v02.api.letsencrypt.org/directory
    email: admin@example.ac.jp          # 期限切れ通知の宛先。実在アドレスにする
    privateKeySecretRef:
      name: letsencrypt-staging-account # ACMEアカウント鍵の保存先(自動生成)
    solvers:
    - http01:
        ingress:
          ingressClassName: nginx
YAML
kubectl get clusterissuer letsencrypt-staging     # READY=True になるまで待つ
```

**3) staging で発行を確認する。**
```bash
WEKO_TLS_ISSUER=letsencrypt-staging bash deploy-amd64.sh
kubectl describe certificate -n weko3 tenant1-tls   # Events で発行の成否を見る
```
> staging の証明書は**ブラウザには信頼されない**（発行者が `(STAGING) Let's Encrypt`）。
> ここで確認するのは「DNSと80番の到達性が正しく、ACMEチャレンジが通るか」の一点。

**4) 本番に切り替える。** staging が成功したら、同じ内容で `server` を本番URLにした Issuer を作り、
`WEKO_TLS_ISSUER` を差し替えて再実行する。
```bash
cat <<'YAML' | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.ac.jp
    privateKeySecretRef:
      name: letsencrypt-prod-account
    solvers:
    - http01:
        ingress:
          ingressClassName: nginx
YAML

# staging で作られた証明書を消してから本番で取り直す(Secretが残っていると再発行されない)
kubectl delete certificate,secret -n weko3 -l app.kubernetes.io/managed-by=cert-manager --ignore-not-found
WEKO_TLS_ISSUER=letsencrypt-prod bash deploy-amd64.sh
```

**5) 確認。**
```bash
echo | openssl s_client -connect localhost:443 -servername repo.example.ac.jp 2>/dev/null \
  | openssl x509 -noout -issuer -enddate
# issuer=C = US, O = Let's Encrypt, CN = ...   ← 本番なら (STAGING) が付かない
```
以後 cert-manager が期限（90日）の30日前に自動更新する。ルートCAの信頼登録は不要。

### DNS-01（80番を公開できない／ワイルドカードが要る場合）
HTTP-01 の代わりに DNS の TXT レコードで所有を証明する。DNSプロバイダのAPI資格情報が要る。
```yaml
    solvers:
    - dns01:
        cloudflare:                      # 例。route53 / clouddns 等も同様
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
```
```bash
kubectl create secret generic cloudflare-api-token -n cert-manager --from-literal=api-token=<TOKEN>
```
ワイルドカード（`*.example.ac.jp`）は **DNS-01 でしか取得できない**。全テナントを1枚で賄いたい場合は
この方式にし、`WEKO_TLS_SECRET` で共有Secret名を指定する。

### 内部CAに戻す
```bash
WEKO_TLS_ISSUER=weko-ca-issuer bash deploy-amd64.sh    # = 既定
```

### つまずきやすい点

| 症状 | 原因 |
|---|---|
| `Certificate` が `READY=False` のまま | `kubectl describe certificate -n weko3 <name>` と `kubectl get challenge -A` を見る |
| チャレンジが `pending` で進まない | 外部から `http://<FQDN>/.well-known/acme-challenge/...` に到達できていない。DNS・FW・NAT を確認 |
| `too many failed authorizations` | 本番でリトライしすぎた。**staging で先に通す**こと。復帰まで待つしかない |
| `.localhost` で発行できない | 仕様。Let's Encrypt は公開ドメインのみ。A を使う |

