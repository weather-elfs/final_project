"""[백엔드 1] Ncloud DB mart_base_anchor -> data/processed/mart_base_anchor.parquet 고속 추출 스크립트."""

from pathlib import Path

import pandas as pd

from src.db.connection import get_raw_connection

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "processed"
OUTPUT_FILE = OUTPUT_DIR / "mart_base_anchor.parquet"


def export_anchor_parquet():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/3] Ncloud PostgreSQL DB 연결 중...")
    conn = get_raw_connection()

    query = """
        SELECT *
        FROM mart_base_anchor
        ORDER BY tm ASC, stn_id ASC;
    """

    try:
        print("[2/3] mart_base_anchor 뷰 데이터 조회 중 (약 10만 건)...")
        df = pd.read_sql(query, conn)

        # 일시 datetime 형변환
        df["tm"] = pd.to_datetime(df["tm"])

        # PostgreSQL numeric -> float64 자동 캐스팅 (머신러닝 최적화)
        numeric_cols = df.select_dtypes(include=["object"]).columns
        for col in numeric_cols:
            if col not in ["stn_id", "stn_name", "buoy_stn_id", "air_station_name"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        print(f" -> 조회 완료: {len(df):,} 행, {len(df.columns)} 개 컬럼")

        print(f"[3/3] Parquet 파일 압축 저장 중 -> {OUTPUT_FILE} ...")
        # snappy 압축 적용하여 pyarrow 엔진으로 저장
        df.to_parquet(OUTPUT_FILE, engine="pyarrow", compression="snappy", index=False)

        size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
        print(f"\n[성공] Parquet 스냅샷 생성 완료!")
        print(f" - 저장 경로: {OUTPUT_FILE}")
        print(f" - 파일 용량: {size_mb:.2f} MB (초경량 압축)")
        print(f" - 기간 범위: {df['tm'].min()} ~ {df['tm'].max()}")
        print(f" - 관측 지점: {df['stn_name'].unique().tolist()}")
        print(f" - 지점별 건수:\n{df['stn_name'].value_counts().to_string()}")

        # 핵심 타겟 결측치 검증
        target_nulls = df[["visibility_km", "pm25", "pm10"]].isna().sum().to_dict()
        print(f" - 타겟 결측치 현황: {target_nulls} (0건이면 정상)")

    finally:
        conn.close()


if __name__ == "__main__":
    export_anchor_parquet()
