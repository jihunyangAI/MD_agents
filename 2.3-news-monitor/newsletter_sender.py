"""newsletter-sender: analyzed_news.json + collected_jobs.json → 텔레그램 데일리 브리핑 발송

사용법
  python newsletter_sender.py --dry-run   # 발송 없이 메시지 미리보기 (.env를 읽지 않음)
  python newsletter_sender.py             # 실제 발송 + newsletter_log.json 기록

외부 패키지 없이 표준 라이브러리만 사용한다.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
WEEKDAY = "월화수목금토일"


# ---------- 공통 ----------
def load_json(name, default=None):
    p = BASE / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def load_dotenv(path):
    """.env의 KEY=VALUE를 환경변수로 등록 (이미 있는 값은 덮어쓰지 않음)"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_MDV2 = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def esc(text):
    """MarkdownV2 일반 텍스트 이스케이프"""
    return _MDV2.sub(r"\\\1", str(text))


def esc_url(url):
    """MarkdownV2 링크 URL 이스케이프 (괄호 닫기와 역슬래시만)"""
    return str(url).replace("\\", "\\\\").replace(")", "\\)")


def link(label, url):
    return f"[{esc(label)}]({esc_url(url)})"


# ---------- 메시지 구성 ----------
def build_sections(cfg, news, jobs, events, today):
    use_emoji = cfg["telegram"].get("use_emoji", True)
    E = (lambda s: s) if use_emoji else (lambda s: "")

    arts = news.get("articles", []) if news else []
    high = [a for a in arts if a["impact_level"] == "높음"]
    mid = [a for a in arts if a["impact_level"] == "보통"]

    job_results = jobs.get("results", []) if jobs else []
    job_total = sum(len(r.get("jobs", [])) for r in job_results)

    date_str = f"{today:%Y-%m-%d}({WEEKDAY[today.weekday()]})"
    header = esc(f"[데일리브리핑] {date_str} | 뉴스 {len(arts)}건 / 채용 {job_total}건")
    raw = load_json("collected_news.json", {}) or {}
    analyzed_date = (news or {}).get("analyzed_at", "")[:10]
    if raw.get("from_cache"):
        header += "\n" + esc(f"(어제 수집 데이터 사용: {raw.get('cache_date', '')})")
    elif analyzed_date and analyzed_date != f"{today:%Y-%m-%d}":
        header += "\n" + esc(f"(오늘 수집 실패 — {analyzed_date} 분석 데이터 사용)")
    sections = [f"{E('✨ ')}*{header}*"]

    # 1. 오늘의 핵심뉴스 — 0건이면 섹션 생략
    if high:
        lines = [f"{E('📈 ')}*{esc('1. 오늘의 핵심뉴스')}* {esc(f'(영향도 높음 {len(high)}건)')}"]
        for i, a in enumerate(high, 1):
            lines.append("")
            lines.append(f"*{esc(f'{i}. ' + a['title'])}*")
            lines.append(f"{E('💡 ')}{esc(a['one_line_summary'])}")
            if a.get("implication"):
                lines.append(f"{E('👉 ')}_{esc(a['implication'])}_")
            lines.append(f"{E('🔗 ')}{link(a['source'] + ' 원문', a['url'])}")
        sections.append("\n".join(lines))

    # 2. 업계동향 — 0건이면 섹션 생략
    if mid:
        lines = [f"{E('📰 ')}*{esc('2. 업계동향')}* {esc(f'(영향도 보통 {len(mid)}건)')}"]
        for a in mid:
            lines.append(f"• {esc(a['one_line_summary'])} {link('링크', a['url'])}")
        sections.append("\n".join(lines))

    # 3. 오늘의 채용공고 — 키워드별, 0건이면 안내 문구
    lines = [f"{E('💼 ')}*{esc('3. 오늘의 채용공고')}*"]
    if not job_results:
        lines.append(esc("오늘은 새 공고가 없습니다"))
    for r in job_results:
        lines.append("")
        lines.append(f"*{esc('[' + r['keyword'] + ']')}*")
        rows = r.get("jobs", [])
        if not rows:
            lines.append(esc("오늘은 새 공고가 없습니다"))
        for j in rows:
            info = " | ".join(x for x in [
                j.get("experience") or "경력 미표기",
                j.get("location") or "근무지 미표기",
                f"마감 {j.get('deadline') or '미표기'}",
            ])
            lines.append(f"• *{esc(j['company'])}* {esc(j['position'])}")
            lines.append(f"  {esc(info)} {link('공고', j['url'])}")
        review = r.get("needs_review", [])
        if review:
            names = ", ".join(f"{x['company']}({x['position']})" for x in review)
            lines.append(f"{E('⚠️ ')}{esc('확인 필요: ' + names)}")
    sections.append("\n".join(lines))

    # 4. 내일 주목할 것 — 예정 이벤트가 없으면 섹션 생략
    if events:
        lines = [f"{E('📅 ')}*{esc('4. 내일 주목할 것')}*"]
        for ev in events:
            lines.append(f"• *{esc(ev['date'])}* {esc(ev['event'])}")
        sections.append("\n".join(lines))

    stats = {"news_total": len(arts), "news_high": len(high), "news_mid": len(mid),
             "jobs_total": job_total, "events": len(events)}
    return sections, stats


def split_messages(sections, limit):
    """섹션 경계 → 줄 경계 순으로 잘라 limit 이하의 메시지 목록을 만든다"""
    parts, cur = [], ""
    for sec in sections:
        for chunk in ([sec] if len(sec) <= limit else sec.split("\n")):
            add = ("\n\n" if cur and chunk is sec else "\n" if cur else "") + chunk
            if len(cur) + len(add) <= limit:
                cur += add
            else:
                if cur:
                    parts.append(cur)
                cur = chunk[:limit]
    if cur:
        parts.append(cur)
    return parts


# ---------- 발송 ----------
def send(token, chat_id, text, parse_mode):
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
                       "disable_web_page_preview": True}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            data = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        data = json.loads(e.read().decode("utf-8") or "{}")
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "unknown error"))
    return data["result"]["message_id"]


def send_with_retry(token, chat_id, text, parse_mode, retries, delay):
    last = None
    for attempt in range(retries + 1):
        try:
            return send(token, chat_id, text, parse_mode)
        except Exception as e:  # 네트워크 오류·API 오류 모두 재시도 대상
            last = e
            if attempt < retries:
                print(f"발송 실패: {e} → {delay}초 후 재시도합니다.", flush=True)
                time.sleep(delay)
    raise last


# ---------- 기록 ----------
def write_backup(today, parts, cfg):
    logcfg = cfg["logging"]
    d = BASE / logcfg["directory"]
    d.mkdir(exist_ok=True)
    path = d / f"briefing_{today:%Y-%m-%d}.md"
    plain = "\n\n---\n\n".join(re.sub(r"\\(.)", r"\1", p) for p in parts)
    path.write_text(plain + "\n", encoding="utf-8")
    cutoff = time.time() - logcfg["retention_days"] * 86400
    for f in d.glob("briefing_*.md"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
    return path


def append_log(entry, retention_days):
    p = BASE / "newsletter_log.json"
    log = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    log.append(entry)
    cutoff = (datetime.now(KST) - timedelta(days=retention_days)).isoformat()
    log = [x for x in log if x.get("sent_at", "") >= cutoff]
    p.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------- main ----------
def main():
    # 윈도우 콘솔(cp949)에서도 이모지·한글이 깨지지 않게
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    dry = "--dry-run" in sys.argv
    cfg = load_json("monitor_config.json")
    tg = cfg["telegram"]
    news = load_json(cfg["impact_analysis"]["output_file"], {})
    jobs = load_json(cfg["job_filters"]["output_file"], {})
    events = load_json("upcoming_events.json", {}).get("events", [])
    now = datetime.now(KST)

    sections, stats = build_sections(cfg, news, jobs, events, now)
    parts = split_messages(sections, tg["max_message_length"])

    if dry:
        for i, p in enumerate(parts, 1):
            print(f"===== 메시지 {i}/{len(parts)} ({len(p)}자) =====")
            print(p)
        print("STATS", json.dumps(stats, ensure_ascii=False))
        return

    entry = {"sent_at": now.replace(microsecond=0).isoformat(), "date": f"{now:%Y-%m-%d}",
             "status": "success", "parts": len(parts), "chars": [len(p) for p in parts],
             "message_ids": [], "stats": stats, "error": None}

    load_dotenv(BASE / tg.get("env_file", ".env"))
    token = os.environ.get(tg["bot_token_env"])
    chat_id = os.environ.get(tg["chat_id_env"])
    if not token or not chat_id:
        entry.update(status="failed",
                     error=f"{tg['bot_token_env']} 또는 {tg['chat_id_env']}가 .env에 설정되어 있지 않습니다.")
    else:
        try:
            for p in parts:
                entry["message_ids"].append(
                    send_with_retry(token, chat_id, p, tg["parse_mode"], tg.get("retry_on_failure", 1),
                                    tg.get("retry_delay_seconds", 180)))
        except Exception as e:
            entry.update(status="failed" if not entry["message_ids"] else "partial", error=str(e))

    backup = write_backup(now, parts, cfg)
    entry["backup_file"] = str(backup.relative_to(BASE)).replace("\\", "/")
    append_log(entry, cfg["logging"]["retention_days"])

    done_at = datetime.now(KST)
    if entry["status"] == "success":
        print(f"브리핑 발송완료 - 뉴스 {stats['news_total']}건 / 채용 {stats['jobs_total']}건 / "
              f"{done_at:%Y-%m-%d %H:%M}")
    else:
        print(f"브리핑 발송실패 - {len(entry['message_ids'])}/{len(parts)}개 메시지 발송 / "
              f"{done_at:%Y-%m-%d %H:%M}")
    if entry["error"]:
        print("오류:", entry["error"])
    print("기록: newsletter_log.json /", entry["backup_file"])
    sys.exit(0 if entry["status"] == "success" else 1)


if __name__ == "__main__":
    main()
