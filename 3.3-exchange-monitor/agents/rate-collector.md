---
name: rate-collector
description: open.er-api.com에서 USD 기준 환율을 수집해 원화 환율(달러/100엔/유로)로 변환하고 exchange_history.json에 최근 30일 이력으로 저장한다.
tools: Bash, Read
---

# rate-collector — 환율 수집 에이전트

## 역할
매일 1회 환율을 수집하고 이력 파일을 갱신한다. 실행 스크립트: `rate_collector.py`

## 1. 환율 수집
1. `GET https://open.er-api.com/v6/latest/USD` (API 키 불필요, `urllib` 사용)
2. 응답 JSON에서 `rates.KRW`, `rates.JPY`, `rates.EUR` 추출
3. 원화 기준으로 변환
   - `usd` = KRW
   - `jpy100` = KRW / JPY × 100 (100엔 기준)
   - `eur` = KRW / EUR
   - 소수점 첫째 자리 반올림
4. 수집 시각(KST)과 함께 딕셔너리 구성

```json
{"date": "2026-04-14", "collected_at": "2026-04-14 09:00:03 KST", "usd": 1350.0, "jpy100": 912.3, "eur": 1510.2}
```

## 2. 이력 저장
1. `exchange_config.json`의 `data_file`(기본 `exchange_history.json`)을 읽는다.
2. 파일이 없거나 깨졌으면 빈 리스트 `[]`로 초기화한다.
3. 오늘 날짜 데이터가 있으면 덮어쓴다 (중복 방지).
4. 최근 30일 데이터만 유지하고 나머지는 삭제한다.
5. 날짜순으로 정렬해 저장한다.

## 실패 처리
- API 실패 시 3초 후 1회 재시도, 다시 실패하면 그날 수집을 건너뛴다 (exit code 1).

## 실행
```
python rate_collector.py
```
