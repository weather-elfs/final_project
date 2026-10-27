"""전달된 관측+예보 튜닝형 세 모델의 입력 구성과 원 단위 출력 복원."""

import hashlib
import json
import logging
import math
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

KST = ZoneInfo("Asia/Seoul")
MODEL_DIR = Path(__file__).resolve().parent / "models" / "forecast_tuned"
METADATA_PATH = MODEL_DIR / "metadata.json"
TARGETS = ("visibility_km", "pm25", "pm10")
MODEL_PATHS = {target: MODEL_DIR / f"cb_tuned_{target}.cbm" for target in TARGETS}
MODEL_PATH = MODEL_PATHS["visibility_km"]
MODEL_VERSION = "low_visibility_89_20261026"


@lru_cache(maxsize=1)
def load_forecast_model():
    """원본 해시·입력 순서를 검사한 뒤 완성 모델만 로드한다."""
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if metadata.get("version") != MODEL_VERSION or len(metadata["features"]) != 89:
        raise ValueError("최신 89개 입력 모델 메타데이터가 필요합니다.")
    models = {}
    for target, path in MODEL_PATHS.items():
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != metadata["targets"][target]["sha256"]:
            raise ValueError(f"모델 원본 해시 불일치: {target}")
        model = CatBoostRegressor().load_model(blob=blob)
        if model.feature_names_ != metadata["features"]:
            raise ValueError(f"모델 입력 순서 불일치: {target}")
        models[target] = model
    return models, metadata


def number(value):
    if value is None:
        return float("nan")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("비정상 모델 입력 수치")
    return value


def dewpoint(temperature, humidity):
    """원본 노트북의 Magnus 식을 그대로 사용한다."""
    if not all(math.isfinite(v) for v in (temperature, humidity)):
        return float("nan")
    gamma = math.log(max(1, min(100, humidity)) / 100) + 17.62 * temperature / (
        243.12 + temperature
    )
    return 243.12 * gamma / (17.62 - gamma)


def read_model_history(conn, station_id, origin, asos_table):
    """현재 DB 스냅샷에서 정확한 시간별 관측 이력만 읽는다. 결측은 채우지 않는다."""
    if asos_table not in (
        "public.raw_weather_asos",
        "public.raw_weather_asos_realtime",
    ):
        raise ValueError("지원하지 않는 관측 테이블")
    codes = {"102": "831492", "112": "823632", "201": "831481"}
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT w.tm, w.visibility / 100.0 AS visibility_km,
            w.humidity, w.sea_press AS pressure, a.pm25, a.pm10,
            w.temp AS temperature, w.dew_point AS dewpoint,
            w.wind_speed, COALESCE(w.rainfall, 0) AS precipitation, m.water_temp AS sea_temp
            FROM {asos_table} w LEFT JOIN public.raw_air_quality a
              ON a.tm=w.tm AND a.station_code=%s
            LEFT JOIN public.raw_tide_observatory m ON m.tm=w.tm AND m.stn_name=%s
            WHERE w.stn_id=%s AND w.tm BETWEEN %s AND %s ORDER BY w.tm""",
            (
                codes[station_id],
                "소청초" if station_id == "102" else "인천",
                station_id,
                origin - timedelta(hours=72),
                origin,
            ),
        )
        return cur.fetchall()


def build_model_input(
    station_id, observed_at, h, asos, airkorea, marine, history, forecast
):
    """최신 89개 입력을 노트북 피처 구성·순서·float32 형식에 맞춘다."""
    if h not in range(1, 49):
        raise ValueError("예측 범위는 1~48시간입니다.")
    _, metadata = load_forecast_model()
    features = dict.fromkeys(metadata["features"], float("nan"))
    temperature, dew = number(asos["temp"]), number(asos["dew_point"])
    direction = number(asos["wind_dir"]) * 10  # ASOS 원천 WD는 10도 단위다.
    visibility = number(asos["visibility"]) / 100  # 원천 시정 단위는 10m다.
    pm25, pm10 = number(airkorea["pm25_ug_m3"]), number(airkorea["pm10_ug_m3"])
    if any(math.isfinite(v) and v < 0 for v in (visibility, pm25, pm10)):
        raise ValueError("현재 시정·PM 관측값은 음수일 수 없습니다.")
    future = observed_at + timedelta(hours=h)
    sea = number(marine["water_temperature_c"])
    buoy_air = number(marine["air_temperature_c"])
    salinity = number(marine["salinity_psu"])
    buoy_direction = number(marine["wind_direction_deg"])
    features.update(
        stn_id=str(station_id),
        h=h,
        visibility_km=visibility,
        temperature=temperature,
        humidity=number(asos["humidity"]),
        dewpoint=dew,
        dewpoint_depression=round(temperature - dew, 4),
        wind_speed=number(asos["wind_speed"]),
        wind_dir=direction,
        wind_dir_sin=round(math.sin(math.radians(direction)), 4),
        wind_dir_cos=round(math.cos(math.radians(direction)), 4),
        pressure=number(asos["sea_press"]),
        precipitation=(
            float("nan")
            if asos.get("_missing")
            else 0.0 if asos["rainfall"] is None else number(asos["rainfall"])
        ),
        cloud_cover=number(asos["cloud"]),
        sea_temp=sea,
        buoy_air_temp=buoy_air,
        sea_air_temp_diff=round(buoy_air - sea, 2),
        land_sea_temp_diff=round(temperature - buoy_air, 2),
        land_water_temp_diff=round(temperature - sea, 2),
        buoy_wind_speed=number(marine["wind_speed_m_s"]),
        buoy_wind_dir=buoy_direction,
        buoy_wind_dir_sin=round(math.sin(math.radians(buoy_direction)), 4),
        buoy_wind_dir_cos=round(math.cos(math.radians(buoy_direction)), 4),
        buoy_pressure=number(marine["air_pressure_hpa"]),
        salinity=salinity,
        temp_salinity_index=round(sea * salinity, 2),
        pm25=pm25,
        pm10=pm10,
        so2=number(airkorea["so2"]),
        no2=number(airkorea["no2"]),
        o3=number(airkorea["o3"]),
        co=number(airkorea["co"]),
        hour_sin=math.sin(2 * math.pi * observed_at.hour / 24),
        hour_cos=math.cos(2 * math.pi * observed_at.hour / 24),
        target_hour_sin=math.sin(2 * math.pi * future.hour / 24),
        target_hour_cos=math.cos(2 * math.pi * future.hour / 24),
    )
    # 학습 당시 결측 규칙을 유지하며 미제공 파랑을 0이나 과거 자료로 대신하지 않는다.
    for key, threshold in {
        "cloud_cover": 0,
        "pressure": 900,
        "buoy_pressure": 900,
    }.items():
        if features[key] < threshold:
            features[key] = float("nan")
    for key in ("humidity", "salinity", "temp_salinity_index"):
        if features[key] <= 0:
            features[key] = float("nan")
    if any(row["tm"] > observed_at for row in history):
        raise ValueError("미래 관측 이력 입력 금지")
    history_columns = [
        *TARGETS,
        "humidity",
        "pressure",
        "temperature",
        "dewpoint",
        "wind_speed",
        "precipitation",
        "sea_temp",
    ]
    frame = pd.DataFrame(history, columns=["tm", *history_columns])
    frame = (
        frame.drop_duplicates("tm", keep="last")
        .set_index("tm")
        .reindex(
            pd.date_range(observed_at - timedelta(hours=72), observed_at, freq="h")
        )
    )
    for c in history_columns:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
        frame.loc[~np.isfinite(frame[c]), c] = np.nan
        frame.loc[observed_at, c] = features[c]
    frame.loc[frame.humidity <= 0, "humidity"] = np.nan
    frame["dewpoint_depression"] = frame.temperature - frame.dewpoint
    frame["air_sea_diff"] = frame.temperature - frame.sea_temp
    # 노트북의 실제 관측 행에서만 무강수를 0으로 해석하고 빈 시간은 유지한다.
    observed = frame.visibility_km.notna()
    rain = frame.precipitation.where(frame.precipitation.notna() | ~observed, 0.0)
    features["precipitation"] = rain.iloc[-1]
    features["rain_3h"] = rain.iloc[-3:].sum(min_count=1)
    features["rain_24h"] = rain.iloc[-24:].sum(min_count=1)
    wet = rain[rain > 0]
    features["hours_since_rain"] = (
        min(72, (observed_at - wet.index[-1]).total_seconds() / 3600)
        if len(wet)
        else float("nan")
    )
    for column, lags in {
        "dewpoint_depression": (3, 6),
        "humidity": (6,),
        "temperature": (3, 6),
        "wind_speed": (3,),
        "visibility_km": (1, 6),
        "air_sea_diff": (3,),
    }.items():
        for lag in lags:
            features[f"chg{lag}h_{column}"] = (
                frame[column].iloc[-1] - frame[column].iloc[-lag - 1]
            )
    features["min_6h_dpd"] = frame.dewpoint_depression.iloc[-6:].min()
    features["humid90_6h"] = (
        (frame.humidity >= 90)
        .astype(float)
        .where(frame.humidity.notna())
        .iloc[-6:]
        .sum(min_count=1)
    )
    features["min_6h_visibility_km"] = frame.visibility_km.iloc[-6:].min()
    for c in TARGETS:
        features[f"lag_1h_{c}"] = frame[c].iloc[-2]
        features[f"diff_3h_{c}"] = frame[c].iloc[-1] - frame[c].iloc[-4]
        features[f"max_24h_{c}"] = frame[c].iloc[-24:].max()
        features[f"min_24h_{c}"] = frame[c].iloc[-24:].min()
        features[f"same_hour_prev_{c}"] = frame.loc[
            future - timedelta(hours=24 if h <= 24 else 48), c
        ]
    features.update(
        air_sea_diff=temperature - sea,
        u=-features["wind_speed"] * features["wind_dir_sin"],
        v=-features["wind_speed"] * features["wind_dir_cos"],
        diff_3h_humidity=frame.humidity.iloc[-1] - frame.humidity.iloc[-4],
        diff_3h_pressure=frame.pressure.iloc[-1] - frame.pressure.iloc[-4],
        pm_ratio=(
            min(1, max(0, pm25 / (pm10 + 1e-5)))
            if math.isfinite(pm25) and math.isfinite(pm10)
            else float("nan")
        ),
    )
    if pd.Timestamp(forecast["valid_at"]).tz_convert(KST).tz_localize(
        None
    ) != pd.Timestamp(future):
        raise ValueError("예보 대상시각 불일치")
    for key in ("kma_issued_at", "airkorea_issued_at"):
        if forecast[key] is None:
            continue
        issued = pd.Timestamp(forecast[key]).tz_convert(KST).tz_localize(None)
        if issued > observed_at:
            raise ValueError("미래에 발표된 예보 입력 금지")
    features.update(forecast["values"])
    ft, rh = features["future_fcst_temp"], features["future_fcst_humidity"]
    features.update(
        f_air_sea_diff=ft - sea, f_dtemp=ft - temperature, f_dpd=ft - dewpoint(ft, rh)
    )
    result = pd.DataFrame([features], columns=metadata["features"])
    for column in result.columns.drop("stn_id"):
        result[column] = result[column].astype("float32")
    if np.isinf(result.select_dtypes("number").to_numpy()).any():
        raise ValueError("무한대 모델 입력")
    return result


def predict_visibility_pm(
    station_id, observed_at, h, asos, airkorea, marine, history, forecast
):
    """원본 노트북의 표준화된 log 잔차를 실제 시정·농도로 복원한다."""
    models, metadata = load_forecast_model()
    inputs = build_model_input(
        station_id, observed_at, h, asos, airkorea, marine, history, forecast
    )
    result = {}
    unavailable = []
    for target, model in models.items():
        current = float(inputs[target].iloc[0])
        if not math.isfinite(current):
            result[target] = None
            unavailable.append(target)
            continue
        try:
            residual = float(model.predict(inputs)[0])
            sigma = metadata["targets"][target]["sigma_by_h"][str(h)]
            value = math.expm1(math.log1p(max(0, current)) + residual * sigma)
            if not math.isfinite(value):
                raise ValueError("비정상 튜닝형 출력")
            high = metadata["targets"][target]["clip_max"]
            result[target] = (
                max(0, min(value, high)) if high is not None else max(0, value)
            )
        except Exception as exc:
            logging.getLogger("uvicorn.error").warning(
                "예측 항목 실패: %s / %s시간 / %s", target, h, type(exc).__name__
            )
            result[target] = None
            unavailable.append(target)
    result["missing_features"] = inputs.columns[inputs.isna().iloc[0]].tolist()
    result["unavailable_targets"] = unavailable
    return result
