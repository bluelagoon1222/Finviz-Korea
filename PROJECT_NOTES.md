# PROJECT NOTES — KOREA MAP 운영 기준

운영자용 기준 문서입니다. 갱신이 멈추면 **5번 장애 대응표**부터 보십시오.
README.md는 외부 소개용이고, 실제 동작의 기준은 이 문서입니다.

- 공개 주소: https://bluelagoon1222.github.io/Finviz-Korea/
- 저장소: https://github.com/bluelagoon1222/Finviz-Korea
- 최종 개정: 2026-09-14 (외부 스케줄러 전환 반영)

---

## 1. 고정된 설계 결정 (바꾸지 않음)

| 항목 | 결정 |
|---|---|
| 색상 | **상승 초록 / 하락 빨강** |
| 셀 크기 기본값 | **√시총 가중** (`sizeMode: 0`) |
| 대상 종목 | KOSPI 200 · KOSDAQ 150 · ETF, 약 404종목 |
| 데이터 소스 | **yfinance** (`fetch_yahoo.py`) |
| 실행 트리거 | **cron-job.org 외부 호출** (GitHub 자체 cron 아님) |

√시총 가중이 기본인 이유: 국내는 삼성전자·SK하이닉스 비중이 커서
단순 시총 가중으로는 나머지 종목 이름이 읽히지 않습니다.

---

## 2. 전체 구조

```
cron-job.org (외부 스케줄러)          ← 시계 역할. 여기가 시작점
  │  POST + 토큰 인증
  ▼
GitHub API (workflow dispatch)
  │
  ▼
GitHub Actions: update-map.yml
  │
  ├─ fetch_yahoo.py --out site      ← yfinance로 시세 수집
  ├─ verify_data.py                 ← 이상치 검사, 실패 시 배포 중단
  ├─ GitHub Pages 배포              ← 매 실행마다
  └─ data.json 커밋                 ← commit=true 인 실행만
```

**중요:** 사이트 화면은 매 실행마다 갱신됩니다.
저장소의 `data.json` 커밋은 하루 1회뿐인데, 이건 **다음 날 폴백용 기준 데이터**를
남기기 위한 것입니다. 커밋이 하루 1건이라고 사이트가 하루 1회 갱신되는 게 아닙니다.

---

## 3. 실행 스케줄

### cron-job.org에 등록된 작업 2개

| 작업 이름 | Crontab | KST | commit | 용도 |
|---|---|---|---|---|
| `KOREA MAP intraday` | `7,37 9-15 * * 1-5` | 09:07~15:37, 30분 간격 14회 | `false` | 장중 갱신 |
| `KOREA MAP close` | `47 15 * * 1-5` | 15:47, 1회 | `true` | 마감 확정치 + 커밋 |

Time zone은 두 작업 모두 **Asia/Seoul**입니다. UTC 환산이 필요 없습니다.

### 호출 방식 (두 작업 공통)

```
POST https://api.github.com/repos/bluelagoon1222/Finviz-Korea/actions/workflows/update-map.yml/dispatches

Headers:
  Accept: application/vnd.github+json
  Authorization: Bearer <토큰>          ← Bearer 뒤 공백 한 칸 필수
  X-GitHub-Api-Version: 2022-11-28
  Content-Type: application/json

Body (intraday): {"ref":"main","inputs":{"commit":"false"}}
Body (close):    {"ref":"main","inputs":{"commit":"true"}}
```

성공 응답은 **204**입니다. 본문 없음이 정상입니다.

### commit 스위치의 의미

| 값 | 동작 |
|---|---|
| `false` | 데이터 수집 → 사이트 배포. **커밋 안 함** |
| `true` | 데이터 수집 → 사이트 배포 → **`data.json` 커밋** |

장중 14회를 모두 커밋하면 저장소 이력이 하루 15건씩 쌓이므로 분리했습니다.
GitHub 웹에서 `Run workflow`로 수동 실행하면 기본값이 `true`입니다.

### GitHub 자체 cron은 비상용 1줄만 남김

`update-map.yml`에 `47 6 * * 1-5`(15:47 KST) 하나만 남아 있습니다.
cron-job.org가 죽었을 때 최소 하루 1회는 돌게 하려는 보험입니다.
**시각은 믿을 수 없습니다.** 아래 4번 참고.

---

## 4. 왜 GitHub cron을 쓰지 않는가 (2026-09-14 전환)

GitHub 무료 예약 실행은 부하에 따라 지연·누락됩니다. 이 저장소의 실측입니다.

| 예약 시각 | 실제 실행 | 지연 |
|---|---|---|
| 15:47 (2026-09-11) | 20:51 | **5시간 4분** |

낮 슬롯이 통째로 밀렸다가 저녁 8시대에 몰려서 처리됐습니다.
cron 문법 문제가 아니었습니다. 실행 Summary에 `Trigger: schedule 47 6 * * 1-5`,
`Run time: 20:51 KST`가 함께 찍혀 확정된 사실입니다.

**따라서 GitHub cron만으로는 장중 30분 정시 갱신이 구조적으로 불가능합니다.**
cron 표기를 어떻게 바꿔도 해결되지 않습니다. 되돌리지 마십시오.

이전에 쓰던 릴레이(`schedule-next`) 방식도 마찬가지로 폐기했습니다.
한 번 끊기면 사람이 눌러야만 되살아나는 구조라 2026-09-10에 장중 전체가 비었습니다.

---

## 5. 장애 대응표

### 증상 A — 사이트 갱신 시각이 오늘 것이 아니다

**1) 브라우저 캐시부터 배제** — `Ctrl + Shift + R` 강력 새로고침

**2) [GitHub 실행 목록](https://github.com/bluelagoon1222/Finviz-Korea/actions/workflows/update-map.yml) 확인**

| 상태 | 원인 | 조치 |
|---|---|---|
| 오늘 실행이 아예 없음 | 외부 호출 실패 | 아래 3)으로 |
| 빨간 X 있음 | 수집·배포 실패 | 증상 C로 |
| 초록인데 화면이 그대로 | 폴백 배포 | 증상 B로 |

**3) cron-job.org 확인** — 로그인 → Cronjobs 목록

- 작업이 **Enable** 상태인지
- **Next executions**에 다음 실행 시각이 잡혀 있는지
- 실행 이력의 응답 코드가 204인지 (아래 표 참고)

### 증상 B — 실행은 초록인데 데이터가 그대로다

`Fetch prices and build page` 단계가 실패하면 폴백이 작동해 **기존 `data.json`으로
사이트를 배포**합니다. 이때도 실행 결과는 **초록색 성공**으로 표시됩니다.

확인법: 실행 화면에서 `Fallback - build page from data already in the repository`
단계가 **회색 사선이 아니라 초록 체크**인지 봅니다. 실행됐다면 시세 수집이 실패한 것입니다.

### 증상 C — 시세 수집 실패

`Fetch prices and build page` 로그에서 구분합니다.

- `Expecting value: line 1 column 1 (char 0)` → 데이터 소스가 빈 응답. 일시적일 수 있으니 수동 재실행
- `IndexError: index -1 is out of bounds` → 위와 같은 원인의 후속 오류
- `ModuleNotFoundError` → 패키지 설치 실패. `Install dependencies` 로그 확인

### 증상 D — cron-job.org 응답 코드가 204가 아니다

| 코드 | 원인 | 조치 |
|---|---|---|
| **401** | 토큰 오류 또는 **만료** | 새 토큰 발급 후 두 작업 모두 교체 (6번) |
| **403** | 토큰 권한 부족 | Actions를 Read and write로 |
| **404** | Request method가 GET / URL 오타 / 토큰 권한 부족 | POST인지 먼저 확인 |
| **422** | Request body 오타 | 중괄호·따옴표 확인 |

**404가 "주소가 틀렸다"를 뜻하지 않습니다.** GitHub은 권한이 없을 때도
저장소 존재를 숨기려고 404를 반환합니다.

### 증상 E — 아무 오류 없이 조용히 멈췄다

**토큰 만료를 가장 먼저 의심하십시오.** 실패 알림이 오지 않고, GitHub 실행 목록도
그냥 비어 있어서 알아차리기 가장 어려운 고장입니다.
cron-job.org 실행 이력에서 401이 찍혀 있으면 확정입니다.

---

## 6. 토큰 관리

| 항목 | 내용 |
|---|---|
| 종류 | Fine-grained personal access token |
| 이름 | `KOREA MAP schedular 2` |
| 권한 | `Finviz-Korea` 저장소, Actions: **Read and write** |
| 만료일 | **2026-12-13** |
| 보관 위치 | cron-job.org 두 작업의 Authorization 헤더 |

### 갱신 절차 (만료 시)

> **2026-12-13 이전에 갱신해야 합니다.**
> 만료되면 자동 갱신이 아무 알림 없이 멈춥니다. 12월 초에 미리 처리하십시오.

1. [새 토큰 발급](https://github.com/settings/personal-access-tokens/new) — 권한은 위와 동일하게
2. cron-job.org → `KOREA MAP intraday` → ADVANCED → Authorization 값 교체
3. `KOREA MAP close`도 동일하게 교체
4. 각 작업에서 **TEST RUN** → 204 확인
5. [옛 토큰 삭제](https://github.com/settings/tokens?type=beta)

토큰 값은 발급 화면에서 한 번만 보입니다. 놓치면 재발급해야 합니다.
**이 문서나 저장소에 토큰 값을 적지 마십시오.** 공개 저장소입니다.

---

## 7. 파일 역할

### 사용 중

| 파일 | 역할 |
|---|---|
| `.github/workflows/update-map.yml` | 수집·배포 설정. `commit` 입력 스위치 포함 |
| `fetch_yahoo.py` | yfinance 시세 수집, 페이지 생성 |
| `verify_data.py` | 배포 전 이상치 검사 |
| `korea_map_template.html` | 화면 템플릿. 색상·레이아웃은 상단 `<style>` |
| `data.json` | 폴백 기준 데이터 |
| `sectors.csv` | 종목코드 → 종목명·섹터 (350종목) |
| `etf_universe.csv` | ETF 유니버스 (54종목) |

### 미사용 (고치지 마십시오)

| 파일 | 상태 |
|---|---|
| `update_korea_map.py` | **미사용.** 구 pykrx 방식. `fetch_yahoo.py`로 대체됨 |
| `requirements.txt` | **미사용.** 워크플로가 yfinance·pandas를 직접 설치 |
| `index.html`, `korea_map.html` | 저장소 사본은 오래된 것. 배포본은 Actions가 생성 |

---

## 8. 바꿔도 되는 것 / 바꾸면 안 되는 것

### 바꿔도 되는 것

| 원하는 것 | 수정할 곳 |
|---|---|
| 섹터 분류 | `sectors.csv` 섹터 열 |
| ETF 추가·삭제 | `etf_universe.csv` 행 추가·삭제 |
| 색상·글꼴·레이아웃 | `korea_map_template.html` 상단 `<style>` |
| 갱신 시각 | **cron-job.org의 Schedule.** 워크플로 cron이 아닙니다 |

### 바꾸면 안 되는 것

- GitHub cron으로 장중 갱신을 되돌리는 것 → 최대 5시간 지연 (4번 참고)
- `schedule-next` 릴레이 job 부활 → 2026-09-10 사고 재발
- 장중 작업의 body를 `commit:"true"`로 변경 → 하루 15건 커밋 누적
- `verify_data.py` 검증 단계 제거 → 이상 데이터가 그대로 배포
- 토큰 값을 저장소나 문서에 기재

---

## 9. 운영 시 유의사항

- **데이터 지연** — 장중은 실시간이 아닌 지연 시세입니다. 매매 타이밍 판단용이 아니라
  **업종·수급 쏠림을 훑는 용도**로 사용하십시오.
- **09:07 실행분** — 개장 직후라 전일 종가에 가깝습니다. 의미 있는 첫 데이터는 09:37부터.
- **실행 기록 표시** — cron-job.org 호출은 GitHub에 `Manually run by bluelagoon1222`로
  표시됩니다. 토큰 소유자 기준이라 정상입니다.
- **GitHub 무료 한도** — Public 저장소는 Actions 무제한.
- **60일 규칙** — 60일간 저장소 활동이 없으면 GitHub이 예약 실행을 멈춥니다.
  매 영업일 `data.json`을 커밋하므로 해당되지 않습니다.
- **파일 업로드 시** — 내려받은 파일명 뒤 `(1)` 확인. 붙어 있으면 반드시 제거.

---

## 10. 변경 이력

| 날짜 | 내용 |
|---|---|
| 2026-09-04 | 최초 배포. pykrx 첫 실행 실패 (KRX 차단) |
| 2026-09-09 | 데이터 소스 yfinance 교체. 릴레이 방식 도입 |
| 2026-09-10 | 릴레이 시동 실패로 장중 갱신 중단. 고정 cron 전환 |
| 2026-09-10 | 버튼 라벨 `시총가중` → `시총√가중` |
| 2026-09-11 | 고정 cron도 최대 5시간 지연 확인 |
| 2026-09-14 | **cron-job.org 외부 스케줄러 전환.** `commit` 스위치 도입 |
