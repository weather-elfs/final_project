"""기상청 ASOS, 조위관측소, 에어코리아 대기질, 단기예보, PM2.5 권역예보 원천 DB 대량 적재 모듈.

data/raw/ 경로의 CSV 파일들을 읽어 PostgreSQL 원천 테이블로 초고속 적재한다.
- 5대 도메인 테이블 및 인덱스 자동 생성 (IF NOT EXISTS)
  1. raw_weather_asos (기상청 지상종관기상 관측)
  2. raw_tide_observatory (국립해양조사원 조위관측소/해양과학기지 관측)
  3. raw_air_quality (에어코리아 확정 대기질 관측)
  4. tb_kma_short_forecast (기상청 단기예보)
  5. raw_air_pm25_forecast (에어코리아 PM2.5 권역별 예보 등급)
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

# 2. 에어코리아 대기질 컬럼 매핑
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

# 3. 조위관측소 컬럼 매핑
TIDE_MAPPING = {
    "관측일자": "tm",
    "tm": "tm",
    "stn_name": "stn_name",
    "지점명": "stn_name",
    "수온(℃)": "water_temp",
    "염분(PSU)": "salinity",
    "기온(℃)": "temp",
    "기압(hPa)": "air_press",
    "풍속(m/s)": "wind_speed",
    "풍향(deg)": "wind_dir",
    "최대순간풍속(m/s)": "gust_speed",
}

# 4. 단기예보 컬럼 매핑
KMA_MAPPING = {
    "동": "dong",
    "dong": "dong",
    "발표일시": "base_time_kst",
    "base_time_kst": "base_time_kst",
    "예보시간": "fcst_lead_time",
    "fcst_lead_time": "fcst_lead_time",
    "예보대상일시": "fcst_time_kst",
    "fcst_time_kst": "fcst_time_kst",
    "1시간강수량": "pcp_1h",
    "pcp_1h": "pcp_1h",
    "1시간기온": "tmp_1h",
    "tmp_1h": "tmp_1h",
    "1시간적설": "sno_1h",
    "sno_1h": "sno_1h",
    "강수형태": "pty",
    "pty": "pty",
    "강수확률": "pop",
    "pop": "pop",
    "남북바람성분": "vvv",
    "vvv": "vvv",
    "동서바람성분": "uuu",
    "uuu": "uuu",
    "습도": "reh",
    "reh": "reh",
    "풍속": "wsd",
    "wsd": "wsd",
    "풍향": "vec",
    "vec": "vec",
    "하늘상태": "sky",
    "sky": "sky",
}

# 5. PM2.5 권역예보 컬럼 매핑
PM25_FCST_MAPPING = {
    "announce_time": "announce_time",
    "target_date": "target_date",
    "fcst_pm25_grade": "fcst_pm25_grade",
}

INT_COLS = {
    "wind_dir",
    "visibility",
    "cloud",
    "low_middle_cloud",
    "fcst_lead_time",
    "pty",
    "pop",
    "reh",
    "sky",
    "fcst_pm25_grade",
}

DDL_INIT_SQL = """
-- 1. ASOS 테이블
CREATE TABLE IF NOT EXISTS public.raw_weather_asos (
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
CREATE INDEX IF NOT EXISTS idx_asos_tm ON public.raw_weather_asos (tm);
CREATE INDEX IF NOT EXISTS idx_asos_stn ON public.raw_weather_asos (stn_id);

-- 2. 조위관측소 테이블 (해양기상부이 대체)
CREATE TABLE IF NOT EXISTS public.raw_tide_observatory (
    tm                  TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    stn_name            VARCHAR(50) NOT NULL,
    water_temp          NUMERIC(5, 2),
    salinity            NUMERIC(5, 2),
    temp                NUMERIC(5, 2),
    air_press           NUMERIC(6, 2),
    wind_speed          NUMERIC(5, 2),
    wind_dir            NUMERIC(5, 1),
    gust_speed          NUMERIC(5, 2),
    created_at          TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_raw_tide_observatory PRIMARY KEY (stn_name, tm)
);
CREATE INDEX IF NOT EXISTS idx_raw_tide_tm_stn ON public.raw_tide_observatory (tm ASC, stn_name ASC);

-- 3. 에어코리아 대기질 테이블
CREATE TABLE IF NOT EXISTS public.raw_air_quality (
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
CREATE INDEX IF NOT EXISTS idx_air_tm ON public.raw_air_quality (tm);
CREATE INDEX IF NOT EXISTS idx_air_station ON public.raw_air_quality (station_name);

-- 4. 기상청 단기예보 테이블
CREATE TABLE IF NOT EXISTS public.tb_kma_short_forecast (
    dong                VARCHAR(20) NOT NULL,
    base_time_kst       TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    fcst_lead_time      NUMERIC(5, 0) NOT NULL,
    fcst_time_kst       TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    pcp_1h              NUMERIC(6, 2),
    tmp_1h              NUMERIC(5, 2),
    sno_1h              NUMERIC(5, 2),
    pty                 NUMERIC(3, 0),
    pop                 NUMERIC(5, 0),
    vvv                 NUMERIC(6, 2),
    uuu                 NUMERIC(6, 2),
    reh                 NUMERIC(5, 0),
    wsd                 NUMERIC(5, 2),
    vec                 NUMERIC(6, 2),
    sky                 NUMERIC(3, 0),
    created_at          TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_tb_kma_short_forecast PRIMARY KEY (dong, fcst_time_kst, base_time_kst, fcst_lead_time)
);
CREATE INDEX IF NOT EXISTS idx_kma_dong_base_lead ON public.tb_kma_short_forecast (dong ASC, base_time_kst ASC, fcst_lead_time ASC);
CREATE INDEX IF NOT EXISTS idx_kma_fcst_query ON public.tb_kma_short_forecast (dong ASC, fcst_time_kst ASC, base_time_kst DESC);

-- 5. PM2.5 권역예보 등급 테이블
CREATE TABLE IF NOT EXISTS public.raw_air_pm25_forecast (
    announce_time       TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    target_date         DATE NOT NULL,
    fcst_pm25_grade     SMALLINT,
    created_at          TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_raw_air_pm25_forecast PRIMARY KEY (announce_time, target_date)
);
CREATE INDEX IF NOT EXISTS idx_air_pm25_target_announce ON public.raw_air_pm25_forecast (target_date ASC, announce_time ASC);
CREATE INDEX IF NOT EXISTS idx_raw_air_pm25_forecast_lookup ON public.raw_air_pm25_forecast (target_date ASC, announce_time DESC);
"""


def init_tables(conn) -> None:
    """원천 테이블 5개 및 인덱스를 생성한다."""
    with conn.cursor() as cur:
        cur.execute(DDL_INIT_SQL)
    conn.commit()
    print(
        "[테이블 확인] ASOS, 조위관측소, 에어코리아, 단기예보, PM2.5 권역예보 테이블 준비 완료"
    )


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
        INSERT INTO public.raw_weather_asos ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (tm, stn_id) DO NOTHING;
    """
    with conn.cursor() as cursor:
        for file_path in csv_files:
            if not file_path.exists():
                continue
            print(f"[ASOS 적재 시작] {file_path.name}")
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
            print(f"[ASOS 완료] {file_path.name} ({len(records):,} 건 적재 완료)")


def load_tide_to_db(conn) -> None:
    """국립해양조사원 조위관측소/해양과학기지 CSV 데이터를 적재한다."""
    possible_names = [
        "tide_obs_ervatory.csv",
        "tide_observatory.csv",
        "raw_tide_observatory.csv",
    ]
    file_path = None
    for name in possible_names:
        p = DATA_DIR / name
        if p.exists():
            file_path = p
            break

    if not file_path:
        print(f"[경고] 조위관측소 CSV 파일 없음: {DATA_DIR}/tide_obs_ervatory.csv")
        return

    target_cols = [
        "tm",
        "stn_name",
        "water_temp",
        "salinity",
        "temp",
        "air_press",
        "wind_speed",
        "wind_dir",
        "gust_speed",
    ]
    insert_query = f"""
        INSERT INTO public.raw_tide_observatory ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (stn_name, tm) DO NOTHING;
    """
    with conn.cursor() as cursor:
        print(f"[조위관측소 적재 시작] {file_path.name}")
        for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False)
                break
            except Exception:
                continue

        available_src = [c for c in TIDE_MAPPING.keys() if c in df.columns]
        df_filtered = df[available_src].rename(columns=TIDE_MAPPING)

        # 중복 컬럼 해소 (예: 관측일자와 tm이 둘 다 매핑된 경우 첫 번째 컬럼 채택)
        df_filtered = df_filtered.loc[:, ~df_filtered.columns.duplicated()]

        df_filtered["tm"] = pd.to_datetime(df_filtered["tm"])
        df_filtered["stn_name"] = df_filtered["stn_name"].astype(str)

        for col in target_cols:
            if col not in df_filtered.columns:
                df_filtered[col] = None

        df_filtered = df_filtered.drop_duplicates(subset=["stn_name", "tm"])
        df_ordered = df_filtered[target_cols]
        records = [
            tuple(sanitize_val(col, val) for col, val in zip(target_cols, row))
            for row in df_ordered.itertuples(index=False, name=None)
        ]
        execute_values(cursor, insert_query, records, page_size=10000)
        conn.commit()
        print(f"[조위관측소 완료] {file_path.name} ({len(records):,} 건 적재 완료)")


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
        INSERT INTO public.raw_air_quality ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (tm, station_name) DO NOTHING;
    """

    with conn.cursor() as cursor:
        print(f"[에어코리아 적재 시작] {file_path.name}")
        for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False)
                break
            except Exception:
                continue

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
        print(f"[에어코리아 완료] {file_path.name} ({len(records):,} 건 적재 완료)")


def load_kma_forecast_to_db(conn) -> None:
    """기상청 단기예보 CSV 데이터를 적재한다."""
    file_path = DATA_DIR / "kma_forecast.csv"
    if not file_path.exists():
        print(f"[경고] 기상청 단기예보 CSV 없음: {file_path}")
        return

    target_cols = [
        "dong",
        "base_time_kst",
        "fcst_lead_time",
        "fcst_time_kst",
        "pcp_1h",
        "tmp_1h",
        "sno_1h",
        "pty",
        "pop",
        "vvv",
        "uuu",
        "reh",
        "wsd",
        "vec",
        "sky",
    ]
    insert_query = f"""
        INSERT INTO public.tb_kma_short_forecast ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (dong, fcst_time_kst, base_time_kst, fcst_lead_time) DO NOTHING;
    """
    with conn.cursor() as cursor:
        print(f"[단기예보 적재 시작] {file_path.name}")
        for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False)
                break
            except Exception:
                continue

        available_src = [c for c in KMA_MAPPING.keys() if c in df.columns]
        df_filtered = df[available_src].rename(columns=KMA_MAPPING)
        df_filtered = df_filtered.loc[:, ~df_filtered.columns.duplicated()]

        df_filtered["dong"] = df_filtered["dong"].astype(str)
        df_filtered["base_time_kst"] = pd.to_datetime(df_filtered["base_time_kst"])
        df_filtered["fcst_time_kst"] = pd.to_datetime(df_filtered["fcst_time_kst"])
        df_filtered["fcst_lead_time"] = pd.to_numeric(
            df_filtered["fcst_lead_time"], errors="coerce"
        )

        for col in target_cols:
            if col not in df_filtered.columns:
                df_filtered[col] = None

        df_filtered = df_filtered.drop_duplicates(
            subset=["dong", "fcst_time_kst", "base_time_kst", "fcst_lead_time"]
        )
        df_ordered = df_filtered[target_cols]

        records = [
            tuple(sanitize_val(col, val) for col, val in zip(target_cols, row))
            for row in df_ordered.itertuples(index=False, name=None)
        ]
        execute_values(cursor, insert_query, records, page_size=10000)
        conn.commit()
        print(f"[단기예보 완료] {file_path.name} ({len(records):,} 건 적재 완료)")


def load_pm25_forecast_to_db(conn) -> None:
    """에어코리아 PM2.5 권역예보 CSV 데이터를 적재한다."""
    file_path = DATA_DIR / "airkorea_pm25_forecast.csv"
    if not file_path.exists():
        print(f"[경고] PM2.5 권역예보 CSV 없음: {file_path}")
        return

    target_cols = [
        "announce_time",
        "target_date",
        "fcst_pm25_grade",
    ]
    insert_query = f"""
        INSERT INTO public.raw_air_pm25_forecast ({", ".join(target_cols)})
        VALUES %s
        ON CONFLICT (announce_time, target_date) DO NOTHING;
    """
    with conn.cursor() as cursor:
        print(f"[PM2.5 권역예보 적재 시작] {file_path.name}")
        for enc in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False)
                break
            except Exception:
                continue

        available_src = [c for c in PM25_FCST_MAPPING.keys() if c in df.columns]
        df_filtered = df[available_src].rename(columns=PM25_FCST_MAPPING)
        df_filtered = df_filtered.loc[:, ~df_filtered.columns.duplicated()]

        df_filtered["announce_time"] = pd.to_datetime(df_filtered["announce_time"])
        df_filtered["target_date"] = pd.to_datetime(df_filtered["target_date"]).dt.date
        df_filtered["fcst_pm25_grade"] = pd.to_numeric(
            df_filtered["fcst_pm25_grade"], errors="coerce"
        )

        for col in target_cols:
            if col not in df_filtered.columns:
                df_filtered[col] = None

        df_filtered = df_filtered.drop_duplicates(
            subset=["announce_time", "target_date"]
        )
        df_ordered = df_filtered[target_cols]

        records = [
            tuple(sanitize_val(col, val) for col, val in zip(target_cols, row))
            for row in df_ordered.itertuples(index=False, name=None)
        ]
        execute_values(cursor, insert_query, records, page_size=10000)
        conn.commit()
        print(f"[PM2.5 권역예보 완료] {file_path.name} ({len(records):,} 건 적재 완료)")


def main():
    conn = get_raw_connection()
    try:
        init_tables(conn)
        load_asos_to_db(conn)  # 1. ASOS 지상기상 (기존 적재본 자동 스킵)
        load_tide_to_db(conn)  # 2. 조위관측소 (부이 대체 신규 적재)
        load_airkorea_to_db(conn)  # 3. 에어코리아 대기질 (기존 적재본 자동 스킵)
        load_kma_forecast_to_db(conn)  # 4. 기상청 단기예보 신규 적재
        load_pm25_forecast_to_db(conn)  # 5. PM2.5 권역예보 신규 적재
        print("\n[전체 완료] 모든 원천 데이터 적재가 완료되었습니다.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
