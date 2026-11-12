""".env의 텔레그램 값을 exchange_config.json의 telegram 항목에 채운다. 값은 화면에 마스킹해서만 표시한다."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
env = {}
for line in (BASE_DIR / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

cfg_path = BASE_DIR / "exchange_config.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
tg = cfg.setdefault("telegram", {})
token = env.get(tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
chat_id = env.get(tg.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
if not token or not chat_id:
    raise SystemExit("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 .env에 없습니다.")
tg["bot_token"] = token
tg["chat_id"] = chat_id
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"OK bot_token={token[:6]}*** chat_id={chat_id[:3]}***")
