# -*- coding: utf-8 -*-
"""텔레그램 발송."""

import html
import os
import time

import requests

API = "https://api.telegram.org/bot{token}/{method}"

ICON = {
    "dart": "🔔",
    "report": "📊",
    "news": "📰",
}
LABEL = {
    "dart": "공시",
    "report": "리포트",
    "news": "뉴스",
}


def _token():
    tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not tok:
        raise RuntimeError("환경변수 TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다.")
    return tok


def _chat_id():
    cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not cid:
        raise RuntimeError("환경변수 TELEGRAM_CHAT_ID 가 설정되지 않았습니다.")
    return cid


def send_text(text, disable_preview=True):
    """텔레그램에 HTML 형식 메시지 전송. 성공 여부를 bool로 반환."""
    url = API.format(token=_token(), method="sendMessage")
    payload = {
        "chat_id": _chat_id(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    for attempt in range(3):
        try:
            r = requests.post(url, data=payload, timeout=20)
            if r.status_code == 429:
                wait = r.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(wait + 1)
                continue
            if r.ok:
                return True
            print(f"  [텔레그램 오류] {r.status_code} {r.text[:300]}")
            return False
        except requests.RequestException as e:
            print(f"  [텔레그램 예외] {e}")
            time.sleep(2)
    return False


def format_item(item):
    """수집 항목 1건을 텔레그램 메시지로."""
    kind = item["kind"]
    icon = ICON.get(kind, "•")
    label = LABEL.get(kind, kind)
    company = html.escape(item.get("company") or "")
    title = html.escape(item.get("title") or "")
    source = html.escape(item.get("source") or "")
    when = html.escape(item.get("date") or "")
    url = item.get("url") or ""

    head = f"{icon} <b>[{label}] {company}</b>"
    lines = [head, title]
    meta = " · ".join(x for x in (source, when) if x)
    if meta:
        lines.append(f"<i>{meta}</i>")
    if url:
        lines.append(f'<a href="{html.escape(url, quote=True)}">원문 보기</a>')
    return "\n".join(lines)


def send_item(item):
    return send_text(format_item(item), disable_preview=(item["kind"] != "news"))
