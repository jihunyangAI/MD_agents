# MD_agents

Claude Code로 만든 **Markdown 기반 에이전트·워크플로우** 실습 모음입니다.
각 실습 폴더의 `CLAUDE.md`가 작업 지침서 역할을 하며, 에이전트(`agents/*.md`)와 워크플로우(`workflows/*.md`)는
YAML 프런트매터 + 본문 형식의 Markdown 파일로 정의되어 있습니다.

## 실습 목록

| 폴더 | 내용 | 주요 산출물 |
|------|------|-------------|
| [`1.1-family-travel-planner`](1.1-family-travel-planner) | 가족 여행 정보(여행지·기간·예산·구성)를 입력하면 일자별 코스, 숙소 추천, 예산 검증, 최종 여행 계획서를 생성 | `family-travel-workflow.json`, `travel_plan.md`, `budget_summary.json` |
| [`1.2-schedule-assistant`](1.2-schedule-assistant) | 자연어 일정 텍스트를 파싱해 캘린더 충돌을 확인하고 Google Calendar 등록·초대 메일까지 처리 | `agents/schedule-parser.md` 외 3개, `workflows/schedule-workflow.md` |
| [`2.1-mail-agent`](2.1-mail-agent) | Gmail 미열람 메일을 긴급/중요/일반으로 분류하고 회신 초안을 Gmail 초안함에 저장, 결과를 텔레그램으로 알림 | `agents/mail-classifier.md`, `agents/reply-drafter.md`, `workflows/mail-workflow.md` |
| [`2.2-file-sender`](2.2-file-sender) | 텔레그램으로 "기획서 보내줘"라고 보내면 PC에서 파일을 찾아 Gmail로 첨부 발송하고 결과를 텔레그램으로 알림 | `agents/command-parser.md` 외 2개, `commands/file-transfer.md`, `check_once.bat` |

## 2.1 mail-agent 구조

```
mail_config.json ─┐
.env.local ───────┤   (텔레그램 토큰·chat_id — 저장소에 포함되지 않음)
                  ▼
[mail-classifier] → classified_mails.json
        │              (키워드·발신자 규칙 + Claude 문맥 분석, 신뢰도 높은 쪽 채택)
        ▼
[reply-drafter]   → draft_replies.json + Gmail 초안함
        │              (긴급=격식체 / 중요=정중체 / 일반=간략체, 발송은 하지 않음)
        ▼
[mail-workflow]   → 요약 통계 · 중요도별 목록 · 텔레그램 전송 · logs/daily_summary_YYYY-MM-DD.md
```

- 분류·초안 모델: Claude (`claude-opus-5-5`)
- 텔레그램 전송: `scripts/send_telegram.ps1` (PowerShell `Invoke-RestMethod`, HTML·UTF-8, 실패 시 1회 재시도, `-DryRun` 지원)
- 회신 메일은 **절대 자동 발송하지 않으며** 초안 저장까지만 수행합니다.

### 실행 준비

1. Claude Code에서 Gmail 커넥터를 연결합니다 (`/mcp`).
2. `2.1-mail-agent/.env.local`을 만듭니다.
   ```
   TELEGRAM_BOT_TOKEN=<BotFather에서 받은 토큰>
   TELEGRAM_CHAT_ID=<내 chat_id>
   ```
3. `mail_config.json`에서 `important_senders`, `urgent_keywords`, `check_interval` 등을 조정합니다.
4. Claude Code에서 `workflows/mail-workflow.md 워크플로우를 실행해줘`라고 요청합니다.

텔레그램 설정만 먼저 확인하려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\send_telegram.ps1 -MessageFile tmp\msg.txt -DryRun
```

## 2.2 file-sender 구조

```
텔레그램 "로또분석파일보내줘"
        ▼
[권한 확인]       authorized_users 외 사용자 → "권한이 없습니다."
        ▼
[command-parser]  file_query · recipient · date_hint · urgency 추출 (Claude)
        ▼
[file-finder]     scripts/file_finder.py — search_folders 안에서만, 확장자·크기 필터, 최신 파일 1개
        │            없으면 → "파일을 찾지 못했습니다" 응답 후 종료
        ▼
[mail-sender]     scripts/mail_sender.py — smtplib + SMTP_SSL(465)로 첨부 발송, 1회 재시도,
                     텔레그램 결과 알림, logs/transfer_log.json 기록
```

- 슬래시 명령: `commands/file-transfer.md`(1건 처리), `commands/telegram-listener.md`(5초 간격 상시 대기)
- 실행: `check_once.bat`(새 메시지가 있을 때만 Claude 실행 — 작업 스케줄러 주기 실행용), `run_listener.bat`(상시 대기)
- 권한: bat은 `--permission-mode default` + `scripts/`의 스크립트 4개만 허용 (auto mode 오판 방지)
- 외부 패키지 없이 Python 표준 라이브러리만 사용

### 실행 준비

1. `sender_config.example.json`을 `sender_config.json`으로 복사하고 `search_folders`, `default_recipient` 등을 수정합니다.
2. `2.2-file-sender/.env`를 만듭니다. (Gmail은 2단계 인증 후 앱 비밀번호 발급)
   ```
   GMAIL_ADDRESS=<보내는 Gmail 주소>
   GMAIL_APP_PASSWORD=<앱 비밀번호 16자리>
   TELEGRAM_BOT_TOKEN=<BotFather에서 받은 토큰>
   TELEGRAM_CHAT_ID=<내 텔레그램 ID>
   ```
3. 무인 실행 시 `claude setup-token`으로 장기 토큰을 발급해 `CLAUDE_CODE_OAUTH_TOKEN` 사용자 환경 변수로 저장합니다.
4. `check_once.bat`을 작업 스케줄러에 등록하거나 `run_listener.bat`을 실행합니다.

## 보안 메모

- `.env`, `.env.*` 파일은 `.gitignore`로 제외됩니다. 토큰·키는 커밋하지 마세요.
- `classified_mails.json`, `draft_replies.json`, `logs/`는 실행할 때마다 생성되는 결과물로, 메일 제목·발신자가 담기므로 `.gitignore`로 제외됩니다.
- 2.2의 `sender_config.json`(개인 메일 주소)과 `logs/`(전송 기록)는 `2.2-file-sender/.gitignore`로 제외됩니다.
