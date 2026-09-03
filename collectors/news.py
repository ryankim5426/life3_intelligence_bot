# -*- coding: utf-8 -*-
"""뉴스 수집.

기본: 구글 뉴스 RSS (API 키 불필요)
선택: 네이버 뉴스 검색 API (NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 이 있으면 함께 사용)
"""

import hashlib
import os
import urllib.parse
import xml.etree.ElementTree as ET

import requests

import config
from filters import is_noise

ERRORS = []

GOOGLE_RSS = "https://news.google.com/rss/search"
NAVER_API = "https://openapi.naver.com/v1/search/news.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; InsuranceIntelBot/1.0)"}


def _hash(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _split_google_title(title):
    """구글뉴스 제목은 '기사제목 - 언론사' 형식."""
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        return head.strip(), tail.strip()
    return title.strip(), ""


def _from_google(company):
    query = f'"{company["news_query"]}" {config.NEWS_LOOKBACK}'.strip()
    url = (f"{GOOGLE_RSS}?q={urllib.parse.quote(query)}"
           f"&hl=ko&gl=KR&ceid=KR:ko")
    out = []
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  [뉴스/구글] {company['label']} 실패: {e}")
        ERRORS.append(f"{e}")
        return out

    for item in root.findall(".//item"):
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        if not title_raw or not link:
            continue
        title, press = _split_google_title(title_raw)
        src_node = item.find("source")
        if src_node is not None and (src_node.text or "").strip():
            press = src_node.text.strip()
        out.append({
            "id": f"news:{_hash(guid)}",
            "kind": "news",
            "company": company["label"],
            "title": title,
            "source": press,
            "date": pub[:16],
            "url": link,
            "sort_key": pub,
        })
        if len(out) >= config.NEWS_MAX_PER_COMPANY:
            break
    return out


def _from_naver(company):
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        return []
    out = []
    try:
        r = requests.get(
            NAVER_API,
            headers={"X-Naver-Client-Id": cid,
                     "X-Naver-Client-Secret": secret, **UA},
            params={"query": company["news_query"], "display": 30, "sort": "date"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  [뉴스/네이버] {company['label']} 실패: {e}")
        ERRORS.append(f"{e}")
        return out

    import re
    tag = re.compile(r"<[^>]+>")
    for row in data.get("items", []):
        link = row.get("originallink") or row.get("link") or ""
        title = tag.sub("", row.get("title", "")).replace("&quot;", '"') \
                   .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        if not link or not title:
            continue
        out.append({
            "id": f"news:{_hash(link)}",
            "kind": "news",
            "company": company["label"],
            "title": title.strip(),
            "source": urllib.parse.urlparse(link).netloc,
            "date": (row.get("pubDate") or "")[:16],
            "url": link,
            "sort_key": row.get("pubDate", ""),
        })
    return out


def collect():
    ERRORS.clear()
    items = []
    seen_titles = set()
    for company in config.COMPANIES:
        for row in _from_google(company) + _from_naver(company):
            # 회사명이 제목에 없으면 검색 노이즈로 간주 (config에서 끌 수 있음)
            if getattr(config, "REQUIRE_NAME_IN_TITLE", True):
                plain = row["title"].replace(" ", "")
                if company["news_query"].replace(" ", "") not in plain:
                    continue
            if is_noise(row["title"]):
                continue
            key = (company["label"], row["title"][:40])
            if key in seen_titles:
                continue
            seen_titles.add(key)
            items.append(row)
    return items
