"""PM1 데이터를 수집·저장·내보내는 명령줄 프로그램의 진입점."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Literal, Mapping, Sequence
from uuid import uuid4

import psycopg

from src.crawlers.pm1.crawler import (
    calculate_eligible_end,
    fetch_hour,
    iter_hour_windows,
    parse_source_offset,
)
from src.crawlers.pm1.database import (
    acquire_source_lock,
    commit_hour,
    connect_database,
    export_csv,
    initialize_schema,
    load_database_config,
    read_ingest_state,
    validate_schema,
)

DEFAULT_CSV_PATH = Path("data/processed/pm1/pm1_measurements.csv")
COLLECTOR_VERSION = "pm1-crawler-v1"
ENV_KEYS = {
    "PM1_API_KEY",
    "PM1_SOURCE_TIMEZONE",
    "PM1_SYNC_LAG_HOURS",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_CONNECTION_MODE",
    "DB_SSLROOTCERT",
    "DB_MIGRATION_USER",
    "DB_MIGRATION_PASSWORD",
    "DB_INGEST_USER",
    "DB_INGEST_PASSWORD",
    "DB_EXPORT_USER",
    "DB_EXPORT_PASSWORD",
}


def load_environment(
    path: Path = Path(".env"), process_env: Mapping[str, str] = os.environ
) -> dict[str, str]:
    """허용된 환경변수만 읽고 운영체제 환경변수를 우선 적용한다.

    ``.env`` 파일은 셸 명령으로 실행하지 않고 단순한 ``키=값`` 텍스트로만
    해석한다. 따라서 명령 치환 같은 문자열이 들어 있어도 실행되지 않는다.
    """
    values: dict[str, str] = {}
    seen: set[str] = set()
    if path.exists():
        # 수집기에서 사용하는 키만 허용해 오타나 불필요한 비밀값이 우연히
        # 프로그램 안으로 들어오는 일을 막는다.
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, raw_value = line.partition("=")
            key = key.strip()
            if key not in ENV_KEYS:
                continue
            if not separator:
                raise ValueError(f"Invalid .env entry on line {line_number}")
            if key in seen:
                raise ValueError(f"Duplicate .env key: {key}")
            seen.add(key)
            value = raw_value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            elif value.startswith(("'", '"')) or value.endswith(("'", '"')):
                raise ValueError(f"Unmatched quote for .env key: {key}")
            if not value:
                raise ValueError(f"Empty .env value for key: {key}")
            values[key] = value

    # 배포 환경에서 주입한 값이 로컬 .env보다 우선해야 같은 코드로 개발과
    # 운영 환경을 모두 실행할 수 있다.
    for key in ENV_KEYS:
        if key in process_env:
            values[key] = process_env[key]
    return values


def _required(env: Mapping[str, str], key: str) -> str:
    """필수 환경변수의 공백을 제거하고 누락 여부를 검사한다."""
    value = env.get(key, "").strip()
    if not value:
        raise ValueError(f"Required environment variable is missing: {key}")
    return value


def _time_contract(env: Mapping[str, str]) -> tuple[str, timezone, int]:
    """원본 시간대와 API 공개 지연시간 설정을 검증해 반환한다."""
    source_timezone_text = _required(env, "PM1_SOURCE_TIMEZONE")
    source_timezone = parse_source_offset(source_timezone_text)
    try:
        sync_lag_hours = int(_required(env, "PM1_SYNC_LAG_HOURS"))
    except ValueError as error:
        raise ValueError("PM1_SYNC_LAG_HOURS must be an integer") from error
    if sync_lag_hours < 0:
        raise ValueError("PM1_SYNC_LAG_HOURS cannot be negative")
    return source_timezone_text, source_timezone, sync_lag_hours


def build_parser() -> argparse.ArgumentParser:
    """PM1 수집기가 지원하는 명령과 인자를 정의한다."""
    parser = argparse.ArgumentParser(description="Collect PM1 data into PostgreSQL")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="create and validate the PostgreSQL schema")
    backfill = commands.add_parser(
        "backfill", help="collect through a fixed source hour"
    )
    backfill.add_argument(
        "--end", required=True, help="final source hour as YYYYMMDDHH00"
    )
    commands.add_parser("sync", help="collect through the current eligible source hour")
    export = commands.add_parser("export-csv", help="write the integrated CSV snapshot")
    export.add_argument("--output", type=Path, default=DEFAULT_CSV_PATH)
    return parser


def run_init_db(env: Mapping[str, str]) -> int:
    """PM1 PostgreSQL 스키마를 만들고 구조와 권한을 검증한다."""
    source_timezone, _, sync_lag_hours = _time_contract(env)
    config = load_database_config("migration", env)
    ingest_role = _required(env, "DB_INGEST_USER")
    export_role = _required(env, "DB_EXPORT_USER")
    with connect_database(config) as connection:
        with connection.transaction():
            initialize_schema(
                connection,
                source_timezone,
                sync_lag_hours,
                ingest_role,
                export_role,
            )
            validate_schema(connection, ingest_role, export_role)
    print("PM1 schema initialized and validated")
    return 0


def run_collection(
    mode: Literal["backfill", "sync"],
    end: str | None,
    env: Mapping[str, str],
) -> int:
    """DB 체크포인트부터 종료 시각까지 PM1 데이터를 시간순으로 수집한다."""
    api_key = _required(env, "PM1_API_KEY")
    source_timezone_text, source_timezone, sync_lag_hours = _time_contract(env)
    config = load_database_config("ingest", env)

    # 아직 제공기관에서 확정되지 않았을 수 있는 최신 시간대는 수집하지 않는다.
    # backfill도 이 경계를 넘지 못하게 해 과거 수집과 실시간 수집의 기준을 맞춘다.
    eligible_end = calculate_eligible_end(
        datetime.now(UTC), source_timezone, sync_lag_hours
    )
    if mode == "backfill":
        if end is None:
            raise ValueError("backfill requires --end")
        list(iter_hour_windows(end[:-2] + "00", end))
        collection_end = end
    else:
        if end is not None:
            raise ValueError("sync does not accept a fixed end")
        collection_end = eligible_end
    if collection_end > eligible_end:
        raise ValueError(f"Requested end exceeds the eligible boundary {eligible_end}")

    run_id = uuid4()
    hours = inserted = already_present = 0
    with connect_database(config) as connection:
        # 같은 데이터 원본을 두 프로세스가 동시에 수집하면 체크포인트가 꼬일 수
        # 있으므로 PostgreSQL 세션 잠금을 먼저 확보한다.
        if not acquire_source_lock(connection):
            print("Another PM1 collection process already holds the source lock")
            return 2
        validate_schema(connection)
        state = read_ingest_state(connection)
        if state.schema_version != 1:
            raise RuntimeError("Unsupported PM1 schema version")
        if (
            state.source_timezone != source_timezone_text
            or state.sync_lag_hours != sync_lag_hours
        ):
            raise RuntimeError("PM1 time configuration differs from persisted state")
        if state.next_start_dtm > collection_end:
            print("PM1 checkpoint is already beyond the requested end")
            return 0

        # 한 시간의 데이터와 다음 체크포인트를 같은 DB 트랜잭션으로 저장한다.
        # 중간에 실패하면 해당 시간 전체가 롤백되어 다음 실행에서 다시 시도된다.
        for window in iter_hour_windows(state.next_start_dtm, collection_end):
            rows = fetch_hour(window, api_key, source_timezone)
            result = commit_hour(
                connection,
                window.start_dtm,
                window,
                rows,
                run_id,
                COLLECTOR_VERSION,
            )
            hours += 1
            inserted += result.inserted
            already_present += result.already_present
            if hours % 100 == 0:
                print(
                    f"PM1 collection progress: hours={hours}, inserted={inserted}, "
                    f"checkpoint={window.start_dtm}",
                    flush=True,
                )
    print(
        f"PM1 collection completed: hours={hours}, inserted={inserted}, "
        f"already_present={already_present}"
    )
    return 0


def run_export(output: Path, env: Mapping[str, str]) -> int:
    """읽기 전용 DB 계정으로 통합 CSV 스냅샷을 생성한다."""
    config = load_database_config("export", env)
    with connect_database(config) as connection:
        row_count = export_csv(connection, output)
    print(f"PM1 CSV exported: rows={row_count}, path={output}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """요청한 PM1 명령 하나를 실행하고 프로세스 종료 코드를 반환한다."""
    arguments = build_parser().parse_args(argv)
    try:
        env = load_environment()
        if arguments.command == "init-db":
            return run_init_db(env)
        if arguments.command == "backfill":
            return run_collection("backfill", arguments.end, env)
        if arguments.command == "sync":
            return run_collection("sync", None, env)
        return run_export(arguments.output, env)
    except (ValueError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except (psycopg.Error, OSError):
        print("ERROR: PM1 database or file operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
