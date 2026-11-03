@echo off
REM Komite dongusu: 5 dakikalik tarama + 1 dakikalik tetik izleme.
REM Kapatmak icin pencereyi kapat / Ctrl+C.
cd /d "%~dp0.."
start "komite-tarama" python -u tools\scan.py --watch --interval 300 --auto
python -u tools\trigger_watch.py --watch --interval 60
