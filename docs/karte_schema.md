# 医院カルテ（karte.json）の項目一覧

`docs/karte.html` で作られるカルテの中身です。自動制作の仕組みはこの表を見て、カルテの値を読み取ります。

## 全体の形

```json
{
  "version": 1,
  "created_at": "2026-11-14T13:47:01.146Z",
  "answers": { "clinic_name": "さくら歯科", "...": "..." },
  "unsure_keys": ["design_mood", "voice"]
}
```

| 項目 | 意味 |
|---|---|
| `version` | カルテの形の版。いまは `1` |
| `created_at` | 作った日時（世界標準時、ISO 形式） |
| `answers` | 各質問の答え（下の表） |
| `unsure_keys` | 「わからない」を選んだ質問のキー。おすすめ値が入っているもの、または「あとで確認」のもの。HPの確認や医院への聞き直しの対象 |

## 値のきまり

- `answers` には下の表のキーが**すべて**入ります。
- `null` … 空欄、または前の答えにより質問を出さなかった（該当なし）。
- 複数選べる項目は配列。何も選んでいなければ `[]`。
- 「わからない」を選んだ場合、おすすめがある質問はおすすめ値が入ります（`unsure_keys` にも入る）。おすすめがない事実の質問（診療科・休診日）は `[]` になり、HPから確認します。
- 曜日のコード: `mon` 月 / `tue` 火 / `wed` 水 / `thu` 木 / `fri` 金 / `sat` 土 / `sun` 日 / `holiday` 祝日

## 各項目

### 基本

| キー | 表示名 | 値 | 既定（おすすめ） |
|---|---|---|---|
| `hp_url` | ホームページ | 文字（URL）または `null` | なし |
| `clinic_name` | 医院名 | 文字（必須） | なし |
| `specialties` | 診療科 | 配列: `dentistry` 歯科 / `orthodontics` 矯正歯科 / `pediatric_dentistry` 小児歯科 / `internal_medicine` 内科 / `dermatology` 皮膚科 / `cosmetic_dermatology` 美容皮膚科 / `pediatrics` 小児科 / `otolaryngology` 耳鼻咽喉科 / `ophthalmology` 眼科 / `orthopedics` 整形外科 / `gynecology` 婦人科 / `gastroenterology` 消化器内科 / `psychiatry` 心療内科・精神科 / `other` その他 | なし（HPで確認） |
| `specialties_other` | その他の診療科 | 文字。`specialties` に `other` があるときだけ。ほかは `null` | なし |
| `area` | 地域（市区町村） | 文字 | なし |
| `director_name` | 院長名 | 文字 | なし |
| `closed_days` | 休診日 | 曜日コードの配列 | なし（HPで確認） |

### 方針

| キー | 表示名 | 値 | 既定（おすすめ） |
|---|---|---|---|
| `audience` | 見てほしい人 | 配列: `new_patients` 新しい患者さん / `current_patients` 通院中の患者さん / `recruit` 求人・採用 | `["new_patients"]` |
| `recruit_roles` | 募集している職種 | 文字の配列。`audience` に `recruit` があるときだけ。ほかは `null` | なし |
| `focus_treatments` | 力を入れたい診療 | 文字の配列（1行1つ） | なし |
| `not_offered` | 行っていない診療 | 文字。この診療は投稿で取り上げない | なし |
| `disclose` | 出してよい情報 | 配列: `equipment` 設備 / `interior` 院内の写真 / `staff` スタッフ紹介 / `price` 料金 / `self_pay` 自費診療。**入っていない情報は投稿に出さない** | `["equipment","interior"]` |

`price` または `self_pay` があるときは、医療広告ガイドラインにより治療の内容・費用・主なリスクや副作用を必ず併記する。`staff` はスタッフ本人の同意が前提。

### 見た目

| キー | 表示名 | 値 | 既定（おすすめ） |
|---|---|---|---|
| `design_color` | 医院の色 | `match_hp` HPの色に合わせる / `calm_blue` 落ち着いた青系 / `soft_pink` やわらかいピンク系 / `green` 緑系 / `custom` 指定 | `match_hp` |
| `design_color_custom` | 指定した色 | `#RRGGBB`。`design_color` が `custom` のときだけ | なし |
| `design_mood` | 雰囲気 | `friendly` 親しみやすい / `clean_trust` 清潔・信頼 / `elegant` 上品 | `clean_trust` |

### 人物

| キー | 表示名 | 値 | 既定（おすすめ） |
|---|---|---|---|
| `person_mode` | 人物の出し方 | `photo_cutout` 先生の写真を切り抜いて使う / `photo_illust` 先生の写真を元にしたイラスト / `fictional_illust` 架空の先生のイラスト（「イメージ」と表示し、名前は付けない） / `none` 人物は出さない | `photo_cutout` |
| `person_consent` | 顔・写真使用の書面同意 | `received` もらった / `pending` これからもらう。`person_mode` が `photo_cutout` か `photo_illust` のときだけ。**`pending` の間は先生の写真・イラストを使わない** | なし（わからない→`pending`） |
| `person_photos` | 使う写真 | `use_hp` HPの写真（使用可否を医院に確認） / `send_new` 新しく撮って送ってもらう / `later` あとで決める。出す条件は `person_consent` と同じ | `use_hp` |
| `illust_style` | イラストのタッチ | `soft` やわらかい手描き風 / `line` すっきりした線の絵 / `watercolor` 水彩風。`person_mode` が `photo_illust` か `fictional_illust` のときだけ | `soft` |

### 動画

| キー | 表示名 | 値 | 既定（おすすめ） |
|---|---|---|---|
| `voice` | 読み上げ | `ai_voice` AI音声（画面に「AI音声」と表示） / `none` 声なし | `ai_voice` |
| `voice_style` | 先生が話す形にするか | `narrator` しない（ナレーター） / `as_doctor` する（口は動かさない・「AI音声」表示）。`voice` が `ai_voice` かつ `person_mode` が `none` 以外のときだけ。`null` はナレーター扱い | `narrator` |
| `bgm` | BGM | `stock` 素材サイトの曲 / `original` 自作の曲 / `none` なし | `stock` |

### 投稿

| キー | 表示名 | 値 | 既定（おすすめ） |
|---|---|---|---|
| `post_days` | 投稿する曜日 | `daily` 毎日 / `weekdays` 平日のみ / `custom` 指定 | `daily` |
| `post_days_custom` | 指定した曜日 | 曜日コードの配列（1つ以上）。`post_days` が `custom` のときだけ | なし |
| `reel_ratio` | リールの本数 | `w4` 週4本 / `w2` 週2本 / `w6plus` 週6本以上（残りは画像投稿） | `w4` |
| `content_mix` | 中身の割合（お役立ち:医院紹介:お知らせ） | `useful` 7:2:1 / `clinic_intro` 5:4:1 / `news` 5:2:3 | `useful` |
| `cta` | 締めの誘導 | 配列: `profile_link` プロフィールのリンク / `web_booking` Web予約 / `phone` 電話 / `line` LINE。`[]` のときは `profile_link` 扱い | `["profile_link"]` |
| `hashtags` | 固定ハッシュタグ | 文字の配列（`#` なし、最大5個）。`[]` のときは制作側で選ぶ | なし |

### 確認

| キー | 表示名 | 値 | 既定（おすすめ） |
|---|---|---|---|
| `ai_disclosure` | 「AI作成」表示の確認 | 常に `true`（確認しないとカルテを作れない）。AIで作った画像・声を使う投稿には Instagram の「AI作成」表示を必ず付ける | `true`（必須） |
| `notes` | その他メモ | 文字 | なし |

## 画面について

- 下書きの貼り付け: `{"answers":{...}}` または答えだけの `{...}` を受け付けます。値はコード（`green`）でも表示名（`緑系`）でも可。`ai_disclosure` は貼り付けでは入らず、必ず画面で確認します。
- 入力の途中は、ブラウザの `localStorage`（キー `clinic_karte_draft_v1`）に保存されます。
