"""mail-sender 실행 스크립트 — 표준 라이브러리만 사용 (smtplib + SMTP_SSL 465, urllib).

사용법:
  python -X utf8 scripts/mail_sender.py --file "C:/tmp/서지영.pdf" --requester 123456789 \
      [--recipient someone@example.com] [--dry-run]

- 비밀 값(.env)은 화면에 출력하지 않는다.
- 결과는 UTF-8 JSON 한 줄로 출력하고 logs/transfer_log.json 에 기록한다.
"""
import argparse, json, os, re, smtplib, ssl, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "sender_config.json"
ENV_FILE = BASE / ".env"
LOG_FILE = BASE / "logs" / "transfer_log.json"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip().upper()] = v.strip().strip('"').strip("'")
    return env


def pick(env, *keys):
    for k in keys:
        if env.get(k):
            return env[k]
    return ""


def expand(value, env):
    return re.sub(r"\$\{(\w+)\}", lambda m: env.get(m.group(1).upper(), ""), str(value))


def human_size(n):
    return f"{n / 1048576:.2f} MB" if n >= 1048576 else f"{n / 1024:.1f} KB"


def notify_telegram(token, chat_id, text, dry_run):
    if dry_run:
        return "dry-run"
    if not token or not chat_id:
        return "skipped: token/chat_id 없음"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=15) as r:
            return "ok" if json.load(r).get("ok") else "fail"
    except Exception as e:
        return f"fail: {type(e).__name__}"


def write_log(entry):
    LOG_FILE.parent.mkdir(exist_ok=True)
    try:
        logs = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        if not isinstance(logs, list):
            logs = []
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []
    logs.append(entry)
    LOG_FILE.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--requester", required=True, help="전송 요청자 텔레그램 ID")
    ap.add_argument("--recipient", default="")
    ap.add_argument("--dry-run", action="store_true", help="메일·텔레그램을 실제로 보내지 않고 점검만")
    a = ap.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    env = {} if a.dry_run else load_env()
    gmail_user = pick(env, "GMAIL_USER", "GMAIL_ADDRESS") or ("dry-run@example.com" if a.dry_run else "")
    gmail_pw = pick(env, "GMAIL_APP_PASSWORD").replace(" ", "")
    token = pick(env, "TELEGRAM_BOT_TOKEN")
    authorized = {expand(u, env) for u in cfg.get("authorized_users", [])}
    now = datetime.now()

    path = Path(unicodedata.normalize("NFC", a.file))
    name = path.name
    recipient = a.recipient.strip()
    recipient_source = "message"
    if not EMAIL_RE.match(recipient) or recipient.lower() == cfg["default_recipient"].lower():
        recipient, recipient_source = cfg["default_recipient"], "default"

    result = {"status": "fail", "file": str(path).replace("\\", "/"), "name": name, "recipient": recipient,
              "recipient_source": recipient_source, "requester": a.requester,
              "time": now.strftime("%Y-%m-%d %H:%M:%S"), "attempts": 0, "error": None, "dry_run": a.dry_run}

    def finish(error=None):
        result["error"] = error
        if error:
            msg = f"전송실패: {error}"
        else:
            result["status"] = "success"
            msg = f"{name}을 {recipient}에게 발송했습니다."
        result["telegram"] = notify_telegram(token, a.requester, msg, a.dry_run)
        result["telegram_message"] = msg
        if not a.dry_run:
            write_log(result)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if not error else 1)

    # --- 사전 점검 ---
    if not a.dry_run and a.requester not in authorized:
        result["telegram"] = notify_telegram(token, a.requester, "권한이 없습니다.", False)
        result["error"] = "unauthorized"
        write_log(result)
        print(json.dumps(result, ensure_ascii=False)); sys.exit(1)
    if not a.dry_run and (not gmail_user or not gmail_pw):
        finish("Gmail 계정 정보가 .env에 없습니다")
    if not path.is_file():
        finish("파일이 존재하지 않습니다")
    real = os.path.realpath(path)
    roots = [os.path.realpath(f) for f in cfg["search_folders"]]
    if not any(os.path.commonpath([real, r]) == r for r in roots if os.path.isdir(r)):
        finish("허용된 검색 폴더 밖의 파일입니다")
    if path.suffix.lower() not in {e.lower() for e in cfg["allowed_extensions"]}:
        finish("허용되지 않은 확장자입니다")
    size = path.stat().st_size
    if size > cfg["max_file_size_mb"] * 1048576:
        finish(f"파일이 너무 큽니다 ({human_size(size)}, 한도 {cfg['max_file_size_mb']} MB)")
    result["size"] = human_size(size)

    # --- 메일 작성 ---
    stamp = now.strftime("%Y-%m-%d %H:%M")
    msg = EmailMessage()
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg["Subject"] = f"[긴급파일전송] {name} - {stamp}"
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(
        "긴급 파일 전송 서비스에서 요청하신 파일을 보내드립니다.\n\n"
        f"■ 발신 시각: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"■ 파일 이름: {name}\n"
        f"■ 파일 크기: {human_size(size)}\n"
        f"■ 전송 요청자 텔레그램 ID: {a.requester}\n"
    )
    msg.add_attachment(path.read_bytes(), maintype="application", subtype="octet-stream", filename=name)

    if a.dry_run:
        result["subject"] = msg["Subject"]
        finish()

    # --- 발송 (실패 시 1회 재시도) ---
    last = None
    for attempt in (1, 2):
        result["attempts"] = attempt
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
                s.login(gmail_user, gmail_pw)
                s.send_message(msg)
            finish()
        except smtplib.SMTPAuthenticationError:
            last = "Gmail 로그인 실패 (앱 비밀번호 확인 필요)"
            break  # 인증 오류는 재시도해도 같음
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:150]}"
            if attempt == 1:
                time.sleep(3)
    finish(last)


if __name__ == "__main__":
    main()
