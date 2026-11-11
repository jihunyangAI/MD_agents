"""텔레그램으로 짧은 응답 보내기 — 표준 라이브러리만 사용 (urllib).

사용법:
  python -X utf8 scripts/telegram_reply.py --chat-id 123456789 --text "파일을 찾지 못했습니다"
출력: {"ok": true} 또는 {"ok": false, "error": "..."}  (토큰은 출력하지 않음)
"""
import argparse, json, sys, urllib.parse, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--chat-id", required=True)
ap.add_argument("--text", required=True)
a = ap.parse_args()

token = ""
f = BASE / ".env"
if f.exists():
    for line in f.read_text(encoding="utf-8").splitlines():
        if line.strip().upper().startswith("TELEGRAM_BOT_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
if not token:
    print(json.dumps({"ok": False, "error": "TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다"}, ensure_ascii=False)); sys.exit(1)

data = urllib.parse.urlencode({"chat_id": a.chat_id, "text": a.text}).encode()
try:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=15) as r:
        print(json.dumps({"ok": bool(json.load(r).get("ok"))}))
except Exception as e:
    print(json.dumps({"ok": False, "error": type(e).__name__}, ensure_ascii=False)); sys.exit(1)
