# WeatherElfs Backend — teammate handoff (2026-10-23)

## Scope

- `backend/main.py`: FastAPI dashboard API (`/api/v1/stations/102|112|201/dashboard`), health (`/api/health`).
- `backend/airkorea_live.py`: read-only latest AirKorea CSV for displayed PM2.5/PM10 and current AQI. Handles `24:00` timestamps.
- `backend/aqi.py`: US EPA NowCast calculation; when input history is insufficient, `status=insufficient_data`, `value=null`.
- `backend/model_predict.py` with `backend/models/`: CatBoost prediction model.
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
- `data.current.pm25_ug_m3` / `pm10_ug_m3` come from the latest AirKorea CSV when available. `data.current.aqi` contains `standard`, `basis`, `value`, `display_level`, `display_grade`, `status`.
- Stale or missing AQI is correctly represented with null/insufficient_data, not invented values.
- **Important model-data caveat:** CatBoost input in `main.py` still reads AirKorea from the historical PostgreSQL `raw_air_quality` table, and marine observations may also be old. This handoff does not prove the live CatBoost predictions use fresh data; check and fix before presenting these predictions as operational forecasts.
- Marine state may be `delayed`. Full end-to-end execution on teammate PC requires a running PostgreSQL/SSH tunnel, installed dependencies, weather API keys, and valid model files.
- Optional `backend_airkorea_test/ingest_airkorea.py --apply` writes to `public.raw_air_quality`. **Do not use `--apply` unless authorized**. Normal 30-minute collection is dry-run for ASOS and CSV-only for AirKorea.
- No actual frontend application is included; this ZIP is a backend integration package.

## Static checks

```powershell
python -m compileall -q backend backend_airkorea_test src/collectors/api
python -m backend_airkorea_test.validate_airkorea_csv .\backend_airkorea_test\data\airkorea_latest.csv
```
