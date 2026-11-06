@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 7日分の投稿を生成します（画像・キャプション）。数分かかります...
set PYTHONIOENCODING=utf-8
python scripts\manual_batch.py --days 7
if errorlevel 1 (
  echo.
  echo エラーが出ました。先に「pip install -r requirements.txt」を実行してください。
  pause
  exit /b 1
)
start "" "output\manual\index.html"
pause
