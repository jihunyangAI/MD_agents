"""keyword-collector — SNS 원문 수집 → 클로드로 기술 키워드 추출 → data/raw_keywords_{날짜}.json 저장

1단계: Tavily API로 topic별 X·LinkedIn 게시물 수집 (X 실패 시 Nitter RSS 대체)
2단계: 클로드(`claude -p` CLI)로 topic·source별 기술 키워드 추출, 원문에서 등장 횟수 집계
3단계: 전체에서 1회만 등장한 키워드 제외, 언급 횟수 내림차순 정렬 후 저장

사용: python scripts/keyword_collector.py [--date YYYY-MM-DD]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
TAVILY_URL = "https://api.tavily.com/search"
HANGUL = re.compile(r"[가-힣]")

EXTRACT_PROMPT = """아래 SNS게시물에서 언급된 AI제품명, 모델명, 프레임워크명, 서비스명만 추출해 JSON으로 반환해. 플랫폼명(트위터, 링크드인, X, LinkedIn, Twitter)과 일반어(ai, 최신, 블로그, 실시간 등)는 제외해.
게임, 스마트폰·가전 같은 하드웨어 제품명, 부품·제품 모델번호(예: M077CE), AI·개발과 무관한 일반 서비스(숙박, 사무용 프로그램, SEO 도구 등)도 제외해.
한국어 조사가 붙으면 제거하고 판단해 (예: 'Claude가' → 'Claude').
게시물에 실제로 쓰인 표기 그대로 적어. 설명 없이 JSON만 출력해.
출력양식: {{"keyword": ["Claude4", "MCP", "Grok3"]}}

게시물 목록:
{posts_text}
"""

# 모델이 놓친 경우를 대비한 2차 필터 (소문자 비교)
STOPWORDS = {
    "x", "twitter", "트위터", "linkedin", "링크드인", "ai", "인공지능", "최신", "블로그", "실시간",
    "llm", "tech", "테크", "개발자도구", "update", "release", "launch", "new", "tool", "tools",
}


def log(msg):
    print(msg, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / f"keyword_collector_{date.today():%Y%m%d}.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


# ---------------- 1단계: 원문 수집 ----------------
def tavily_search(api_key, query, domains, max_results, time_range):
    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "time_range": time_range,
        "include_domains": domains,
    }
    r = requests.post(TAVILY_URL, json=payload, timeout=30,
                      headers={"Authorization": f"Bearer {api_key}"})
    r.raise_for_status()
    return r.json().get("results", [])


def collect_tavily(api_key, cfg, source, topic):
    col = cfg["collection"]
    sc = col[source]
    target = col["linkedin_post_count"] if source == "linkedin" else col["x_result_count"]
    per_call = min(col.get("tavily_max_results_per_call", 20), 20)
    queries = [col["primary_queries"][source].format(topic=topic)]
    queries += sc["queries_ko"].get(topic, []) + sc["queries_en_fallback"].get(topic, [])

    posts, seen = [], set()
    for q in queries:
        if len(posts) >= target:
            break
        for item in tavily_search(api_key, q, sc["include_domains"], per_call, sc["time_range"]):
            url = item.get("url", "")
            if sc["url_filter"] not in url or url in seen:
                continue
            seen.add(url)
            posts.append({"title": item.get("title", ""), "snippet": item.get("content", ""), "url": url})
    # 한국어 우선 정렬
    if sc["korean_priority"]["sort_hangul_first"]:
        posts.sort(key=lambda p: 0 if HANGUL.search(p["title"] + p["snippet"]) else 1)
    return posts[:target]


def collect_nitter(cfg, topic):
    nf = cfg["collection"]["x"]["nitter_fallback"]
    term = nf["query_terms"].get(topic, topic)
    url = nf["base_url"] + nf["rss_path"].format(query=quote(term))
    r = requests.get(url, timeout=nf["timeout_seconds"], headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    posts = [{"title": e.get("title", ""), "snippet": re.sub(r"<[^>]+>", " ", e.get("summary", "")),
              "url": e.get("link", "")} for e in feed.entries]
    return posts[: cfg["collection"]["x_result_count"]]


def collect_all(cfg, api_key):
    raw = {}
    for topic in cfg["topics"]:
        for source in ("x", "linkedin"):
            posts = []
            try:
                if not api_key:
                    raise RuntimeError("TAVILY_API_KEY 없음")
                posts = collect_tavily(api_key, cfg, source, topic)
                log(f"[수집] {topic}/{source} Tavily {len(posts)}건")
            except Exception as e:
                log(f"[수집] {topic}/{source} Tavily 실패: {e}")
            if source == "x" and not posts and cfg["collection"]["x"]["nitter_fallback"]["enabled"]:
                try:
                    posts = collect_nitter(cfg, topic)
                    log(f"[수집] {topic}/x Nitter RSS {len(posts)}건")
                except Exception as e:
                    log(f"[수집] {topic}/x Nitter RSS 실패: {e} → LinkedIn 결과만 사용")
            raw[(topic, source)] = posts
    return raw


# ---------------- 2단계: 클로드로 키워드 추출 ----------------
def claude_extract(posts, model):
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude CLI를 찾을 수 없음")
    posts_text = "\n".join(f"{i+1}. {p['title']} — {p['snippet'][:500]}" for i, p in enumerate(posts))
    prompt = EXTRACT_PROMPT.format(posts_text=posts_text)
    last_err = None
    for attempt in range(2):  # 실패 시 1회 재시도
        try:
            res = subprocess.run([claude, "-p", "--model", model], input=prompt, capture_output=True,
                                 text=True, encoding="utf-8", timeout=180)
            m = re.search(r"\{.*\}", res.stdout, re.S)
            if res.returncode != 0 or not m:
                raise RuntimeError(f"응답 오류(code={res.returncode}): {(res.stderr or res.stdout)[:200]}")
            return json.loads(m.group(0)).get("keyword", [])
        except Exception as e:
            last_err = e
            time.sleep(2)
    raise RuntimeError(last_err)


def strip_particle(word):
    return re.sub(r"(은|는|이|가|을|를|의|에|에서|와|과|로|으로|도|만)$", "", word.strip()) \
        if HANGUL.search(word[-1:] or "") else word.strip()


def count_mentions(word, posts):
    """원문(제목+본문)에서 키워드 등장 횟수 — 대소문자 무시, 영숫자 경계 기준"""
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])", re.I)
    return sum(len(pat.findall(p["title"] + " " + p["snippet"])) for p in posts)


def load_noise_filter(cfg):
    nf = cfg["analysis"].get("noise_filter", {})
    exclude = {w.lower() for w in nf.get("exclude_keywords", [])} | STOPWORDS
    patterns = [re.compile(p) for p in nf.get("exclude_patterns", [])]
    aliases = {k.lower(): v for k, v in nf.get("aliases", {}).items()}

    def normalize(word):
        """노이즈면 None, 아니면 별칭 통일한 표기 반환"""
        if not word or word.lower() in exclude or any(p.search(word) for p in patterns):
            return None
        return aliases.get(word.lower(), word)
    return normalize


def extract_all(cfg, raw):
    model = cfg["analysis"].get("claude_model", "haiku")
    normalize = load_noise_filter(cfg)
    counts = {}
    for (topic, source), posts in raw.items():
        if not posts:
            continue
        try:
            words = claude_extract(posts, model)
        except Exception as e:
            log(f"[추출] {topic}/{source} 실패 → 스킵: {e}")
            continue
        merged = {}  # 소문자 기준 중복 병합, 첫 표기 유지
        for w in words:
            raw_word = strip_particle(str(w))
            w = normalize(raw_word)
            if not w:
                continue
            n = count_mentions(raw_word, posts) or 1  # 모델이 찾았는데 표기 차이로 못 세면 1회로
            key = w.lower()
            if key in merged:
                # 같은 표기 중복 → 큰 값 유지 / 별칭(다른 표기) → 합산
                if raw_word.lower() == key:
                    merged[key]["count"] = max(merged[key]["count"], n)
                else:
                    merged[key]["count"] += n
            else:
                merged[key] = {"word": w, "count": n}
        counts[(topic, source)] = merged
        log(f"[추출] {topic}/{source} 키워드 {len(merged)}개")
    return counts


# ---------------- 3단계: 필터·정렬·저장 ----------------
def build_result(cfg, counts):
    # 전체 topic에 걸친 합계: 1개 topic에서만 1회 등장 → 제외
    totals, topic_sets = {}, {}
    for (topic, _), merged in counts.items():
        for key, v in merged.items():
            totals[key] = totals.get(key, 0) + v["count"]
            topic_sets.setdefault(key, set()).add(topic)
    excluded = {k for k in totals if totals[k] <= 1 and len(topic_sets[k]) == 1}

    top_n = cfg["analysis"]["top_keywords_count"]
    result = []
    for topic in cfg["topics"]:
        for source in ("x", "linkedin"):
            merged = counts.get((topic, source))
            if merged is None:
                continue
            kws = sorted((v for k, v in merged.items() if k not in excluded),
                         key=lambda v: (-v["count"], v["word"].lower()))
            result.append({"topic": topic, "source": source, "keywords": kws[:top_n]})
    return result, len(excluded)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--reuse-raw", action="store_true",
                    help="수집 생략, data/raw_posts_{날짜}.json으로 추출만 다시 실행")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = json.loads((ROOT / "trend_config.json").read_text(encoding="utf-8"))
    DATA.mkdir(exist_ok=True)
    raw_path = DATA / f"raw_posts_{args.date}.json"

    if args.reuse_raw and raw_path.exists():
        raw = {(r["topic"], r["source"]): r["posts"]
               for r in json.loads(raw_path.read_text(encoding="utf-8"))}
        log(f"[수집] 기존 원문 재사용: {raw_path.relative_to(ROOT)}")
    else:
        raw = collect_all(cfg, os.getenv("TAVILY_API_KEY"))
        # 원문 보관 (재추출·디버깅용)
        raw_path.write_text(json.dumps(
            [{"topic": t, "source": s, "posts": p} for (t, s), p in raw.items()],
            ensure_ascii=False, indent=2), encoding="utf-8")

    counts = extract_all(cfg, raw)
    result, n_excluded = build_result(cfg, counts)

    out = DATA / f"raw_keywords_{args.date}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    uniq = {k["word"].lower() for r in result for k in r["keywords"]}
    log(f"[저장] {out.relative_to(ROOT)} — 고유 키워드 {len(uniq)}개 (1회 등장 제외 {n_excluded}개)")
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
