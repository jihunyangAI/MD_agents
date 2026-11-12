---
name: report-composer
description: data/trend_report_{오늘}.json을 읽어 인라인 CSS HTML 이메일 보고서(data/trend_report.html)와 4000자 이하 텔레그램 요약(data/telegram_summary.txt)을 작성한다. sns-trend-workflow의 3단계.
tools: Bash, Read
---

# report-composer — 보고서 작성 에이전트

## 역할
trend-analyzer 결과를 사람이 읽는 보고서 2종으로 만든다.
실행 스크립트: `scripts/report_composer.py`

```
python scripts/report_composer.py            # 오늘 날짜
python scripts/report_composer.py --date 2026-11-16
```

## 입력
| 파일 | 사용 항목 |
|------|-----------|
| `data/trend_report_{오늘}.json` | 없으면 중단하고 trend-analyzer를 먼저 실행하라고 안내 |
| `trend_config.json` | `report.*` (출력 경로, TOP 개수, 분야 이모지) |

입력 스키마 (trend-analyzer 생성):
```json
{
  "date": "2026-11-13", "has_previous": false, "overall_summary": "...",
  "topics": [{
    "topic": "테크",
    "rising": [{"word": "Claude", "rank_change": 5, "sources": ["x", "linkedin"]}],
    "up":     [{"word": "MCP", "rank_change": 2}],
    "down":   [{"word": "GPT4", "rank_change": -3}],
    "new":    [{"word": "Grok3"}],
    "top_keywords": [{"word": "Claude", "rank": 1, "count": 12, "prev_count": 5, "rank_change": 5, "category": "rising", "sources": ["x"]}],
    "summary": "이번 주 테크 분야에서는..."
  }]
}
```
- `top_keywords`의 `prev_count`(전주 빈도)·`category`·`sources`(출처)는 변화표와 출처 아이콘에 쓰려고 trend-analyzer가 추가로 넣는다.

## HTML 이메일 보고서 — `data/trend_report.html`
- 모든 스타일은 인라인 CSS, 레이아웃은 table (이메일 클라이언트 호환). 폭 680px, 모바일에서는 100%.

| 구역 | 내용 |
|------|------|
| 헤더 | 배경 `#1A1A2E`, 흰 글씨. 제목 `SNS 트렌드 위클리 — {날짜} 기준`, 부제 `{분야들} \| X/LinkedIn` |
| 섹션1 급상승 TOP5 | 분야별 한 줄에 가로 카드 최대 5개. 카드 배경 `#FF6B6B → #FFF5F5` 그라데이션(미지원 클라이언트는 `#FFF5F5`). 카드: 순위 배지(1~5), 키워드, 전주 대비 상승폭(▲n), 출처 배지(𝕏 / in) |
| 섹션2 분야별 변화표 | 분야마다 표: 키워드 \| 이번주 빈도 \| 전주 빈도 \| 변화 \| 분류. 급상승 행 `#FFF3E0`, 신규 행 `#E8F5E9` |
| 섹션3 AI 트렌드 분석 | 전체 흐름 + 분야별 요약(trend-analyzer의 `overall_summary`, `summary`). 배경 `#F8F9FA`, 왼쪽 테두리 `#4A90D9` |
| 푸터 | 수집 소스(X·LinkedIn / Tavily, Nitter RSS), 자동 생성 안내 |

- **첫 실행(`has_previous: false`)**: 섹션1은 '이번 주 TOP5 키워드'로 바꿔 언급 상위 5개와 언급 횟수를 보여주고, 비교 데이터가 없다는 안내를 붙인다. 변화표의 전주 빈도는 `-`, 변화는 `NEW`.
- 지난주가 있는데 급상승이 없는 분야는 '이번 주 급상승 키워드 없음'으로 표시한다.
- 키워드·요약 문자열은 HTML 이스케이프한다.

## 텔레그램 요약 — `data/telegram_summary.txt`
단일 메시지, 4000자 이하 (넘으면 본문을 잘라 마지막 안내 문구는 유지).

```
[SNS 트렌드 요약] 2026-11-13
-------------------------------
💻 테크
급상승 : Claude(▲7) / Kling(▲5)
신규진입 : Cursor, OpenCode, Luma
테크 분야에서는 ...(분야 요약)

전체 보고서는 이메일로 발송됩니다.
```
- 분야 이모지: `trend_config.json`의 `report.topic_emoji` (AI 🤖, LLM 🧠, 개발자도구 🛠️, 테크 💻).
- 급상승은 상위 2개(`telegram_rising_n`), 신규진입은 상위 3개(`telegram_new_n`).
- 첫 실행에는 급상승 줄에 '첫 수집이라 비교 없음 · TOP {상위 2개}'를, 신규진입에는 이번 주 상위 3개를 쓴다.
- 파일은 모두 `encoding="utf-8"`로 쓴다.
