# images/ — 構成図の PNG / PNG copies of the architecture diagrams

`README-arm64.md` / `README-arm64.en.md` の「デプロイ後のシステム構成」にある mermaid 図を PNG に書き出したもの。
mermaid を描画しないビューア向けの控えなので、**図を直したら mermaid 側と PNG の両方を更新する**。

These are PNG exports of the mermaid diagrams in the "System architecture after deploy" section of
`README-arm64.md` / `README-arm64.en.md`, kept for viewers that do not render mermaid. **When a diagram
changes, update both the mermaid source and the PNG.**

| PNG | 対応する図 / Diagram |
|---|---|
| `arch-base.png` / `arch-base.en.png` | 基本構成（全体図） / The base architecture |
| `arch-optional.png` / `arch-optional.en.png` | 任意機能を有効にした場合 / With the optional features enabled |
| `arch-request.png` / `arch-request.en.png` | リクエスト経路 / The request path |
| `arch-storage.png` / `arch-storage.en.png` | データの置き場所 / Where the data lives |

## 再生成 / Regenerating

README 内の mermaid ブロックを順番に取り出して `mmdc` に渡す。ブロックの順番が上の表の順番と対応する。

Extract the mermaid blocks from the README in order and feed them to `mmdc`; the order matches the table above.

```bash
cd k8s-weko
mkdir -p /tmp/mmd

# 1) README から mermaid ブロックを 1.mmd 〜 4.mmd に取り出す
awk '/^```mermaid$/{n++; inb=1; next} /^```$/{inb=0} inb && n{print > ("/tmp/mmd/" n ".mmd")}' README-arm64.md

# 2) PNG に書き出す（.en.md からは arch-*.en.png を作る）
names=(arch-base arch-optional arch-request arch-storage)
for i in 1 2 3 4; do
  npx -y @mermaid-js/mermaid-cli -i /tmp/mmd/$i.mmd -o images/${names[$i-1]}.png -b white -s 2
done
```

## arm64 ホストでの注意 / Notes for arm64 hosts

- Chrome for Testing に linux-arm64 ビルドが無いため、mermaid-cli が同梱の Chrome を起動しようとすると
  `qemu-x86_64: Could not open '/lib64/ld-linux-x86-64.so.2'` で失敗する。**システムの chromium を使う**:
  `PUPPETEER_EXECUTABLE_PATH=/snap/bin/chromium npx -y @mermaid-js/mermaid-cli ...`
- snap 版 chromium は confinement のため、`/tmp` と**ドットで始まるディレクトリ**（`~/.cache` など）配下の
  `file://` を読めず `net::ERR_ACCESS_DENIED` になる。`node_modules` を含む作業ディレクトリは
  `$HOME/<ドットなしの名前>/` に置く。
- 日本語ラベルには CJK フォントが要る（`fc-list :lang=ja` で確認。Noto Sans CJK JP など）。

- There is no linux-arm64 build of Chrome for Testing, so mermaid-cli's bundled Chrome fails with
  `qemu-x86_64: Could not open '/lib64/ld-linux-x86-64.so.2'`. **Use the system chromium** via
  `PUPPETEER_EXECUTABLE_PATH=/snap/bin/chromium`.
- The snap chromium is confined and cannot read `file://` paths under `/tmp` or under dot-directories such as
  `~/.cache` (`net::ERR_ACCESS_DENIED`). Keep the working directory that holds `node_modules` in
  `$HOME/<a name without a leading dot>/`.
- Japanese labels need a CJK font installed (check with `fc-list :lang=ja`).
