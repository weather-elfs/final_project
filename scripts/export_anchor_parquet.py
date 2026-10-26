"""[백엔드 1] Ncloud DB 무누수 관측 마트 및 48시간 단기예보 전용 마트 Parquet 고속 추출 스크립트.

DB 뷰 데이터를 임의로 대치·변형하지 않고, 순수 원본 형태 그대로 조회하여
머신러닝 학습 및 재현용 Snappy 압축 Parquet 스냅샷으로 저장한다.
(결측치 대치 및 이상치 필터링은 모델 파이프라인에서 전담)
"""

import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd

from src.db.connection import get_raw_connection

OUTPUT_DIR = BASE_DIR / "data" / "processed"
OBS_OUTPUT_FILE = OUTPUT_DIR / "mart_tide_anchor_obs.parquet"
OBS_FIXED_OUTPUT_FILE = OUTPUT_DIR / "mart_tide_anchor_obs_fixed.parquet"
FCST_OUTPUT_FILE = OUTPUT_DIR / "mart_forecast_pit_48h.parquet"


def export_observation_mart(conn) -> None:
    """1. 순수 관측 마트(mart_tide_anchor_obs)를 원본 그대로 Parquet으로 추출한다."""
    print("\n" + "=" * 70)
    print("[1/2] 순수 관측 마트 (mart_tide_anchor_obs) 추출 시작...")
    print("=" * 70)

    query_obs = """
        SELECT *
        FROM public.mart_tide_anchor_obs
        ORDER BY tm ASC, stn_id ASC;
    """
    df_obs = pd.read_sql(query_obs, conn)

    # 1. 일시 datetime 형변환
    df_obs["tm"] = pd.to_datetime(df_obs["tm"])

    # 2. 수치형 컬럼 최적화 캐스팅 (문자열 컬럼 제외하고 수치형으로 보정)
    text_cols = {"stn_id", "stn_name", "buoy_stn_id", "air_station_name"}
    numeric_cols = [
        c
        for c in df_obs.select_dtypes(include=["object"]).columns
        if c not in text_cols
    ]
    for col in numeric_cols:
        df_obs[col] = pd.to_numeric(df_obs[col], errors="coerce")

    # (결측치 임의 대치 로직 제거: 모델 전처리 파이프라인에서 전담 처리)

    print(f" -> 조회 완료: {len(df_obs):,} 행, {len(df_obs.columns)} 개 컬럼")
    print(f" -> Parquet 압축 저장 중 -> {OBS_OUTPUT_FILE} ...")
    df_obs.to_parquet(
        OBS_OUTPUT_FILE, engine="pyarrow", compression="snappy", index=False
    )

    # obs_fixed 호환 파일 동시 생성
    shutil.copy2(OBS_OUTPUT_FILE, OBS_FIXED_OUTPUT_FILE)

    size_mb = OBS_OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print("[성공] 관측 마트 Parquet 생성 및 호환 사본 동기화 완료!")
    print(f" - 저장 경로 1: {OBS_OUTPUT_FILE} ({size_mb:.2f} MB)")
    print(f" - 저장 경로 2: {OBS_FIXED_OUTPUT_FILE}")
    print(f" - 기간 범위: {df_obs['tm'].min()} ~ {df_obs['tm'].max()}")


def export_forecast_pit_mart(conn) -> None:
    """2. 48시간 Point-in-Time 단기예보 마트(mart_forecast_pit_48h)를 원본 그대로 Parquet으로 추출한다."""
    print("\n" + "=" * 70)
    print("[2/2] 48시간 무누수 단기예보 마트 (mart_forecast_pit_48h) 추출 시작...")
    print("=" * 70)

    query_fcst = """
        SELECT 
            stn_id,
            tm,
            lead_h,
            target_tm,
            fcst_temp,
            fcst_humidity,
            fcst_wind_speed,
            fcst_wind_dir,
            fcst_wind_dir_sin,
            fcst_wind_dir_cos,
            fcst_precipitation,
            fcst_pop,
            fcst_pty,
            fcst_sky,
            fcst_pm25_grade,
            fcst_base_time
        FROM public.mart_forecast_pit_48h
        ORDER BY tm ASC, stn_id ASC, lead_h ASC;
    """
    df_fcst = pd.read_sql(query_fcst, conn)

    # 1. 일시 datetime 형변환
    df_fcst["tm"] = pd.to_datetime(df_fcst["tm"])
    df_fcst["target_tm"] = pd.to_datetime(df_fcst["target_tm"])
    df_fcst["fcst_base_time"] = pd.to_datetime(df_fcst["fcst_base_time"])
    df_fcst["stn_id"] = df_fcst["stn_id"].astype(str)

    # (예보 강수량 결측 대치 로직 제거: 모델 전처리 파이프라인에서 전담 처리)

    print(f" -> 조회 완료: {len(df_fcst):,} 행, {len(df_fcst.columns)} 개 컬럼")

    # 2. 인과성 누수 전수 검증 (Audit)
    leakage_count = (df_fcst["fcst_base_time"] > df_fcst["tm"]).sum()
    print(f" -> 인과성 누수 전수 검증 결과: {leakage_count:,} 건 (0건이어야 정상)")

    print(f" -> Parquet 압축 저장 중 -> {FCST_OUTPUT_FILE} ...")
    df_fcst.to_parquet(
        FCST_OUTPUT_FILE, engine="pyarrow", compression="snappy", index=False
    )

    size_mb = FCST_OUTPUT_FILE.stat().st_size / (1024 * 1024)
    print("[성공] 단기예보 전용 Parquet 생성 완료!")
    print(f" - 저장 경로: {FCST_OUTPUT_FILE} ({size_mb:.2f} MB)")
    print(f" - 리드타임 범위: {df_fcst['lead_h'].min()}h ~ {df_fcst['lead_h'].max()}h")


def export_all_marts() -> None:
    """Ncloud DB에서 관측 마트 및 단기예보 전용 마트를 일괄 추출한다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Ncloud PostgreSQL DB 연결 중...")
    conn = get_raw_connection()

    try:
        export_observation_mart(conn)
        export_forecast_pit_mart(conn)
        print("\n" + "=" * 70)
        print("[최종 완료] 2종의 무누수 Parquet 스냅샷이 성공적으로 생성되었습니다.")
        print("=" * 70)
    finally:
        conn.close()


if __name__ == "__main__":
    export_all_marts()
