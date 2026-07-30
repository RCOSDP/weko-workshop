# COAR Notify を動かす（amd64 / k8s-weko-amd64）

WEKO3 の COAR Notify 連携（`weko-notifications`）を、外部依存なしで kind クラスタの中だけで
動かすための手順。

```bash
WEKO_COAR_NOTIFY=yes bash deploy-amd64.sh
```

受信した通知はブラウザで `https://<tenant>.localhost/inbox` から見られる。
ログにそのまま流したいときは:

```bash
kubectl -n weko3 logs -f deploy/coar-notify-inbox
```

英語版: [COAR-NOTIFY.en.md](COAR-NOTIFY.en.md)

---

## なぜ inbox を自前で立てるのか

**WEKO3 は COAR Notify の「送信」と「閲覧」しか実装していない。** inbox 本体は外部サービスである。

`weko-notifications/config.py` の既定値がそれを示している:

```python
WEKO_NOTIFICATIONS_INBOX_ADDRESS = "http://inbox:8080"
WEKO_NOTIFICATIONS_INBOX_ENDPOINT = "/inbox"
```

つまり WEKO は `http://inbox:8080/inbox` へ通知を POST し、一覧を取るときも同じ URL を GET する。
**`inbox` という名前の Service を `weko3` 名前空間に置けば、WEKO 側は無設定のまま届く。**

`72-coar-notify-inbox.yaml` はそれだけのものである。中身は `coar-notify-inbox/inbox.py`
（Python 標準ライブラリのみ、約190行）で、通知はメモリにしか持たない（Pod を再起動すると消える）。
本番の inbox は永続化・認証・署名検証を備えた別実装になる。

---

## 全体の流れ

```
   ワークフロー操作              WEKO3 (uwsgi)                inbox                ブラウザ
        |                            |                         |                     |
        |  承認ボタン                 |                         |                     |
        |--------------------------->|                         |                     |
        |                            |  POST /inbox            |                     |
        |                            |  (application/ld+json)  |                     |
        |                            |------------------------>|                     |
        |                            |                     201 Created               |
        |                            |                         |                     |
        |                            |  GET /api/notifications （閲覧側）             |
        |                            |  -> GET /inbox?target=<user uri>              |
        |                            |------------------------>|                     |
        |                            |   ldp:contains の IRI 一覧                     |
        |                            |                         |                     |
        |                            |     GET https://<tenant>/inbox/<id>            |
        |                            |     （nginx が inbox へ中継）                  |
        |                            |<--------------------------------------------->|
```

---

## 構成要素

| ファイル | 役割 |
|---|---|
| `72-coar-notify-inbox.yaml` | inbox の Deployment と Service（**Service 名は `inbox` である必要がある**） |
| `coar-notify-inbox/inbox.py` | inbox の実体。ConfigMap `coar-notify-inbox-src` として渡される |
| `21-nginx-config.yaml` | テナントの `/inbox` を inbox Service に中継する `location` |
| `gen-tenant.sh` | `WEKO_COAR_NOTIFY=yes` のとき invenio.cfg に送信先を明示 |

`inbox.py` を manifest に埋め込まず ConfigMap にしているのは、同じコードを 2 か所に持たないため。
deploy スクリプトが `kubectl create configmap --from-file` で作る。

### inbox が実装している範囲

`py-ldnlib 0.1.3`（`ldnlib/sender.py`、`consumer.py`）が実際に使う分だけを実装している。

| リクエスト | 要件 |
|---|---|
| `POST <inbox>` | `Content-Type: application/ld+json`。**2xx を返すこと**（`Sender` が `raise_for_status()` する） |
| `GET <inbox>` | rdflib でパースできる JSON-LD。`ldp:contains` のオブジェクトが通知 IRI の一覧になる |
| `GET <inbox>/<id>` | 通知そのもの |
| `OPTIONS <inbox>` | `Accept-Post` ヘッダ（`Sender` が Graph を送るときだけ見る） |
| `HEAD /` | `ldp#inbox` の Link ヘッダ（`BaseLDN.discover` 用） |

`GET <inbox>?target=<uri>` の絞り込みは、通知の `target.id` と突き合わせている。
WEKO 側（`weko_notifications/views.py`）は `?target=<THEME_SITEURL>/users/<id>` を付けて GET する。

---

## 通知の種類

`weko-workflow` は 8 種類を発行する（`weko_workflow/api.py` の `notify_about_activity`）。

| ケース | COAR Notify の type | 宛先 |
|---|---|---|
| `registered` | `Announce` + `coar-notify:IngestAction` | 登録者 |
| `request_approval` | `Offer` + `coar-notify:EndorsementAction` | 承認者 |
| `approved` | `Announce` + `coar-notify:EndorsementAction` | 登録者 |
| `rejected` | `Reject` | 登録者 |
| `deleted` | `Announce` + `coar-notify:IngestAction` + `Delete` | 登録者 |
| `deletion_request` | `Offer` + `coar-notify:EndorsementAction` + `Delete` | 承認者 |
| `deletion_approved` | `Announce` + `coar-notify:EndorsementAction` + `Delete` | 登録者 |
| `deletion_rejected` | `Reject` + `Delete` | 登録者 |

SWORD 経由の登録・削除にも `notify_item_imported` / `notify_item_deleted` がある
（`weko-swordserver/utils.py`）。

### 宛先はどう決まるか

- **登録者向け**（`_get_params_for_registrant`）:
  `activity_login_user` と共有ユーザ。ただし **操作者自身（`activity_update_user`）は除外される**。
  自分で登録して自分で公開した場合、通知は 0 件になる（実装どおりで、不具合ではない）。
- **承認者向け**（`_get_params_for_approver`）:
  `WEKO_ADMIN_PERMISSION_ROLE_REPO`（Repository Administrator）ロールを持つユーザを DB から解決する。
  フローの承認アクションに `action_role` が設定されていればそれも加味される。

---

## どの操作で飛ぶのか

**ワークフローのどのボタンでも飛ぶわけではない。** `weko_workflow/views.py` の中の
限られた遷移だけである。

```python
if next_action_endpoint == "approval":
    work_activity.notify_about_activity(activity_id, "request_approval")   # 次が承認のとき
...
if next_action_endpoint == "end_action":
    if action_endpoint == "approval":
        work_activity.notify_about_activity(activity_id, "approved")       # 承認を終えたとき
    else:
        work_activity.notify_about_activity(activity_id, "registered")
```

既定フロー（Start → Item Registration → Item Link → Identifier Grant → Approval → End）だと:

| 遷移 | 通知 |
|---|---|
| Item Registration → Item Link | **なし** |
| Item Link → Identifier Grant | **なし** |
| Identifier Grant → Approval | `request_approval`（次が承認だから） |
| Approval → End | `approved`（承認を終えたから） |

「登録したのに通知が来ない」と思ったときは、**まだ Approval の手前にいないか**を確認すること。

---

## 動作確認

```bash
# 1) inbox が受信しているか（受信内容がそのまま出る）
kubectl -n weko3 logs -f deploy/coar-notify-inbox

# 2) テナント経由で inbox が見えるか（通知 IRI はこの URL になる）
curl -k -H 'accept: application/ld+json' https://tenant1.localhost/inbox

# 3) 特定ユーザ宛だけ
curl -k -H 'accept: application/ld+json' \
  'https://tenant1.localhost/inbox?target=http://tenant1.localhost/users/2'
```

ブラウザで `https://tenant1.localhost/inbox` を開くと、受信一覧が HTML で見られる。

WEKO の閲覧 API は `GET /api/notifications`（要ログイン、ログインユーザ宛だけを返す）。

---

## 設定

`WEKO_COAR_NOTIFY=yes` のとき、`gen-tenant.sh` が invenio.cfg に次を追記する。

```python
WEKO_NOTIFICATIONS = True
WEKO_NOTIFICATIONS_INBOX_ADDRESS = "http://inbox:8080"
WEKO_NOTIFICATIONS_INBOX_ENDPOINT = "/inbox"
```

`weko-notifications` の既定値がそもそもこの値なので**無設定でも動く**が、
invenio.cfg を見れば送信先が分かるようにするため、また外部 inbox に差し替えられるようにするために
明示している。差し替えるときは:

```bash
WEKO_COAR_NOTIFY=yes WEKO_INBOX_ADDRESS=https://inbox.example.org bash deploy-amd64.sh
```

| 環境変数 | 既定 | 意味 |
|---|---|---|
| `WEKO_COAR_NOTIFY` | `no` | `yes` で inbox を立てる |
| `WEKO_INBOX_IMAGE` | `python:3.12-alpine` | inbox のベースイメージ |
| `WEKO_INBOX_ADDRESS` | `http://inbox:8080` | 送信先（`gen-tenant.sh` が読む） |

---

## 既定（`WEKO_COAR_NOTIFY=no`）のときどうなるか

- inbox は立たない。`gen-tenant.sh` は invenio.cfg に**1行も追記しない**。
- `WEKO_NOTIFICATIONS` はモジュール既定の `True` のままなので、**通知の送信自体は試みられる**。
  inbox が無いので接続に失敗するが、`_notify_about_activity_wiht_case` が `except Exception` で
  握ってログに残すだけで、**ワークフローは従来どおり完走する**。
- `21-nginx-config.yaml` の `/inbox` はどの構成でも入るが、後述のとおり nginx の起動には影響せず、
  リクエストが来たときに 502 を返すだけである。

送信の試行自体を止めたい場合は、invenio.cfg に `WEKO_NOTIFICATIONS = False` を足す。

---

## 実際に嵌まった点

### 1. Service 名 `inbox` が環境変数を注入してくる

Kubernetes は Service 名から Docker link 形式の環境変数を、同じ名前空間の**全 Pod** に注入する。
Service を `inbox` にすると `INBOX_PORT=tcp://10.96.x.x:8080` が入るため、
`inbox.py` 側で `INBOX_PORT` を使うと `int()` で落ちる。`LISTEN_PORT` のように衝突しない名前にすること。

```
ValueError: invalid literal for int() with base 10: 'tcp://10.96.225.2:8080'
```

### 2. nginx の resolver は `/etc/resolv.conf` の search を使わない

WEKO 側は `http://inbox:8080` で通るが、nginx の `resolver` はサフィックス補完をしないので
短縮名では引けない。**FQDN で書く必要がある。**

```
[error] inbox could not be resolved (2: Server failure)
```

`21-nginx-config.yaml` では `inbox.weko3.svc.cluster.local` を使っている。

### 3. `proxy_pass` にホスト名を直書きすると nginx が起動しなくなる

nginx は起動時に upstream の名前解決を試みるため、inbox Service が無い構成では**nginx ごと
起動に失敗する**。変数経由にするとリクエスト時解決になるので、既定（inbox 無し）でも従来どおり起動する。

```nginx
location /inbox {
    resolver 10.96.0.10 valid=30s ipv6=off;
    set $coar_inbox http://inbox.weko3.svc.cluster.local:8080;
    proxy_pass $coar_inbox$request_uri;
}
```

### 4. 通知 IRI の URL は 2 種類ある

`inbox_url()` と `inbox_url(_external=True)` は別物である。

| 呼び方 | 値 | 用途 |
|---|---|---|
| `inbox_url()` | `WEKO_NOTIFICATIONS_INBOX_ADDRESS` + `/inbox` | WEKO がサーバ側から叩く先 |
| `inbox_url(_external=True)` | `THEME_SITEURL` + `/inbox` | 通知の中や API の返り値に載る URL |

`views.py` は返す IRI に対して前者から後者への**文字列置換**をかける。したがって inbox が組み立てる
IRI のベース（`INBOX_BASE_URL`）は、WEKO の設定値と**完全に一致していなければならない**。
また後者が指す `https://<tenant>/inbox` を実際に配信するために、nginx の中継が要る。

---

## この構成で本番と違うところ

| 項目 | この構成 | 本番相当 |
|---|---|---|
| 永続化 | **なし**（メモリ。Pod 再起動で消える） | DB / ファイル |
| 認証 | **なし**（誰でも POST できる） | トークン等 |
| 署名検証 | **なし** | 必要に応じて |
| 配信範囲 | クラスタ内 + テナントの `/inbox` | 公開エンドポイント |
| 相手 | 自分自身（WEKO → 自前 inbox） | 外部サービス（査読・推薦・overlay journal 等） |

COAR Notify は本来 **リポジトリと外部サービスの間**でやり取りするものなので、この構成は
「WEKO が仕様どおりの通知を出せているか」を確認するためのものである。

---

## 片付け

```bash
kubectl -n weko3 delete -f 72-coar-notify-inbox.yaml
kubectl -n weko3 delete configmap coar-notify-inbox-src
```

nginx の `/inbox` はそのままでよい（502 を返すだけ）。

---

## 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| [README-amd64.md](README-amd64.md) | 構築手順の全体 |
| [SHIBBOLETH-IDP.md](SHIBBOLETH-IDP.md) | Shibboleth ログイン（同じく環境変数で切り替える機能） |
| [ACCESS-kubectl.md](ACCESS-kubectl.md) | 各コンポーネントへの kubectl アクセス |
