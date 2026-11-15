"""競合の候補アカウントが Instagram から読めるか（ビジネス／クリエイターの公開アカウントか）を確かめる。

投稿用リポジトリの「競合アカウントの比較」ワークフローを、試し読みのモードで動かし、結果を表示する。
Instagram のトークンは GitHub の Secrets にあるので、手元には置かない。

使い方: python -X utf8 check_accounts.py <owner/repo> ユーザー名 [ユーザー名 ...]
出力: 1行目以降に「OK ユーザー名」「NG ユーザー名 理由」と、読めたアカウントの比較表
"""
import io
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

OP = Path(__file__).resolve().parents[3] / "config" / "operator.json"


def main() -> int:
    repo, names = sys.argv[1], [n.lstrip("@") for n in sys.argv[2:]]
    tok = json.loads(OP.read_text(encoding="utf-8"))["github_token"]
    h = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}/actions/workflows/competitors.yml"
    get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=h))  # noqa: E731
    before = json.load(get(api + "/runs?per_page=1"))["workflow_runs"]
    last_id = before[0]["id"] if before else 0
    body = json.dumps({"ref": "main", "inputs": {"check": " ".join(names)}}).encode()
    urllib.request.urlopen(urllib.request.Request(api + "/dispatches", data=body, method="POST", headers=h))
    run = None
    for _ in range(90):  # 最大15分
        time.sleep(10)
        runs = json.load(get(api + "/runs?per_page=1"))["workflow_runs"]
        if runs and runs[0]["id"] != last_id and runs[0]["status"] == "completed":
            run = runs[0]
            break
    if not run:
        print("時間内に終わりませんでした")
        return 1
    z = zipfile.ZipFile(io.BytesIO(get(run["logs_url"]).read()))
    text = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist() if "/" not in n)
    ok, ng = [], []
    for line in text.splitlines():
        line = line[29:].replace(tok, "***")
        if "読めました: @" in line:
            ok.append(line.split("@", 1)[1].strip())
        elif "読めませんでした: @" in line:
            ng.append(line.split("@", 1)[1].strip())
    for n in ok:
        print("OK", n)
    for n in ng:
        print("NG", n)
    for line in text.splitlines():
        if line[29:].startswith(("|", "- いいね", "## @")):
            print(line[29:].replace(tok, "***"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
