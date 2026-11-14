---
name: insta-auto-produce
description: Instagram 自動投稿の「毎週のネタづくり」を裏で自動で行う手順。毎週月曜に、分析データを見て次の週の7本を作り、採点表（RUBRIC.md）の全項目5点まで直し、分析サイトの「確認待ち」に置いて木曜の夜を期限に確認を待つ。期限後（または全部 OK）に投稿の予定へ入れる。予定タスク（毎晩）から呼ばれるほか、「ネタを作って」「医院のネタを作って」と言われたときに使う。
---

# 毎週のネタづくり（作る → 確認待ち → 期限後に自動で予定へ）

依頼主は旅河さん（たびかわ。「旅川」と書かない。英語が読めない。報告・メモ・コミット文・カレンダーの文はすべて日本語）。
品質の基準は「お客様（医院）に納品できる」こと。

**大原則**
- 採点表 `.claude/skills/insta-quality-check/RUBRIC.md` の**全項目が5点**の投稿だけを確認待ちに出す。採点は作った本人ではない別のエージェント（作った理由は渡さない）
- 旅河さんの確認は**任意**。期限（その週の木曜 23:59 日本時間）までは予定に入れずに待ち、期限を過ぎたら自動で入れる。全部に OK が付いたら期限を待たずに入れる
- 毎日の投稿・毎晩の記録には Claude を使わない（GitHub Actions のプログラム）。Claude を使うのは、この手順のときだけ
- Instagram に直接投稿しない。config・ワークフロー・Secrets は変えない。既存の content/webmarketing.json などは書き換えない
- トークン（config/operator.json）は画面・ログ・コミットに出さない。曲のファイル（mp3）は公開リポジトリに入れない
- Claude の利用上限に当たったら、作業フォルダに途中経過を残して終わる。次の回は続きから

## 場所
- テンプレート（作業の起点）: C:\Users\user\Desktop\インスタ
- 作業フォルダ（消えない場所）: `%USERPROFILE%\insta-work\<対象名>\`。`log.md`（毎回1行以上）、`repo/`（投稿用リポジトリの clone）、`analytics/`（分析リポジトリの clone）、`week/<週の月曜の日付>/`（下書き・描画物・状態 state.json）
- 対象の一覧: `.claude/skills/insta-auto-produce/targets.json`（name, repo, content_key, analytics_account, approval など）
- 分析リポジトリ（非公開）: rennonkun-png/insta-analytics。サイトは https://insta-analytics-jvi.pages.dev （Google ログイン）
  - 確認待ちの一覧: `site/data/<account>/review.json`、旅河さんの判断: `site/data/<account>/review_decisions.json`、描画物: `site/review/<account>/<週>/`
- GitHub 操作は config/operator.json の github_token（https://x-access-token:***@github.com/... で push。出力は *** に置き換える）

## 毎晩やること（予定タスクから。上から順に、当てはまるものだけ）

### A. 状態を読む（無料）
1. repo/ と analytics/ を pull。`python -X utf8 scripts/stock.py --root <repo>` で在庫を数える
2. 今週の state.json（無ければ「まだ作っていない」）と review_decisions.json を読む
3. 何もすることが無ければ log.md に1行書いて終わる（連絡しない）

### B. 月曜（日本時間）で、今週の分をまだ作っていない → 作る
1. **データを読む**（記録が3週間分以上あるとき）: analytics/site/data/<account>/posts.json と post_daily から、投稿後7日時点の「リーチ」「保存率」「シェア」「フォロー」を、話題（topic）・形式・リールの型・曜日ごとに比べ、伸びた傾向と伸びなかった傾向をメモ（gen/insights.md）。競合（competitors.json）の反応が多い投稿の話題も見る。3週間未満なら採点表中心で作る
2. **次の週（来週の月〜日）の7本を作る**。日付ごとの形式は config の formats.reel_weekdays で決まる（その日がリールの日ならリール向けの台本・reel を必ず入れる）。各投稿に `"date": "YYYY-MM-DD"` を付ける（common.pick_post は date が今日の投稿を最優先で出す）。`category` も必ず付ける。話題・文例・例え・写真は既存の全投稿と重ねない。書き方は docs/production/CONTENT_SPEC.md
   - 下書きはサブエージェント（model: sonnet）に、直しも sonnet、採点だけ opus
3. **機械のチェック → 採点 → 直す**（最大4回）: `scripts/quality_check.py --render`（E・W 0件）、`scripts/assign_photos.py`（写真が足りなければ Pexels から集める）、全ページ・リールを描画して採点役に渡す。5点にならないものは予備の題材で作り直す
4. **描画物を確認待ちに出す**: カルーセルは全ページの jpg、リールは mp4（声・BGM付き。BGM は非公開の genova-insta-assets の曲。無ければ自作の曲）を analytics/site/review/<account>/<週>/ に置き、review.json に7件を足す（id, date, format, reel_style, topic, title, caption, media_urls, quality_notes, revision: 1, status: pending）。`deadline` は今週の木曜 23:59（+09:00）。analytics に commit・push（Cloudflare が1〜2分で反映）
5. **Google カレンダー**: 予定「インスタ投稿の確認（期限）」を木曜 23:00〜23:59 に作る。説明に「確認待ち ○本」「確認ページ https://insta-analytics-jvi.pages.dev/ の『確認待ち』」「期限を過ぎたら自動で採用されます」。通知は前日（水曜）19:00 ごろと当日 18:00。event id を state.json に保存
6. **旅河さんに通知**（PushNotification、無ければ SendUserFile）: 「来週の投稿7本が確認待ちです。期限は木曜23:59。見なくても期限後に自動で採用されます」と、データから変えた点を1〜2行
7. state.json に「作成済み・期限・各投稿の revision」を保存。log.md に記録

### C. 確認待ちの期間中（毎晩）
- review_decisions.json に「直してほしい（fix）」があり、その revision の直しがまだ → コメントの内容で直す（必要なら再採点）→ 描画し直して差し替え、revision を1増やし status を pending に戻す → push。直した内容を通知で一言
- 直してほしいの内容は、採点表 RUBRIC.md の末尾「新しい指摘」に日付つきで足す（同じことを二度言わせない）
- 全部の投稿が approved（OK）になったら、期限を待たずに D へ

### D. 期限を過ぎた（金曜の回）または全部 OK → 予定に入れる
1. 採用する投稿: approved と、何も選ばれなかったもの。fix のものは直した版（直しが間に合わなければ、直す前の版のうち採点5点のもの）。rejected（使わない）は外し、予備の題材から作った投稿で埋める（その分は確認なしで採用）
2. repo/content/generated.json に足す（date 付き）。`scripts/quality_check.py`（E・W 0件）を全体で通す
3. repo に commit・push（日本語のコミット文、末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。毎日投稿のワークフローを dry_run で1回動かして成功を確かめる
4. review.json の該当の投稿を status: scheduled にして analytics に push。カレンダーの予定を「確認済み（○本を予定に入れました）」に更新
5. 旅河さんに通知: 入れた本数、使わないにした分の置き換え、直した点

### E. 安全のための補充
- stock.py で在庫が7日分を切っていたら、曜日に関係なく B を行う（確認期限は作った日の3日後の 23:59）

## 医院の対象（targets.json の approval が "first"）
- 初回は期限で自動採用しない。旅河さんの OK を待つ（state.json に「初回承認待ち」）。2回目からは上と同じ
- カルテ（docs/karte_schema.md）・医院カルテ（clinic_profile.md）の範囲で作る。医療広告ガイドラインは `anthropic-skills:medical-advertising-compliance` で確認

## 新しい指摘を受けたら
旅河さんから新しい指摘があったら RUBRIC.md に項目を足す（日付と言葉を残す）。機械で判定できるものは scripts/quality_check.py にもチェックを足す。
