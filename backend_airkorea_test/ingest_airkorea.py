"""Validate and optionally ingest AirKorea CSV into PostgreSQL."""

import argparse
import csv
import math
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path

DATE = "\ub0a0\uc9dc"
NAME = "\uce21\uc815\uc18c\uba85"
CODE = "\uce21\uc815\uc18c\ucf54\ub4dc"
REGION = "\uc2dc\ub3c4"

FIELD_MAP = {
    "\uc544\ud669\uc0b0\uac00\uc2a4": "so2",
    "\uc77c\uc0b0\ud654\ud0c4\uc18c": "co",
    "\uc624\uc874": "o3",
    "\uc774\uc0b0\ud654\uc9c8\uc18c": "no2",
    "PM10": "pm10",
    "PM2.5": "pm25",
}

STATION_CODES = {
    "\uc22d\uc758": "823632",
    "\uc11d\ubaa8\ub9ac": "831481",
    "\ubc31\ub839\ub3c4": "831492",
}

COLUMNS = [
    "tm",
    "station_name",
    "station_code",
    "sido",
    "so2",
    "co",
    "o3",
    "no2",
    "pm10",
    "pm25",
]


def parse_time(value):
    value = value.strip()
    if value.endswith(" 24:00"):
        return datetime.strptime(value[:10], "%Y-%m-%d") + timedelta(days=1)
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def parse_number(value):
    value = (value or "").strip()
    if not value:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("NON_FINITE_NUMBER")
    return result


def prepare_records(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {DATE, NAME, CODE, REGION, *FIELD_MAP.keys()}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("MISSING_COLUMNS: " + repr(missing))
        rows = list(reader)

    records = []
    seen = set()
    normalized = 0

    for line_number, row in enumerate(rows, start=2):
        try:
            raw_time = row[DATE].strip()
            tm = parse_time(raw_time)
            name = row[NAME].strip()
            code = str(int(row[CODE].strip()))

            if STATION_CODES.get(name) != code:
                raise ValueError("STATION_CODE_MISMATCH")

            key = (tm, name)
            if key in seen:
                raise ValueError("DUPLICATE_PRIMARY_KEY")
            seen.add(key)

            record = {
                "tm": tm,
                "station_name": name,
                "station_code": code,
                "sido": row[REGION].strip(),
            }

            for csv_column, db_column in FIELD_MAP.items():
                record[db_column] = parse_number(row[csv_column])

            records.append(record)
            if raw_time.endswith(" 24:00"):
                normalized += 1

        except Exception as error:
            raise ValueError(f"CSV_LINE_{line_number}: {error}") from error

    return records, normalized


def apply_records(records, connection=None):
    from backend.database import get_connection

    placeholders = ", ".join(["%s"] * len(COLUMNS))
    column_sql = ", ".join(COLUMNS)

    sql = f"""
        INSERT INTO public.raw_air_quality ({column_sql})
        VALUES ({placeholders})
        ON CONFLICT (tm, station_name) DO UPDATE SET
        {', '.join(f'{column} = EXCLUDED.{column}' for column in COLUMNS if column not in ('tm', 'station_name'))}
    """

    inserted = 0

    with (
        nullcontext(connection) if connection is not None else get_connection()
    ) as conn:
        with conn.cursor() as cur:
            for record in records:
                cur.execute(
                    sql,
                    tuple(record[column] for column in COLUMNS),
                )
                inserted += cur.rowcount

    return inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to PostgreSQL",
    )
    args = parser.parse_args()

    records, normalized = prepare_records(args.csv)

    print("CSV_VALID:", len(records))
    print("NORMALIZED_24H:", normalized)

    if not args.apply:
        print("MODE: DRY_RUN")
        print("DB_WRITE: NOT_PERFORMED")
        return

    inserted = apply_records(records)
    print("MODE: APPLY")
    print("DB_INSERTED:", inserted)


if __name__ == "__main__":
    main()
