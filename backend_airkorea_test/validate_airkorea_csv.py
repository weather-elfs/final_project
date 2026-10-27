import sys
from pathlib import Path
from backend_airkorea_test.ingest_airkorea import prepare_records

path = Path(sys.argv[1])
records, _ = prepare_records(path)

expected = {"823632", "831481", "831492"}
codes = {str(r["station_code"]) for r in records}

if not expected.issubset(codes):
    raise SystemExit("[FAIL] Missing station data")

if not records:
    raise SystemExit("[FAIL] Empty CSV")

print("[OK] Validated records:", len(records))

for code in sorted(expected):
    latest = max(
        r["tm"] for r in records
        if str(r["station_code"]) == code
    )
    print("Station", code, "Latest", latest)
