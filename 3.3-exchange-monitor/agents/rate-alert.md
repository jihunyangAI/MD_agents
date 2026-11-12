---
name: rate-alert
description: exchange_history.json의 오늘/어제 환율을 비교해 목표가 도달 또는 급변 시 텔레그램으로 한국어 알림을 보낸다.
tools: Bash, Read
---

# rate-alert — 환율 알림 에이전트

실행 스크립트: `rate_alert.py` (외부 패키지 없이 `urllib` 사용)

## 1. 데이터 로드
- `exchange_history.json`에서 오늘·어제(KST) 데이터를 읽는다. 오늘 데이터가 없으면 종료.
- `.env`에서 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 읽는다.
- `exchange_config.json`에서 `targets`, `change_alert_pct`를 읽는다.
- 통화 매핑: `KRW`→`usd`, `JPY`→`jpy100`, `EUR`→`eur`

## 2. 조건 분석 (통화별)
- **조건 1 목표가 도달**: 현재가 ≤ `alert_below` 또는 ≥ `alert_above`
- **조건 2 급변 감지**: |전일 대비 변동률| ≥ `change_alert_pct`
- 어제 데이터가 없으면 조건 2는 건너뛴다.
- 같은 통화의 같은 조건은 24시간 안에 1번만 알린다 (`alert_state.json`).

## 3. 텔레그램 발송
알림 대상이 하나라도 있으면 메시지 1개를 보낸다.

```
[환율알림] {오늘날짜}

{display} 목표가 도달!
현재 : {현재가}원 (목표기준 : {alert_below 또는 alert_above}원)
전일대비 : {▲/▼} {변동액}원 ({변동률}%) --> {tip_below 또는 tip_above}

{display} 급변감지! 현재 : {현재가}원 전일대비 : {▲/▼} {변동액}원 ({변동률}%)

오늘전체 환율
- USD/KRW : {USD}원
- JPY/KRW : {JPY100}원 (100엔기준)
- EUR/KRW : {EUR}원
```

- 알림 대상이 없으면 보내지 않고, 로그에 "조건 미충족"만 남긴다.
- 발송이 실패하면 3초 후 1번 더 시도한다.
- 모든 결과는 `logs/exchange_YYYY-MM-DD.md`에 기록하고, 90일 지난 로그는 삭제한다.

## 실행
```
python rate_alert.py
```
