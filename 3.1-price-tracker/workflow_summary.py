"""price-track-workflow ⑤ 완료 메시지 출력 (스케줄 실행용).

출력: 수집완료 - [YYYY-MM-DD HH:MM] / 추적 중 상품 N개
"""
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent


def load(name):
    with open(BASE / name, encoding="utf-8") as f:
        return json.load(f)


def main():
    scraped = load("scraped_prices.json")
    watch = load("watchlist.json")
    when = datetime.fromisoformat(scraped["collected_at"]).strftime("%Y-%m-%d %H:%M")
    active = sum(1 for p in watch["products"] if p.get("active"))
    print(f"수집완료 - [{when}] / 추적 중 상품 {active}개")
    s = scraped.get("summary", {})
    print(f"수집: {s.get('success', 0)}/{s.get('total', 0)}개 성공")
    for r in scraped.get("results", []):
        if not r.get("success"):
            print(f"  - 실패: {r['id']} {r.get('error')} {r.get('error_message') or ''}")


if __name__ == "__main__":
    main()
