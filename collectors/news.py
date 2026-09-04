# -*- coding: utf-8 -*-
"""뉴스 수집.

어느 곳에서 가져올지는 config.NEWS_SOURCE 로 정합니다.
  naver  : 네이버 뉴스 검색 API — 원문 링크로 바로 연결 (권장)
  google : 구글 뉴스 RSS — 키가 필요 없지만 링크가 한 단계 더 거칠 수 있음
  both   : 둘 다 조회 후 중복 제거

네이버를 골랐는데 키가 없으면 자동으로 구글로 대체합니다.
"""

import base64
import binascii
import datetime as dt
import hashlib
import html
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

import config
import dedup
from filters import is_noise

ERRORS = []

GOOGLE_RSS = "https://news.google.com/rss/search"
NAVER_API = "https://openapi.naver.com/v1/search/news.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; InsuranceIntelBot/1.0)"}

_KST = dt.timezone(dt.timedelta(hours=9))
_TAG = re.compile(r"<[^>]+>")
_PUNCT = re.compile(r"[\s\"'`·…‘’“”\[\](){}<>「」『』,.\-–—_|/\\!?%:;]+")
_ARTICLE_ID = re.compile(r"/(?:rss/)?articles/([A-Za-z0-9_\-]{20,})")
_URL_IN_BLOB = re.compile(rb"https?://[\x21-\x7e]{8,}")


def _hash(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def _press(url):
    """기사 주소에서 언론사 표기용 도메인만 뽑아냄."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _title_key(title):
    """언론사가 달라도 같은 기사면 같은 값이 나오도록 제목을 정규화."""
    return _PUNCT.sub("", (title or "")).lower()[:60]


def _direct_link(link):
    """구글뉴스 중간 페이지 주소를 실제 기사 주소로 바꿔줌.

    구글뉴스 링크는 기사 주소를 base64로 감싼 형태(protobuf)라 대부분 그대로
    풀립니다. 새 형식이라 못 풀면 원래 링크를 돌려줍니다(동작에는 지장 없음).
    """
    if "news.google.com" not in link:
        return link
    m = _ARTICLE_ID.search(link)
    if not m:
        return link
    try:
        raw = m.group(1)
        blob = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError):
        return link

    idx = blob.find(b"http")
    if idx < 2:
        return link

    # 문자열 앞의 길이 접두사(varint)를 읽어 정확히 그만큼만 잘라냄
    if blob[idx - 2] >= 0x80:
        length = (blob[idx - 2] & 0x7F) | (blob[idx - 1] << 7)
    else:
        length = blob[idx - 1]

    if 15 <= length <= len(blob) - idx:
        url = blob[idx:idx + length].decode("utf-8", "ignore")
    else:
        url = _URL_IN_BLOB.match(blob[idx:]).group(0).decode("utf-8", "ignore") \
            if _URL_IN_BLOB.match(blob[idx:]) else ""

    url = url.strip().split("\\")[0]
    if len(url) < 15 or "news.google.com" in url or " " in url:
        return link
    return url


_META_REFRESH = re.compile(r'url=([^"\'>\s]+)', re.I)
_ANCHOR = re.compile(r'<a[^>]+href="(https?://(?!news\.google\.)[^"]+)"', re.I)
_DATA_AU = re.compile(r'data-n-au="([^"]+)"')


def resolve_link(url):
    """구글뉴스 링크를 실제 기사 주소로 끝까지 따라감.

    _direct_link 로 안 풀리는 새 형식(암호화된 CBMi… 링크)을 위해
    실제로 한 번 접속해 최종 주소를 알아냅니다. 느리므로 발송 직전
    새 기사에만 씁니다. 실패하면 원래 링크를 그대로 돌려줍니다.
    """
    if not url or "news.google.com" not in url:
        return url

    decoded = _direct_link(url)
    if "news.google.com" not in decoded:
        return decoded

    browser = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/124.0.0.0 Safari/537.36",
               "Accept-Language": "ko-KR,ko;q=0.9"}
    try:
        r = requests.get(url, headers=browser, timeout=20, allow_redirects=True)
        final = r.url or ""
        if final and "news.google.com" not in final:
            return final                      # 리다이렉트로 바로 도착한 경우
        body = r.text[:200000]
    except Exception:
        return url

    for pattern in (_DATA_AU, _ANCHOR, _META_REFRESH):
        hit = pattern.search(body)
        if not hit:
            continue
        found = html.unescape(hit.group(1)).strip()
        if found.startswith("http") and "news.google.com" not in found:
            return found
    return url


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
            "url": _direct_link(link),
            "via": "google",
            "sort_key": pub,
        })
        if len(out) >= config.NEWS_MAX_PER_COMPANY:
            break
    return out


def _from_naver(company):
    """네이버 뉴스 검색 API. originallink 가 언론사 원문 주소라 바로 열립니다."""
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
            params={"query": company["news_query"],
                    "display": min(100, max(10, config.NEWS_MAX_PER_COMPANY * 3)),
                    "sort": "date"},
            timeout=30,
        )
        if r.status_code != 200:
            # 네이버가 돌려준 사유를 그대로 보여줘야 원인을 알 수 있음
            #   024 = 키가 틀림 / 101 = 이 앱에 검색 API 권한 없음
            #   012 = 헤더 누락 / 429 = 하루 한도 초과
            detail = " ".join(r.text.split())[:200]
            msg = f"HTTP {r.status_code} · {detail}"
            print(f"  [뉴스/네이버] {company['label']} 실패: {msg}")
            ERRORS.append(f"네이버 {msg}")
            return out
        data = r.json()
    except Exception as e:
        print(f"  [뉴스/네이버] {company['label']} 실패: {e}")
        ERRORS.append(f"{e}")
        return out

    cutoff = None
    hours = getattr(config, "NEWS_LOOKBACK_HOURS", 0)
    if hours:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)

    for row in data.get("items", []):
        link = (row.get("originallink") or row.get("link") or "").strip()
        title = html.unescape(_TAG.sub("", row.get("title", ""))).strip()
        if not link or not title:
            continue

        published, pretty = None, ""
        raw_date = (row.get("pubDate") or "").strip()
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=dt.timezone.utc)
                pretty = published.astimezone(_KST).strftime("%m-%d %H:%M")
            except (TypeError, ValueError):
                pretty = raw_date[:16]
        if cutoff and published and published < cutoff:
            continue

        out.append({
            "id": f"news:{_hash(link)}",
            "kind": "news",
            "company": company["label"],
            "title": title,
            "source": _press(link),
            "date": pretty,
            "url": link,
            "via": "naver",
            "sort_key": published.isoformat() if published else raw_date,
        })
        if len(out) >= config.NEWS_MAX_PER_COMPANY:
            break
    return out


def collect():
    """3사 뉴스를 모아 같은 기사는 한 건으로 합칩니다.

    같은 기사가 두 회사 검색에 걸리면 (예: '생명보험협회·한화생명·교보생명')
    두 번 보내지 않고 한 건으로 묶어 회사명을 나란히 표시합니다.
    """
    ERRORS.clear()
    merged = {}
    order = []
    by_company = {}   # 회사별로 이미 담은 기사 키 — 유사 기사 비교용

    source = getattr(config, "NEWS_SOURCE", "google").lower()
    has_naver = bool(os.environ.get("NAVER_CLIENT_ID", "").strip()
                     and os.environ.get("NAVER_CLIENT_SECRET", "").strip())
    if source == "naver" and not has_naver:
        print("  [뉴스] 네이버 키가 없어 구글 뉴스로 대체합니다")
        source = "google"

    # 1) 설정된 곳에서 먼저 수집
    fetched = []
    for company in config.COMPANIES:
        rows = []
        if source in ("naver", "both"):
            rows += _from_naver(company)
        if source in ("google", "both"):
            rows += _from_google(company)
        fetched.append((company, rows))

    # 2) 네이버만 쓰기로 했는데 한 건도 못 가져왔으면 구글로 재시도
    #    (키가 거부되거나 네이버 쪽 장애일 때 봇이 조용해지는 것을 막음)
    if source == "naver" and not any(rows for _, rows in fetched):
        print("  [뉴스] 네이버에서 결과를 받지 못해 구글 뉴스로 재시도합니다")
        ERRORS.append("네이버 응답 없음 → 구글로 대체")
        fetched = [(c, _from_google(c)) for c in config.COMPANIES]

    for company, rows in fetched:
        for row in rows:
            # 회사명이 제목에 없으면 검색 노이즈로 간주 (config에서 끌 수 있음)
            if getattr(config, "REQUIRE_NAME_IN_TITLE", True):
                plain = row["title"].replace(" ", "")
                if company["news_query"].replace(" ", "") not in plain:
                    continue
            if is_noise(row["title"]):
                continue

            key = _title_key(row["title"])
            if not key:
                continue

            # ① 제목이 완전히 같은 기사 (회사가 달라도 합침)
            found = merged.get(key)

            # ② 표현만 다른 같은 기사 — 오탐을 막기 위해 같은 회사 안에서만 비교
            if found is None:
                for prev_key in by_company.get(company["label"], []):
                    candidate = merged.get(prev_key)
                    if candidate and dedup.is_same_story(candidate["title"],
                                                         row["title"]):
                        found = candidate
                        break

            if found is None:
                row["companies"] = [company["label"]]
                row["_key"] = key
                merged[key] = row
                order.append(key)
                by_company.setdefault(company["label"], []).append(key)
                continue

            # 합쳐진 기사도 이 회사의 비교 대상 목록에 넣어 둠
            canon = found.get("_key")
            bucket = by_company.setdefault(company["label"], [])
            if canon and canon not in bucket:
                bucket.append(canon)

            # 이미 담긴 기사 — 회사명만 덧붙이고 링크는 더 좋은 쪽으로
            if company["label"] not in found["companies"]:
                found["companies"].append(company["label"])
            if found.get("via") == "google" and row.get("via") == "naver":
                found["url"] = row["url"]
                found["source"] = row["source"]
                found["via"] = "naver"

    items = []
    for key in order:
        row = merged[key]
        row["company"] = " · ".join(row["companies"])
        # 고유 ID를 제목 기준으로 — 회사·언론사가 달라도 같은 기사면 한 번만 발송
        row["id"] = "news:" + _hash(key)
        row.pop("_key", None)
        items.append(row)
    return items
