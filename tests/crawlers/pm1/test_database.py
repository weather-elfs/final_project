from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from src.crawlers.pm1.crawler import HourWindow, MeasurementRow
from src.crawlers.pm1.database import (
    SCHEMA_PATH,
    CheckpointConflictError,
    DataConflictError,
    acquire_source_lock,
    commit_hour,
    export_csv,
    initialize_schema,
    load_database_config,
    read_ingest_state,
    validate_schema,
)

BASE_ENV = {
    "DB_HOST": "db.example.internal",
    "DB_PORT": "5432",
    "DB_NAME": "weather_db",
    "DB_SSLROOTCERT": "certs/root.crt",
}


class FakeTransaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> "FakeTransaction":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.committed = exc_type is None
        self.rolled_back = exc_type is not None


class FakeCopy:
    def __init__(self, blocks: list[bytes | Exception]) -> None:
        self.blocks = blocks

    def __enter__(self) -> "FakeCopy":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def __iter__(self):
        for block in self.blocks:
            if isinstance(block, Exception):
                raise block
            yield block


class FakeCursor:
    def __init__(
        self, fetch_results: list[object], copy_blocks: list[bytes | Exception]
    ) -> None:
        self.fetch_results = fetch_results
        self.copy_blocks = copy_blocks
        self.executed: list[tuple[object, object]] = []
        self.rowcount = 1

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def execute(self, query: object, params: object = None) -> None:
        self.executed.append((query, params))

    def fetchone(self) -> object:
        return self.fetch_results.pop(0)

    def copy(self, query: object) -> FakeCopy:
        self.executed.append((query, None))
        return FakeCopy(self.copy_blocks)


class FakeConnection:
    def __init__(
        self,
        fetch_results: list[object],
        copy_blocks: list[bytes | Exception] | None = None,
    ) -> None:
        self.cursor_value = FakeCursor(fetch_results, copy_blocks or [])
        self.transactions: list[FakeTransaction] = []

    def cursor(self) -> FakeCursor:
        return self.cursor_value

    def transaction(self) -> FakeTransaction:
        transaction = FakeTransaction()
        self.transactions.append(transaction)
        return transaction


def sample_row() -> MeasurementRow:
    return MeasurementRow(
        obsrr_tpcd="0383",
        obsrr_nm="강화_숲2",
        obsrt_dtm="202309180000",
        observed_at_utc=datetime(2023, 9, 17, 15, tzinfo=UTC),
        obsrt_tmprt=None,
        obsrt_hmdt=None,
        obsrt_wndrc_val=None,
        obsrt_ws=None,
        obsrt_pm01_val=None,
        obsrt_pm25_val=None,
        obsrt_pm10_val=None,
        avoc_obsrt_pm01_val=None,
        avoc_obsrt_pm25_val=None,
        avoc_obsrt_pm10_val=None,
    )


def test_load_database_config_requires_role_specific_credentials() -> None:
    with pytest.raises(ValueError, match="DB_INGEST_USER"):
        load_database_config("ingest", BASE_ENV)


def test_database_config_forces_verified_tls_inputs() -> None:
    env = {
        **BASE_ENV,
        "DB_INGEST_USER": "pm1_ingest",
        "DB_INGEST_PASSWORD": "secret-sentinel",
    }

    config = load_database_config("ingest", env)

    assert config.host == "db.example.internal"
    assert config.port == 5432
    assert config.sslrootcert == Path("certs/root.crt")
    assert config.connect_kwargs()["sslmode"] == "verify-full"
    assert config.connect_kwargs()["channel_binding"] == "require"
    assert config.connect_kwargs()["gssencmode"] == "disable"


def test_database_config_allows_ssh_tunnel_only_on_localhost() -> None:
    env = {
        **BASE_ENV,
        "DB_HOST": "localhost",
        "DB_CONNECTION_MODE": "ssh-tunnel",
        "DB_INGEST_USER": "pm1_ingest",
        "DB_INGEST_PASSWORD": "secret-sentinel",
    }
    env.pop("DB_SSLROOTCERT")

    config = load_database_config("ingest", env)

    assert config.connect_kwargs()["sslmode"] == "disable"
    assert "sslrootcert" not in config.connect_kwargs()
    assert "channel_binding" not in config.connect_kwargs()


@pytest.mark.parametrize("host", ["db.example.internal", "192.0.2.4"])
def test_database_config_rejects_ssh_tunnel_on_non_loopback(host: str) -> None:
    env = {
        **BASE_ENV,
        "DB_HOST": host,
        "DB_CONNECTION_MODE": "ssh-tunnel",
        "DB_INGEST_USER": "pm1_ingest",
        "DB_INGEST_PASSWORD": "secret-sentinel",
    }

    with pytest.raises(ValueError, match="loopback"):
        load_database_config("ingest", env)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "192.0.2.4"])
def test_database_config_rejects_ip_host(host: str) -> None:
    env = {
        **BASE_ENV,
        "DB_HOST": host,
        "DB_EXPORT_USER": "pm1_export",
        "DB_EXPORT_PASSWORD": "secret-sentinel",
    }

    with pytest.raises(ValueError) as error:
        load_database_config("export", env)

    assert "secret-sentinel" not in str(error.value)


def test_database_config_rejects_missing_ca_without_leaking_password() -> None:
    env = {
        **BASE_ENV,
        "DB_SSLROOTCERT": "",
        "DB_MIGRATION_USER": "pm1_owner",
        "DB_MIGRATION_PASSWORD": "secret-sentinel",
    }

    with pytest.raises(ValueError) as error:
        load_database_config("migration", env)

    assert "secret-sentinel" not in str(error.value)


def test_schema_is_non_destructive_and_idempotent() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8").upper()

    assert "DROP " not in sql
    assert "TRUNCATE " not in sql
    assert "CREATE OR REPLACE" not in sql
    assert " DEFAULT " not in sql
    assert sql.count("CREATE TABLE IF NOT EXISTS") == 2
    assert sql.count("CREATE INDEX IF NOT EXISTS") == 2


def test_schema_enforces_station_mapping_and_hour_boundary() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "obsrr_tpcd = '0383' AND obsrr_nm = '강화_숲2'" in sql
    assert "obsrr_tpcd = '0151' AND obsrr_nm = '인천_산단'" in sql
    assert "substring(obsrt_dtm FROM 11 FOR 2) = '00'" in sql
    assert "raw_weather_pm1_finite_numeric_check" in sql
    assert "NOT IN ('NaN', 'Infinity', '-Infinity')" in sql


def test_schema_restricts_public_and_defines_checkpoint_invariants() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "REVOKE ALL ON public.raw_weather_pm1 FROM PUBLIC" in sql
    assert "REVOKE ALL ON public.weather_ingest_state FROM PUBLIC" in sql
    assert "last_success_start_dtm IS NULL AND last_success_end_dtm IS NULL" in sql
    assert "schema_version = 1" in sql


def test_initialize_schema_is_repeatable_and_records_time_contract() -> None:
    connection = FakeConnection([("pm1_dust_data",), ("pm1_dust_data",)])

    initialize_schema(connection, "+09:00", 1, "pm1_ingest", "pm1_export")
    initialize_schema(connection, "+09:00", 1, "pm1_ingest", "pm1_export")

    assert all(transaction.committed for transaction in connection.transactions)
    params = [params for _, params in connection.cursor_value.executed]
    assert ("pm1_dust_data", "202103290000", "+09:00", 1) in params


def test_validate_schema_rejects_failed_catalog_postcondition() -> None:
    connection = FakeConnection([(True, True, False, True, True, True)])

    with pytest.raises(RuntimeError, match="schema validation"):
        validate_schema(connection)


def test_acquire_source_lock_returns_database_result() -> None:
    connection = FakeConnection([(True,)])

    assert acquire_source_lock(connection) is True


def test_read_ingest_state_maps_persisted_configuration() -> None:
    connection = FakeConnection([("202103290000", None, None, "+09:00", 1, 1)])

    state = read_ingest_state(connection)

    assert state.next_start_dtm == "202103290000"
    assert state.source_timezone == "+09:00"
    assert state.sync_lag_hours == 1


def test_commit_hour_inserts_and_advances_checkpoint_atomically() -> None:
    connection = FakeConnection(
        [
            ("202309180000", None, None, "+09:00", 1, 1),
            ("0383",),
        ]
    )

    result = commit_hour(
        connection,
        "202309180000",
        HourWindow("202309180000", "202309180000"),
        [sample_row()],
        UUID("00000000-0000-0000-0000-000000000001"),
        "test-version",
    )

    assert result.inserted == 1
    assert result.already_present == 0
    assert connection.transactions[0].committed is True


def test_commit_hour_rejects_stale_checkpoint_and_rolls_back() -> None:
    connection = FakeConnection(
        [("202309180100", "202309180000", "202309180000", "+09:00", 1, 1)]
    )

    with pytest.raises(CheckpointConflictError):
        commit_hour(
            connection,
            "202309180000",
            HourWindow("202309180000", "202309180000"),
            [],
            UUID("00000000-0000-0000-0000-000000000001"),
            "test-version",
        )

    assert connection.transactions[0].rolled_back is True


def test_commit_hour_rejects_same_key_with_different_values() -> None:
    row = sample_row()
    existing_values = list(row.__dict__.values())
    existing_values[4] = 99
    connection = FakeConnection(
        [
            ("202309180000", None, None, "+09:00", 1, 1),
            None,
            tuple(existing_values),
        ]
    )

    with pytest.raises(DataConflictError):
        commit_hour(
            connection,
            "202309180000",
            HourWindow("202309180000", "202309180000"),
            [row],
            UUID("00000000-0000-0000-0000-000000000001"),
            "test-version",
        )

    assert connection.transactions[0].rolled_back is True


def test_export_csv_streams_and_atomically_replaces_existing_file(
    tmp_path: Path,
) -> None:
    output = tmp_path / "pm1_measurements.csv"
    output.write_text("old", encoding="utf-8")
    header = (
        b"obsrr_tpcd,obsrr_nm,obsrt_dtm,obsrt_tmprt,obsrt_hmdt,"
        b"obsrt_wndrc_val,obsrt_ws,obsrt_pm01_val,obsrt_pm25_val,"
        b"obsrt_pm10_val,avoc_obsrt_pm01_val,avoc_obsrt_pm25_val,"
        b"avoc_obsrt_pm10_val\n"
    )
    connection = FakeConnection(
        [(0, 1)], [header, b"0383,ganghwa,202309180000,,,,,,,,,,\n"]
    )

    count = export_csv(connection, output)

    assert count == 1
    assert output.read_bytes().startswith(header)
    assert connection.transactions[0].committed is True


def test_export_csv_failure_preserves_existing_file(tmp_path: Path) -> None:
    output = tmp_path / "pm1_measurements.csv"
    output.write_text("old", encoding="utf-8")
    connection = FakeConnection([(0, 1)], [b"header\n", OSError("disk full")])

    with pytest.raises(OSError, match="disk full"):
        export_csv(connection, output)

    assert output.read_text(encoding="utf-8") == "old"
