# -*- coding: utf-8 -*-
"""발송 이력 저장 — 같은 항목을 두 번 보내지 않기 위한 상태 파일."""

import json
import os
import time

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
MAX_KEEP = 3000        # 항목이 너무 쌓이지 않게 오래된 것부터 정리
STORY_HOURS = 72       # 최근 며칠간 보낸 기사 제목을 기억할지
STORY_MAX = 400        # 기억할 제목 최대 개수


def _blank():
    return {"seen": {}, "stories": {}, "news_queue": [], "initialized": False}


# --- 뉴스 다이제스트 대기열 -------------------------------------------------

QUEUE_MAX = 200


def enqueue_news(state, item):
    """즉시 보내지 않고 다음 다이제스트까지 모아 둠."""
    queue = state.setdefault("news_queue", [])
    keep = ("id", "kind", "company", "title", "source", "date", "url", "sort_key")
    queue.append({k: item.get(k) for k in keep})
    if len(queue) > QUEUE_MAX:
        del queue[:len(queue) - QUEUE_MAX]


def take_news_queue(state):
    """대기열을 통째로 꺼내고 비움."""
    queue = state.get("news_queue", [])
    state["news_queue"] = []
    return queue


def queued_count(state):
    return len(state.get("news_queue", []))


def load():
    if not os.path.exists(STATE_PATH):
        return _blank()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _blank()
    data.setdefault("seen", {})
    data.setdefault("stories", {})
    data.setdefault("news_queue", [])
    data.setdefault("initialized", False)
    return data


def recent_stories(state):
    """최근 STORY_HOURS 안에 발송한 뉴스 제목 목록 (오래된 것은 정리)."""
    cutoff = int(time.time()) - STORY_HOURS * 3600
    stories = {t: ts for t, ts in state.get("stories", {}).items() if ts >= cutoff}
    if len(stories) > STORY_MAX:
        keep = sorted(stories.items(), key=lambda kv: kv[1], reverse=True)[:STORY_MAX]
        stories = dict(keep)
    state["stories"] = stories
    return list(stories.keys())


def remember_story(state, title):
    state.setdefault("stories", {})[title] = int(time.time())


def save(state):
    seen = state.get("seen", {})
    if len(seen) > MAX_KEEP:
        # 오래된 순으로 잘라냄
        keep = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:MAX_KEEP]
        state["seen"] = dict(keep)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def is_new(state, item_id):
    return item_id not in state["seen"]


def mark(state, item_id):
    state["seen"][item_id] = int(time.time())
