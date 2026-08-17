#!/usr/bin/env python3
"""문항 파일 검증기 — content/questions-week*.json 전부를 검사한다.

왜 있나: 4주차에서 '규칙에서 벗어난 숫자'가 둘로 읽히는 문항을 만들었는데, 보기 개수·
중복·정답 포함 같은 **구조 검사만으로는 못 잡았다.** 사람 눈으로도 놓친다. 문항의
의미를 코드로 다시 따져 파일의 answer와 대조해야 걸린다.

5주차부터는 더 어렵다 — 정답이 **문항 사이의 관계**(Spaced Retrieval 일정)로 정해져서
파일 한 곳만 봐서는 맞는지 알 수 없다. `srt_schedule` 표와 실제 문항을 대조한다.

사용법:
    python3 scripts/validate_content.py           # 전체 검사
    python3 scripts/validate_content.py --week 5  # 한 주차만

문제가 하나라도 있으면 exit 1. 통과하면 0.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
CHOICES_BY_LEVEL = {1: 2, 2: 4, 3: 4}  # PRD §3.3
FORBIDDEN = ("틀렸", "오답입니다", "다시 하세요", "정답은")  # PRD §3.4


def iter_main(day: dict):
    """day['main']의 (레벨키, 문항) 쌍. '_note' 같은 설명 키는 건너뛴다."""
    for key, q in day["main"].items():
        if isinstance(q, dict):
            yield key, q


def check_structure(data: dict, name: str, errs: list[str]) -> list[int]:
    ids: list[int] = []
    for lvl, q in data["common"]["warmup"].items():
        if isinstance(q, dict):
            ids.append(q["id"])

    days = data["days"]
    if [d["day"] for d in days] != [1, 2, 3, 4, 5]:
        errs.append(f"{name}: day 번호가 1~5가 아니다")

    for day in days:
        for key, q in iter_main(day):
            ids.append(q["id"])
            qid = q["id"]
            level = int(key[0])

            for field in ("prompt", "answer_type"):
                if field not in q:
                    errs.append(f"{qid}: '{field}' 없음")

            for bad in FORBIDDEN:
                if bad in q.get("prompt", ""):
                    errs.append(f"{qid}: 금지 문구 '{bad}' (PRD §3.4)")

            choices = q.get("choices")
            if q["answer_type"] == "static":
                if not choices:
                    errs.append(f"{qid}: static인데 choices 없음")
                    continue
                if len(choices) != CHOICES_BY_LEVEL[level]:
                    errs.append(
                        f"{qid}: 보기 {len(choices)}개 — 레벨 {level}은 "
                        f"{CHOICES_BY_LEVEL[level]}개여야 한다 (PRD §3.3)"
                    )
                if len(set(choices)) != len(choices):
                    errs.append(f"{qid}: 보기에 같은 값이 둘 이상 — 서버가 섞으므로 정답이 둘이 된다")
                if q.get("answer") not in choices:
                    errs.append(f"{qid}: 정답 {q.get('answer')!r}이 보기에 없다")
            elif "answer" in q and q["answer"] is not None:
                errs.append(f"{qid}: dynamic인데 answer가 파일에 있다 (서버가 계산해야 한다)")

        if day["recall"].get("judged") is not False:
            errs.append(f"{name} day{day['day']}: recall은 judged:false여야 한다")
        if not day["mission"]["text"].strip():
            errs.append(f"{name} day{day['day']}: mission이 비어 있다")
    return ids


def check_srt(data: dict, name: str, errs: list[str]) -> None:
    """Spaced Retrieval 일정과 실제 문항을 대조한다 (5주차 이후)."""
    schedule = data.get("srt_schedule")
    if not schedule:
        return

    days_by_num = {d["day"]: d for d in data["days"]}
    claimed_days: set[int] = set()

    # 인출에 쓰이는 오답 전부. 부호화 보기에 이게 들어가면 간섭이 생긴다 — 같은 항목만이
    # 아니라 **다른 항목의 오답도** 마찬가지다 (day1에 '항아리'를 썼다가 그게 day4
    # 주전자 인출의 오답이라 간섭이 생긴 적이 있다. 항목별로만 보던 검사가 놓쳤다).
    all_distractors = {d for it in schedule["items"] for d in it["distractors"]}

    for item in schedule["items"]:
        target, cat = item["target"], item["category"]
        allowed = {target, *item["distractors"]}
        enc_day, ret_days = item["encode_day"], item["retrieve_days"]
        claimed_days |= {enc_day, *ret_days}

        # 없는 day를 가리키면 여기서 걸러낸다 — 아래에서 days_by_num[d]로 죽지 않도록.
        missing = [d for d in (enc_day, *ret_days) if d not in days_by_num]
        if missing:
            errs.append(f"{name} 항목{item['key']}: 일정이 없는 day {missing}를 가리킨다")
            continue

        for d in ret_days:
            if d <= enc_day:
                errs.append(f"{name} 항목{item['key']}: 인출일 {d}이 부호화일 {enc_day}보다 앞이다")

        # 부호화일 — 모든 레벨이 같은 항목을 심어야 한다 (레벨 독립)
        for key, q in iter_main(days_by_num[enc_day]):
            if q.get("answer") != target:
                errs.append(
                    f"{q['id']}: 부호화 정답이 {q.get('answer')!r} — 항목{item['key']}의 "
                    f"{target!r}여야 한다. 레벨마다 다르면 인출과 짝이 어긋난다"
                )
            if q.get("srt_role") != "encode":
                errs.append(f"{q['id']}: srt_role이 'encode'가 아니다")
            # 간섭 방지: 부호화 보기에 (어느 항목이든) 인출용 오답이 섞이면 인출이 오염된다
            leaked = set(q.get("choices", [])) & all_distractors
            if leaked:
                errs.append(
                    f"{q['id']}: 부호화 보기에 인출용 오답 {sorted(leaked)}이 있다 — "
                    f"다른 항목의 오답이어도 간섭이 생긴다"
                )

        # 인출일 — 정답은 항목 그대로, 오답은 전부 같은 범주
        for d in ret_days:
            for key, q in iter_main(days_by_num[d]):
                if q.get("answer") != target:
                    errs.append(
                        f"{q['id']}: 인출 정답이 {q.get('answer')!r} — 항목{item['key']}의 "
                        f"{target!r}여야 한다"
                    )
                if q.get("srt_role") != "retrieve":
                    errs.append(f"{q['id']}: srt_role이 'retrieve'가 아니다")
                outside = set(q.get("choices", [])) - allowed
                if outside:
                    errs.append(
                        f"{q['id']}: 보기 {sorted(outside)}이 '{cat}' 범주 밖이다 — "
                        f"범주가 섞이면 단서만으로 정답이 찍힌다"
                    )
        # 문구: day는 완료 순서지 달력이 아니다
        for d in ret_days:
            for key, q in iter_main(days_by_num[d]):
                if "어제" in q.get("prompt", "") or "오늘 아침" in q.get("prompt", ""):
                    errs.append(
                        f"{q['id']}: '어제' 같은 달력 표현은 쓸 수 없다 — day는 완료 순서다. "
                        f"'지난번/전에'로 쓸 것"
                    )

    for day in data["days"]:
        if "srt_item" in day and day["day"] not in claimed_days:
            errs.append(f"{name} day{day['day']}: srt_item이 있는데 srt_schedule에 없다")


def main() -> None:
    ap = argparse.ArgumentParser(description="문항 파일 검증")
    ap.add_argument("--week", type=int, default=None, help="이 주차만 검사")
    args = ap.parse_args()

    paths = sorted(CONTENT_DIR.glob("questions-week*.json"))
    if not paths:
        sys.exit(f"문항 파일을 찾지 못했습니다: {CONTENT_DIR}")

    errs: list[str] = []
    all_ids: list[int] = []
    checked = []

    for p in paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        ids = check_structure(data, p.name, errs)
        all_ids.extend(ids)  # id 중복은 주차 선택과 무관하게 전체에서 본다
        if args.week is not None and data["week"] != args.week:
            continue
        check_srt(data, p.name, errs)
        checked.append(f"{p.name}({data['domain']}, 문항 {len(ids)})")

    dup = sorted(i for i, c in Counter(all_ids).items() if c > 1)
    if dup:
        errs.append(f"문항 id 중복: {dup}")

    print("검사:", ", ".join(checked) if checked else "(해당 주차 없음)")
    print(f"전체 문항 id {len(all_ids)}개, 중복 {len(dup)}건")
    if errs:
        print(f"\n문제 {len(errs)}건:")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    print("문제 없음.")


if __name__ == "__main__":
    main()
