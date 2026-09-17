# 매트리스 KPI 시스템 — 설계 문서

FURSYS · iloom 매트리스 생산팀·품질보증팀 KPI 통합 콘솔.
**단일 HTML 파일 + React UMD + Firebase Firestore**로 동작하며 빌드 도구·서버 없이 정적 호스팅(GitHub Pages)으로 배포.

---

## 1. 시스템 개요

```
┌─────────────────────────────────────────────────────────────────────┐
│                          브라우저 (클라이언트)                       │
│                                                                      │
│  index.html ─┬─ React 18 UMD       ┬─ KPI Dashboard UI              │
│              ├─ Babel Standalone   │  (JSX in-browser 변환)         │
│              ├─ Tailwind CDN       │                                 │
│              ├─ Chart.js 4         │  (라인·도넛·막대·듀얼축)        │
│              └─ SheetJS 0.18.5     │  (CP949 → UTF-8 ERP 파싱)      │
│       │                                                              │
│       ▼                                                              │
│  ┌──────────────┐         ┌────────────────────┐                    │
│  │ localStorage │ ◀──────▶│ Firebase Firestore │ (onSnapshot 실시간)│
│  │   (오프라인)  │         │   kpidb_v2/main    │                    │
│  └──────────────┘         └────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

- **빌드 도구 없음** — 모든 라이브러리 CDN, `index.html` 하나만 배포
- **이중 캐시** — localStorage = 오프라인·즉시 응답, Firestore = 다중 PC 동기화
- **저장 단위** — `STORE_KEYS`의 각 키별로 `JSON.stringify` 후 Firestore 문서 merge

---

## 2. 디렉토리 구조

```
KPI Dashboard/
├─ index.html       — 전체 앱 (7,700+ 줄, 단일 파일)
├─ README.md        — 본 설계 문서
└─ .gitignore       — node_modules, grd_list_*.xls (실 ERP 데이터)
```

---

## 3. 라우팅 & 화면 트리

해시 라우팅 (`useHashRoute`). `#/<route>` 기준으로 페이지 컴포넌트 마운트.

```
홈  /                                       HomePage
├─ 대시보드           /dashboard            DashboardPage
│   ├ 기간 토글 (일별(기본) / 주별 / 월별 / 전체) — 일별 기본값 = 어제
│   ├ 생산 KPI 6장 Hero 카드 (전기간/전일 대비 변화 △/▼)
│   ├ 공정별 상세 grid (발포·퀼팅·스프링 행 단위)
│   └ 품질 KPI 3카드 (발생 건수 · 내부 손실 · 외주 손실 합계) + 유형 도넛 + 공정 막대
│
├─ 생산팀 입력        /production           ProductionPage
│   ├ 일간 입력      ProductionInputTab   — 일자별 KPI · progressThis는 같은 주 carry-forward
│   ├ 주간 기록      WeeklyJournalTab     — 담당자별 성장 로그 (주 단위 그대로)
│   ├ 종합 지표      ProductionSummaryTab — 일별/주별/월별/기간/전체 추세
│   ├ 봉탈 기록      BunghalAnalysisTab (mode=record)  — 작업일지 사진 인식·표 입력 + 이력
│   ├ 봉탈 분석      BunghalAnalysisTab (mode=analysis)— KPI·추세·도넛·Top·불량률
│   └ 작성 이력      ProductionHistoryTab + 휴지통(7일)
│
├─ 품질보증팀 입력    /quality              QualityPage
│   ├ 부적합 리포트   QualityReportTab     — ERP `.xls` 자동 파싱
│   ├ 종합 지표      QualitySummaryTab
│   ├ 외주협력업체    QualityVendorTab
│   └ 업로드 이력    UploadHistoryTab + 휴지통(7일)
│
├─ 생산팀 목표        /production/settings  ProductionSettings — 6 KPI × {target,warn,danger}
└─ 품질팀 목표        /quality/settings     QualitySettings    — 부적합 건수·내부 손실·외주 손실 6 항목
```

---

## 4. 데이터 모델

### 4-1. Firestore 스키마

**프로젝트**: `spring-6bcfc` / **컬렉션**: `kpidb_v2` / **문서**: `main` (운영) · `dev` (`file://` 로컬)

각 키는 JSON.stringify 후 문자열로 저장 (`merge: true`).

| key               | 형태                                                        | 설명                                |
|-------------------|------------------------------------------------------------|-------------------------------------|
| `production`      | `Entry[]`                                                  | 주간 생산 KPI 입력                  |
| `quality`         | `[]`                                                       | (구) 수기 입력 · 호환 보존 미사용  |
| `erpReports`      | `Report[]`                                                 | ERP 부적합 리포트 (일자별)         |
| `targets`         | `{[kpiKey]: {target, warn, danger}}`                       | 생산 6 KPI 임계                     |
| `qualityTargets`  | 6 항목 (아래 4-2 참조)                                       | 품질 임계 (건수 2 + 손실 금액 4)   |
| `productionTrash` | `Entry[]`                                                  | 생산 휴지통 (7일 자동 청소)        |
| `erpTrash`        | `Report[]`                                                 | ERP 휴지통                          |
| `weeklyJournal`   | `{[weekKey]: {[proc]: {[owner]: string}}}`                 | 주간 기록 (담당자별 자유 메모)     |
| `bunghalLog`      | `BunghalEntry[]`                                           | 작업일지 (생산+부적합) · date+owner unique key |
| `productCatalog`  | `{products, sizes, positions, aliases, causes, origins, actions, owners}` | 봉탈 기록 사전 (자동완성·Gemini 프롬프트) |
| `bunghalCorrections` | `[{field, wrong, correct, date}]` (최근 100건)         | Gemini 자가 학습 — 오인식 교정 누적 |
| `geminiApiKey`    | `string`                                                   | Gemini Vision API 키 (팀 공유 — 누구나 *사용* 가능) |
| `geminiPassHash`  | `string` (SHA-256 hex)                                     | API 키 관리용 비밀번호 해시 (팀 공유 — *조회·변경·삭제* 인증) |
| `priceMaster`     | `[]`                                                       | (구) 단가 마스터 · 호환 보존 미사용|

### 4-2. 주요 엔티티

**Production Entry** (일간 입력 — entry 1건 = 한 일)

```js
{
  id,
  date,                                // 입력 일자 YYYY-MM-DD (primary key)
  year, week, weekKey: 'YYYY-Www',     // date에서 파생, 호환·집계 가속용
  owner,                               // localStorage 'kpi_owner_prod' 기준
  tasks: {
    foam:     { task1, task2, task3 },
    quilting: { task1, task2, task3 },
    spring:   { task1, task2, task3 },
  },
  // tasks → tasksToFlatKpis() 로 평탄화된 6개 KPI
  spongeYield, foamInsourcing,
  quiltingDefect, interlockDefect,
  springDaily, springChangeover,
  createdAt, updatedAt,
}
```

**호환성**: 이전 주간 entries는 `date`(그 주 월요일)를 그대로 가지고 있어 일별 entry처럼 자동 노출됨. 데이터 마이그레이션 불필요.

**ERP Report** (품질 ERP 업로드 단위)

```js
{
  id, reportDate,                      // 발생일 (한 묶음 = 한 날짜)
  filename, source,                    // 'erp' | 'manual'
  records: [{ 원인공정, 품목, 유형, 부적합률, 발생수량, ... }],
  processIncidents,                    // 공정 이상발생 (인라인 편집)
  inputQty,                            // 투입 수량
  notes,
  createdAt, updatedAt,
}
```

**Quality Targets**

```js
{
  weeklyDefect:        { target, warn, danger },    // 주간 부적합 건수
  weeklyInternalLoss:  { target, warn, danger },    // 주간 내부 손실 금액 (원)
  weeklyVendorLoss:    { target, warn, danger },    // 주간 외주 손실 금액 (원)
  monthlyDefect:       { target, warn, danger },
  monthlyInternalLoss: { target, warn, danger },
  monthlyVendorLoss:   { target, warn, danger },
}
```

저장은 원 단위, 입력 UI는 **만 원 단위** (`isKRW` 플래그 시 `ThreshField`가 자동 ×10000 변환).

**Weekly Journal**

```js
{
  '2026-W21': {
    foam:     { '고영주': 'text…' },
    quilting: { '조상원': 'text…', '양승우': 'text…' },
    spring:   { '김민현': 'text…' },
  },
  ...
}
```

**Bunghal Entry** (작업일지 — date + owner unique key)

```js
{
  id, date, owner,
  productionRecords: [                 // 상단 표 — 생산
    { _id, product, size, position, qty, time }  // time: "8:40-10:25" 형식
  ],
  records: [                           // 하단 표 — 부적합
    { _id, product, size, position, qty, cause, originProc, action }
  ],
  createdAt, updatedAt,
}
```

**`parseTimeRangeMinutes(s)`** — `time` 필드("8:40-10:25" 등)를 분 단위 정수로 파싱. 등록된 작업일지 이력 표의 *작업시간* 컬럼 집계에 사용.

**Product Catalog** (봉탈 기록 사전)

```js
{
  products:  ['이브닝', '쿠시노', '데일리', '데일리라이트', '뉴문', '하프문', ...],
  sizes:     ['S', 'SS', 'D', 'Q', 'K', 'KK'],
  positions: ['최상단', '상', '하'],
  aliases:   { '라이트': '데일리라이트' },
  causes:    ['봉탈', '재작업 부족', '스펀지 접힘', ...],
  origins:   ['퀼팅', '인터', '업체', '수선'],
  actions:   ['수선', '폐기'],
  owners:    ['진아라', '옥사나'],
}
```

---

## 5. 핵심 데이터 흐름

### 5-1. 저장 흐름 (입력 → 영속화)

```
[사용자 입력]
     │
     ▼
컴포넌트 state (useState)
     │  (트리거: 명시적 저장 버튼 또는 onBlur)
     ▼
saveXxx(next)   ─ App 컴포넌트의 핸들러
     │
     ├──▶ setData(prev => {...prev, [key]: next})        — UI 즉시 반영
     │
     └──▶ LS.set(key, next)
              ├──▶ localStorage.setItem(...)              — 동기 (100%)
              └──▶ window.__fb.set(key, next)             — 비동기 (Firestore)
```

### 5-2. 동기화 흐름 (다른 PC 변경 → 본 PC 반영)

```
다른 PC가 Firestore 갱신
     │
     ▼
window.__fb.listen 콜백 (onSnapshot)
     │
     ▼
STORE_KEYS 순회 — JSON.parse 후
     ├─▶ localStorage 갱신
     └─▶ setData(prev => {...prev, ...out})              — UI 즉시 반영
```

### 5-3. 주간 기록 입력 보호 (창 닫기 대응)

```
JournalCell  ─  textarea 단위
     │
     ├─ 입력 중       → 로컬 draft state만 갱신 (Firestore 호출 X)
     │
     ├─ onBlur        → draft → onCommit → saveWeeklyJournal
     │
     └─ pagehide / visibilitychange='hidden'
                       → 강제 flush — 창 닫기·새로고침·탭 전환 직전
                          (localStorage 100% 보존, Firestore best-effort)
```

---

## 6. 비즈니스 도메인

### 6-1. 생산 KPI 매트릭스 (공정 × 과제 × 입력 필드)

| 공정 | 과제 1 | 과제 2 | 과제 3 |
|------|--------|--------|--------|
| **발포** (amber `#F59E0B`) | 스펀지 수율 (레코텍/엘라스틱/테롤) | 외주 폼 내작 진행률 | 현장 지원 능력 |
| **퀼팅** (violet `#8B5CF6`) | 봉탈률 (퀼팅 + 인터로크) | 치수 불량률 | 현장 지원 (퀼팅 + 인터로크) |
| **스프링** (emerald `#10B981`) | 일 평균 생산량 (1·2라인) | 품목 교체 시간 (1·2라인) | 현장 지원 능력 |

- 발포·스프링의 "현장 지원 능력" = `숙련도` (단일 % 입력)
- 퀼팅의 "현장 지원" = 퀼팅·인터로크 두 % 입력

`TASK_DEFS` → `tasksToFlatKpis()` → 6개 평탄 KPI:
`spongeYield`, `foamInsourcing`, `quiltingDefect`, `interlockDefect`, `springDaily`, `springChangeover`

`KPI_DEFS`가 각 KPI의 `{label, process, unit, target, warn, danger, higher}` 정의.

### 6-2. ERP 부적합 정규화

```
grd_list_YYYYMMDDHHMMSS.xls
     │  (SheetJS, codepage: 949 → UTF-8)
     ▼
헤더 자동 매핑 (원인공정 · 품목 · 부적합 유형 · 부적합률 · 발생수량 · 발생일 …)
     │
     ├─▶ 품목명에 "커버" 또는 "cover"(대소문자 무관) 미포함 → 제외
     │
     ├─▶ 부적합 유형 7종 정규화
     │     · 퀼팅 봉탈  · 작업자 부주의  · 구멍 및 찢어짐
     │     · 인터 봉탈  · 오염 및 얼룩   · 기타  · 이물
     │
     ├─▶ 원인공정 → 층 매핑
     │     · 커버 퀼팅 · 인터로크   → 4층
     │     · 외주협력업체            → 별도 그룹 (OUT)
     │     · 그 외                  → 2층
     │
     └─▶ 발생일별 grouping → 하루치마다 ERP Report 1건 생성
```

**`getDispositionType(r)` — 처리결정 필드 기반 폐기/수리 분류**

`decision` 필드(Excel '처리결정' 컬럼) 텍스트 기준으로 분류:
- `폐기 · 파기 · 스크랩 · 반품 · 반납` 포함 → `'폐기'`
- 그 외 → `'수리'`

외주협력업체 반품 건이 수리로 오집계되는 문제를 `반품|반납` 패턴 추가로 수정.

**재업로드 dedup 정책**: 같은 발생일의 기존 entry는 **파일명 무관하게 통째로 대체**. ERP 원본을 진실로 간주 — 인라인 편집한 `processIncidents`·`inputQty`·`notes`도 함께 사라짐.

### 6-3. 부적합 리포트 인라인 편집 정책

`ErpReportView`의 `공정 이상발생`·`투입 수량`·`비고` 셀:

- **단일 일자 보기** (`filtered.length === 1`) → 클릭하여 수정 가능, 즉시 Firestore 저장
- **합산 모드** (주별·월별·기간 — 여러 일자) → 저장 대상이 모호하므로 **readonly**
- **투입 수량 표시**: readonly 모드에서 `<input type="number">` → `toLocaleString('ko-KR')` 포맷 스팬으로 렌더링 (콤마 구분 표시). 편집 모드에서는 number input 유지.
- **손실비용 분리**: 폐기 비용 / 수리 비용 / 합계 3열로 분리. 각 셀 클릭 시 해당 조건으로 필터된 RAW 레코드 드릴다운 인라인 표시 (날짜·원인공정·품목명·수량·단가·처리구분·금액·부적합유형).

### 6-4. 생산 KPI 집계 규칙 (일별 → 주/월)

- **입력 단위**: 일별 entry (date 기준 unique)
- **평탄 KPI 산출 (`tasksToFlatKpis`)** — entry의 tasks에서 6개 평탄 KPI 계산. 화면 표시 시점에도 `refreshFlatKpis()`로 *항상 최신 공식 재계산* (Firestore 저장 옛 값 무시 — 공식 변경 시 자동 반영, 데이터 마이그레이션 불필요)

  | KPI | 산출 |
  |-----|------|
  | `spongeYield` (스펀지 수율) | 레코텍·엘라스틱·테롤 **평균** · 0 제외 (`safeAvgNonZero`) |
  | `foamInsourcing` (외주 폼 진행률) | 입력값 그대로 |
  | `quiltingDefect` / `interlockDefect` (봉탈률) | 입력값 그대로 |
  | `springDaily` (일 생산량) | 1라인 + 2라인 **합계** (`safeSum`) |
  | `springChangeover` (교체 시간) | 1라인·2라인 평균 |

- **일별 → 주/월 평균 (`avgKpiValues`)**: 일별 entries의 KPI 값을 주/월/기간 단위로 평균. `kpi.excludeZeroFromAvg=true`면 0도 제외 (현재 `spongeYield`만 적용)
- **0의 의미**:
  - 수율 (`spongeYield`) → 0은 *미측정/입력 실수* 가능성 → 평균 제외
  - 그 외 KPI (불량률·생산량·교체 시간) → 0이 *유효한 값* → 포함
- **추세 차트 → 매트릭스 표 (종합 지표 탭)**: KPI 추세 라인 차트 대신 **KPI × 시점 매트릭스 표**로 표시. 토글에 따라 X축이 일/주/월. 셀은 status 컬러 코딩 (달성/주의/경고)
- **Carry-forward 정책** (같은 주 한정 · 입력 단계):
  - **`progressThis` (금주 진행 예정)** — 현재 entry가 비어있으면 같은 주 다른 entry의 가장 최근 값에서 복사
  - **`task3` (현장 지원 능력)** — 입력값이 비어있으면 같은 주 다른 entry의 가장 최근 값에서 통째로 복사
  - **`task1`/`task2` 입력값** — carry-forward 안 함 (일별로 측정해야 의미 있음)
  - 그 일자 entry에 명시적으로 입력된 값은 *덮어쓰지 않음*
  - 주차가 바뀌면 자동으로 비어있는 상태로 시작
- **`progressThis` fallback (표시 단계 · 대시보드)**: 그 entry의 progressThis가 비어있으면 *모든 entry 중 가장 최근*의 progressThis로 자동 표시 (주차 경계 무시 — 데이터 안 건드림). 입력 단계 carry-forward 실패 시 안전망
- **운영 패턴 가정**: 오늘 KPI는 퇴근 후 다음날 아침에 입력 → 모든 화면의 일별 기본값 = **어제**

### 6-5. 품질 KPI 대시보드 카드 구성

3카드 — 외주 vs 내부 분리:

| 카드 | 값 산정 | 주별 목표 | 월별 목표 |
|------|---------|-----------|-----------|
| **발생 건수** | 전체 records 합 (외주 포함) | `weeklyDefect.target` | `monthlyDefect.target` |
| **내부 손실 비용** | `byFloor['2F'].amount + byFloor['4F'].amount` (외주 제외) | `weeklyInternalLoss.target` | `monthlyInternalLoss.target` |
| **외주 손실 금액 합계** | 모든 vendor amount 합 + **Top 3 vendor 리스트 표시** | `weeklyVendorLoss.target` | `monthlyVendorLoss.target` |

- 목표는 *주별·월별 토글일 때만* 노출 (전체 기간에선 비교 의미 없음)
- 외주 카드의 Top 3 리스트는 항상 표시 (hover 의존 X)

### 6-6. 봉탈 기록 · Gemini Vision 자동 인식

손글씨 작업일지(생산 + 부적합 두 표)를 Gemini Vision API로 JSON 추출 → 표 자동 채움.

```
[손글씨 작업일지 사진]
       │ Ctrl+V 또는 파일 선택
       ▼
gemini-2.5-flash (Vision)
       │  [이미지 전처리] compressImageDataUrl — 최대 1500px · JPEG 85% 압축
       │    휴대폰 사진 5~8MB → 200~400KB, 업로드·처리 시간 대폭 단축
       │  프롬프트: catalog 사전 + alias + 축약 규칙 + 시간 블록 규칙 + corrections 컨텍스트
       │  응답: { meta:{date,owner}, production:[...], defects:[...] }
       │  오류 시: HTTP 상태 코드별 한국어 안내 메시지
       │    400 → "API 키가 잘못됐거나 이미지 형식이 지원되지 않습니다."
       │    403 → "API 키 권한이 없습니다."
       │    429 → "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
       │    5xx → "Gemini 서버 오류 (상태코드). 잠시 후 다시 시도해주세요."
       │    JSON 파싱 실패 → "사진이 너무 흐리거나 글씨가 잘 안 보이면 다시 촬영해주세요."
       ▼
[검증 표]
   ├─ 상단: 생산량 표 (emerald)
   ├─ 하단: 부적합 표 (rose)
   ├─ 빈 필수 셀: 빨간 점선 강조
   └─ 헤더 자동 갱신 (사진의 일자·작업자가 헤더와 다르면 confirm)
       │  사용자가 검토·수정
       ▼
[저장]
   ├─ bunghalLog에 BunghalEntry 저장 (date+owner unique key)
   ├─ 자동 동기화 — production entry의 quiltingDefect/interlockDefect 자동 계산·갱신
   └─ 사용자 수정분 → bunghalCorrections 누적 (다음 인식 컨텍스트)
```

**등록된 작업일지 이력 표 컬럼 구성**

| 일자 | 요일 | 작업자 | 생산량 | 불량 수량 | 작업시간 | 최종 저장 | 동작 |
|------|------|--------|--------|-----------|----------|-----------|------|
| date | 요일 | owner | Σ productionRecords.qty | Σ records.qty | Σ parseTimeRangeMinutes(고유 time) 분 | updatedAt | 수정·삭제 |

- **작업시간 집계 중복 제거**: 같은 시간 범위를 공유하는 여러 행이 있을 때 중복 합산 방지. `[...new Set(time들)]`로 고유 time 문자열만 합산 (예: `13:00-15:20` 3행 → 140분 × 1).

- 이력 표 우상단 **"CSV 다운로드"** 버튼 — UTF-8 BOM 포함, Excel 한글 깨짐 없음
- 기간 필터 드롭다운(일/주/월/기간/전체)은 `bunghalLog` + `productionRecordsAll` 양쪽 날짜를 통합해 옵션 목록 생성

**프롬프트 핵심 규칙**

- 품목 사전 fuzzy match — catalog.products 중 가장 가까운 단어로 자동 교정
- Alias 자동 치환 (예: `"라이트"` → `"데일리라이트"`)
- 축약 규칙: `"`/`〃`/빈칸 = 위 행 그대로 / `"SS` = 위 행 품목명 + 새 사이즈
- 위치 기본값 — 명확히 안 적혀있으면 `"상"`
- 수선건 자동 분류 — 원인 텍스트에 "수선" 포함 시 originProc = `"수선"`
- **작업시간 블록 규칙**: 여러 행이 하나의 시간 블록을 공유하는 패턴 처리
  - `"HH:MM -"` (시작 시간만) → 새 블록 시작, 이후 시간 공백 행은 같은 블록
  - 블록 내 마지막/단독 `"HH:MM"` → 해당 블록의 종료시간
  - 같은 블록의 모든 행 `time = "시작-종료"` (예: `"13:00-17:05"`)
- 최근 30건 corrections를 *"이전 오인식 — 같은 오류 반복 금지"* 컨텍스트로 주입

**API 키 보안 (Gemini) — 팀 공유 모델**

- 모델: `gemini-2.5-flash` (`gemini-flash-latest` alias는 Google deprecated → 명시적 버전으로 변경)
- **저장**: API 키와 비밀번호 해시 둘 다 **Firestore 공유** (`geminiApiKey` / `geminiPassHash`)
- **권한 모델**:

| 액션 | 본인 (비밀번호 ✓) | 타인 (비밀번호 ✗) |
|------|----|----|
| 사진 인식 — 키 사용 | ✓ | **✓** (백그라운드 호출) |
| 키 조회 / 변경 / 삭제 | ✓ 비밀번호 입력 후 | **✗** 비밀번호 입력 화면에서 차단 |
| 비밀번호 재설정 | ✓ "초기화" 버튼 | **✗** |

- SHA-256 해시로 비밀번호 검증, 평문 비밀번호는 어디에도 저장 안 함
- 잠금 해제 상태는 *세션 한정* (PC별 메모리 — 탭 닫으면 다시 잠김)
- 기존 localStorage 저장값(`kpi_gemini_key` / `kpi_gemini_pass_hash`)은 첫 진입 시 Firestore로 자동 마이그레이션

**보안 한계 — 솔직히**

- API 키는 Firestore에 *평문*. Firestore 콘솔 접근 권한 있는 사람은 *UI 우회해서 직접 조회 가능*
- 비밀번호 분실 시 *본인도 변경 불가* — Firestore 콘솔에서 `geminiPassHash` 필드 삭제 후 재설정
- 즉 Firestore 콘솔 접근 = **절대 권한**. 사내 도구·Firestore 규칙으로 외부 차단 전제

**자동 동기화 — 일간 KPI**

봉탈 기록 저장 시 그 일자의 production entry의 `quiltingDefect` · `interlockDefect` 자동 계산·갱신.

```
totalProduction    = Σ 그 일자의 모든 작업자 productionRecords.qty
quiltingDefectQty  = Σ originProc='퀼팅' records.qty
interlockDefectQty = Σ originProc='인터' records.qty

quiltingDefect  = quiltingDefectQty  / totalProduction × 100
interlockDefect = interlockDefectQty / totalProduction × 100
```

- `production` entry의 `tasks.quilting.task1`만 갱신 (다른 task는 손대지 않음)
- 일간 입력 탭 진입 시 자동 채워진 값 표시 — 사용자가 수기로 덮어쓰기 가능
- 봉탈 entry 삭제 시에도 재계산

### 6-7. 주차 표기

ISO 주차 → "YYYY M월 N주차" (`isoWeekToMonthLabel`).
주차의 월요일이 속한 달을 기준으로 N번째 월요일.

### 6-8. 주간 기록 노출 정책

- **시작 주차** — 2026-W21 (5월 3주차) 고정. 이전 주차는 목록 미표시.
- **미래 주차** — 오늘 기준 +4주까지 자동 생성. 시간이 흐르면 새 주차가 끝에 자동 추가.
- **담당자** — `JOURNAL_OWNERS = { foam:['고영주'], quilting:['조상원','양승우'], spring:['김민현'] }`
- **자동 저장** — 명시적 저장 버튼 없음. onBlur + pagehide + visibilitychange.

### 6-9. 휴지통·이력 보존 정책

- 삭제된 항목은 `*Trash`로 이동 → 7일 후 자동 영구 삭제 (1시간마다 `purge()`)
- **`deletedAt` 없는 레거시 항목 처리**: `deletedAt`이 없으면 타임스탬프를 `0`(1970-01-01 epoch)으로 처리 → 다음 purge 주기에 즉시 삭제. 과거 Date.now() 대입 방식은 7일 TTL을 재시작시켜 항목이 무한 누적되는 버그가 있었음.
- 토스트의 *되돌리기* 버튼 — 7초간 노출
- 작성·업로드 이력 표 — 최근 30건만 표시 (전체 건수는 헤더에 표기)

---

## 7. 컴포넌트 책임

```
App                       — 라우팅 · 전역 상태 · Firebase 구독 · 휴지통 purge
├─ HomePage               — 진입 화면 (3개 진입 버튼)
├─ TopBar                 — 페이지별 헤더 · 동기화 시각
├─ DashboardPage          — Hero KPI 카드 · 공정 상세 grid · 품질 3카드
│   └ QualitySummaryCard   — 일반 카드(값+trend+목표) + vendorList(외주 카드 전용)
├─ ProductionPage         — 생산팀 6탭 컨테이너
│   ├ ProductionInputTab    — 공정 × 과제 grid (TaskInputCard × 9) · 일자 selector · progressThis prefill
│   ├ WeeklyJournalTab      — 주차별 펼침 카드, 공정 × 담당자 grid
│   │   └ JournalCell       — onBlur·pagehide·visibilitychange 보호
│   ├ ProductionSummaryTab  — 일별/주별/월별/기간/전체 토글 (주차·월 selector 대시보드 패턴) + KpiMatrix
│   │   └ KpiMatrix          — KPI × 시점 표 (라인 차트 대신, status 컬러 셀)
│   ├ BunghalAnalysisTab    — 두 모드 (mode prop 분기)
│   │   ├ mode='record'      — 작업일지 사진 인식 + 두 표 입력 + 등록 이력 + 자가 학습
│   │   │   ├ BunghalKpiCard / BunghalTrendChart / BunghalDonutChart — 차트 컴포넌트
│   │   │   └ Gemini Vision 연동 — gemini-2.5-flash + 이미지 압축 + catalog 사전 주입
│   │   └ mode='analysis'    — KPI 5장 + 추세 라인 + 도넛 2개 + 원인/품목/불량률 Top
│   └ ProductionHistoryTab  — 일별 entry 목록 + 휴지통
├─ QualityPage            — 품질팀 4탭 컨테이너
│   ├ QualityReportTab      — ERP 업로드 + cross-tab + 단일 일자 인라인 편집
│   │   └ ErpReportView     — onUpdateField로 readonly/편집 분기
│   ├ QualitySummaryTab     — 기간 토글 + 추세·도넛
│   ├ QualityVendorTab      — 외주협력업체 손실 Top
│   └ UploadHistoryTab      — 업로드 묶음 + 휴지통
├─ ProductionSettings     — 6 KPI × {target, warn, danger}
├─ QualitySettings        — 6 항목 (좌 건수 2 / 우 손실 금액 4)
│   └ ThreshField          — isKRW 플래그 시 만 원 단위 자동 변환
├─ DateRangePicker        — 듀얼 캘린더 popover (모든 기간 선택 통합)
│   └ MonthGrid            — 일~토 단일 달 그리드 (일/토 컬러 강조)
├─ ConfirmProvider            — Promise 기반 커스텀 confirm 모달 (browser confirm() 대체)
│   └ useConfirm()             — `await dialog('메시지')` → true/false. ESC·배경 클릭 = false (취소)
└─ Icon · CountUp · ToastProvider · ChartCanvas — 공통 빌딩 블록
```

**TopBar 동기화 인디케이터**

- 앱 최초 로드 시 `syncing=true` → 상단에 파란 shimmer 로딩 바 표시 (`z-[99999]`)
- TopBar의 동기화 상태 점이 **노란색 맥박 애니메이션** + "동기화 중…" 텍스트로 전환
- Firestore `pullFB()` 완료 → `syncing=false` → 로딩 바 사라짐, 초록 점 + "동기화" 복귀

**BunghalAnalysisTab Top 카드 더보기**

- 원인·품목·작업자 Top 카드는 기본 5위 표시
- 데이터가 5건 초과 시 **"더보기 +N ▼"** 버튼 표시 → 클릭 시 최대 10위까지 확장
- 확장 상태에서 **"접기 ▲"** 버튼으로 다시 5위로 축소

**DateRangePicker 동작**
- 4군데 (ProductionSummary·QualityReport·QualitySummary·QualityVendor)에서 동일 컴포넌트 재사용
- `ReactDOM.createPortal`로 `document.body`에 직접 렌더링 → 부모의 `overflow`/`transform`에 잘리지 않음
- 트리거 클릭 → 단일 달 캘린더 popover → 셀 클릭 2회로 시작·종료일 지정 → 자동 닫힘
- 시작 선택 후 hover로 범위 프리뷰 표시 (옅은 accent 배경)
- 외부 클릭 / 닫기 버튼 / scroll·resize 시 위치 자동 재계산

---

## 8. 디자인 시스템

- **폰트**: Pretendard
- **베이스**: slate-50 + 화이트 카드 + slate-200 보더
- **공정 컬러**: 발포 `#F59E0B` / 퀼팅 `#8B5CF6` / 스프링 `#10B981`
- **품질 컬러**: rose `#F43F5E` / fuchsia `#A21CAF` / pink `#EC4899` (외주)
- **상태 컬러**: 달성 emerald / 주의 amber / 경고 rose
- **금액 표기 (출력)**: `fmtKRW` — `140만 원` / `2.5억 원` / `5,200 원`
- **금액 입력 (목표 설정)**: 만 원 단위 (UI ↔ 저장값 ×10000 자동 변환)
- **주차 표기**: `2026 5월 3주차`
- **숫자 정렬**: `font-variant-numeric: tabular-nums`
- **아이콘**: Lucide 스타일 inline SVG (`Icon` 컴포넌트)
- **애니메이션**: fade-up · count-up · slide-down · glass blur
- **줄바꿈 보존**: 진행 메모 표시 영역에 `whitespace-pre-line`
- **달력 요일 컬러**: 일요일 `text-rose-500` / 토요일 `text-blue-500` / 평일 `text-slate-700` — 헤더는 한 톤 흐리게 (-100)

---

## 9. 외부 의존성

모두 CDN — 오프라인 사용 불가, 첫 로드 후 브라우저 캐시.

| 라이브러리        | 버전     | 용도                  |
|------------------|---------|----------------------|
| React + ReactDOM | 18.2.0  | UI                   |
| Babel Standalone | 7.24.0  | JSX 변환             |
| Tailwind CDN     | latest  | 스타일링             |
| Chart.js         | 4.4.0   | 라인·도넛·막대       |
| SheetJS (xlsx)   | 0.18.5  | ERP `.xls` 파싱      |
| Firebase compat  | 9.23.0  | Firestore            |
| Pretendard       | 1.3.9   | 한글 폰트            |
| Gemini API       | 2.5-flash    | 손글씨 작업일지 OCR (팀 공유 키, Firestore 저장) |

---

## 10. Firebase 보안

```js
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /kpidb_v2/{docId} {
      allow read, write: if docId in ['main', 'dev'];
    }
  }
}
```

`main` (운영) · `dev` (`file://` 로컬) 두 문서만 허용. 사내 도구 가정 — 인증 없음.

---

## 11. 배포 (GitHub Pages)

```powershell
cd "C:\Users\FURSYS\Desktop\상원 진미\1. 생산\ERP 개선\KPI Dashboard"
git init
git add index.html .gitignore README.md
git commit -m "초기 배포"
git branch -M main
git remote add origin https://github.com/<USERNAME>/<REPO>.git
git push -u origin main
```

레포 → Settings → Pages → Source `main` / `/ (root)` → Save → `https://<USERNAME>.github.io/<REPO>/`

`.gitignore` 제외 대상:
- `node_modules/`, `package.json`, `package-lock.json` (xlsx 파싱 검증 시 임시 생성됐던 파일)
- `grd_list_*.xls`, `grd_list_*.xlsx` (실 ERP 부적합 데이터 — 저장소 노출 금지)

---

## 12. 확장 포인트

- **생산 KPI 추가** — `KPI_DEFS` 항목 + `TASK_DEFS` 필드 + `tasksToFlatKpis` 매핑 (3중 등록)
- **품질 목표 항목 추가** — `QUALITY_TARGET_DEFS` + `DEFAULT_QUALITY_TARGETS` 동시 등록 (UI는 `QualitySettings`가 unit으로 그룹 자동 분리: 건수/금액)
- **품질 KPI 카드 추가** — `DashboardPage`의 `QualitySummaryCard` 호출부에 카드 + `qualityTargets`에서 적절한 목표 키 매핑
- **품질 부적합 유형 추가** — ERP 정규화 함수의 유형 매핑 테이블 수정
- **새 페이지 추가** — `useHashRoute` 라우트 분기 + `PAGE_META` 등록
- **기간 선택 UI** — 새 화면이 시작·종료일이 필요하면 `DateRangePicker` 컴포넌트 재사용 (`{startDate, endDate, onChange, min, max}` props)
- **봉탈 사전 항목 추가** — `productCatalog`(products/sizes/positions/causes/origins/actions/owners)에 추가하면 즉시 자동완성·Gemini 프롬프트에 반영. 작업자 추가는 ✎ inline 편집기로 가능
- **새 Vision 인식 화면** — Gemini API 키는 `localStorage('kpi_gemini_key')` 공유. `buildBunghalPrompt` 패턴 재활용 가능 (사전 + 축약 규칙 + corrections)
- **저장 키 추가** — `STORE_KEYS` + App state·`pullFB`·`saveXxx` 핸들러 (3중 등록)
- **담당자 추가** — `JOURNAL_OWNERS`에 공정별 이름 추가
- **주간 기록 시작점 변경** — `JOURNAL_START_YEAR` / `JOURNAL_START_WEEK` 상수만 수정
