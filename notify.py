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


# --- 뉴스 다이제스트 ---------------------------------------------------------

MAX_CHARS = 3500          # 텔레그램 한 통 제한(4096)보다 여유 있게
_WEEKDAY = ("월", "화", "수", "목", "금", "토", "일")


def _company_order(label, companies):
    """설정에 적은 회사 순서대로 정렬하기 위한 값."""
    for i, c in enumerate(companies):
        if c["label"] in label:
            return i
    return len(companies)


def build_digest(items, now, companies):
    """모아둔 뉴스를 회사별로 묶어 한 통(또는 몇 통)의 메시지로."""
    if not items:
        return []

    ordered = sorted(
        items,
        key=lambda x: (_company_order(x.get("company", ""), companies),
                       x.get("sort_key") or ""),
    )

    header = (f"📰 <b>오늘의 뉴스</b>  {now.month}월 {now.day}일"
              f"({_WEEKDAY[now.weekday()]})\n"
              f"<i>지난 하루 {len(ordered)}건 · 중복 정리 완료</i>")

    blocks, current = [], None
    lines = [header]
    for item in ordered:
        company = item.get("company") or ""
        if company != current:
            current = company
            lines.append(f"\n<b>▸ {html.escape(company)}</b>")
        title = html.escape(item.get("title") or "")
        url = item.get("url") or ""
        press = html.escape(item.get("source") or "")
        link = f'<a href="{html.escape(url, quote=True)}">{title}</a>' if url else title
        lines.append(f"· {link}" + (f"  <i>{press}</i>" if press else ""))

    # 길면 여러 통으로 나눔 (회사 구분선은 유지)
    for line in lines:
        if not blocks:
            blocks.append(line)
            continue
        if len(blocks[-1]) + len(line) + 1 > MAX_CHARS:
            blocks.append(line)
        else:
            blocks[-1] += "\n" + line
    return blocks


def send_digest(blocks):
    sent = 0
    for block in blocks:
        if send_text(block, disable_preview=True):
            sent += 1
    return sent == len(blocks)
