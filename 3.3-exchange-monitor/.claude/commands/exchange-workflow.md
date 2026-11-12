---
description: 환율 수집 → 알림 조건 확인 → 텔레그램 발송까지 한 번에 실행하는 exchange-workflow
allowed-tools: Bash, Read
---

# exchange-workflow — 환율 모니터링 통합 워크플로

## 수동 실행 트리거 (둘 다 동일 동작)
- 슬래시 명령어: `/exchange-workflow`
- 자연어: "지금 바로 환율수집하고 알림조건을 확인해서 텔레그램 발송해줘."

확인 질문 없이 아래 단계를 **순서대로** 실행한다. 각 단계는 직전 산출물에 의존한다.
작업 폴더: 이 프로젝트 루트 (`3.3-exchange-monitor`)

## 1단계 — rate-collector (`agents/rate-collector.md`)
```
PYTHONIOENCODING=utf-8 python rate_collector.py
```
- open.er-api.com에서 USD/JPY(100엔)/EUR 원화 환율을 수집해 `exchange_history.json`에 저장한다.
- API 실패 시 1회 재시도한다. 다시 실패하면(exit 1) 오늘 데이터가 없으므로 2단계는 "수집 실패로 생략"을 출력하고 3단계로 간다.

## 2단계 — rate-alert (`agents/rate-alert.md`)
```
PYTHONIOENCODING=utf-8 python rate_alert.py
```
- 목표가 도달·급변 여부를 확인하고, 대상이 있으면 텔레그램을 보낸다 (누락 금지).
- 콘솔에 발송 결과를 출력한다: `[텔레그램] 성공/실패 (메시지 길이 N자)`
- 실패하면 1회 재시도하고 `logs/telegram_YYYY-MM-DD.log`에 기록한 뒤 다음 단계로 간다 (전체 중단 금지).
- 대상이 없거나 24시간 내 중복이면 발송하지 않고 그 사실을 출력한다.

## 3단계 — 완료 메시지
```
python -c "from datetime import datetime,timedelta,timezone;print('환율확인완료 - '+datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')+' KST')"
```
- 24시간 중복 방지를 무시하고 강제로 다시 보내려면 2단계에서 `python rate_alert.py --force`를 쓴다 (수동 검증용).

## 결과 보고
수집 환율 3종, 알림 건수(목표가/급변), 텔레그램 발송 결과를 짧게 보고한다.
