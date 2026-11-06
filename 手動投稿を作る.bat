@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if exist "config\genova.json" set CLINIC_CONFIG=config\genova.json
if not "%~1"=="" set CLINIC_CONFIG=%~1
echo 7日分の投稿を生成します（画像・キャプション）。数分かかります...
python scripts\manual_batch.py --days 7
if errorlevel 1 (
  echo.
  echo エラーが出ました。先に「pip install -r requirements.txt」を実行してください。
  pause
  exit /b 1
)
start "" "output\manual\index.html"
pause
