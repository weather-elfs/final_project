import json
from pathlib import Path
import math
from catboost import CatBoostRegressor
from datetime import timedelta
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent / "models"

MODEL_PATH = MODEL_DIR / "catboost_48h_multioutput.cbm"
METADATA_PATH = MODEL_DIR / "catboost_48h_metadata.json"


def load_forecast_model():
    model = CatBoostRegressor()
    model.load_model(str(MODEL_PATH))

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return model, metadata


def build_time_features(observed_at, h):
    future_time = observed_at + timedelta(hours=h)

    return {
        "h": h,
        "hour_sin": round(math.sin(2 * math.pi * observed_at.hour / 24.0), 4),
        "hour_cos": round(math.cos(2 * math.pi * observed_at.hour / 24.0), 4),
        "dayofyear_sin": round(
            math.sin(2 * math.pi * observed_at.timetuple().tm_yday / 365.0), 4
        ),
        "dayofyear_cos": round(
            math.cos(2 * math.pi * observed_at.timetuple().tm_yday / 365.0), 4
        ),
        "target_hour_sin": math.sin(2 * math.pi * future_time.hour / 24.0),
        "target_hour_cos": math.cos(2 * math.pi * future_time.hour / 24.0),
    }


def build_asos_features(asos):
    def to_float(value):
        if value is None:
            return float("nan")
        return float(value)

    temperature = to_float(asos["temp"])
    dewpoint = to_float(asos["dew_point"])
    wind_dir = to_float(asos["wind_dir"])

    return {
        "temperature": temperature,
        "humidity": to_float(asos["humidity"]),
        "dewpoint": dewpoint,
        "dewpoint_depression": round(temperature - dewpoint, 4),
        "wind_speed": to_float(asos["wind_speed"]),
        "wind_dir_sin": round(math.sin(math.radians(wind_dir)), 4),
        "wind_dir_cos": round(math.cos(math.radians(wind_dir)), 4),
        "pressure": to_float(asos["sea_press"]),
        "precipitation": to_float(asos["rainfall"]),
        "cloud_cover": to_float(asos["cloud"]),
    }


def build_marine_features(asos, marine):
    def to_float(value):
        if value is None:
            return float("nan")
        return float(value)

    land_temp = to_float(asos["temp"])
    sea_temp = to_float(marine["water_temperature_c"])
    buoy_air_temp = to_float(marine["air_temperature_c"])
    buoy_wind_dir = to_float(marine["wind_direction_deg"])
    salinity = to_float(marine["salinity_psu"])

    return {
        "sea_temp": sea_temp,
        "buoy_air_temp": buoy_air_temp,
        "sea_air_temp_diff": round(buoy_air_temp - sea_temp, 2),
        "land_sea_temp_diff": round(land_temp - buoy_air_temp, 2),
        "land_water_temp_diff": round(land_temp - sea_temp, 2),
        "buoy_wind_speed": to_float(marine["wind_speed_m_s"]),
        "buoy_wind_dir_sin": round(math.sin(math.radians(buoy_wind_dir)), 4),
        "buoy_pressure": to_float(marine["air_pressure_hpa"]),
        "buoy_wind_dir_cos": round(math.cos(math.radians(buoy_wind_dir)), 4),
        "salinity": salinity,
        "temp_salinity_index": round(sea_temp * salinity, 2),
    }


def build_airkorea_features(airkorea):
    def to_float(value):
        if value is None:
            return float("nan")
        return float(value)

    return {
        "so2": to_float(airkorea["so2"]),
        "no2": to_float(airkorea["no2"]),
        "o3": to_float(airkorea["o3"]),
        "co": to_float(airkorea["co"]),
    }


def build_model_input(station_id, observed_at, h, asos, airkorea, marine):
    features = {
        "stn_id": str(station_id),
        **build_time_features(observed_at, h),
        **build_asos_features(asos),
        **build_airkorea_features(airkorea),
        **build_marine_features(asos, marine),
    }

    _, metadata = load_forecast_model()
    feature_names = metadata["model_features"]

    missing = [name for name in feature_names if name not in features]

    if missing:
        raise ValueError(f"모델 입력 변수 누락: {missing}")

    return pd.DataFrame([features], columns=feature_names)


def predict_visibility_pm(station_id, observed_at, h, asos, airkorea, marine):
    model, metadata = load_forecast_model()

    model_input = build_model_input(
        station_id=station_id,
        observed_at=observed_at,
        h=h,
        asos=asos,
        airkorea=airkorea,
        marine=marine,
    )

    predictions = model.predict(model_input)[0]

    return {
        name: float(value)
        for name, value in zip(metadata["target_columns"], predictions)
    }
