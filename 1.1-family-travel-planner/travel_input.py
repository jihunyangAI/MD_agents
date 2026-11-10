"""가족 여행 조건을 입력받아 travel_input.json으로 저장하는 스크립트.

사용법:
  1) 대화형 입력:  python travel_input.py
  2) 인자 입력:    python travel_input.py --destination 제주도 --period 2박3일 \
                      --budget 80만원 --family "성인2명, 아이2명(5세,8세)" \
                      --style "자연중심, 아이 체험"
  3) 기본값 사용:  python travel_input.py --default

값을 비워 두면 기본값이 사용됩니다.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

OUTPUT_FILE = Path(__file__).parent / "travel_input.json"

DEFAULTS = {
    "destination": "제주도",
    "period": "2박3일",
    "budget": "80만원",
    "family": "성인2명, 아이2명(5세,8세)",
    "style": "자연중심, 아이 체험",
}

PROMPTS = {
    "destination": "여행지 (예: 제주도, 부산, 강릉)",
    "period": "여행기간 (예: 2박3일, 3박4일)",
    "budget": "총예산 (예: 80만원, 150만원)",
    "family": "가족구성 (예: 성인2명, 아이2명(5세,8세))",
    "style": "여행스타일 (예: 자연중심, 맛집투어, 테마파크)",
}


def parse_period(text: str) -> dict:
    """'2박3일' → {'박': 2, '일': 3}"""
    compact = text.replace(" ", "")
    m = re.search(r"(\d+)박(\d+)일", compact)
    if m:
        nights, days = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(\d+)일", compact)
        days = int(m.group(1)) if m else 3
        nights = max(days - 1, 0)
    return {"원문": text, "박": nights, "일": days}


def parse_budget(text: str) -> int:
    """'80만원', '1,500,000원', '150만' → 원 단위 정수"""
    compact = text.replace(",", "").replace(" ", "").replace("₩", "")
    total = 0
    m = re.search(r"(\d+(?:\.\d+)?)억", compact)
    if m:
        total += int(float(m.group(1)) * 100_000_000)
        compact = compact[m.end():]
    m = re.search(r"(\d+(?:\.\d+)?)만", compact)
    if m:
        total += int(float(m.group(1)) * 10_000)
        compact = compact[m.end():]
    m = re.search(r"(\d+)", compact)
    if m:
        total += int(m.group(1))
    if total <= 0:
        raise ValueError(f"예산을 해석할 수 없습니다: {text}")
    return total


def parse_family(text: str) -> dict:
    """'성인2명, 아이2명(5세,8세)' → 인원 구조"""
    compact = text.replace(" ", "")
    adults_m = re.search(r"(?:성인|어른)(\d+)", compact)
    kids_m = re.search(r"(?:아이|어린이|자녀|아동)(\d+)", compact)
    ages_m = re.search(r"\(([^)]*)\)", compact)

    adults = int(adults_m.group(1)) if adults_m else 0
    ages = [int(a) for a in re.findall(r"(\d+)세", ages_m.group(1))] if ages_m else []
    kids = int(kids_m.group(1)) if kids_m else len(ages)

    return {
        "원문": text,
        "성인": adults,
        "아이": kids,
        "아이_나이": ages,
        "총인원": adults + kids,
    }


def parse_style(text: str) -> list[str]:
    """'자연중심, 맛집투어' → ['자연중심', '맛집투어']"""
    items = [s.strip() for s in re.split(r"[,/+·]", text) if s.strip()]
    return items or [text.strip()]


def ask(key: str) -> str:
    value = input(f"{PROMPTS[key]} [기본값: {DEFAULTS[key]}]: ").strip()
    return value or DEFAULTS[key]


def collect(args: argparse.Namespace) -> dict:
    interactive = not args.default and sys.stdin.isatty()
    raw = {}
    for key in DEFAULTS:
        value = getattr(args, key)
        if value:
            raw[key] = value
        elif interactive:
            raw[key] = ask(key)
        else:
            raw[key] = DEFAULTS[key]
    return raw


def build_data(raw: dict) -> dict:
    period = parse_period(raw["period"])
    budget = parse_budget(raw["budget"])
    family = parse_family(raw["family"])
    return {
        "여행지": raw["destination"].strip(),
        "여행기간": period,
        "총예산": budget,
        "가족구성": family,
        "여행스타일": parse_style(raw["style"]),
        "1인당_예산": budget // family["총인원"] if family["총인원"] else budget,
        "생성일시": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="가족 여행 조건 입력 → travel_input.json 생성")
    parser.add_argument("--destination", help=PROMPTS["destination"])
    parser.add_argument("--period", help=PROMPTS["period"])
    parser.add_argument("--budget", help=PROMPTS["budget"])
    parser.add_argument("--family", help=PROMPTS["family"])
    parser.add_argument("--style", help=PROMPTS["style"])
    parser.add_argument("--default", action="store_true", help="입력 없이 기본값 사용")
    args = parser.parse_args()

    data = build_data(collect(args))
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"저장 완료: {OUTPUT_FILE.name}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
