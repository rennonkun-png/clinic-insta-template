"""Meta アプリのシークレットを config/operator.json に登録する（画面に表示せずに貼り付け）。"""
from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "config" / "operator.json"


def main() -> int:
    op = json.loads(P.read_text(encoding="utf-8"))
    print("Meta for Developers の「アプリの設定 → ベーシック」を開いてください。\n")
    app_id = input(f"アプリID（いまの登録: {op.get('ig_app_id')}。同じなら何も入れずに Enter）: ").strip()
    if app_id:
        if not app_id.isdigit():
            print("アプリIDは数字だけです。もう一度やり直してください。")
            return 1
        op["ig_app_id"] = app_id
    print("\napp secret の「表示」を押してコピーし、下に貼り付けて Enter を押してください。")
    print("（貼り付けても画面には何も表示されませんが、入力はされています。貼り付けは右クリックか Ctrl+V）")
    sec = getpass.getpass("app secret: ").strip()
    if not sec:
        print("何も入力されなかったので、変更しませんでした。")
        return 1
    if len(sec) != 32 or not all(c in "0123456789abcdef" for c in sec.lower()):
        print(f"注意: 入力された文字数は {len(sec)} 文字でした（通常は英数字32文字）。コピーした範囲を確認してください。")
        if input("このまま登録しますか？ (y/n): ").strip().lower() != "y":
            return 1
    op["ig_app_secret"] = sec
    P.write_text(json.dumps(op, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n登録しました（末尾 {sec[-4:]}）。このウィンドウは閉じて大丈夫です。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
