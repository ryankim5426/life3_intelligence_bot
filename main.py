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

import datetime as dt

import config
import dedup
import store
import notify
from collectors import dart, news, reports

KST = dt.timezone(dt.timedelta(hours=9))


def digest_due(state, now):
    """오늘치 뉴스 다이제스트를 지금 보내야 하는지."""
    if getattr(config, "NEWS_DELIVERY", "instant") != "digest":
        return False
    if getattr(config, "NEWS_DIGEST_WEEKDAYS_ONLY", False) and now.weekday() >= 5:
        return False
    try:
        hh, mm = (int(x) for x in config.NEWS_DIGEST_AT.split(":"))
    except (AttributeError, ValueError):
        hh, mm = 8, 30
    today = now.date().isoformat()
    if state.get("last_digest") == today:
        return False
    return (now.hour, now.minute) >= (hh, mm)

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
    force_digest = "--digest" in args   # 시각과 무관하게 지금 다이제스트 발송
    now = dt.datetime.now(KST)

    items, health = gather()

    if check:
        print("\n=== 수집원 점검 결과 ===")
        for k, v in health.items():
            print(f"  {k}: {v}")
        for it in items[:10]:
            print(f"  · [{it['kind']}] {it['company']} | {it['title'][:50]}")
        return

    # 한 번의 실행 안에서 같은 항목이 두 번 들어오는 경우를 먼저 제거
    unique, seen_ids = [], set()
    for it in items:
        if it["id"] in seen_ids:
            continue
        seen_ids.add(it["id"])
        unique.append(it)
    items = unique

    state = store.load()
    fresh = [it for it in items if store.is_new(state, it["id"])]
    fresh.sort(key=lambda x: (ORDER.get(x["kind"], 9), x.get("sort_key", "")))

    first_run = not state.get("initialized")

    # 최근 며칠 사이 이미 보낸 기사와 같은 내용이면 제목이 달라도 건너뜀
    if not (seed or first_run):
        recent = store.recent_stories(state)
        kept = []
        skipped = 0
        for it in fresh:
            if it["kind"] == "news":
                if any(dedup.is_same_story(it["title"], old) for old in recent):
                    store.mark(state, it["id"])   # 조용히 읽음 처리
                    skipped += 1
                    continue
                recent.append(it["title"])
            kept.append(it)
        if skipped:
            print(f"이미 보낸 기사와 같은 내용 {skipped}건 제외")
        fresh = kept

    if seed or first_run:
        for it in items:
            store.mark(state, it["id"])
            if it["kind"] == "news":
                store.remember_story(state, it["title"])
        state["initialized"] = True
        state["last_digest"] = now.date().isoformat()   # 오늘치는 건너뛰고 내일부터
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

    # 뉴스를 모아 보내는 설정이면 대기열에 쌓아 두고, 공시·리포트만 즉시 발송
    digest_mode = getattr(config, "NEWS_DELIVERY", "instant") == "digest"
    # 새로 나갈 뉴스만 실제 기사 주소로 바꿔둠 (접속이 필요해 느리므로 여기서)
    resolved = 0
    for it in fresh:
        if it["kind"] != "news":
            continue
        better = news.resolve_link(it.get("url", ""))
        if better != it.get("url"):
            it["url"] = better
            resolved += 1
    if resolved:
        print(f"뉴스 링크 {resolved}건을 원문 주소로 변환")

    instant = []
    for it in fresh:
        if digest_mode and it["kind"] == "news":
            store.enqueue_news(state, it)
            store.mark(state, it["id"])
            store.remember_story(state, it["title"])
        else:
            instant.append(it)

    if instant:
        print(f"즉시 발송 {len(instant)}건 (공시·리포트)")
    sent = 0
    for it in instant:
        if dry:
            print("---")
            print(notify.format_item(it))
            store.mark(state, it["id"])
            sent += 1
            continue
        if notify.send_item(it):
            store.mark(state, it["id"])
            if it["kind"] == "news":
                store.remember_story(state, it["title"])
            sent += 1

    # 다이제스트 시각이 지났으면 모아둔 뉴스를 한 번에
    if digest_mode:
        waiting = store.queued_count(state)
        if force_digest or digest_due(state, now):
            queued = store.take_news_queue(state)
            blocks = notify.build_digest(queued, now, config.COMPANIES)
            if blocks:
                if dry:
                    for b in blocks:
                        print("---\n" + b)
                    ok = True
                else:
                    ok = notify.send_digest(blocks)
                print(f"뉴스 다이제스트 {len(queued)}건 발송"
                      + ("" if ok else " (일부 실패)"))
                if not ok:      # 실패하면 다음 실행에서 다시 시도
                    state["news_queue"] = queued
                else:
                    state["last_digest"] = now.date().isoformat()
            else:
                state["last_digest"] = now.date().isoformat()
                print("보낼 뉴스가 없어 다이제스트를 건너뜁니다")
        elif waiting:
            print(f"뉴스 {waiting}건 대기 중 "
                  f"(다음 {config.NEWS_DIGEST_AT} 발송 예정)")

    store.save(state)
    if instant:
        print(f"즉시 발송 완료: {sent}/{len(instant)}")
    elif not digest_mode:
        print("신규 항목 없음")


if __name__ == "__main__":
    main()
