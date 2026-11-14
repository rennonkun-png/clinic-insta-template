# 分析サイトのデータの形（schema_version: 1）

分析サイト（`analytics/site/`）は、`site/data/` にある JSON ファイルだけを読んで、ブラウザの中で集計とグラフ表示をします。
毎晩の記録プログラムは、この形でファイルを書き出してください。試作データは `analytics/make_sample.py` で作れます。

## 共通の決まり

- 文字コードは UTF-8。日付は `YYYY-MM-DD`（日本時間）、日時は `YYYY-MM-DDTHH:MM:SS+09:00`。
- 数値が取れなかったときは `null`（0 と区別する）。
- 記録は「前日分までを毎晩1回」が前提。サイトは `accounts.json` の `last_date` までを表示します。
- 記録前の期間を選ぶと、サイトは「この期間はまだ記録がありません（記録開始: ○月○日）」と出します。
- ファイルの置き場所:

```
data/
  accounts.json
  <アカウントid>/
    daily.json
    posts.json
    post_daily/2026-11.json   … 月ごとに分ける
    audience.json
    competitors.json
    review.json
```

## data/accounts.json — アカウントの一覧

```json
{
  "generated_at": "2026-11-15T03:00:00+09:00",
  "schema_version": 1,
  "accounts": [
    {
      "id": "genova",                 // フォルダ名にも使う（英数字と _ のみ）
      "name": "GENOVA",               // 画面に出す名前
      "username": "genova_xxx",       // Instagram のユーザー名（@なし）
      "kind": "自社",                 // 「自社」か「医院」
      "record_start": "2026-08-17",   // 記録を始めた日
      "last_date": "2026-11-14",      // 記録がある最後の日
      "post_daily_months": ["2026-08", "2026-09"],  // post_daily/ にある月の一覧
      "sample": false                 // 試作データなら true（画面に「サンプル」と出る）
    }
  ]
}
```

## <id>/daily.json — アカウントの日ごとの数字

```json
{ "days": [ { "date": "2026-11-14", "followers": 1083, "follows_new": 5, "unfollows": 1,
              "reach": 412, "views": 905, "profile_views": 31, "website_clicks": 4,
              "accounts_engaged": 22, "total_interactions": 30,
              "likes": 21, "comments": 1, "saves": 6, "shares": 2 } ] }
```

| 項目 | 意味 | Instagram API の元 |
|---|---|---|
| followers | その日の終わりのフォロワー数 | `followers_count`（毎晩の値を保存） |
| follows_new / unfollows | その日に増えた・減ったフォロー | `follows_and_unfollows`（内訳 follow_type） |
| reach | その日に見た人の数 | `reach`（period=day） |
| views | その日の表示回数 | `views` |
| profile_views | プロフィールが見られた回数 | `profile_views`（取れない場合は `profile_links_taps` 等で代替、無ければ null） |
| website_clicks | プロフィールのリンクが押された回数 | `website_clicks` |
| accounts_engaged | 反応した人の数 | `accounts_engaged` |
| total_interactions, likes, comments, saves, shares | その日の反応の数 | 同名の指標 |

- 1年で約365行・数十KB なので、分けずに1ファイルで持ちます（3年を超えたら `daily/2027.json` のように年ごとに分ける）。
- `reach` と `accounts_engaged` は日ごとの人数です。サイトで期間を合計すると「同じ人が別の日に見た分も重ねて数えた値」になります（画面の説明にも書いてあります）。

## <id>/posts.json — 投稿の一覧

```json
{ "posts": [ { "id": "1789...", "date": "2026-11-14", "time": "19:00",
               "permalink": "https://www.instagram.com/p/xxxx/",
               "format": "リール", "reel_style": "telop", "topic": "口コミ",
               "title": "口コミの返し方", "caption_head": "投稿文の最初の100字程度",
               "thumbnail_url": null } ] }
```

- `format` は「リール」「カルーセル」「画像」のどれか。
- `reel_style` はリールのときだけ `screen`（スマホ操作型）/ `telop`（大きな文字の型）/ `photo`（写真ストーリーの型）。それ以外は null。
- `topic` は話題の分類（自動投稿の元データの分類名をそのまま入れる）。`title` は自動投稿の元データの題名。
- `thumbnail_url` は任意。Instagram の画像 URL は期限切れになるので、入れるなら自前で保存した画像の相対パス（例 `thumbs/1789.jpg`）にする。

## <id>/post_daily/YYYY-MM.json — 投稿ごと×日ごとの累計

ファイルを小さくするため、項目名は先頭に1回だけ書き、行は配列にします。

```json
{ "metrics": ["reach","views","likes","comments","saves","shares","follows",
              "profile_visits","reel_avg_watch_sec","reel_skip_rate"],
  "rows": [ ["1789...", "2026-11-14", 812, 1544, 31, 2, 18, 7, 4, 15, 7.8, 52.3] ] }
```

- 行は `[投稿id, 日付, metrics の順の値...]`。その日の終わり時点の**累計**です。
- 期間の値 = 期間の最終日の累計 − 期間の前日の累計（前日の行が無く、投稿日が記録開始より前なら、最初に記録した日の累計を起点にする）。
- `reel_avg_watch_sec`（平均視聴時間・秒）と `reel_skip_rate`（スキップ率・％）は累計ではなく、その日時点の値。リール以外は null。
- 記録は投稿日から最低90日続ける。それ以降は止めてよい（止めた後の期間は増加0として扱う）。
- 月ごとに分けるので、ふつうは1ファイル 100KB 前後です。サイトは選んだ期間に必要な月だけ読みます。新しい月のファイルを作ったら `accounts.json` の `post_daily_months` に足してください。

## <id>/audience.json — フォロワーの属性（スナップショット）

```json
{ "snapshots": [ { "date": "2026-11-14", "followers": 1083,
    "gender_age": [ { "age": "25-34", "gender": "F", "count": 210 } ],
    "cities":    [ { "name": "渋谷区", "count": 80 } ],
    "regions":   [ { "name": "東京都", "count": 300 } ],
    "countries": [ { "name": "日本", "count": 1040 } ],
    "online_hours": [[0,0,...24個], ...7行] } ] }
```

- 週1回などの間隔で追加します。サイトは選んだ期間の最終日以前で一番新しいものを使います。
- `gender` は `F`（女性）/ `M`（男性）/ `U`（不明）。`age` は Instagram の区分（13-17, 18-24, 25-34, 35-44, 45-54, 55-64, 65+）。
- `online_hours` は 曜日（月=0 … 日=6）× 時（0〜23時）の、オンラインだったフォロワーの数。Instagram の `online_followers` を曜日ごとに保存したもの。
- Instagram はフォロワーが少ないと属性を返さないことがあります。その時は配列を空にします。

## <id>/competitors.json — 競合のスナップショット

```json
{ "competitors": [ { "id": "self", "name": "自分", "username": "...", "is_self": true },
                   { "id": "c1", "name": "競合A", "username": "...", "is_self": false } ],
  "snapshots": [ { "date": "2026-11-14", "competitor_id": "c1", "followers": 2300,
                   "media_count": 410, "posts_per_week": 3.5, "avg_likes": 41.2,
                   "avg_comments": 1.8, "engagement_rate": 1.87, "reel_share": 45.0,
                   "top_posts": [ { "date": "2026-11-10", "format": "リール", "permalink": "...",
                                    "caption_head": "...", "likes": 120, "comments": 4 } ] } ] }
```

- `scripts/competitors.py` の週1回の比較で取れる公開情報（Business Discovery）から作ります。
- 比べやすいように、自分のアカウントも `is_self: true` で同じ形で入れます。
- `engagement_rate` は（平均いいね＋平均コメント）÷フォロワー×100（％）。`reel_share` は直近投稿に占めるリールの割合（％）。
- 週1回・1社あたり1行なので、1年でも数百行。分けずに1ファイルで持ちます。

## <id>/review.json — 確認待ちの投稿（ページは準備中）

```json
{ "items": [ { "id": "...", "created_at": "...", "scheduled_for": "...", "format": "カルーセル",
               "reel_style": null, "topic": "...", "title": "...", "caption": "...",
               "media_urls": ["review/xxx_1.jpg"], "status": "pending",
               "quality_notes": ["品質チェックの指摘"], "decided_by": null,
               "decided_at": null, "comment": null } ] }
```

- `status` は `pending`（確認待ち）/ `approved`（承認）/ `rejected`（差し戻し）。
- 承認・差し戻しの書き込み先は、ログインの仕組みと一緒にあとで決めます（静的サイトだけでは書き込めないため）。

## 画面で計算する指標（ファイルには持たない）

| 指標 | 計算 |
|---|---|
| 反応の合計 | いいね＋コメント＋保存＋シェア |
| 反応率 | 反応の合計 ÷ リーチ |
| 保存率 | 保存 ÷ リーチ |
| フォロワーの純増 | follows_new − unfollows |
| 投稿数 | 期間内に投稿した数 |
