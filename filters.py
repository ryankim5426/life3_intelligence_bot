# -*- coding: utf-8 -*-
"""스포츠단 등 노이즈 기사 걸러내기."""

import config


def _norm(text):
    return (text or "").replace(" ", "").lower()


def is_noise(title):
    """제목이 제외 대상이면 True.

    제외어가 있어도 EXCLUDE_OVERRIDE(실적·규제 등 경영 키워드)가
    함께 들어 있으면 살려 둡니다.
    """
    t = _norm(title)
    hit = None
    for kw in config.EXCLUDE_KEYWORDS:
        if _norm(kw) and _norm(kw) in t:
            hit = kw
            break
    if hit is None:
        return False
    for kw in config.EXCLUDE_OVERRIDE:
        if _norm(kw) and _norm(kw) in t:
            return False
    return True


def explain(title):
    """디버깅용 — 왜 걸러졌는지."""
    t = _norm(title)
    for kw in config.EXCLUDE_KEYWORDS:
        if _norm(kw) in t:
            for ov in config.EXCLUDE_OVERRIDE:
                if _norm(ov) in t:
                    return f"통과 (제외어 '{kw}' 있으나 '{ov}' 로 예외)"
            return f"차단 (제외어 '{kw}')"
    return "통과"
