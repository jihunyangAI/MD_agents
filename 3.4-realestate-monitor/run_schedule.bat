@echo off
REM property-monitor daily run (Task Scheduler: RealEstateMonitor-Daily, every day 17:40)
REM Steps 1,5,6 run as scripts. Steps 2~4 (web research) reuse the latest
REM transport/school/policy score files; refresh them manually with
REM the property-monitor command in Claude Code.
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PY=C:\Python314\python.exe
cd /d "%~dp0"
if not exist logs mkdir logs
set RUNLOG=logs\schedule_run.log

echo ===== %date% %time% ===== >> "%RUNLOG%"
echo [1] price-collector >> "%RUNLOG%"
"%PY%" price_collector.py >> "%RUNLOG%" 2>&1
echo [2-4] transport/school/policy: reuse existing score files >> "%RUNLOG%"
echo [5] value-analyzer >> "%RUNLOG%"
"%PY%" value_analyzer.py --no-alert >> "%RUNLOG%" 2>&1
echo [6] telegram-alert >> "%RUNLOG%"
"%PY%" telegram_alert.py >> "%RUNLOG%" 2>&1

REM keep logs for 90 days
forfiles /p logs /m run_*.md /d -90 /c "cmd /c del @path" > nul 2>&1
echo [done] %date% %time% >> "%RUNLOG%"
echo. >> "%RUNLOG%"
