@echo off
REM exchange-workflow daily run (Task Scheduler: every day 09:00)
set PYTHONIOENCODING=utf-8
set PY=C:\Python314\python.exe
cd /d "%~dp0"
if not exist logs mkdir logs
set RUNLOG=logs\schedule_run.log

echo ===== %date% %time% ===== >> "%RUNLOG%"
echo [1] rate-collector >> "%RUNLOG%"
"%PY%" rate_collector.py >> "%RUNLOG%" 2>&1
if errorlevel 1 goto done
echo [2] rate-alert >> "%RUNLOG%"
"%PY%" rate_alert.py >> "%RUNLOG%" 2>&1

:done
echo [3] done >> "%RUNLOG%"
"%PY%" -c "from datetime import datetime,timedelta,timezone;print('\ud658\uc728\ud655\uc778\uc644\ub8cc - '+datetime.now(timezone(timedelta(hours=9))).strftime('%%Y-%%m-%%d %%H:%%M')+' KST')" >> "%RUNLOG%" 2>&1
echo. >> "%RUNLOG%"
