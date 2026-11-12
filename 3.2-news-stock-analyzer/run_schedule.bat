@echo off
REM ============================================================
REM  news-stock-workflow - weekdays 17:00 (NewsStockAnalyzer-Evening)
REM  Step 1-2 (news-collector, impact-analyzer): Claude Code headless (-p)
REM  Step 3-4 (report-printer, telegram-sender): python scripts
REM  Step 5: open daily_report.md
REM  Usage: run_schedule.bat          (full run)
REM         run_schedule.bat --check  (show settings only, no run)
REM ============================================================
setlocal
cd /d "%~dp0"

set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
set "PYTHON=C:\Python314\python.exe"
set "PYTHONIOENCODING=utf-8"
set "TOOLS=Read,Write,Edit,Glob,Grep,Bash(python:*),WebSearch,WebFetch,mcp__tavily__tavily_search,mcp__tavily__tavily_extract"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
if not exist logs mkdir logs
set "LOG=logs\schedule_%TODAY%.log"

if /i "%~1"=="--check" goto :check

echo ===== [%date% %time%] news-stock-workflow start ===== >> "%LOG%"

REM ---- Step 1-2 news-collector + impact-analyzer ----
"%CLAUDE%" -p --allowedTools "%TOOLS%" < schedule_prompt.txt >> "%LOG%" 2>&1
if errorlevel 1 echo [WARN] claude step returned error >> "%LOG%"

REM ---- freshness check: never send stale results as today's report ----
"%PYTHON%" check_fresh.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] news/analysis not updated for today - report and telegram skipped >> "%LOG%"
  endlocal & exit /b 1
)

REM ---- Step 3 report-printer ----
"%PYTHON%" report_printer.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] report-printer failed - workflow stopped >> "%LOG%"
  endlocal & exit /b 1
)

REM ---- Step 4 telegram-sender (failure is logged, continue) ----
"%PYTHON%" telegram_sender.py >> "%LOG%" 2>&1
if errorlevel 1 echo [WARN] telegram-sender failed - see logs\telegram_%TODAY%.log >> "%LOG%"

REM ---- Step 5 open report ----
start "" "daily_report.md"

echo ===== [%date% %time%] end ===== >> "%LOG%"

REM ---- delete logs older than 60 days ----
forfiles /p logs /m schedule_*.log /d -60 /c "cmd /c del @path" >nul 2>&1
forfiles /p logs /m telegram_*.log /d -60 /c "cmd /c del @path" >nul 2>&1

endlocal & exit /b 0

:check
echo DIR    = %cd%
echo TODAY  = %TODAY%
echo LOG    = %LOG%
if exist "%CLAUDE%" (echo CLAUDE = OK %CLAUDE%) else (echo CLAUDE = NOT FOUND %CLAUDE%)
if exist "%PYTHON%" (echo PYTHON = OK %PYTHON%) else (echo PYTHON = NOT FOUND %PYTHON%)
if exist schedule_prompt.txt (echo PROMPT = OK) else (echo PROMPT = NOT FOUND)
for %%f in (check_fresh.py report_printer.py telegram_sender.py .env) do (
  if exist %%f (echo FILE   = OK %%f) else (echo FILE   = NOT FOUND %%f)
)
endlocal & exit /b 0
