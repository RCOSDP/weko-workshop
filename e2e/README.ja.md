# WEKO3 E2E テスト（基本テスト）

English: [`README.md`](README.md)

WEKO3 の環境に対して、**テスト用インデックスの作成 → テスト用ワークフローの
定義 → デフォルトアイテムタイプ（フル）でのアイテム登録 → 公開**までを一通り
流す e2e テストです。派生版（DOI 付与、制限公開、シンプルアイテムタイプ など）
は、このスイートの部品を使い回して作ることを前提にしています。

WEKO のチェックアウトの中ではなくこのリポジトリに置いてあるので、手元の
`install.sh` 環境でも、FQDN のステージングサーバでも、同僚の環境でも、同じ
スイートを向けられます。対象環境に関する値はコードに埋め込んでいません
（[設定](#設定環境変数)を参照）。

テストが作ったデータ（インデックス／フロー／ワークフロー／アクティビティ／
アイテム）は台帳に記録され、`./e2ectl clean` で消せます。

## ディレクトリ

| ファイル | 内容 |
| --- | --- |
| `tests/test_basic_publish.py` | 基本テスト本体。13 ステップで 1 つの流れ |
| `tests/test_ark_mint.py` | オプション `ark`: ARK が発行されることを確認 |
| `tests/test_coar_notify.py` | オプション `coarnotify`: ワークフローが COAR Notify で通知されることを確認 |
| `tests/test_crossref_doi.py` | オプション `crossref`: Crossref DOI が付与されることを確認 |
| `conftest.py` | セッション共有のブラウザ・HTTP クライアント・台帳 |
| `weko_e2e/flow.py` | 全スイートが共通で使う登録フロー |
| `weko_e2e/arkstub.py` | `ark` 用のスタブ ARK サーバ |
| `weko_e2e/notify.py` | COAR Notify で何が通知されたかを読む |
| `weko_e2e/pushstub.py` | Web Push 用の代替ブラウザ購読 |
| `weko_e2e/config.py` | 環境変数／環境ファイルから読む設定 |
| `weko_e2e/client.py` | 画面と同じエンドポイントを叩く HTTP クライアント（準備と後始末用） |
| `weko_e2e/ui.py` | アクティビティ画面を進めるための Playwright ヘルパ |
| `weko_e2e/ledger.py` | 実行が作ったものを記録する台帳（`.e2e-state.json`） |
| `weko_e2e/purge.py` | web コンテナにコピーして実行する物理削除スクリプト |
| `weko_e2e/inboxpurge.py` | 同じものの inbox コンテナ版（LDN Inbox の通知を消す） |
| `weko_e2e/cli.py`, `e2ectl` | テストツール本体 |
| `environments/` | コピーして使う環境ファイルの雛形 |
| `evidence/` | 直近の実行記録とエビデンス画像。オプションスイートごとにフォルダが分かれる |

## 準備

```bash
# このリポジトリのルートで
python3 -m venv .venv-e2e
.venv-e2e/bin/pip install -r e2e/requirements.txt
.venv-e2e/bin/playwright install chromium
```

テスト対象の WEKO3 環境も必要です。手元に立てる場合は WEKO のチェックアウトで:

```bash
./install.sh
```

## 対象環境の指定

環境変数で指定するか、環境ファイルに書きます。雛形が
[`environments/`](environments) にあります。

| ファイル | 用途 |
| --- | --- |
| `local-docker.env` | `install.sh` で手元に立てた環境（既定値と同じ） |
| `fqdn.env` | 正式な FQDN と正式な証明書を持つ環境 |
| `fqdn-no-dns.env` | DNS で引けないホスト名で公開されている環境 |
| `crossref-sandbox.env` | 自分のアカウントで Crossref サンドボックスへ deposit する |
| `ark-server.env` | 自分の ARK サーバに対して ARK を発行する |
| `coar-notify.env` | COAR Notify スイートが使う 2 つのアカウント |

```bash
cp environments/local-docker.env e2e.env    # 置いておけば自動で読む
# または
WEKO_E2E_ENV=environments/fqdn.env ...      # 実行ごとに指定
```

環境変数はファイルより優先されるので、1 回だけ値を差し替えるのも簡単です。
`e2ectl env` で実際に使われる値を確認できます。うまく動かないときはまずここ
から見てください。

```console
$ ../.venv-e2e/bin/python ./e2ectl env
environment file         /home/you/weko-workshop/e2e/environments/fqdn.env
base URL                 https://repository.example.org
host                     repository.example.org
host resolver rule       (DNS)
verify TLS               yes
account                  e2e-admin@example.org
item type                デフォルトアイテムタイプ（フル）
...
```

### DNS で引けないホスト名の場合

WEKO は Host ヘッダから絶対 URL を組み立てるため、IP でしか届かない環境でも
**そのホスト名でアクセスする**必要があります。送り先はこう指定します。

```bash
WEKO_BASE_URL=https://weko3.example.org
WEKO_E2E_HOST_IP=127.0.0.1
```

ブラウザと HTTP クライアントの両方がこれに従うので、`/etc/hosts` への追記も
root 権限も要りません。そのホスト名の証明書は検証できないので、この場合
`WEKO_E2E_VERIFY_TLS` はオフのままにしてください。

## 実行

```bash
cd e2e

# 設定を確認 → 環境に届くかとアカウントを確認
../.venv-e2e/bin/python ./e2ectl env
../.venv-e2e/bin/python ./e2ectl ping

# 基本テストを流す
../.venv-e2e/bin/python -m pytest
```

ブラウザを見ながら流したいときは `WEKO_HEADED=1` を付けます。

アカウントはシステム管理者である必要があります（インデックス・フロー・
ワークフローを作り、自分のアクティビティを承認するため）。

## 実行するテストの選択

基本テストは常に実行されます。オプションのテストは、環境ごとに前提が異なる
ため、**名前で明示的に有効化**したときだけ実行されます。

| スイート | 確認すること | 前提 |
| --- | --- | --- |
| （基本） | インデックス・ワークフロー・アイテム登録・公開 | 動作する WEKO 環境だけ |
| `ark` | ARK が発行され、アイテムのパーマリンクになる | ARK サーバ（`e2ectl ark-account enable`）、または代替スタブ（`e2ectl ark-stub enable`） |
| `coarnotify` | 承認依頼と承認が COAR Notify で正しい相手に通知され、Web Push でも届く | LDN Inbox（`inbox` サービス）と承認役のもう 1 アカウント。Web Push の確認には `e2ectl webpush-stub enable` |
| `crossref` | Crossref DOI が付与され、パーマリンクになる | なし。さらに Crossref へ登録（deposit）するにはアカウントが必要 |

```bash
python -m pytest                      # 基本のみ。オプションは skip
python -m pytest --suite crossref     # + Crossref
python -m pytest --suite all          # 全部
WEKO_E2E_SUITES=ark,coarnotify python -m pytest # 環境変数でも同じ
```

有効化していないスイートは**隠されるのではなく skip され**、理由と有効化の
方法が出ます。

```
tests/test_ark_mint.py::test_01_login SKIPPED (optional suite 'ark' not
enabled; run with --suite ark or WEKO_E2E_SUITES=ark)
```

`--suite` は `WEKO_E2E_SUITES` を置き換えるのではなく追加します。各スイートは
自分専用のインデックス・フロー・ワークフローを作るので、同一セッションで複数
流しても衝突しません。

### `ark` スイート

WEKO は Item Registration アクションの完了時に ARK サーバを呼んで ARK を発行
します。発行されるのは環境が ARK 設定済みのときだけです（mint URL・NAAN・
shoulder と、API key またはログイン情報）。管理画面は無くインスタンス設定
なので、ツールが書き込みます。

#### 自分の ARK サーバに対して

```bash
# 環境ファイル（雛形 environments/ark-server.env）または環境変数で:
WEKO_E2E_ARK_MINT_URL=https://ark.example.org/api/mint
WEKO_E2E_ARK_NAAN=12345
WEKO_E2E_ARK_SHOULDER=x9
WEKO_E2E_ARK_API_KEY=...                 # または LOGIN 系 3 つ

../.venv-e2e/bin/python ./e2ectl ark-account enable    # 書き込み + 再起動
../.venv-e2e/bin/python -m pytest --suite ark
../.venv-e2e/bin/python ./e2ectl ark-account disable   # 元に戻す
```

API key は `WEKO_E2E_ARK_API_KEY_HEADER` ヘッダに
`WEKO_E2E_ARK_API_KEY_PREFIX` を前置して送られます（既定は
`Authorization: Bearer ...`。生のキーを送るなら `X-API-Key` + プレフィックス
空）。API key が無い場合は `WEKO_E2E_ARK_LOGIN_URL` にログインしてトークンを
取得する方式になります。`enable` は設定されている方を書き込み、どちらも
揃っていなければ足りない変数名を挙げて中止します。

#### ARK サーバが無い場合（代替スタブ）

```bash
../.venv-e2e/bin/python ./e2ectl ark-stub enable    # 設定追加・再起動・スタブ起動
WEKO_E2E_ARK_NAAN=99999 ../.venv-e2e/bin/python -m pytest --suite ark
../.venv-e2e/bin/python ./e2ectl ark-stub disable   # 元に戻す
```

スタブは `weko_e2e/arkstub.py` を web コンテナの loopback で動かすものです
（WEKO が mint を呼ぶのはこのコンテナからなので、外部到達性もアカウントも
不要）。`ark:/99999/fk4...` を払い出します。

どちらの `enable` も WEKO チェックアウトの `scripts/instance.cfg`（コンテナが
起動時に `invenio.cfg` を生成する元ファイル）にマーカ付きブロックを追記して
`web` と `worker` を再起動し、対応する `disable` がそのブロックだけを取り除き
ます。両者は同じ設定キーを書くため、片方を有効にするともう片方は無効化され
ます。`status` で現在の状態を確認できます。

コンテナを再起動するとスタブのプロセスは落ちます。`ark-stub start` で設定に
触れずにプロセスだけ起動し直せます（`ark-stub stop` はその逆）。

`WEKO_E2E_ARK_NAAN` を指定すると、発行された ARK がその NAAN 配下かどうかも
確認します。未指定なら ARK であれば通ります。

### `coarnotify` スイート

WEKO はワークフローの出来事を COAR Notify のメッセージに変換し、LDN Inbox
へ POST します。Inbox は WEKO とは別のサービスで、`install.sh` の構成では
`inbox` コンテナがそれにあたります。WEKO は送信側でしかなく、受け取った通知は
宛先の利用者に対して `GET /api/notifications` で返します。

**誰に届くかが肝心です。** WEKO は「自分が行った操作の通知」から自分自身を
除外するので、1 つのアカウントで全部やってしまう実行では何も確認できません。
そのためこのスイートは 2 つのアカウントを使い、その間の往復を確認します。

| | | |
| --- | --- | --- |
| 登録者がアイテムを承認に回す | → | 承認者に `Offer` + `EndorsementAction` が届く |
| 承認者がそれを承認する | → | 登録者に `Announce` + `EndorsementAction` が届く |

どちらも利用者と同じ読み方（当人として `GET /api/notifications`）で取得し、
さらに Inbox から本体を取ってきて中身を 1 項目ずつ確認します（`@context`、
`urn:uuid:` の id、宛先、対象アイテム、どのアクティビティのものか）。
あわせて、サイトが Inbox を広告していること（トップページへの HEAD に対する
`Link: rel="ldp#inbox"`）、未ログインの閲覧者には他人の通知ではなく 401 が
返ること、利用者に通知方法を選ぶ画面があることも確認します。

```bash
../.venv-e2e/bin/python -m pytest --suite coarnotify
../.venv-e2e/bin/python ./e2ectl inbox --run <実行 ID>   # 何が通知されたか
```

`install.sh` の構成なら設定は不要です。`scripts/instance.cfg` で
`WEKO_NOTIFICATIONS` が有効になっており、承認依頼の宛先である
リポジトリ管理者は `repoadmin@example.org` です。承認役が別のアカウントの
環境では `WEKO_E2E_APPROVER_EMAIL` と `WEKO_E2E_APPROVER_PASSWORD` を
指定してください（雛形は `environments/coar-notify.env`）。

通知は WEKO の DB ではなく Inbox 側の DB にあるため、WEKO の DB を初期状態に
戻しても残ります。`clean --hard` はその実行が出した通知を `inbox` コンテナ
から併せて削除します。

#### Web Push

通知は Web Push で利用者に届けることもできます。WEKO の担当は、購読・
ユーザープロファイル・メッセージテンプレートを Inbox に登録するところまでで、
通知を購読鍵で暗号化して配送するのは Inbox です。スイートはその全体を確認
します。Push が届き、復号でき、`push.json` の文面がこのアイテムと承認者で
展開されていること。

これを実際に行うには 2 つ障害があり、`e2ectl webpush-stub` が両方を片付け
ます。本物の購読はブラウザの Push サービス（Google / Mozilla）から取るもので、
ローカル環境からは到達できません。また配布時の compose ファイルは Inbox の
VAPID 鍵を空にしているため、そもそも署名ができません。

```bash
../.venv-e2e/bin/python ./e2ectl webpush-stub enable   # 鍵・作り直し・代替
../.venv-e2e/bin/python -m pytest --suite coarnotify
../.venv-e2e/bin/python ./e2ectl webpush-stub disable  # すべて元に戻す
```

`enable` は VAPID 鍵を生成し、WEKO チェックアウトの compose ファイルへ
マーカ付きで書き込み（鍵は WEKO ではなく `inbox` サービスのものなので
`instance.cfg` ではありません）、Inbox を作り直して読み込ませ、
`weko_e2e/pushstub.py` をそのコンテナのループバックで起動します。代替側は
自前の購読鍵を持ち、通知設定画面が本物の購読を登録するのと同じ手順で Inbox
に登録し、届いたものを復号します。`disable` はブロックを外して元の行を戻し、
`status` は現状を表示、`start` / `stop` はプロセスだけを操作します。

代替を動かしていない環境では、Web Push の 4 ステップが理由と有効化方法つきで
skip されます（Crossref の deposit と同じ扱いです）。

### `crossref` スイート

付与の確認だけなら事前準備は不要です。`/admin/identifier/` で Crossref 付与を
有効にし、プレフィックスを `WEKO_E2E_CROSSREF_PREFIX`（既定は Crossref の
例示用 `10.5555`）に設定し、**終了時に元の設定へ戻します**（成功・失敗に
かかわらず。戻ったことも検証します）。

```bash
../.venv-e2e/bin/python -m pytest --suite crossref
```

#### Crossref への登録（deposit）

WEKO は先にローカルで DOI を付与し、その後 worker が Crossref へ deposit
します。アカウントを設定した環境では、このスイートがその deposit の完了まで
待って結果を確認します。アカウントが無い環境では最後の 2 ステップが skip され
ます（仕様どおりの挙動であり、失敗ではありません）。

認証情報はインスタンス設定です（管理画面はありません）。ツールが書き込みます。

```bash
# 環境ファイル、または環境変数で:
WEKO_E2E_CROSSREF_DEPOSIT=1
WEKO_E2E_CROSSREF_LOGIN_ID=you@example.org/role
WEKO_E2E_CROSSREF_LOGIN_PASSWD=...
WEKO_E2E_CROSSREF_DEPOSITOR_EMAIL=you@example.org
WEKO_E2E_CROSSREF_PREFIX=10.80000        # そのアカウントで使えるプレフィックス

../.venv-e2e/bin/python ./e2ectl crossref-account enable   # 書き込み + 再起動
../.venv-e2e/bin/python -m pytest --suite crossref
../.venv-e2e/bin/python ./e2ectl crossref-account disable  # 元に戻す
```

登録先は **Crossref のサンドボックス**
`https://test.crossref.org/servlet/deposit`（WEKO の既定値）です。変更する
場合は `WEKO_E2E_CROSSREF_DEPOSIT_URL` と
`WEKO_E2E_CROSSREF_SUBMISSION_LOG_URL` を指定します。deposit を有効にすると
プレフィックスはそのアカウントが登録できるものである必要があるため、
`10.5555` のままでは通りません。

`enable` は `ark-stub` と同じく WEKO チェックアウトの `scripts/instance.cfg`
にマーカ付きブロックを追記して `web` と `worker` を再起動し、`disable` はその
ブロックだけを取り除きます。`status` で現在の状態、`e2ectl doi-log` で WEKO が
送った deposit の一覧を確認できます。

deposit の状態は web コンテナ内の `doi_deposit_log` から読むので、この 2
ステップには WEKO チェックアウトが必要です（無ければ skip）。Crossref に
拒否された場合は、Crossref が返した理由を添えて失敗します。

## 基本テストが行うこと

| ステップ | 内容 |
| --- | --- |
| 01 | システム管理者でログイン |
| 02 | テスト用インデックスを作成し、公開状態にする |
| 03 | テスト用フローを定義する（Start / Item Registration / Item Link / Identifier Grant / Approval / End） |
| 04 | テスト用ワークフローを定義する（デフォルトアイテムタイプ（フル） + 上記フロー） |
| 05 | そのワークフローでアクティビティを開始する |
| 06 | ファイルを添付し、必須メタデータ（公開日・タイトル・資源タイプ）を入力する |
| 07 | インデックスを指定する |
| 08 | アイテムリンクは指定せず次へ |
| 09 | 識別子は付与しない（Not Grant）で次へ |
| 10 | 承認する = ここでアイテムが登録・公開される |
| 11 | アイテムが登録され、タイトルが表示される |
| 12 | 未ログインの利用者からもアイテムが見える（= 公開されている） |
| 13 | 検索がそのインデックス配下にアイテムを見つける（ワーカーと Elasticsearch の確認） |

実環境での確認事項:

- インデックスは新規作成した時点では**非公開**なので、02 で公開状態にして
  います。これをしないと 12（未ログインからの閲覧）が失敗します。
- ワークフローにインデックスを設定する（`create_workflow(index_id=...)`）と、
  アイテム登録時にそのインデックスが自動指定され、**07 のインデックス指定画面
  がスキップされます**。基本テストは既定のワークフロー（index は未設定）に
  合わせ、画面で指定する形にしています。
- 所要時間は環境によって 13 ステップで約 60〜110 秒です。

## 後始末（テストツール）

実行したものは既定では**消さずに残します**（失敗時に画面を確認できるように）。
消すときは `e2ectl` に指示します。

```bash
cd e2e

# 何が残っているか
../.venv-e2e/bin/python ./e2ectl status

# 台帳にあるものを全部消す（画面と同じ削除 API を使う）
../.venv-e2e/bin/python ./e2ectl clean

# 実行 ID を指定して消す
../.venv-e2e/bin/python ./e2ectl clean --run 20260916-120000

# 何を消すかだけ見る
../.venv-e2e/bin/python ./e2ectl clean --dry-run

# WEKO が論理削除しかしない行まで物理的に消す（web コンテナで purge を実行）
../.venv-e2e/bin/python ./e2ectl clean --hard

# 台帳が失われた場合: 名前（ラベルで始まるもの）から探して消す
../.venv-e2e/bin/python ./e2ectl clean --discover --hard
```

WEKO の削除はインデックス・ワークフロー・フロー・アイテムいずれも論理削除
（行は残り、画面から消えるだけ）です。画面上きれいになれば十分なら `clean`、
`install.sh` 直後の状態に戻したいなら `--hard` を使ってください。

docker が要るのは `--hard` だけです。`weko_e2e/purge.py` を web コンテナに
コピーして `invenio shell` で実行し、あわせて `weko_e2e/inboxpurge.py` を
inbox コンテナにコピーして、その実行が出した COAR Notify の通知を Inbox 側の
DB から消すため、compose ファイルを持つ WEKO のチェックアウトが必要に
なります。このリポジトリの隣にあって `wekov2` /
`weko3` / `weko` という名前なら自動で見つけます。それ以外は `WEKO_E2E_REPO`
を指定してください。見つかったかどうかは `e2ectl ping` が表示します。
テスト実行・`clean`・`status` は docker のないリモート環境でも動きます。

`--hard` はワークフローからそのアクティビティを、アクティビティからその下書き
アイテムを辿って消します。アクティビティ一覧画面は既定ではアクティビティ ID の
列を表示しないため HTTP からは見つけられず、途中で失敗した実行が残した下書きを
確実に消せるのは `--hard` です。

テスト実行と同時に消したい場合は pytest 側から指示できます。

```bash
../.venv-e2e/bin/python -m pytest --clean-after          # 終了時に clean
../.venv-e2e/bin/python -m pytest --clean-after --clean-hard
```

## 設定（環境変数）

いずれも環境ファイルに 1 行として書けます。

### 対象環境

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_BASE_URL` | `https://localhost` | 対象の WEKO |
| `WEKO_E2E_HOST_IP` | （空） | そのホスト名の送り先アドレス。ブラウザと HTTP クライアントの両方に効く |
| `WEKO_HOST_MAP` | （空） | chromium の host resolver ルールを直接指定（例 `MAP weko3.example.org 127.0.0.1`）。`WEKO_E2E_HOST_IP` より優先 |
| `WEKO_E2E_VERIFY_TLS` | オフ | 証明書を検証する。正式な証明書の環境ではオンに |

### アカウント

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_TEST_EMAIL` | `wekosoftware@nii.ac.jp` | システム管理者 |
| `WEKO_TEST_PASSWORD` | `uspass123` | |
| `WEKO_E2E_APPROVER_EMAIL` | `repoadmin@example.org` | `coarnotify` で承認役になる別のアカウント |
| `WEKO_E2E_APPROVER_PASSWORD` | `uspass123` | |

### 作成するもの

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_E2E_LABEL` | `E2E` | 作成物の名前の接頭辞。`--discover` はこれで探す。共有環境では人ごとに変える |
| `WEKO_E2E_ITEM_TYPE` | `デフォルトアイテムタイプ（フル）` | 登録に使うアイテムタイプ |
| `WEKO_E2E_RUN_ID` | 実行時刻 | 1 回の実行に付く ID。作成物の名前に入る |
| `WEKO_E2E_STATE` | `e2e/.e2e-state.json` | 台帳の場所 |

### 待ち時間

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_E2E_TIMEOUT` | `60000` | ブラウザ操作 1 回のミリ秒 |
| `WEKO_E2E_STEP_TIMEOUT` | `300` | ワークフローのステップ遷移を待つ秒数 |
| `WEKO_E2E_UPLOAD_TIMEOUT` | `180` | ファイルアップロードを待つ秒数 |
| `WEKO_E2E_SEARCH_TIMEOUT` | `180` | Elasticsearch への反映を待つ秒数 |

### オプションスイート

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_E2E_SUITES` | （なし） | 実行するオプション: `ark` / `coarnotify` / `crossref`、カンマ区切り、または `all` |
| `WEKO_E2E_CROSSREF_PREFIX` | `10.5555` | `crossref` が設定し、期待するプレフィックス |
| `WEKO_E2E_ARK_NAAN` | （空） | 発行に使い、`ark` が期待する NAAN |
| `WEKO_E2E_NOTIFY_TIMEOUT` | `120` | `coarnotify` が通知の到着を待つ秒数 |

### ARK サーバ（発行用）

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_E2E_ARK_MINT_URL` | （空） | 払い出しエンドポイント |
| `WEKO_E2E_ARK_NAAN` | （空） | 払い出しに使う NAAN |
| `WEKO_E2E_ARK_SHOULDER` | （空） | 払い出しに使う shoulder |
| `WEKO_E2E_ARK_API_KEY` | （空） | API key。設定するとログイン手順を省略 |
| `WEKO_E2E_ARK_API_KEY_HEADER` | `Authorization` | API key を載せるヘッダ名 |
| `WEKO_E2E_ARK_API_KEY_PREFIX` | `Bearer ` | API key の前置詞。空で生のキー |
| `WEKO_E2E_ARK_LOGIN_URL` | （空） | API key が無いときの認証先 |
| `WEKO_E2E_ARK_LOGIN_USER` | （空） | |
| `WEKO_E2E_ARK_LOGIN_PASSWD` | （空） | |
| `WEKO_E2E_ARK_TIMEOUT` | `30` | ARK サーバへのタイムアウト秒 |

これらは `e2ectl ark-account enable` がインスタンスに書き込みます。
変数を設定しただけでは環境は変わりません。

### Crossref アカウント（deposit 用）

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_E2E_CROSSREF_DEPOSIT` | オフ | deposit の完了まで待って結果を確認する |
| `WEKO_E2E_CROSSREF_LOGIN_ID` | （空） | Crossref のログイン ID。ロール付きなら `user@example.org/role` |
| `WEKO_E2E_CROSSREF_LOGIN_PASSWD` | （空） | |
| `WEKO_E2E_CROSSREF_DEPOSITOR_EMAIL` | （空） | Crossref が結果を送る宛先 |
| `WEKO_E2E_CROSSREF_DEPOSITOR_NAME` | `WEKO E2E` | |
| `WEKO_E2E_CROSSREF_REGISTRANT` | `WEKO E2E` | |
| `WEKO_E2E_CROSSREF_DEPOSIT_URL` | `https://test.crossref.org/servlet/deposit` | サンドボックス |
| `WEKO_E2E_CROSSREF_SUBMISSION_LOG_URL` | `https://test.crossref.org/servlet/submissionDownload` | 結果の取得先 |
| `WEKO_E2E_CROSSREF_DEPOSIT_TIMEOUT` | `600` | Crossref の応答を待つ秒数 |

これらは `e2ectl crossref-account enable` がインスタンスに書き込みます。
変数を設定しただけでは環境は変わりません。

### `clean --hard` でのみ使う

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_E2E_REPO` | 自動検出 | compose ファイルを持つ WEKO のチェックアウト |
| `WEKO_E2E_COMPOSE_FILE` | `docker-compose2.yml` | |
| `WEKO_E2E_WEB_SERVICE` | `web` | WEKO が動く compose サービス名 |
| `WEKO_E2E_INBOX_SERVICE` | `inbox` | LDN Inbox が動く compose サービス名。実行の通知を消す先であり、Web Push 代替の動作場所 |
| `WEKO_E2E_CONTAINER_REPO` | `/code` | そのコンテナ内でのチェックアウトのパス |

### その他

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `WEKO_E2E_ENV` | あれば `e2e/e2e.env` | 読み込む環境ファイル |
| `WEKO_HEADED` | オフ | ブラウザを表示する |

## 実際に流した環境

| | 結果 |
| --- | --- |
| `https://localhost`（`install.sh` の手元 docker 環境） | 13 passed |
| `https://weko3.example.org`（DNS 登録なし、`WEKO_E2E_HOST_IP=127.0.0.1`） | 13 passed |
| 同上、別のシステム管理者アカウントで | 13 passed |
| 4 スイート同時実行（`--suite all`、ARK スタブ使用） | 37 passed |
| `crossref` + deposit 有効（Crossref 代替スタブ宛て） | 10 passed、deposit が `success` に到達 |
| `ark` + `ark-account`（ログイン方式）で設定したサーバ宛て | 6 passed、`ark:/12345/x9...` を発行 |
| `coarnotify`（環境付属の `inbox` サービス宛て） | 10 passed、2 通ともそれぞれ正しい相手に到達 |

## 派生版の作り方

基本テストは「準備（02〜04）」と「流れ（05〜13）」に分かれていて、準備は
`weko_e2e.client`、流れは `weko_e2e.ui` の部品でできています。派生版は
`tests/` にファイルを足し、変えたいところだけ変えてください。

- **別のアイテムタイプ** — `WEKO_E2E_ITEM_TYPE` を変える。メタデータ欄の
  コントロール名はアイテムタイプ ID を含むので、`test_basic_publish.py` の
  `_title_field()` 等にあたる部分を書き換える
- **フローを変える** — `client.create_flow(name, actions=[...])` に渡す
  アクション名の並びを変える（`Start` と `End` は必須）
- **識別子を付与する** — `flow.choose_identifier_grant(page, settings,
  value=...)`（`0` 付与しない / `1` JaLC DOI / `2` Crossref DOI /
  `3` DataCite DOI）。`tests/test_crossref_doi.py` が実例（付与の有効化と
  設定の復元まで含む）
- **新しいオプションスイートを足す** — モジュールに
  `pytestmark = pytest.mark.suite('名前')` を付け、`weko_e2e/config.py` の
  `OPTIONAL_SUITES` に名前を追加し、`weko_e2e.flow` の部品で組む。作成物の
  名前はスイートごとに自動で分かれます
- **公開範囲を変える** — 02 の `client.create_index(..., public=False)` に
  して、12 の期待を反転させる
- **インデックスの自動指定を使う** — 04 で `index_id=flow_state['index_id']`
  を渡す。07 のインデックス指定画面が出なくなるので、07 は削除し、06 の
  `wait_for_index_tree()` も外す

作ったものは必ず `record(kind, id, name)` で台帳に記録してください。`e2ectl`
が消せるのは台帳にあるもの（と `--discover` で見つかるもの）だけです。

## うまく動かないとき

- **想定と違う動きをする** — まず `./e2ectl env`。たいていは設定が思っている
  のと別の場所を指しています
- **`e2ectl ping` が「does not answer」** — 手元の環境なら
  `docker compose -f docker-compose2.yml ps` でコンテナを確認する。DNS で
  引けないホスト名なら `WEKO_E2E_HOST_IP` を指定する
- **ログインはできるがアイテムタイプが NOT FOUND** — その環境には別の
  アイテムタイプがある。`ping` が一覧を出すので `WEKO_E2E_ITEM_TYPE` を
  合わせる
- **アイテム登録の Next で止まる / ファイルアップロードが 500** —
  過去にあった例として、`user_activity_logs` は月ごとのパーティションなので
  当月分がないとログを書く全リクエストが失敗する。作成する:
  ```sql
  CREATE TABLE user_activity_logs_YYYYMM PARTITION OF user_activity_logs
      FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-MM+1-01');
  ```
- **13 だけ失敗する** — worker が動いていないか、`WEKO_E2E_SEARCH_TIMEOUT`
  より遅い環境
- **リモート環境でタイムアウトする** — `WEKO_E2E_TIMEOUT` と
  `WEKO_E2E_STEP_TIMEOUT` を上げる。`environments/fqdn.env` に出発点になる
  値があります
- **前の実行のアクティビティが残っていて開始できない** — 05 は開いたままの
  アクティビティを自動で quit するが、消したいときは
  `./e2ectl clean --discover`
- **`ark` で「no ARK」と言われる** — 環境が ARK 未設定か、mint に失敗して
  いる。`./e2ectl ark-account status`（またはスタブなら `ark-stub status`）と
  web のログを確認する。WEKO は mint 失敗の理由をログに出し、アイテム登録自体
  は続行します
- **`coarnotify` で「承認者に何も届いていない」と言われる** — `inbox`
  コンテナが起動していない（`docker compose -f docker-compose2.yml ps
  inbox`）、`scripts/instance.cfg` の `WEKO_NOTIFICATIONS` が無効、または
  承認役として指定したアカウントがその環境の承認依頼の宛先ではない。
  `./e2ectl inbox` で各アカウントに何が届いているか確認できます
- **`coarnotify` で承認者に承認画面が出ないと言われる** — そのアカウントに
  承認権限がないか、前の実行で開いたままのアクティビティを掴んでいる。
  掴み直しはスイート側で解除しますが、アクティビティ自体は
  `./e2ectl clean --discover` で消せます
- **Web Push のステップが skip される** — 代替が動いていない。
  `./e2ectl webpush-stub enable` で用意でき、`./e2ectl webpush-stub status`
  で現状を確認できます。代替は `inbox` コンテナ内で動くため、WEKO
  チェックアウトが見つからない環境でも skip されます
- **承認通知は届くが Push が来ない** — Inbox はバックグラウンドタスクで送信し、
  失敗はログにしか出しません（`docker compose -f docker-compose2.yml logs
  inbox`）。1 通の Push には購読・同じ URI のユーザープロファイル・通知の
  `type` に一致するテンプレートの 3 つが要ります。前 2 つは代替が登録し、
  3 つ目は WEKO が起動時に `push.json` から登録するので、`push.json` を
  変更したあと再起動していない環境では古い文面のままです
- **`crossref` で付与が提示されないと言われる** — 識別子設定の保存に失敗して
  いる。`/admin/identifier/` を開いて確認する
- **deposit のステップが skip される** — `WEKO_E2E_CROSSREF_DEPOSIT` がオフ、
  または WEKO チェックアウトが見つかっていない。`./e2ectl env` で確認する
- **deposit が記録されていないと言われる** — アカウントがインスタンス設定に
  入っていない。`./e2ectl crossref-account status` と worker の稼働を確認する
- **Crossref に拒否される** — 失敗メッセージに Crossref の返答が出ます。
  そのアカウントで使えないプレフィックスが典型的な原因です。
  `./e2ectl doi-log` で deposit 一覧とエラーを確認できます

## 実行記録

[`evidence/README.ja.md`](evidence/README.ja.md) が実行全体・基本スイート・
後始末です。オプションスイートはそれぞれ専用の記録を持ち、その記録が使う
画像も隣にあります。

```
evidence/
├── README.md, README.ja.md      実行全体と基本スイート
├── images/                      基本スイートの画像
├── ark/README.ja.md, images/    ark スイートとその画像
├── coarnotify/README.ja.md, …
└── crossref/README.ja.md, …
```

画像はテスト自身が固定の名前で撮るので、スイートを再実行すればそのスイートの
フォルダだけが撮り直され、記録が実装から乖離しません。
