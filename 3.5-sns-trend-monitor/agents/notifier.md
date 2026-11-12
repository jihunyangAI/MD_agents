---
name: notifier
description: data/trend_report.html을 Gmail SMTP로 trend_config.json의 subscribers 전원에게 BCC 발송하고, data/telegram_summary.txt를 텔레그램 단일 메시지로 발송한다. 이메일 성공 여부와 무관하게 텔레그램은 항상 발송. sns-trend-workflow의 4단계.
tools: Bash, Read
---

# notifier — 발송 에이전트

## 역할
완성된 보고서를 이메일과 텔레그램으로 보낸다.
실행 스크립트: `scripts/notifier.py`

```
python scripts/notifier.py              # 실제 발송
python scripts/notifier.py --dry-run    # 발송 없이 제목·구독자 수·환경변수 설정 여부만 점검
```

## 입력
| 파일 | 사용 항목 |
|------|-----------|
| `data/trend_report.html` | 이메일 본문. 없으면 중단하고 report-composer를 먼저 실행하라고 안내 |
| `data/telegram_summary.txt` | 텔레그램 메시지 |
| `trend_config.json` | `subscribers`, `email.*`, `telegram.*`, `topics` |
| `.env` | `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |

- `trend_config.json`에는 `${GMAIL_ADDRESS}`처럼 변수 이름만 있고, 실제 값은 실행 시 `.env`에서 읽는다. 코드·로그에 값을 쓰지 않는다.

## 1. 이메일 (Gmail SMTP)
- `smtp.gmail.com:587`, STARTTLS, 앱 비밀번호로 로그인.
- **수신자**: `subscribers` 전원을 BCC로 (To 헤더에는 보낸 사람 본인만 표시, 구독자 주소 노출 안 함).
- **제목**: `SNS 트렌드 위클리 | {날짜} - {분야} 급상승 키워드`
  - `{분야}`는 `topics`를 `·`로 연결 → `SNS 트렌드 위클리 | 2026-11-13 - AI·LLM·개발자도구·테크 급상승 키워드`
- **본문**: `trend_report.html` 그대로, `Content-Type: text/html; charset=utf-8`.
- 실패 시 1회 재시도.

## 2. 텔레그램 (Bot API `sendMessage`)
- `telegram_summary.txt` 내용을 **단일 메시지**로 발송 (4000자 초과분은 자른다).
- **이메일 성공 여부와 무관하게 항상 발송**한다.
- 실패 시 1회 재시도. 오류 메시지에는 토큰이 섞이지 않게 API의 `description`만 남긴다.

## 3. 발송 결과 알림
콘솔과 `logs/notifier_{YYYYMMDD}.log`에 남긴다.

| 결과 | 메시지 |
|------|--------|
| 모두 성공 | `트렌드 보고서 발송완료 \| 이메일 {N}명 / 텔레그램` |
| 하나라도 실패 | `발송오류:{오류내용}` (예: `발송오류:이메일 (535, 인증 실패)`) |

- 이메일만 실패하고 텔레그램이 성공했으면 `발송오류:...` 메시지를 텔레그램으로도 한 번 더 보낸다.
- 종료 코드: 모두 성공 0, 실패 있으면 1.
