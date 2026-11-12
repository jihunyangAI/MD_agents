"""trend-analyzer — 이번 주/지난 주 키워드 순위 비교 → 4분류 + 클로드 요약 → data/trend_report_{날짜}.json

1단계: data/raw_keywords_{오늘}.json, data/raw_keywords_{7일 전}.json(없으면 '지난주 없음') 읽기
2단계: 분야별 순위 비교 → 급상승 / 상승 / 하락 / 신규
3단계: 클로드(`claude -p`)로 분야별 요약 + 전체 흐름 2~3문장 요약 (실패 시 규칙 기반 요약)
4단계: data/trend_report_{오늘}.json 저장 (모든 입출력 utf-8)

사용: python scripts/trend_analyzer.py [--date YYYY-MM-DD] [--prev-file 경로]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"

SUMMARY_PROMPT = """다음은 SNS(X·LinkedIn) 기술 키워드의 분야별 주간 순위 변화 데이터야.
{prev_note}
각 분야(topic)별로 1~2문장 요약과, 전체 트렌드 흐름을 2~3문장으로 요약해.
예: '이번 주 테크 분야에서는 AI 에이전트 관련 키워드가 급부상했으며...'
데이터에 없는 사실은 지어내지 말고, 키워드 이름은 그대로 써. 한국어로 쓰고 설명 없이 JSON만 출력해.
출력양식: {{"topics": {{"<분야명>": "<요약>"}}, "overall": "<전체 요약>"}}

데이터:
{data}
"""


def log(msg):
    print(msg, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / f"trend_analyzer_{date.today():%Y%m%d}.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------- 1단계: 데이터 읽기 ----------------
PREV_WINDOW_DAYS = (3, 13)  # 정확히 7일 전 파일이 없을 때 찾는 범위


def find_prev(today):
    """지난주 파일: 7일 전 파일 우선, 없으면 3~13일 전 중 가장 최근 파일. 없으면 존재하지 않는 경로 반환"""
    exact = DATA / f"raw_keywords_{(today - timedelta(days=7)).isoformat()}.json"
    if exact.exists():
        return exact
    lo, hi = PREV_WINDOW_DAYS
    for back in range(lo, hi + 1):
        p = DATA / f"raw_keywords_{(today - timedelta(days=back)).isoformat()}.json"
        if p.exists():
            return p
    return exact
def topic_ranking(raw, topic, top_n):
    """분야 내 source(x·linkedin) 합산 → 언급 횟수 내림차순 순위 (1위부터)"""
    totals, display, sources = {}, {}, {}
    for rec in raw:
        if rec["topic"] != topic:
            continue
        for k in rec["keywords"]:
            key = k["word"].lower()
            totals[key] = totals.get(key, 0) + k["count"]
            display.setdefault(key, k["word"])
            sources.setdefault(key, set()).add(rec["source"])
    ordered = sorted(totals, key=lambda k: (-totals[k], k))[:top_n]
    return {k: {"word": display[k], "rank": i + 1, "count": totals[k],
                "sources": sorted(sources[k], key=lambda s: s != "x")}  # x 먼저
            for i, k in enumerate(ordered)}


# ---------------- 2단계: 분류 ----------------
def classify(cur, prev, threshold):
    res = {"rising": [], "up": [], "down": [], "new": []}
    for key, c in cur.items():
        if prev is None or key not in prev:
            res["new"].append({"word": c["word"], "rank": c["rank"], "count": c["count"],
                               "sources": c["sources"]})
            continue
        change = prev[key]["rank"] - c["rank"]  # 양수 = 순위 상승
        item = {"word": c["word"], "rank_change": change, "rank": c["rank"],
                "prev_rank": prev[key]["rank"], "count": c["count"],
                "prev_count": prev[key]["count"], "sources": c["sources"]}
        if change >= threshold:
            res["rising"].append(item)
        elif change > 0:
            res["up"].append(item)
        elif change < 0:
            res["down"].append(item)
    res["rising"].sort(key=lambda x: -x["rank_change"])
    res["up"].sort(key=lambda x: -x["rank_change"])
    res["down"].sort(key=lambda x: x["rank_change"])
    res["new"].sort(key=lambda x: x["rank"])
    return res


# ---------------- 3단계: 요약 ----------------
def claude_summary(payload, has_prev, model):
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude CLI를 찾을 수 없음")
    prev_note = ("지난 주 데이터와 비교한 결과다." if has_prev else
                 "지난 주 데이터가 없는 첫 실행이라 모든 키워드가 신규다. 순위 변화 대신 이번 주 상위 키워드 위주로 요약해.")
    prompt = SUMMARY_PROMPT.format(prev_note=prev_note,
                                   data=json.dumps(payload, ensure_ascii=False, indent=1))
    last_err = None
    for _ in range(2):  # 실패 시 1회 재시도
        try:
            r = subprocess.run([claude, "-p", "--model", model], input=prompt, capture_output=True,
                               text=True, encoding="utf-8", timeout=180)
            m = re.search(r"\{.*\}", r.stdout, re.S)
            if r.returncode != 0 or not m:
                raise RuntimeError(f"응답 오류(code={r.returncode}): {(r.stderr or r.stdout)[:200]}")
            out = json.loads(m.group(0))
            return out.get("topics", {}), out.get("overall", "")
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise RuntimeError(last_err)


def fallback_summary(topic, cls, top, has_prev):
    names = lambda items: ", ".join(i["word"] for i in items[:3])
    if not has_prev:
        return f"이번 주 {topic} 분야에서는 {names(top)} 등이 가장 많이 언급되었습니다. (지난주 데이터 없음)"
    parts = [f"이번 주 {topic} 분야에서는"]
    if cls["rising"]:
        parts.append(f"{names(cls['rising'])}이(가) 급상승했고,")
    if cls["new"]:
        parts.append(f"{names(cls['new'])}이(가) 새로 진입했습니다.")
    else:
        parts.append(f"{names(top)} 중심의 흐름이 이어졌습니다.")
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--prev-file", help="지난주 파일 직접 지정 (기본: raw_keywords_{7일 전}.json)")
    args = ap.parse_args()

    cfg = read_json(ROOT / "trend_config.json")
    top_n = cfg["analysis"]["top_keywords_count"]
    threshold = cfg["analysis"]["trending_rise_threshold"]
    model = cfg["analysis"].get("claude_model", "haiku")

    today = date.fromisoformat(args.date)
    cur_path = DATA / f"raw_keywords_{today.isoformat()}.json"
    prev_path = Path(args.prev_file) if args.prev_file else find_prev(today)

    if not cur_path.exists():
        log(f"[읽기] 이번 주 파일 없음: {cur_path.name} → keyword-collector를 먼저 실행하세요")
        return 1
    cur_raw = read_json(cur_path)
    prev_raw = read_json(prev_path) if prev_path.exists() else None
    has_prev = prev_raw is not None
    log(f"[읽기] 이번 주 {cur_path.name} / 지난 주 {prev_path.name if has_prev else '지난주 없음'}")

    topics_out, summary_input = [], {}
    for topic in cfg["topics"]:
        cur = topic_ranking(cur_raw, topic, top_n)
        prev = topic_ranking(prev_raw, topic, top_n) if has_prev else None
        cls = classify(cur, prev, threshold)
        # 변화표용: 이번 주 top20 각각에 전주 순위·빈도와 분류를 붙인다
        cat_of = {i["word"].lower(): name for name in ("rising", "up", "down", "new") for i in cls[name]}
        top = []
        for key, c in cur.items():
            p = prev.get(key) if prev else None
            top.append({**c,
                        "prev_rank": p["rank"] if p else None,
                        "prev_count": p["count"] if p else None,
                        "rank_change": (p["rank"] - c["rank"]) if p else None,
                        "category": cat_of.get(key, "same")})
        topics_out.append({"topic": topic, **cls, "top_keywords": top, "summary": ""})
        summary_input[topic] = {
            "top10": [f"{t['word']}({t['count']})" for t in top[:10]],
            **({k: [i["word"] for i in cls[k][:8]] for k in ("rising", "up", "down", "new")} if has_prev else {}),
        }
        log(f"[분류] {topic}: 급상승 {len(cls['rising'])} / 상승 {len(cls['up'])} / "
            f"하락 {len(cls['down'])} / 신규 {len(cls['new'])}")

    try:
        topic_sums, overall = claude_summary(summary_input, has_prev, model)
        log("[요약] 클로드 요약 완료")
    except Exception as e:
        log(f"[요약] 클로드 실패 → 규칙 기반 요약: {e}")
        topic_sums, overall = {}, ""
    for t in topics_out:
        t["summary"] = topic_sums.get(t["topic"]) or fallback_summary(
            t["topic"], t, t["top_keywords"], has_prev)
    if not overall:
        overall = " ".join(t["summary"] for t in topics_out[:2])

    report = {
        "date": today.isoformat(),
        "previous_date": prev_path.stem.replace("raw_keywords_", "") if has_prev else None,
        "has_previous": has_prev,
        "trending_rise_threshold": threshold,
        "overall_summary": overall,
        "topics": topics_out,
    }
    out = DATA / f"trend_report_{today.isoformat()}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[저장] {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
