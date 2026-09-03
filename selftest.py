# -*- coding: utf-8 -*-
"""오프라인 자체 점검 — 실제 네트워크 없이 파싱/필터/중복제거 로직 검증."""
import os, sys, json, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import filters, store, notify, config

fail = 0
def check(name, cond):
    global fail
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond: fail += 1

print("\n[1] 스포츠 노이즈 필터")
noise = [
    "한화생명e스포츠, LCK 서머 우승… 3연속 결승 진출",
    "'한화생명e스포츠' 새 미드라이너 영입",
    "삼성생명 블루밍스, WKBL 개막전 승리",
    "삼성생명 여자농구단 신임 감독 선임",
    "한화 이글스, 프로야구 4연승",
]
keep = [
    "한화생명, 상반기 순이익 5000억… CSM 확대",
    "삼성생명 K-ICS 비율 190%대 유지",
    "교보생명, 후순위채 3000억 발행",
    "금융당국, GA 1200% 룰 확대 시행",
    "한화생명, e스포츠 마케팅 효과로 보험 브랜드 인지도 실적 개선",
]
for t in noise:
    check(f"차단: {t[:34]}", filters.is_noise(t))
for t in keep:
    check(f"통과: {t[:34]}", not filters.is_noise(t))

print("\n[2] 네이버 금융 리포트 파싱")
from collectors import reports
import requests as _rq
NAVER_HTML = """
<table class="type_1"><tr><th>종목명</th></tr>
<tr><td><a href="/item/main.naver?code=088350">한화생명</a></td>
<td><a href="/research/company_read.naver?nid=77777">2Q26 CSM 순증 지속, 목표주가 상향</a></td>
<td>미래에셋증권</td><td><a href="x.pdf">첨부</a></td><td>26.09.02</td><td>1234</td></tr>
<tr><td><a href="/item/main.naver?code=088350">한화생명</a></td>
<td><a href="/research/company_read.naver?nid=77778">배당 확대 여력 점검</a></td>
<td>NH투자증권</td><td></td><td>26.09.01</td><td>987</td></tr>
</table>"""
class R:
    text = NAVER_HTML; encoding = "euc-kr"
    def raise_for_status(self): pass
reports.requests = types.SimpleNamespace(get=lambda *a, **k: R(), utils=_rq.utils)
rows = reports._naver_reports({"label": "한화생명", "stock_code": "088350"})
check(f"2건 파싱 (실제 {len(rows)}건)", len(rows) == 2)
if rows:
    check("제목 추출", "CSM" in rows[0]["title"])
    check("증권사 추출: " + rows[0]["source"], rows[0]["source"] == "미래에셋증권")
    check("작성일 추출: " + rows[0]["date"], rows[0]["date"] == "26.09.02")
    check("링크 절대경로", rows[0]["url"].startswith("https://finance.naver.com"))
    check("고유 ID", rows[0]["id"] == "report:naver:77777")

print("\n[3] 한경컨센서스 파싱")
HK_HTML = """
<table><tr><th>작성일</th></tr>
<tr><td>2026-09-02</td><td>기업</td>
<td><a href="/apps.analysis/analysis.list?report_idx=123">생명보험 - 금리 하락기 밸류 점검</a></td>
<td><a href="/analysis/downpdf?report_idx=123">pdf</a></td><td>홍길동</td><td>키움증권</td></tr>
</table>"""
class R2:
    text = HK_HTML; encoding = "utf-8"
    def raise_for_status(self): pass
reports.requests = types.SimpleNamespace(get=lambda *a, **k: R2(), utils=_rq.utils)
hk = reports._hankyung("생명보험", "INDU", "보험업종")
check(f"1건 파싱 (실제 {len(hk)}건)", len(hk) == 1)
if hk:
    check("PDF 링크", "downpdf" in hk[0]["url"])
    check("날짜", hk[0]["date"] == "2026-09-02")

print("\n[4] 구글뉴스 RSS 파싱 + 필터 결합")
from collectors import news
RSS = """<?xml version="1.0"?><rss><channel>
<item><title>한화생명, 2분기 순익 급증 - 매일경제</title>
<link>https://n.example/1</link><guid>g1</guid>
<pubDate>Wed, 02 Sep 2026 09:00:00 GMT</pubDate><source>매일경제</source></item>
<item><title>한화생명e스포츠, LCK 결승 진출 - 데일리e스포츠</title>
<link>https://n.example/2</link><guid>g2</guid>
<pubDate>Wed, 02 Sep 2026 10:00:00 GMT</pubDate><source>데일리e스포츠</source></item>
<item><title>무관한 기사 제목 - 어디신문</title>
<link>https://n.example/3</link><guid>g3</guid>
<pubDate>Wed, 02 Sep 2026 11:00:00 GMT</pubDate><source>어디신문</source></item>
</channel></rss>"""
class R3:
    content = RSS.encode("utf-8")
    def raise_for_status(self): pass
news.requests = types.SimpleNamespace(get=lambda *a, **k: R3(), RequestException=Exception)
orig = config.COMPANIES
config.COMPANIES = [{"label": "한화생명", "news_query": "한화생명", "stock_code": "088350", "dart_names": []}]
got = news.collect()
check(f"3건 중 1건만 통과 (실제 {len(got)}건)", len(got) == 1)
if got:
    check("남은 기사가 실적 기사", "순익" in got[0]["title"])
    check("언론사 추출: " + got[0]["source"], got[0]["source"] == "매일경제")
config.COMPANIES = orig

print("\n[5] 중복 제거 / 상태 저장")
store.STATE_PATH = "/tmp/_state_test.json"
if os.path.exists(store.STATE_PATH): os.remove(store.STATE_PATH)
st = store.load()
check("첫 실행 감지", st["initialized"] is False)
check("신규 판정", store.is_new(st, "dart:X"))
store.mark(st, "dart:X"); st["initialized"] = True; store.save(st)
st2 = store.load()
check("재실행 시 중복 차단", not store.is_new(st2, "dart:X"))
check("초기화 플래그 유지", st2["initialized"] is True)

print("\n[6] 텔레그램 메시지 포맷")
msg = notify.format_item({
    "kind": "dart", "company": "한화생명",
    "title": "주요사항보고서(자기주식취득결정) <시험&문자>",
    "source": "한화생명보험", "date": "2026-09-03",
    "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260903000123"})
print("  ---\n  " + msg.replace("\n", "\n  ") + "\n  ---")
check("HTML 이스케이프 처리", "&lt;시험&amp;문자&gt;" in msg)
check("종류 표시", "[공시]" in msg)
check("링크 포함", "dart.fss.or.kr" in msg)

print(f"\n{'='*46}\n결과: {'전체 통과' if fail == 0 else str(fail) + '건 실패'}\n{'='*46}")
sys.exit(1 if fail else 0)
