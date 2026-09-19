# E2E テスト実行記録

English: [`README.md`](README.md)

`install.sh` で構築した環境に対してスイートを実行した記録です。画像は各
ステップがテストの実行中に自分で撮ったもので、再実行すると同じ名前で上書き
されます。したがってこの記録は実装から乖離しません。

このファイルは実行全体・基本スイート・後始末です。オプションスイートは
[それぞれ専用の記録](#オプションスイート)があり、画像もその隣にあります。

## 結果

| | |
| --- | --- |
| 実行日時 | 2026-09-19 04:37:49 〜 04:43:26 (UTC) |
| 実行 ID | `20260919-043749` |
| 結果 | **37 passed, 2 skipped**（所要 336.58 秒） |
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

============ 37 passed, 2 skipped, 20 warnings in 336.58s (0:05:36) ============
```

skip 2 件は Crossref の deposit です。この環境には Crossref アカウントを
設定していないため、WEKO は DOI を付与して送信は行いません（仕様どおりの
挙動）。deposit 経路は別途検証しており、[`crossref/README.ja.md`](crossref/README.ja.md)
に記録しています。

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
| 基本 | `1789792754033` | `3e5875f0…` / `04c12c39…` | `A-20260919-00014` | `2000053` |
| `ark` | `1789792686782` | `a92947f8…` / `bcf6c81e…` | `A-20260919-00013` | `2000052` |
| `coarnotify` | `1789792844096` | `41fb8d9f…` / `64c39c83…` | `A-20260919-00015` | `2000054` |
| `crossref` | `1789792927666` | `a56e2f94…` / `fb89d190…` | `A-20260919-00016` | `2000055` |

オプションスイートが確認したもの:

| | |
| --- | --- |
| 発行された ARK | `ark:/99999/fk400002` |
| 付与された Crossref DOI | `10.5555/0002000055` |
| COAR Notify で送られた通知 | 5 件。アイテムを登録した各スイートの承認依頼 1 件ずつと、`coarnotify` スイートが確認した承認通知 1 件 |

---

## 基本スイート: ステップごとのエビデンス

### 01. ログイン（test_01_login）

システム管理者 `wekosoftware@nii.ac.jp` でログインする。

![ログイン後のトップ画面](images/01-logged-in.png)

### 02. テスト用インデックスの作成（test_02_create_index）

インデックスを作成し、公開状態にする。管理画面の Index Tree に
`E2E Index 20260919-043749` が既定の `Sample Index` と並んで現れている。

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

INDEX TREE で `E2E Index 20260919-043749` にチェックを入れ、
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

`/records/2000053` にアイテムが登録され、登録したタイトルが表示される。

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

## オプションスイート

それぞれに専用の実行記録があり、その記録が使う画像も同じ場所にあります。
コード側のスイート分割と同じ切り方なので、1 つのスイートを読む・足すときに
他を気にせずに済みます。

| スイート | 実行記録 | 結果 | 確認すること |
| --- | --- | --- | --- |
| `ark` | [`ark/README.ja.md`](ark/README.ja.md) | 6 passed | ARK が発行され、アイテムのパーマリンクになる |
| `coarnotify` | [`coarnotify/README.ja.md`](coarnotify/README.ja.md) | 10 passed | 承認依頼と承認が COAR Notify で意図した相手に届く |
| `crossref` | [`crossref/README.ja.md`](crossref/README.ja.md) | 8 passed, 2 skipped | Crossref DOI が付与され、パーマリンクになる |

skip 2 件は Crossref の deposit で、この環境にはアカウントがありません。
別途検証した deposit 経路は `crossref/README.ja.md` に記録しています。

---

## 後始末の記録

テストは既定では作成物を**残す**（失敗時に画面を確認できるようにするため）。
残っているものは台帳で確認できる。

```console
$ ./e2ectl status          # status 行の run_id は status を呼んだ時刻のもの
Settings(base_url='https://localhost', run_id='20260919-044426', label='E2E')
ledger: /home/mhaya/weko-workshop/e2e/.e2e-state.json
  run 20260919-043749  started 2026-09-19T04:38:06  20 resource(s)
    index     1789792686782            E2E Index 20260919-043749-ark
    flow      a92947f8-df56-4b86-a9d5-fe116b7677a8 E2E Flow 20260919-043749-ark
    workflow  bcf6c81e-62b2-44dc-9624-d6eceb5d50a0 E2E Workflow 20260919-043749-ark
    activity  A-20260919-00013         E2E Workflow 20260919-043749-ark
    item      2000052                  E2E item 20260919-043749-ark
    index     1789792754033            E2E Index 20260919-043749
    ...                                （基本スイートの 5 件）
    index     1789792844096            E2E Index 20260919-043749-coarnotify
    ...                                （coarnotify スイートの 5 件）
    index     1789792927666            E2E Index 20260919-043749-crossref
    ...                                （crossref スイートの 5 件）
```

```console
$ ./e2ectl clean --hard
deleted  item 2000052 E2E item 20260919-043749-ark
deleted  item 2000053 E2E item 20260919-043749
deleted  item 2000054 E2E item 20260919-043749-coarnotify
deleted  item 2000055 E2E item 20260919-043749-crossref
deleted  activity A-20260919-00013 ...
deleted  workflow bcf6c81e-62b2-44dc-9624-d6eceb5d50a0 ...
deleted  flow a92947f8-df56-4b86-a9d5-fe116b7677a8 ...
deleted  index 1789792686782 E2E Index 20260919-043749-ark
deleted  index 1789792754033 E2E Index 20260919-043749
deleted  index 1789792844096 E2E Index 20260919-043749-coarnotify
deleted  index 1789792927666 E2E Index 20260919-043749-crossref
hard purge: docker compose -f docker-compose2.yml exec -T web invenio shell /tmp/weko-e2e-purge.py /tmp/weko-e2e-purge.json
purged items: 2000052, 2000053, 2000054, 2000055
purged activities: A-20260919-00013, A-20260919-00014, A-20260919-00015, A-20260919-00016
purged workflows: bcf6c81e-..., 04c12c39-..., 64c39c83-..., fb89d190-...
purged flows: a92947f8-..., 3e5875f0-..., 41fb8d9f-..., a56e2f94-...
purged indexes: 1789792686782, 1789792754033, 1789792844096, 1789792927666
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
$ curl -s -o /dev/null -w '%{http_code}\n' --insecure https://localhost/records/2000053
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
