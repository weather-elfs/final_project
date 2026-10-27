"""PM1 수집 데이터와 체크포인트를 PostgreSQL에 안전하게 저장하는 모듈."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence
from uuid import UUID

import psycopg
from psycopg import sql

from src.crawlers.pm1.crawler import HourWindow, MeasurementRow, parse_source_offset

DatabaseRole = Literal["migration", "ingest", "export"]
ConnectionMode = Literal["tls", "ssh-tunnel"]
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SOURCE_NAME = "pm1_dust_data"
SCHEMA_OWNER_ROLE = "weather_schema_owner"

_ROLE_ENV = {
    "migration": ("DB_MIGRATION_USER", "DB_MIGRATION_PASSWORD"),
    "ingest": ("DB_INGEST_USER", "DB_INGEST_PASSWORD"),
    "export": ("DB_EXPORT_USER", "DB_EXPORT_PASSWORD"),
}


@dataclass(frozen=True)
class DatabaseConfig:
    """용도별 DB 계정에 대해 검증을 마친 PostgreSQL 연결 설정."""

    host: str
    port: int
    dbname: str
    user: str
    password: str
    connection_mode: ConnectionMode
    sslrootcert: Path | None

    def connect_kwargs(self) -> dict[str, Any]:
        """검증된 TLS 또는 로컬 SSH 터널에 맞는 연결 옵션을 반환한다."""
        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
            "gssencmode": "disable",
            "autocommit": True,
        }
        if self.connection_mode == "ssh-tunnel":
            # SSH가 암호화와 서버 인증을 담당하므로 로컬 터널 구간에서는
            # PostgreSQL TLS를 사용하지 않는다.
            kwargs["sslmode"] = "disable"
        else:
            # 원격 직접 연결은 CA와 호스트명을 모두 확인하고 채널 바인딩으로
            # 중간자 공격에 대한 보호를 강화한다.
            kwargs.update(
                {
                    "sslmode": "verify-full",
                    "sslrootcert": str(self.sslrootcert),
                    "channel_binding": "require",
                }
            )
        return kwargs


@dataclass(frozen=True)
class IngestState:
    """DB에 영구 저장되는 수집 체크포인트와 시간 경계 설정."""

    next_start_dtm: str
    last_success_start_dtm: str | None
    last_success_end_dtm: str | None
    source_timezone: str
    sync_lag_hours: int
    schema_version: int


@dataclass(frozen=True)
class CommitResult:
    """한 시간 단위 원자적 저장에서 발생한 행 수 집계."""

    inserted: int
    already_present: int


class CheckpointConflictError(RuntimeError):
    """API 조회 중 다른 작업이 DB 체크포인트를 변경했음을 나타낸다."""


class DataConflictError(RuntimeError):
    """같은 기본키에 대해 API 값과 기존 DB 값이 다름을 나타낸다."""


def _required(env: Mapping[str, str], key: str) -> str:
    """필수 환경변수의 공백을 제거하고 누락 여부를 검사한다."""
    value = env.get(key, "").strip()
    if not value:
        raise ValueError(f"Required environment variable is missing: {key}")
    return value


def load_database_config(role: DatabaseRole, env: Mapping[str, str]) -> DatabaseConfig:
    """비밀값을 오류에 노출하지 않고 용도별 DB 연결 설정을 읽는다."""
    if role not in _ROLE_ENV:
        raise ValueError(f"Unsupported database role: {role}")

    host = _required(env, "DB_HOST")
    connection_mode = env.get("DB_CONNECTION_MODE", "tls").strip()
    if connection_mode not in {"tls", "ssh-tunnel"}:
        raise ValueError("DB_CONNECTION_MODE must be tls or ssh-tunnel")
    if connection_mode == "ssh-tunnel":
        # SSH 터널 모드에서 원격 주소를 허용하면 암호화되지 않은 직접 연결이
        # 될 수 있으므로 반드시 로컬 루프백 주소만 받는다.
        try:
            loopback = ip_address(host).is_loopback
        except ValueError:
            loopback = host.lower() == "localhost"
        if not loopback:
            raise ValueError("SSH tunnel connections require a loopback DB_HOST")
    else:
        # verify-full은 인증서의 호스트명을 검사하므로 IP 주소 대신 인증서에
        # 등록된 DNS 이름이 필요하다.
        try:
            ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("DB_HOST must be a DNS name for TLS hostname verification")

    port_text = _required(env, "DB_PORT")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("DB_PORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise ValueError("DB_PORT must be between 1 and 65535")

    user_key, password_key = _ROLE_ENV[role]
    sslrootcert = (
        None
        if connection_mode == "ssh-tunnel"
        else Path(_required(env, "DB_SSLROOTCERT"))
    )
    return DatabaseConfig(
        host=host,
        port=port,
        dbname=_required(env, "DB_NAME"),
        user=_required(env, user_key),
        password=_required(env, password_key),
        connection_mode=connection_mode,
        sslrootcert=sslrootcert,
    )


def connect_database(config: DatabaseConfig) -> psycopg.Connection[tuple[Any, ...]]:
    """검증된 설정으로 autocommit PostgreSQL 연결을 연다."""
    return psycopg.connect(**config.connect_kwargs())


def initialize_schema(
    connection: psycopg.Connection[Any],
    source_timezone: str,
    sync_lag_hours: int,
    ingest_role: str,
    export_role: str,
) -> None:
    """기존 객체와 상태를 덮어쓰지 않고 최초 스키마와 권한을 구성한다."""
    if not ingest_role or not export_role:
        raise ValueError("Ingest and export database roles are required")
    if sync_lag_hours < 0:
        raise ValueError("PM1_SYNC_LAG_HOURS cannot be negative")
    parse_source_offset(source_timezone)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connection.transaction():
        with connection.cursor() as cursor:
            # 테이블 소유권은 로그인할 수 없는 전용 역할에 고정해 애플리케이션
            # 계정이 스키마를 임의로 바꾸지 못하게 한다.
            cursor.execute(
                sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(SCHEMA_OWNER_ROLE))
            )
            cursor.execute(schema_sql)
            cursor.execute(
                """
                INSERT INTO public.weather_ingest_state (
                    source_name, next_start_dtm, source_timezone, sync_lag_hours,
                    schema_version, updated_at
                ) VALUES (%s, %s, %s, %s, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (source_name) DO UPDATE
                SET source_name = EXCLUDED.source_name
                WHERE weather_ingest_state.source_timezone = EXCLUDED.source_timezone
                  AND weather_ingest_state.sync_lag_hours = EXCLUDED.sync_lag_hours
                  AND weather_ingest_state.schema_version = 1
                RETURNING source_name
                """,
                (SOURCE_NAME, "202103290000", source_timezone, sync_lag_hours),
            )
            if cursor.fetchone() is None:
                raise RuntimeError(
                    "Existing ingest state has a different timezone, lag, or schema version"
                )
            cursor.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON public.raw_weather_pm1, "
                    "public.weather_ingest_state FROM {}, {}"
                ).format(sql.Identifier(ingest_role), sql.Identifier(export_role))
            )
            cursor.execute(
                sql.SQL("GRANT SELECT, INSERT ON public.raw_weather_pm1 TO {}").format(
                    sql.Identifier(ingest_role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON public.weather_ingest_state TO {}").format(
                    sql.Identifier(ingest_role)
                )
            )
            cursor.execute(
                sql.SQL(
                    "GRANT UPDATE (next_start_dtm, last_success_start_dtm, "
                    "last_success_end_dtm, updated_at) "
                    "ON public.weather_ingest_state TO {}"
                ).format(sql.Identifier(ingest_role))
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON public.raw_weather_pm1 TO {}").format(
                    sql.Identifier(export_role)
                )
            )


def validate_schema(
    connection: psycopg.Connection[Any],
    ingest_role: str | None = None,
    export_role: str | None = None,
) -> None:
    """불완전하거나 오래됐거나 권한이 잘못된 DB 스키마를 거부한다."""
    # 단순히 테이블 존재 여부만 보면 오래된 컬럼·제약 조건을 놓칠 수 있다.
    # 예상 컬럼, 길이, NULL 정책, 제약, 인덱스, 소유권을 한 번에 비교한다.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT array_agg(
                            column_name::text || ':' || data_type::text || ':' ||
                            is_nullable::text ORDER BY ordinal_position
                        )
                   FROM information_schema.columns
                  WHERE table_schema = 'public'
                    AND table_name = 'raw_weather_pm1') = ARRAY[
                    'obsrr_tpcd:character varying:NO',
                    'obsrr_nm:character varying:NO',
                    'obsrt_dtm:character:NO',
                    'observed_at_utc:timestamp with time zone:NO',
                    'obsrt_tmprt:numeric:YES', 'obsrt_hmdt:numeric:YES',
                    'obsrt_wndrc_val:numeric:YES', 'obsrt_ws:numeric:YES',
                    'obsrt_pm01_val:numeric:YES', 'obsrt_pm25_val:numeric:YES',
                    'obsrt_pm10_val:numeric:YES',
                    'avoc_obsrt_pm01_val:numeric:YES',
                    'avoc_obsrt_pm25_val:numeric:YES',
                    'avoc_obsrt_pm10_val:numeric:YES',
                    'ingest_run_id:uuid:NO',
                    'collector_version:character varying:NO',
                    'ingested_at:timestamp with time zone:NO'
                ],
                (SELECT array_agg(
                            column_name::text || ':' || data_type::text || ':' ||
                            is_nullable::text ORDER BY ordinal_position
                        )
                   FROM information_schema.columns
                  WHERE table_schema = 'public'
                    AND table_name = 'weather_ingest_state') = ARRAY[
                    'source_name:character varying:NO',
                    'next_start_dtm:character:NO',
                    'last_success_start_dtm:character:YES',
                    'last_success_end_dtm:character:YES',
                    'source_timezone:character varying:NO',
                    'sync_lag_hours:integer:NO',
                    'schema_version:smallint:NO',
                    'updated_at:timestamp with time zone:NO'
                ],
                (SELECT jsonb_object_agg(
                            table_name::text || '.' || column_name::text,
                            character_maximum_length
                        )
                   FROM information_schema.columns
                  WHERE table_schema = 'public'
                    AND (table_name, column_name) IN (
                        ('raw_weather_pm1', 'obsrr_tpcd'),
                        ('raw_weather_pm1', 'obsrr_nm'),
                        ('raw_weather_pm1', 'obsrt_dtm'),
                        ('raw_weather_pm1', 'collector_version'),
                        ('weather_ingest_state', 'source_name'),
                        ('weather_ingest_state', 'next_start_dtm'),
                        ('weather_ingest_state', 'last_success_start_dtm'),
                        ('weather_ingest_state', 'last_success_end_dtm'),
                        ('weather_ingest_state', 'source_timezone')
                    )) = '{
                        "raw_weather_pm1.obsrr_tpcd": 4,
                        "raw_weather_pm1.obsrr_nm": 50,
                        "raw_weather_pm1.obsrt_dtm": 12,
                        "raw_weather_pm1.collector_version": 80,
                        "weather_ingest_state.source_name": 80,
                        "weather_ingest_state.next_start_dtm": 12,
                        "weather_ingest_state.last_success_start_dtm": 12,
                        "weather_ingest_state.last_success_end_dtm": 12,
                        "weather_ingest_state.source_timezone": 6
                    }'::jsonb,
                NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name IN (
                          'raw_weather_pm1', 'weather_ingest_state'
                      )
                      AND column_default IS NOT NULL
                ),
                (SELECT array_agg(conname::text ORDER BY conname)
                   FROM pg_constraint
                  WHERE conrelid = 'public.raw_weather_pm1'::regclass
                    AND contype IN ('p', 'c')) = ARRAY[
                    'raw_weather_pm1_dtm_check',
                    'raw_weather_pm1_finite_numeric_check',
                    'raw_weather_pm1_pkey',
                    'raw_weather_pm1_station_check'
                ],
                (SELECT bool_and(
                            convalidated
                            AND coalesce(
                                (to_jsonb(pg_constraint)->>'conenforced')::boolean,
                                true
                            )
                            AND CASE conname
                                WHEN 'raw_weather_pm1_pkey' THEN
                                    pg_get_constraintdef(oid) =
                                    'PRIMARY KEY (obsrr_tpcd, obsrt_dtm)'
                                WHEN 'raw_weather_pm1_station_check' THEN
                                    position('0383' IN pg_get_constraintdef(oid)) > 0
                                    AND position(
                                        '강화_숲2' IN pg_get_constraintdef(oid)
                                    ) > 0
                                    AND position('0151' IN pg_get_constraintdef(oid)) > 0
                                    AND position(
                                        '인천_산단' IN pg_get_constraintdef(oid)
                                    ) > 0
                                WHEN 'raw_weather_pm1_dtm_check' THEN
                                    position(
                                        'obsrt_dtm' IN pg_get_constraintdef(oid)
                                    ) > 0
                                    AND position(
                                        '''00''' IN pg_get_constraintdef(oid)
                                    ) > 0
                                WHEN 'raw_weather_pm1_finite_numeric_check' THEN
                                    position('NaN' IN pg_get_constraintdef(oid)) > 0
                                    AND position(
                                        'Infinity' IN pg_get_constraintdef(oid)
                                    ) > 0
                                ELSE false
                            END
                        )
                   FROM pg_constraint
                  WHERE conrelid = 'public.raw_weather_pm1'::regclass
                    AND contype IN ('p', 'c')),
                (SELECT array_agg(conname::text ORDER BY conname)
                   FROM pg_constraint
                  WHERE conrelid = 'public.weather_ingest_state'::regclass
                    AND contype IN ('p', 'c')) = ARRAY[
                    'weather_ingest_state_lag_check',
                    'weather_ingest_state_next_check',
                    'weather_ingest_state_pkey',
                    'weather_ingest_state_schema_check',
                    'weather_ingest_state_success_pair_check',
                    'weather_ingest_state_timezone_check'
                ],
                (SELECT bool_and(
                            convalidated
                            AND coalesce(
                                (to_jsonb(pg_constraint)->>'conenforced')::boolean,
                                true
                            )
                            AND CASE conname
                                WHEN 'weather_ingest_state_pkey' THEN
                                    pg_get_constraintdef(oid) =
                                    'PRIMARY KEY (source_name)'
                                WHEN 'weather_ingest_state_next_check' THEN
                                    position(
                                        'next_start_dtm' IN pg_get_constraintdef(oid)
                                    ) > 0
                                WHEN 'weather_ingest_state_success_pair_check' THEN
                                    position(
                                        'last_success_start_dtm' IN
                                        pg_get_constraintdef(oid)
                                    ) > 0
                                    AND position(
                                        'last_success_end_dtm' IN
                                        pg_get_constraintdef(oid)
                                    ) > 0
                                    AND position(
                                        '^[0-9]{10}00$' IN
                                        pg_get_constraintdef(oid)
                                    ) > 0
                                WHEN 'weather_ingest_state_timezone_check' THEN
                                    position(
                                        'source_timezone' IN pg_get_constraintdef(oid)
                                    ) > 0
                                WHEN 'weather_ingest_state_lag_check' THEN
                                    position(
                                        'sync_lag_hours' IN pg_get_constraintdef(oid)
                                    ) > 0
                                    AND position('>= 0' IN pg_get_constraintdef(oid)) > 0
                                WHEN 'weather_ingest_state_schema_check' THEN
                                    position(
                                        'schema_version' IN pg_get_constraintdef(oid)
                                    ) > 0
                                    AND position('= 1' IN pg_get_constraintdef(oid)) > 0
                                ELSE false
                            END
                        )
                   FROM pg_constraint
                  WHERE conrelid = 'public.weather_ingest_state'::regclass
                    AND contype IN ('p', 'c')),
                to_regclass('public.raw_weather_pm1_dtm_station_idx') IS NOT NULL
                AND to_regclass('public.raw_weather_pm1_observed_at_utc_idx') IS NOT NULL
                AND position(
                    '(obsrt_dtm, obsrr_tpcd)' IN pg_get_indexdef(
                        'public.raw_weather_pm1_dtm_station_idx'::regclass
                    )
                ) > 0
                AND position(
                    '(observed_at_utc)' IN pg_get_indexdef(
                        'public.raw_weather_pm1_observed_at_utc_idx'::regclass
                    )
                ) > 0,
                (SELECT bool_and(
                            pg_get_userbyid(relowner) = 'weather_schema_owner'
                        )
                   FROM pg_class
                  WHERE oid IN (
                    'public.raw_weather_pm1'::regclass,
                    'public.weather_ingest_state'::regclass
                  )),
                EXISTS (
                    SELECT 1
                    FROM pg_roles
                    WHERE rolname = 'weather_schema_owner'
                      AND NOT rolcanlogin
                ),
                NOT EXISTS (
                    SELECT 1
                    FROM pg_namespace AS namespace
                    CROSS JOIN LATERAL aclexplode(
                        coalesce(
                            namespace.nspacl,
                            acldefault('n', namespace.nspowner)
                        )
                    ) AS privilege
                    WHERE namespace.nspname = 'public'
                      AND privilege.grantee = 0
                      AND privilege.privilege_type = 'CREATE'
                ),
                NOT EXISTS (
                    SELECT 1
                    FROM pg_class AS relation
                    CROSS JOIN LATERAL aclexplode(
                        coalesce(
                            relation.relacl,
                            acldefault('r', relation.relowner)
                        )
                    ) AS privilege
                    WHERE relation.oid IN (
                        'public.raw_weather_pm1'::regclass,
                        'public.weather_ingest_state'::regclass
                    )
                      AND privilege.grantee = 0
                )
            """
        )
        checks = cursor.fetchone()
    if checks is None or not all(checks):
        raise RuntimeError("PostgreSQL schema validation failed")
    if (ingest_role is None) != (export_role is None):
        raise ValueError("Both database role names are required for grant validation")
    if ingest_role is None or export_role is None:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                has_schema_privilege(%(ingest)s, 'public', 'USAGE')
                AND NOT has_schema_privilege(%(ingest)s, 'public', 'CREATE'),
                has_table_privilege(
                    %(ingest)s, 'public.raw_weather_pm1', 'SELECT'
                )
                AND has_table_privilege(
                    %(ingest)s, 'public.raw_weather_pm1', 'INSERT'
                )
                AND NOT (
                    has_table_privilege(
                        %(ingest)s, 'public.raw_weather_pm1', 'UPDATE'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.raw_weather_pm1', 'DELETE'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.raw_weather_pm1', 'TRUNCATE'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.raw_weather_pm1', 'REFERENCES'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.raw_weather_pm1', 'TRIGGER'
                    )
                ),
                has_table_privilege(
                    %(ingest)s, 'public.weather_ingest_state', 'SELECT'
                )
                AND has_column_privilege(
                    %(ingest)s, 'public.weather_ingest_state',
                    'next_start_dtm', 'UPDATE'
                )
                AND has_column_privilege(
                    %(ingest)s, 'public.weather_ingest_state',
                    'last_success_start_dtm', 'UPDATE'
                )
                AND has_column_privilege(
                    %(ingest)s, 'public.weather_ingest_state',
                    'last_success_end_dtm', 'UPDATE'
                )
                AND has_column_privilege(
                    %(ingest)s, 'public.weather_ingest_state',
                    'updated_at', 'UPDATE'
                )
                AND NOT has_column_privilege(
                    %(ingest)s, 'public.weather_ingest_state',
                    'source_timezone', 'UPDATE'
                )
                AND NOT has_column_privilege(
                    %(ingest)s, 'public.weather_ingest_state',
                    'sync_lag_hours', 'UPDATE'
                )
                AND NOT has_column_privilege(
                    %(ingest)s, 'public.weather_ingest_state',
                    'schema_version', 'UPDATE'
                )
                AND NOT (
                    has_table_privilege(
                        %(ingest)s, 'public.weather_ingest_state', 'INSERT'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.weather_ingest_state', 'DELETE'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.weather_ingest_state', 'TRUNCATE'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.weather_ingest_state', 'REFERENCES'
                    )
                    OR has_table_privilege(
                        %(ingest)s, 'public.weather_ingest_state', 'TRIGGER'
                    )
                ),
                has_schema_privilege(%(export)s, 'public', 'USAGE')
                AND NOT has_schema_privilege(%(export)s, 'public', 'CREATE'),
                has_table_privilege(
                    %(export)s, 'public.raw_weather_pm1', 'SELECT'
                )
                AND NOT (
                    has_table_privilege(
                        %(export)s, 'public.raw_weather_pm1', 'INSERT'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.raw_weather_pm1', 'UPDATE'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.raw_weather_pm1', 'DELETE'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.raw_weather_pm1', 'TRUNCATE'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.raw_weather_pm1', 'REFERENCES'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.raw_weather_pm1', 'TRIGGER'
                    )
                ),
                NOT (
                    has_table_privilege(
                        %(export)s, 'public.weather_ingest_state', 'SELECT'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.weather_ingest_state', 'INSERT'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.weather_ingest_state', 'UPDATE'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.weather_ingest_state', 'DELETE'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.weather_ingest_state', 'TRUNCATE'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.weather_ingest_state', 'REFERENCES'
                    )
                    OR has_table_privilege(
                        %(export)s, 'public.weather_ingest_state', 'TRIGGER'
                    )
                )
            """,
            {"ingest": ingest_role, "export": export_role},
        )
        role_checks = cursor.fetchone()
    if role_checks is None or not all(role_checks):
        raise RuntimeError("PostgreSQL role grant validation failed")


def acquire_source_lock(connection: psycopg.Connection[Any]) -> bool:
    """동일 API의 중복 수집을 막는 PostgreSQL 세션 잠금을 시도한다."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", (1400377, 1))
        row = cursor.fetchone()
    return bool(row and row[0])


def _state_from_row(row: Sequence[Any] | None) -> IngestState:
    """DB 조회 결과를 검증해 수집 상태 객체로 변환한다."""
    if row is None:
        raise RuntimeError("PM1 ingest state has not been initialized")
    return IngestState(
        next_start_dtm=row[0],
        last_success_start_dtm=row[1],
        last_success_end_dtm=row[2],
        source_timezone=row[3],
        sync_lag_hours=row[4],
        schema_version=row[5],
    )


def read_ingest_state(connection: psycopg.Connection[Any]) -> IngestState:
    """현재 PM1 수집 체크포인트와 시간 설정을 읽는다."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT next_start_dtm, last_success_start_dtm,
                   last_success_end_dtm, source_timezone,
                   sync_lag_hours, schema_version
            FROM public.weather_ingest_state
            WHERE source_name = %s
            """,
            (SOURCE_NAME,),
        )
        return _state_from_row(cursor.fetchone())


def _measurement_values(row: MeasurementRow) -> tuple[Any, ...]:
    """관측값 객체를 INSERT와 동일한 컬럼 순서의 튜플로 바꾼다."""
    return (
        row.obsrr_tpcd,
        row.obsrr_nm,
        row.obsrt_dtm,
        row.observed_at_utc,
        row.obsrt_tmprt,
        row.obsrt_hmdt,
        row.obsrt_wndrc_val,
        row.obsrt_ws,
        row.obsrt_pm01_val,
        row.obsrt_pm25_val,
        row.obsrt_pm10_val,
        row.avoc_obsrt_pm01_val,
        row.avoc_obsrt_pm25_val,
        row.avoc_obsrt_pm10_val,
    )


def commit_hour(
    connection: psycopg.Connection[Any],
    expected_start_dtm: str,
    window: HourWindow,
    rows: Sequence[MeasurementRow],
    ingest_run_id: UUID,
    collector_version: str,
) -> CommitResult:
    """정각 한 시간의 데이터 저장과 체크포인트 이동을 원자적으로 처리한다."""
    if window.start_dtm != expected_start_dtm:
        raise ValueError("Window start does not match the expected checkpoint")
    if window.end_dtm != window.start_dtm:
        raise ValueError("Hour window must request one exact HH00")
    try:
        next_start_dtm = (
            datetime.strptime(window.end_dtm, "%Y%m%d%H%M") + timedelta(hours=1)
        ).strftime("%Y%m%d%H%M")
    except ValueError as error:
        raise ValueError("Hour window has an invalid end datetime") from error

    inserted = 0
    already_present = 0
    with connection.transaction():
        with connection.cursor() as cursor:
            # API를 조회하는 동안 다른 작업이 먼저 저장했는지 확인하고, 현재
            # 체크포인트 행을 잠가 아래 INSERT와 갱신이 끝날 때까지 보호한다.
            cursor.execute(
                """
                SELECT next_start_dtm, last_success_start_dtm,
                       last_success_end_dtm, source_timezone,
                       sync_lag_hours, schema_version
                FROM public.weather_ingest_state
                WHERE source_name = %s
                FOR UPDATE
                """,
                (SOURCE_NAME,),
            )
            state = _state_from_row(cursor.fetchone())
            if state.next_start_dtm != expected_start_dtm:
                raise CheckpointConflictError(
                    "Persisted checkpoint changed while the hour was being fetched"
                )

            for row in rows:
                values = _measurement_values(row)
                cursor.execute(
                    """
                    INSERT INTO public.raw_weather_pm1 (
                        obsrr_tpcd, obsrr_nm, obsrt_dtm, observed_at_utc,
                        obsrt_tmprt, obsrt_hmdt, obsrt_wndrc_val, obsrt_ws,
                        obsrt_pm01_val, obsrt_pm25_val, obsrt_pm10_val,
                        avoc_obsrt_pm01_val, avoc_obsrt_pm25_val,
                        avoc_obsrt_pm10_val, ingest_run_id, collector_version,
                        ingested_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (obsrr_tpcd, obsrt_dtm) DO NOTHING
                    RETURNING obsrr_tpcd
                    """,
                    (*values, ingest_run_id, collector_version),
                )
                if cursor.fetchone() is not None:
                    inserted += 1
                    continue

                # 재실행으로 같은 기본키가 이미 있다면 단순히 성공 처리하지 않고
                # 모든 원본 값이 같은지 확인한다. 값이 다르면 조용한 데이터 변경을
                # 막기 위해 시간 전체를 롤백한다.
                cursor.execute(
                    """
                    SELECT obsrr_tpcd, obsrr_nm, obsrt_dtm, observed_at_utc,
                           obsrt_tmprt, obsrt_hmdt, obsrt_wndrc_val, obsrt_ws,
                           obsrt_pm01_val, obsrt_pm25_val, obsrt_pm10_val,
                           avoc_obsrt_pm01_val, avoc_obsrt_pm25_val,
                           avoc_obsrt_pm10_val
                    FROM public.raw_weather_pm1
                    WHERE obsrr_tpcd = %s AND obsrt_dtm = %s
                    """,
                    (row.obsrr_tpcd, row.obsrt_dtm),
                )
                existing = cursor.fetchone()
                if existing is None or tuple(existing) != values:
                    raise DataConflictError(
                        "Existing observation differs for "
                        f"{row.obsrr_tpcd} {row.obsrt_dtm}"
                    )
                already_present += 1

            # 관측값과 체크포인트를 같은 트랜잭션에서 갱신해야 실패 후 재시작 시
            # 빠진 시간 없이 정확히 해당 시각부터 다시 수집할 수 있다.
            cursor.execute(
                """
                UPDATE public.weather_ingest_state
                SET next_start_dtm = %s,
                    last_success_start_dtm = %s,
                    last_success_end_dtm = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE source_name = %s AND next_start_dtm = %s
                """,
                (
                    next_start_dtm,
                    window.start_dtm,
                    window.end_dtm,
                    SOURCE_NAME,
                    expected_start_dtm,
                ),
            )
            if cursor.rowcount != 1:
                raise CheckpointConflictError("Checkpoint update affected no state row")
    return CommitResult(inserted=inserted, already_present=already_present)


def export_csv(connection: psycopg.Connection[Any], output_path: Path) -> int:
    """검증하고 정렬한 DB 스냅샷을 CSV 파일로 원자적으로 내보낸다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        # 최종 파일과 같은 폴더에 임시 파일을 만들어 마지막 os.replace가 같은
        # 파일시스템 안에서 원자적으로 수행되도록 한다.
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            with connection.transaction():
                with connection.cursor() as cursor:
                    # 행 수 검증과 COPY가 동일한 시점의 데이터를 보도록 읽기 전용
                    # REPEATABLE READ 스냅샷을 사용한다.
                    cursor.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
                    )
                    cursor.execute(
                        """
                        SELECT count(*) FILTER (
                                   WHERE NOT (
                                       (obsrr_tpcd = '0383' AND obsrr_nm = '강화_숲2')
                                       OR (obsrr_tpcd = '0151' AND obsrr_nm = '인천_산단')
                                   )
                                   OR obsrt_dtm !~ '^[0-9]{12}$'
                                   OR substring(obsrt_dtm FROM 11 FOR 2)
                                      <> '00'
                                   OR obsrr_tpcd ~ '^[=+@-]'
                                   OR obsrr_nm ~ '^[=+@-]'
                                   OR obsrt_dtm ~ '^[=+@-]'
                                   OR obsrt_tmprt::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR obsrt_hmdt::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR obsrt_wndrc_val::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR obsrt_ws::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR obsrt_pm01_val::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR obsrt_pm25_val::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR obsrt_pm10_val::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR avoc_obsrt_pm01_val::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR avoc_obsrt_pm25_val::text IN ('NaN', 'Infinity', '-Infinity')
                                   OR avoc_obsrt_pm10_val::text IN ('NaN', 'Infinity', '-Infinity')
                               ),
                               count(*)
                        FROM public.raw_weather_pm1
                        """
                    )
                    validation = cursor.fetchone()
                    if validation is None:
                        raise RuntimeError("CSV export validation returned no result")
                    invalid_count, row_count = validation
                    if invalid_count:
                        raise RuntimeError(
                            "CSV export rejected invalid station, datetime, or text data"
                        )
                    copy_sql = """
                        COPY (
                            SELECT obsrr_tpcd, obsrr_nm, obsrt_dtm,
                                   obsrt_tmprt, obsrt_hmdt, obsrt_wndrc_val,
                                   obsrt_ws, obsrt_pm01_val, obsrt_pm25_val,
                                   obsrt_pm10_val, avoc_obsrt_pm01_val,
                                   avoc_obsrt_pm25_val, avoc_obsrt_pm10_val
                            FROM public.raw_weather_pm1
                            ORDER BY obsrt_dtm, obsrr_tpcd
                        ) TO STDOUT WITH (FORMAT CSV, HEADER TRUE, NULL '')
                    """
                    with cursor.copy(copy_sql) as copy:
                        # COPY 스트림을 사용해 전체 결과를 메모리에 올리지 않는다.
                        for block in copy:
                            output.write(bytes(block))
            output.flush()
            # 교체 전에 디스크 기록을 완료해 프로세스 장애 시 손상된 최종 파일이
            # 남을 가능성을 줄인다.
            os.fsync(output.fileno())
        os.replace(temporary_path, output_path)
        return int(row_count)
    except Exception:
        # 실패하면 기존 최종 CSV는 그대로 두고 미완성 임시 파일만 제거한다.
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
