"""today_news.json / impact_analysis.json 이 오늘 날짜로 새로 만들어졌는지 확인한다.
오래된 결과를 오늘 리포트로 발송하지 않기 위한 안전장치. 통과 0, 실패 1.
"""
import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
today = date.today().isoformat()

try:
    news = json.loads((BASE / "today_news.json").read_text(encoding="utf-8"))
    analysis = json.loads((BASE / "impact_analysis.json").read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"[check] FAIL: 파일 읽기 오류 - {e}")
    sys.exit(1)

problems = []
if news.get("date") != today:
    problems.append(f"today_news.json date={news.get('date')} (오늘={today})")
if not news.get("news"):
    problems.append("today_news.json 뉴스 0건")
if not str(analysis.get("analyzed_at", "")).startswith(today):
    problems.append(f"impact_analysis.json analyzed_at={analysis.get('analyzed_at')}")
if not analysis.get("market_summary"):
    problems.append("market_summary 비어 있음")

if problems:
    print("[check] FAIL: " + " / ".join(problems))
    sys.exit(1)
print(f"[check] OK: {today} 뉴스 {len(news['news'])}건, 분석 완료")
