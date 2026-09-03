# -*- coding: utf-8 -*-
"""DART 전자공시 수집 (금융감독원 OpenDART API)."""

import datetime as dt
import io
import json
import os
import zipfile
import xml.etree.ElementTree as ET

import requests

import config

ERRORS = []

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "corp_codes.json")
LIST_URL = "https://opendart.fss.or.kr/api/list.json"
CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcpNo}"


def _key():
    k = os.environ.get("DART_API_KEY", "").strip()
    if not k:
        raise RuntimeError("환경변수 DART_API_KEY 가 설정되지 않았습니다.")
    return k


def _load_corp_codes():
    """법인명 → corp_code 매핑. 최초 1회만 내려받아 corp_codes.json 에 캐시."""
    if os.path.exists(CACHE):
        try:
            with open(CACHE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached:
                return cached
        except (json.JSONDecodeError, OSError):
            pass

    print("  DART 법인코드 목록을 내려받는 중… (최초 1회, 약 20MB)")
    r = requests.get(CORPCODE_URL, params={"crtfc_key": _key()}, timeout=120)
    r.raise_for_status()

    wanted = []
    for c in config.COMPANIES:
        wanted.extend(c["dart_names"])

    mapping = {}
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = z.namelist()[0]
        root = ET.fromstring(z.read(name).decode("utf-8"))
        for node in root.iter("list"):
            corp_name = (node.findtext("corp_name") or "").strip()
            corp_code = (node.findtext("corp_code") or "").strip()
            if not corp_name or not corp_code:
                continue
            for w in wanted:
                if w in corp_name:
                    # 같은 이름이 여러 개면 종목코드가 있는 쪽(상장사)을 우선
                    stock = (node.findtext("stock_code") or "").strip()
                    prev = mapping.get(corp_name)
                    if prev is None or (stock and not prev.get("stock_code")):
                        mapping[corp_name] = {"corp_code": corp_code,
                                              "stock_code": stock}

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)
    print(f"  법인코드 {len(mapping)}건 캐시 완료: {list(mapping)}")
    return mapping


def _resolve(company, mapping):
    """설정의 회사 1곳에 해당하는 corp_code 목록."""
    codes = []
    for want in company["dart_names"]:
        for corp_name, info in mapping.items():
            if want in corp_name:
                codes.append((corp_name, info["corp_code"]))
    return codes


def collect():
    """최근 N일 공시를 3사 기준으로 수집."""
    ERRORS.clear()
    items = []
    try:
        mapping = _load_corp_codes()
    except Exception as e:
        print(f"  [DART] 법인코드 조회 실패: {e}")
        ERRORS.append(f"{e}")
        return items

    today = dt.date.today()
    bgn = (today - dt.timedelta(days=config.DART_LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    for company in config.COMPANIES:
        for corp_name, corp_code in _resolve(company, mapping):
            params = {
                "crtfc_key": _key(),
                "corp_code": corp_code,
                "bgn_de": bgn,
                "end_de": end,
                "page_count": 100,
            }
            if config.DART_PBLNTF_TY:
                params["pblntf_ty"] = config.DART_PBLNTF_TY
            try:
                r = requests.get(LIST_URL, params=params, timeout=30)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                print(f"  [DART] {company['label']} 조회 실패: {e}")
                ERRORS.append(f"{e}")
                continue

            status = data.get("status")
            if status == "013":       # 조회 결과 없음
                continue
            if status != "000":
                print(f"  [DART] {company['label']} 응답 오류: "
                      f"{status} {data.get('message')}")
                ERRORS.append("DART {} {}".format(status, data.get("message")))
                continue

            for row in data.get("list", []):
                rcept_no = row.get("rcept_no", "")
                if not rcept_no:
                    continue
                report_nm = (row.get("report_nm") or "").strip()
                rcept_dt = row.get("rcept_dt", "")
                pretty_dt = (f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:]}"
                             if len(rcept_dt) == 8 else rcept_dt)
                items.append({
                    "id": f"dart:{rcept_no}",
                    "kind": "dart",
                    "company": company["label"],
                    "title": report_nm,
                    "source": (row.get("flr_nm") or corp_name).strip(),
                    "date": pretty_dt,
                    "url": VIEWER.format(rcpNo=rcept_no),
                    "sort_key": rcept_dt,
                })
    return items
