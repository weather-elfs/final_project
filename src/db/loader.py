"""기상청 ASOS, 해양기상부이, 에어코리아 CSV 원천 데이터 통합 DB 대량 적재 모듈.

data/raw/ 경로의 CSV 파일들을 읽어 PostgreSQL 원천 테이블로 초고속 적재한다.
- 3대 도메인(ASOS, BUOY, AIRKOREA) 테이블 및 인덱스 자동 생성 (IF NOT EXISTS)
- 결측치는 0으로 대치하지 않고 순수 NULL로 유지
- 복합 기본키 기준 중복 관측치는 ON CONFLICT DO NOTHING 처리
"""

from pathlib import Path
from typing import Any

import pandas as pd
from psycopg2.extras import execute_values

from src.db.connection import get_raw_connection

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "raw"

# ASOS 지점 코드 매핑
ASOS_STN_KO_MAP = {"102": "백령도", "112": "인천", "201": "강화도"}

# 1. ASOS 컬럼 매핑
ASOS_MAPPING = {
    "일시": "tm",
    "지점": "stn_id",
    "station_name": "stn_ko",
    "지점명": "stn_ko",
    "기온(°C)": "temp",
    "강수량(mm)": "rainfall",
    "풍속(m/s)": "wind_speed",
    "풍향(16방위)": "wind_dir",
    "습도(%)": "humidity",
    "증기압(hPa)": "vapor_press",
    "이슬점온도(°C)": "dew_point",
    "현지기압(hPa)": "local_press",
    "해면기압(hPa)": "sea_press",
    "일조(hr)": "sunshine",
    "일사(MJ/m2)": "solar_radiation",
    "적설(cm)": "snow",
    "지면온도(°C)": "ground_temp",
    "시정(10m)": "visibility",
    "전운량(10분위)": "cloud",
    "중하층운량(10분위)": "low_middle_cloud",
}

# 2. 부이 컬럼 매핑
BUOY_MAPPING = {
    "일시": "tm",
    "지점": "stn_id",
    "풍속(m/s)": "wind_speed",
    "풍향(deg)": "wind_dir",
    "GUST풍속(m/s)": "gust_speed",
    "현지기압(hPa)": "local_press",
    "습도(%)": "humidity",
    "기온(°C)": "temp",
    "수온(°C)": "water_temp",
    "최대파고(m)": "max_wave_height",
    "유의파고(m)": "sig_wave_height",
    "평균파고(m)": "avg_wave_height",
    "파주기(sec)": "wave_period",
    "파향(deg)": "wave_dir",
}

# 3. 에어코리아 컬럼 매핑
AIR_MAPPING = {
    "날짜": "tm",
    "시도": "sido",
    "측정소명": "station_name",
    "측정소코드": "station_code",
    "아황산가스": "so2",
    "일산화탄소": "co",
    "오존": "o3",
    "이산화질소": "no2",
    "PM10": "pm10",
    "PM2.5": "pm25",
}


INT_COLS = {
    "wind_dir",
    "visibility",
    "cloud",
    "low_middle_cloud",
    "wave_dir",
}

DDL_INIT_SQL = """
-- 1. ASOS 테이블
CREATE TABLE IF NOT EXISTS raw_weather_asos (
    tm                  TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    stn_id              VARCHAR(10) NOT NULL,
    stn_ko              VARCHAR(50),
    temp                NUMERIC(4, 1),
    rainfall            NUMERIC(5, 1),
    wind_speed          NUMERIC(4, 1),
    wind_dir            INTEGER,
    humidity            NUMERIC(4, 1),
    vapor_press         NUMERIC(5, 1),
    dew_point           NUMERIC(4, 1),
    local_press         NUMERIC(6, 1),
    sea_press           NUMERIC(6, 1),
    sunshine            NUMERIC(4, 1),
    solar_radiation     NUMERIC(5, 2),
    snow                NUMERIC(5, 1),
    ground_temp         NUMERIC(4, 1),
    visibility          INTEGER,
    cloud               INTEGER,
    low_middle_cloud    INTEGER,
    created_at          TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_raw_weather_asos PRIMARY KEY (tm, stn_id)
);
CREATE INDEX IF NOT EXISTS idx_asos_tm ON raw_weather_asos (tm);
CREATE INDEX IF NOT EXISTS idx_asos_stn ON raw_weather_asos (stn_id);

-- 2. 해양기상부이 테이블
-- 2. 해양기상부이 테이블
CREATE TABLE IF NOT EXISTS raw_weather_buoy (
    tm                  TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    stn_id              VARCHAR(10) NOT NULL,
    wind_speed          NUMERIC(4, 1),
    wind_dir            INTEGER,
    gust_speed          NUMERIC(4, 1),
    local_press         NUMERIC(6, 1),
    humidity            NUMERIC(4, 1),
    temp                NUMERIC(4, 1),
    water_temp          NUMERIC(4, 1),
    max_wave_height     NUMERIC(4, 1),
    sig_wave_height     NUMERIC(4, 1),
    avg_wave_height     NUMERIC(4, 1),
    wave_period         NUMERIC(4, 1),
    wave_dir            INTEGER,
    created_at          TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_raw_weather_buoy PRIMARY KEY (tm, stn_id)
);
CREATE INDEX IF NOT EXISTS idx_buoy_tm ON raw_weather_buoy (tm);
CREATE INDEX IF NOT EXISTS idx_buoy_stn ON raw_weather_buoy (stn_id);

-- 3. 에어코리아 대기질 테이블
CREATE TABLE IF NOT EXISTS raw_air_quality (
    tm                  TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    station_name        VARCHAR(50) NOT NULL,
    station_code        VARCHAR(20),
    sido                VARCHAR(50),
    so2                 NUMERIC(6, 4),
    co                  NUMERIC(5, 2),
    o3                  NUMERIC(6, 4),
    no2                 NUMERIC(6, 4),
    pm10                NUMERIC(6, 1),
    pm25                NUMERIC(6, 1),
    created_at          TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_raw_air_quality PRIMARY KEY (tm, station_name)
);
CREATE INDEX IF NOT EXISTS idx_air_tm ON raw_air_quality (tm);
CREATE INDEX IF NOT EXISTS idx_air_station ON raw_air_quality (station_name);
"""


def init_tables(conn) -> None:
    """원천 테이블 3개 및 인덱스를 생성한다."""
    with conn.cursor() as cur:
        cur.execute(DDL_INIT_SQL)
    conn.commit()
    print("[테이블 확인] ASOS, 부이, 에어코리아 테이블 준비 완료")


def sanitize_val(col_name: str, val: Any) -> Any:
    """결측치는 SQL NULL(None)로 변환하고 정수 컬럼은 안전하게 캐스팅한다."""
    if pd.isna(val) or val == "" or val is None:
        return None
    if col_name in INT_COLS:
        try:
            return int(round(float(val)))
        except (ValueError, TypeError):
            return None
    return val


def load_asos_to_db(conn) -> None:
    """ASOS 데이터(2015~2025 과거본 + 2026 실시간 수집본)를 적재한다."""
    csv_files = [
        DATA_DIR / "asos_hourly_2015_2025_HR.csv",
        DATA_DIR / "asos_hourly_incheon_ganghwa_baengnyeong_2026.csv",
    ]
    target_cols = [
        "tm",
        "stn_id",
        "stn_ko",
        "temp",
        "rainfall",
        "wind_speed",
        "wind_dir",
        "humidity",
        "vapor_press",
        "dew_point",
        "local_press",
        "sea_press",
        "sunshine",
        "solar_radiation",
        "snow",
        "ground_temp",
        "visibility",
        "cloud",
        "low_middle_cloud",
    ]
    insert_query = f"""
        INSERT INTO raw_weather_asos ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (tm, stn_id) DO NOTHING;
    """
    with conn.cursor() as cursor:
        for file_path in csv_files:
            if not file_path.exists():
                continue
            df = pd.read_csv(file_path, low_memory=False)
            available_src = [c for c in ASOS_MAPPING.keys() if c in df.columns]
            df_filtered = df[available_src].rename(columns=ASOS_MAPPING)
            df_filtered["tm"] = pd.to_datetime(df_filtered["tm"])
            df_filtered["stn_id"] = df_filtered["stn_id"].astype(str)

            if (
                "stn_ko" not in df_filtered.columns
                or df_filtered["stn_ko"].isna().all()
            ):
                df_filtered["stn_ko"] = df_filtered["stn_id"].map(ASOS_STN_KO_MAP)
            else:
                df_filtered["stn_ko"] = df_filtered["stn_ko"].fillna(
                    df_filtered["stn_id"].map(ASOS_STN_KO_MAP)
                )

            for col in target_cols:
                if col not in df_filtered.columns:
                    df_filtered[col] = None

            df_filtered = df_filtered.drop_duplicates(subset=["tm", "stn_id"])
            df_ordered = df_filtered[target_cols]
            records = [
                tuple(sanitize_val(col, val) for col, val in zip(target_cols, row))
                for row in df_ordered.itertuples(index=False, name=None)
            ]
            execute_values(cursor, insert_query, records, page_size=10000)
            conn.commit()


def load_buoy_to_db(conn) -> None:
    """해양기상부이 CSV 데이터를 적재한다."""
    file_path = DATA_DIR / "MARINE_BUOY_ALL_STATIONS_2016_2026.csv"
    if not file_path.exists():
        return
    target_cols = [
        "tm",
        "stn_id",
        "wind_speed",
        "wind_dir",
        "gust_speed",
        "local_press",
        "humidity",
        "temp",
        "water_temp",
        "max_wave_height",
        "sig_wave_height",
        "avg_wave_height",
        "wave_period",
        "wave_dir",
    ]
    insert_query = f"""
        INSERT INTO raw_weather_buoy ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (tm, stn_id) DO NOTHING;
    """
    with conn.cursor() as cursor:
        df = pd.read_csv(file_path, low_memory=False)
        df_filtered = df.rename(columns=BUOY_MAPPING)
        df_filtered["tm"] = pd.to_datetime(df_filtered["tm"])
        df_filtered["stn_id"] = df_filtered["stn_id"].astype(str)

        for col in target_cols:
            if col not in df_filtered.columns:
                df_filtered[col] = None

        df_filtered = df_filtered.drop_duplicates(subset=["tm", "stn_id"])
        df_ordered = df_filtered[target_cols]
        records = [
            tuple(sanitize_val(col, val) for col, val in zip(target_cols, row))
            for row in df_ordered.itertuples(index=False, name=None)
        ]
        execute_values(cursor, insert_query, records, page_size=10000)
        conn.commit()


def load_airkorea_to_db(conn) -> None:
    """에어코리아 최종 대기질 CSV 데이터를 DB에 적재한다."""
    file_path = DATA_DIR / "에어코리아_최종데이터.csv"
    if not file_path.exists():
        print(f"[경고] 에어코리아 파일 없음: {file_path}")
        return

    target_cols = [
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
    insert_query = f"""
        INSERT INTO raw_air_quality ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (tm, station_name) DO NOTHING;
    """

    with conn.cursor() as cursor:
        print(f"[에어코리아 적재 시작] {file_path.name}")
        # 인코딩 자동 호환
        for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False)
                break
            except Exception:
                continue

        # 엑셀 변환 빈 끝 행 제거
        if "날짜" in df.columns:
            df = df[df["날짜"].notna() & (df["날짜"] != "")]

        df_filtered = df.rename(columns=AIR_MAPPING)
        df_filtered["tm"] = pd.to_datetime(df_filtered["tm"])
        df_filtered["station_name"] = df_filtered["station_name"].astype(str)

        if "station_code" in df_filtered.columns:
            df_filtered["station_code"] = (
                pd.to_numeric(df_filtered["station_code"], errors="coerce")
                .fillna(0)
                .astype(int)
                .astype(str)
            )

        for col in target_cols:
            if col not in df_filtered.columns:
                df_filtered[col] = None

        df_filtered = df_filtered.drop_duplicates(subset=["tm", "station_name"])
        df_ordered = df_filtered[target_cols]

        records = [
            tuple(sanitize_val(col, val) for col, val in zip(target_cols, row))
            for row in df_ordered.itertuples(index=False, name=None)
        ]

        execute_values(cursor, insert_query, records, page_size=10000)
        conn.commit()
        print(f"[에어코리아 완료] 에어코리아 대기질 적재 완료 ({len(records):,} 건)")


def main():
    conn = get_raw_connection()
    try:
        init_tables(conn)
        load_asos_to_db(conn)  # 기존 적재본 자동 스킵
        load_buoy_to_db(conn)  # 기존 적재본 자동 스킵
        load_airkorea_to_db(conn)  # 에어코리아 신규 적재
        print("\n[전체 완료] 모든 원천 데이터 적재가 완료되었습니다.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
