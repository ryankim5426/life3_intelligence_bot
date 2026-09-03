# -*- coding: utf-8 -*-
"""생보 3사 인텔리전스 봇 — 공시 / 증권사 리포트 / 뉴스 감시.

사용법
    python main.py            평상시 실행 (신규 항목만 텔레그램 발송)
    python main.py --seed     최초 1회. 지금까지 것은 '읽음' 처리만 하고 안 보냄
    python main.py --dry      텔레그램 발송 없이 화면에만 출력 (테스트용)
    python main.py --check    각 수집원이 살아있는지만 점검
"""

import os
import sys
import traceback


def _load_dotenv():
    """같은 폴더의 .env 파일을 환경변수로 읽어들임 (외부 라이브러리 없이)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v


_load_dotenv()

import store
import notify
from collectors import dart, news, reports

COLLECTORS = [
    ("공시(DART)", dart.collect, dart),
    ("증권사 리포트", reports.collect, reports),
    ("뉴스", news.collect, news),
]

ORDER = {"dart": 0, "report": 1, "news": 2}


def gather():
    all_items, report = [], {}
    for name, fn, mod in COLLECTORS:
        try:
            got = fn()
            all_items.extend(got)
            errs = list(getattr(mod, "ERRORS", []))
            if errs:
                report[name] = (f"일부 실패 ({len(got)}건 조회, "
                                f"오류 {len(errs)}건) → {errs[0][:120]}")
            else:
                report[name] = f"정상 ({len(got)}건 조회)"
            print(f"[{name}] {len(got)}건 조회"
                  + (f" / 오류 {len(errs)}건" if errs else ""))
        except Exception as e:
            report[name] = f"실패: {e}"
            print(f"[{name}] 실패: {e}")
            traceback.print_exc()
    return all_items, report


def main():
    args = set(sys.argv[1:])
    dry = "--dry" in args
    seed = "--seed" in args
    check = "--check" in args

    items, health = gather()

    if check:
        print("\n=== 수집원 점검 결과 ===")
        for k, v in health.items():
            print(f"  {k}: {v}")
        for it in items[:10]:
            print(f"  · [{it['kind']}] {it['company']} | {it['title'][:50]}")
        return

    state = store.load()
    fresh = [it for it in items if store.is_new(state, it["id"])]
    fresh.sort(key=lambda x: (ORDER.get(x["kind"], 9), x.get("sort_key", "")))

    first_run = not state.get("initialized")

    if seed or first_run:
        for it in items:
            store.mark(state, it["id"])
        state["initialized"] = True
        store.save(state)
        msg = (f"✅ <b>생보 3사 인텔리전스 봇 가동</b>\n"
               f"삼성생명 · 교보생명 · 한화생명\n"
               f"공시 / 증권사 리포트 / 뉴스를 감시합니다.\n\n"
               f"<i>기존 {len(items)}건은 읽음 처리했고, "
               f"지금부터 올라오는 것만 알려드립니다.</i>")
        print(msg)
        if not dry:
            notify.send_text(msg)
        return

    if not fresh:
        print("신규 항목 없음")
        return

    print(f"신규 {len(fresh)}건 발송")
    sent = 0
    for it in fresh:
        if dry:
            print("---")
            print(notify.format_item(it))
            store.mark(state, it["id"])
            sent += 1
            continue
        if notify.send_item(it):
            store.mark(state, it["id"])
            sent += 1

    store.save(state)
    print(f"발송 완료: {sent}/{len(fresh)}")


if __name__ == "__main__":
    main()
