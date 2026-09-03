# -*- coding: utf-8 -*-
"""발송 이력 저장 — 같은 항목을 두 번 보내지 않기 위한 상태 파일."""

import json
import os
import time

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
MAX_KEEP = 3000  # 항목이 너무 쌓이지 않게 오래된 것부터 정리


def load():
    if not os.path.exists(STATE_PATH):
        return {"seen": {}, "initialized": False}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"seen": {}, "initialized": False}
    data.setdefault("seen", {})
    data.setdefault("initialized", False)
    return data


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
