# WeatherElfs Backend — teammate handoff (updated 2026-10-26)

## Latest-data request flow (2026-10-26)

### 실행 서버와 모델 경로 (2026-10-26 확인)

5174 프론트의 `/api/*`는 8000 서버로 프록시한다. 실제 백엔드는 `feature/backend` 브랜치이며,
현재 로컬 실행 루트는 `C:\Users\INA\Documents\workspace\final-project\_workspace\backend-live-request`다.
`feature/frontend` 작업 폴더에 남은 `backend/`는 기존 버전이므로 실행 폴더를 구분해야 한다.

```text
backend.main:app → station_dashboard → predict_visibility_pm → load_forecast_model
  → backend/models/forecast_tuned/cb_tuned_visibility_km.cbm
  → backend/models/forecast_tuned/cb_tuned_pm25.cbm
  → backend/models/forecast_tuned/cb_tuned_pm10.cbm
```

세 파일은 각각 시정(km), PM2.5(µg/m³), PM10(µg/m³)을 예측한다.
`catboost_48h_multioutput.cbm`은 기존 모델이며 이 경로에서는 사용하지 않는다.
2026-10-26 develop `ea70b07`(#9)의 최신 `models/cb_tuned_*.cbm` 세 파일과 바이트 동일성을 확인했다.
`forecast_tuned`는 완성 모델의 배포 사본이며 추가 학습·튜닝은 하지 않았다.
입력은 89개다. `pm1`·`extinction_coef`를 제거하고 강수·습도·시정 추세 등 15개를 추가했다.
`metadata.json`은 입력 순서·모델 해시·제공 노트북 해시와 출력 계수 `sigma[h]`를 보관한다.
계수는 `관측소별_저시정개선학습.ipynb`의 재학습 구간(2022-04-01 이상, 대상시각 2025-04-01 미만)에서
다시 계산했다. 타깃별 유효 표본 합계 3,136,858개가 노트북 출력과 일치한다.
출력 복원식은 `expm1(log1p(현재값) + 모델 출력 × sigma[h])`다.

기존 API 키를 프로세스 환경변수로 주입한 PowerShell에서 실행한다.

```powershell
Set-Location 'C:\Users\INA\Documents\workspace\final-project\_workspace\backend-live-request'
$env:PYTHONIOENCODING = 'utf-8'
& 'C:\Users\INA\Documents\workspace\final-project\.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

다른 PC·Docker에서는 이 로컬 절대 경로 대신 `feature/backend` 체크아웃 루트에서 실행한다.
이미지에 `backend/models/forecast_tuned/` 전체를 포함해야 하며, 일반 실시간 조회는 DB 없이 동작한다.
응답의 `data.meta.model.name = catboost_observation_forecast_tuned`로 모델 종류를 확인한다.
최신 버전은 `meta.model.version = low_visibility_89_20261026`, `feature_count = 89`다.

현재 API는 최신 **Tuned 3개 모델**을 사용한다. 노트북의 최종 `Switch`는 Raw·Tuned·현재값을
리드별 NNLS 가중치로 혼합하고 시정 4km 미만에서 Tuned로 전환하는 별도 앙상블이다.
정밀한 48개 리드 전체의 가중치가 내보내지지 않아 Switch/Stacked는 적용하지 않았다.
노트북의 Switch 평가 성능을 이 API의 성능으로 표시하면 안 된다.

최신 모델 검증(2026-10-26): 회귀 테스트 51개, 설정 API 검사 4개 통과.
1~48시간 × 3개 타깃 총 144개 고정 입력 추론이 유효했고, 배포 모델 3개는 develop과 바이트 동일했다.
5174 실제 API에서 인천·6시간 간격의 4개 시점이 수집 오류 없이 표시됐다.
12시간 간격도 +12/+24/+36/+48시간 모두 시정·PM 예측을 표시했다. +36/+48시간의 AirKorea 예보는
누락되어 degraded와 누락 출처를 함께 표시했다. 파고·파주기, 수집 구간 내 강수가 없어 계산할 수 없는
마지막 강수 경과 시간은 결측으로 유지한다. 이 검사는 실행·연동 확인이며 예측 정확도 평가는 아니다.

AQI responsibility (verified 2026-10-26): the backend computes the PM2.5/PM10
NowCast from actual hourly observations, retaining missing hourly slots. Invalid
concentrations do not count toward the two-of-three completeness requirement.
AQI above 500 follows the last EPA interval's linear slope instead of being capped.
The frontend maps the returned numeric AQI to the product's existing five display
stages; backend display labels are retained for compatibility, not UI authority.
No observation interpolation or missing future forecast fabrication is enabled.

### Active model: observation + forecast tuned

The active artifacts are `backend/models/forecast_tuned/cb_tuned_{visibility_km,pm25,pm10}.cbm`
copied byte-for-byte from develop `ea70b07`. The old multi-output draft is retained but no longer loaded.
No fitting/retraining is performed. Runtime checks the version, three hashes and identical
89-column feature order. The exporter restores the refit (Train+Val) horizon standard deviations
following the supplied `관측소별_저시정개선학습.ipynb`, cells 12/15/17.
The original ZIP below supplies observation Parquet data only; its old model weights are ignored.
`weights-directory` must contain the three latest `cb_tuned_*.cbm` files. The exporter validates all
models and coefficients before replacing deployment copies; run it before starting the server.

```powershell
python -m backend.import_tuned_models "C:\path\to\최종모델.zip" "C:\path\to\weights-directory" "C:\path\to\관측소별_저시정개선학습.ipynb"
```

- Sources: approved data.go.kr `VilageFcstInfoService_2.0/getVilageFcst` (weather),
  AirKorea `ArpltnInforInqireSvc/getMinuDustFrcstDspth` (Incheon PM2.5 grade).
  Both use existing `DATA_API_KEY`; AirKorea may use `AIRKOREA_API_KEY` instead.
  If weather collection or validation fails, retry the same release and grid through
  KMA APIHub `VilageFcstInfoService_2.0/getVilageFcst`. APIHub uses
  the existing `KMA_API_KEY` (fallback: `KMA_AUTH_KEY`) and requires
  the corresponding API usage approval. Observation credentials are unchanged.
  The primary request has an 8-second pagination budget, and APIHub has 12 seconds,
  within the existing 25-second collection phase. Both routes use the same field,
  release-time, grid and value validation; no pages or releases are mixed.
  If both fail, `KMA_FORECAST` remains missing and partial predictions are preserved.
  Backend logs record `[기상청 예보 수신] 경로 DATA_GO_KR/KMA_APIHUB` without keys or URLs.
- Model PIT-grid mapping follows the provided collection pipeline: 102 → (21,136)/백령면,
  112 → (54,125)/동인천동, 201 → (51,130)/불은면. This is separate from the legacy weather-label helper.
- The ASOS window is 73 hourly points (origin minus 72 hours through origin). Temperature,
  dewpoint, wind and rain history plus exact-hour marine temperature joins supply new trend inputs.
  Rolling sums/minima use the notebook's min_periods=1; humidity >=90% is an hourly count, not a ratio.
  A missing rain field on a received ASOS row is interpreted as no rain, as in the notebook;
  entirely missing hours remain NaN. `hours_since_rain` is capped at 72 and stays NaN if no
  positive rain was observed in the available window. No observation values are forward-filled.
- Forecasts are matched at `origin + horizon`, using KMA releases publicly available at the
  observation origin (20-minute publication margin) and PM releases no later than that origin.
  Neighboring target hours or future releases are never substituted.
- Live requests match the collected forecast rows in memory. Historical DB reads use the same
  matching/conversion function. Live collection does not open a DB connection or write any tables.
- The tuned output is not a final concentration: `result = expm1(log1p(current) + residual × sigma[h])`.
  Clamp below at zero; visibility additionally uses the original train-target maximum from metadata.
- PM1 and extinction coefficient are excluded from the latest model. Wave height/period are
  unavailable and remain NaN as supported by CatBoost, never zero or stale observations.
  A missing current baseline disables only
  that target; the other models still run. Model errors are also isolated by target and horizon.
- `meta.model` identifies this model, its inverse transform and missing input features.
  `meta.model.origin_at` is the prediction origin even if ASOS is unavailable; it is not
  fabricated as `current.observed_at`, which remains null when ASOS is missing.
  `meta.forecasts[]` gives each horizon's actual numeric forecast inputs, valid time and separate
  KMA/AirKorea issue times.
- Missing/old/incorrectly matched live forecasts become NaN inputs for that source/horizon.
  Available predictions are returned with `status=degraded`, `missing_sources`, `missing_features`
  and `unavailable_targets`. Nonfinite values are serialized as JSON null, never zero.
  `as_of` does not collect or write: historical predictions require matching historical forecast rows already in DB.

Normal dashboard requests without `as_of` now collect the selected station's ASOS,
AirKorea and KHOA observations in parallel, then obtain weather/PM forecasts, validate them,
and run the existing CatBoost model for four horizons from that request's in-memory records.
Displayed PM, NowCast AQI and model inputs use the same collected records.
No DB credentials, connection, persistence or DB fallback are used for normal live requests
or `/api/v1/dashboard/config`. Config marks uncollected current status as `UNKNOWN`;
the frontend uses the selected station's actual dashboard status after collection.

- Collectors: `backend/live_observations.py`, `backend/forecast_inputs.py`. Reuse the existing ASOS/AirKorea collectors and ingestion validators.
- Required live server environment: `KMA_AUTH_KEY` (fallback `KMA_API_KEY`),
  `AIRKOREA_API_KEY` (fallback `DATA_API_KEY`), and `DATA_API_KEY` for KHOA.
  Weather labels reuse collected KMA forecast rows, so source-only retries make no extra label API call.
  Keys must have the relevant API permissions.
- KHOA: [조위관측소 최신 관측데이터](https://www.data.go.kr/data/15155508/openapi.do),
  `dtRecent/GetDTRecentApiService`. The approved hourly query uses `obsCode=DT_0001`
  (인천) or `IE_0062` (옹진소청초); the latter retains DB/model name `소청초`.
  Existing station mapping is preserved: 102 → 소청초; 112/201 → 인천.
- There is no durable collection history. For source-only retries, up to 64 request snapshots are
  retained for 600 seconds in this process's memory. A per-snapshot lock serializes retries.
  Successful sources are reused and retain their original `fetched_at` and observation timestamps.
- All sources must have observations at or before the ASOS base time, no older
  than two hours at collection start. Future/nonfinite/invalid measurements are rejected.
  AirKorea may publish a future hourly row with only some pollutants; all rows after the
  request time are excluded, regardless of which measurements are already present.
  KHOA timeout/network/HTTP 429 or 5xx failures are retried once; each attempt times out after 10 seconds.
  Collected input times are rechecked before model execution. Null instrument values
  remain null; the existing model's missing-value handling is unchanged.
- A source failure is returned in `meta.collection.errors` and `retryable_sources` alongside
  successful observations and possible forecasts in HTTP 200 `PARTIAL_SUCCESS`.
  Incomplete predictions do not pass mission evaluation (`INPUT_INCOMPLETE`). Missing values are
  not substituted with old observations, adjacent forecasts or zeros. Forecast accuracy with missing
  inputs has not been evaluated.
  A received row with a missing current visibility/PM baseline remains visible and makes
  that source retryable (`BASELINE_MISSING`). Source status `partial` distinguishes incomplete
  returned data from a wholly missing source. Forecast source times use `issued_at` and
  `collected_at`, not an observation timestamp.
- Observation and forecast collection phases each wait up to 25 seconds; pending results are
  marked `TIMEOUT` and discarded even if the network call finishes later.
- `as_of` remains a read-only historical query. The existing Incheon `mock=true`
  response bypasses collection. These legacy paths still require DB credentials/data;
  a DB-free deployment should omit `as_of` and use `mock=false`.
  No scheduler or background collection process is required.
- `meta.collection` reports `requested_at`, `collected_at`,
  `model_input_observed_at`, `collected_rows` and `storage: "memory"`.
  Forecast times are ASOS base time + horizon.
  Sources publish on their own schedules: request time is not observation time.
- Existing DB timestamps remain naive KST for compatibility; API timestamps include `+09:00`.
  This change does not retrain or validate forecast accuracy.

Retry the same dashboard route with the original station/interval/mission and
`collection_id=<meta.collection.id>&retry_source=<failed source>`. Only that API is called;
the response is rebuilt from the updated snapshot. Allowed sources are ASOS, AIRKOREA,
TIDE_OBSERVATORY, KMA_FORECAST and AIRKOREA_FORECAST. Invalid parameter pairs return 422;
expired/missing snapshots, mismatched conditions and already-successful sources return 409.
Expiration, eviction, a process restart or a different worker requires a new full dashboard request.
Multiple workers/replicas require routing retries to the same process; no distributed cache is used.
When ASOS recovery changes the prediction origin, all retained rows are rematched by that origin;
an unavailable forecast time is marked missing instead of mixing incompatible releases.

Live logs contain `[API 수집 완료]`, `[예측 완료]`, `API 부분 실패` and HTTP status.
`/api/health` alone does not verify external collection or prediction. A 200 with partial data
does not imply that every source, target or horizon is complete.

The 2026-10-23 package notes below describe the old snapshot. Its CSV loop is optional
legacy tooling and is not used by the latest-data dashboard request.

## Scope

- `backend/main.py`: FastAPI dashboard API (`/api/v1/stations/102|112|201/dashboard`), health (`/api/health`).
- `backend/airkorea_live.py`: legacy read-only CSV helper; no longer used by the dashboard response.
- `backend/aqi.py`: US EPA NowCast calculation; when input history is insufficient, `status=insufficient_data`, `value=null`.
- `backend/model_predict.py` with `backend/models/forecast_tuned/`: observation + forecast tuned CatBoost models.
- `backend/kma_weather.py`: weather labels; uses the separate `KMA_API_KEY` environment variable.
- `backend_airkorea_test/run_csv_auto.ps1`: update AirKorea and ASOS CSV on a 30-minute loop; verify the running dashboard API on port 8000. Its ASOS pipeline does not apply DB changes by default.

## Windows PowerShell setup

Unzip preserving folder structure; run commands from the extracted top-level directory.

```powershell
python -m pip install -r requirements-backend.txt
# Start an SSH port forward to PostgreSQL separately, if required by deployment.
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "5434"
$env:DB_NAME = "weather_db"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = Read-Host "PostgreSQL Password"
$env:KMA_API_KEY = Read-Host "KMA forecast API key"
$env:KMA_AUTH_KEY = Read-Host "KMA ASOS API key"
$env:AIRKOREA_API_KEY = Read-Host "AirKorea API key"
$env:DATA_API_KEY = Read-Host "KHOA public data API key"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a **different** PowerShell terminal, if collecting data:

```powershell
$env:KMA_AUTH_KEY = Read-Host "KMA ASOS API key"
$env:AIRKOREA_API_KEY = Read-Host "AirKorea API key"
powershell -ExecutionPolicy Bypass -File .\backend_airkorea_test\run_csv_auto.ps1 -Loop -IntervalMinutes 30
```

`KMA_AUTH_KEY` (ASOS collector) and `KMA_API_KEY` (weather display) are distinct environment variable names. The same actual API key may be usable for both **only if its permissions support both APIs**. Environment variables set in one terminal do not automatically populate another terminal.

Never put passwords or keys into source files, ZIP archives, or chat. The CSV snapshot in this package is from 2026-10-23 and will become stale until collection resumes. `DB_PASSWORD` is only required for the running FastAPI server / PostgreSQL reads, not the dry-run collection script.

## Snapshot verified offline (2026-10-23 16:00 KST)

| ASOS ID | AirKorea station | PM2.5 | PM10 | AQI | Status |
|---|---|---:|---:|---|---|
| 102 | Baengnyeong | 14 | 21 | 58 | calculated |
| 112 | Incheon/Sungui | 10 | 26 | 46 | calculated |
| 201 | Ganghwa/Seokmori | 3 | 17 | null | insufficient_data (recent hourly gaps) |

CSV 68 rows verified including normalization of three `24:00` timestamps; CatBoost model loaded and completed a **synthetic-input smoke test**, not an accuracy or production prediction validation.

## API contract and limitations

- `data.current.observed_at` refers to ASOS, while `data.source_status[]` entry where `source=AIRKOREA` has its own observation time.
- `data.current.pm25_ug_m3` / `pm10_ug_m3` come from the collected PostgreSQL snapshot. `data.current.aqi` contains `standard`, `basis`, `value`, `display_level`, `display_grade`, `status`.
- Stale or missing AQI is correctly represented with null/insufficient_data, not invented values.
- Full end-to-end execution requires a running PostgreSQL/SSH tunnel, installed dependencies, approved source API keys, and valid model files. Fresh inputs do not prove operational forecast accuracy.
- Optional `backend_airkorea_test/ingest_airkorea.py --apply` writes to `public.raw_air_quality`. **Do not use `--apply` unless authorized**. Normal 30-minute collection is dry-run for ASOS and CSV-only for AirKorea.
- No actual frontend application is included; this ZIP is a backend integration package.

## Static checks

### 수집 진단 로그 (2026-10-27)

일시 오류 시 같은 관측소에서 이전에 정상 수집한 자료를 프로세스 메모리에서 최대 2시간 재사용한다.
각 PM 항목은 실제 관측 시각이 조회 시각으로부터 2시간 이내인 마지막 유효값만 사용하며,
`current.pm25_observed_at` / `pm10_observed_at`, `pm25_reused` / `pm10_reused`로 출처를 표시한다.
시간별 원본 이력은 채워 넣지 않으며, NowCast도 실제 관측 이력만 사용한다. 이전 값 사용 시 예측은
보완된 결과로 표시하고 임무 판정은 대기한다. 예보는 별도로 대상 시각 일치와 기존 발표 시각 기준을
통과해야 한다. 메모리 캐시는 서버 재시작 시 비워지고 다른 워커와 공유되지 않는다.

서버·접근·수집 로그는 KST 기준 `YYYYMMDD HHMMSS LEVEL: 메시지`로 출력한다.
누락이 발생한 출처에는 `[API 누락 상세]` JSON을 추가한다. 같은 `collection_id`로 조회와 재시도를 묶어 확인한다.

- `response_json`: 원천 응답에서 선별한 header·항목 필드. 관측은 요청별 최대 3행, 예보는 페이지별 최대 100행이며 전체 응답은 출력하지 않는다.
- `normalized_records`: 모델 입력으로 정규화한 수집값. 관측은 최신 3행을 표시한다.
- `missing_details`: 누락 필드·사용한 값·대상 시각. `TARGET_NOT_PROVIDED`는 대상 날짜/시각 미제공, `FORECAST_TOO_OLD`는 현재 유효 기준 초과, `NO_USABLE_TARGET_VALUES`는 대상 자료가 있으나 입력값으로 사용 불가다.
- `[API 수집 오류 상세]`: 오류 종류·가능한 HTTP 상태·응답 header. 응답을 받기 전 실패하면 JSON 내용은 없을 수 있다.

API 키·인증 헤더·비밀번호는 제거하고, JSON 숫자 결측은 `null`로 출력한다. 원천의 `-`·빈 문자열은 `response_json`에서 그대로 비교할 수 있다.
발표 시각이 이르다는 이유만으로 누락 처리하지 않는다. 대상 날짜 유무와 출처별 유효 기준을 각각 확인한다.

```powershell
python -m compileall -q backend backend_airkorea_test src/collectors/api
python -m backend_airkorea_test.validate_airkorea_csv .\backend_airkorea_test\data\airkorea_latest.csv
```
