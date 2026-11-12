"""rate-collector: open.er-api.com에서 환율을 수집해 exchange_history.json에 저장한다."""
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "exchange_config.json"
API_URL = "https://open.er-api.com/v6/latest/USD"
KST = timezone(timedelta(hours=9))
KEEP_DAYS = 30


def fetch_rates():
    """API 호출 (실패 시 1회 재시도)."""
    for attempt in range(2):
        try:
            req = urllib.request.Request(API_URL, headers={"User-Agent": "exchange-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("result") != "success":
                raise ValueError(f"API 응답 오류: {data.get('error-type')}")
            return data["rates"]
        except Exception as e:
            print(f"[수집 실패 {attempt + 1}/2] {e}")
            if attempt == 0:
                time.sleep(3)
    return None


def build_record(rates):
    krw, jpy, eur = rates["KRW"], rates["JPY"], rates["EUR"]
    return {
        "date": datetime.now(KST).strftime("%Y-%m-%d"),
        "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
        "usd": round(krw, 1),
        "jpy100": round(krw / jpy * 100, 1),
        "eur": round(krw / eur, 1),
    }


def save_history(record, data_file):
    path = BASE_DIR / data_file
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    # 오늘 날짜 덮어쓰기
    history = [h for h in history if h.get("date") != record["date"]]
    history.append(record)
    # 최근 30일만 유지
    cutoff = (datetime.now(KST) - timedelta(days=KEEP_DAYS - 1)).strftime("%Y-%m-%d")
    history = sorted((h for h in history if h["date"] >= cutoff), key=lambda h: h["date"])
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    rates = fetch_rates()
    if rates is None:
        print("오늘 수집을 건너뜁니다.")
        sys.exit(1)
    record = build_record(rates)
    history = save_history(record, config.get("data_file", "exchange_history.json"))
    print(json.dumps(record, ensure_ascii=False))
    print(f"이력 {len(history)}건 저장 완료")


if __name__ == "__main__":
    main()
