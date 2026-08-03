# Shibboleth IdP を立てて WEKO3 にログインする（arm64 / k8s-weko）

kind クラスタの中に **本物の Shibboleth Identity Provider（IdP 5.2.3）** を立て、WEKO3 の
Shibboleth ログイン（学認相当の経路）を外部依存なしで動かすための手順。

```bash
WEKO_SHIB=yes bash deploy-arm64.sh
# 動作確認（ブラウザの代わりに一通りたどる）
python3 check-shib-login.py
```

ログイン入口は `https://<tenant>.localhost/weko/shib/sp/login`。
`/login` 自体を IdP に飛ばしたい場合は `WEKO_SHIB_LOGIN_ONLY=yes`（後述、既定は `no`）。

| デモユーザ | パスワード | wekoSocietyAffiliation | WEKO ロール |
|---|---|---|---|
| `admin` | `admin123` | 管理者 | System Administrator |
| `libadmin` | `libadmin123` | 図書館員 | Repository Administrator |
| `teacher` | `teacher123` | 教員 | Contributor |
| `commadmin` | `commadmin123` | 教員 | Contributor + **Community Administrator** |

`commadmin` だけロールが 2 つ付く。`WEKO_ACCOUNTS_SHIB_ROLE_RELATION` は 管理者/図書館員/教員/教官 の
4 語しか持たず Community Administrator を返す語が無いので、このロールは学認mAP のグループ
（`jc_<FQDN>_ro_cadm`）経由でしか付かない。`WEKO_SHIB_MAP=no` のときは `commadmin` は Contributor
だけになる。

メールアドレスは `<ログインID>@example.org`（IdP の `idp.scope`）になる。`tenants.txt` の管理者が
`admin@example.org` なので、`admin` でログインすると既定のテナント管理者とそのまま結び付く。

---

## なぜ自前ビルドなのか

Docker Hub にある既製の Shibboleth IdP イメージ（`unicon/shibboleth-idp`、`i2incommon/shib-idp`、
`tier/shib-idp`）は**すべて amd64 専用**で、arm64 のホストでは動かない。一方 IdP 本体は純 Java の
tarball で配布されておりアーキテクチャ非依存なので、`shib-idp-build/Dockerfile` で
**公式 tarball + Tomcat 10.1（マルチアーキ）** から組み立てている。arm64 でも amd64 でもネイティブに通る。

> IdP 5 は `jakarta.servlet` なので **Tomcat 10.1 以上**が必要（Tomcat 9 は `javax` で動かない）。
> また `/idp/status` だけは Velocity ではなく JSP で描画されるため、Jetty と違って JSTL を同梱しない
> Tomcat では JSTL の jar を 2 つ足さないと 500 になる（Dockerfile で Maven Central から入れている）。
> ログイン画面自体は Velocity なので、この jar が要るのは `/idp/status` だけ。

認証はディレクトリサーバを使わず、IdP 5 標準の `shibboleth.HTPasswdValidator` で htpasswd ファイルを
読ませている（`shib-idp-build/idp-conf/credentials/demo.htpasswd`）。
`HTPasswdCredentialValidator` が解釈できるのは `$apr1$` / `{SHA}` / `crypt(3)` だけで
**bcrypt は非対応**なので、ユーザを足すときは `htpasswd -nbm` で作ること。

---

## 全体の流れ

```
ブラウザ                nginx + shibd (SP)              WEKO3 (uwsgi)            IdP
   |                          |                             |                    |
   |  /weko/shib/sp/login     |                             |                    |
   |------------------------->|---------------------------->|                    |
   |            302 /secure/login.py?next=/                  |                    |
   |<--------------------------------------------------------|                   |
   |  /secure/login.py        |                             |                    |
   |------------------------->| shib_request /shibauthorizer|                    |
   |            302 /idp/profile/SAML2/Redirect/SSO?SAMLRequest=...               |
   |<-------------------------|                             |                    |
   |  ログインフォーム                                                            |
   |----------------------------------------------------------------------------->|
   |  SAMLResponse の自動 POST フォーム                                            |
   |<-----------------------------------------------------------------------------|
   |  POST /Shibboleth.sso/SAML2/POST                                             |
   |------------------------->| shibd がアサーションを検証しセッション確立         |
   |            302 /secure/login.py?next=/                  |                    |
   |<-------------------------|                             |                    |
   |  /secure/login.py（属性つき）                          |                    |
   |------------------------->| login.py が属性を集めて      |                    |
   |                          | POST /weko/shib/login ------>|                    |
   |            302 /weko/shib/login?Shib-Session-ID=...     |                    |
   |<-------------------------|                             |                    |
   |  WEKO アカウント紐付け画面 -> ログイン完了              |                    |
```

初回ログインでは **WEKO アカウントとの紐付け画面**が出る。
- 既存の WEKO アカウントに紐付ける → メールアドレスとパスワードを入力
- 新規 WEKO ユーザを作る → 「Login (New WEKO users)」

2 回目以降はこの画面を経ずにそのままログインする。

---

## 構成要素

| ファイル | 役割 |
|---|---|
| `shib-idp-build/Dockerfile` | IdP イメージ（公式 tarball を無人インストール → Tomcat 10.1 に載せる） |
| `shib-idp-build/idp-conf/` | IdP の設定オーバーレイ（認証方式・属性定義・公開ポリシー・メタデータ参照） |
| `70-shibboleth-idp.yaml` | 機関 IdP の Deployment / Service / Ingress（`idp.localhost`） |
| `71-shibboleth-map.yaml` | 学認mAP 相当の属性認証局（`map.localhost`）。`WEKO_SHIB_MAP=aggregation` のときだけ使う |
| `provision-shib.sh` | SP 鍵の生成、IdP / 属性認証局メタデータの取り出し、SP メタデータの登録、NFS への配置 |
| `shib-sp-template/shibboleth2.xml` | SP（shibd）の設定テンプレート。テナントごとに FQDN を差し込む |
| `shib-sp-template/attribute-map-weko.xml` | WEKO 独自属性（`wekoId` / `wekoSocietyAffiliation`）の SP 側マッピング |
| `shib-sp-template/simple-aggregation.xml` | SimpleAggregation のブロック（`aggregation` のときだけ差し込まれる） |
| `shib-sp-template/map-metadata-provider.xml` | 属性認証局のメタデータを読む `<MetadataProvider>`（同上） |
| `21-nginx-config.yaml` の `default-shib.conf` | `shibauthorizer` / `/secure/login.py` / `/weko/shib` を含む nginx 設定 |

### 信頼関係の張り方

フェデレーションのメタデータ配信は使わず、**ローカルファイルだけで完結**させている。

- **SP → IdP**：`provision-shib.sh` が IdP イメージから `idp-metadata.xml` を取り出し、各テナントの
  `/fs-shibboleth/<tenant>/` に置く。イメージから取るので IdP の署名鍵と必ず一致する。
- **IdP → SP**：`tenants.txt` の全テナント分の SP メタデータを 1 つの `EntitiesDescriptor` にまとめ、
  ConfigMap `weko-idp-sp-metadata` として IdP にマウントする。
- **SP の鍵**：`provision-shib.sh` が `.shib-sp/` に 1 組だけ作り、以後は再利用する
  （`.gitignore` 済み。消すと信頼関係を張り直すことになる）。

IdP イメージを作り直すと署名鍵が変わるので、**`provision-shib.sh` を必ず流し直す**こと。

### 属性の受け渡し

| IdP の属性 | SAML 属性名 | SP 側 id | WEKO での用途 |
|---|---|---|---|
| `eduPersonPrincipalName` | `urn:oid:1.3.6.1.4.1.5923.1.1.1.6` | `eppn` | `shib_eppn`（同一人物の判定キー） |
| `mail` | `urn:oid:0.9.2342.19200300.100.1.3` | `mail` | `shib_mail`（WEKO アカウントの照合） |
| `displayName` | `urn:oid:2.16.840.1.113730.3.1.241` | `displayName` | `shib_user_name` |
| `wekoSocietyAffiliation` | `urn:oid:1.3.6.1.4.1.32264.2.1.6` | `wekoSocietyAffiliation` | ロール決定（`WEKO_ACCOUNTS_SHIB_ROLE_RELATION`） |
| `wekoId` | `urn:oid:1.3.6.1.4.1.32264.2.1.1` | `wekoId` | `SHIB_ATTR_USER_NAME` |

ユーザごとの値は LDAP ではなく、ログイン ID から導出している
（`shib-idp-build/idp-conf/conf/attribute-resolver.xml`）。ロールは `Mapped` 属性定義で
`admin` → 管理者、`libadmin` → 図書館員、それ以外 → 教員（既定値）としている
（`commadmin` も既定値の教員）。
ユーザやロールを増やすときはこのファイルと `demo.htpasswd` の 2 つを直す。学認mAP のグループを
増やすときも同じファイルの `mapRoleGroup` / `mapOrgGroup` / `mapOrgAdminGroup` を直す。
いずれもイメージに焼き込まれるので、変更後は再ビルドが必要（`deploy-arm64.sh` のイメージビルド段）。

---

## `/login` の挙動を選ぶ（`WEKO_SHIB_LOGIN_ONLY`）

weko-accounts のログイン画面は `WEKO_ACCOUNTS_SHIB_INST_LOGIN_DIRECTLY_ENABLED` で 2 通りに分かれる。
`WEKO_SHIB_LOGIN_ONLY` はこのフラグを切り替えるだけのもの。

| | `no`（既定） | `yes` |
|---|---|---|
| `/login/` | ローカルのログインフォーム（＋学認 WAYF ウィジェット） | `<meta http-equiv="Refresh">` で `/secure/login.py` へ → IdP |
| Shibboleth の入口 | `/weko/shib/sp/login` | `/login/` でも `/weko/shib/sp/login` でも可 |
| WEKO のパスワードでのログイン | できる | **できない** |

```bash
WEKO_SHIB=yes WEKO_SHIB_LOGIN_ONLY=yes bash deploy-arm64.sh
```

instance.cfg のコメントでいう「パターン4: Shibbolth(Idp) のみ」に相当する。**ログイン自体は
どちらのモードでも同じように成功する**が、`yes` には以下の副作用がある（いずれも実機で確認済み）。

**1. IdP が停止するとブラウザから一切ログインできない。**
`/login/` にローカルフォームが出なくなるため、IdP を落とした状態では 503 しか返らない。
復旧は `kubectl exec` で `invenio.cfg` を書き換えるしかなくなる。

**2. ログアウトしても同じユーザで再ログインされる。**
WEKO のログアウトでは SP セッションクッキー（`_shibsession_*`）も IdP セッションも消えない。
その状態で `/login/` に行くと IdP を経由せずそのまま再ログインが成立するので、
別アカウントに切り替える手段がない。

**3. 失敗時のエラーメッセージが表示されない。**
weko-accounts の失敗系は `flash()` ＋ログイン画面へのリダイレクトで通知する設計
（`_redirect_method()`）。`yes` ではそのログイン画面が即リダイレクトなので flash が描画されない。
たとえば紐付け画面で WEKO のパスワードを間違えたとき:

| | 遷移先 | 画面の表示 |
|---|---|---|
| `no` | `/login/` | `check_weko_user` と表示される |
| `yes` | 同じ紐付け画面 | **何も出ずにフォームに戻るだけ** |

2 と 3 は「Shibboleth 専用」を選ぶ以上は本番でも同じ性質なので、バグというより運用上の割り切り。
ワークショップでは 1 の影響が大きいため既定を `no` にしている。

---

## 学認mAP 連携（`WEKO_SHIB_MAP`）

WEKO は `isMemberOf`（mAP のグループ所属）を見て WEKO ロールを決める。その `isMemberOf` を
どこから持ってくるかを `WEKO_SHIB_MAP` で選ぶ。

| | 内容 | 立つ Pod |
|---|---|---|
| `no`（既定） | 使わない | `weko-shib-idp` |
| `sso` | IdP が SSO アサーションに `isMemberOf` を載せる | `weko-shib-idp` |
| `aggregation` | **本番と同じ**。SP が SimpleAggregation で属性認証局に SAML2 AttributeQuery を投げる | `weko-shib-idp` + `weko-shib-map` |

```bash
WEKO_SHIB=yes WEKO_SHIB_MAP=aggregation bash deploy-arm64.sh
```

### なぜ属性認証局が別 Pod なのか

**SP は「既に属性を取得済みのエンティティ」への問い合わせを意図的にスキップする。** ログイン IdP 自身を
`<Entity>` に指定しても AttributeQuery は永久に発行されない。shibd のログで確認できる:

```
DEBUG SimpleAggregation: using input attribute (eppn) as identifier for queries
DEBUG SimpleAggregation: skipping previously queried attribute source (https://idp.localhost/idp/shibboleth)
```

本番が成立しているのは学認クラウドゲートウェイが機関 IdP とは別エンティティだからで、ここでも
`map.localhost` を別に立てている（`71-shibboleth-map.yaml`）。イメージは同じで ARG が違うだけ。

役割分担:

| | 配る属性 |
|---|---|
| `idp.localhost`（機関 IdP） | 認証 + `eppn` / `mail` / `displayName` / `wekoId` / `wekoSocietyAffiliation` |
| `map.localhost`（属性認証局） | `isMemberOf` のみ（AttributeQuery に応答） |

`aggregation` では機関 IdP が `isMemberOf` を SSO で配らない（`IDP_RELEASE_ISMEMBEROF=no` でビルド）ので、
SP のセッションに `isMemberOf` があれば AttributeQuery が成功した証拠になる。

### SP 側の設定（本番の手順と同じ形）

```xml
<MetadataProvider type="XML" validate="true" path="map-metadata.xml"/>

<AttributeResolver type="SimpleAggregation" attributeId="eppn"
                   format="urn:oid:1.3.6.1.4.1.5923.1.1.1.6">
    <Entity>https://map.localhost/idp/shibboleth</Entity>
    <saml2:Attribute xmlns:saml2="urn:oasis:names:tc:SAML:2.0:assertion"
                     Name="urn:oid:1.3.6.1.4.1.5923.1.5.1.1"
                     NameFormat="urn:oasis:names:tc:SAML:2.0:attrname-format:uri"
                     FriendlyName="isMemberOf"/>
</AttributeResolver>
```

`attribute-map.xml` の `isMemberOf` は**追加不要** — イメージ同梱のものに既に入っている。

### 動かすために必要だったこと（すべて実測で判明）

| 症状 | 原因と対処 |
|---|---|
| AttributeQuery が発行されない | ログイン IdP と同一エンティティだった → 別エンティティ（`map.localhost`）を立てる |
| `MessageAuthenticationError` | クエリが未署名 → SP の `<ApplicationDefaults signing="back">` でバックチャネルに署名させる |
| `Transport confidentiality required, but not available.` | 平文 HTTP を SP が拒否 → IdP 標準のバックチャネル（8443, `idp-backchannel.p12`）を Tomcat に追加 |
| `No peer encryption credential found` | メタデータに暗号化鍵が無い → `AttributeAuthorityDescriptor` に KeyDescriptor を 3 つとも入れる |
| TLS のホスト名が合わない | 証明書は `CN=map.localhost` → Service の ClusterIP を固定し、テナント Pod の `hostAliases` で `map.localhost` を向ける |
| `no MetadataProvider available` | `mktemp` の 0600 が `mv` で残り `_shibd` が読めない → 配置後に 0644 |

### WEKO 側で必要な設定

`gen-tenant.sh` が `invenio.cfg` に追記する。**`WEKO_ACCOUNTS_ATTRIBUTE_MAP` の上書きが要点**で、
既定のマップには `shib_is_member_of` が無く、その場合 `parse_attributes()` は
`SHIB_ATTR_IS_MEMBER_OF` というフィールド名を探すが、`login.py` が実際に送るのは
`isMemberOf`（`/etc/nginx/shib_fastcgi_params` 由来）なので**値が黙って捨てられる**。

```python
WEKO_ACCOUNTS_SHIB_BIND_GAKUNIN_MAP_GROUPS = True
WEKO_ACCOUNTS_IDP_ENTITY_ID = "https://idp.localhost/idp/shibboleth"
WEKO_ACCOUNTS_ATTRIBUTE_MAP = {..., "shib_is_member_of": "isMemberOf"}
```

### グループ名とロールの対応

`create_fqdn_from_entity_id()` が `WEKO_ACCOUNTS_IDP_ENTITY_ID` から FQDN（`idp.localhost` →
`idp_localhost`）を作り、グループ名の末尾セグメントと突き合わせる。属性認証局は自分ではなく
**機関 IdP の** FQDN をグループ名に埋める（`IDP_GROUP_FQDN_HOST`）。

| デモユーザ | isMemberOf | WEKO ロール |
|---|---|---|
| `admin` | `/gakunin/idp_localhost/jc_roles_sysadm` | System Administrator |
| `libadmin` | `/gakunin/idp_localhost/jc_idp_localhost_ro_radm` | Repository Administrator |
| `commadmin` | `/gakunin/idp_localhost/jc_idp_localhost_ro_cadm` | Community Administrator |
| `teacher` | `/gakunin/idp_localhost/jc_idp_localhost_ro_cont` | Contributor |

`WEKO_ACCOUNTS_GAKUNIN_GROUP_PATTERN_DICT` が解釈できる 4 種類すべてに、デモユーザを 1 人ずつ
割り当ててある。SimpleAggregation 経路をロール単位で切り分けて確かめられるようにするため。

ロール以外のグループも既定で入れてある。「どのユーザにどの値が返るか」を切り分けるためのもので、
`WEKO_ACCOUNTS_GAKUNIN_GROUP_PATTERN_DICT` のパターンには一致しない。

ただし**ロールがまったく増えないわけではない**。`_assign_roles_to_user()` は最後に
「グループ名と同名の Role が Role テーブルにあれば、それも付与する」という分岐を持つ。後述の
`sync_shib_gakunin_map_groups` で Redis のグループ一覧を投入すると、その一覧に載せた名前が
そのまま Role として自動作成されるため、以後は同名ロールが付く。逆に一覧に載せなければ
Role が存在せず、ロールは増えない。既定ではテスト用グループを一覧に入れていないので後者になる。

| グループ | 所属するデモユーザ | 用途 |
|---|---|---|
| `all_users` | 全員（Static データコネクタ） | 共通グループ |
| `research-project-a` | `libadmin`, `teacher` | 研究プロジェクト相当 |
| `research-project-a/admin` | `libadmin` | 管理者フレーバ（読み飛ばされる） |
| `lib-staff` | `libadmin` | 部署相当 |
| `test-group-1` | `admin`, `libadmin` | 複数ユーザが同じグループ |
| `test-group-1/admin` | `admin` | 管理者フレーバ（読み飛ばされる） |
| `test-group-2` | `teacher`, `commadmin` | 別の組み合わせ |
| `test-group-3` | `commadmin` | 単独所属 |

`/admin` で終わる値と `/sp/` を含む値は `_assign_roles_to_user()` が読み飛ばす。`admin` と `libadmin`
はメンバー値と管理者値の両方を受け取るので、その挙動をそのまま確認できる。

### ロール表の同期（`sync_shib_gakunin_map_groups`）

mAP のグループ一覧は Redis DB 4 のハッシュ `<FQDN>_gakunin_groups` から読まれ、`jc_*` ロールが
自動作成・削除される。weko-accounts 自身は書き込まないので（本番では別のバッチが入れる）、
手で投入して動かせる。

```bash
kubectl exec -n weko3re redis-0 -- redis-cli -n 4 hset idp_localhost_gakunin_groups \
  groups "jc_idp_localhost_ro_radm,jc_idp_localhost_ro_cadm,jc_idp_localhost_ro_cont,jc_roles_sysadm"
```

投入後にログインすると、パターン一致によるロールに加えてグループ名そのもののロールも付く:

```
admin@example.org    | jc_roles_sysadm, System Administrator
libadmin@example.org | jc_idp_localhost_ro_radm, Repository Administrator
```

### 確認

```bash
# 属性認証局に AttributeQuery が届いたか
kubectl -n weko3 exec deploy/weko-shib-map -- \
  grep "Shibboleth-Audit.AttributeQuery" /opt/shibboleth-idp/logs/idp-process.log | tail -1

# SP のセッションに isMemberOf が入ったか
kubectl -n weko3 exec deploy/tenant1-web -c nginx -- \
  sh -c 'grep TRANSACTION.Login /var/log/shibboleth/transaction.log | tail -1'
```

---

## ユーザを追加する / isMemberOf を変える

編集するファイルは 2 つだけ。

| 変えたいもの | ファイル | 反映先 |
|---|---|---|
| ログイン ID とパスワード | `shib-idp-build/idp-conf/credentials/demo.htpasswd` | 機関 IdP |
| `isMemberOf`（mAP グループ） | `shib-idp-build/idp-conf/conf/attribute-resolver.xml` の `isMemberOf` | `aggregation` なら**属性認証局**、`sso` なら機関 IdP |
| `wekoSocietyAffiliation`（もう一つのロール源） | 同ファイルの `wekoSocietyAffiliation` | 機関 IdP |

> **ロールの源は 2 つある。** `check_in()` はまず `wekoSocietyAffiliation` でロールを決め、その後
> `isMemberOf` のグループ分を足す。片方だけ変えるともう片方のロールが残るので、両方見ること。

### 1) ユーザを追加する

`HTPasswdCredentialValidator` は `$apr1$` / `{SHA}` / `crypt(3)` しか解釈しない（**bcrypt は不可**）。

```bash
htpasswd -nbm taro taro123    # -m (apr1) を使う。-B (bcrypt) はダメ
# taro:$apr1$qwMNHJL1$nHtH9wxr7rfaEBk8xL5MG0
```

出力を `demo.htpasswd` に足す。`attribute-resolver.xml` に何も書かなければ、そのユーザは
`isMemberOf` / `wekoSocietyAffiliation` の `<DefaultValue>`（Contributor 相当）になる。

### 2) isMemberOf を変える

`attribute-resolver.xml` の `isMemberOf` は `Mapped` 属性定義。ログイン ID ごとに `ValueMap` を足す。

```xml
<AttributeDefinition id="isMemberOf" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <DefaultValue passThru="false">__MAP_BASE__/jc___IDP_FQDN___ro_cont</DefaultValue>
    <ValueMap>
        <ReturnValue>__MAP_BASE__/jc_roles_sysadm</ReturnValue>
        <SourceValue>taro</SourceValue>       <!-- ← 足す -->
    </ValueMap>
    ...
</AttributeDefinition>
```

`__IDP_FQDN__` はビルド時に置換されるのでそのまま書く。グループ名は末尾セグメントだけが評価される:

| 末尾セグメント | WEKO ロール |
|---|---|
| `jc_roles_sysadm` | System Administrator |
| `jc_<機関IdP の FQDN>_ro_radm` | Repository Administrator |
| `jc_<機関IdP の FQDN>_ro_cadm` | Community Administrator |
| `jc_<機関IdP の FQDN>_ro_cont` | Contributor |

グループ名と同名のロール（`jc_idp_localhost_ro_radm` 等）も付けたい場合は、そのロールが
Role テーブルに存在している必要がある。Redis のグループ一覧に足すと自動作成される（後述）。

### 3) 反映する

```bash
# aggregation: 属性認証局のイメージを作り直す
docker build --build-arg IDP_HOST=map.localhost \
             --build-arg IDP_ENTITYID=https://map.localhost/idp/shibboleth \
             --build-arg IDP_GROUP_FQDN_HOST=idp.localhost \
             -t weko3-shib-map:arm64 shib-idp-build
kind load docker-image weko3-shib-map:arm64 --name weko3
kubectl -n weko3 rollout restart deploy/weko-shib-map

# 機関 IdP（ユーザ追加・wekoSocietyAffiliation 変更のとき）
docker build --build-arg IDP_RELEASE_ISMEMBEROF=no -t weko3-shib-idp:arm64 shib-idp-build
kind load docker-image weko3-shib-idp:arm64 --name weko3
kubectl -n weko3 rollout restart deploy/weko-shib-idp
```

> **`idp-conf/` を編集した再ビルドでは署名鍵は変わらない。** インストーラを流す `RUN` より後ろの
> レイヤだけが無効化されるため。`provision-shib.sh` の流し直しは不要。
> 一方 **Dockerfile のインストーラ行より上（ARG など）を触ると鍵が作り直される**ので、その場合は
> `provision-shib.sh` を実行して SP 側のメタデータを更新すること。忘れると
> `Message was signed, but signature could not be verified.` で SSO が 500 になる。

### 4) 試すだけならビルド不要

Pod の中を直接いじって IdP に設定を再読込させれば、ビルドせずに確認できる（**Pod 再起動で消える**）。

```bash
# ユーザ追加は再読込すら不要 — htpasswd は毎回読み直される
kubectl -n weko3 exec deploy/weko-shib-idp -- sh -c \
  "echo 'taro:\$apr1\$qwMNHJL1\$nHtH9wxr7rfaEBk8xL5MG0' >> /opt/shibboleth-idp/credentials/demo.htpasswd"

# isMemberOf を変えたら属性解決サービスだけ再読込
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'vi /opt/shibboleth-idp/conf/attribute-resolver.xml'     # 任意のエディタで編集
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp bash bin/reload-service.sh -id shibboleth.AttributeResolverService'

# 何が返るか確認（ログイン不要）
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp bash bin/aacli.sh -n taro -r https://tenant1.localhost/shibboleth-sp'
```

再読込できるサービス: `shibboleth.AttributeResolverService` / `shibboleth.AttributeFilterService` /
`shibboleth.MetadataResolverService` / `shibboleth.RelyingPartyResolverService`。

### 5) isMemberOf を複数値にする（グループ情報など）

#### 本番 (学認mAP) が返す値の形

mAP は**グループの URL** を返す。同じグループについて、メンバーと管理者で 2 種類の値が来る。

```
https://cg.gakunin.jp/gr/research-project-a         … そのグループのメンバー
https://cg.gakunin.jp/gr/research-project-a/admin   … そのグループの管理者
```

weko-accounts の `_assign_roles_to_user()` は、

1. `/admin` で終わる値と `/sp/` を含む値を**読み飛ばす**（管理者かどうかは WEKO のロールに反映しない）
2. 残りの値の**最後のセグメントだけ**を取り出す（`research-project-a`）
3. それを `jc_<FQDN>_ro_*` のパターン照合と、同名ロールの検索に使う

という順で処理する。つまり**ホスト部分は何でもよい**。この一式では `__MAP_BASE__`
（既定 `https://<IdP のホスト>/gr`）をベースにしていて、`IDP_GROUP_BASE_URL` のビルド引数で変えられる。

#### 定義の書き方

種類ごとに分けて定義し、`Simple` 属性定義で束ねるのが素直。
以下は書き方を示すための抜粋で、既定の定義そのものではない（実物は
`shib-idp-build/idp-conf/conf/attribute-resolver.xml`。上の 2 つの表がその既定値の一覧）。

```xml
<!-- ① ロール決定用（ユーザごとに 1 つ） -->
<AttributeDefinition id="mapRoleGroup" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <DefaultValue passThru="false">__MAP_BASE__/jc___IDP_FQDN___ro_cont</DefaultValue>
    <ValueMap><ReturnValue>__MAP_BASE__/jc_roles_sysadm</ReturnValue>
              <SourceValue>admin</SourceValue></ValueMap>
    <ValueMap><ReturnValue>__MAP_BASE__/jc___IDP_FQDN___ro_cadm</ReturnValue>
              <SourceValue>commadmin</SourceValue></ValueMap>
</AttributeDefinition>

<!-- ② 研究プロジェクトなどの一般グループ（同じユーザに複数マッチしてよい。SourceValue は正規表現） -->
<AttributeDefinition id="mapOrgGroup" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <ValueMap><ReturnValue>__MAP_BASE__/research-project-a</ReturnValue>
              <SourceValue>libadmin|teacher</SourceValue></ValueMap>
    <ValueMap><ReturnValue>__MAP_BASE__/lib-staff</ReturnValue>
              <SourceValue>libadmin</SourceValue></ValueMap>
    <ValueMap><ReturnValue>__MAP_BASE__/test-group-1</ReturnValue>
              <SourceValue>admin|libadmin</SourceValue></ValueMap>
</AttributeDefinition>

<!-- ③ そのグループの管理者であることを表す値。mAP はメンバーの値とセットで返す -->
<AttributeDefinition id="mapOrgAdminGroup" xsi:type="Mapped">
    <InputAttributeDefinition ref="uid" />
    <ValueMap><ReturnValue>__MAP_BASE__/research-project-a/admin</ReturnValue>
              <SourceValue>libadmin</SourceValue></ValueMap>
</AttributeDefinition>

<!-- ④ 全員が入る共通グループ（Static データコネクタ。<Value> を並べれば増やせる） -->
<AttributeDefinition id="mapCommonGroup" xsi:type="Simple">
    <InputDataConnector ref="staticAttributes" attributeNames="commonGroup" />
</AttributeDefinition>

<!-- ①〜④ を束ねる。値の無い入力は単に無視される -->
<AttributeDefinition id="isMemberOf" xsi:type="Simple">
    <InputAttributeDefinition ref="mapRoleGroup" />
    <InputAttributeDefinition ref="mapOrgGroup" />
    <InputAttributeDefinition ref="mapOrgAdminGroup" />
    <InputAttributeDefinition ref="mapCommonGroup" />
</AttributeDefinition>
```

`staticAttributes` 側にも足す（`exportAttributes` に載せるのを忘れないこと）:

```xml
<DataConnector id="staticAttributes" xsi:type="Static"
               exportAttributes="schacHomeOrganization commonGroup">
    ...
    <Attribute id="commonGroup">
        <Value>__MAP_BASE__/all_users</Value>
    </Attribute>
</DataConnector>
```

押さえるべき挙動（いずれも実測）:

| | 挙動 |
|---|---|
| `Mapped` の `ValueMap` | **一致したものを全部返す**。同じ `SourceValue` を複数書けば 1 ユーザに複数値が付く |
| `SourceValue` | **正規表現**。`libadmin\|teacher` のように書ける |
| `Mapped` の `DefaultValue` 省略 | どれにも一致しないユーザには**値が付かない**（`Simple` で束ねるときはこれが便利） |
| `Simple` の複数入力 | 全入力の値を連結する |
| SP → WEKO | 多値属性は SP が **`;` 区切り**で 1 つの環境変数にまとめ、`ShibUser.__init__` が `;` で split して戻す |

#### 結果

```
$ python3 list-shib-users.py --table
eppn                  isMemberOf
--------------------  --------------------------------------------
admin@example.org     https://map.localhost/gr/all_users
admin@example.org     https://map.localhost/gr/jc_roles_sysadm
libadmin@example.org  https://map.localhost/gr/all_users
libadmin@example.org  https://map.localhost/gr/research-project-a/admin
libadmin@example.org  https://map.localhost/gr/research-project-a
libadmin@example.org  https://map.localhost/gr/lib-staff
libadmin@example.org  https://map.localhost/gr/jc_idp_localhost_ro_radm
teacher@example.org   https://map.localhost/gr/all_users
teacher@example.org   https://map.localhost/gr/research-project-a
teacher@example.org   https://map.localhost/gr/jc_idp_localhost_ro_cont
```

ロール決定に使われるのは `jc_*` の 1 つだけで、残りは**グループ名と同名のロール**として付く
（そのロールが Role テーブルにあれば）。`libadmin` の実際の結果:

```
libadmin@example.org | Repository Administrator, all_users, jc_idp_localhost_ro_radm,
                       lib-staff, research-project-a
```

`Repository Administrator` は `jc_..._ro_radm` のパターン一致由来、`all_users` / `lib-staff` /
`research-project-a` はグループ名そのものが Role テーブルにあるため付いたもの。

**`research-project-a/admin` からはロールが付いていない。** `admin` という名前のロールを
Role テーブルに用意した状態で試しても付かないので、`/admin` の読み飛ばしが効いていることが分かる。

### 6) jc_* ロールを増やす

グループ名そのもののロールは Redis のグループ一覧から作られる。新しいグループを使うなら足しておく。

```bash
kubectl exec -n weko3re redis-0 -- redis-cli -n 4 hset idp_localhost_gakunin_groups \
  groups "jc_idp_localhost_ro_radm,jc_idp_localhost_ro_cadm,jc_idp_localhost_ro_cont,jc_roles_sysadm,research-project-a,lib-staff,all_users"
```

一覧から外したロール（`jc_` で始まるもの）は次回ログイン時に**削除される**ので注意。

### 7) 現在のユーザとグループを一覧で見る

ユーザ情報とグループ情報は**保存先が分かれている**。`isMemberOf` は WEKO の DB に残らない
（`ShibUser.__init__` が読んだあと `del` する）ので、グループを見るには IdP 側に問い合わせるしかない。

| 見たいもの | 出どころ |
|---|---|
| eppn / mail / displayName / wekoSocietyAffiliation / `isMemberOf` | IdP・属性認証局（`aacli.sh`） |
| 紐付いた WEKO アカウントと付与済みロール | WEKO の DB（`shibboleth_user` × `accounts_role`） |

両方を突き合わせて出すスクリプトを用意してある。

```bash
python3 list-shib-users.py              # htpasswd の全ユーザ
python3 list-shib-users.py --user teacher
python3 list-shib-users.py --table      # eppn と isMemberOf だけを表形式で
python3 list-shib-users.py --tsv        # 同じものをタブ区切りで (grep/sort 用)
```

`--table` はグループ 1 つにつき 1 行:

```
eppn                  isMemberOf
--------------------  --------------------------------------------
admin@example.org     /gakunin/idp_localhost/all_users
admin@example.org     /gakunin/idp_localhost/jc_roles_sysadm
libadmin@example.org  /gakunin/idp_localhost/all_users
libadmin@example.org  /gakunin/idp_localhost/lib_staff
libadmin@example.org  /gakunin/idp_localhost/dept_science
libadmin@example.org  /gakunin/idp_localhost/jc_idp_localhost_ro_radm
teacher@example.org   /gakunin/idp_localhost/all_users
teacher@example.org   /gakunin/idp_localhost/dept_science
teacher@example.org   /gakunin/idp_localhost/jc_idp_localhost_ro_cont
```

`--tsv` にすると絞り込みや集計に回せる:

```bash
python3 list-shib-users.py --tsv | grep '/jc_'              # ロール決定用のグループだけ
python3 list-shib-users.py --tsv | awk -F'\t' '{print $2}' | sort -u   # 使われているグループ一覧
```

```
IdP            : weko-shib-idp
グループの出どころ / groups from : weko-shib-map

== libadmin ==
  eppn                   : libadmin@example.org
  mail                   : libadmin@example.org
  displayName            : libadmin
  wekoSocietyAffiliation : 図書館員
  isMemberOf (4)         : /gakunin/idp_localhost/all_users
                           /gakunin/idp_localhost/lib_staff
                           /gakunin/idp_localhost/dept_science
                           /gakunin/idp_localhost/jc_idp_localhost_ro_radm
  --- WEKO (ログイン済み / logged in) ---
  WEKO アカウント        : libadmin@example.org
  付与済みロール         : all_users, dept_science, jc_idp_localhost_ro_radm, lib_staff, Repository Administrator
```

**ログインしなくても確認できる**（`aacli.sh` は属性解決だけを行う）ので、`attribute-resolver.xml` を
直したあとの確認に使える。末尾には「htpasswd から消したのに WEKO に紐付けが残っているユーザ」も出る。

個別に見たいときは以下でも足りる。

```bash
# IdP がこれから発行する属性
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp \
     bash bin/aacli.sh -n libadmin -r https://tenant1.localhost/shibboleth-sp'

# ↑ の JSON を eppn / isMemberOf の表にする
kubectl -n weko3 exec deploy/weko-shib-map -- sh -c \
  'cd /opt/shibboleth-idp && IDP_BASE_URL=http://localhost:8080/idp \
     bash bin/aacli.sh -n libadmin -r https://tenant1.localhost/shibboleth-sp' 2>/dev/null \
| python3 -c '
import sys, json, re
d = json.loads(re.search(r"\{.*\}", sys.stdin.read(), re.S).group(0))
a = {x["name"]: x.get("values", []) for x in d.get("attributes", [])}
eppn = (a.get("eduPersonPrincipalName") or ["-"])[0]
print("%-24s %s" % ("eppn", "isMemberOf"))
for g in a.get("isMemberOf") or ["-"]:
    print("%-24s %s" % (eppn, g))
'

# WEKO 側の紐付けとロール
PGM=$(kubectl get pod -n weko3 -l cluster-name=weko-postgresql,spilo-role=master -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n weko3 "$PGM" -- psql -U postgres -d wekodb -c \
  "select s.shib_eppn, u.email, s.shib_role_authority_name, string_agg(r.name, ', ' order by r.name)
     from shibboleth_user s join accounts_user u on u.id = s.weko_uid
     left join accounts_userrole ur on ur.user_id = u.id
     left join accounts_role r on r.id = ur.role_id
    group by 1,2,3 order by 1;"
```

### 8) 確認例

`taro` を追加し、`isMemberOf` を `jc_roles_sysadm` に変えて再ログインした結果:

```
taro@example.org | Contributor, System Administrator, jc_roles_sysadm
```

`System Administrator` と `jc_roles_sysadm` が `isMemberOf` 由来、`Contributor` は
`wekoSocietyAffiliation` の既定値（教員）由来。両方の源が効いていることが分かる。

---

## この構成で本番と違うところ

| 項目 | 本番（学認 / weko-k8s） | ここ |
|---|---|---|
| IdP | 学認の IdP | クラスタ内のテスト IdP 1 台 |
| 属性認証局 | 学認クラウドゲートウェイ（mAP） | 同じイメージで立てたテスト用 AA 1 台（`aggregation` のとき） |
| グループ情報 | mAP が実際のグループを管理 | ログイン ID から静的に導出（`Mapped` 属性定義） |
| IdP の選択 | DS（WAYF）で選ぶ | IdP を 1 つに固定（`<SSO entityID=...>`） |
| メタデータ | フェデレーションから取得し署名検証 | ローカルファイルを無条件に信頼 |
| 属性の公開 | SP ごとにポリシーを絞る | 登録済み SP すべてに公開 |
| 認証 | LDAP | htpasswd |
| nginx | `weko.conf`（IP 制限・WAF 相当のルール込み） | `default-shib.conf`（必要な location だけ） |
| `NO_CHECK_WEKOSOCIETYAFFILIATION` | `FALSE`（属性が無ければ拒否） | `TRUE`（属性が無くてもログインは通す） |

`NO_CHECK_WEKOSOCIETYAFFILIATION` を本番同様 `FALSE` にしたい場合は
`21-nginx-config.yaml` の `default-shib.conf` を編集して `kubectl rollout restart deploy/<tenant>-web -n weko3`。

---

## TLS の扱いに注意

TLS は Ingress で終端し、nginx 自身は平文で受けている。一方 shibd は受け取った FastCGI パラメータから
ACS の URL や SAML の `Destination` を組み立てるため、**https だと伝えないと検証に落ちる**。
`default-shib.conf` は Ingress が付ける `X-Forwarded-Proto` を見て
`HTTPS` / `REQUEST_SCHEME` / `SERVER_PORT` を差し替えている。IdP 側も同じ理由で Tomcat に
`RemoteIpValve` を入れている。

`WEKO_TLS_ISSUER=` を空にして HTTPS を切ると、この前提が崩れて SAML が通らなくなる。
Shibboleth ログインを使うときは **HTTPS を有効のまま**にすること。

---

## 確認とトラブルシュート

```bash
# IdP が設定を読み込めているか（200 なら OK。403 は access-control.xml の許可漏れ）
curl -sk -o /dev/null -w '%{http_code}\n' -H 'Host: idp.localhost' https://localhost/idp/status

# IdP のログ
kubectl logs -n weko3 deploy/weko-shib-idp --tail=100
kubectl exec -n weko3 deploy/weko-shib-idp -- tail -100 /opt/shibboleth-idp/logs/idp-process.log

# SP(shibd) のログ。属性が届いているかはここを見る
kubectl logs -n weko3 deploy/tenant1-web -c nginx --tail=100

# SP が IdP のメタデータを読めているか
kubectl exec -n weko3 deploy/tenant1-web -c nginx -- ls -l /etc/shibboleth/

# 属性認証局 (WEKO_SHIB_MAP=aggregation のとき)
kubectl logs -n weko3 deploy/weko-shib-map --tail=100
kubectl exec -n weko3 deploy/weko-shib-map -- \
  grep "Shibboleth-Audit.AttributeQuery" /opt/shibboleth-idp/logs/idp-process.log | tail -3

# SP が実際に受け取った属性 (isMemberOf が入っていれば AttributeQuery 成功)
kubectl exec -n weko3 deploy/tenant1-web -c nginx -- \
  sh -c 'grep TRANSACTION.Login /var/log/shibboleth/transaction.log | tail -1'
```

| 症状 | 見るところ |
|---|---|
| `/secure/login.py` が 502 | `fcgiwrap` が入っているか（`deploy-arm64.sh` の nginx イメージビルド）。CGI のステータス行を `Status:` に直すパッチも当たっているか |
| IdP へ飛ばずに 403/500 | shibd が起動していないか、`/etc/shibboleth/` の中身が欠けている。`WEKO_SHIB=yes` で生成し直したか確認 |
| IdP が `Message Destination` エラー | `X-Forwarded-Proto` が届いていない（HTTPS を切っていないか） |
| SP がアサーションを拒否 | IdP を作り直したのに `provision-shib.sh` を流していない（署名鍵の不一致） |
| ログインは通るがロールが付かない | `wekoSocietyAffiliation` が公開されていない。`attribute-filter.xml` と `attribute-resolver.xml` を確認 |
| `isMemberOf` が届かない | `WEKO_ACCOUNTS_ATTRIBUTE_MAP` に `shib_is_member_of` があるか（無いと黙って捨てられる）。`aggregation` なら属性認証局の監査ログに AttributeQuery が出ているか |
| `Transport confidentiality required` | 属性認証局の 8443 バックチャネルに届いていない。Service の 8443 と `hostAliases` の `map.localhost` を確認 |

---

## 片付け

IdP（と属性認証局）だけ落とす場合:

```bash
kubectl delete -f 70-shibboleth-idp.yaml
kubectl delete -f 71-shibboleth-map.yaml --ignore-not-found
kubectl delete configmap weko-idp-sp-metadata -n weko3
```

WEKO3 側を Shibboleth 無効に戻すには、`WEKO_SHIB` を付けずに再デプロイする。

```bash
bash deploy-arm64.sh
```
