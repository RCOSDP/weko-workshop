# E2E テスト実行記録: `crossref` スイート

English: [`README.md`](README.md) ·
この記録が属する実行: [`../README.ja.md`](../README.ja.md)

Crossref DOI が付与され、パーマリンクになることを確認します。Crossref
への登録（deposit）はさらにその先で、この環境には無いアカウントが要ります。

テスト本体は
[`../../tests/test_crossref_doi.py`](../../tests/test_crossref_doi.py)、画像は
[`images/`](images) にあり、 各ステップが実行中に自分で撮ったものです。

| | |
| --- | --- |
| 実行 ID | `20260930-075808` |
| 結果 | **8 passed, 2 skipped** |
| 有効化 | `--suite crossref` |

---

### プレフィックスの設定（test_01）

Crossref 付与を有効にしプレフィックスを設定します。終了時にはどちらも元へ
戻します。

![プレフィックスを設定した識別子設定](images/01-identifier-settings.png)

### deposit に必要なメタデータ（test_03）

Crossref は掲載誌・ISSN・発行日が無いジャーナル論文を受け付けないため、
基本フローでは入力しないこれらを補います。

![掲載誌情報を入力したメタデータ画面](images/02-item-metadata.png)

### Crossref 付与が提示され、選択される（test_04）

![Crossref DOI が提示された識別子付与画面](images/03-grant-chosen.png)

### 承認と DOI の確認（test_05〜test_08）

![承認画面](images/04-approval.png)

![承認後](images/05-approved.png)

設定したプレフィックス配下の `10.5555/0002000088` が付与され、パーマリンク
として表示されます。

![DOI が表示されたアイテム詳細](images/06-record-page.png)

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
