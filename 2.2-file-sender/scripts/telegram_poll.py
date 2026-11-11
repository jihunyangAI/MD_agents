"""텔레그램 새 메시지 가져오기 — 표준 라이브러리만 사용 (urllib).

사용법:
  python -X utf8 scripts/telegram_poll.py --once              # 한 번만 확인하고 끝
  python -X utf8 scripts/telegram_poll.py --max-wait 540      # 새 메시지가 올 때까지 5초마다 확인 (최대 540초)

출력: 새 텍스트 메시지 목록 JSON. 토큰은 출력하지 않는다.
  [{"update_id":..,"chat_id":"..","from_id":"..","from_name":"..","text":"..","date":"..","authorized":true}]
처리한 위치(offset)는 logs/telegram_offset.json 에 저장해 같은 메시지를 두 번 가져오지 않는다.
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
POLL_SEC = 5
OFFSET_FILE = BASE / "logs" / "telegram_offset.json"


def load_env():
    env, f = {}, BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip().upper()] = v.strip().strip('"').strip("'")
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max-wait", type=int, default=540)
    ap.add_argument("--peek", action="store_true",
                    help="새 메시지 개수만 확인 (처리 위치를 저장하지 않음). 출력: {\"pending\": N}")
    a = ap.parse_args()
    if a.peek:
        a.once = True

    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print(json.dumps({"error": "TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다"}, ensure_ascii=False)); sys.exit(1)
    cfg = json.loads((BASE / "sender_config.json").read_text(encoding="utf-8"))
    authorized = {re.sub(r"\$\{(\w+)\}", lambda m: env.get(m.group(1).upper(), ""), str(u))
                  for u in cfg.get("authorized_users", [])}

    try:
        offset = json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        offset = 0

    deadline = time.time() + a.max_wait
    while True:
        q = urllib.parse.urlencode({"offset": offset, "timeout": 0, "allowed_updates": '["message"]'})
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates?{q}", timeout=20) as r:
                updates = json.load(r).get("result", [])
        except Exception as e:
            code = getattr(e, "code", "")
            print(json.dumps({"error": f"텔레그램 연결 실패 {type(e).__name__} {code}".strip()}, ensure_ascii=False))
            sys.exit(1)

        msgs = []
        for u in updates:
            offset = max(offset, u["update_id"] + 1)
            m = u.get("message") or {}
            if "text" not in m:
                continue
            frm = m.get("from", {})
            msgs.append({
                "update_id": u["update_id"],
                "chat_id": str(m["chat"]["id"]),
                "from_id": str(frm.get("id", "")),
                "from_name": frm.get("first_name", ""),
                "text": m["text"],
                "date": datetime.fromtimestamp(m["date"]).strftime("%Y-%m-%d %H:%M:%S"),
                "authorized": str(frm.get("id", "")) in authorized,
            })
        if a.peek:
            print(json.dumps({"pending": len(msgs)}))
            sys.exit(0 if msgs else 3)  # 3 = 새 메시지 없음
        if updates:
            OFFSET_FILE.parent.mkdir(exist_ok=True)
            OFFSET_FILE.write_text(json.dumps({"offset": offset}), encoding="utf-8")

        if msgs or a.once or time.time() >= deadline:
            print(json.dumps(msgs, ensure_ascii=False))
            return
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
