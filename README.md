# Instagram 毎日自動投稿システム（歯科・医科クリニック向け）

健康コラムを毎日自動で Instagram に投稿し、反応データを分析して自分で賢くなる仕組みです。
GitHub の無料枠と無料AIだけで動くため、**費用は0円**（AIネタ生成を使う場合のみ Anthropic API の従量課金）。

**初期設定ガイド（設定ファイル作成ツール付き）→ `docs/index.html`**
GitHub Pages を有効にすると `https://<ユーザー名>.github.io/<リポジトリ名>/` で開けます。

## できること

| 機能 | 内容 |
|---|---|
| 毎日自動投稿 | GitHub Actions が毎日（日本時間12:00）実行。曜日・休診日・開始日を設定可能 |
| 目的別の最適化 | `goals` に reach / reels / followers / acquisition を複数指定。形式（1枚・カルーセル・リール）と文末の呼びかけが変わる |
| サービス紹介CTA | `services` に登録したサービス（ホワイトニング・矯正・美容点滴…）に関連する投稿の末尾に案内文を自動付与。未登録サービスの投稿は除外 |
| 画像・イラスト・動画 | `docs/リサーチ_伸びる投稿の分析.md`（記事調査＋Instagram 実例の目視分析）に基づく型。表紙は「＼○○医が解説／」の肩書き＋画面いっぱいの縁取り文字（助詞は小さく、数字と「」は色の箱）＋「保存して読み返す」帯。カルーセルは目次 → 1 枚 1 ポイント → まとめ → CTA 1 つ。リールは上部の帯タイトル＋中央の大きな縁取りテロップ「① …」。院長写真（person_image）があれば右下に。背景写真は投稿ごとの illustration_prompt から無料AI（Cloudflare Workers AI / Hugging Face / Pollinations）で生成。写真が無い日は医院カラーの濃色ベタ。ffmpeg でリール動画化。絵文字は使わない |
| 投稿ネタ | 13ジャンル・435本（各投稿に切り口 hook・季節 months・サービス紐付け・イラスト指示を付与） |
| 週次PDCA | insights（リーチ・保存・いいね・コメント・シェア・再生）を取得し、カテゴリ／形式／切り口／サービス紹介の重みを学習。`docs/report.json` にレポート |
| AIネタ生成 | 医院HP・PDFから投稿ネタと提供サービスを生成（`scripts/ai_generate.py`）。週次で好調投稿の傾向から新ネタ生成・不調ネタ引退 |
| 自社アカウント | `specialties: ["webmarketing"]` でクリニック向けWEB知識を発信し、問い合わせに誘導 |

## 2つの進め方

| | 医院が自分で設定 | 運用会社がまとめて設定（推奨） |
|---|---|---|
| 医院の作業 | ガイドの Step 1〜5（約1時間） | プロアカウント化＋許可リンクをタップ（約5分） |
| 運用側の作業 | なし | `python scripts/setup_clinic.py --name "○○歯科" --code 届いたコード` |
| ガイド | `docs/index.html` | `docs/operator.html`（運用者）/ `docs/clinic.html`（医院に送る） |

運用者モードは GitHub と Meta アプリを運用会社が1つずつ持ち、医院ごとのリポジトリ作成・Secrets 登録・Pages 設定・設定ファイル生成・テスト起動を `scripts/setup_clinic.py` が GitHub API で自動実行します。トークンは `scripts/get_token.py --link` で作る許可リンク → 医院がタップ → `docs/authorize.html` に出るコード → `--code` で交換、という流れです。運用者の秘密情報は `config/operator.json`（gitignore 済み）に置きます。

## 手動投稿モード（Meta アプリの準備前や、自動投稿を使わない医院向け）

```bash
python scripts/manual_batch.py --days 7        # または 手動投稿を作る.bat をダブルクリック
```
本番と同じネタ選び・デザインで `output/manual/YYYY-MM-DD/` に画像・動画・caption.txt を出力し、`output/manual/index.html` から保存・コピーして投稿します。履歴は `state/posted.json` に残るので、後で自動投稿に切り替えても重複しません。

## フォルダ構成

```
config/clinic.json          医院ごとの設定（ガイドのフォームで生成）
config/examples/            業種別の設定見本（内科＋美容点滴、自社WEB発信用）
content/*.json              投稿ネタ（dental / internal / gastroenterology / dermatology / ent / pediatrics / ophthalmology / orthopedics / gynecology / mental / beauty / common / webmarketing）
content/custom.json         医院独自のネタ・AI生成ネタ（任意）
content/generated.json      週次ブラッシュアップで AI が追加したネタ（自動）
scripts/main.py             毎日の投稿（画像生成 → GitHub Pages 公開 → Instagram API）
scripts/analyze.py          週次の分析・学習・レポート
scripts/ai_generate.py      HP・資料からのネタ生成 / ブラッシュアップ
scripts/generate_image.py   1枚画像・カルーセル・リール用フレームの描画
scripts/illustration.py     無料AIイラスト（医院の写真 image_path を優先）
scripts/media.py            ffmpeg でリール動画化
scripts/instagram.py        Instagram API（Instagram Login 版・Facebookページ不要）
scripts/check_setup.py      トークン・設定の確認
scripts/manual_batch.py     手動投稿モード: 数日分をまとめて生成
scripts/setup_clinic.py     運用者向け: 医院を1件まとめてセットアップ（GitHub API）
scripts/get_token.py        運用者向け: 許可リンク作成とコード→トークン交換
config/operator.example.json 運用者設定の見本（operator.json は gitignore）
state/                      投稿履歴・insights・学習結果（自動更新）
docs/                       ガイドサイト + 公開用の画像/動画（GitHub Pages）
.github/workflows/          daily-post.yml（毎日）/ weekly-analyze.yml（毎週月曜）
```

## GitHub Secrets

| 名前 | 必須 | 内容 |
|---|---|---|
| `IG_ACCESS_TOKEN` | 必須 | Instagram 長期アクセストークン（毎日自動延長） |
| `IG_USER_ID` | 必須 | Instagram ユーザーID |
| `ANTHROPIC_API_KEY` | 任意 | AIネタ生成・週次ブラッシュアップ |
| `CF_ACCOUNT_ID` / `CF_API_TOKEN` | 推奨 | Cloudflare Workers AI（無料枠）で背景写真を安定生成 |
| `HF_TOKEN` | 任意 | Hugging Face 無料トークン（Cloudflare の代わり） |

## ローカルで試す

```bash
pip install -r requirements.txt
cd scripts
DRY_RUN=1 python main.py                 # 画像・キャプション生成のみ（docs/images/）
DRY_RUN=1 FORMAT=reel python main.py     # リール動画を生成
python generate_image.py                 # 3スタイル＋カルーセル＋リールのプレビュー（docs/preview/）
CLINIC_CONFIG=../config/examples/webmarketing_own.json DRY_RUN=1 python main.py   # 別設定で試す
IG_ACCESS_TOKEN=... python check_setup.py
```

Windows (PowerShell) は `$env:DRY_RUN="1"; python main.py` のように指定します。

## 投稿ネタの形式

```json
{
  "id": "whitening-coffee",
  "title": "コーヒー好きの歯が黄ばみやすい理由",
  "hook": "question",
  "body": ["箇条書き1", "箇条書き2", "箇条書き3"],
  "service": "whitening",
  "hashtags": ["#ホワイトニング"],
  "months": [1, 2],
  "date": "2026-12-01",
  "image_path": "assets/photos/whitening.jpg",
  "cta": "この投稿だけの案内文（任意）"
}
```

## 注意

- 投稿文は医療広告ガイドライン（誇大・比較表現、体験談、ビフォーアフターの禁止、自由診療の明記）に配慮して作っていますが、最終確認は各医院の責任で行ってください。
- Instagram API の仕様変更により調整が必要になることがあります（`scripts/instagram.py` の `API_VERSION`）。
