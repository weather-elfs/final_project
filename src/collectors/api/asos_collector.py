"""ASOS hourly collector for Baengnyeongdo (102), Incheon (112), Ganghwa (201).

Requires: pip install pandas
API key: KMA_AUTH_KEY environment variable.
Times are KST (Asia/Seoul) in the source API and CSV (naive local timestamps).
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

API_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "raw" / "asos"
DEFAULT_OUTPUT_FILENAME = "asos_실시간데이터.csv"
STATIONS = {102: "백령도", 112: "인천", 201: "강화도"}
RAW_FIELD_NAMES = [
    "TM", "STN", "WD", "WS", "GST_WD", "GST_WS", "GST_TM", "PA", "PS",
    "PT", "PR", "TA", "TD", "HM", "PV", "RN", "RN_DAY", "RN_JUN",
    "RN_INT", "SD_HR3", "SD_DAY", "SD_TOT", "WC", "WP", "WW", "CA_TOT",
    "CA_MID", "CH_MIN", "CT", "CT_TOP", "CT_MID", "CT_LOW", "VS", "SS",
    "SI", "ST_GD", "TS", "TE_005", "TE_01", "TE_02", "TE_03",
    "ST_SEA", "WH", "BF", "IR", "IX",
]
COLUMN_MAPPING = {
    "STN": "지점", "TM": "일시", "TA": "기온(°C)", "RN": "강수량(mm)",
    "WS": "풍속(m/s)", "WD": "풍향(16방위)", "HM": "습도(%)",
    "PV": "증기압(hPa)", "TD": "이슬점온도(°C)", "PA": "현지기압(hPa)",
    "PS": "해면기압(hPa)", "SS": "일조(hr)", "SI": "일사(MJ/m2)",
    "SD_TOT": "적설(cm)", "CH_MIN": "최저운고(100m )", "VS": "시정(10m)",
    "CA_TOT": "전운량(10분위)", "CA_MID": "중하층운량(10분위)",
    "ST_GD": "지면상태(지면상태코드)", "WW": "현상번호(국내식)",
    "TS": "지면온도(°C)", "TE_005": "5cm 지중온도(°C)",
    "TE_01": "10cm 지중온도(°C)", "TE_02": "20cm 지중온도(°C)",
    "TE_03": "30cm 지중온도(°C)",
}
FINAL_COLUMNS = [
    "지점", "station_name", "일시", "기온(°C)", "강수량(mm)", "풍속(m/s)",
    "풍향(16방위)", "습도(%)", "증기압(hPa)", "이슬점온도(°C)",
    "현지기압(hPa)", "해면기압(hPa)", "일조(hr)", "일사(MJ/m2)",
    "적설(cm)", "지면온도(°C)", "시정(10m)", "전운량(10분위)",
    "중하층운량(10분위)",
]
NUMERIC_SOURCE = [
    "TA", "RN", "WS", "WD", "HM", "PV", "TD", "PA", "PS", "SS", "SI",
    "SD_TOT", "CH_MIN", "VS", "CA_TOT", "CA_MID", "TS", "TE_005",
    "TE_01", "TE_02", "TE_03",
]
MISSING_VALUES = {"-99.0", "-999.0", "-9.0", "-99", "-999", "-9", "-"}


def parse_kma_text_data(raw_text: str) -> list[dict[str, Any]]:
    """Parse space-delimited KMA response, ignoring comments and END markers."""
    fields = RAW_FIELD_NAMES
    lines = raw_text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            tokens = stripped.lstrip("#").strip().split()
            if len(tokens) >= 40 and "TM" in tokens and "STN" in tokens:
                fields = tokens
                break

    records = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("7777END"):
            continue
        tokens = stripped.split()
        if len(tokens) < len(fields):
            continue
        row = {name: (None if tokens[i] in MISSING_VALUES else tokens[i])
               for i, name in enumerate(fields)}
        # Avoid treating server errors or unexpected lines as observations.
        if not (str(row.get("TM", "")).isdigit() and str(row.get("STN", "")).isdigit()):
            continue
        records.append(row)
    return records


def fetch_period_data(stn: int, start_tm: str, end_tm: str, auth_key: str,
                      max_retries: int = 3, timeout: int = 60) -> list[dict[str, Any]]:
    params = {"tm1": start_tm, "tm2": end_tm, "stn": str(stn), "help": "0", "authKey": auth_key}
    req = urllib.request.Request(
        API_URL + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "WeatherElfs-AsosCollector/1.1"},
    )
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("euc-kr", errors="replace")
            return parse_kma_text_data(body)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PermissionError(f"ASOS API 인증/권한 오류: HTTP {exc.code}") from exc
            if attempt == max_retries or exc.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            if attempt == max_retries:
                raise
        time.sleep(2 * attempt)
    return []


def generate_monthly_chunks(start_dt: datetime, end_dt: datetime):
    chunks = []
    current = start_dt
    while current <= end_dt:
        end = min(current + timedelta(days=30), end_dt)
        chunks.append((current, end))
        current = end + timedelta(hours=1)
    return chunks


def get_realtime_window(hours: int = 3) -> tuple[str, str]:
    now = datetime.now()
    latest = (now - timedelta(hours=1) if now.minute < 15 else now).replace(
        minute=0, second=0, microsecond=0)
    start = latest - timedelta(hours=hours - 1)
    return start.strftime("%Y%m%d%H%M"), latest.strftime("%Y%m%d%H%M")


def seconds_until_next_fetch(target_minute: int = 15) -> float:
    now = datetime.now()
    next_time = now.replace(minute=target_minute, second=0, microsecond=0)
    if now >= next_time:
        next_time += timedelta(hours=1)
    return max((next_time - now).total_seconds(), 1)


def collect_asos_dataset(start_tm: str, end_tm: str, auth_key: str,
                         max_records: int = 20000) -> list[dict[str, Any]]:
    start = datetime.strptime(start_tm, "%Y%m%d%H%M")
    end = datetime.strptime(end_tm, "%Y%m%d%H%M")
    if start > end:
        raise ValueError("--start must be earlier than or equal to --end")
    chunks = generate_monthly_chunks(start, end)
    all_data = []
    print(f"[ASOS] 수집 기간(KST): {start_tm} ~ {end_tm}", flush=True)
    for stn, name in STATIONS.items():
        count = 0
        for chunk_start, chunk_end in chunks:
            if len(all_data) >= max_records:
                print(f"[안전 제약] 최대 {max_records:,}개 레코드 도달")
                return all_data
            a = chunk_start.strftime("%Y%m%d%H%M")
            b = chunk_end.strftime("%Y%m%d%H%M")
            try:
                records = fetch_period_data(stn, a, b, auth_key)
            except PermissionError:
                raise
            except Exception as exc:
                print(f"[오류] {name} {a}~{b}: {exc}", file=sys.stderr)
                continue
            for record in records:
                if str(record.get("STN")) != str(stn):
                    continue
                record["station_name"] = name
                all_data.append(record)
                count += 1
                if len(all_data) >= max_records:
                    break
        print(f"[{name} {stn}] {count:,}건 수집", flush=True)
    return all_data


def format_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=FINAL_COLUMNS)
    df = pd.DataFrame(records)
    df["TM"] = pd.to_datetime(df["TM"], format="%Y%m%d%H%M", errors="coerce")
    df["STN"] = pd.to_numeric(df["STN"], errors="coerce")
    for col in NUMERIC_SOURCE:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns=COLUMN_MAPPING)
    for col in FINAL_COLUMNS:
        if col not in df:
            df[col] = pd.NA
    df = df[FINAL_COLUMNS].dropna(subset=["지점", "일시"])
    return df.sort_values(["station_name", "일시"]).reset_index(drop=True)


def save_to_csv(df: pd.DataFrame, output: Path, mode: str) -> None:
    if df.empty:
        print("[저장 생략] 유효한 관측 데이터 없음")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    if mode == "append" and output.exists():
        # Read errors are fatal; never silently overwrite an existing file.
        existing = pd.read_csv(output, encoding="utf-8-sig")
        missing = set(FINAL_COLUMNS) - set(existing.columns)
        if missing:
            raise ValueError(f"기존 CSV 컬럼 불일치: {sorted(missing)}")
        existing = existing[FINAL_COLUMNS]
        df = pd.concat([existing, df], ignore_index=True)
    df["일시"] = pd.to_datetime(df["일시"], errors="coerce")
    df["지점"] = pd.to_numeric(df["지점"], errors="coerce")
    df = (df.dropna(subset=["지점", "일시"])
          .drop_duplicates(subset=["지점", "일시"], keep="last")
          .sort_values(["station_name", "일시"]).reset_index(drop=True))
    # Atomic replacement avoids leaving a partially written CSV after a crash.
    temporary = output.with_name(output.name + ".tmp")
    try:
        df.to_csv(temporary, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S")
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"[저장 완료] {len(df):,}건 → {output.resolve()}")
    print(f"[최신 관측(KST)] {df['일시'].max()}")
    print("[지점별 최신 관측(KST)]")
    print(df.groupby("station_name")["일시"].max().to_string())


def execute_cycle(start: str, end: str, auth_key: str, max_records: int,
                  output: Path, mode: str) -> bool:
    records = collect_asos_dataset(start, end, auth_key, max_records)
    if not records:
        print("[결과] 수집된 관측 데이터 없음", file=sys.stderr)
        return False
    df = format_dataframe(records)
    if df.empty:
        print("[결과] 유효한 관측 데이터 없음", file=sys.stderr)
        return False
    save_to_csv(df, output, mode)
    print("[미리보기]")
    print(df[["지점", "station_name", "일시", "기온(°C)", "시정(10m)", "습도(%)"]].tail(5).to_string(index=False))
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ASOS 시간자료 수집: 기간/최신/반복")
    parser.add_argument("--realtime", "-r", action="store_true", help="현재 시각 기준 최근 N시간 조회")
    parser.add_argument("--hours", type=int, default=3, help="최신 조회 범위(시간), 기본 3")
    parser.add_argument("--loop", action="store_true", help="시작 즉시 1회, 이후 매시 15분 반복")
    parser.add_argument("--save-mode", choices=["append", "overwrite"], default=None)
    parser.add_argument("--start", "-s", default="202601010000", help="KST YYYYMMDDHHMM")
    parser.add_argument("--end", "-e", default=datetime.now().strftime("%Y%m%d%H00"), help="KST YYYYMMDDHHMM")
    parser.add_argument("--max-records", "-m", type=int, default=20000, help="실행 1회 최대 저장 대상 레코드 수")
    parser.add_argument("--output-dir", "-o", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-filename", default=DEFAULT_OUTPUT_FILENAME)
    parser.add_argument("--auth-key", "-k", default=None, help="가급적 KMA_AUTH_KEY 환경변수 사용")
    args = parser.parse_args(argv)
    if args.hours < 1 or args.max_records < 1:
        parser.error("--hours, --max-records must be >= 1")
    auth_key = args.auth_key or os.environ.get("KMA_AUTH_KEY", "")
    if not auth_key:
        print("[오류] KMA_AUTH_KEY 환경변수를 설정하세요.", file=sys.stderr)
        return 1
    output = Path(args.output_dir) / args.output_filename
    mode = args.save_mode or ("append" if (args.realtime or args.loop) else "overwrite")
    try:
        if args.loop:
            print("[반복 모드] 시작 즉시 실행, 이후 매시 15분 재조회 (종료: Ctrl+C)")
            while True:
                start, end = get_realtime_window(args.hours)
                try:
                    execute_cycle(start, end, auth_key, args.max_records, output, "append")
                except PermissionError:
                    raise
                except Exception as exc:
                    print(f"[오류] 수집 주기 실패: {exc}", file=sys.stderr)
                delay = seconds_until_next_fetch()
                print(f"[대기] 다음 수집까지 약 {delay / 60:.1f}분")
                time.sleep(delay)
        if args.realtime:
            start, end = get_realtime_window(args.hours)
        else:
            start, end = args.start, args.end
        return 0 if execute_cycle(start, end, auth_key, args.max_records, output, mode) else 1
    except KeyboardInterrupt:
        print("\n[종료] 사용자 중단")
        return 0
    except Exception as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
