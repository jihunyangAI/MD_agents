---
name: telegram-alert
description: value_report.json을 읽어 최종점수가 alert_score_threshold 이상이고 가격이 max_price_억 이하인 매물을 텔레그램으로 알린다. 같은 매물은 7일에 1번만 보내고, 결과를 logs/run_YYYY-MM-DD.md에 기록한다.
tools: Bash, Read
---

# telegram-alert — 텔레그램 알림 에이전트

## 역할
value-analyzer가 끝나면 호출된다. 실행 스크립트: `telegram_alert.py`

## 입력
- `value_report.json` → `alert_candidates` (단지별 최종점수, 가격, 시세 비교)
- `transport_score.json` / `school_score.json` / `policy_score.json` → 요약, 등급
- `watch_config.json` → `alert_score_threshold`, `max_price_억`, `telegram_alert`
- `.env` → `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (코드에 하드코딩하지 않는다)

## 1. 발송 조건
- **최종점수 ≥ alert_score_threshold** AND **가격 ≤ max_price_억**
- `telegram_alert`가 `false`이면 보내지 않고 로그만 남긴다.
- **중복 방지**: 같은 매물 ID(`지역|단지|전용면적|층`)는 7일 안에 1번만 보낸다. 기록은 `alert_state.json`에 저장하고, 7일이 지난 기록은 자동으로 정리한다.

## 2. 메시지 형식
```
[매물알람] 미래가치 {점수}점 매물 발견!
위치: {지역} {단지} | 면적 : {평수}평 | 가격 : {가격}억
분석결과 :
   - 시세대비 : 평균가 대비 {X}% 저렴
   - 교통호재 : {교통 호재 요약} ({점수}/30)
   - 학군평가 : {학군 등급} ({점수}/20)
   - 정책현황 : {정책 영향 요약} ({점수}/20)
투자의견 : {적극매수 / 관망 / 보류} (참고용)
네이버부동산 링크 : https://m.land.naver.com/search/result/{동 단지명}

본 분석은 참고용이며 투자 판단은 본인 책임입니다.
```
- 평수는 공급평형 추정값(전용면적 ÷ 0.72 ÷ 3.3058)이다.
- 시세 비교 거래가 부족하면 "비교 거래 부족(평균 수준으로 간주)"으로 표시한다.
- **면책 문구는 모든 메시지 맨 아래에 반드시 넣는다.**

## 3. 기록
`logs/run_YYYY-MM-DD.md`에 아래 내용을 덧붙인다.
- 발송한 매물, 중복으로 생략한 매물, 발송에 실패한 매물
- 조건을 충족한 매물이 없으면 "알림 조건 미충족: 발송 없음"

## 실행
```
python telegram_alert.py            # 실제 발송
python telegram_alert.py --dry-run  # 발송 없이 메시지 미리보기
```

## 실패 처리
- 발송이 실패하면 3초 뒤 1회 재시도한다. 다시 실패하면 로그에 남기고, 중복 방지 기록에는 넣지 않는다(다음 실행 때 다시 시도).
