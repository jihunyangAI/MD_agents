@echo off
chcp 65001 > nul
setlocal
title 긴급 파일 전송 - 텔레그램 리스너

rem ============================================================
rem  긴급 파일 전송 서비스 - 텔레그램 상시 대기
rem  - commands/telegram-listener.md 절차를 Claude Code로 실행
rem  - 한 번에 10회(약 90분) 대기 후 새 세션으로 다시 시작 (대화 기록이 계속 쌓이지 않게)
rem  - 멈추려면 이 창에서 Ctrl+C 또는 창 닫기
rem ============================================================

cd /d "%~dp0"
set PYTHONUTF8=1
rem 저장된 장기 토큰(setx CLAUDE_CODE_OAUTH_TOKEN)을 바로 읽어 옴 - 로그아웃 없이 적용
for /f "skip=2 tokens=2,*" %%a in ('reg query HKCU\Environment /v CLAUDE_CODE_OAUTH_TOKEN 2^>nul') do set "CLAUDE_CODE_OAUTH_TOKEN=%%b"
if not exist logs mkdir logs

where claude > nul 2>&1
if errorlevel 1 (
  echo [오류] claude 명령을 찾을 수 없습니다. Claude Code 설치를 확인하세요.
  pause
  exit /b 1
)

echo.
echo  긴급 파일 전송 리스너를 시작합니다. (5초 간격으로 텔레그램 확인)
echo  ※ 같은 봇을 쓰는 "Claude 텔레그램"은 꺼 두세요.
echo  ※ 멈추려면 Ctrl+C
echo.

:loop
echo [%date% %time:~0,8%] 대기 세션 시작 >> logs\listener.log
claude -p "commands/telegram-listener.md 파일을 읽고 그 절차를 그대로 수행해. $ARGUMENTS 값은 10 이다. 이 프로젝트의 agents/, commands/, scripts/ 외의 작업은 하지 마." ^
  --model sonnet ^
  --permission-mode default ^
  --allowedTools "Read" "Bash(cd:*)" "Bash(python -X utf8 -I scripts/telegram_poll.py:*)" "Bash(python -X utf8 -I scripts/telegram_reply.py:*)" "Bash(python -X utf8 -I scripts/file_finder.py:*)" "Bash(python -X utf8 -I scripts/mail_sender.py:*)"
echo [%date% %time:~0,8%] 대기 세션 종료 (코드 %errorlevel%) >> logs\listener.log

rem 오류로 바로 끝났을 때 과도한 재시작을 막기 위해 10초 쉼
timeout /t 10 /nobreak > nul
goto loop
