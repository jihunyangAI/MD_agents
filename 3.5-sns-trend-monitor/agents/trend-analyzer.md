---
name: trend-analyzer
description: data/raw_keywords_{오늘}.json과 7일 전 파일을 비교해 분야별 키워드를 급상승/상승/하락/신규로 분류하고, 클로드로 분야별·전체 트렌드 요약을 만들어 data/trend_report_{오늘}.json에 저장한다. 지난주 파일이 없으면 전부 신규로 처리. sns-trend-workflow의 2단계.
tools: Bash, Read
---

# trend-analyzer — 트렌드 분석 에이전트

## 역할
이번 주와 지난 주 키워드 순위를 비교해 변화를 분류하고 요약한다.
실행 스크립트: `scripts/trend_analyzer.py`

```
python scripts/trend_analyzer.py                      # 오늘 날짜
python scripts/trend_analyzer.py --date 2026-11-16
python scripts/trend_analyzer.py --prev-file data/raw_keywords_2026-11-06.json   # 지난주 파일 직접 지정
```

## 1단계: 데이터 읽기
| 파일 | 사용 항목 |
|------|-----------|
| `trend_config.json` | `topics`, `analysis.top_keywords_count`(20), `analysis.trending_rise_threshold`(3), `analysis.claude_model` |
| `data/raw_keywords_{오늘}.json` | 이번 주 데이터. 없으면 중단하고 keyword-collector를 먼저 실행하라고 안내 |
| `data/raw_keywords_{7일 전}.json` | 지난 주 데이터. 정확히 7일 전 파일이 없으면 **3~13일 전 중 가장 최근 파일**을 쓴다. 그것도 없으면 **'지난주 없음'** 처리 |

- 모든 파일 입출력은 `encoding="utf-8"`.
- 분야 순위: 같은 topic의 x·linkedin 언급 횟수를 합산(대소문자 무시)해 내림차순 정렬, 상위 20개에 1위부터 순위를 매긴다.

## 2단계: 키워드 분류 (분야별)
순위 변화 `rank_change = 지난주 순위 − 이번 주 순위` (양수 = 상승)

| 분류 | 키 | 조건 |
|------|----|------|
| 급상승 | `rising` | `rank_change ≥ trending_rise_threshold`(3) |
| 상승 | `up` | `rank_change`가 1~2 |
| 하락 | `down` | `rank_change < 0` (이번 주 top20 안에 남아 있는 키워드) |
| 신규 | `new` | 지난 주 top20에 없었고 이번 주 top20에 진입 |

- 순위 변화가 0인 키워드는 어느 분류에도 넣지 않는다 (`top_keywords`에는 포함).
- **지난주 데이터가 없으면(첫 실행)** 순위 비교 없이 모든 키워드를 `new`로 처리한다.

## 3단계: 트렌드 요약
- 분야별 top10과 분류 결과를 `claude -p --model haiku`에 보내 **분야별 1~2문장 + 전체 흐름 2~3문장** 요약을 받는다.
  - 예: '이번 주 테크 분야에서는 AI 에이전트 관련 키워드가 급부상했으며...'
  - 데이터에 없는 사실은 쓰지 않도록 지시한다. 첫 실행이면 이번 주 상위 키워드 위주로 요약하게 한다.
- 클로드 실패 시 1회 재시도, 그래도 실패하면 상위 키워드 이름으로 만든 규칙 기반 문장으로 대신한다.

## 4단계: 결과 저장
출력: `data/trend_report_{YYYY-MM-DD}.json`

```json
{
  "date": "2026-11-13",
  "previous_date": null,
  "has_previous": false,
  "trending_rise_threshold": 3,
  "overall_summary": "전체 흐름 2~3문장",
  "topics": [
    {
      "topic": "테크",
      "rising": [{"word": "Claude", "rank_change": 5, "rank": 1, "prev_rank": 6, "count": 12}],
      "up":     [{"word": "MCP", "rank_change": 2, "rank": 3, "prev_rank": 5, "count": 7}],
      "down":   [{"word": "GPT4", "rank_change": -3, "rank": 8, "prev_rank": 5, "count": 4}],
      "new":    [{"word": "Grok3", "rank": 4, "count": 6}],
      "top_keywords": [{"word": "Claude", "rank": 1, "count": 12}],
      "summary": "이번 주 테크 분야에서는..."
    }
  ]
}
```
- 요청 형식의 `word`·`rank_change`에 더해 `rank`·`prev_rank`·`count`를 붙였다.
- `top_keywords`(이번 주 top20)와 `overall_summary`는 report-composer가 보고서를 쓸 때 사용한다. 첫 실행에는 `top_keywords`만 보고서에 싣는다.

로그: `logs/trend_analyzer_{YYYYMMDD}.log`
