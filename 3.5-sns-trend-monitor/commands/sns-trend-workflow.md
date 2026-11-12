---
description: X·LinkedIn 키워드 수집 → 전주 대비 변화 분석 → HTML 보고서·텔레그램 요약 작성 → 이메일·텔레그램 발송까지 한 번에 실행하는 sns-trend-workflow
allowed-tools: Bash, Read, Write
---

# sns-trend-workflow — SNS 트렌드 주간 보고 워크플로

## 수동 실행 트리거 (둘 다 같은 동작)
- 슬래시 명령어: `/sns-trend-workflow`
- 자연어: **"지금 트렌드 분석해줘"**

확인 질문 없이 아래 4단계를 **순서대로** 즉시 실행하고, 마지막에 텔레그램(과 이메일)을 바로 발송한다.
- 작업 폴더: 프로젝트 루트 (`3.5-sns-trend-monitor`)
- 설정: `trend_config.json` / 비밀 값: `.env` (직접 읽지 않는다. 스크립트가 `python-dotenv`로 읽는다)
- Python 명령은 `PYTHONIOENCODING=utf-8`을 붙여 실행한다 (Windows 콘솔 한글 깨짐 방지).
- 날짜는 오늘(`YYYY-MM-DD`). 모든 단계가 같은 날짜 파일을 주고받는다.

**공통 실패 원칙**: 한 단계가 실패해도 다음 단계에 필요한 파일이 있으면 계속 진행한다. 필요한 파일이 없으면 거기서 멈추고, 텔레그램으로 `발송오류:{단계} 실패 — {오류내용}`을 보낸 뒤 완료 보고에 적는다.

---

## 1단계 — keyword-collector (`agents/keyword-collector.md`)
```
PYTHONIOENCODING=utf-8 python scripts/keyword_collector.py
```
- topics(AI, LLM, 개발자도구, 테크)별로 X·LinkedIn 최근 7일 게시물을 Tavily API로 수집한다 (X 실패 시 Nitter RSS → 그래도 실패면 LinkedIn만).
- 클로드로 기술 키워드를 추출하고, 노이즈 필터 적용, 전체에서 1회만 나온 키워드는 제외한다.
- 산출물: `data/raw_posts_{날짜}.json`(원문), `data/raw_keywords_{날짜}.json`
- 같은 날 이미 수집했고 추출만 다시 하려면 `--reuse-raw` (Tavily 사용량 절약). 수동 트리거에서는 항상 새로 수집한다.

## 2단계 — trend-analyzer (`agents/trend-analyzer.md`)
```
PYTHONIOENCODING=utf-8 python scripts/trend_analyzer.py
```
- `raw_keywords_{오늘}.json`과 `raw_keywords_{7일 전}.json`을 비교해 분야별 급상승 / 상승 / 하락 / 신규로 분류한다.
- 7일 전 파일이 없으면 '지난주 없음' → 전부 신규로 처리한다.
- 클로드로 분야별 요약과 전체 흐름 2~3문장 요약을 만든다.
- 산출물: `data/trend_report_{날짜}.json`

## 3단계 — report-composer (`agents/report-composer.md`)
```
PYTHONIOENCODING=utf-8 python scripts/report_composer.py
```
- 산출물: `data/trend_report.html`(인라인 CSS 이메일 보고서), `data/telegram_summary.txt`(4000자 이하 단일 메시지)

## 4단계 — notifier (`agents/notifier.md`)
```
PYTHONIOENCODING=utf-8 python scripts/notifier.py
```
- 이메일: `subscribers` 전원 BCC, 제목 `SNS 트렌드 위클리 | {날짜} - {분야} 급상승 키워드`, 본문 HTML.
- 텔레그램: `telegram_summary.txt`를 단일 메시지로 발송. **이메일 결과와 무관하게 항상 발송**한다.
- 결과: `트렌드 보고서 발송완료 | 이메일 {N}명 / 텔레그램` 또는 `발송오류:{오류내용}`
- 발송 없이 점검만 하려면 `--dry-run`.

---

## 완료 보고 (콘솔 출력)
```
✅ 완료
수집 키워드 N개
급상승 TOP 5: [키워드 나열]
보고서: data/trend_report.html
발송: 이메일 성공/실패, 텔레그램 성공/실패
사용한 가정: [있다면]
```
- 수집 키워드 N: `raw_keywords_{날짜}.json`의 고유 키워드 수 (대소문자 무시)
- 급상승 TOP 5: `trend_report_{날짜}.json` 전 분야 `rising`을 `rank_change` 내림차순으로 5개.
  첫 실행(`has_previous: false`)이면 "지난주 데이터 없음 — 이번 주 TOP: ..."으로 전 분야 언급 상위 5개를 적는다.
- 발송: 4단계 출력(`logs/notifier_{YYYYMMDD}.log`) 기준.
- 분야별 한 줄 요약(trend-analyzer의 `summary`)을 함께 보여준다.
