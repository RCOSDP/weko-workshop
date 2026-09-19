# E2E テスト実行記録（基本テスト）

English: [`README.md`](README.md)

`install.sh` で構築した環境に対して、[`../tests/test_basic_publish.py`](../tests/test_basic_publish.py)
を実行した記録です。画像は各ステップがテストの実行中に自分で撮ったもので、
再実行すると同じ名前で上書きされます。したがってこの記録は実装から乖離しません。

## 結果

| | |
| --- | --- |
| 実行日時 | 2026-09-19 03:31:03 〜 03:36:41 (UTC) |
| 実行 ID | `20260919-033104` |
| 結果 | **37 passed, 2 skipped**（所要 337.38 秒） |
| 対象 | `https://localhost`（`install.sh` / `docker-compose2.yml`） |
| スイート | 基本 / `ark`（代替 ARK サーバ使用） / `coarnotify` / `crossref` |
| 後始末 | `./e2ectl clean --hard` で全削除、DB も Inbox も `install.sh` 直後の状態に復帰 |

```
============================= test session starts ==============================
platform linux -- Python 3.11.12, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/mhaya/weko-workshop/e2e
configfile: pytest.ini
collected 37 items

tests/test_basic_publish.py::test_01_login PASSED
tests/test_basic_publish.py::test_02_create_index PASSED
tests/test_basic_publish.py::test_03_define_flow PASSED
tests/test_basic_publish.py::test_04_define_workflow PASSED
tests/test_basic_publish.py::test_05_start_activity PASSED
tests/test_basic_publish.py::test_06_register_metadata PASSED
tests/test_basic_publish.py::test_07_designate_index PASSED
tests/test_basic_publish.py::test_08_item_link PASSED
tests/test_basic_publish.py::test_09_identifier_grant PASSED
tests/test_basic_publish.py::test_10_approve PASSED
tests/test_basic_publish.py::test_11_record_is_registered PASSED
tests/test_basic_publish.py::test_12_record_is_public PASSED
tests/test_basic_publish.py::test_13_record_is_in_index PASSED

tests/test_ark_mint.py::test_01_login PASSED
tests/test_ark_mint.py::test_02_set_up PASSED
tests/test_ark_mint.py::test_03_register_item PASSED
tests/test_ark_mint.py::test_04_ark_was_minted PASSED
tests/test_ark_mint.py::test_05_ark_is_the_permalink PASSED
tests/test_ark_mint.py::test_06_ark_is_published PASSED

tests/test_coar_notify.py::test_01_login PASSED
tests/test_coar_notify.py::test_02_the_instance_announces_its_inbox PASSED
tests/test_coar_notify.py::test_03_notifications_are_not_public PASSED
tests/test_coar_notify.py::test_04_the_approver_can_read_their_notifications PASSED
tests/test_coar_notify.py::test_05_set_up PASSED
tests/test_coar_notify.py::test_06_send_the_item_for_approval PASSED
tests/test_coar_notify.py::test_07_the_approver_is_offered_the_item PASSED
tests/test_coar_notify.py::test_08_the_approver_approves PASSED
tests/test_coar_notify.py::test_09_the_registrant_is_told_it_was_approved PASSED
tests/test_coar_notify.py::test_10_the_user_can_choose_how_to_be_notified PASSED

tests/test_crossref_doi.py::test_01_prefix_is_set PASSED
tests/test_crossref_doi.py::test_02_set_up PASSED
tests/test_crossref_doi.py::test_03_register_item PASSED
tests/test_crossref_doi.py::test_04_choose_crossref_grant PASSED
tests/test_crossref_doi.py::test_05_approve PASSED
tests/test_crossref_doi.py::test_06_doi_was_granted PASSED
tests/test_crossref_doi.py::test_07_doi_is_the_permalink PASSED
tests/test_crossref_doi.py::test_08_doi_is_published PASSED
tests/test_crossref_doi.py::test_09_deposit_was_recorded SKIPPED
tests/test_crossref_doi.py::test_10_deposit_reached_crossref SKIPPED

============ 37 passed, 2 skipped, 20 warnings in 337.38s (0:05:37) ============
```

skip 2 件は Crossref の deposit です。この環境には Crossref アカウントを
設定していないため、WEKO は DOI を付与して送信は行いません（仕様どおりの
挙動）。deposit 経路は別途検証しており、後述します。

警告はいずれも自己署名証明書に対する `InsecureRequestWarning` で、
テスト対象の挙動とは無関係です。

## 実行環境

```
suite     : weko-workshop  feature/e2e-tests  61e0174
WEKO      : wekov2  feature/nii_WACREN_crossref_doi  594e070cf
python    : 3.11.12（テスト実行側）
playwright: 1.63.0 / chromium-1243
pytest    : 9.1.1
requests  : 2.34.2 / beautifulsoup4 4.15.0
```

| サービス | イメージ | 状態 |
| --- | --- | --- |
| web | wekov2-web | Up |
| worker | wekov2-worker | Up |
| nginx | wekov2-nginx | Up |
| elasticsearch | wekov2-elasticsearch | Up |
| postgresql | postgres:12 | Up |
| pgpool | pgpool/pgpool:4.2.2 | Up |
| redis | redis:7.4.1 | Up |
| rabbitmq | rabbitmq:4.0.2 | Up |
| mongo | mongo:7.0.14 | Up |
| inbox | wekov2-inbox | Up |
| flower | mher/flower:0.9.5 | Up |

この実行で作成したリソース。スイートごとに 5 つずつ、名前が分かれているので
4 スイートが同一セッションを共有できます。

| スイート | インデックス | フロー / ワークフロー | アクティビティ | アイテム |
| --- | --- | --- | --- | --- |
| 基本 | `1789788748142` | `80fe7b37…` / `3e1c6c93…` | `A-20260919-00010` | `2000049` |
| `ark` | `1789788681275` | `b8003d70…` / `e10b1a8b…` | `A-20260919-00009` | `2000048` |
| `coarnotify` | `1789788837713` | `a6419b6e…` / `ef72e531…` | `A-20260919-00011` | `2000050` |
| `crossref` | `1789788922177` | `efd70637…` / `b3f63b3e…` | `A-20260919-00012` | `2000051` |

オプションスイートが確認したもの:

| | |
| --- | --- |
| 発行された ARK | `ark:/99999/fk400002` |
| 付与された Crossref DOI | `10.5555/0002000051` |
| COAR Notify で送られた通知 | 5 件。アイテムを登録した各スイートの承認依頼 1 件ずつと、`coarnotify` スイートが確認した承認通知 1 件 |

---

## 基本スイート: ステップごとのエビデンス

### 01. ログイン（test_01_login）

システム管理者 `wekosoftware@nii.ac.jp` でログインする。

![ログイン後のトップ画面](images/01-logged-in.png)

### 02. テスト用インデックスの作成（test_02_create_index）

インデックスを作成し、公開状態にする。管理画面の Index Tree に
`E2E Index 20260919-033104` が既定の `Sample Index` と並んで現れている。

新規作成したインデックスは非公開なので、ここで公開状態にする。
これをしないと 12（未ログインからの閲覧）が失敗する。

![Edit Tree に作成したインデックスが出ている](images/02-index-created.png)

### 03. テスト用フローの定義（test_03_define_flow）

Start / Item Registration / Item Link / Identifier Grant / Approval / End の
6 アクションを順番どおりに定義する。Status が `Available` になっている。

![6 アクションのフロー定義](images/03-flow-defined.png)

### 04. テスト用ワークフローの定義（test_04_define_workflow）

アイテムタイプ「デフォルトアイテムタイプ（フル）」と 03 のフローを
割り当てたワークフローを定義する。インデックスは**指定しない**
（指定するとアイテム登録時に自動指定され、07 の画面が出なくなるため）。

![ワークフロー定義](images/04-workflow-defined.png)

### 05. アクティビティの開始（test_05_start_activity）

ワークフロー一覧に定義したワークフローが現れる。

![ワークフロー一覧](images/05-workflow-list.png)

開始すると Item Registration の画面になる。

![アクティビティ開始直後](images/06-activity-started.png)

### 06. メタデータ入力（test_06_register_metadata）

サンプル PDF を添付し、このアイテムタイプの必須項目
（PubDate / Title / Resource Type）を入力する。

![メタデータ入力後](images/07-item-metadata.png)

### 07. インデックス指定（test_07_designate_index）

INDEX TREE で `E2E Index 20260919-033104` にチェックを入れ、
DESIGNATE INDEX に反映されていることを確認する。

![インデックス指定](images/08-index-designated.png)

### 08. アイテムリンク（test_08_item_link）

他アイテムとのリンクは指定せずに次へ進む。

![アイテムリンク画面](images/09-item-link.png)

### 09. 識別子付与（test_09_identifier_grant）

基本テストでは DOI を付与しない。`Not Grant` が選択されていることを確認する。
DOI 付与は派生版で扱う（先行例: `works/crossref-doi-manual/e2e/`）。

![Not Grant を選択](images/10-identifier-grant.png)

### 10. 承認 = 公開（test_10_approve）

承認画面。

![承認画面](images/11-approval.png)

承認するとアクティビティが End になり、6 アクションすべてが Done、
履歴に Start から End までが並ぶ。この時点でアイテムが登録・公開される。

![承認後（Status: End、全アクション Done）](images/12-approved.png)

### 11. アイテムの登録確認（test_11_record_is_registered）

`/records/2000049` にアイテムが登録され、登録したタイトルが表示される。

![アイテム詳細（管理者）](images/13-record-page.png)

### 12. 公開の確認（test_12_record_is_public）

**未ログイン**のブラウザコンテキストから同じページを開く。右上が `Log in`
（＝ログインしていない）状態で、タイトル・ファイル・アイテムタイプ
「デフォルトアイテムタイプ（フル）」が見えている。ここまでで「公開された」
ことが確認できる。

![アイテム詳細（未ログイン）](images/14-record-page-anonymous.png)

### 13. 検索での確認（test_13_record_is_in_index）

未ログインのまま、作成したインデックス配下を検索する。`Found 1 result.` で
登録したアイテムがヒットする。Elasticsearch への反映は非同期なので、
テストはここだけ最大 3 分待つ。worker と Elasticsearch が動いていることの
確認も兼ねている。

![インデックス検索（未ログイン）](images/15-search-in-index.png)

---

## `ark` スイート

この環境には ARK サーバが無いため、代替スタブ（`e2ectl ark-stub enable`）に
対して実行しています。`e2ectl ark-account enable` で設定した実サーバに対する
実行結果は後述の「別の環境設定での実行」にあります。

### DOI を付与せずにアイテムを登録（test_03）

ARK は Item Registration の完了時に発行されるため、画面上で ARK を要求する
操作はありません。

![ARK 実行時の承認画面](images/ark-02-approval.png)

![承認後](images/ark-03-approved.png)

### アイテムが ARK を持つ（test_04 / test_05）

DOI も CNRI も無いアイテムのパーマリンクは ARK になります。ここでは
`ark:/99999/fk400002` で、設定した NAAN 配下であることも確認しています。

![ARK がパーマリンクとして表示されたアイテム詳細](images/ark-04-record-page.png)

---

## `coarnotify` スイート

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

![承認待ちのアクティビティ](images/coarnotify-01-awaiting-approval.png)

`repoadmin@example.org` として読み出し、Inbox から本体を取得したもの:

```json
{
  "id": "urn:uuid:2d6758d5-ff84-44ba-a23d-2c3e8e3c3122",
  "@context": ["https://www.w3.org/ns/activitystreams", "https://coar-notify.net"],
  "type": ["Offer", "coar-notify:EndorsementAction"],
  "origin": {"id": "https://localhost/", "inbox": "…/inbox", "type": "Service"},
  "target": {"id": "https://weko3.example.org/users/2", "inbox": "…/inbox", "type": "Person"},
  "object": {"id": "https://localhost/records/2000050",
             "type": ["Page", "sorg:WebPage"],
             "name": "E2E item 20260919-033104-coarnotify"},
  "actor":  {"id": "https://weko3.example.org/users/1", "type": "Person"},
  "context": {"id": "https://localhost/workflow/activity/detail/A-20260919-00011",
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

![承認者から見た承認画面](images/coarnotify-02-approver-screen.png)

![承認後](images/coarnotify-03-approved.png)

### 承認が登録者に返る（test_09）

```
urn:uuid:fce8aee7-18a4-4e52-9ffc-7c5ce3c5d396
  Announce+coar-notify:EndorsementAction
  -> https://weko3.example.org/users/1
  about 'E2E item 20260919-033104-coarnotify' (https://localhost/records/2000050)
```

`users/1` が登録者、`actor` は `users/2` = 依頼を受け取ったアカウントです。
ステップはまさにそこを確認します。依頼を受けた人が承認者として名乗られて
いること、そして承認した本人には通知が返っていないこと。

`./e2ectl inbox --run <実行 ID>` で往復の両端が見えます。

```console
$ ./e2ectl inbox --run 20260919-033104
registrant: wekosoftware@nii.ac.jp
  announced inbox: https://weko3.example.org/inbox
  2026-09-19 03:35:00  … Announce+…EndorsementAction -> …/users/1 about 'E2E item 20260919-033104-coarnotify'
  1 of 1 notification(s) shown
approver: repoadmin@example.org
  2026-09-19 03:34:43  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-033104-coarnotify'
  2026-09-19 03:36:10  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-033104-crossref'
  2026-09-19 03:32:06  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-033104-ark'
  2026-09-19 03:33:29  … Offer+…EndorsementAction -> …/users/2 about 'E2E item 20260919-033104'
  4 of 40 notification(s) shown
```

承認依頼が 4 件あるのは、アイテムを登録する**すべての**スイート（基本と
識別子系 2 つを含む）がそれぞれ 1 件送るためです。承認通知が 1 件だけなのは、
登録者以外に承認させるのが `coarnotify` スイートだけだからです。

### 通知方法の設定画面（test_10）

![通知設定画面](images/coarnotify-04-settings.png)

利用者ごとに Web push と Email を選べます。スイートは両方が提示されることを
確認します。Web push を実際に有効化するにはブラウザの通知許可と inbox
コンテナ側の VAPID 鍵が要りますが、この環境では鍵は未設定です。

---

## `crossref` スイート

### プレフィックスの設定（test_01）

Crossref 付与を有効にしプレフィックスを設定します。終了時にはどちらも元へ
戻します。

![プレフィックスを設定した識別子設定](images/crossref-01-identifier-settings.png)

### deposit に必要なメタデータ（test_03）

Crossref は掲載誌・ISSN・発行日が無いジャーナル論文を受け付けないため、
基本フローでは入力しないこれらを補います。

![掲載誌情報を入力したメタデータ画面](images/crossref-02-item-metadata.png)

### Crossref 付与が提示され、選択される（test_04）

![Crossref DOI が提示された識別子付与画面](images/crossref-03-grant-chosen.png)

### 承認と DOI の確認（test_05〜test_08）

![承認画面](images/crossref-04-approval.png)

![承認後](images/crossref-05-approved.png)

設定したプレフィックス配下の `10.5555/0002000051` が付与され、パーマリンク
として表示されます。

![DOI が表示されたアイテム詳細](images/crossref-06-record-page.png)

### deposit（test_09 / test_10）

この実行ではアカウント未設定のため skip。経路全体は Crossref 代替スタブに
対して別途検証済みです。

```
granted DOI: 10.5555/0002000032
deposit: {'id': 1, 'agency': 'Crossref', 'status': 'submitted', 'attempt': 1,
          'poll': 0, 'http': 200, 'tracking_id': 'weko-82309c1d…-20260917222135'}
deposit: {'id': 1, 'agency': 'Crossref', 'status': 'success', 'attempt': 1,
          'poll': 1, 'http': 200, 'error': 'Crossref registered the DOI.'}
→ 10 passed
```

`WEKO_E2E_CROSSREF_DEPOSIT` を有効にし、`e2ectl crossref-account enable` で
アカウントをインスタンスへ書き込むと、この 2 ステップが worker の deposit
完了まで待って Crossref の応答を報告します。

---

## 後始末の記録

テストは既定では作成物を**残す**（失敗時に画面を確認できるようにするため）。
残っているものは台帳で確認できる。

```console
$ ./e2ectl status          # status 行の run_id は status を呼んだ時刻のもの
Settings(base_url='https://localhost', run_id='20260919-033742', label='E2E')
ledger: /home/mhaya/weko-workshop/e2e/.e2e-state.json
  run 20260919-033104  started 2026-09-19T03:31:21  20 resource(s)
    index     1789788681275            E2E Index 20260919-033104-ark
    flow      b8003d70-3c24-4c10-95e9-e6b3cc9a2829 E2E Flow 20260919-033104-ark
    workflow  e10b1a8b-f5ce-4421-8601-18a876d7ec4e E2E Workflow 20260919-033104-ark
    activity  A-20260919-00009         E2E Workflow 20260919-033104-ark
    item      2000048                  E2E item 20260919-033104-ark
    index     1789788748142            E2E Index 20260919-033104
    ...                                （基本スイートの 5 件）
    index     1789788837713            E2E Index 20260919-033104-coarnotify
    ...                                （coarnotify スイートの 5 件）
    index     1789788922177            E2E Index 20260919-033104-crossref
    ...                                （crossref スイートの 5 件）
```

```console
$ ./e2ectl clean --hard
deleted  item 2000048 E2E item 20260919-033104-ark
deleted  item 2000049 E2E item 20260919-033104
deleted  item 2000050 E2E item 20260919-033104-coarnotify
deleted  item 2000051 E2E item 20260919-033104-crossref
deleted  activity A-20260919-00009 ...
deleted  workflow e10b1a8b-f5ce-4421-8601-18a876d7ec4e ...
deleted  flow b8003d70-3c24-4c10-95e9-e6b3cc9a2829 ...
deleted  index 1789788681275 E2E Index 20260919-033104-ark
deleted  index 1789788748142 E2E Index 20260919-033104
deleted  index 1789788837713 E2E Index 20260919-033104-coarnotify
deleted  index 1789788922177 E2E Index 20260919-033104-crossref
hard purge: docker compose -f docker-compose2.yml exec -T web invenio shell /tmp/weko-e2e-purge.py /tmp/weko-e2e-purge.json
purged items: 2000048, 2000049, 2000050, 2000051
purged activities: A-20260919-00009, A-20260919-00010, A-20260919-00011, A-20260919-00012
purged workflows: e10b1a8b-..., 3e1c6c93-..., ef72e531-..., b3f63b3e-...
purged flows: b8003d70-..., 80fe7b37-..., a6419b6e-..., efd70637-...
purged indexes: 1789788681275, 1789788748142, 1789788837713, 1789788922177
purged notifications: 5
```

最後の 1 行は Inbox です。Inbox は独立したサービスで DB も別なので、WEKO の
DB を戻しても通知は残ります。`--hard` は `weko_e2e/inboxpurge.py` を `inbox`
コンテナにコピーし、`context` がその実行のアクティビティを指す通知だけを
削除します（承認依頼 4 件と承認通知 1 件、それ以外はそのまま）。

### DB の増減

`install.sh` 直後の状態（サンプルインデックス 1・既定フロー 1・既定ワークフロー
2）を基準に、実行で増えた分が `--hard` で過不足なく消えている。

| 時点 | index | flow | workflow | activity | records | bucket | pid | inbox |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| テスト前 | 1 | 1 | 2 | 0 | 0 | 0 | 0 | 36 |
| テスト後 | 5 | 5 | 6 | 4 | 8 | 8 | 37 | 41 |
| `clean --hard` 後 | **1** | **1** | **2** | **0** | **0** | **0** | **0** | **36** |

スイートごとに 1 つずつ増えています。アイテム 1 件あたりレコードと bucket が
2 件ずつなのは、WEKO が「バージョンなし」と「Ver.1」の 2 レコードで持つため
です。pidstore も 0 件に戻っており、付与された DOI と発行された ARK も
残っていません。Inbox も実行前の 36 件に戻っています。

削除後はアイテムのページも消えている。

```console
$ curl -s -o /dev/null -w '%{http_code}\n' --insecure https://localhost/records/2000049
404
```

## 別の環境設定での実行

同じスイートを、同じ環境に別の経路で向けて実行しました。設定はこのためにあり、
いずれもコード変更は不要です。

| 設定 | 結果 |
| --- | --- |
| 既定値（`https://localhost`） | 13 passed |
| `WEKO_BASE_URL=https://weko3.example.org` + `WEKO_E2E_HOST_IP=127.0.0.1`（DNS 登録なし、`/etc/hosts` も未編集） | 13 passed |
| 同上 + `WEKO_TEST_EMAIL` / `WEKO_TEST_PASSWORD` を別のシステム管理者アカウントに、`WEKO_E2E_LABEL=E2E-user2` | 13 passed |
| `ark` を `e2ectl ark-account enable` で設定した実サーバ（API key ではなくログイン方式）に対して | 6 passed、設定どおり `ark:/12345/x900002` を発行 |
| `crossref` に `WEKO_E2E_CROSSREF_DEPOSIT=1` を付け、Crossref 代替スタブ宛てに | 10 passed、deposit が `success` に到達 |
| `coarnotify` 単体を、環境付属の `inbox` サービス宛てに | 10 passed、依頼が `users/2`、承認通知が `users/1` に到達 |

2 行目はブラウザ側の host resolver ルールと HTTP クライアント側のホスト
ピン留めの両方を通ります。3 行目は、環境に最初から入っているアカウントに
依存していないことの確認です。検証用に作ったアカウントは削除済みで、
いずれの実行後も DB は基準状態に戻っています。

## 繰り返し実行について

同じ環境で連続実行しても、リソース名に実行 ID が入るため衝突しません。
`--clean-after --clean-hard` を付けた連続 2 サイクルが成功し、
いずれも DB が基準状態に戻ることを確認済みです。

```console
$ for i in 1 2; do ../.venv-e2e/bin/python -m pytest --clean-after --clean-hard -q; done
================== 13 passed, 6 warnings in 82.08s (0:01:22) ===================
================== 13 passed, 6 warnings in 82.27s (0:01:22) ===================
```

スイート同士も衝突しません。作成物の名前には実行 ID に加えてスイート名が
入るため、上記 4 スイートが同一セッションを共有できています。

## この記録の再作成

```bash
cd e2e
../.venv-e2e/bin/python ./e2ectl ark-stub enable # ark スイートにはサーバが要る
../.venv-e2e/bin/python ./e2ectl clean --hard   # 基準状態に戻す
WEKO_E2E_ARK_NAAN=99999 \
  ../.venv-e2e/bin/python -m pytest --suite all   # 画像が撮り直される
../.venv-e2e/bin/python ./e2ectl status         # 台帳を確認
../.venv-e2e/bin/python ./e2ectl clean --hard    # 後始末
../.venv-e2e/bin/python ./e2ectl ark-stub disable
```

`coarnotify` スイートに事前準備は不要です。`inbox` サービスも
`repoadmin@example.org` も `install.sh` が用意するものです。

画像は `images/` に固定の名前で書かれるので、実行するたびに差し替わります。
この文書の数値（実行 ID・アイテム ID・所要時間）は実行ごとに変わります。
