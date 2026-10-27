-- 두 대상 관측소의 정각 관측값을 원본 형태로 보존하는 테이블이다.
CREATE TABLE IF NOT EXISTS public.raw_weather_pm1 (
    obsrr_tpcd varchar(4) NOT NULL,
    obsrr_nm varchar(50) NOT NULL,
    obsrt_dtm char(12) NOT NULL,
    observed_at_utc timestamptz NOT NULL,
    obsrt_tmprt numeric,
    obsrt_hmdt numeric,
    obsrt_wndrc_val numeric,
    obsrt_ws numeric,
    obsrt_pm01_val numeric,
    obsrt_pm25_val numeric,
    obsrt_pm10_val numeric,
    avoc_obsrt_pm01_val numeric,
    avoc_obsrt_pm25_val numeric,
    avoc_obsrt_pm10_val numeric,
    ingest_run_id uuid NOT NULL,
    collector_version varchar(80) NOT NULL,
    ingested_at timestamptz NOT NULL,
    CONSTRAINT raw_weather_pm1_pkey PRIMARY KEY (obsrr_tpcd, obsrt_dtm),
    -- 관측소 코드와 이름이 서로 어긋난 행은 저장하지 않는다.
    CONSTRAINT raw_weather_pm1_station_check CHECK (
        (obsrr_tpcd = '0383' AND obsrr_nm = '강화_숲2')
        OR (obsrr_tpcd = '0151' AND obsrr_nm = '인천_산단')
    ),
    -- 결측은 NULL로 허용하지만 계산 결과를 왜곡하는 비유한 수는 거부한다.
    CONSTRAINT raw_weather_pm1_finite_numeric_check CHECK (
        (obsrt_tmprt IS NULL OR obsrt_tmprt::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (obsrt_hmdt IS NULL OR obsrt_hmdt::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (obsrt_wndrc_val IS NULL OR obsrt_wndrc_val::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (obsrt_ws IS NULL OR obsrt_ws::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (obsrt_pm01_val IS NULL OR obsrt_pm01_val::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (obsrt_pm25_val IS NULL OR obsrt_pm25_val::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (obsrt_pm10_val IS NULL OR obsrt_pm10_val::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (avoc_obsrt_pm01_val IS NULL OR avoc_obsrt_pm01_val::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (avoc_obsrt_pm25_val IS NULL OR avoc_obsrt_pm25_val::text NOT IN ('NaN', 'Infinity', '-Infinity'))
        AND (avoc_obsrt_pm10_val IS NULL OR avoc_obsrt_pm10_val::text NOT IN ('NaN', 'Infinity', '-Infinity'))
    ),
    -- API 요청·저장은 YYYYMMDDHH00 형식의 정각 데이터만 허용한다.
    CONSTRAINT raw_weather_pm1_dtm_check CHECK (
        obsrt_dtm ~ '^[0-9]{12}$'
        AND substring(obsrt_dtm FROM 9 FOR 2)::integer BETWEEN 0 AND 23
        AND substring(obsrt_dtm FROM 11 FOR 2) = '00'
    )
);

CREATE INDEX IF NOT EXISTS raw_weather_pm1_dtm_station_idx
    ON public.raw_weather_pm1 (obsrt_dtm, obsrr_tpcd);

CREATE INDEX IF NOT EXISTS raw_weather_pm1_observed_at_utc_idx
    ON public.raw_weather_pm1 (observed_at_utc);

-- 장애 후 마지막 성공 지점부터 다시 시작하기 위한 수집 상태 테이블이다.
CREATE TABLE IF NOT EXISTS public.weather_ingest_state (
    source_name varchar(80) PRIMARY KEY,
    next_start_dtm char(12) NOT NULL,
    last_success_start_dtm char(12),
    last_success_end_dtm char(12),
    source_timezone varchar(6) NOT NULL,
    sync_lag_hours integer NOT NULL,
    schema_version smallint NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT weather_ingest_state_next_check CHECK (
        next_start_dtm ~ '^[0-9]{10}00$'
    ),
    CONSTRAINT weather_ingest_state_success_pair_check CHECK (
        (last_success_start_dtm IS NULL AND last_success_end_dtm IS NULL)
        OR (
            last_success_start_dtm ~ '^[0-9]{10}00$'
            AND last_success_end_dtm ~ '^[0-9]{10}00$'
            AND last_success_start_dtm <= last_success_end_dtm
            AND next_start_dtm > last_success_start_dtm
        )
    ),
    CONSTRAINT weather_ingest_state_timezone_check CHECK (
        source_timezone ~ '^[+-][0-9]{2}:[0-9]{2}$'
    ),
    CONSTRAINT weather_ingest_state_lag_check CHECK (sync_lag_hours >= 0),
    CONSTRAINT weather_ingest_state_schema_check CHECK (schema_version = 1)
);

-- 명시적으로 권한을 받은 수집·내보내기 계정만 테이블을 사용할 수 있다.
REVOKE ALL ON public.raw_weather_pm1 FROM PUBLIC;
REVOKE ALL ON public.weather_ingest_state FROM PUBLIC;
