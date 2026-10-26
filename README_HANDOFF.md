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
2026-10-26 원본 `최종모델.zip`의 세 모델과 바이트 동일성, 메타데이터의 ZIP 해시 일치를 확인했다.
`forecast_tuned`는 완성 모델을 추출한 폴더이며 추가 학습·튜닝은 하지 않았다.
`metadata.json`은 입력 순서·모델 해시와 원본 노트북 방식으로 복원한 출력 계수 `sigma[h]`를 보관한다.
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

AQI responsibility (verified 2026-10-26): the backend computes the PM2.5/PM10
NowCast from actual hourly observations, retaining missing hourly slots. Invalid
concentrations do not count toward the two-of-three completeness requirement.
AQI above 500 follows the last EPA interval's linear slope instead of being capped.
The frontend maps the returned numeric AQI to the product's existing five display
stages; backend display labels are retained for compatibility, not UI authority.
No observation interpolation or missing future forecast fabrication is enabled.

### Active model: observation + forecast tuned

The active artifacts are `backend/models/forecast_tuned/cb_tuned_{visibility_km,pm25,pm10}.cbm`
from the supplied `최종모델.zip`. The old multi-output draft is retained but no longer loaded.
No fitting/retraining is performed. Runtime checks the three original hashes and the identical
76-column feature order. The exporter below restores the train-only horizon standard deviations
omitted from the supplied model files, following `피처확인_관측예보_분석.ipynb` cells 13/14/17/19.

```powershell
python -m backend.import_tuned_models "C:\path\to\최종모델.zip"
```

- Sources: approved data.go.kr `VilageFcstInfoService_2.0/getVilageFcst` (weather),
  AirKorea `ArpltnInforInqireSvc/getMinuDustFrcstDspth` (Incheon PM2.5 grade).
  Both use existing `DATA_API_KEY`; AirKorea may use `AIRKOREA_API_KEY` instead.
- Model PIT-grid mapping follows the provided collection pipeline: 102 → (21,136)/백령면,
  112 → (54,125)/동인천동, 201 → (51,130)/불은면. This is separate from the legacy weather-label helper.
- The ASOS window is now 25 hourly points (origin minus 24 hours through origin). The model
  derives lag-1h, difference-3h, rolling-24h and same-hour history without forward-filling missing hours.
- Forecasts are matched at `origin + horizon`, using KMA releases publicly available at the
  observation origin (20-minute publication margin) and PM releases no later than that origin.
  Neighboring target hours or future releases are never substituted.
- Live requests match the collected forecast rows in memory. Historical DB reads use the same
  matching/conversion function. Live collection does not open a DB connection or write any tables.
- The tuned output is not a final concentration: `result = expm1(log1p(current) + residual × sigma[h])`.
  Clamp below at zero; visibility additionally uses the original train-target maximum from metadata.
- PM1 and wave height/period are currently unavailable and remain NaN as supported by CatBoost;
  they are never filled with zero or stale observations. A missing current baseline disables only
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

```powershell
python -m compileall -q backend backend_airkorea_test src/collectors/api
python -m backend_airkorea_test.validate_airkorea_csv .\backend_airkorea_test\data\airkorea_latest.csv
```
