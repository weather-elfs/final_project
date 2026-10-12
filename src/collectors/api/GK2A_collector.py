# -*- coding: utf-8 -*-
# =============================================================================
# GK2A 실시간 수집·처리 통합 파일
#
# 먼저 확인할 것
# 1. 기준 Parquet 파일은 ZIP에 미포함. 실행 전 별도 준비 필요.
#    기본 안내 파일명: GK2A_FOG_APPS_ROI_202206230000_202506232300.parquet

# 2. Python 3.10 이상 및 numpy, h5py, pyarrow, pandas, duckdb, tqdm 설치 필요.
#    PyArrow의 write_page_checksum 및 ParquetWriter.add_key_value_metadata 지원 필요.

# 3. API 수집에는 KMA_AUTH_KEY 또는 KMA_API_KEY 환경변수 설정 필요.
#    인증키 직접 기재 및 로그 기록 금지. --process-only 실행에는 키 불필요.

# 4. 원본(raw), 상태(state), 처리 결과(processed), 기준 파일, 최종 파일 경로 분리 필요.
#
# 권장 실행 순서 (Windows PowerShell)
# 아래 경로는 예시. 기준 Parquet 실제 위치 확인 후 $base 수정.
#
#   $root = Join-Path $env:USERPROFILE "GK2A_Realtime"
#   $base = Join-Path $root "baseline\GK2A_FOG_APPS_ROI_202206230000_202506232300.parquet"
#   $raw = Join-Path $root "raw"
#   $state = Join-Path $root "state"
#   $processed = Join-Path $root "processed"
#   $final = Join-Path $processed "GK2A_FOG_APPS_ROI_current.parquet"
#   Test-Path $base
#
#   1) 수집 대상과 저장 경로 확인 (API 호출·인증키 입력 없음)
#   python .\GK2A_실시간_수집처리_통합본.py --base-parquet "$base" --output-dir "$raw" --state-dir "$state" --processed-root "$processed" --final-parquet "$final" --dry-run
#
#   2) 인증키를 화면에 보이지 않게 설정
#   $env:KMA_AUTH_KEY = [System.Net.NetworkCredential]::new("", (Read-Host "기상청 APIHub 인증키" -AsSecureString)).Password
#
#   3) 수집부터 최신 전체기간 Parquet 갱신까지 1회 실행
#   python .\GK2A_실시간_수집처리_통합본.py --base-parquet "$base" --output-dir "$raw" --state-dir "$state" --processed-root "$processed" --final-parquet "$final"
#
#   기존 원본 처리 옵션: --process-only --start YYYYMMDDHH00 --end YYYYMMDDHH00 추가.
#   시작·종료는 UTC 정시 기준. --start/--end와 --loop 동시 지정 불가.
#   최종 확인 대상: $final 파일 및 실행 로그.
#
# 처리 범위와 주요 가정
# - FOG/APPS 제품의 KO 영역 대상 UTC 정시 단위 수집. 전체 2분·10분 자료 수집용이 아님.
# - 기본 수집 범위: 최근 정시 3개 재조회. 20분 생성 지연은 운영 가정이며 제공 보장 아님.
# - ROI 범위: KO 격자 y=440..508, x=381..487.
# - 기준 파일 보존 및 별도 최종 파일 갱신. 예상과 다른 구조·격자 발견 시 처리 중단.
# - 실행용 운영 코드 통합본. 원본 ZIP 미수정.
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.client import HTTPException, HTTPResponse
from pathlib import Path
from typing import Iterator, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
  import duckdb
  import h5py
  import numpy as np
  import pandas as pd
  import pyarrow as pa
  import pyarrow.compute as pc
  import pyarrow.parquet as pq
  from tqdm import tqdm
except ImportError as error:
  raise SystemExit(
    "필수 패키지 확인 필요: numpy, h5py, pyarrow, pandas, duckdb, tqdm"
  ) from error

LOGGER = logging.getLogger("gk2a_integrated")


# =============================================================================
# 수집기
# =============================================================================

COLLECTOR_VERSION = "gk2a-realtime-v1"
BYTES_PER_GB = 1_000_000_000
READ_CHUNK_BYTES = 1024 * 1024
POLL_WAIT_SECONDS = 30
MAX_BACKOFF_SECONDS = 30
API_BASE = "https://apihub.kma.go.kr/api/typ05/api/GK2A/LE2"
PRODUCTS = ("FOG", "APPS")
AREA = "KO"
UTC = timezone.utc
KST = timezone(timedelta(hours=9))
NETCDF_SIGNATURES = (b"\x89HDF\r\n\x1a\n", b"CDF\x01", b"CDF\x02", b"CDF\x05")


class CollectionStop(Exception):
  """인증/한도 문제는 나머지 호출도 중단."""


def now_utc() -> datetime:
  """현재 UTC 시각을 시간대 정보와 함께 반환."""
  return datetime.now(UTC)


def parse_utc(value: str) -> datetime:
  """사용자 지정 UTC 정시 문자열 검증."""
  dt = datetime.strptime(value, "%Y%m%d%H%M").replace(tzinfo=UTC)
  if len(value) != 12 or dt.minute != 0:
    raise ValueError("시각은 YYYYMMDDHH00 형식의 UTC 정시여야 합니다.")
  return dt


def observation_slots(
  now: datetime, lookback_hours: int, lag_minutes: int
) -> list[datetime]:
  """지연 대기를 반영한 최근 정시 슬롯의 시간순 반환."""
  # [필수 확인] 서버 시간대와 무관하게 UTC 처리. 최근 N개 정시를 양 끝 포함.
  end = (now.astimezone(UTC) - timedelta(minutes=lag_minutes)).replace(
    minute=0, second=0, microsecond=0
  )
  return [end - timedelta(hours=i) for i in reversed(range(lookback_hours))]


def target_path(root: Path, product: str, obs: datetime) -> Path:
  """기존 수집기 호환 원본 파일 경로 반환."""
  stamp = obs.strftime("%Y%m%d%H%M")
  return root / product / AREA / stamp[:4] / stamp[4:6] / (
    f"gk2a_ami_le2_{product.lower()}_{AREA.lower()}_{stamp}.nc"
  )


def has_netcdf_signature(path: Path) -> bool:
  """파일 앞부분의 NetCDF/HDF 시그니처 확인."""
  # [필수 확인] NetCDF를 열거나 픽셀을 해독하지 않음. 완전성/과학적 타당성 보장 아님.
  with path.open("rb") as stream:
    return stream.read(8).startswith(NETCDF_SIGNATURES)


@contextmanager
def single_instance(root: Path) -> Iterator[None]:
  """동일 운영 원장을 사용하는 동시 실행 방지."""
  # ponytail: 같은 저장 폴더 1프로세스. 여러 호스트의 공유 폴더에는 별도 조율 필요.
  lock = root / "collector.lock"
  fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
  try:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
      stream.write(str(os.getpid()))
    yield
  finally:
    lock.unlink(missing_ok=True)


def open_ledger(root: Path) -> sqlite3.Connection:
  """운영 상태 폴더 내 SQLite 수집 원장 연결."""
  db = sqlite3.connect(root / "gk2a_collection.sqlite3")
  db.executescript("""
        CREATE TABLE IF NOT EXISTS usage (
            date_kst TEXT PRIMARY KEY, calls INTEGER NOT NULL,
            body_bytes INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files (
            product TEXT, area TEXT, obs_time_utc TEXT, obs_time_kst TEXT,
            status TEXT, attempts INTEGER NOT NULL DEFAULT 0, http_status INTEGER,
            file_path TEXT, size_bytes INTEGER, received_at_utc TEXT,
            checked_at_utc TEXT, detail TEXT, source_url TEXT, dataset_id TEXT,
            collector_version TEXT, run_id INTEGER,
            PRIMARY KEY (product, area, obs_time_utc)
        );
        CREATE TABLE IF NOT EXISTS runs (
            run_id INTEGER PRIMARY KEY, started_at_utc TEXT, ended_at_utc TEXT,
            first_obs_utc TEXT, last_obs_utc TEXT, settings_json TEXT, exit_code INTEGER
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
  return db


def start_run(
  db: sqlite3.Connection, root: Path, args: argparse.Namespace
) -> int:
  """실행 버전·대상·설정 기록 및 다른 원본 폴더의 원장 재사용 방지."""
  saved = db.execute("SELECT value FROM settings WHERE key='raw_root'").fetchone()
  if saved is not None and saved[0] != str(root):
    raise ValueError("다른 원본 저장 폴더에 연결된 원장입니다.")
  settings = {
    "source": API_BASE,
    "dataset": "GK2A_LE2",
    "collector_version": COLLECTOR_VERSION,
    "products": PRODUCTS,
    "area": AREA,
    "raw_root": str(root),
    "interval_minutes": args.interval_minutes,
    "lookback_hours": args.lookback_hours,
    "lag_minutes": args.lag_minutes,
    "max_calls": args.max_calls,
    "max_bytes": args.max_bytes,
    "retries": args.retries,
    "request_gap": args.request_gap,
    "timeout": args.timeout,
    "loop": args.loop,
    "start_utc": args.start,
    "end_utc": args.end,
    "preprocessing": "ROI -> monthly -> final incremental" if args.base_parquet else "none",
    "validation": "raw signature/length; ROI/schema/sorted final" if args.base_parquet
           else "signature and available Content-Length only",
    "base_parquet": str(args.base_parquet.resolve()) if args.base_parquet else None,
    "final_parquet": str(args.final_parquet.resolve()) if args.base_parquet else None,
    "processed_root": str(args.processed_root.resolve()) if args.base_parquet else None,
    "process_only": args.process_only,
  }
  with db:
    db.execute(
      "INSERT OR IGNORE INTO settings VALUES ('raw_root', ?)",
      (str(root),)
    )
    cursor = db.execute(
      "INSERT INTO runs (started_at_utc, settings_json) VALUES (?, ?)",
      (now_utc().isoformat(), json.dumps(settings, ensure_ascii=False)),
    )
  if cursor.lastrowid is None:
    raise RuntimeError("실행 계보 기록 실패")
  return cursor.lastrowid


def record_file(
  db: sqlite3.Connection, product: str, obs: datetime, path: Path,
  status: str, detail: str = "", http: int | None = None, attempted: bool = False
) -> None:
  """파일별 최신 수집 상태 및 요청 시도 수 기록."""
  checked = now_utc().isoformat()
  size = path.stat().st_size if path.exists() else None
  received = checked if status == "SUCCESS" else None
  run_id = db.execute("SELECT MAX(run_id) FROM runs").fetchone()[0]
  with db:
    db.execute("""
            INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product, area, obs_time_utc) DO UPDATE SET
                status=excluded.status, attempts=files.attempts+excluded.attempts,
                http_status=excluded.http_status, file_path=excluded.file_path,
                size_bytes=excluded.size_bytes,
                received_at_utc=COALESCE(
                    excluded.received_at_utc, files.received_at_utc
                ),
                checked_at_utc=excluded.checked_at_utc, detail=excluded.detail,
                source_url=excluded.source_url, dataset_id=excluded.dataset_id,
                collector_version=excluded.collector_version, run_id=excluded.run_id
        """, (product, AREA, obs.isoformat(), obs.astimezone(KST).isoformat(),
       status, int(attempted), http, str(path), size, received, checked, detail,
       f"{API_BASE}/{product}/{AREA}/data", f"GK2A_LE2_{product}_{AREA}",
       COLLECTOR_VERSION, run_id))


def usage(db: sqlite3.Connection) -> tuple[str, int, int]:
  """현재 KST 날짜의 호출 수 및 본문 수신량 반환."""
  day = now_utc().astimezone(KST).date().isoformat()
  with db:
    db.execute("INSERT OR IGNORE INTO usage VALUES (?, 0, 0)", (day,))
  calls, body_bytes = db.execute(
    "SELECT calls, body_bytes FROM usage WHERE date_kst=?", (day,)
  ).fetchone()
  return day, calls, body_bytes


def add_usage(
  db: sqlite3.Connection, calls: int = 0, body_bytes: int = 0
) -> None:
  """현재 날짜 운영 예산 집계에 사용량 추가."""
  day, _, _ = usage(db)
  with db:
    db.execute("UPDATE usage SET calls=calls+?, body_bytes=body_bytes+? WHERE date_kst=?",
         (calls, body_bytes, day))


def save_response(
  response: HTTPResponse, part: Path, db: sqlite3.Connection, max_bytes: int
) -> str | None:
  """원본 응답 임시 저장 및 전송 길이·시그니처 오류 사유 반환."""
  length = response.headers.get("Content-Length")
  expected = int(length) if length is not None else None
  if expected is not None and expected < 0:
    raise ValueError("Content-Length 오류")
  _, _, used = usage(db)
  if expected is not None and expected > max_bytes - used:
    raise CollectionStop("남은 본문 수신 예산보다 파일이 큼")
  downloaded = 0
  with part.open("wb") as stream:
    while True:
      chunk = response.read(READ_CHUNK_BYTES)
      if not chunk:
        break
      # 중단 파일에서 이미 읽은 본문 바이트도 사용량에 포함해 과소 집계 방지.
      add_usage(db, body_bytes=len(chunk))
      _, _, used = usage(db)
      if used > max_bytes:
        raise CollectionStop("본문 수신 예산 초과")
      stream.write(chunk)
      downloaded += len(chunk)
    stream.flush()
    os.fsync(stream.fileno())
  if expected is not None and downloaded != expected:
    return "Content-Length 불일치"
  if not has_netcdf_signature(part):
    return "NetCDF 시그니처 불일치"
  return None


def download_one(
  db: sqlite3.Connection, root: Path, product: str, obs: datetime,
  key: str, args: argparse.Namespace
) -> str:
  """원본 파일 검증·저장 또는 명시적 실패 상태 반환."""
  path = target_path(root, product, obs)
  if path.exists():
    saved = db.execute(
      "SELECT size_bytes, status FROM files "
      "WHERE product=? AND area=? AND obs_time_utc=?",
      (product, AREA, obs.isoformat())
    ).fetchone()
    size_matches = saved is None or (saved[1] != "EXISTING_INVALID" and (
      saved[0] is None or saved[0] == path.stat().st_size
    ))
    if has_netcdf_signature(path) and size_matches:
      record_file(db, product, obs, path, "SKIPPED_EXISTING", "SIGNATURE_ONLY")
      return "SKIPPED_EXISTING"
    # [필수 확인] 기존 손상 의심 파일도 자동 덮어쓰지 않음. 검토 후 별도 이동 필요.
    record_file(db, product, obs, path, "EXISTING_INVALID", "기존 파일 확인 필요")
    return "EXISTING_INVALID"

  path.parent.mkdir(parents=True, exist_ok=True)
  part = path.with_suffix(".nc.part")
  params = urlencode({"date": obs.strftime("%Y%m%d%H%M"), "authKey": key})
  request = Request(f"{API_BASE}/{product}/{AREA}/data?{params}",
           headers={"User-Agent": "GK2A-Realtime-Collector/1.0",
               "Accept-Encoding": "identity"})
  # [필수 확인] dataList 미사용. 실사용 수집기와 같은 정시 /data 직접 요청 방식.
  for attempt in range(args.retries + 1):
    part.unlink(missing_ok=True)
    status, detail, http = "FAILED", "", None
    stop = False
    try:
      _, calls, body_bytes = usage(db)
      if calls >= args.max_calls or body_bytes >= args.max_bytes:
        status, stop = "QUOTA_STOP", True
        raise CollectionStop("로컬 일일 수집 예산 도달")
      # 재시도·실패도 호출 1회로 집계. 요청 전에 기록하여 강제종료 시 과소 집계 완화.
      add_usage(db, calls=1)
      record_file(db, product, obs, path, "DOWNLOADING", attempted=True)
      time.sleep(args.request_gap)
      with urlopen(request, timeout=args.timeout) as response:
        http = response.status
        if http == 204:
          status, detail = "UNAVAILABLE", "HTTP 204; 영구 누락 확정 아님"
        elif http != 200:
          status, detail = "HTTP_ERROR", f"HTTP {http}"
        else:
          reason = save_response(response, part, db, args.max_bytes)
          if reason:
            status, detail = "INVALID_DOWNLOAD", reason
          else:
            # Raw 원본 바이트 보존. 픽셀 품질 변환은 후속 단계.
            os.replace(part, path)
            record_file(
              db,
              product,
              obs,
              path,
              "SUCCESS",
              "SIGNATURE_ONLY",
              http
            )
            return "SUCCESS"
    except HTTPError as err:
      http = err.code
      err.close()
      if http == 404:
        status, detail = "UNAVAILABLE", "HTTP 404; 영구 누락 확정 아님"
      elif http in (401, 403):
        status, detail, stop = "AUTH_STOP", f"HTTP {http}; 권한/제한 확인", True
      else:
        status, detail = "HTTP_ERROR", f"HTTP {http}"
    except CollectionStop as err:
      status, detail, stop = "QUOTA_STOP", str(err), True
    except (
      URLError,
      TimeoutError,
      ConnectionError,
      HTTPException,
      ValueError
    ) as err:
      # [필수 확인] 예외 원문·응답 본문·전체 요청 URL 출력 금지(authKey 노출 방지).
      detail = type(err).__name__
    finally:
      part.unlink(missing_ok=True)
    record_file(db, product, obs, path, status, detail, http)
    if stop:
      raise CollectionStop(status)
    retryable = status in ("FAILED", "INVALID_DOWNLOAD") or http == 429 or (
      http is not None and 500 <= http <= 599
    )
    if not retryable or attempt == args.retries:
      return status
    time.sleep(min(MAX_BACKOFF_SECONDS, 2 ** attempt))
  raise RuntimeError("수집 상태 누락")


def run_cycle(
  db: sqlite3.Connection, root: Path, slots: Sequence[datetime],
  key: str, args: argparse.Namespace
) -> int:
  """회차별 기대 파일 확인 및 부분 성공 구분."""
  counts = Counter()
  total = len(slots) * len(PRODUCTS)
  for obs in slots:
    for product in PRODUCTS:
      try:
        status = download_one(db, root, product, obs, key, args)
      except CollectionStop as err:
        counts[str(err)] += 1
        result = {"status": str(err), "expected": total, "counts": dict(counts)}
        LOGGER.info("%s", json.dumps(result, ensure_ascii=False))
        return 3 if str(err) == "QUOTA_STOP" else 1
      counts[status] += 1
      LOGGER.info("%s %s UTC %s", product, obs.strftime("%Y%m%d%H%M"), status)
  good = counts["SUCCESS"] + counts["SKIPPED_EXISTING"]
  status = "SUCCESS" if good == total else ("PARTIAL_SUCCESS" if good else "FAILED")
  LOGGER.info("%s", json.dumps(
    {"status": status, "expected": total, "counts": dict(counts)},
    ensure_ascii=False
  ))
  return 0 if status == "SUCCESS" else 2


def main(argv: Sequence[str] | None = None) -> int:
  """명령줄 설정 검증 및 1회·반복 수집 실행."""
  parser = argparse.ArgumentParser(description=__doc__,
                  formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--output-dir", type=Path, default=Path("data/raw/gk2a"))
  parser.add_argument("--state-dir", type=Path,
            default=Path("data/interim/gk2a_collection"),
            help="운영 원장과 잠금 폴더; 원본 폴더와 분리")
  parser.add_argument("--loop", action="store_true", help="반복 수집; 미지정 시 1회")
  parser.add_argument("--interval-minutes", type=int, default=10, help="조회 반복 주기")
  parser.add_argument("--lookback-hours", type=int, default=3, help="다시 확인할 정시 슬롯 수")
  parser.add_argument("--lag-minutes", type=int, default=20, help="생성 지연 대기 가정값")
  parser.add_argument("--start", help="보완 수집 시작 UTC YYYYMMDDHH00")
  parser.add_argument("--end", help="보완 수집 종료 UTC YYYYMMDDHH00; 양 끝 포함")
  parser.add_argument("--max-calls", type=int, default=18000, help="로컬 KST 일일 요청 예산")
  parser.add_argument(
    "--max-gb",
    type=float,
    default=4.5,
    help="본문 수신 예산; 1 GB=10^9 bytes"
  )
  parser.add_argument("--retries", type=int, default=2, help="최초 요청 이후 최대 재시도 수")
  parser.add_argument("--request-gap", type=float, default=0.5, help="요청 전 대기 초")
  parser.add_argument("--timeout", type=float, default=60, help="네트워크 작업 타임아웃 초")
  parser.add_argument("--dry-run", action="store_true", help="키/통신/파일 생성 없이 대상 출력")
  parser.add_argument("--base-parquet", type=Path, help="보존할 기존 전체기간 기준 파일")
  parser.add_argument("--final-parquet", type=Path,
            default=Path("data/processed/gk2a/GK2A_FOG_APPS_ROI_current.parquet"))
  parser.add_argument("--processed-root", type=Path,
            default=Path("data/processed/gk2a"), help="시간별/월별 ROI 파생자료 경로")
  parser.add_argument("--process-only", action="store_true",
            help="API 없이 지정 슬롯의 기존 Raw를 최종 Parquet까지 처리")
  args = parser.parse_args(argv)
  if args.process_only and not args.base_parquet:
    parser.error("--process-only는 --base-parquet과 함께 사용하세요.")
  if args.base_parquet and args.base_parquet.resolve() == args.final_parquet.resolve():
    parser.error("기준 파일과 최종 갱신 파일 경로는 달라야 합니다.")
  if (args.interval_minutes <= 0 or args.lookback_hours <= 0 or args.lag_minutes < 0
      or args.max_calls <= 0 or not math.isfinite(args.max_gb) or args.max_gb <= 0
      or args.retries < 0
      or not math.isfinite(args.request_gap) or args.request_gap < 0
      or not math.isfinite(args.timeout) or args.timeout <= 0):
    parser.error("주기/범위/예산/타임아웃은 유효한 양수, 지연/재시도/대기는 0 이상")
  if bool(args.start) != bool(args.end) or (args.loop and args.start):
    parser.error("--start/--end는 함께 지정하며 --loop와 함께 사용할 수 없습니다.")
  args.max_bytes = int(args.max_gb * BYTES_PER_GB)
  if args.max_bytes <= 0:
    parser.error("본문 수신 예산은 최소 1바이트여야 합니다.")
  fixed_slots = None
  if args.start:
    try:
      start, end = parse_utc(args.start), parse_utc(args.end)
      if start > end or end > now_utc():
        raise ValueError("시작/종료 순서 또는 미래 관측시각 확인 필요")
    except ValueError as err:
      parser.error(str(err))
    fixed_slots = [start + timedelta(hours=i)
           for i in range(int((end - start).total_seconds() // 3600) + 1)]
  slots = fixed_slots or observation_slots(
    now_utc(),
    args.lookback_hours,
    args.lag_minutes
  )
  root = args.output_dir.resolve()
  if args.dry_run:
    for obs in slots:
      for product in PRODUCTS:
        LOGGER.info("%s %s UTC -> %s", product, obs.strftime("%Y%m%d%H%M"),
              target_path(root, product, obs))
    return 0
  key = os.getenv("KMA_AUTH_KEY", "").strip() or os.getenv("KMA_API_KEY", "").strip()
  if not key and not args.process_only:
    parser.error("KMA_AUTH_KEY 또는 KMA_API_KEY 환경변수 설정 필요")
  state_dir = args.state_dir.resolve()
  if (
    state_dir == root
    or state_dir.is_relative_to(root)
    or root.is_relative_to(state_dir)
  ):
    parser.error("원본과 운영 상태 폴더는 서로 분리해야 합니다.")
  if args.base_parquet:

    template_metadata(args.base_parquet)
    for derived in (args.processed_root.resolve(), args.final_parquet.resolve()):
      if derived == root or derived.is_relative_to(root):
        parser.error("파생자료/최종 파일은 Raw 폴더 밖에 저장하세요.")
  root.mkdir(parents=True, exist_ok=True)
  state_dir.mkdir(parents=True, exist_ok=True)
  with single_instance(state_dir):
    db = open_ledger(state_dir)
    run_id = None
    code = 1
    try:
      run_id = start_run(db, root, args)
      while True:
        slots = fixed_slots or observation_slots(
          now_utc(), args.lookback_hours, args.lag_minutes
        )
        with db:
          db.execute(
            "UPDATE runs SET first_obs_utc=COALESCE(first_obs_utc, ?), "
            "last_obs_utc=? WHERE run_id=?",
            (slots[0].isoformat(), slots[-1].isoformat(), run_id),
          )
        code = 0 if args.process_only else run_cycle(db, root, slots, key, args)
        if args.base_parquet:
          # 요청 실패·예산 중단 전 확보 원본도 처리. 수집 종료 코드는 유지.
          result = process_increment(slots, root, args.processed_root,
                       args.base_parquet, args.final_parquet)
          if code == 0 and result["status"] == "NO_NEW_SCENES":
            code = 2
        if not args.loop or code in (1, 3):
          return code
        # 시작은 즉시, 이후 UTC epoch 기준 주기 경계에 조회. 작업 중 중복 실행 없음.
        interval = args.interval_minutes * 60
        next_poll = (math.floor(time.time() / interval) + 1) * interval
        while time.time() < next_poll:
          time.sleep(max(0, min(POLL_WAIT_SECONDS, next_poll - time.time())))
    except KeyboardInterrupt:
      code = 130
      raise
    except (OSError, sqlite3.Error, RuntimeError, ValueError):
      code = 1
      raise
    finally:
      try:
        if run_id is not None:
          with db:
            db.execute(
              "UPDATE runs SET ended_at_utc=?, exit_code=? WHERE run_id=?",
              (now_utc().isoformat(), code, run_id),
            )
      finally:
        db.close()

# =============================================================================
# 월별 통합 보조 기능
# =============================================================================

FILE_PATTERN = re.compile(r"^GK2A_KO_(\d{12})\.parquet$")

ROW_GROUP_TARGET = 1_000_000

COMMON_METADATA_KEYS = (
  b"gk2a.conversion_version",
  b"gk2a.grid_fingerprint",
  b"gk2a.range_policy",
  b"gk2a.roi_name",
  b"gk2a.roi_version",
  b"gk2a.roi_fingerprint",
  b"gk2a.roi_spec",
)

def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
  """UTC 기준 월 시작 및 다음 월 시작 시각 반환."""
  start = datetime(year, month, 1, tzinfo=timezone.utc)

  if month == 12:
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
  else:
    end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

  return start, end

def parse_file_time(path: Path) -> datetime:
  """시간별 Parquet 파일명에서 UTC 관측시각 추출."""
  match = FILE_PATTERN.fullmatch(path.name)

  if match is None:
    raise ValueError(f"파일명 규칙 불일치: {path}")

  return datetime.strptime(
    match.group(1),
    "%Y%m%d%H%M"
  ).replace(tzinfo=timezone.utc)

def require_metadata(metadata: dict, key: bytes, path: Path) -> bytes:
  """필수 메타데이터 확인 및 누락 시 처리 중단."""
  value = metadata.get(key)

  if value is None:
    raise ValueError(
      f"필수 메타데이터 누락: {key.decode()} | {path}"
    )

  return value

def preflight_month(year: int, month: int, month_dir: Path) -> dict:
  """월별 입력의 시각·스키마·행 수·메타데이터 일치 확인."""
  files = sorted(
    month_dir.glob("*.parquet"),
    key=parse_file_time
  )

  if not files:
    raise ValueError(f"Parquet 파일 없음: {month_dir}")

  start, end = month_bounds(year, month)
  parsed_times = [parse_file_time(path) for path in files]

  if len(set(parsed_times)) != len(parsed_times):
    raise ValueError(
      f"동일 시각 중복 파일 존재: {year:04d}-{month:02d}"
    )

  for path, obs_time in zip(files, parsed_times):
    if not start <= obs_time < end:
      raise ValueError(
        f"월 범위 밖 파일: {path.name}"
      )

  first_pf = pq.ParquetFile(files[0])
  base_schema = first_pf.schema_arrow.remove_metadata()
  base_metadata = first_pf.schema_arrow.metadata or {}

  common_metadata = {
    key: require_metadata(base_metadata, key, files[0])
    for key in COMMON_METADATA_KEYS
  }

  rows_per_file = first_pf.metadata.num_rows

  range_counts = {}
  manifest_hash = hashlib.sha256()
  total_rows = 0

  for path, expected_time in zip(files, parsed_times):
    pf = pq.ParquetFile(path)
        
        

    schema = pf.schema_arrow.remove_metadata()
    metadata = pf.schema_arrow.metadata or {}

    if not schema.equals(
      base_schema,
      check_metadata=False
    ):
      raise ValueError(
        f"스키마 불일치: {path}"
      )

    if pf.metadata.num_rows != rows_per_file:
      raise ValueError(
        f"행 수 불일치: {path.name} | "
        f"{pf.metadata.num_rows:,} != {rows_per_file:,}"
      )

    for key, expected_value in common_metadata.items():
      actual_value = require_metadata(
        metadata,
        key,
        path
      )

      if actual_value != expected_value:
        raise ValueError(
          f"공통 메타데이터 불일치: "
          f"{key.decode()} | {path.name}"
        )

    source_fingerprint = require_metadata(
      metadata,
      b"gk2a.source_fingerprint",
      path
    )

    manifest_hash.update(
      path.name.encode("utf-8")
      + b"\t"
      + source_fingerprint
      + b"\n"
    )

    counts_raw = require_metadata(
      metadata,
      b"gk2a.range_violation_counts",
      path
    )

    counts = json.loads(
      counts_raw.decode("utf-8")
    )

    for key, value in counts.items():
      range_counts[key] = (
        range_counts.get(key, 0) + int(value)
      )

    time_col = pq.read_table(
      path,
      columns=["obs_time_utc"]
    ).column("obs_time_utc")

    expected_scalar = pa.scalar(
      expected_time,
      type=time_col.type
    )

    if not pc.all(
      pc.equal(time_col, expected_scalar)
    ).as_py():
      raise ValueError(
        f"내부 obs_time_utc 불일치: {path.name}"
      )

    total_rows += pf.metadata.num_rows

  expected_times = []
  current = start

  while current < end:
    expected_times.append(current)
    current += timedelta(hours=1)

  missing_times = sorted(
    set(expected_times) - set(parsed_times)
  )

  return {
    "files": files,
    "times": parsed_times,
    "base_schema": base_schema,
    "common_metadata": common_metadata,
    "rows_per_file": rows_per_file,
    "total_rows": total_rows,
    "range_counts": range_counts,
    "manifest_sha256": manifest_hash.hexdigest(),
    "period_start": parsed_times[0],
    "period_end": parsed_times[-1],
    "missing_times": missing_times,
  }

def build_month_metadata(info: dict) -> dict:
  """월별 통합 파일의 기간·행 수·누락·출처 정보 생성."""
  metadata = dict(info["common_metadata"])

  metadata.update({
    b"gk2a.range_violation_counts": json.dumps(
      info["range_counts"],
      sort_keys=True,
      separators=(",", ":")
    ).encode("utf-8"),
    b"gk2a.merge_level": b"monthly",
    b"gk2a.period_start_utc": (
      info["period_start"]
      .isoformat()
      .replace("+00:00", "Z")
      .encode("ascii")
    ),
    b"gk2a.period_end_utc": (
      info["period_end"]
      .isoformat()
      .replace("+00:00", "Z")
      .encode("ascii")
    ),
    b"gk2a.source_file_count": str(
      len(info["files"])
    ).encode("ascii"),
    b"gk2a.row_count": str(
      info["total_rows"]
    ).encode("ascii"),
    b"gk2a.sort_order": (
      b"obs_time_utc,pixel_y,pixel_x"
    ),
    b"gk2a.source_manifest_sha256": (
      info["manifest_sha256"].encode("ascii")
    ),
  })

  return metadata

def verify_output(output_path: Path, info: dict) -> None:
  """생성 파일의 스키마·행 수·정렬·기간 확인."""
  with pq.ParquetFile(output_path) as pf:
    output_schema = pf.schema_arrow.remove_metadata()

    if pf.metadata.num_rows != info["total_rows"]:
      raise ValueError(
        f"출력 행 수 불일치: "
        f"{pf.metadata.num_rows:,} != "
        f"{info['total_rows']:,}"
      )

    if not output_schema.equals(
      info["base_schema"],
      check_metadata=False
    ):
      raise ValueError(
        f"출력 스키마 불일치: {output_path}"
      )

    previous_last = None
    first_time = None
    last_time = None

    for batch in pf.iter_batches(
      batch_size=131_072,
      columns=[
        "obs_time_utc",
        "pixel_y",
        "pixel_x",
      ]
    ):
      frame = batch.to_pandas()

      order_index = pd.MultiIndex.from_frame(
        frame[
          [
            "obs_time_utc",
            "pixel_y",
            "pixel_x",
          ]
        ]
      )

      if not order_index.is_monotonic_increasing:
        raise ValueError(
          f"출력 정렬 불일치: {output_path}"
        )

      first_row = tuple(
        frame.iloc[0][
          [
            "obs_time_utc",
            "pixel_y",
            "pixel_x",
          ]
        ]
      )

      last_row = tuple(
        frame.iloc[-1][
          [
            "obs_time_utc",
            "pixel_y",
            "pixel_x",
          ]
        ]
      )

      if (
        previous_last is not None
        and first_row < previous_last
      ):
        raise ValueError(
          f"배치 경계 정렬 불일치: {output_path}"
        )

      if first_time is None:
        first_time = frame["obs_time_utc"].iloc[0]

      last_time = frame["obs_time_utc"].iloc[-1]
      previous_last = last_row

    if first_time.to_pydatetime() != info["period_start"]:
      raise ValueError(
        f"최초 관측시각 불일치: {output_path}"
      )

    if last_time.to_pydatetime() != info["period_end"]:
      raise ValueError(
        f"최종 관측시각 불일치: {output_path}"
      )

# =============================================================================
# 결과 검증 기능
# =============================================================================

ROWS_PER_SCENE = 7_383

PIXEL_Y_MIN, PIXEL_Y_MAX = 440, 508

PIXEL_X_MIN, PIXEL_X_MAX = 381, 487

REQUIRED_COLUMNS = [
  "obs_time_utc", "obs_time_kst", "pixel_y", "pixel_x",
  "fog_class", "fog_dqf", "del_fta_k",
  "aod", "aod_dqf", "aep", "aep_dqf",
  "daod055", "daod055_dqf", "daod11", "daod11_dqf",
]

VALUE_RANGES = {
  "fog_class": (1, 7),
  "fog_dqf": (0, 15),
  "del_fta_k": (-10.0, 6.0),
  "aod": (0.0, 5.0),
  "aod_dqf": (0, 2),
  "aep": (-1.0, 3.0),
  "aep_dqf": (0, 2),
  "daod055": (0.0, 5.0),
  "daod055_dqf": (0, 2),
  "daod11": (0.0, 5.0),
  "daod11_dqf": (0, 2),
}

FILL_VALUES = {
  "fog_class": 65535,
  "fog_dqf": 255,
  "del_fta_k": -3276.8,
  "aod_dqf": 255,
  "aep_dqf": 255,
  "daod055_dqf": 255,
  "daod11_dqf": 255,
}

MONTH_FILE_RE = re.compile(r"^GK2A_KO_(\d{6})\.parquet$")

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

def to_ns(value: datetime) -> int:
  """시간대가 있는 시각의 UTC epoch 기준 나노초 변환."""
  delta = value.astimezone(timezone.utc) - EPOCH
  return (
    (delta.days * 86_400 + delta.seconds) * 1_000_000_000
    + delta.microseconds * 1_000
  )

def count_true(mask: pa.Array | pa.ChunkedArray) -> int:
  """NULL 제외 조건 해당 값의 개수 계산."""
  value = pc.sum(
    pc.cast(pc.fill_null(mask, False), pa.int64())
  ).as_py()
  return int(value or 0)

def get_month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
  """UTC 기준 월별 검사 구간 반환."""
  start = datetime(year, month, 1, tzinfo=timezone.utc)

  if month == 12:
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
  else:
    end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

  return start, end

def scan_monthly_file(path: Path, expected_schema: pa.Schema, month_label: str) -> dict:
  """Parquet 배치 읽기를 통한 구조·좌표·시각·품질 통계 검사."""
  result = {
    "rows": 0,
    "scenes": 0,
    "times": set(),
    "nulls": Counter(),
    "nans": Counter(),
    "non_finite": Counter(),
    "fill_values": Counter(),
    "out_of_range": Counter(),
    "value_counts": {},
    "minmax": {},
    "sort_errors": 0,
    "coordinate_errors": 0,
    "duplicate_scenes": 0,
    "month_boundary_rows": 0,
    "utc_kst_mismatches": 0,
    "null_time_rows": 0,
    "scene_row_errors": 0,
    "missing_columns": [],
    "extra_columns": [],
    "schema_mismatch": False,
    "metadata": {},
    "schema": None,
  }

  with pq.ParquetFile(path) as parquet_file:
    actual_schema = parquet_file.schema_arrow.remove_metadata()
    metadata = parquet_file.schema_arrow.metadata or {}
    available_columns = actual_schema.names

    result["metadata"] = metadata
    result["schema"] = actual_schema
    result["missing_columns"] = [
      column for column in REQUIRED_COLUMNS
      if column not in available_columns
    ]
    result["extra_columns"] = [
      column for column in available_columns
      if column not in REQUIRED_COLUMNS
    ]

    if result["missing_columns"]:
      return result

    result["schema_mismatch"] = not actual_schema.equals(
      expected_schema, check_metadata=False
    )

    field_indexes = {
      name: actual_schema.get_field_index(name)
      for name in REQUIRED_COLUMNS
    }

    utc_type = actual_schema.field("obs_time_utc").type
    kst_type = actual_schema.field("obs_time_kst").type

    unit_to_ns = {
      "s": 1_000_000_000,
      "ms": 1_000_000,
      "us": 1_000,
      "ns": 1,
    }
    utc_multiplier = (
      unit_to_ns.get(utc_type.unit)
      if pa.types.is_timestamp(utc_type)
      else None
    )
    kst_multiplier = (
      unit_to_ns.get(kst_type.unit)
      if pa.types.is_timestamp(kst_type)
      else None
    )

    match = MONTH_FILE_RE.fullmatch(path.name)
    if month_label == "full_period":
      month_start_ns, month_end_ns = -(2**63), 2**63 - 1
    elif match is None:
      raise ValueError("월별 검사 파일명 불일치")
    else:
      year, month = int(match.group(1)[:4]), int(match.group(1)[4:6])
      month_start, month_end = get_month_bounds(year, month)
      month_start_ns, month_end_ns = to_ns(month_start), to_ns(month_end)

    # 정본 ROI의 사전 계산 좌표
    expected_y = np.repeat(
      np.arange(PIXEL_Y_MIN, PIXEL_Y_MAX + 1, dtype=np.uint16),
      PIXEL_X_MAX - PIXEL_X_MIN + 1,
    )
    expected_x = np.tile(
      np.arange(PIXEL_X_MIN, PIXEL_X_MAX + 1, dtype=np.uint16),
      PIXEL_Y_MAX - PIXEL_Y_MIN + 1,
    )

    # 배치·장면 경계를 넘는 정렬 상태
    previous_order = None
    active_scene = None
    active_scene_rows = 0
    active_scene_offset = 0
    seen_scene_times = set()

    total_batches = math.ceil(
      parquet_file.metadata.num_rows / BATCH_SIZE
    )

    with tqdm(
      total=total_batches,
      desc=f"{month_label} 행·정렬·값 검사",
      unit="batch",
      leave=False,
      dynamic_ncols=True,
    ) as batch_bar:
      for batch in parquet_file.iter_batches(
        batch_size=BATCH_SIZE,
        columns=REQUIRED_COLUMNS,
      ):
        result["rows"] += batch.num_rows

        utc_array = batch.column(field_indexes["obs_time_utc"])
        kst_array = batch.column(field_indexes["obs_time_kst"])
        y_array = batch.column(field_indexes["pixel_y"])
        x_array = batch.column(field_indexes["pixel_x"])

        result["null_time_rows"] += utc_array.null_count + kst_array.null_count

        if utc_multiplier is None or kst_multiplier is None:
          result["sort_errors"] += 1
          batch_bar.update(1)
          continue

        # 시간대 표기와 단위가 다른 시각 컬럼의 UTC 기준 정규화
        utc_ticks = utc_array.cast(pa.int64()).fill_null(0).to_numpy(
          zero_copy_only=False
        )
        kst_ticks = kst_array.cast(pa.int64()).fill_null(0).to_numpy(
          zero_copy_only=False
        )
        utc_ns = utc_ticks * utc_multiplier
        kst_ns = kst_ticks * kst_multiplier

        valid_time_mask = (
          ~utc_array.is_null().to_numpy(zero_copy_only=False)
          & ~kst_array.is_null().to_numpy(zero_copy_only=False)
        )
        result["utc_kst_mismatches"] += int(np.count_nonzero(
          valid_time_mask & (utc_ns != kst_ns)
        ))

        # 좌표 Null을 ROI 밖의 sentinel로 바꾸는 검사 방식
        y_values = y_array.fill_null(65535).to_numpy(
          zero_copy_only=False
        )
        x_values = x_array.fill_null(65535).to_numpy(
          zero_copy_only=False
        )
        null_time_mask = utc_array.is_null().to_numpy(
          zero_copy_only=False
        )

        result["month_boundary_rows"] += int(np.count_nonzero(
          (~null_time_mask)
          & ((utc_ns < month_start_ns) | (utc_ns >= month_end_ns))
        ))

        if len(utc_ns):
          # 배치 첫 행과 직전 배치 마지막 행의 정렬 연결
          if previous_order is not None:
            first_order = (
              int(utc_ns[0]), int(y_values[0]), int(x_values[0])
            )
            if first_order < previous_order:
              result["sort_errors"] += 1

          # 배치 내부의 시각 → pixel_y → pixel_x 오름차순
          if len(utc_ns) > 1:
            time_backwards = utc_ns[1:] < utc_ns[:-1]
            same_time = utc_ns[1:] == utc_ns[:-1]
            y_backwards = y_values[1:] < y_values[:-1]
            same_y = y_values[1:] == y_values[:-1]
            x_backwards = x_values[1:] < x_values[:-1]

            invalid_order = (
              time_backwards
              | (same_time & y_backwards)
              | (same_time & same_y & x_backwards)
            )
            result["sort_errors"] += int(
              np.count_nonzero(invalid_order)
            )

          previous_order = (
            int(utc_ns[-1]), int(y_values[-1]), int(x_values[-1])
          )

          # 장면별 좌표 검사 기준: 동일 시각 행의 연속 구간 가정
          boundaries = np.flatnonzero(
            utc_ns[1:] != utc_ns[:-1]
          ) + 1
          starts = np.concatenate(([0], boundaries))
          ends = np.concatenate((boundaries, [len(utc_ns)]))

          for start, end in zip(starts, ends):
            if null_time_mask[start]:
              continue

            scene_ns = int(utc_ns[start])

            if active_scene != scene_ns:
              if active_scene is not None:
                if active_scene_rows != ROWS_PER_SCENE:
                  result["scene_row_errors"] += 1

              if scene_ns in seen_scene_times:
                result["duplicate_scenes"] += 1

              seen_scene_times.add(scene_ns)
              result["times"].add(scene_ns)
              result["scenes"] += 1
              active_scene = scene_ns
              active_scene_rows = 0
              active_scene_offset = 0

            count = int(end - start)
            expected_end = active_scene_offset + count

            if expected_end > ROWS_PER_SCENE:
              result["coordinate_errors"] += 1
            else:
              y_expected = expected_y[
                active_scene_offset:expected_end
              ]
              x_expected = expected_x[
                active_scene_offset:expected_end
              ]

              if (not np.array_equal(y_values[start:end], y_expected)
                  or not np.array_equal(x_values[start:end], x_expected)):
                result["coordinate_errors"] += 1

            active_scene_rows += count
            active_scene_offset = expected_end

        # 과학값·DQF의 Null·NaN·Fill·범위·분포 집계
        for column in REQUIRED_COLUMNS[4:]:
          array = batch.column(field_indexes[column])
          result["nulls"][column] += array.null_count

          if column in FILL_VALUES:
            try:
              fill_value = FILL_VALUES[column]
              if pa.types.is_floating(array.type):
                fill_value = np.float32(fill_value)

              fill_scalar = pa.scalar(fill_value, type=array.type)
              result["fill_values"][column] += count_true(
                pc.equal(array, fill_scalar)
              )
            except (pa.ArrowInvalid, OverflowError, TypeError):
              pass

          if pa.types.is_floating(array.type):
            result["nans"][column] += count_true(pc.is_nan(array))
            result["non_finite"][column] += count_true(
              pc.invert(pc.is_finite(array))
            )
            finite_mask = pc.fill_null(
              pc.is_finite(array), False
            )
            finite_values = pc.filter(array, finite_mask)
          else:
            finite_values = array.drop_null()

          if len(finite_values):
            low, high = VALUE_RANGES.get(column, (None, None))

            if low is not None:
              outside = pc.or_(
                pc.less(finite_values, low),
                pc.greater(finite_values, high),
              )
              result["out_of_range"][column] += count_true(outside)

            minimum = pc.min(finite_values).as_py()
            maximum = pc.max(finite_values).as_py()
            old_minmax = result["minmax"].get(column)

            if old_minmax is None:
              result["minmax"][column] = [minimum, maximum]
            else:
              old_minmax[0] = min(old_minmax[0], minimum)
              old_minmax[1] = max(old_minmax[1], maximum)

          if column == "fog_class" or column.endswith("_dqf"):
            counts = pc.value_counts(
              array.drop_null()
            ).to_pylist()
            column_counts = result["value_counts"].setdefault(
              column, Counter()
            )
            for item in counts:
              column_counts[str(item["values"])] += int(item["counts"])

        batch_bar.update(1)
        batch_bar.set_postfix(
          rows=f"{result['rows']:,}",
          scenes=f"{result['scenes']:,}",
          refresh=False,
        )

    # 마지막 배치에 걸친 장면의 행 수 판정
    if active_scene is not None and active_scene_rows != ROWS_PER_SCENE:
      result["scene_row_errors"] += 1

  return result

def compare_all_values(
  monthly_path: Path, hourly_files: list[Path], temp_dir: Path, month_label: str
) -> tuple[int, int]:
  """월별 파일과 시간별 입력 간 전체 컬럼 값 차이의 양방향 집계."""
  tqdm.write(
    f"{month_label}: 전체 컬럼 값 대조 시작 "
    f"({len(hourly_files):,}개 시간별 파일)"
  )

  connection = duckdb.connect(database=":memory:")
  connection.execute("SET threads=4")
  connection.execute("SET memory_limit='4GB'")
  connection.execute(
    "SET temp_directory="
    + "'" + str(temp_dir).replace("'", "''") + "'"
  )
  connection.execute("SET enable_progress_bar=true")
  connection.execute("SET progress_bar_time=1000")

  query = """
        WITH monthly AS MATERIALIZED (
            SELECT * FROM read_parquet(?, union_by_name=false)
        ),
        hourly AS MATERIALIZED (
            SELECT * FROM read_parquet(?, union_by_name=false)
        )
        SELECT
            (
                SELECT count(*)
                FROM (
                    SELECT * FROM monthly
                    EXCEPT ALL
                    SELECT * FROM hourly
                )
            ) AS only_in_monthly,
            (
                SELECT count(*)
                FROM (
                    SELECT * FROM hourly
                    EXCEPT ALL
                    SELECT * FROM monthly
                )
            ) AS only_in_hourly
    """

  try:
    values = connection.execute(
      query,
      [
        str(monthly_path),
        [str(path) for path in hourly_files],
      ],
    ).fetchone()
  finally:
    connection.close()

  return int(values[0]), int(values[1])

# =============================================================================
# 전처리와 증분 갱신
# =============================================================================

VERSION = "gk2a-incremental-v1"
ROWS = 7383
GRID_SIZE = 900
BATCH_SIZE = 131072
Y_MIN, Y_MAX = 440, 508
X_MIN, X_MAX = 381, 487
FIELDS = {
  "FOG": [("FOG", "fog_class", "uint16"),
      ("DQF_FOG", "fog_dqf", "uint8"),
      ("Del_Fta", "del_fta_k", "int16")],
  "APPS": [("AOD", "aod", "uint16"), ("AOD_DQF", "aod_dqf", "uint8"),
      ("AEP", "aep", "uint16"), ("AEP_DQF", "aep_dqf", "uint8"),
      ("DAOD055", "daod055", "uint16"),
      ("DAOD055_DQF", "daod055_dqf", "uint8"),
      ("DAOD11", "daod11", "uint16"), ("DAOD11_DQF", "daod11_dqf", "uint8")],
}
SCHEMA = pa.schema([
  ("obs_time_utc", pa.timestamp("ms", tz="UTC")),
  ("obs_time_kst", pa.timestamp("ms", tz="Asia/Seoul")),
  ("pixel_y", pa.uint16()), ("pixel_x", pa.uint16()),
  *[(column, pa.float32() if column in {
    "del_fta_k", "aod", "aep", "daod055", "daod11"
  } else pa.uint16() if column == "fog_class" else pa.uint8())
   for fields in FIELDS.values() for _, column, _ in fields],
])
EXPECTED_Y = np.repeat(np.arange(Y_MIN, Y_MAX + 1, dtype=np.uint16), X_MAX-X_MIN+1)
EXPECTED_X = np.tile(np.arange(X_MIN, X_MAX + 1, dtype=np.uint16), Y_MAX-Y_MIN+1)
PROJECTION = {
  "grid_mapping_name": "lambert_conformal_conic",
  "standard_parallel1": 30.0, "standard_parallel2": 60.0,
  "origin_latitude": 38.0, "central_meridian": 126.0,
  "false_easting": 0.0, "false_northing": 0.0,
  "image_width": 900, "image_height": 900, "pixel_size": 2000.0,
  "upper_left_easting": -899000.0, "upper_left_northing": 899000.0,
  "upper_right_easting": 899000.0, "upper_right_northing": 899000.0,
  "lower_left_easting": -899000.0, "lower_left_northing": -899000.0,
  "lower_right_easting": 899000.0, "lower_right_northing": -899000.0,
}


def file_hash(path: Path) -> str:
  """파일 변경 없는 원본 SHA256 계산."""
  digest = hashlib.sha256()
  with path.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def template_metadata(base: Path) -> dict:
  """실제 기준 파일의 15컬럼·ROI 계약 확인."""
  with pq.ParquetFile(base) as parquet:
    if not parquet.schema_arrow.equals(SCHEMA, check_metadata=False):
      raise ValueError("기준 Parquet의 15컬럼 자료형 계약 불일치")
    metadata = parquet.schema_arrow.metadata or {}
  common = {
    key: require_metadata(metadata, key, base)
    for key in COMMON_METADATA_KEYS
  }
  roi = json.loads(common[b"gk2a.roi_spec"])
  expected = {"rows": ROWS, "x_min": X_MIN, "x_max": X_MAX,
        "y_min": Y_MIN, "y_max": Y_MAX, "width": 107, "height": 69}
  if any(roi.get(key) != value for key, value in expected.items()):
    raise ValueError("기준 파일의 ROI가 확정 7,383화소 영역과 다름")
  return common


def _scalar(dataset, key: str):
  if key not in dataset.attrs:
    raise ValueError(f"필수 원천 속성 누락: {dataset.name}.{key}")
  value = dataset.attrs[key]
  if isinstance(value, np.ndarray):
    if value.size != 1:
      raise ValueError(f"스칼라 속성 아님: {dataset.name}.{key}")
    value = value.reshape(-1)[0]
  if isinstance(value, np.generic):
    value = value.item()
  return value.decode() if isinstance(value, bytes) else value


def _read_product(path: Path, product: str) -> tuple[dict, dict]:
  arrays, definitions = {}, {}
  with h5py.File(path, "r") as source:
    if "gk2a_imager_projection" not in source:
      raise ValueError("원천 투영 변수 없음")
    projection = source["gk2a_imager_projection"]
    for key, expected in PROJECTION.items():
      if _scalar(projection, key) != expected:
        raise ValueError(f"검증된 KO 격자와 {key} 불일치")
    for name, column, raw_type in FIELDS[product]:
      if name not in source:
        raise ValueError(f"원천 변수 없음: {product}/{name}")
      dataset = source[name]
      if dataset.shape != (GRID_SIZE, GRID_SIZE) or str(dataset.dtype) != raw_type:
        raise ValueError(f"원천 shape/dtype 변경: {product}/{name}")
      raw = dataset[Y_MIN:Y_MAX+1, X_MIN:X_MAX+1]
      fill = _scalar(dataset, "_FillValue")
      low, high = _scalar(dataset, "valid_min"), _scalar(dataset, "valid_max")
      if not all(np.isfinite(v) for v in (fill, low, high)) or low > high:
        raise ValueError(f"원천 Fill/범위 속성 오류: {name}")
      mask = raw == fill
      dtype = SCHEMA.field(column).type
      definition = {"fill": fill, "valid_min": low, "valid_max": high}
      if pa.types.is_floating(dtype):
        scale = np.float32(_scalar(dataset, "scale_factor"))
        offset = np.float32(_scalar(dataset, "add_offset"))
        if not np.isfinite(scale) or not np.isfinite(offset) or scale == 0:
          raise ValueError(f"원천 scale/offset 오류: {name}")
        values = raw.astype(np.float32) * scale + offset
        definition.update(scale=float(scale), offset=float(offset))
      else:
        values = raw
      if "DQF" in name:
        definition["flag_meanings"] = _scalar(dataset, "flag_meanings")
      arrays[column] = pa.array(values.ravel(), mask=mask.ravel(), type=dtype)
      definitions[column] = definition
    # 소프트웨어 버전 문자열은 계보 정보로 보존. 격자·자료형 변경과 구분.
    version = source.attrs.get("algorithm_version")
    definitions["algorithm_version"] = str(version) if version is not None else None
  return arrays, definitions


def validate_scene(table: pa.Table, obs: datetime | None = None) -> datetime:
  """Scene 키·ROI·UTC/KST 일치 및 7,383행 검사."""
  if table.num_rows != ROWS or not table.schema.equals(SCHEMA, check_metadata=False):
    raise ValueError("Scene 행 수/스키마 불일치")
  for name in SCHEMA.names[:4]:
    if table[name].null_count:
      raise ValueError("Scene 키/시각에 NULL 존재")
  observed = table["obs_time_utc"][0].as_py()
  if observed.minute or observed.second or observed.microsecond:
    raise ValueError("정시가 아닌 Scene")
  if obs is not None and observed != obs:
    raise ValueError("요청 시각과 Scene 내부 시각 불일치")
  stamp = table["obs_time_utc"][0].cast(pa.int64()).as_py()
  for name in ("obs_time_utc", "obs_time_kst"):
    if not pc.all(pc.equal(table[name].cast(pa.int64()), stamp)).as_py():
      raise ValueError("Scene UTC/KST 값 불일치")
  if not np.array_equal(table["pixel_y"].to_numpy(), EXPECTED_Y):
    raise ValueError("ROI y 순서/중복 오류")
  if not np.array_equal(table["pixel_x"].to_numpy(), EXPECTED_X):
    raise ValueError("ROI x 순서/중복 오류")
  return observed


def convert_scene(
  obs: datetime, raw_root: Path, hourly_root: Path, common: dict
) -> Path | None:
  """원천의 ROI 변환 및 지연 도착 산출물의 원천 지문 변경 반영."""
  paths = {product: target_path(raw_root, product, obs) for product in FIELDS}
  available = {product: path.is_file() for product, path in paths.items()}
  if not any(available.values()):
    return None
  hashes = {product: file_hash(paths[product]) if present else None
       for product, present in available.items()}
  fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
  target = hourly_root / obs.strftime("%Y/%m") / f"GK2A_KO_{obs:%Y%m%d%H%M}.parquet"
  if target.exists():
    old = pq.read_metadata(target).metadata or {}
    if old.get(b"gk2a.source_fingerprint") == fingerprint.encode():
      validate_scene(pq.read_table(target), obs)
      return target
  epoch = int(obs.timestamp()*1000)
  columns = {
    "obs_time_utc": pa.array(np.full(ROWS, epoch), type=SCHEMA.field(0).type),
    "obs_time_kst": pa.array(np.full(ROWS, epoch), type=SCHEMA.field(1).type),
    "pixel_y": pa.array(EXPECTED_Y), "pixel_x": pa.array(EXPECTED_X),
  }
  definitions = {}
  for product, fields in FIELDS.items():
    if available[product]:
      arrays, definition = _read_product(paths[product], product)
      columns.update(arrays)
      definitions[product] = definition
    else:
      columns.update({column: pa.nulls(ROWS, SCHEMA.field(column).type)
              for _, column, _ in fields})
  table = pa.table(columns, schema=SCHEMA)
  validate_scene(table, obs)
  counts = {}
  for name, (low, high) in VALUE_RANGES.items():
    counts[name] = count_true(pc.or_(pc.less(table[name], low),
                          pc.greater(table[name], high)))
  metadata = dict(common)
  metadata.update({
    b"gk2a.incremental_converter_version": VERSION.encode(),
    b"gk2a.source_fingerprint": fingerprint.encode(),
    b"gk2a.source_metadata": json.dumps({"sha256": hashes, "encoding": definitions},
                     sort_keys=True).encode(),
    b"gk2a.range_violation_counts": json.dumps(counts, sort_keys=True,
                         separators=(",", ":")).encode(),
    b"gk2a.fog_available": str(available["FOG"]).lower().encode(),
    b"gk2a.apps_available": str(available["APPS"]).lower().encode(),
  })
  target.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(dir=target.parent, prefix=".stage-") as stage:
    candidate = Path(stage) / target.name
    pq.write_table(table.replace_schema_metadata(metadata), candidate,
           compression="zstd", write_page_checksum=True)
    validate_scene(pq.read_table(candidate), obs)
    os.replace(candidate, target)
  return target


def refresh_months(hourly_root: Path, monthly_root: Path) -> list[Path]:
  """월별 통합 기능을 통한 신규 시간자료 포함 월별 파일 갱신."""
  outputs = []
  for month_dir in sorted(hourly_root.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]")):
    year, month = int(month_dir.parent.name), int(month_dir.name)
    info = preflight_month(year, month, month_dir)
    target = monthly_root / f"{year:04d}" / f"GK2A_KO_{year:04d}{month:02d}.parquet"
    if target.exists() and (pq.read_metadata(target).metadata or {}).get(
      b"gk2a.source_manifest_sha256"
    ) == info["manifest_sha256"].encode():
      outputs.append(target)
      continue
    metadata = build_month_metadata(info)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".stage-") as stage:
      candidate = Path(stage) / target.name
      with pq.ParquetWriter(candidate, info["base_schema"].with_metadata(metadata),
                 compression="zstd", write_page_checksum=True) as writer:
        buffer, buffered = [], 0
        for path in info["files"]:
          table = pq.read_table(path).sort_by([
            ("pixel_y", "ascending"), ("pixel_x", "ascending")])
          buffer.append(table.replace_schema_metadata(metadata))
          buffered += table.num_rows
          if buffered >= ROW_GROUP_TARGET:
            writer.write_table(pa.concat_tables(buffer))
            buffer, buffered = [], 0
        if buffer:
          writer.write_table(pa.concat_tables(buffer))
      # 최종 승격 전 월별 통합 기능을 통한 생성 결과 확인.
      verify_output(candidate, info)
      os.replace(candidate, target)
    outputs.append(target)
  return outputs


def scene_stream(path: Path) -> Iterator[pa.Table]:
  """정렬된 Parquet의 Scene 단위 읽기를 통한 전체 파일 메모리 적재 회피."""
  with pq.ParquetFile(path) as source:
    buffer = None
    previous = None
    for batch in source.iter_batches(batch_size=BATCH_SIZE):
      table = pa.Table.from_batches([batch]).replace_schema_metadata(None)
      buffer = table if buffer is None else pa.concat_tables([buffer, table])
      offset = 0
      while buffer.num_rows-offset >= ROWS:
        scene = buffer.slice(offset, ROWS)
        observed = validate_scene(scene)
        if previous is not None and observed <= previous:
          raise ValueError("중복 Scene 또는 시간 정렬 역전")
        previous = observed
        yield scene
        offset += ROWS
      buffer = buffer.slice(offset)
    if buffer is not None and buffer.num_rows:
      raise ValueError("마지막 Scene 행 수 불완전")


def _delta_stream(months: Sequence[Path]) -> Iterator[pa.Table]:
  previous = None
  for month in sorted(months):
    for scene in scene_stream(month):
      observed = scene["obs_time_utc"][0].as_py()
      if previous is not None and observed <= previous:
        raise ValueError("월별 증분 Scene 중복/정렬 역전")
      previous = observed
      yield scene


def _availability(hourly_root: Path) -> dict:
  availability = {}
  for path in hourly_root.glob("*/*/GK2A_KO_*.parquet"):
    observed = parse_file_time(path)
    metadata = pq.read_metadata(path).metadata or {}
    flags = []
    for product in FIELDS:
      key = f"gk2a.{product.lower()}_available".encode()
      if metadata.get(key) not in (b"true", b"false"):
        raise ValueError("시간별 파일에 산출물 가용성 메타데이터 없음")
      flags.append(metadata[key] == b"true")
    availability[observed] = dict(zip(FIELDS, flags))
  return availability


def _combine_scene(old: pa.Table, new: pa.Table, flags: dict) -> pa.Table:
  columns = {name: new[name] for name in SCHEMA.names[:4]}
  for product, fields in FIELDS.items():
    for _, column, _ in fields:
      # 신규 산출물의 실제 Fill→NULL 유지 및 부재 산출물의 기존 값 보존.
      columns[column] = new[column] if flags[product] else old[column]
  return pa.table(columns, schema=SCHEMA)


def update_final(
  base: Path, final: Path, months: Sequence[Path], hourly_root: Path, common: dict
) -> dict:
  """기존 최종 파일과 월별 증분의 시간순 병합·검증 후 원자적 갱신."""
  if final.resolve() == base.resolve():
    raise ValueError("기준 파일과 최종 갱신 파일 경로는 달라야 합니다.")
  parent = final if final.exists() else base
  if template_metadata(parent) != common:
    raise ValueError("기준/이전 최종 파일의 공통 메타데이터 계약 불일치")
  availability = _availability(hourly_root)
  signatures = {str(path.resolve()): file_hash(path) for path in months}
  fingerprint = hashlib.sha256(json.dumps(signatures, sort_keys=True).encode()).hexdigest()
  if final.exists() and (pq.read_metadata(final).metadata or {}).get(
    b"gk2a.incremental_manifest_sha256"
  ) == fingerprint.encode():
    return {"status": "UNCHANGED", "file": str(final)}
  if not months:
    return {"status": "NO_NEW_SCENES", "file": str(parent)}
  source_hash = file_hash(parent)
  old_iter, new_iter = scene_stream(parent), _delta_stream(months)
  old, new = next(old_iter, None), next(new_iter, None)
  rows, scenes, added, replaced = 0, 0, 0, 0
  start, end = None, None
  counts = {name: 0 for name in VALUE_RANGES}
  final.parent.mkdir(parents=True, exist_ok=True)
  try:
    with tempfile.TemporaryDirectory(dir=final.parent, prefix=".stage-") as stage:
      candidate = Path(stage) / final.name
      with pq.ParquetWriter(candidate, SCHEMA.with_metadata(common),
                 compression="zstd", write_page_checksum=True) as writer:
        buffer, buffered = [], 0
        while old is not None or new is not None:
          old_time = old["obs_time_utc"][0].as_py() if old is not None else None
          new_time = new["obs_time_utc"][0].as_py() if new is not None else None
          if new is None or (old is not None and old_time < new_time):
            scene, observed = old, old_time
            old = next(old_iter, None)
          elif old is None or new_time < old_time:
            scene, observed = new, new_time
            new = next(new_iter, None)
            added += 1
          else:
            scene = _combine_scene(old, new, availability[new_time])
            observed = new_time
            old, new = next(old_iter, None), next(new_iter, None)
            replaced += 1
          start, end = start or observed, observed
          scenes += 1
          rows += scene.num_rows
          for name, (low, high) in VALUE_RANGES.items():
            counts[name] += count_true(pc.or_(
              pc.less(scene[name], low), pc.greater(scene[name], high)))
          buffer.append(scene)
          buffered += scene.num_rows
          if buffered >= ROW_GROUP_TARGET:
            writer.write_table(pa.concat_tables(buffer))
            buffer, buffered = [], 0
        if buffer:
          writer.write_table(pa.concat_tables(buffer))
        missing_scenes = int((end - start).total_seconds() // 3600) + 1 - scenes
        metadata = {
          "gk2a.merge_level": "full_period",
          "gk2a.source_merge_level": "monthly_incremental",
          "gk2a.incremental_version": VERSION,
          "gk2a.incremental_manifest_sha256": fingerprint,
          "gk2a.parent_sha256": source_hash,
          "gk2a.source_scene_count": str(scenes), "gk2a.row_count": str(rows),
          "gk2a.missing_scene_count": str(missing_scenes),
          "gk2a.sort_order": "obs_time_utc,pixel_y,pixel_x",
          "gk2a.period_start_utc": start.isoformat(),
          "gk2a.period_end_utc": end.isoformat(),
          "gk2a.range_violation_counts": json.dumps(counts, sort_keys=True,
                               separators=(",", ":")),
        }
        writer.add_key_value_metadata(metadata)
      result = scan_monthly_file(candidate, SCHEMA, "full_period")
      failures = [key for key in ("sort_errors", "coordinate_errors", "duplicate_scenes",
            "utc_kst_mismatches", "null_time_rows", "scene_row_errors",
            "missing_columns", "schema_mismatch") if result[key]]
      if failures or any(result["non_finite"].values()) or result["rows"] != rows:
        raise ValueError(f"최종 파일 검증 실패: {failures}")
      if file_hash(parent) != source_hash:
        raise ValueError("병합 도중 기준/이전 최종 파일이 변경됨")
      # 사용자 기준 파일은 보존. 이전 생성본은 한 세대 백업 후 신규 생성본 승격.
      if final.exists():
        shutil.copy2(final, final.with_suffix(".parquet.previous"))
      os.replace(candidate, final)
  finally:
    old_iter.close()
    new_iter.close()
  return {"status": "UPDATED", "file": str(final), "rows": rows, "scenes": scenes,
      "added_scenes": added, "updated_scenes": replaced,
      "missing_scenes": missing_scenes,
      "start_utc": start.isoformat(), "end_utc": end.isoformat()}


def process_increment(
  slots: Sequence[datetime], raw_root: Path, processed_root: Path,
  base: Path, final: Path
) -> dict:
  """수집 회차 원본 변환 및 월별·최종 파일 갱신 연결."""
  common = template_metadata(base)
  hourly = processed_root / "hourly"
  monthly_root = processed_root / "monthly"
  for obs in slots:
    convert_scene(obs, raw_root, hourly, common)
  months = refresh_months(hourly, monthly_root)
  result = update_final(base, final, months, hourly, common)
  LOGGER.info("최종 Parquet 갱신: %s", json.dumps(result, ensure_ascii=False))
  return result

# =============================================================================
# 명령줄 실행 진입점
# =============================================================================

def run_cli(argv: Sequence[str] | None = None) -> int:
  """통합 실행 옵션 확인 및 로그·종료 코드 설정."""
  arguments = list(sys.argv[1:] if argv is None else argv)
  has_base = any(
    argument == "--base-parquet" or argument.startswith("--base-parquet=")
    for argument in arguments
  )
  has_help = any(argument in ("-h", "--help") for argument in arguments)
  if not has_base and not has_help:
    raise SystemExit("통합 실행에는 --base-parquet 기존전체기간파일.parquet 지정이 필요합니다.")

  logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
  )
  try:
    return main(arguments)
  except KeyboardInterrupt:
    LOGGER.info("중단되었습니다. 다음 실행에서 재조회 범위 내 파일을 확인합니다.")
    return 130
  except ImportError:
    LOGGER.error("필수 패키지 확인 필요: numpy/h5py/pyarrow/pandas/duckdb/tqdm")
    return 1
  except (OSError, sqlite3.Error, RuntimeError, ValueError) as error:
    # 인증키·요청 URL 노출 방지를 위한 예외 유형만 기록.
    LOGGER.error(
      "실행 중단: %s. 저장 경로·잠금·원장 상태를 확인하세요.",
      type(error).__name__,
    )
    return 1


if __name__ == "__main__":
  raise SystemExit(run_cli())

