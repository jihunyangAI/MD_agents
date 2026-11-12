@echo off
REM ============================================================
REM  sns-trend-workflow weekly run (Task: SNSTrendMonitor-Weekly, MON 18:00)
REM  1 keyword-collector -> 2 trend-analyzer -> 3 report-composer -> 4 notifier
REM  Usage: run.bat          (full run, sends email + telegram)
REM         run.bat test     (reuse today's raw posts, no sending)
REM ============================================================
chcp 65001 > nul
setlocal

cd /d "%~dp0"
set "PY=C:\Python314\python.exe"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
REM claude CLI (keyword extraction / summary) must be on PATH for the scheduled task
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

if not exist logs mkdir logs
for /f "usebackq" %%i in (`%PY% -c "import datetime;print(datetime.date.today())"`) do set "TODAY=%%i"
set "LOG=logs\run_%TODAY%.log"

set "COLLECT_OPT="
set "NOTIFY_OPT="
if /i "%~1"=="test" (
    set "COLLECT_OPT=--reuse-raw"
    set "NOTIFY_OPT=--dry-run"
)

echo ===== %DATE% %TIME% sns-trend-workflow start (%~1) ===== >> "%LOG%"

echo [1/4] keyword-collector >> "%LOG%"
"%PY%" scripts\keyword_collector.py %COLLECT_OPT% >> "%LOG%" 2>&1
echo   exit=%ERRORLEVEL% >> "%LOG%"

echo [2/4] trend-analyzer >> "%LOG%"
"%PY%" scripts\trend_analyzer.py >> "%LOG%" 2>&1
echo   exit=%ERRORLEVEL% >> "%LOG%"

echo [3/4] report-composer >> "%LOG%"
"%PY%" scripts\report_composer.py >> "%LOG%" 2>&1
echo   exit=%ERRORLEVEL% >> "%LOG%"

REM notifier always runs: it reports a missing report as a send error
echo [4/4] notifier >> "%LOG%"
"%PY%" scripts\notifier.py %NOTIFY_OPT% >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo   exit=%RC% >> "%LOG%"

REM keep logs for the last 12 weeks (84 days)
forfiles /p logs /m *.log /d -84 /c "cmd /c del @path" > nul 2>&1

echo ===== %DATE% %TIME% sns-trend-workflow end (rc=%RC%) ===== >> "%LOG%"
endlocal & exit /b %RC%
