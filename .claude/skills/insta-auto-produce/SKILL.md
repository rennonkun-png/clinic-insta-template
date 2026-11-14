---
name: insta-auto-produce
description: Instagram 自動投稿の「ネタの補充」を、裏で自動で行う手順。ネタの残りを数え、少なければ新しい投稿を作り、採点表（RUBRIC.md）の全項目が5点になるまで作り直してから投稿の列に足す。予定タスク（毎晩）から呼ばれるほか、「ネタを補充して」「医院のネタを作って」と言われたときに使う。
---

# ネタの自動補充（5点満点になるまで作り直す）

依頼主は旅河さん（英語が読めない。報告・メモ・コミットの文はすべて日本語）。
目的: 毎日の自動投稿が、ネタ切れで同じ投稿の出し直しにならないようにする。品質は「お客様（医院）に納品できる」こと。

**大原則**
- 採点表 `.claude/skills/insta-quality-check/RUBRIC.md` の**全項目が5点**の投稿だけを足す。4点以下が1つでもあれば直す。直しきれないものは捨てる（足さない）
- 採点は、作った本人ではない別のエージェントが行う。作った理由・意図は渡さない（作品と採点表だけを渡す）
- 毎日の投稿そのものには Claude を使わない（GitHub Actions のプログラムが行う）。Claude を使うのは、この補充のときだけ
- 既存の投稿（content/webmarketing.json など）は書き換えない。新しい投稿は `content/generated.json` に足す
- Instagram に直接投稿しない。config・ワークフロー・Secrets は変えない
- 途中で Claude の利用上限に当たったら、作業フォルダに途中経過を残して終わる。次の回は続きから始める

## 0. 作業フォルダと対象
- 作業フォルダ: `%USERPROFILE%\insta-work\<対象名>\`（一時フォルダではなく、消えない場所）。中に `log.md`（毎回の結果を追記）と `gen/`（下書き）を置く
- 対象（targets）は `.claude/skills/insta-auto-produce/targets.json` に書く。1件ごとに:
  - `name`（例: genova）、`repo`（例: rennonkun-png/clinic-insta-own）、`content_key`（例: webmarketing）、`threshold`（残りがこの本数以下で補充。既定14）、`batch`（1回に足す本数。既定30）、`approval`（"auto" = 合格したら自動で足す／"first" = 初回だけ旅河さんの OK を待つ）、`karte`（医院のときのカルテ JSON のパス）
- GitHub の操作には、テンプレートのフォルダの `config/operator.json` の `github_token` を使う。トークンは画面・ログ・コミットに絶対に出さない（`***` に置き換える）

## 1. 残りを数える（無料）
```
git clone（なければ）/ git pull で作業フォルダの repo/ を最新にする
python -X utf8 scripts/stock.py --root <作業フォルダ>/repo --threshold <threshold>
```
- 終了コード 0（補充は不要）なら、log.md に1行（日付・残り本数・使い切る日）を書いて終わる。旅河さんへの連絡はしない
- 終了コード 2 なら補充に進む

## 2. 新しいネタの題材を決める
- 既存の全投稿（content/*.json と content/generated.json）の title・id・要点と、state/posted.json を一覧にし、**同じ話題・同じ文例・同じ例え**を避ける
- GENOVA（院長向けの WEB 集患）: 院長が明日から自院で試せる具体的な話。ツールを使う話なら、確認済み URL（docs/production/CONTENT_SPEC.md）のツールだけ
- 医院: カルテ（docs/karte_schema.md の形）の `focus_treatments` を中心に、`not_offered` の診療は扱わない。HP（`hp_url`）の内容に合わせ、HP の文章は写さない。医療広告ガイドラインの確認は `anthropic-skills:medical-advertising-compliance` を使う
- 題材の一覧を `gen/topics.md` に書く（batch 本＋予備5本）

## 3. 下書き（10本ずつ、軽いモデルで）
- サブエージェント（model: sonnet）に10本ずつ任せる。渡すもの: `docs/production/CONTENT_SPEC.md`、RUBRIC.md、担当の題材、既存投稿の一覧（避ける話題）、出力先 `gen/batch_K.json`
- 各投稿に `category`（GENOVA は "webmarketing"）を必ず書く。`id` は既存と重ならない英小文字のハイフン区切り

## 4. 機械のチェック（無料・何度でも）
- 下書きを既存の投稿の後ろにつないだ一時ファイルを作り、`python -X utf8 scripts/quality_check.py <一時ファイル> --render --config <repo>/config/clinic.json` を走らせる。新しい投稿の E（エラー）・W（注意）を0件にする
- 写真: `python -X utf8 scripts/assign_photos.py <一時ファイル>` で1枚1回を割り当てる。足りない（終了コード1）ときは、ブラウザで Pexels（https://www.pexels.com/ja-jp/）の検索ページから集め、assets/photos と catalog.json に足す。写真の中の文字・ロゴ・顔を目で確かめ、だめなものは rejected に入れる
- 直しはサブエージェント（model: sonnet）に、エラーの文だけを渡して任せる

## 5. 採点（別の目・5点満点）
- 新しい投稿をすべて描画する（カルーセル全ページの一覧画像、リールは各型からコマを抜いた一覧画像）。手順は insta-quality-check の手順2と同じ
- 採点役のサブエージェント（model: opus）に、**一覧画像・投稿の JSON・RUBRIC.md だけ**を渡す。作った理由や前回の点数は渡さない
- 返してもらう形: 投稿ごと × 項目ごとの点数（1〜5）と、5点でない項目の具体的な直し方
- RUBRIC.md の「全体を見る項目」（並び・単調さ・写真の重複など）も、既存の投稿とつないだ状態で採点させる

## 6. 直して、もう一度採点（最大4回）
- 4点以下があった投稿だけ、直し役（sonnet）に「項目・点数・直し方」を渡して直す → 手順4の機械チェック → 手順5の採点
- 4回直しても5点にならない投稿は捨て、予備の題材で作り直す（予備も尽きたら、その回は合格した分だけ足す）
- 各回の点数を log.md に残す

## 7. 足す
- 合格した投稿を repo/content/generated.json の末尾に足す（GENOVA の並び順は config の schedule.order = "sequence"。既存の後ろに並ぶ）
- もう一度、全体で `quality_check.py`（E・W 0件）と `assign_photos.py` を通す
- `approval` が "first" で、まだ一度も OK をもらっていない対象は、ここで止めて旅河さんに見本を送り、OK を待つ（log.md に「承認待ち」と書く）
- それ以外は、repo にコミットして push（コミット文は日本語。末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。写真を足したときは assets/photos も含める。曲のファイル（mp3）は絶対に含めない
- push のあと、GitHub Actions の毎日投稿ワークフローを「テスト実行（dry_run）」で1回起動し、成功を確かめる

## 8. 旅河さんへの報告（日本語・短く）
- PushNotification（使えないときは SendUserFile）で: 足した本数、採点の結果（全項目5点になった本数／捨てた本数）、使い切る日がいつに延びたか、見本の一覧画像1〜2枚
- 失敗したとき（上限に当たった、写真が集まらない、push できない など）も、何ができて何が残ったかを正直に書く

## 新しい指摘を受けたら
旅河さんから新しい指摘があったら、RUBRIC.md に項目を足す（日付と言葉を残す）。機械で判定できるものは scripts/quality_check.py にもチェックを足す。
