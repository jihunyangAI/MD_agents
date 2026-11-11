@echo off
REM ============================================================
REM  price-track-workflow - runs every day at 16:45 (PriceTracker-Daily)
REM  Step 1 (price-scraper, web search): Claude Code headless (-p)
REM  Step 2-4 (recorder / alert / chart): python scripts
REM  Step 5: completion message -> log
REM  Usage: run_schedule.bat          (full run)
REM         run_schedule.bat --check  (show settings only, no run)
REM ============================================================
setlocal
cd /d "%~dp0"

set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
set "PYTHON=C:\Python314\python.exe"
set "PYTHONIOENCODING=utf-8"
set "TOOLS=Read,Write,Glob,Grep,Bash(python:*),WebSearch,WebFetch,mcp__tavily__tavily_search,mcp__tavily__tavily_extract"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
if not exist logs mkdir logs
set "LOG=logs\schedule_%TODAY%.log"

if /i "%~1"=="--check" goto :check

echo ===== [%date% %time%] price-track-workflow start ===== >> "%LOG%"

REM ---- Step 1 price-scraper ----
"%CLAUDE%" -p --allowedTools "%TOOLS%" < schedule_prompt.txt >> "%LOG%" 2>&1
if errorlevel 1 echo [WARN] price-scraper failed - continuing with existing scraped_prices.json >> "%LOG%"

REM ---- Step 2 price-recorder (stop on failure) ----
"%PYTHON%" price_recorder.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] price-recorder failed - workflow stopped >> "%LOG%"
  endlocal & exit /b 1
)

REM ---- Step 3 price-alert (failure is logged, continue) ----
"%PYTHON%" price_alert.py >> "%LOG%" 2>&1
if errorlevel 1 echo [WARN] price-alert failed >> "%LOG%"

REM ---- Step 4 price-chart ----
"%PYTHON%" price_chart.py >> "%LOG%" 2>&1
if errorlevel 1 echo [WARN] price-chart failed >> "%LOG%"

REM ---- Step 5 completion message ----
"%PYTHON%" workflow_summary.py >> "%LOG%" 2>&1

echo ===== [%date% %time%] end ===== >> "%LOG%"

REM ---- delete schedule logs older than 30 days ----
forfiles /p logs /m schedule_*.log /d -30 /c "cmd /c del @path" >nul 2>&1

endlocal & exit /b 0

:check
echo DIR    = %cd%
echo TODAY  = %TODAY%
echo LOG    = %LOG%
if exist "%CLAUDE%" (echo CLAUDE = OK %CLAUDE%) else (echo CLAUDE = NOT FOUND %CLAUDE%)
if exist "%PYTHON%" (echo PYTHON = OK %PYTHON%) else (echo PYTHON = NOT FOUND %PYTHON%)
if exist schedule_prompt.txt (echo PROMPT = OK) else (echo PROMPT = NOT FOUND)
for %%f in (price_recorder.py price_alert.py price_chart.py workflow_summary.py watchlist.json) do (
  if exist %%f (echo FILE   = OK %%f) else (echo FILE   = NOT FOUND %%f)
)
endlocal & exit /b 0
