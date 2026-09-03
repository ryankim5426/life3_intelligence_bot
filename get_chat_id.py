# -*- coding: utf-8 -*-
"""텔레그램 그룹의 chat_id 확인용 도우미.

실행 전에:
  1) BotFather 에서 만든 봇을 팀 그룹방에 초대
  2) 그 방에 아무 메시지나 하나 보내기 (예: /start)
  3) TELEGRAM_BOT_TOKEN 을 설정한 뒤 이 파일 실행
"""

import os
import sys

import requests

token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    token = input("봇 토큰을 붙여넣으세요: ").strip()

r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
data = r.json()

if not data.get("ok"):
    print("오류:", data)
    sys.exit(1)

found = {}
for upd in data.get("result", []):
    msg = upd.get("message") or upd.get("channel_post") or {}
    chat = msg.get("chat") or {}
    if chat.get("id"):
        found[chat["id"]] = f'{chat.get("type")} / {chat.get("title") or chat.get("username") or ""}'

if not found:
    print("받은 메시지가 없습니다. 봇을 그룹에 초대한 뒤 그 방에 메시지를 한 번 보내고 다시 실행하세요.")
    print("(그룹에서 봇이 메시지를 못 읽는 경우: BotFather → /setprivacy → Disable)")
else:
    print("찾은 채팅방:")
    for cid, desc in found.items():
        print(f"  TELEGRAM_CHAT_ID = {cid}   ← {desc}")
