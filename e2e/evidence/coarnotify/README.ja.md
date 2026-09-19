# E2E テスト実行記録: `coarnotify` スイート

English: [`README.md`](README.md) ·
この記録が属する実行: [`../README.ja.md`](../README.ja.md)

承認依頼と承認が COAR Notify で通知され、意図した相手に届くことを確認します。WEKO
は「自分が行った操作の通知」から自分自身を除外するため、2 アカウントが要ります。

テスト本体は
[`../../tests/test_coar_notify.py`](../../tests/test_coar_notify.py)、画像は
[`images/`](images) にあり、 各ステップが実行中に自分で撮ったものです。

| | |
| --- | --- |
| 実行 ID | `20260919-043749` |
| 結果 | **10 passed** |
| 有効化 | `--suite coarnotify` |

---

WEKO はワークフローの出来事を COAR Notify のメッセージに変換し、この環境の
LDN Inbox（`inbox` コンテナ）へ POST します。受け取った通知は、宛先の利用者
に対して `GET /api/notifications` で返されます。

**誰に届くかが肝心です。** WEKO は「自分が行った操作の通知」から自分自身を
除外するため、このスイートは 2 アカウントを使います。登録は
`wekosoftware@nii.ac.jp`、承認は承認依頼の宛先であるリポジトリ管理者
`repoadmin@example.org` です。

### サイトが Inbox を広告している（test_02）

```console
$ curl -sI --insecure https://localhost/ | grep -i '^link:'
Link: <https://weko3.example.org/inbox>; rel="http://www.w3.org/ns/ldp#inbox"
```

この URL は `THEME_SITEURL`（インスタンスが自称する URL）から作られ、
テスト対象のアドレスとは限りません。そのためスイートは通知を URL そのもの
ではなく**パス**でテスト対象から取得します。またこのヘッダはトップページへの
HEAD にだけ付き GET には付かないので、ステップも HEAD で確認します。

未ログインの閲覧者に対しては、他人の通知ではなく 401 が返ります（test_03）。

### 承認者にアイテムが渡る（test_06 / test_07）

識別子付与から次へ進むとアクティビティが Approval に乗り、そこで WEKO が
承認者へ通知を送ります。

![承認待ちのアクティビティ](images/01-awaiting-approval.png)

`repoadmin@example.org` として読み出し、Inbox から本体を取得したもの:

```json
{
  "id": "urn:uuid:d98ca136-e8dd-42ca-ad2b-2d76b3f2efe0",
  "@context": ["https://www.w3.org/ns/activitystreams", "https://coar-notify.net"],
  "type": ["Offer", "coar-notify:EndorsementAction"],
  "origin": {"id": "https://localhost/", "inbox": "…/inbox", "type": "Service"},
  "target": {"id": "https://weko3.example.org/users/2", "inbox": "…/inbox", "type": "Person"},
  "object": {"id": "https://localhost/records/2000054",
             "type": ["Page", "sorg:WebPage"],
             "name": "E2E item 20260919-043749-coarnotify"},
  "actor":  {"id": "https://weko3.example.org/users/1", "type": "Person"},
  "context": {"id": "https://localhost/workflow/activity/detail/A-20260919-00015",
              "type": ["Page", "sorg:WebPage"]}
}
```

通知とアクティビティを結び付けるのは `context` だけです。スイートは
「最後に届いたもの」ではなく、この `context` で自分の実行の通知を特定します。

### 承認者が承認する（test_08）

承認者は自分専用のブラウザコンテキストでアクティビティを開きます。WEKO は
アクティビティを「開いているウィンドウ」に対してロックするので、登録者が
先に画面から離れ（人が作業を引き継ぐときと同じ）、承認者は前の実行で掴んだ
ままのロックがあれば解放してから開きます。

![承認者から見た承認画面](images/02-approver-screen.png)

![承認後](images/03-approved.png)

### 承認が登録者に返る（test_09）

```
urn:uuid:7f989264-5966-4cc0-847f-6aefb97887d2
  Announce+coar-notify:EndorsementAction
  -> https://weko3.example.org/users/1
  about 'E2E item 20260919-043749-coarnotify' (https://localhost/records/2000054)
```

`users/1` が登録者、`actor` は `users/2` = 依頼を受け取ったアカウントです。
ステップはまさにそこを確認します。依頼を受けた人が承認者として名乗られて
いること、そして承認した本人には通知が返っていないこと。

`./e2ectl inbox --run <実行 ID>` で往復の両端が見えます。

```console
$ ./e2ectl inbox --run 20260919-043749
registrant: wekosoftware@nii.ac.jp
  announced inbox: https://weko3.example.org/inbox
  2026-09-19 04:41:45  … Announce+…EndorsementAction -> …/users/1 about 'E2E item 20260919-043749-coarnotify'
  1 of 1 notification(s) shown
approver: repoadmin@example.org
  2026-09-19 04:41:28  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749-coarnotify'
  2026-09-19 04:42:54  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749-crossref'
  2026-09-19 04:38:52  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749-ark'
  2026-09-19 04:40:15  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-043749'
  4 of 40 notification(s) shown
```

承認依頼が 4 件あるのは、アイテムを登録する**すべての**スイート（基本と
識別子系 2 つを含む）がそれぞれ 1 件送るためです。承認通知が 1 件だけなのは、
登録者以外に承認させるのが `coarnotify` スイートだけだからです。

### 通知方法の設定画面（test_10）

![通知設定画面](images/04-settings.png)

利用者ごとに Web push と Email を選べます。スイートは両方が提示されることを
確認します。Web push を実際に有効化するにはブラウザの通知許可と inbox
コンテナ側の VAPID 鍵が要りますが、この環境では鍵は未設定です。
