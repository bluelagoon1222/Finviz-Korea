# PROJECT NOTES — KOREA MAP 운영 기준

이 문서는 **운영자용 기준 문서**입니다. 장애가 생겼을 때 여기부터 봅니다.
README.md는 외부 소개용이고, 실제 동작의 기준은 이 문서입니다.

- 공개 주소: https://bluelagoon1222.github.io/Finviz-Korea/
- 저장소: https://github.com/bluelagoon1222/Finviz-Korea
- 최종 정리: 2026-09-10

---

## 1. 고정된 설계 결정 (바꾸지 않음)

| 항목 | 결정 |
|---|---|
| 색상 | **상승 초록 / 하락 빨강** |
| 셀 크기 기본값 | **√시총 가중** (`sizeMode: 0`) |
| 대상 종목 | KOSPI 200 · KOSDAQ 150 · ETF, 총 약 404종목 |
| 데이터 소스 | **yfinance** (`fetch_yahoo.py`) |
| 호스팅 | GitHub Pages, Actions 배포 방식 |

√시총 가중이 기본인 이유: 국내는 삼성전자·SK하이닉스가 시총의 큰 부분을 차지해
단순 시총 가중으로는 나머지 종목 이름이 읽히지 않습니다.

---

## 2. 데이터 흐름

```
GitHub Actions (예약 실행)
  ↓
fetch_yahoo.py --out site      ← yfinance로 시세 수집
  ↓
site/data.json + site/index.html 생성
  ↓
verify_data.py 로 이상치 검사    ← 실패하면 배포 중단
  ↓
GitHub Pages 배포              ← 매 실행마다
  ↓
data.json 저장소 커밋          ← 15:47 마감분과 수동 실행 때만
```

**중요:** 사이트에 보이는 데이터는 매 실행마다 갱신됩니다.
저장소의 `data.json` 커밋은 하루 1회뿐인데, 이건 **다음 날 폴백용 기준 데이터**를
남기기 위한 것입니다. 커밋이 하루 1건이라고 해서 사이트가 하루 1회만
갱신되는 것이 아닙니다. 이 둘을 혼동하기 쉽습니다.

---

## 3. 실행 스케줄

`.github/workflows/update-map.yml` 의 cron 값 (UTC 기준, KST = UTC + 9)

| cron | KST | 횟수 | 비고 |
|---|---|---|---|
| `7,37 0-6 * * 1-5` | 09:07 ~ 15:37, 30분 간격 | 14회 | 장중 갱신 |
| `47 6 * * 1-5` | 15:47 | 1회 | 마감 확정치, **이 실행만 커밋함** |

평일만 실행합니다. 주말·공휴일은 돌지 않습니다.

### :00 / :30 이 아니라 :07 / :37 인 이유

GitHub 예약 실행은 전 세계 사용자가 정각과 30분에 몰려 지연·누락이 잦습니다.
7분·37분은 이를 피하기 위한 의도적 선택입니다. **정각으로 되돌리지 마십시오.**

### 릴레이 방식을 쓰지 않는 이유 (2026-09-10 변경)

이전에는 실행이 끝나면 스스로 다음 실행을 예약하는 릴레이(`schedule-next` job) 방식이었습니다.
2026-09-10 오전, 체인을 시작하는 워치독 cron이 발동하지 않아 **장중 전체가 갱신되지 않는
사고**가 발생했습니다. 릴레이는 한 번 끊기면 사람이 버튼을 눌러야만 되살아납니다.

현재는 고정 cron이라 한 슬롯을 놓쳐도 30분 뒤 다음 슬롯이 정상 실행됩니다.
**릴레이 방식으로 되돌리지 마십시오.**

---

## 4. 파일 역할

### 현재 사용 중

| 파일 | 역할 |
|---|---|
| `.github/workflows/update-map.yml` | 자동 갱신·배포 설정. **모든 운영의 핵심** |
| `fetch_yahoo.py` | yfinance로 시세 수집, 페이지 생성 |
| `verify_data.py` | 배포 전 데이터 이상치 검사 |
| `korea_map_template.html` | 화면 템플릿. 색상·레이아웃은 여기 `<style>` 블록 |
| `data.json` | 폴백 기준 데이터 (수집 실패 시 이 파일로 사이트 유지) |
| `sectors.csv` | 종목코드 → 종목명 · 섹터 매핑 (350종목) |
| `etf_universe.csv` | ETF 유니버스 (54종목) |

### 남아 있으나 현재 쓰이지 않음

| 파일 | 상태 |
|---|---|
| `update_korea_map.py` | **미사용.** 구 pykrx 방식. `fetch_yahoo.py`로 대체됨 |
| `requirements.txt` | **미사용.** 워크플로가 yfinance·pandas를 직접 설치함 |
| `index.html`, `korea_map.html` | 저장소 사본은 오래된 것. 실제 배포본은 Actions가 생성 |

삭제해도 무방하지만, 지워서 얻는 이익이 없으므로 그대로 둡니다.
**단, 문제가 생겼을 때 `update_korea_map.py`를 고치지 마십시오. 실행되지 않는 파일입니다.**

---

## 5. 장애 대응표

### 증상 A — 사이트 갱신 시각이 오늘 것이 아니다

1. [Actions 실행 목록](https://github.com/bluelagoon1222/Finviz-Korea/actions/workflows/update-map.yml) 확인
2. **오늘 실행 기록이 아예 없다** → GitHub cron 미발동. `Run workflow` 수동 실행
3. **빨간 X가 있다** → 해당 실행 클릭 → 실패한 단계 펼쳐서 로그 확인 (아래 증상 C 참고)
4. **초록인데 화면이 안 바뀐다** → 브라우저 강력 새로고침 (`Ctrl + Shift + R`)

### 증상 B — 실행은 성공인데 데이터가 그대로다

`Fetch prices and build page` 단계가 실패하면 폴백이 작동해 **기존 `data.json`으로
사이트를 배포**합니다. 이때 실행 결과는 초록색 성공으로 표시됩니다.

확인 방법: 실행 화면에서 `Fallback - build page from data already in the repository`
단계가 **실행됐는지**(회색 사선이 아니라 초록 체크인지) 봅니다.
실행됐다면 시세 수집이 실패한 것입니다.

### 증상 C — 시세 수집 실패

로그에서 다음을 구분합니다.

- `Expecting value: line 1 column 1 (char 0)` → 데이터 소스가 빈 응답을 준 것.
  일시적일 수 있으니 수동 실행으로 재시도. 반복되면 소스 차단 의심.
- `IndexError: index -1 is out of bounds` → 위와 같은 원인의 후속 오류.
- `ModuleNotFoundError` → 패키지 설치 실패. `Install dependencies` 단계 로그 확인.

과거 사례: 2026-09-04, pykrx가 KRX에서 빈 응답을 받아 실패.
GitHub 서버가 해외 IP라 KRX가 차단한 것으로 판단. **yfinance로 소스 교체하여 해결.**

### 증상 D — 실행 목록이 하루 두 배로 늘었다

워크플로 파일을 업로드할 때 파일명이 `update-map (1).yml` 처럼 되어
**워크플로가 두 개 생긴 경우**입니다.
[.github/workflows 폴더](https://github.com/bluelagoon1222/Finviz-Korea/tree/main/.github/workflows)에서
파일이 `update-map.yml` 하나뿐인지 확인하고, 여분은 삭제합니다.

---

## 6. 바꿔도 되는 것 / 바꾸면 안 되는 것

### 바꿔도 되는 것

| 원하는 것 | 수정할 곳 |
|---|---|
| 섹터 분류 변경 | `sectors.csv` 의 섹터 열 |
| ETF 추가·삭제 | `etf_universe.csv` 에 행 추가·삭제 |
| 색상·글꼴·레이아웃 | `korea_map_template.html` 상단 `<style>` 블록 |
| 갱신 시각 | `update-map.yml` 의 cron. UTC 기준이므로 **KST − 9시간** |

### 바꾸면 안 되는 것

- cron 분(minute)을 `0` 또는 `30`으로 변경 → 지연·누락 급증
- `schedule-next` 릴레이 job 부활 → 2026-09-10 사고 재발
- `verify_data.py` 검증 단계 제거 → 이상 데이터가 그대로 배포됨
- `Save data.json` 단계의 커밋 조건을 매 실행으로 변경 → 하루 15건씩 커밋 누적

---

## 7. 운영 시 유의사항

- **데이터 지연** — 장중 시세는 실시간이 아닙니다. 지연 시세 기준이므로
  매매 타이밍 판단용이 아니라 **업종·수급 쏠림을 눈으로 훑는 용도**로 사용합니다.
- **09:07 실행분** — 개장 직후라 전일 종가에 가깝습니다.
  의미 있는 첫 데이터는 09:37 실행분부터로 보는 것이 안전합니다.
- **GitHub 무료 한도** — Public 저장소는 Actions 무제한. 비용 문제 없습니다.
- **60일 규칙** — GitHub은 60일간 저장소 활동이 없으면 예약 실행을 멈춥니다.
  이 워크플로는 매 영업일 `data.json` 을 커밋하므로 해당되지 않습니다.
- **파일 업로드 시** — 내려받은 파일명 뒤에 `(1)` 이 붙지 않았는지 반드시 확인합니다.

---

## 8. 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-09-04 | 최초 배포. pykrx 방식 첫 실행 실패 (KRX 차단) |
| 2026-09-09 | 데이터 소스를 yfinance(`fetch_yahoo.py`)로 교체. 릴레이 방식 도입 |
| 2026-09-10 | 릴레이 시동 실패로 장중 갱신 중단 사고 발생 |
| 2026-09-10 | **고정 cron으로 전환** (09:07~15:37 30분 간격 + 15:47). 릴레이 제거 |
| 2026-09-10 | `korea_map_template.html` 버튼 라벨 `시총가중` → `시총√가중` 수정 |
| 2026-09-10 | PROJECT_NOTES.md 신규 작성, README.md 현행화 |
