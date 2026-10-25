# WeatherElfs Backend — teammate handoff (updated 2026-10-25)

## Latest-data request flow (2026-10-25)

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
- The same observation transaction also upserts existing `tb_kma_short_forecast` and
  `raw_air_pm25_forecast`. No schema change, deletion, or duplicate insertion into the unindexed
  `mart_forecast_pit_48h` is performed. Prediction reads those rows in the same DB snapshot as observations.
- The tuned output is not a final concentration: `result = expm1(log1p(current) + residual × sigma[h])`.
  Clamp below at zero; visibility additionally uses the original train-target maximum from metadata.
- PM1 and wave height/period are currently unavailable and remain NaN as supported by CatBoost;
  they are never filled with zero or stale observations. Missing current visibility/PM baselines abort prediction.
- `meta.model` identifies this model, its inverse transform and missing input features.
  `meta.forecasts[]` gives each horizon's actual numeric forecast inputs, valid time and separate
  KMA/AirKorea issue times. `meta.collection.forecast_provenance` verifies fetched vs DB-read releases.
- Missing/old/incorrectly matched stored forecasts return HTTP 503 `FORECAST_INPUT_UNAVAILABLE`.
  `as_of` does not collect or write: historical predictions require matching historical forecast rows already in DB.

Normal dashboard requests without `as_of` now collect the selected station's ASOS,
AirKorea and KHOA observations in parallel, then obtain weather/PM forecasts, validate them, upsert all five sources
in one PostgreSQL transaction, then read a consistent snapshot and run the existing
CatBoost model for four horizons. Displayed PM, NowCast AQI and model inputs use the
same DB snapshot; the local AirKorea CSV no longer overrides API responses.

- Collectors: `backend/live_observations.py`, `backend/forecast_inputs.py`. Reuse the existing ASOS/AirKorea collectors and ingestion validators.
- Required server environment: `DB_*`, `KMA_AUTH_KEY` (fallback `KMA_API_KEY`),
  `AIRKOREA_API_KEY` (fallback `DATA_API_KEY`), and `DATA_API_KEY` for KHOA.
  Keep `KMA_API_KEY` for weather labels. Keys must have the relevant API permissions.
- KHOA: [조위관측소 최신 관측데이터](https://www.data.go.kr/data/15155508/openapi.do),
  `dtRecent/GetDTRecentApiService`. The approved hourly query uses `obsCode=DT_0001`
  (인천) or `IE_0062` (옹진소청초); the latter retains DB/model name `소청초`.
  Existing station mapping is preserved: 102 → 소청초; 112/201 → 인천.
- Upserts target `raw_weather_asos_realtime`, `raw_air_quality`, `raw_tide_observatory`,
  `tb_kma_short_forecast`, `raw_air_pm25_forecast`. Same keys update corrected values; no schema
  changes or historical deletion. `stored_rows` counts inserts and updates, not new rows only.
- All sources must have observations at or before the ASOS base time, no older
  than two hours at collection start. Future/nonfinite/invalid measurements are rejected.
  Actual DB input times are rechecked before model execution. Null instrument values
  remain null; the existing model's missing-value handling is unchanged.
- Collection/ingestion/input mismatch returns HTTP 503 `LATEST_DATA_UNAVAILABLE`;
  model failure returns HTTP 503 `FORECAST_FAILED`. Old observations are not substituted.
  Failed ingestion rolls back all five sources. A model failure does not undo already
  committed valid observations.
- `as_of` remains a read-only historical query. The existing Incheon `mock=true`
  response bypasses collection. No scheduler or background collection process is required.
- `meta.collection` reports `requested_at`, `collected_at`,
  `model_input_observed_at` and `stored_rows`. Forecast times are ASOS base time + horizon.
  Sources publish on their own schedules: request time is not observation time.
- Existing DB timestamps remain naive KST for compatibility; API timestamps include `+09:00`.
  This change does not retrain or validate forecast accuracy.

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
