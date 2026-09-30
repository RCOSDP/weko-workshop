# E2E テスト実行記録: `shibboleth` スイート

English: [`README.md`](README.md) ·
この実行全体: [`../README.ja.md`](../README.ja.md)

Shibboleth ユーザがログインし、WEKO が作るアカウントが `eppn` ではなく
`mail` から作られることを確認します。IdP は使いません。既存のアカウントには
一切触れません。

スイート本体は
[`../../tests/test_shibboleth.py`](../../tests/test_shibboleth.py)、
画像は [`images/`](images) にあり、各ステップが自分で撮ったものです。

| | |
| --- | --- |
| 実行 ID | `20260930-234316` |
| 結果 | **9 passed** |
| 有効化 | `--suite shibboleth` |

---

## なぜ IdP が要らないのか

SAML を話すのは WEKO ではなく SP（nginx 側）です。WEKO に届くのは、IdP が
返した属性を普通に POST したものだけで、それを作っているのが
`nginx/login.py` です。

```python
# nginx コンテナ内の nginx/login.py
base_url = os.environ['REQUEST_SCHEME'] + '://' + os.environ['HTTP_HOST']
requests.post(base_url + '/weko/shib/login?next=' + next_url, data=attrs)
```

したがって IdP は不要です。`weko_e2e/shibstub.py` を **nginx コンテナ**に
コピーし、このスクリプトと同じものを、同じ場所から送ります。

**肝心なのは「どこから POST したか」です。** `release_v2.1.0` では
`POST /weko/shib/login` が `WEKO_ACCOUNTS_SHIB_SP_ALLOWED_ADDRS` 以外から
拒否されます。

```python
@shib_sp_source_required
def shib_sp_login():
    ...
```

SP と同じ場所に立つことが、このスイートがその検査の内側に留まる方法です。
**このスイートはそのリストを広げません。** どこからでもこの属性を受け付ける
環境は、誰でも誰にでもなりすませる環境です。

### 代役が送るもの（test_01, test_03）

```console
$ ./e2ectl shib login
posted as e2e-shibboleth@example.org (mail e2e-shibboleth-mail@example.org)
WEKO answered 200
follow /weko/shib/login?Shib-Session-ID=_4262e5a1fb8c41cba73d67b5fa16d44e&next=%2F to take the session
```

`eppn` と `mail` を**意図的に別の値**にしてあります。これによって、どちらが
使われたかを「決めつけず」に確認できます。

WEKO が返すのはリダイレクトではなくパスです（リダイレクトにするのは SP の
スクリプトの仕事）。セッションになるのは、それを*たどった側*です。WEKO が
知らない ID は確認画面に飛ばされ、ステップはそこを確認します。

---

## 確認画面の 2 つの道と、片方しか通らない理由（test_04）

![確認画面](images/01-confirm-account.png)

| | |
| --- | --- |
| **Login as new ID** | 属性から新しいアカウントを作る |
| **Login as registerd ID** | 指定したアカウントに紐付け、**そのアカウントのメールアドレスを上書きする** |

後者は想像の話ではありません。

```python
# weko_accounts/api.py, ShibUser.bind_relation_info
with db.session.begin_nested():
    self.user.email = self.shib_attr['shib_mail']
```

`wekosoftware@nii.ac.jp` を Shibboleth ID に紐付ければ、そのアカウントの
名前は IdP が返した値に変わり、以後ログイン画面からは入れなくなります。
そのためスイートは新規ユーザの道だけを通り、このステップは「両方の道が
提示されていること」だけを確認します。

### 新規ユーザはそのままログイン状態になる（test_05）

![Shibboleth ユーザとしてログインした状態](images/02-logged-in.png)

---

## どの属性がアカウントになったか（test_06, test_07）

```console
$ psql -c "SELECT s.shib_eppn, u.email FROM shibboleth_user s
           JOIN accounts_user u ON u.id = s.weko_uid"
     e2e-shibboleth@example.org | e2e-shibboleth-mail@example.org
```

`eppn` は紐付けに、`mail` はアカウントになりました。プロフィール画面
（利用者自身のアカウントだけを表示する唯一の画面）から読み戻したもの：

![WEKO が作ったアカウントのプロフィール](images/03-profile.png)

この画面に `eppn` はどこにも出てきません。`Username` は IdP が返した
`DisplayName`、`Email address` は `mail` です。

**ここがテストする価値のある部分です。** `eppn` だけを返して `mail` を返さない
IdP や、リポジトリが把握している宛先とは違う `mail` を返す IdP では、誰も
予期しない名前のアカウントができます。しかもリポジトリ側には、それが
起きていることを見せてくれる画面がありません。

### 既知の ID は確認画面を経ずに入る（test_08）

2 回目のログインでは確認画面ではなく `/weko/auto/login` が返ります。WEKO が
紐付けを見つけ、尋ねることが無くなったからです。

### 誰も発行していないセッション ID では入れない（test_09）

SP が利用者を飛ばす先の URL にはセッション ID が載っています。これが安全なのは
「その ID は WEKO が受け入れた POST でしかキャッシュされない」からであり、
その POST を守っているのが送信元アドレスの検査です。このステップは適当な ID を
使ってみて、結果が依然として未ログインであることを確認します。

---

## 実行後に残るもの

何も残りません。

```console
$ ./e2ectl shib status
shibboleth login: off
e2e-shibboleth@example.org: nothing bound
```

スイート自身が `/admin/shibboleth/` で Shibboleth ログインを有効化し、元の
状態に戻します。作ったアカウントも最後に削除します。どちらも fixture の
後始末で行うため、成功・失敗にかかわらず実行されます。

なお、この画面はスイッチ・既定ロール・属性マッピング・ブロックユーザを
**まとめて**保存し、後ろの 3 つはページではなくブラウザ側で組み立てられます。
そのためスイッチだけを送る保存は、残りを空のまま WEKO に届き、**それらを
消してしまいます**。`shib_login_enabled()` は画面が保持している値をすべて
そのまま送り返し、スイッチだけを変更します。
