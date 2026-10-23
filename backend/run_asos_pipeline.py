"""ASOS 수집 → CSV 검증 → 테스트 DB 적재 파이프라인."""

import subprocess
import sys
from pathlib import Path
import argparse

from backend.ingest_asos import (
    validate_csv,
    prepare_records,
    insert_records,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CSV_PATH = (
    PROJECT_ROOT / "src/collectors/api/data/raw/asos/asos_realtime_pipeline_test.csv"
)

COLLECTOR_PATH = PROJECT_ROOT / "src/collectors/api/asos_collector.py"


def main():
    parser = argparse.ArgumentParser(description="ASOS 수집 및 DB 적재")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="테스트 DB에 실제 적재",
    )
    args = parser.parse_args()

    subprocess.run(
        [
            sys.executable,
            str(COLLECTOR_PATH),
            "--realtime",
            "--hours=3",
            "--output-filename=asos_realtime_pipeline_test.csv",
            "--save-mode=overwrite",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    print("[2/3] CSV 검증 및 변환")

    records = prepare_records(validate_csv(CSV_PATH))
    print(f"[CSV 검증 성공] {len(records)}건")

    print("[3/3] DB 적재")
    inserted = insert_records(records, apply=args.apply)

    if args.apply:
        print(f"[파이프라인 완료] 신규 적재 {inserted}건")
    else:
        print("[파이프라인 테스트 완료] DB 변경 없음")


if __name__ == "__main__":
    main()
