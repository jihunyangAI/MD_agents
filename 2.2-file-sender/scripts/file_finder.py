"""file-finder 실행 스크립트 — sender_config.json 의 search_folders 안에서만 파일 검색 (표준 라이브러리만 사용).

사용법:
  python -X utf8 -I scripts/file_finder.py --query "기획서" [--date-hint today] [--ext-hint .pdf]
출력: UTF-8 JSON (found, file, match_count, candidates, reason)
"""
import argparse, os, re, sys, json, unicodedata
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
nfc = lambda s: unicodedata.normalize("NFC", s)
SEP = re.compile(r"[\s_\-.()\[\]]+")
squeeze = lambda s: SEP.sub("", s)  # 띄어쓰기·_·-·.·괄호 제거 후 비교

BASE = Path(__file__).resolve().parent.parent
cfg = json.loads((BASE / "sender_config.json").read_text(encoding="utf-8"))
allowed = {e.lower() for e in cfg["allowed_extensions"]}
max_bytes = cfg["max_file_size_mb"] * 1024 * 1024
depth_limit = int(cfg["search_depth"])
SYSTEM = {"windows", "program files", "program files (x86)", "programdata",
          "$recycle.bin", "system volume information"}

ap = argparse.ArgumentParser()
ap.add_argument("--query", default="")
ap.add_argument("--date-hint", default="")
ap.add_argument("--ext-hint", default="")
args = ap.parse_args()
q = nfc(args.query.strip()).lower()
# 검색어 끝에 붙은 일반 단어(파일·문서·자료·관련) 제거 — 붙여 쓴 경우 포함. 남는 말이 없으면 그대로 둔다
GENERIC_TAIL = re.compile(r"(\s*(관련|파일|문서|자료))+$")
_stripped = GENERIC_TAIL.sub("", q).strip()
if _stripped:
    q = _stripped
date_hint = args.date_hint.strip() or None
ext_hint = args.ext_hint.strip().lower() or None
if ext_hint and ext_hint not in allowed:
    ext_hint = None

now = datetime.now()
today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
ranges = {
    "today": (today0, now + timedelta(days=1)),
    "yesterday": (today0 - timedelta(days=1), today0),
    "2days_ago": (today0 - timedelta(days=2), today0 - timedelta(days=1)),
    "this_week": (today0 - timedelta(days=today0.weekday()), now + timedelta(days=1)),
    "last_week": (today0 - timedelta(days=today0.weekday() + 7), today0 - timedelta(days=today0.weekday())),
    "this_month": (today0.replace(day=1), now + timedelta(days=1)),
}
if date_hint and len(date_hint) == 10 and date_hint[4] == "-":
    d = datetime.strptime(date_hint, "%Y-%m-%d"); ranges[date_hint] = (d, d + timedelta(days=1))
pref = ranges.get(date_hint)

q_has_ext = os.path.splitext(q)[1] in allowed
q_cmp = squeeze(q)

roots = []
for f in cfg["search_folders"]:
    p = os.path.realpath(f)
    if os.path.isdir(p) and not any(part.lower() in SYSTEM for part in Path(p).parts[1:]):
        roots.append(p)
if not roots:
    print(json.dumps({"found": False, "file": None, "match_count": 0, "candidates": [], "reason": "no_valid_folder"}, ensure_ascii=False)); sys.exit()

hits = []
def walk(d, depth, root):
    try:
        entries = list(os.scandir(d))
    except OSError:
        return
    for e in entries:
        try:
            if e.is_symlink() or getattr(e, "is_junction", lambda: False)():
                continue
            if e.is_dir(follow_symlinks=False):
                if depth < depth_limit and e.name.lower() not in SYSTEM:
                    real = os.path.realpath(e.path)
                    if os.path.commonpath([real, root]) == root:
                        walk(e.path, depth + 1, root)
                continue
            name = nfc(e.name); stem, ext = os.path.splitext(name); ext = ext.lower()
            if ext not in allowed or (ext_hint and ext != ext_hint):
                continue
            st = e.stat(follow_symlinks=False)
            if st.st_size > max_bytes:
                continue
            target = name.lower() if q_has_ext else stem.lower()
            if q and q_cmp not in squeeze(target):
                continue
            hits.append((e.path, name, st.st_size, datetime.fromtimestamp(st.st_mtime)))
        except OSError:
            continue

for r in roots:
    walk(r, 0, r)

reason = "no_match"
if not q:
    hits = [h for h in hits if h[3] >= now - timedelta(hours=1)]
    reason = "empty_query"

in_pref = lambda m: pref is not None and pref[0] <= m < pref[1]
hits.sort(key=lambda h: (not in_pref(h[3]), -h[3].timestamp()))

def info(h):
    return {"path": h[0].replace("\\", "/"), "name": h[1], "size_mb": round(h[2] / 1048576, 2),
            "modified": h[3].strftime("%Y-%m-%d %H:%M:%S"), "modified_today": h[3] >= today0}

out = {"found": bool(hits), "file": info(hits[0]) if hits else None, "match_count": len(hits),
       "candidates": [info(h)["path"] for h in hits[:5]], "reason": None if hits else reason}
print(json.dumps(out, ensure_ascii=False, indent=2))
