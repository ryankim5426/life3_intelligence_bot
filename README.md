# 생보 3사 인텔리전스 봇

삼성생명 · 교보생명 · 한화생명의 **공시 / 증권사 리포트 / 뉴스**가 올라오는 즉시
팀 텔레그램 그룹방으로 쏴 주는 봇입니다.

| 종류 | 출처 | 비고 |
|---|---|---|
| 🔔 공시 | 금융감독원 OpenDART API | 3사 전체 공시. 교보생명 포함 |
| 📊 증권사 리포트 | 네이버 금융 리서치 + 한경 컨센서스 | 종목 리포트 + 보험 산업 리포트 |
| 📰 뉴스 | 구글 뉴스 RSS (+선택: 네이버 뉴스 API) | 회사명이 제목에 들어간 기사만 |

**스포츠단 기사는 걸러냅니다.** 한화생명e스포츠(LCK), 삼성생명 블루밍스(여자농구),
한화 이글스 등은 제외어로 차단하되, "e스포츠 마케팅 → 브랜드 실적" 같은
경영 관련 기사는 살려 둡니다. 제외어 목록은 `config.py`에서 직접 고칠 수 있습니다.

---

## 1단계 · 텔레그램 준비 (5분)

1. 텔레그램에서 **@BotFather** 검색 → `/newbot` → 이름과 아이디 입력
   → **토큰**(`8123456789:AAF...`)을 받아 둡니다.
2. 팀원들과 쓸 **그룹방을 새로 만들고**, 만든 봇을 그 방에 초대합니다.
3. BotFather에서 `/setprivacy` → 봇 선택 → **Disable**
   (안 하면 봇이 그룹 메시지를 못 읽어 chat_id 확인이 안 됩니다.)
4. 그룹방에 아무 메시지나 하나 보냅니다. (예: `안녕`)
5. 아래를 실행해 **chat_id**를 확인합니다. `-100...`으로 시작하는 숫자입니다.

```
python get_chat_id.py
```

## 2단계 · DART 인증키 발급 (3분)

1. https://opendart.fss.or.kr → 인증키 신청/관리 → **오픈API 이용동의 및 인증키 신청**
2. 이메일 인증하면 **40자리 인증키**가 발급됩니다. (무료, 하루 2만 건)

## 3단계 · 설정 파일 만들기

`.env.example`을 복사해 **`.env`** 로 이름을 바꾸고 값을 채웁니다.

```
TELEGRAM_BOT_TOKEN=8123456789:AAF...
TELEGRAM_CHAT_ID=-1001234567890
DART_API_KEY=여기에_40자리_인증키
```

> ⚠️ `.env`는 절대 공유하거나 GitHub에 올리지 마세요. `.gitignore`에 이미 등록돼 있습니다.

## 4단계 · 동작 확인

```
pip install -r requirements.txt
python main.py --check     # 세 수집원이 살아있는지 점검
python main.py --dry       # 텔레그램 발송 없이 화면에만 출력
python main.py             # 실제 실행 (첫 실행은 자동으로 '읽음' 처리)
```

첫 실행 때는 기존 항목을 전부 읽음 처리하고 **"봇 가동" 메시지 한 건만** 보냅니다.
과거 기사가 수백 건 쏟아지는 일은 없습니다.

---

## 5단계 · 24시간 자동 실행

### 방법 A. GitHub Actions — **추천** (무료, PC를 꺼도 동작)

컴퓨터를 켜 둘 필요가 없고 카드 등록도 필요 없습니다.

1. GitHub에서 **Private 저장소**를 만들고 이 폴더 전체를 올립니다.
2. 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
   에서 3개를 등록합니다: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DART_API_KEY`
3. **Actions** 탭 → "생보 3사 감시" → **Run workflow** 로 첫 실행.
4. 이후 10분마다 자동 실행됩니다. (`.github/workflows/watch.yml`의 cron으로 주기 변경)

> GitHub 무료 계정은 Private 저장소에 월 2,000분의 실행시간이 있습니다.
> 10분 주기·회당 1분이면 월 약 4,300분으로 초과합니다.
> **20분 주기(`*/20 * * * *`)로 두거나, 저장소를 Public으로 만들면 무제한 무료**입니다.
> (코드에 비밀값이 없고 Secrets는 노출되지 않으므로 Public도 안전합니다.)
> 참고로 GitHub 스케줄러는 혼잡 시 몇 분 지연될 수 있습니다.

### 방법 B. 내 PC 작업 스케줄러 (설정은 가장 간단, PC를 켜 둬야 함)

1. `Win + R` → `taskschd.msc` → **작업 만들기**
2. 트리거: 매일 / 반복 간격 **5분** / 기간 **무기한**
3. 동작: 프로그램 시작 → 이 폴더의 **`run.bat`** 지정
4. "사용자가 로그온했는지 여부에 관계없이 실행" 체크

실행 로그는 같은 폴더의 `bot.log`에 쌓입니다.

> 사내망 방화벽에서 `api.telegram.org`나 `news.google.com`이 막혀 있으면
> `python main.py --check`가 실패로 나옵니다. 그 경우 방법 A를 쓰세요.

---

## 설정 바꾸기 (`config.py`)

| 항목 | 설명 |
|---|---|
| `COMPANIES` | 감시 대상 회사. 손보사·지주사 추가 가능 (법인명·종목코드만 넣으면 됨) |
| `EXCLUDE_KEYWORDS` | 걸러낼 단어. 스포츠단 관련어가 기본으로 들어 있음 |
| `EXCLUDE_OVERRIDE` | 제외어가 있어도 살릴 경영 키워드 (실적·CSM·금감원 등) |
| `NEWS_LOOKBACK` | 뉴스 조회 기간 (`when:1d` / `when:2d` / `when:7d`) |
| `DART_PBLNTF_TY` | 공시 유형 제한. `"B"`로 두면 주요사항보고서만 |
| `INCLUDE_INDUSTRY_REPORTS` | 보험 산업 리포트 포함 여부 |

필터가 잘 듣는지 확인:

```
python -c "import filters; print(filters.explain('한화생명e스포츠 LCK 우승'))"
```

## 파일 구성

```
main.py             실행 진입점
config.py           감시 대상·필터 설정  ← 주로 여기만 고치면 됩니다
filters.py          스포츠단 등 노이즈 제외 로직
store.py            발송 이력(중복 방지)
notify.py           텔레그램 발송·메시지 서식
collectors/dart.py     공시 수집
collectors/reports.py  증권사 리포트 수집
collectors/news.py     뉴스 수집
get_chat_id.py      그룹 chat_id 확인 도우미
selftest.py         네트워크 없이 로직 점검
run.bat             윈도우 작업 스케줄러용
.github/workflows/  GitHub Actions 자동 실행 설정
```

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| chat_id가 안 나옴 | 봇을 그룹에 초대했는지, `/setprivacy` Disable 했는지 확인 후 그룹에 메시지 한 번 더 |
| 공시만 오고 리포트가 안 옴 | 네이버·한경 페이지 구조가 바뀌었을 수 있습니다. `python main.py --check` 결과를 알려주시면 파서를 고쳐 드립니다 |
| 알림이 너무 많음 | `config.py`의 `EXCLUDE_KEYWORDS`에 단어 추가, 또는 `DART_PBLNTF_TY = "B"` 로 주요 공시만 |
| 같은 기사가 두 번 옴 | 언론사가 다른 URL로 재송고한 경우. `state.json`은 제목 기준이 아니라 링크 기준이라 드물게 발생합니다 |
| 처음부터 다시 시작 | `state.json` 삭제 후 `python main.py --seed` |
