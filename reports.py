# -*- coding: utf-8 -*-
"""증권사 리포트 수집.

두 곳을 함께 봅니다. 한쪽이 막혀도 나머지는 계속 동작합니다.
  1) 네이버 금융 리서치 - 종목 리포트 (상장사만)
  2) 한경 컨센서스        - 종목/산업 리포트 (교보생명·업종 커버)
"""

import hashlib
import re

import requests
from bs4 import BeautifulSoup

import config

ERRORS = []

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

NAVER_COMPANY = ("https://finance.naver.com/research/company_list.naver"
                 "?keyword=&brokerCode=&writeFromDate=&writeToDate="
                 "&searchType=itemCode&itemCode={code}")
NAVER_BASE = "https://finance.naver.com/research/"

HK_LIST = ("http://consensus.hankyung.com/apps.analysis/analysis.list"
           "?sdate=&edate=&now_page=1&search_text={q}&pagenum=30&report_type={rt}")
HK_BASE = "http://consensus.hankyung.com"


def _hash(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- 네이버 금융
def _naver_reports(company):
    code = company.get("stock_code")
    if not code:
        return []
    out = []
    try:
        r = requests.get(NAVER_COMPANY.format(code=code), headers=UA, timeout=30)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [리포트/네이버] {company['label']} 실패: {e}")
        ERRORS.append(f"{e}")
        return out

    for tr in soup.select("table tr"):
        link = tr.find("a", href=re.compile(r"company_read\.naver\?nid=\d+"))
        if not link:
            continue
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) < 4:
            continue
        title = link.get_text(" ", strip=True)
        href = link["href"]
        url = href if href.startswith("http") else NAVER_BASE + href.lstrip("/")
        nid = re.search(r"nid=(\d+)", href).group(1)
        # 열 순서: 종목명 | 제목 | 증권사 | 첨부 | 작성일 | 조회수
        broker = tds[2] if len(tds) > 2 else ""
        date = ""
        for cell in tds:
            if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", cell):
                date = cell
                break
        out.append({
            "id": f"report:naver:{nid}",
            "kind": "report",
            "company": company["label"],
            "title": title,
            "source": broker,
            "date": date,
            "url": url,
            "sort_key": date,
        })
    return out


# ------------------------------------------------------------ 한경 컨센서스
def _hankyung(query, report_type, company_label):
    out = []
    url = HK_LIST.format(q=requests.utils.quote(query), rt=report_type)
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [리포트/한경] {query} 실패: {e}")
        ERRORS.append(f"{e}")
        return out

    for tr in soup.select("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds]
        date = ""
        for c in cells:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c):
                date = c
                break
        if not date:
            continue
        # PDF 원문 링크를 우선하고, 없으면 상세 링크
        pdf = (tr.find("a", href=re.compile(r"downpdf"))
               or tr.find("a", href=re.compile(r"report_idx")))
        title = ""
        for td in tds:
            txt = td.get_text(" ", strip=True)
            if len(txt) > len(title) and not re.fullmatch(r"[\d\-.]+", txt):
                title = txt
        if not title:
            continue
        link = HK_BASE + pdf["href"] if (pdf and pdf.get("href", "").startswith("/")) \
            else (pdf["href"] if pdf else "https://markets.hankyung.com/consensus")
        broker = cells[-1] if cells else ""
        out.append({
            "id": f"report:hk:{_hash(date + title)}",
            "kind": "report",
            "company": company_label,
            "title": title,
            "source": broker,
            "date": date,
            "url": link,
            "sort_key": date,
        })
    return out


def collect():
    ERRORS.clear()
    items = []
    seen = set()

    for company in config.COMPANIES:
        for row in _naver_reports(company):
            if row["id"] not in seen:
                seen.add(row["id"])
                items.append(row)

        for row in _hankyung(company["news_query"], "CO", company["label"]):
            if company["news_query"] not in row["title"]:
                continue
            if row["id"] not in seen:
                seen.add(row["id"])
                items.append(row)

    if config.INCLUDE_INDUSTRY_REPORTS:
        for kw in config.INDUSTRY_REPORT_KEYWORDS:
            for row in _hankyung(kw, "INDU", "보험업종"):
                if not any(k in row["title"] for k in config.INDUSTRY_REPORT_KEYWORDS):
                    continue
                if row["id"] not in seen:
                    seen.add(row["id"])
                    items.append(row)

    return items
