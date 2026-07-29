# kind を離れて本番環境を構築するための道筋

`weko-k8s-sample`（kind 検証環境）を出発点に、**本格的な Kubernetes 環境を構築していく順序**をまとめる。

何がどう違うのかは [COMPARE-production.md](COMPARE-production.md) を参照。本ドキュメントは
「その差異を**どの順番で、何を判断しながら**解消していくか」に絞る。
英語版: [PRODUCTION-ROADMAP.en.md](PRODUCTION-ROADMAP.en.md)

---

## 0. 基本方針

### 0-1. kind 版は改造せず、分岐させる

`k8s-weko-amd64` を書き換えるのではなく、**別ディレクトリに分岐させる**ことを推奨する。

理由は、`imagePullPolicy: Never`・固定 ClusterIP・`FORCE_INIT=yes` といった選択が
**「検証環境としては正しく、本番では逆」**だからである。一つのファイルで両方を満たそうとすると
条件分岐だらけになり、どちらの環境の記述なのか読めなくなる。

kind 版は「1台のサーバで本番構成を再現できる検証環境」として完成度が高く、**その価値を保つべきである**。

### 0-2. 到達点は「本番 IaC への合流」

最終的には `RCOSDP/weko-k8s` の構成（kustomize `base`/`components`/`overlay`）に合流させるのが望ましい。
ゼロから別体系を作ると、本番 IaC との二重メンテが永久に続く。

したがって道筋は **「kind 版を kustomize 化する」→「overlay を本番値に差し替える」→
「本番 IaC の構造に寄せる」→「運用層を積む」** という順になる。

### 0-3. 順序の原則

**「起動しないもの」を先に、「動くが不十分なもの」を後に。**

[COMPARE-production.md](COMPARE-production.md) の分類でいえば:

| 順序 | 対象 | 理由 |
|---|---|---|
| 1番目 | 🟡 **代替物** | これが残っていると**そもそも起動しない**。フィードバックが得られない |
| 2番目 | 🔵 **簡略化** | 起動はする。実負荷をかける前に本番仕様へ |
| 3番目 | 🔴 **未実装** | 動いてから積む。ただし本番稼働前には必須 |

---

## 全体像

```
Phase 0  前提の意思決定          ← ここを飛ばすと後で必ず手戻りする
   ↓
Phase 1  kustomize 化           kind で動いたまま、構造だけ変える
   ↓
Phase 2  本番 overlay の作成     🟡 代替物を本物に置換 → 実クラスタで起動させる
   ↓
Phase 3  本番構造への合流        🔵 簡略化を解消 → weko-k8s の構造に寄せる
   ↓
Phase 4  運用層の構築            🔴 未実装を積む
   ↓
Phase 5  本番稼働の準備          データ移行・リハーサル・切替
```

各 Phase は**前の Phase の完了条件を満たしてから**着手する。特に Phase 1 と Phase 2 を
同時にやると、失敗したとき「構造変更のせいか、値の差し替えのせいか」が切り分けられなくなる。

---

## Phase 0 — 前提の意思決定

**目的**: 後段の作業内容を決定づける選択を、着手前に確定させる。

ここを曖昧にしたまま進めると、Phase 2 以降で必ず手戻りする。

### 決めるべきこと

| # | 決定事項 | 選択肢 | これが決まらないと |
|---|---|---|---|
| 1 | **実行基盤** | OKE / EKS / GKE / オンプレ kubeadm | StorageClass も LB も決まらない |
| 2 | **k8s バージョン** | 本番 IaC は v1.32.1 | API の非互換が判明しない |
| 3 | **ブロック StorageClass** | `oci-bv` / `gp3` / Ceph RBD … | 全 PVC が Pending |
| 4 | **共有 FS の実体** | OCI FSS / EFS / 学内 NAS / Ceph FS | テナントの Pod が起動しない |
| 5 | **Ingress Controller** | **NGINX Plus + App Protect（商用）** / ingress-nginx OSS | WAF 要件と費用が決まらない |
| 6 | **外部公開の方式** | LoadBalancer / MetalLB / 外部 LB + NodePort | DNS も証明書も決まらない |
| 7 | **レジストリ** | OCIR / Harbor / GHCR / ECR | イメージ供給の設計ができない |
| 8 | **本番データの移行有無** | あり / なし（新規構築） | **PG のメジャーバージョンが決まらない** |
| 9 | **TLS ホップ2 の扱い** | 本番踏襲（暗号化のみ）/ 正しい証明書 + 検証有効化 | nginx イメージの要否が決まらない |

### 特に重要な2つ

**① Ingress Controller は費用・要件の意思決定である（#5）**

本番 IaC は **NGINX Plus + App Protect** を使っており、どちらも商用ライセンスが必要である。
OSS の ingress-nginx で行くなら、WAF は ModSecurity 等で別途設計するか、要件から外す判断が要る。
これは技術的な選択ではなく**調達の判断**なので、最も早く着手すべき項目である。

**② PG のメジャーバージョンは移行有無で決まる（#8）**

サンプルは PG17、本番 IaC は PG12（`spilo-13` イメージ上）。本番からデータを移行するなら
バージョンを揃えるか、`pg_upgrade` / dump-restore の計画が要る。
なお `51-postgresql-ha.yaml:5` のコメントは「本番は PG13」と書いているが現行 IaC は `version: "12"` なので、
**本番実機で実際のバージョンを確認すること**。

### 完了条件（DoD）
- [ ] 上記9項目すべてに回答が出ている
- [ ] #5 について、ライセンス調達の可否と WAF 要件の結論が出ている
- [ ] #8 について、移行元の PG バージョンを実機で確認済み

---

## Phase 1 — kustomize 化（挙動は変えない）

**目的**: kind で動く状態を保ったまま、構造だけを本番 IaC と同じ形にする。

### なぜ先にやるのか

値を差し替えられる構造がないと、Phase 2 で「本番用にコピーした別ファイル」が量産され、
kind 版と本番版が乖離していく。**先に器を作る。**

### 作業

`base` と `overlay/kind` に分割する。この時点で overlay に切り出すのは、
Phase 2 で差し替えることが確定している**次の4点だけ**でよい。

| # | overlay に出す項目 | kind の値 |
|---|---|---|
| 1 | StorageClass 名 | `standard` / `nfs-static` |
| 2 | イメージ名・`imagePullPolicy`・`imagePullSecrets` | ローカルビルド名 / `Never` / なし |
| 3 | NFS サーバのアドレス | `10.96.0.99` |
| 4 | Ingress のホスト名と TLS 発行方式 | `*.localhost` / `weko-ca-issuer` |

欲張って namespace 分割やサイジングまで手を出さないこと。**この Phase の価値は「挙動を変えないこと」**にある。

### 完了条件（DoD）
- [ ] `kubectl kustomize overlay/kind` の出力が、現行 manifest と**意味的に一致**する
- [ ] `overlay/kind` で kind 環境が従来どおり構築でき、テナントに HTTPS でアクセスできる
- [ ] 上記4点が overlay 側だけの記述で切り替えられる

---

## Phase 2 — 本番 overlay の作成（🟡 代替物の置換）

**目的**: 🟡 代替物を本物に置き換え、**実クラスタで起動する**ところまで持っていく。

### なぜここが山場か

[COMPARE-production.md](COMPARE-production.md) の 🟡 は「動いているように見えるが本番では通用しない」
ものであり、**一つでも残っていると起動しない**。逆に言えば、ここを越えれば以降はフィードバックを
得ながら進められる。

### 作業順序

**2-1. イメージ供給（これが通らないと何も起動しない）**
1. レジストリを用意し、WEKO / ES / nginx の3イメージを push
2. `kind load docker-image` を全削除（4箇所）
3. `imagePullPolicy: Never` を9箇所すべて修正
4. `imagePullSecrets` を全 Pod spec に追加

**2-2. ストレージ**
1. `storageClassName: standard` を6箇所、実 SC 名に置換
2. **`60-nfs-server.yaml` を丸ごと削除**し、外部 NFS を用意
3. `NFS_SERVER` を実 NFS のアドレスへ。`clusterIP: 10.96.0.99` への依存を除去
4. MinIO を削除し、S3 エンドポイントを実オブジェクトストレージへ（`set-s3-location.sh` の書き換え）

**2-3. 配置**
1. ノードに `nodeType` ラベルを付与（この時点では `WEKO`/`DATA` の2種のままでよい）
2. `13-elasticsearch.yaml` の privileged initContainer を削除し、ノード側で sysctl を設定

**2-4. ネットワーク・公開**
1. Ingress Controller を Phase 0 #5 の決定に従って導入
2. LoadBalancer / MetalLB / 外部 LB を構成
3. `tenants.txt` の `*.localhost` を実 FQDN へ、DNS を設定
4. `61-tls-ca.yaml` を削除し、実証明書 Secret 方式へ
5. 疎通確認スクリプト（`deploy-amd64.sh:328-355`）を実 FQDN 向けに書き換え

**2-5. 安全装置**
1. `FORCE_INIT` の既定を `no` に（または初期化ステップを別コマンドに分離）
2. `teardown-*.sh` を本番用ディレクトリから除外

### この Phase でやらないこと
- namespace 分割（Phase 3）
- サイジングの本番化（Phase 3）
- 監視・ログ・バックアップ（Phase 4）

**差分を小さく保つ。** ここで欲張ると、起動しないときの切り分けが不可能になる。

### 完了条件（DoD）
- [ ] **検証用の実 k8s クラスタ**（本番相当の基盤、ただし本番そのものではない）で全 Pod が Running
- [ ] テナントに実 FQDN + 実証明書で HTTPS アクセスできる
- [ ] アイテム登録・検索が通る（ES / PG / RabbitMQ / Redis / オブジェクトストレージの疎通確認）
- [ ] 🟡 の項目がすべて解消されている

---

## Phase 3 — 本番構造への合流（🔵 簡略化の解消）

**目的**: 本番 IaC (`weko-k8s`) と同じ構造・同じ規模にする。

### 3-1. namespace 分割 ← **影響範囲が最大**

`weko3pg` / `weko3es` / `weko3ra` に分割する。これに伴い **Service の FQDN がすべて変わる**
（`elasticsearch` → `elasticsearch.weko3es.svc.cluster.local` 等）。

`gen-tenant.sh` が ConfigMap に書き込む接続先を全て見直すこと。
**単独のステップとして実施し、他の変更と混ぜないこと。**

### 3-2. ノード種別ラベルの分解

`WEKO`/`DATA` の2種を、本番の8種（`WEKO` `PGO` `PGPOOL` `ES` `RA` `RE` `SE` `LOG`）へ。
併せて `nodeSelector` 直書きから、本番同様の **kustomize component による `nodeAffinity` 注入**へ移す。

### 3-3. テナント管理の統合

| 選択肢 | 内容 | 評価 |
|---|---|---|
| **(A) 本番スクリプトに寄せる** | `gen-tenant.sh` を捨て、`make_weko_manifests.sh` + `deploy/weko/manifest_template/` を使う。テナント定義も `repositories_file` 形式へ | **推奨。** 二重メンテが消える |
| (B) `gen-tenant.sh` を拡張 | 列を本番互換（20列）に増やし、メモリ・uwsgi プロセス数・WAF annotation を追加 | 「1コマンドで完結」は残るが、雛形の差分管理が残る |

Deployment の構造自体はほぼ一致しているので (A) は現実的である
（[COMPARE-production.md §6](COMPARE-production.md) 参照）。

### 3-4. サイジングの本番化

`oci-pr` の値を参考に、**実ノード構成とテナント数で再計算する**。`oci-pr` の値をそのまま持ってきても
合わない（PG に 25 CPU / 32Gi を要求している）。

併せて pgpool（1→複数）と、オブジェクトストレージの SPOF を解消する。

### 3-5. 秘密情報の管理

本番同様の `secret.properties` + `secretFromProperties` generator 方式へ。
理想は External Secrets Operator / Sealed Secrets / OCI Vault。
**`tenants.txt` を Git 管理から外す。**

### 3-6. nginx コンテナと TLS ホップ2（Phase 0 #9 の決定に従う）

本番同等にする場合、次の3点がセットで必要:
1. Shibboleth SP 入り nginx イメージ
2. `server.crt` / `server.key` を共有 FS に配置
3. Ingress に `backend-protocol: HTTPS` / `ssl-services` annotation

### 完了条件（DoD）
- [ ] namespace が本番と同じ構成になり、全 Service が疎通する
- [ ] ノードラベルが本番体系になっている
- [ ] テナント生成の方式が確定し、実行できる
- [ ] サイジングが実構成で再計算され、実負荷試験を通っている

---

## Phase 4 — 運用層の構築（🔴 未実装の追加）

**目的**: 本番稼働に必要な運用基盤を積む。

Phase 3 までで構造が本番 IaC と揃っていれば、`weko-k8s` の該当ディレクトリを
**overlay を足すだけで再利用できる可能性が高い**。

### 優先順位

| 優先度 | 項目 | 本番 IaC の該当箇所 |
|---|---|---|
| **最優先** | **バックアップとリストア** | `postgresql/components/{backup_s3,pgdump_s3}`、`elasticsearch/components/backup_s3`、`contents-backup/`、`scripts/restore_*.sh` |
| **最優先** | **監視** | `deploy/monitoring/`（kube-prometheus-stack + ServiceMonitor + アラートルール） |
| 高 | **ログ集約** | `deploy/logging/`（fluentd → ES → Kibana、Slack 通知） |
| 中 | メンテナンス画面・保守 Pod | `deploy/maintenance/`、`deploy/maintenance-pod/` |
| 中 | ノード保守手順 | `scripts/maintenance/` |
| 要件次第 | WAF | `ingress/components/ap-config/`、`scripts/waf_management/` |
| 要件次第 | 内部向け Ingress | `deploy/ingress-nginx-internal/` |
| 対応済み | metrics-server（サンプルにも導入済み。HPA を使う場合に必須） | `deploy/metrics-server/` |

> **バックアップを最優先にする理由**: 監視は「壊れたことに気づく」ための仕組みだが、
> バックアップは「壊れても戻せる」ための仕組みである。順序を逆にしてはいけない。
> **リストアは必ず実際に試すこと。** 取れているだけで戻せないバックアップは無いのと同じである。

### HA 強化の判断（本番 IaC も未実装の領域）

PDB / NetworkPolicy / topologySpreadConstraints は**本番 IaC にも無い**。
「本番と同等でよい」のか「本番ごと改善する」のかを、ここで意識的に決める。
改善する場合は本番 IaC 側へのフィードバックも検討する。

### 完了条件（DoD）
- [ ] バックアップが取得され、**リストアの実演が成功している**
- [ ] 監視ダッシュボードとアラートが動作している
- [ ] ログが集約され、検索できる
- [ ] ノードの drain / アップグレード手順が文書化され、試行済み

---

## Phase 5 — 本番稼働の準備

**目的**: 実データを載せ、切り替える。

1. **データ移行のリハーサル** — PG のバージョン差（Phase 0 #8）を踏まえた移行手順を、本番相当データで試行
2. **負荷試験** — 想定テナント数・同時接続数で、Phase 3-4 のサイジングを検証
3. **障害試験** — ノード停止、PG フェイルオーバー、pgpool 停止時の挙動確認
4. **切替リハーサル** — DNS 切替、ロールバック手順の確認
5. **運用手順書の整備** — 日常運用・障害対応・定期メンテナンス

### 完了条件（DoD）
- [ ] 本番相当データでの移行が成功している
- [ ] 想定負荷を捌けることが実測で確認されている
- [ ] 主要な障害シナリオで復旧できることを確認済み
- [ ] ロールバック手順が確立している

---

## 手戻りしやすいポイント

経験上、次の場所で手戻りが起きやすい。

| 手戻りの原因 | 予防策 |
|---|---|
| Phase 0 を飛ばして着手する | **必ず9項目を先に決める。** 特に #5（Ingress の調達）と #8（PG バージョン） |
| Phase 1 と 2 を同時にやる | 構造変更と値の差し替えを分ける。失敗時の切り分けが可能になる |
| Phase 2 で namespace 分割まで手を出す | Phase 3 に回す。起動確認までの差分を最小に保つ |
| namespace 分割時に Service FQDN を見落とす | ConfigMap の接続先を**全て**洗い出してから着手 |
| `oci-pr` のサイジングをそのまま持ってくる | 実ノード構成で再計算する |
| バックアップを「取れた」で終わらせる | **リストアを実演する** |
| `FORCE_INIT=yes` のまま本番運用に入る | Phase 2-5 で既定を変更し、初期化を分離 |

---

## 進捗チェックリスト

### Phase 0 — 前提の意思決定
- [ ] 実行基盤・k8s バージョンを決定
- [ ] StorageClass（ブロック）と共有 FS の実体を決定
- [ ] Ingress Controller と WAF 要件を決定（**調達判断**）
- [ ] 外部公開の方式を決定
- [ ] レジストリを決定
- [ ] データ移行の有無と PG バージョンを確定（**移行元実機で確認**）
- [ ] TLS ホップ2 の方針を決定

### Phase 1 — kustomize 化
- [ ] `base` / `overlay/kind` に分割
- [ ] 4項目が overlay で切り替え可能
- [ ] kind で従来どおり動作

### Phase 2 — 🟡 代替物の置換
- [ ] レジストリ push + `kind load` 全削除
- [ ] `imagePullPolicy: Never` 9箇所修正、`imagePullSecrets` 追加
- [ ] `storageClassName: standard` 6箇所置換
- [ ] `60-nfs-server.yaml` 削除、外部 NFS へ、固定 ClusterIP 依存を除去
- [ ] MinIO 削除、実オブジェクトストレージへ
- [ ] `nodeType` ラベル付与
- [ ] privileged initContainer 削除、ノードで sysctl 設定
- [ ] Ingress Controller と外部公開経路を構成
- [ ] 実 FQDN + DNS + 実証明書
- [ ] `FORCE_INIT` 既定変更、`teardown-*.sh` 隔離
- [ ] **実クラスタで全 Pod Running、アイテム登録・検索が通る**

### Phase 3 — 🔵 簡略化の解消
- [ ] namespace 分割と Service FQDN 修正
- [ ] ノードラベルを8種体系へ
- [ ] テナント生成方式を確定（(A) または (B)）
- [ ] サイジング再計算
- [ ] 秘密情報を `secret.properties` 方式へ、`tenants.txt` を Git 管理外に
- [ ] nginx / TLS ホップ2 の方針を実装

### Phase 4 — 🔴 未実装の構築
- [ ] バックアップ構築 + **リストア実演**
- [ ] 監視 + アラート
- [ ] ログ集約
- [ ] メンテナンス・保守手順
- [ ] HA 強化の要否を判断

### Phase 5 — 本番稼働
- [ ] データ移行リハーサル
- [ ] 負荷試験
- [ ] 障害試験
- [ ] 切替・ロールバック手順

---

## 関連ドキュメント

| ドキュメント | 内容 |
|---|---|
| [COMPARE-production.md](COMPARE-production.md) | kind 環境と本番環境の全レイヤ差異カタログ |
| [README.md](README.md) | サンプル全体の設計 |
| [CONSTRUCTION.md](CONSTRUCTION.md) | 構築の経緯と HA クラスタ化の設計判断 |
| [JAIRO-CLOUD-ARCHITECTURE.md](JAIRO-CLOUD-ARCHITECTURE.md) | JAIRO Cloud 本番アーキテクチャ |
| [k8s-weko-amd64/HTTPS-letsencrypt.md](k8s-weko-amd64/HTTPS-letsencrypt.md) | Let's Encrypt への切替 |
| `~/weko-k8s`（`RCOSDP/weko-k8s`） | 本番 IaC 本体 |
