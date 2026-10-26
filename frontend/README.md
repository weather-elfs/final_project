# 저시정 상황판 프론트엔드

- 기술 구성: React + TypeScript + Vite
- 개발·Storybook 데이터: MSW 기반 백엔드 계약 모사
- 배포 시연 데이터: `demo` 빌드에서만 로그인·경보·이력을 프론트 샘플로 처리하고, 기상 API는 실제 백엔드 사용
- 도메인 판정: 안개는 시정으로 계산하고 대기질은 서버 NowCast AQI를 우선 표시한다. 해당 계약이 없는 기존 응답만 PM 기반 추정 AQI를 사용하며, 종합 판정·임무 가능 여부는 API 결과를 표시한다.

## 실행

```bash
pnpm install
pnpm dev
pnpm test
pnpm typecheck
pnpm build
pnpm storybook
pnpm build-storybook
```

### 로컬 백엔드 로그 확인 (PowerShell / UTF-8)

현재 로컬 백엔드는 백그라운드로 실행하며 접근 로그는 `stdout.log`, 수집·예측 완료와 시작·오류 로그는
`stderr.log`에 저장한다. 아래는 2026-10-26 실행 세션의 경로이며, 재실행할 때는
로그를 저장하도록 지정한 실제 폴더로 바꾼다. 로그가 깨지지 않도록 `-Encoding UTF8`을 명시한다.

```powershell
$backendLogDir = Join-Path $env:TEMP 'codex-backend-partial-final-f220e78b617449e99c4207a767a33d96'
Get-Content -LiteralPath (Join-Path $backendLogDir 'stdout.log') -Encoding UTF8 -Tail 50 -Wait
```

`-Wait`은 새 로그를 계속 표시하며 `Ctrl+C`로 조회만 종료한다. 백엔드 서버는 종료되지 않는다.
같은 창에서 로그 조회를 종료한 뒤 시작·오류 출력으로 전환하려면 다음 명령을 실행한다.

```powershell
Get-Content -LiteralPath (Join-Path $backendLogDir 'stderr.log') -Encoding UTF8 -Tail 50 -Wait
```

`[API 수집 완료]`, `[예측 완료]`와 해당 `/api/v1/stations/.../dashboard` 요청의 HTTP 상태를 함께 확인한다.
`/api/health`의 200 응답만으로 실제 수집·예측 성공을 판단하지 않는다. 이 경로는 로컬
임시 폴더이며 Docker 배포 환경의 로그 위치·조회 명령과는 다르다.

## API 기준

- [BE–FE 연동 API 명세서 v0.4 (2026-09-30)](https://docs.google.com/document/d/1zjBbNEa1c2HuNsfqGURhRHMnJt8upEdP/edit?rtpof=true&tab=t.0)

### 최신 관측 수집·예측 조회 (2026-10-26)

#### 실제 사용 모델과 실행 경로

현재 5174에서 사용하는 서버는 **`feature/backend` 브랜치의 `backend.main:app`**이다.
실행 경로는 다음과 같다.

```text
프론트 127.0.0.1:5174 /api/*
  → Vite 프록시 → 127.0.0.1:8000
  → backend/main.py:station_dashboard
  → backend/model_predict.py:predict_visibility_pm
  → backend/models/forecast_tuned/ 안의 완성 모델 3개
```

| 모델 파일 (`backend/models/forecast_tuned/` 기준) | 출력 |
| --- | --- |
| `cb_tuned_visibility_km.cbm` | 시정(km) |
| `cb_tuned_pm25.cbm` | PM2.5(µg/m³) |
| `cb_tuned_pm10.cbm` | PM10(µg/m³) |

세 모델은 전달받은 `최종모델.zip`에서 원본 그대로 추출했으며, 2026-10-26에 ZIP과
바이트 동일성을 확인했다. 추가 학습·튜닝은 수행하지 않았다. `forecast_tuned/metadata.json`은
입력 피처 순서·원본 해시·예측 시간별 출력 복원 계수를 기록한다. 모델 출력은
`expm1(log1p(현재 관측값) + 모델 출력 × sigma[h])`로 원 단위로 복원한다.

`backend/models/catboost_48h_multioutput.cbm`은 기존 모델이며 이 실행 경로에서는 로드하지 않는다.
**프론트 작업 폴더에도 구버전 `backend/`가 남아 있으므로, 백엔드는 아래 별도 작업 폴더에서 실행한다.**

| 현재 로컬 역할 | 브랜치 | 작업 폴더 |
| --- | --- | --- |
| 프론트 소스·Vite | `feature/frontend` | `C:\Users\INA\Documents\workspace\final-project\frontend` |
| 실제 API 서버 소스 | `feature/backend` | `C:\Users\INA\Documents\workspace\final-project\_workspace\backend-live-request` |

기존 API 키가 프로세스 환경변수에 주입된 PowerShell에서 실행한다. DB 환경변수는 일반 실시간 조회에 필요하지 않다.

```powershell
Set-Location 'C:\Users\INA\Documents\workspace\final-project\_workspace\backend-live-request'
$env:PYTHONIOENCODING = 'utf-8'
& 'C:\Users\INA\Documents\workspace\final-project\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

이 절대 경로는 현재 로컬 작업 배치다. 다른 PC·Docker에서는 `feature/backend`를 체크아웃한
저장소 루트에서 같은 `backend.main:app`을 실행하고 `models/forecast_tuned/`와 메타데이터를 함께 포함한다.
실제 응답의 `data.meta.model.name = catboost_observation_forecast_tuned`로 모델 종류를 확인한다.

브랜치 동기화 확인일: 2026-10-26. `feature/frontend`에는 백엔드 PR #6이 병합된
`develop`의 `0da333f`를 반영했다. 이 기준의 백엔드 소스와, 이후 수정한 실시간 수집
백엔드는 구분한다. **실시간 관측·예보 수집과 튜닝 모델을 사용하는 백엔드 브랜치는
`feature/backend`**이며, `489c470`(수집·적재·모델 연동), `a189222`(NowCast AQI 보정)를 포함한다.
프론트는 `pnpm dev:backend --port 5174`로 실행하고, 실시간 기능 검증 시에는
`feature/backend` 소스에서 실행한 8000 포트 서버에 연결한다. 브랜치 이름을 바꿔도
실행 중인 서버의 소스 폴더·프로세스가 자동으로 전환되는 것은 아니다.

실제 백엔드 모드의 일반 대시보드 조회는 ASOS·AirKorea·국립해양조사원 관측과
기상청 단기예보·AirKorea PM2.5 예보를 수집하고, 요청별 메모리 자료로 관측+예보 튜닝형 예측을 수행한다.
일반 실시간 조회와 대시보드 설정 조회는 DB 연결·적재 및 `DB_*` 환경변수를 요구하지 않는다.
ASOS 최근 25개 시간대와 AirKorea 실측 시계열을 사용하며 결측 시간을 임의 보간하지 않는다.
대기질 예보는 `ArpltnInforInqireSvc/getMinuDustFrcstDspth`의 인천 PM2.5 예보 등급을 사용한다.
조회 전 관측소 상태는 `UNKNOWN`이며, 선택한 관측소의 지도 상태는 실제 대시보드 응답으로 갱신한다.
이 요청만 최대 60초를 기다린다. 일부 API가 실패해도 받은 관측과 가능한 예측을 표시한다.
전체 요청의 통신 오류가 발생하면 같은 관측소·예측 간격의 기존 결과를 시각 정보와 함께 유지한다.
조회 조건이 다른 결과를 새 조건의 데이터로 표시하지 않는다. 다른 API의 제한 시간은 변경하지 않는다.

`current.observed_at`은 ASOS 관측 시각, `source_status[].observed_at`은 출처별 관측 시각이다.
예보 출처는 관측 시각 대신 `issued_at`(발표)·`collected_at`(수집)을 따로 표시한다.
`meta.model.origin_at`은 예측 기준 시각이며, ASOS 누락 시에도 현재 관측 시각으로 대신 표시하지 않는다.
`meta.collection.requested_at` / `collected_at`은 수집 요청·수집 완료 시각이며,
`meta.collection.model_input_observed_at`으로 실제 모델 입력의 출처별 시각을 확인할 수 있다.
최신 자료는 기관이 공개한 가장 최근 관측을 뜻하며, 요청한 초의 관측을 의미하지 않는다.
`meta.collection.storage = memory`, `collected_rows`로 메모리 처리와 출처별 수집 건수를 확인한다.
자료는 영구 저장하지 않고, 출처별 재시도를 위해 한 프로세스의 메모리에 최대 10분·64개 조회를 보관한다.
`as_of` 과거 조회와 인천 `mock=true`는 기존 DB 경로이므로
DB 없는 실행에서는 파라미터를 생략하고 실제 API 기본값(`mock=false`)을 사용한다.
외부 API 장애·미발표 예보는 해당 출처와 시점에 누락으로 표시한다.

### 부분 성공과 출처별 재시도

통신 오류 안내는 지도 위에 겹치지 않고 대시보드 상단에 표시하며 닫기·재시도를 제공한다.
긴 오류 메시지와 요청 ID는 접힌 상세 영역에서 확인한다. 기존 자료가 있는 갱신 실패 안내는
8초 뒤 자동으로 닫히고, 상세 내용을 펼쳐 읽는 동안에는 자동 닫기를 멈춘다.
최초 조회 실패 안내와 출처별 부분 누락 상태는 자동으로 숨기지 않는다.

- 응답은 `PARTIAL_SUCCESS`로 사용 가능한 관측과 4개 예측 시점을 유지한다.
- 예측 입력이 부족하면 모델이 지원하는 결측값으로 계산하며, 시점별 `status`, `missing_sources`,
  `missing_features`, `unavailable_targets`로 누락 상태를 표시한다. 없는 값을 0이나 다른 시점의 예보로 채우지 않는다.
- 현재 시정·PM 기준값이 없는 항목이나 모델 오류가 발생한 항목은 예측값을 `null`로 반환한다.
  일부 입력이 누락되거나 시점별 예측이 불완전하면 임무 판정은 대기한다. 결측 상태의 정확도는 별도 평가가 필요하다.
- `meta.collection.id`와 원래 조회 조건을 유지하고 `retry_source`로 실패한 출처만 다시 요청한다.
  성공한 출처의 `fetched_at`과 관측값은 유지하며, 재시도 중에도 표를 숨기지 않는다.
- 재시도 대상은 `ASOS`, `AIRKOREA`, `TIDE_OBSERVATORY`, `KMA_FORECAST`, `AIRKOREA_FORECAST`다.
  응답의 `errors`·`retryable_sources`를 기준으로 버튼을 표시한다.
- 보관 만료·서버 재시작·다른 워커로 요청되어 조회 ID가 없으면 409를 반환한다. 이때 현재 관측 갱신으로 전체 조회를 실행한다.
  여러 워커·컨테이너를 사용하면 같은 프로세스로 재시도 요청이 가도록 라우팅해야 한다.

`meta.model.name = catboost_observation_forecast_tuned`는 전달된 최종 ZIP의 튜닝형을 뜻한다.
`meta.forecasts[]`에는 각 예측 대상시각의 실제 예보 입력값, `kma_issued_at`,
`airkorea_issued_at`이 포함된다. 예보는 관측 기준시각에 공개된 자료만 사용한다.
`meta.model.missing_features`의 입력은 결측 그대로 처리되며, 예보 누락·매칭 실패를
프론트 목 데이터나 과거 예측값으로 대체하지 않는다. 화면에는 기존 `forecast_timeline` 계약을 그대로 사용한다.

## Docker 배포용 시연 모드

`pnpm build`는 `vite build --mode demo`로 빌드한다. 생성된 `dist/`를 백엔드 또는
웹 서버에서 제공하고, 같은 출처의 `/api/*`는 실제 백엔드에 연결한다.
Vite 개발 프록시는 배포 파일에 포함되지 않는다.

| 기능 | 시연 빌드 동작 |
| --- | --- |
| 로그인 | 센터 ID `33182`, 공개 시연 코드 `100005`가 모두 맞으면 화면 진입. 서버 요청 없음 |
| 대시보드 설정·현재 관측·예측 | 기존 실제 백엔드 API 사용 |
| 예측 레이어 안개 음영 | 기존 GK2A 격자로 이동 시연. 실제 안개 예측 아님 |
| 경보 운영 | 프론트의 합성 샘플 표시. 실제 발령·해제·저장 없음 |
| 이력 조회 | 합성 샘플 표시와 유형·임무 필터 적용. 실제 조회 결과 저장·이력 API 호출 없음 |

로그인은 **실제 인증·인가 기능이 아닌 공개 시연용 화면**이다. 코드와 샘플 데이터는
브라우저 번들에서 확인할 수 있으며, 이 진입 화면으로 백엔드 API를 보호할 수 없다.
민감 데이터나 실제 운영 기능의 접근 제어로 사용하지 않는다. 비밀번호를 서버로 보내거나
저장하지 않고, 기존 ID 저장 옵션만 유지한다. 새로고침하면 시연 로그인 화면으로 돌아간다.

로그인 화면과 경보·이력 페이지에는 시연용임을 표시한다. 샘플은
`src/mocks/operationsFixtures.ts`, 시연 분기는 `src/demo.ts`와 `src/api.ts`에서 관리한다.
전체 MSW를 운영에서 켜지 않으며 `mockServiceWorker.js`는 시연 빌드 산출물에서 제외한다.
실제 인증·경보·이력 API로 전환할 때는 시연 모드와 연결 정책을 함께 변경해야 한다.

### 예측 레이어 안개 이동 시연

`예측 레이어`에서는 API의 `forecast_timeline` 시점을 그대로 사용하면서 안개 음영만
기존 이동 시연으로 재생한다. API에 `fog_layer`가 없으면 번들에 포함된 과거 GK2A
격자(`src/mocks/gk2aFogLayer.ts`)를 예측 지도 전용 바탕으로 사용한다. 현재 관측 모드에는
이 대체 격자를 넣지 않으며, 관측·예측 수치와 API 응답도 변경하지 않는다.

- 프레임 생성: `src/features/dashboard/forecastFog.ts`의 `buildForecastFogDemoFrames`
- 재생: 기존 900 ms 간격, 프레임 간 부드러운 보간, 마지막 시점 뒤 처음부터 재생
- 표시: 실제 안개 예측이 아닌 과거 격자 기반 시연임을 지도 아래에 명시
- 제어: 일시정지·재생·시점 선택 지원. 동작 줄이기 설정에서는 자동 재생하지 않음
- 예측 시점이 없으면 임의의 시점을 만들지 않음. 재생 중 매 프레임마다 API를 호출하지 않음

이 연결은 실제 API 개발 모드(`pnpm dev:backend`)와 배포 시연 빌드(`pnpm build`) 모두에서
동작하며, 기존 안개 모양·색상·투명도·보간 렌더링은 그대로 사용한다.

## PM 기반 추정 AQI 계산

현재 기상 카드의 **시정 영향 요인 → 대기질**은 최신 백엔드의
`current.aqi.basis = NOWCAST_CURRENT` 응답이 있으면 서버가 실제 12시간 관측으로 계산한
`value`를 사용하고, 등급·색상은 프론트의 기획안 `AIR_QUALITY_CRITERIA`로 결정한다.
서버의 `display_level`, `display_grade`로 기획안 등급을 덮어쓰지 않는다.
`status = calculated`, 유한한 0 이상 정수일 때만 사용하며 500 초과도 위험 5단계로 표시한다.
자료 부족·유효하지 않은 응답은 판단 대기로 표시한다. 이 경우 현재 PM 농도로
대체 계산하지 않는다. 화면과 기준 안내에도 서버 NowCast 사용을 구분한다.

아래 산식은 NowCast 계약이 없는 기존 응답·목 데이터에만 적용한다.
API의 `current.pm25_ug_m3`, `current.pm10_ug_m3`(단위: µg/m³)를 어댑터에서 변환한
`pm25UgM3`, `pm10UgM3`로 계산하며, `diagnosis.pm_display_grade`는 사용하지 않는다.

- 구현: [gradeTones.ts](src/features/dashboard/gradeTones.ts)의 `airQualityByParticles`
- 표시: [VisibilitySummary.tsx](src/features/dashboard/components/VisibilitySummary.tsx)
- 테스트: [gradeTones.test.ts](src/features/dashboard/gradeTones.test.ts), [VisibilitySummary.test.ts](src/features/dashboard/components/VisibilitySummary.test.ts)

### 계산 순서와 산식

1. PM2.5는 소수 첫째 자리까지, PM10은 정수까지 남기고 그 아래 자리는 버린다.
   예: PM2.5 `9.19 → 9.1`, PM10 `19.99 → 19`.
2. 아래 표에서 각 농도가 속한 구간을 찾고 선형 보간한다.
3. 각 입자 지수를 가장 가까운 정수로 반올림한다(`Math.round`).
4. 두 입자 지수 중 더 높은 값을 대기질 추정 지수로 표시한다. 더하거나 평균내지 않는다.

```text
입자별 지수 I = (I_high - I_low) / (C_high - C_low) × (C - C_low) + I_low
추정 AQI = max(round(I_PM2.5), round(I_PM10))
```

- `C`: 자릿수 버림을 적용한 입자 농도
- `C_low`, `C_high`: 해당 농도 구간의 하한·상한
- `I_low`, `I_high`: 해당 구간에 대응하는 AQI 하한·상한

### 입자별 농도 구간

EPA/AirNow의 농도 구간과 산식을 사용한다. **입력값의 평균 기간이 확인되지 않으므로
24시간 평균 또는 NowCast를 적용한 공식 AQI가 아닌 단일 관측값 기반 추정값**이다.

| AQI 구간 | PM2.5 농도(µg/m³) | PM10 농도(µg/m³) |
| --- | --- | --- |
| 0–50 | 0.0–9.0 | 0–54 |
| 51–100 | 9.1–35.4 | 55–154 |
| 101–150 | 35.5–55.4 | 155–254 |
| 151–200 | 55.5–125.4 | 255–354 |
| 201–300 | 125.5–225.4 | 355–424 |
| 301–500 | 225.5–325.4 | 425–604 |

표의 마지막 농도 상한을 넘으면 마지막 구간 산식으로 외삽한다. 계산된 지수를
500으로 제한하지 않으며, 300을 초과하는 값은 모두 프로젝트의 위험 5단계다.

### 프로젝트 표시 단계

EPA의 공식 AQI 범주를 그대로 표시하는 것이 아니라, 기존 UI 기준에 따라
AQI 0–50과 51–100을 **양호 1단계**로 묶은 5단계를 사용한다.
배지와 안내 팝업은 같은 `AIR_QUALITY_CRITERIA`를 공유한다.

| 추정 AQI | 표시 단계 | 표시명 | 색상 |
| --- | --- | --- | --- |
| 0–100 | 1/5단계 | 양호 | 초록 |
| 101–150 | 2/5단계 | 민감군 주의 | 주황 |
| 151–200 | 3/5단계 | 나쁨 | 빨강 |
| 201–300 | 4/5단계 | 매우 나쁨 | 보라 |
| 301 이상 | 5/5단계 | 위험 | 적갈색 |

### 계산 예시

인천 응답의 PM2.5 `3 µg/m³`, PM10 `19 µg/m³`인 경우:

```text
PM2.5 지수 = round((50 - 0) / (9.0 - 0.0) × (3.0 - 0.0) + 0) = 17
PM10 지수 = round((50 - 0) / (54 - 0) × (19 - 0) + 0) = 18
추정 AQI = max(17, 18) = 18
화면 표시 = 추정 AQI 18 · 양호 · 1/5단계
```

### 누락값과 한계

- 두 농도가 모두 유효해야 계산한다. 하나라도 `null`·`undefined`·음수·`NaN`·무한대이면
  `추정 AQI — · 판단 대기`, `—/5단계`와 회색 배지를 표시한다. `0`은 유효한 관측값이다.
- 입력 농도의 평균 기간, NowCast, 오존 등 다른 오염물질을 반영하지 않는다.
  따라서 공식 AQI·통합대기환경지수(CAI) 또는 건강·작전 판단의 대체 지표로 사용하지 않는다.
- 관측값이 오래됐어도 그 값으로 계산되며, 데이터 신선도는 출처별 데이터 상태에서 별도로 표시한다.
- 종합 추정 문구와 임무 판정은 이 계산으로 변경하지 않고 서버 응답을 유지한다.

기준 확인일: 2026-10-26.
[EPA/AirNow AQI 기술 문서(2026년 5월), Equation 1·Table 6](https://document.airnow.gov/technical-assistance-document-for-the-reporting-of-daily-air-quailty.pdf),
[EPA AQS 농도 구간표](https://aqs.epa.gov/aqsweb/documents/codetables/aqi_breakpoints.html).

## 시각 표시와 결측 보완 원칙

시각 표시 기준 확인일: 2026-10-26. 브라우저 현재 시계와 API 자료의 시각을 분리한다.

| 표시 정보 | 원본 | 동작·누락 처리 |
| --- | --- | --- |
| 현재 시각 | 브라우저의 `new Date()` | 매초 새로 읽어 KST로 표시. 상단·작전 환경·경보·이력 화면에 공유하며 API 조회 중·실패 중에도 진행 |
| 관측 시각 | `data.current.observed_at`, 출처별 `data.source_status[].observed_at` | 실제 관측 시각만 표시. 없으면 `--:--:--`이며 설정 응답 생성 시각으로 대체하지 않음 |
| 갱신 시각 | `data.meta.generated_at` | 서버가 응답을 생성한 시각. 브라우저 수신 시각이나 관측 시각으로 대체하지 않음 |
| 예측 기준 시각 | `data.current.observed_at` | 현재 백엔드가 모델 입력 기준으로 사용하는 ASOS 관측 시각. 없으면 `--:--:--` |

예측 대상 시각은 별도로 `data.forecast_timeline[].valid_at`을 표시한다. 브라우저 현재 시각에
예측 간격을 더해 다시 만들지 않으며, 예측 대상 시각이 없어도 설정 응답 시각으로 채우지 않는다.
브라우저 시계는 사용자 PC 시각이 부정확하면 영향을 받는다. 관측·갱신·예측 시각은
API가 준 값을 그대로 사용하며 현재 시계처럼 매초 증가시키지 않는다.

관련 구현: `DashboardView.tsx`의 `useCurrentTime`, `MissionConditionsForm.tsx`,
`VisibilitySummary.tsx`. 현재 시계 분리는 `e8211bf`, 시각 간 대체 표시 제거는 `d08f8fc`에 반영했다.

- 원본 관측은 덮어쓰지 않는다. 보완을 도입할 때는 방법·원본 시각·보완 여부를 별도로 전달한다.
- 변수별 허용 공백과 현재 모델 오차 비교가 검증되기 전까지 실제 관측의 자동 보간은 활성화하지 않는다.
- PM2.5 예보 등급을 평균·보간하거나 미발표 미래 예보를 관측으로 대체하지 않는다.
- 위 실제 데이터 원칙은 별도 표시된 시연용 합성 데이터·지도 애니메이션 보간과 구분한다.

## 구조와 재사용 경계

- `DashboardPage`: API 조회와 상태 관리
- `dashboardAdapter`: API `snake_case`의 UI `camelCase` 변환
- `types.ts`: 화면·컴포넌트 공용 TypeScript 계약
- `DashboardView`: 외부 데이터 의존성 없는 화면 조합
- `components/`: 좁은 props 기반 표시·입력 컴포넌트
- `stories/`: 합성 fixture 기반 상태 카탈로그
- `mocks/`: 개발·Storybook 전용 API 계약

## 재사용 범위

- 기본 묶음: `DashboardView`, `components/`, `dashboardAdapter`, `styles.css`
- npm 패키지 전환 시점: 두 번째 소비자 발생과 버전 정책 확정 이후

## 운영 전 보안 항목

- 인증·인가 계약 미확정
  - 현재: 개발용 `/api/v1/auth/login`은 MSW 계약이며, 배포 시연 모드는 공개 시연 ID·코드를 프론트에서 확인한다. 둘 다 운영 보안 수단이 아님
  - 운영 전: 서버 세션 확인·로그아웃·권한 검사 확정 및 `HttpOnly; Secure; SameSite` 쿠키 적용
- CSRF·CORS 미확정
  - 현재: 쿠키 인증 방식과 실제 API 호스트 미확정
  - 운영 전: CSRF 토큰과 CORS 허용 출처의 서버 공동 확정
- 배포 보안 헤더 미확정
  - 운영 전: `Content-Security-Policy`(`frame-ancestors` 포함), `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Cache-Control: no-store`, HTTPS/HSTS 적용
- 발표용 지도 예외
  - 현재: 민감 데이터가 없는 발표 시연에 OpenStreetMap 공개 타일 사용
  - 유의 사항: 외부 타일 서버로 브라우저 IP·요청 좌표·Referer 전달 가능
  - 운영 전: 민감 데이터·운영 환경 전환 전 승인된 내부 타일 서버로 교체
- MSW 운영 제외
  - 현재: MSW는 개발·Storybook 전용. `demo` 빌드는 worker 파일을 산출물에서 제거하고 경보·이력 합성 데이터만 직접 사용
  - 운영 전: 예전에 같은 출처에 등록한 개발용 worker가 없는지 확인. 배포 도메인에서 개발 서버를 제공하지 않음
- Storybook 공개 금지
  - 운영 관측값·좌표·계정 정보의 story/fixture 사용 금지
  - 게시 시 사내 인증 적용 및 외부 검색·공개 배포 금지
- 명세 확인 필요
  - 현재: 설정 응답 스키마의 관측소 상태 필드와 예시 응답 불일치
  - 계약 확정 전: UI의 `available` 필드만 사용

> 프런트엔드 로그인 화면과 상태값은 서버 인가 수단 아님.
