"""Auto-converted from train_final_forecast.ipynb
Pipeline script for training and evaluation.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ======================================================================
# # 관측 · 예보 테이블 피처 확인
#
# 위에서부터 순서대로 실행하세요. 마지막 셀의 **예보 테이블 시간 관련 컬럼** 출력을 복사해서 Claude에게 보내주시면 모델 노트북 설정을 맞춰 드립니다.
#
# ======================================================================

# !pip install -q gdown pyarrow catboost koreanize-matplotlib

import gdown
import pandas as pd

# 파일 ID 정의 OBS : 원천데이터 데이터 통합 FCST : 기상청 단기예보 및 PM2.5 권역별 예보 데이터통합
OBS_FILE_ID = "1o8wV5c-Gfigr4U9zfbc0CU8rptkGeHfy"
FCST_FILE_ID = "1yFYhYMZeE3E9wsGcs8kgIXqZtBqSbZkl"

obs_path = "mart_tide_anchor_obs.parquet"
fcst_path = "mart_forecast_pit_48h.parquet"

gdown.download(id=OBS_FILE_ID, output=obs_path, quiet=False)
gdown.download(id=FCST_FILE_ID, output=fcst_path, quiet=False)

print("\n파일 다운로드 완료")


# ======================================================================
# ### 데이터 탐색
#
# ======================================================================

import pandas as pd
from IPython.display import display

obs = pd.read_parquet(obs_path)  # mart_tide_anchor_obs
fcst = pd.read_parquet(fcst_path)  # mart_forecast_pit_48h


# ---------- 1. 컬럼(피처) 요약표 ----------
def describe_table(df, name):
    print(f"\n===== {name}: {len(df):,} 행 x {df.shape[1]} 컬럼 =====")
    info = pd.DataFrame(
        {
            "dtype": df.dtypes.astype(str),
            "결측률(%)": (df.isna().mean() * 100).round(1),
            "고유값 수": df.nunique(),
            "예시값": df.iloc[0],
        }
    )
    num = df.select_dtypes("number")
    info.loc[num.columns, "최소"] = num.min().round(3)
    info.loc[num.columns, "최대"] = num.max().round(3)
    print(info)
    print(df.head())


describe_table(obs, "관측 mart_tide_anchor_obs")
describe_table(fcst, "예보 mart_forecast_pit_48h")


# ======================================================================
# ---
#
# # 모델 학습 · 평가 · 계절 영향 분석
#
#
#
# - 계절(월·dayofyear)은 **모델 피처에 넣지 않음** → 날짜로 특정 해 사건을 외우는 과적합/누수 방지
# - 계절은 **결과를 나눠 보고, 계절별로 어떤 물리 요인이 작용하는지 분석할 때만** 사용
#
# ======================================================================

obs_raw = obs.copy()
fc_raw = fcst.copy()
print("관측", obs_raw.shape, "| 예보", fc_raw.shape)

# VIS_EXPERIMENTS = {
#    "current": dict(
#        transform="log1p",
#        bin_weight_power=0.5,
#        horizon_norm=True,
#    ),
#    "lighter_weight": dict(
#        transform="log1p",
#        bin_weight_power=0.25,
#        horizon_norm=True,
#    ),
#    "strong_low_visibility": dict(
#       transform="log1p",
#        bin_weight_power=0.75,
#        horizon_norm=True,
#    ),
#    "sqrt_weighted": dict(
#        transform="sqrt",
#        bin_weight_power=0.5,
#        horizon_norm=True,
#    ),
# }


# ======================================================================
# ![image.png](attachment:image.png)
#
# ======================================================================


# ======================================================================
# ## A. 설정
#
# ======================================================================

import gc

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from IPython.display import display
from scipy.optimize import nnls

try:
    import koreanize_matplotlib
except ImportError:
    pass

QUICK = False  # True: 빠른 점검 (리드 일부·반복 수 축소)

TRAIN_START, TRAIN_END, VAL_END = "2022-04-01", "2024-04-01", "2025-04-01"
HORIZONS = [1, 3, 6, 12, 24, 48] if QUICK else list(range(1, 49))
CORE = ["visibility_km", "pm25", "pm10"]

# ============================== 타깃별 설정 ==============================
TARGET_CFG = {
    "visibility_km": dict(
        unit="km",
        transform="log1p",  # "none" | "sqrt" | "log1p"
        bin_weight_power=0.5,  # 0 ~ 1
        horizon_norm=True,
        clip_hi="train_max",  # 관측 상한(예: 50km)으로 자르기. None이면 상한 없음
        bins=[0, 1, 3, 10, 20, 40, np.inf],
    ),
    "pm25": dict(
        unit="㎍/m³",
        transform="log1p",
        bin_weight_power=0.5,
        horizon_norm=True,
        clip_hi=None,
        bins=[0, 15, 35, 75, np.inf],  # 환경부 등급: 좋음/보통/나쁨/매우나쁨
    ),
    "pm10": dict(
        unit="㎍/m³",
        transform="log1p",
        bin_weight_power=0.5,
        horizon_norm=True,
        clip_hi=None,
        bins=[0, 30, 80, 150, np.inf],
    ),
}
RAW_CFG = dict(
    transform="none", bin_weight_power=0.0, horizon_norm=False
)  # 비교 기준 (기존 Base 방식)

CASE_STN = "112"  # 사례 그래프 관측소
LOG_Y_CASE = {
    "visibility_km": False,
    "pm25": False,
    "pm10": False,
}  # 사례 그래프 y축 로그 여부

try:
    from catboost.utils import get_gpu_device_count

    TASK = "GPU" if get_gpu_device_count() > 0 else "CPU"
except Exception:
    TASK = "CPU"
print("CatBoost 장치:", TASK)

# ============================== 파일 · 컬럼 설정 ==============================
OBS_PATH = "mart_tide_anchor_obs.parquet"
FCST_PATH = "mart_forecast_pit_48h.parquet"
OBS_GDRIVE_ID, FCST_GDRIVE_ID = None, None  # 구글드라이브에서 받을 거면 파일 ID 입력

OBS_COLS = dict(stn="stn_id", tm="tm")
# 예보 테이블 컬럼 이름 (없는 건 None)
FC_COLS = dict(
    stn="stn_id",
    tm="tm",  # 기준시각 t (예측을 하는 시각)
    h="lead_h",  # 리드(시간)
    valid="target_tm",  # 예보 대상 시각 (t+h)
    base="fcst_base_time",  # 단기예보 발표시각
    pm_base=None,  # PM 예보 발표시각이 따로 있으면 컬럼명 (없으면 base 기준으로 점검)
)
PM_FCST_COLS = ["fcst_pm25_grade"]  # PM 예보 컬럼 (pm_base 기준으로 점검)
# 발표 → 실제 사용 가능까지 여유. 0이면 '발표시각 ≤ t' (마트 조건과 동일)
# 기상청 API는 발표 후 약 10분 뒤 제공 → 엄격하게 하려면 pd.Timedelta(minutes=10)
#   (단, 이미 조인된 마트에서는 조건을 어긴 행을 이전 발표분으로 대체할 수 없어서 그 행의 예보가 비게 됨)
DELAY = pd.Timedelta(0)

# 피처에서 반드시 뺄 것 (날짜·계절 정보)
DROP_CALENDAR = [
    "dayofyear_sin",
    "dayofyear_cos",
    "month",
    "season",
    "doy",
    "dayofyear",
]
SEASONS = {
    "Spring": [3, 4, 5],
    "Summer": [6, 7, 8],
    "Autumn": [9, 10, 11],
    "Winter": [12, 1, 2],
}

# ---- 그래프 축 설정 ----
VIS_AXIS_MAX = 100  # 시정 축 최대 (km)
PM_ZOOM = 30  # PM 확대 보기 상한 (20으로 바꾸면 더 촘촘히)
LEAD_GROUPS = {"1~6h": (1, 6), "7~24h": (7, 24), "25~48h": (25, 48)}


# ======================================================================
# ## B. 전처리 · 예보 매칭(발표시각 ≤ t) · long 테이블
#
# ======================================================================


def load(path, gid):
    import os

    if not os.path.exists(path) and gid:
        import gdown

        gdown.download(id=gid, output=path, quiet=False)
    return pd.read_parquet(path)


def to_dt(s):
    # datetime / 문자열 / epoch 정수 → 모두 datetime64[ns] (정밀도가 다르면 merge_asof 오류)
    return _to_dt(s).astype("datetime64[ns]")


def _to_dt(s):
    # datetime / 문자열 / epoch 정수(ns·us·ms·s, int64 최솟값=결측) 모두 처리
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.tz_localize(None) if getattr(s.dt, "tz", None) is not None else s
    if pd.api.types.is_integer_dtype(s) or pd.api.types.is_float_dtype(s):
        v = s.where(s != np.iinfo(np.int64).min).astype("float64").to_numpy()
        ns = np.full(len(v), np.nan)
        # 값 크기로 단위를 행마다 판정: epoch ns / us / ms / YYYYMMDDHHMM / epoch s
        for lo, hi, mul in (
            (1e17, np.inf, 1),
            (1e14, 1e17, 1e3),
            (1e12, 1e14, 1e6),
            (0, 1e11, 1e9),
        ):
            m = (v >= lo) & (v < hi)
            ns[m] = v[m] * mul
        out = pd.Series(pd.to_datetime(ns, unit="ns"), index=s.index)
        ymd = (v >= 1e11) & (v < 1e12)
        if ymd.any():
            out[ymd] = pd.to_datetime(
                pd.Series(v[ymd]).astype("int64").astype(str),
                format="%Y%m%d%H%M",
                errors="coerce",
            ).to_numpy()
        return out.dt.round("min")
    return pd.to_datetime(s, errors="coerce")


assert (
    "obs_raw" in globals() and "fc_raw" in globals()
), "위의 [데이터 불러오기] 셀을 먼저 실행하세요"
print("관측:", obs_raw.shape, "| 예보:", fc_raw.shape)

# ---------------- 관측 ----------------
d = obs_raw.rename(columns={OBS_COLS["stn"]: "stn_id", OBS_COLS["tm"]: "tm"}).copy()
d["tm"] = to_dt(d["tm"])
d["stn_id"] = d["stn_id"].astype(str)
d = (
    d.drop_duplicates(["stn_id", "tm"])
    .sort_values(["stn_id", "tm"])
    .reset_index(drop=True)
)
BAD = {
    "cloud_cover": lambda x: x < 0,
    "pressure": lambda x: x < 900,
    "buoy_pressure": lambda x: x < 900,
    "humidity": lambda x: x <= 0,
    "salinity": lambda x: x <= 0,
    "temp_salinity_index": lambda x: x <= 0,
}
for c, f in BAD.items():
    if c in d:
        m = f(d[c])
        if m.any():
            print(f"  관측 {c}: 이상값 {int(m.sum()):,}개 → NaN")
        d.loc[m, c] = np.nan
if "precipitation" in d:
    d["precipitation"] = d["precipitation"].fillna(0.0)
# 시각 주기 (하루 주기는 계절과 무관 → 사용). 날짜 계열은 만들지도 않음
d["hour_sin"] = np.sin(2 * np.pi * d["tm"].dt.hour / 24)
d["hour_cos"] = np.cos(2 * np.pi * d["tm"].dt.hour / 24)


# ---------------- 예보 ----------------
# 컬럼 이름 자동 인식 (FC_COLS에 직접 적은 값이 실제로 있으면 그걸 우선 사용)
def _guess(cols, cands):
    low = {c.lower(): c for c in cols}
    for c in cands:
        if c.lower() in low:
            return low[c.lower()]
    return None


_cols = list(fc_raw.columns)
_auto = dict(
    stn=_guess(_cols, ["stn_id", "stn", "station_id", "station"]),
    tm=_guess(
        _cols,
        [
            "tm",
            "anchor_tm",
            "anchor_time",
            "pred_tm",
            "pred_time",
            "origin_tm",
            "origin_time",
            "issue_tm",
            "t0",
        ],
    ),
    h=_guess(_cols, ["h", "lead_h", "lead_hour", "horizon", "horizon_h", "h_lead"]),
    valid=_guess(  # 예보 테이블 컬럼 이름 들어오게 설정
        _cols,
        [
            "valid_dt",
            "valid_tm",
            "valid_time",
            "target_tm",
            "target_time",
            "fcst_tm",
            "fcst_time",
            "fcst_dt",
        ],
    ),
    base=_guess(
        _cols,
        [
            "base_dt",
            "base_tm",
            "base_time",
            "fcst_base_time",
            "fcst_base_dt",
            "issue_time",
            "announce_time",
            "ann_tm",
        ],
    ),
    pm_base=_guess(
        _cols,
        [
            "pm_base_dt",
            "pm_base_tm",
            "pm_base_time",
            "pm25_base_time",
            "pm_issue_time",
            "pm_announce_time",
        ],
    ),
)
for k in _auto:
    if not (FC_COLS.get(k) and FC_COLS[k] in _cols):
        FC_COLS[k] = _auto[k]
print("예보 컬럼 매핑:", FC_COLS)
assert FC_COLS[
    "stn"
], "예보 테이블의 지점 컬럼을 못 찾음 → 설정 셀 FC_COLS['stn']에 직접 입력"
assert FC_COLS[
    "base"
], "예보 테이블의 발표시각 컬럼을 못 찾음 → FC_COLS['base']에 직접 입력 (누수 점검에 필수)"
assert (FC_COLS["tm"] and (FC_COLS["h"] or FC_COLS["valid"])) or FC_COLS[
    "valid"
], "기준시각(tm)+리드(h) 또는 대상시각(valid) 컬럼이 필요 → FC_COLS에 직접 입력"

fc = fc_raw.rename(columns={v: k for k, v in FC_COLS.items() if v}).copy()
fc["stn"] = fc["stn"].astype(str)
for c in ("tm", "valid", "base", "pm_base"):
    if c in fc:
        fc[c] = to_dt(fc[c])

# 기상청 코드명 → 노트북 이름 (파생변수 계산에 사용)
KMA_ALIAS = {
    "TMP": "fcst_temp",
    "T1H": "fcst_temp",
    "REH": "fcst_humidity",
    "WSD": "fcst_wind_speed",
    "PCP": "fcst_precipitation",
    "RN1": "fcst_precipitation",
    "SNO": "fcst_snow",
    "POP": "fcst_pop",
    "SKY": "fcst_sky",
    "PTY": "fcst_pty",
    "UUU": "fcst_uuu",
    "VVV": "fcst_vvv",
    "VEC": "fcst_wind_dir",
    "WAV": "fcst_wave",
}
fc = fc.rename(columns={k: v for k, v in KMA_ALIAS.items() if k in fc and v not in fc})
for c in ("fcst_humidity",):
    if c in fc:
        fc.loc[fc[c] <= 0, c] = np.nan

KEYS = {"stn", "tm", "h", "valid", "base", "pm_base"}
SKIP = (
    KEYS
    | set(DROP_CALENDAR)
    | {"fcst_lead_time", "lead_time", "nx", "ny", "region", "region_code"}
)
FC_VARS = [
    c for c in fc.columns if c not in SKIP and pd.api.types.is_numeric_dtype(fc[c])
]
PM_FCST_COLS = [c for c in FC_VARS if "pm" in c.lower() or "grade" in c.lower()]
FC_MODE = "joined" if "tm" in fc else "raw"

_so, _sf = set(obs_raw[OBS_COLS["stn"]].astype(str)), set(fc["stn"])
print(
    f"지점: 관측 {sorted(_so)} / 예보 {sorted(_sf)[:10]}{'...' if len(_sf) > 10 else ''}"
)
if not (_so & _sf):
    raise ValueError(
        "관측과 예보의 지점 코드가 하나도 안 겹침 → 예보 테이블 지점 컬럼/코드 확인"
    )
print(f"PM 예보 컬럼(별도 발표시각 점검): {PM_FCST_COLS}")
print(f"예보 형식: {FC_MODE} | 예보 변수 {len(FC_VARS)}개: {FC_VARS}")

if FC_MODE == "raw":
    # (지점, 대상시각)이 같고 '발표+지연 ≤ t' 인 것 중 가장 최근 발표분 1개
    fr = fc.dropna(subset=["valid", "base"]).copy()
    fr["avail"] = fr["base"] + DELAY
    fr = fr.sort_values("avail")
    obs_keys = d[["stn_id", "tm"]].rename(columns={"stn_id": "stn"})
    out = []
    for h in HORIZONS:
        left = obs_keys.assign(
            valid=obs_keys["tm"] + pd.Timedelta(hours=h), h=np.float32(h)
        ).sort_values("tm")
        m = pd.merge_asof(
            left,
            fr[
                ["stn", "valid", "avail", "base"]
                + FC_VARS
                + (["pm_base"] if "pm_base" in fr else [])
            ],
            left_on="tm",
            right_on="avail",
            by=["stn", "valid"],
            direction="backward",
        )
        out.append(m)
    FJ = pd.concat(out, ignore_index=True)
else:
    FJ = fc.copy()
    if "h" not in FJ:
        FJ["h"] = (FJ["valid"] - FJ["tm"]).dt.total_seconds() / 3600
    FJ["h"] = FJ["h"].astype("float32")
    FJ = FJ[FJ["h"].isin(HORIZONS)]
    dup = FJ.duplicated(["stn", "tm", "h"]).sum()
    if dup:
        print(f"  [주의] (지점,t,h) 중복 {dup:,}건 → 가장 최근 발표분만 남김")
        FJ = FJ.sort_values("base" if "base" in FJ else "tm").drop_duplicates(
            ["stn", "tm", "h"], keep="last"
        )


# ---- 방어적 누수 점검: 발표+지연 > t 인 값은 NaN ----
def mask_future(cols, bcol):
    if bcol not in FJ or not cols:
        print(f"  [경고] 발표시각 컬럼({bcol}) 없음 → {cols} 점검 불가")
        return
    same = int((FJ[bcol] == FJ["tm"]).sum())
    if same:
        print(
            f"  [참고] 발표시각 = 기준시각인 행 {same:,}건 ({same / len(FJ):.0%}) — 실제로는 발표 약 10분 뒤 제공이라 "
            f"아주 약간 낙관적. 엄격히 하려면 DELAY=10분 또는 마트를 '발표시각 < t'로 재생성"
        )
    bad = FJ[bcol].notna() & (FJ[bcol] + DELAY > FJ["tm"])
    print(
        f"  {bcol} 기준 위반 {int(bad.sum()):,}건 / {len(FJ):,} → NaN 처리  ({cols[:3]}{'...' if len(cols) > 3 else ''})"
    )
    FJ.loc[bad, cols] = np.nan
    nob = FJ[bcol].isna()
    FJ.loc[nob, cols] = np.nan  # 발표시각 모르는 값은 쓰지 않음


pm_cols = [c for c in PM_FCST_COLS if c in FC_VARS]
mask_future([c for c in FC_VARS if c not in pm_cols], "base")
mask_future(pm_cols, "pm_base" if "pm_base" in FJ else "base")

FJ["fcst_age_h"] = (
    ((FJ["tm"] - FJ["base"]).dt.total_seconds() / 3600).astype("float32")
    if "base" in FJ
    else np.nan
)
FJ = FJ.rename(columns={c: f"future_{c}" for c in FC_VARS}).rename(
    columns={"stn": "stn_id"}
)
FUT_COLS = [f"future_{c}" for c in FC_VARS] + ["fcst_age_h"]
FJ = FJ[["stn_id", "tm", "h"] + FUT_COLS]
for c in FUT_COLS:
    FJ[c] = FJ[c].astype("float32")
avail = FJ.groupby("h")[FUT_COLS[0]].apply(lambda s: s.notna().mean())
print(
    "예보 사용 가능 비율:",
    ", ".join(
        f"h{int(h)}={avail.get(h, np.nan):.0%}"
        for h in [1, 3, 5, 6, 12, 24, 36, 48]
        if h in avail.index
    ),
)


# ======================================================================
# ### 4. 학습 데이터셋 구성 — 관측 피처 생성 · 리드타임 전개 · 기간 분할 · 예보(PIT) 결합
#
# ======================================================================


def dewpoint(t, rh):  # 이슬점 함수 Magnus 식
    a, b = 17.62, 243.12
    rh = np.clip(rh, 1, 100)
    gam = np.log(rh / 100) + a * t / (b + t)
    return b * gam / (a - gam)


# 관측 수치 컬럼 선택
OBS_NUM = [
    c
    for c in d.columns
    if c not in ("stn_id", "tm")
    and pd.api.types.is_numeric_dtype(d[c])
    and c not in DROP_CALENDAR
    and not c.startswith("fcst_")
]
tr_start, tr_end, va_end = (
    np.datetime64(pd.Timestamp(x)) for x in (TRAIN_START, TRAIN_END, VAL_END)
)
parts = {"train": [], "val": [], "test": []}
for stn, g in d.groupby("stn_id", sort=False):
    g = g.set_index("tm").sort_index().asfreq("h")
    F = g[OBS_NUM].copy()
    for c in CORE:
        F[f"lag_1h_{c}"] = g[c].shift(1)  # 1시간 전 값
        F[f"diff_3h_{c}"] = g[c] - g[c].shift(3)  # 최근 3시간 변화량
        F[f"max_24h_{c}"] = (
            g[c].rolling(24, min_periods=1).max()
        )  # 최근 24시간 최댓값, 최솟값
        F[f"min_24h_{c}"] = (
            g[c].rolling(24, min_periods=1).min()
        )  # 기온-해수온, 해무 발생 지표
    if {"temperature", "sea_temp"} <= set(g):
        F["air_sea_diff"] = g["temperature"] - g["sea_temp"]
    if {"wind_speed", "wind_dir_sin", "wind_dir_cos"} <= set(g):
        F["u"] = (
            -g["wind_speed"] * g["wind_dir_sin"]
        )  # 풍속 방향을 동서,남북 성분으로 분해
        F["v"] = (
            -g["wind_speed"] * g["wind_dir_cos"]
        )  ##풍속 방향을 동서,남북 성분으로 분해
    if "humidity" in g:
        F["diff_3h_humidity"] = g["humidity"] - g["humidity"].shift(
            3
        )  # 습도·기압의 3시간 변화 (기압 변화 표준지표라서 3시간 해둠)
    if "pressure" in g:
        F["diff_3h_pressure"] = g["pressure"] - g["pressure"].shift(
            3
        )  # 습도·기압의 3시간 변화
    F["pm_ratio"] = (g["pm25"] / (g["pm10"] + 1e-5)).clip(
        0, 1
    )  # PM2.5 / PM10 비율. 미세 입자 비중-> 발생 원인 구분에 도움
    cols = list(F.columns)
    Fv = F.to_numpy(np.float32)
    t0 = g.index.to_numpy()
    for h in HORIZONS:
        vt = g.index + pd.Timedelta(hours=h)
        vtn = vt.to_numpy()
        Y = g[CORE].reindex(vt).to_numpy(np.float32)
        SH = (
            g[CORE]
            .reindex(vt - pd.Timedelta(hours=24 if h <= 24 else 48))
            .to_numpy(np.float32)
        )
        ok = np.isfinite(Y).any(axis=1)
        sel = {
            "train": ok & (t0 >= tr_start) & (vtn < tr_end),
            "val": ok & (t0 >= tr_end) & (vtn < va_end),
            "test": ok & (t0 >= va_end),
        }
        hr = vt.hour.to_numpy()
        for sp, m in sel.items():
            if not m.any():
                continue
            blk = pd.DataFrame(Fv[m], columns=cols)
            for j, c in enumerate(CORE):
                blk[f"same_hour_prev_{c}"] = SH[m, j]
                blk[f"y_future_{c}"] = Y[m, j]
            blk["h"] = np.float32(h)
            blk["target_hour_sin"] = np.sin(2 * np.pi * hr[m] / 24).astype(np.float32)
            blk["target_hour_cos"] = np.cos(2 * np.pi * hr[m] / 24).astype(np.float32)
            blk.insert(0, "stn_id", stn)
            blk.insert(1, "tm", t0[m])
            parts[sp].append(blk)
    del F, Fv

L = {}
for sp, v in parts.items():
    if not v:
        continue
    x = pd.concat(v, ignore_index=True)
    x = x.merge(FJ, on=["stn_id", "tm", "h"], how="left")  # 예보 붙이기 (PIT)
    if "future_fcst_temp" in x:
        if "sea_temp" in x:
            x["f_air_sea_diff"] = x["future_fcst_temp"] - x["sea_temp"]
        if "temperature" in x:
            x["f_dtemp"] = x["future_fcst_temp"] - x["temperature"]
        if "future_fcst_humidity" in x:
            x["f_dpd"] = x["future_fcst_temp"] - dewpoint(
                x["future_fcst_temp"], x["future_fcst_humidity"]
            )
    x["stn_id"] = x["stn_id"].astype("category")
    f64 = x.select_dtypes("float64").columns
    x[f64] = x[f64].astype("float32")
    L[sp] = x
del parts
gc.collect()

FEATURES = [
    c
    for c in L["train"].columns
    if c not in ["tm"] + [f"y_future_{c}" for c in CORE] and c not in DROP_CALENDAR
]
assert not any(c in FEATURES for c in DROP_CALENDAR), "날짜/계절 피처가 들어있음"
for sp, v in L.items():
    print(
        f"  {sp:5s}: {len(v):>10,} 행  ({v['tm'].min():%Y-%m-%d} ~ {v['tm'].max():%Y-%m-%d})"
    )
print(f"피처 {len(FEATURES)}개 (날짜·계절 피처 없음)")


# ## C. 학습 (타깃별 Raw / Tuned) · 앙상블
#
# ======================================================================


def fwd(x, tr):
    x = np.clip(np.asarray(x, dtype="float64"), 0, None)
    return {"none": x, "sqrt": np.sqrt(x), "log1p": np.log1p(x)}[tr]


def inv(x, tr):
    x = np.asarray(x, dtype="float64")
    return {"none": x, "sqrt": np.clip(x, 0, None) ** 2, "log1p": np.expm1(x)}[tr]


def bin_of(y, bins):
    return np.clip(np.digitize(y, bins[1:-1]), 0, len(bins) - 2)


def bin_labels(bins):
    return [
        f"{bins[i]:g}~{bins[i+1]:g}" if np.isfinite(bins[i + 1]) else f"{bins[i]:g}+"
        for i in range(len(bins) - 1)
    ]


common = dict(
    loss_function="RMSE",
    iterations=200 if QUICK else 3000,
    learning_rate=0.05,
    depth=8,
    l2_leaf_reg=4.0,
    random_seed=42,
    early_stopping_rounds=150,
    verbose=500,
    allow_writing_files=False,
    task_type=TASK,
)


def fit_member(tgt, cfg):
    tr, power, hnorm = cfg["transform"], cfg["bin_weight_power"], cfg["horizon_norm"]
    bins = TARGET_CFG[tgt]["bins"]
    data = {}
    for sp in ("train", "val"):
        v = L[sp]
        m = (np.isfinite(v[f"y_future_{tgt}"]) & np.isfinite(v[tgt])).to_numpy()
        dlt = fwd(v.loc[m, f"y_future_{tgt}"], tr) - fwd(v.loc[m, tgt], tr)
        data[sp] = (m, dlt)
    # 리드타임별 표준편차 (train에서만 계산)
    m_tr, d_tr = data["train"]
    h_tr = L["train"].loc[m_tr, "h"].to_numpy()
    sig = (
        pd.Series(d_tr).groupby(h_tr).std().clip(lower=1e-6)
        if hnorm
        else pd.Series(1.0, index=HORIZONS)
    )
    # 값 구간별 가중 (train 분포 기준)
    freq = None
    if power > 0:
        b_tr = bin_of(L["train"].loc[m_tr, f"y_future_{tgt}"].to_numpy(), bins)
        freq = np.bincount(b_tr, minlength=len(bins) - 1) / len(b_tr)

    def pool(sp):
        m, dlt = data[sp]
        v = L[sp].loc[m]
        y = dlt / v["h"].map(sig).to_numpy()
        w = None
        if freq is not None:
            w = (
                1.0
                / np.maximum(freq[bin_of(v[f"y_future_{tgt}"].to_numpy(), bins)], 1e-6)
            ) ** power
            w = w / w.mean()
        return Pool(v[FEATURES], y, cat_features=["stn_id"], weight=w)

    ptr, pva = pool("train"), pool("val")
    model = CatBoostRegressor(**common)
    model.fit(ptr, eval_set=pva, use_best_model=True)
    del ptr, pva
    gc.collect()
    return dict(model=model, sig=sig, transform=tr)


def predict_member(mem, tgt, sp):
    v = L[sp]
    cur = v[tgt].to_numpy("float64")
    z = mem["model"].predict(v[FEATURES])
    lvl = inv(
        fwd(cur, mem["transform"]) + z * v["h"].map(mem["sig"]).to_numpy(),
        mem["transform"],
    )
    hi = TARGET_CFG[tgt]["clip_hi"]
    if hi == "train_max":
        hi = float(np.nanmax(L["train"][f"y_future_{tgt}"]))
    return np.clip(lvl, 0, hi)


PRED = {}  # PRED[(tgt, split)] = {모델명: 예측}
for tgt in CORE:
    cfg = TARGET_CFG[tgt]
    print(f"\n==================== {tgt} ====================")
    print(f"[Raw]   transform=none, 가중 없음, 리드표준화 없음")
    raw = fit_member(tgt, RAW_CFG)
    print(
        f"[Tuned] transform={cfg['transform']}, bin_weight_power={cfg['bin_weight_power']}, horizon_norm={cfg['horizon_norm']}"
    )
    tuned = fit_member(tgt, cfg)
    for sp in ("val", "test"):
        if sp not in L:
            continue
        cur = L[sp][tgt].to_numpy("float64")
        PRED[(tgt, sp)] = {
            "Persistence": cur,
            "Raw": predict_member(raw, tgt, sp),
            "Tuned": predict_member(tuned, tgt, sp),
        }
        PRED[(tgt, sp)]["Avg"] = (PRED[(tgt, sp)]["Raw"] + PRED[(tgt, sp)]["Tuned"]) / 2
    raw["model"].save_model(str(MODEL_DIR / f"cb_raw_{tgt}.cbm"))
    tuned["model"].save_model(str(MODEL_DIR / f"cb_tuned_{tgt}.cbm"))
    del raw, tuned
    gc.collect()

MEMBERS = ["Persistence", "Raw", "Tuned"]
STACK_W = {}
for tgt in CORE:
    v, t = L["val"], L["test"]
    yv = v[f"y_future_{tgt}"].to_numpy("float64")
    Pv = np.column_stack([PRED[(tgt, "val")][n] for n in MEMBERS])
    Pt = np.column_stack([PRED[(tgt, "test")][n] for n in MEMBERS])
    hv, ht = v["h"].to_numpy(), t["h"].to_numpy()
    out_v, out_t, W = np.full(len(v), np.nan), np.full(len(t), np.nan), {}
    for h in HORIZONS:
        mf = (hv == h) & np.isfinite(yv) & np.isfinite(Pv).all(1)
        w, _ = nnls(Pv[mf], yv[mf])
        w = w / w.sum() if w.sum() > 0 else np.full(len(MEMBERS), 1 / len(MEMBERS))
        W[h] = w
        out_v[hv == h] = np.where(
            np.isfinite(Pv[hv == h]).all(1), np.nan_to_num(Pv[hv == h]) @ w, np.nan
        )
        out_t[ht == h] = np.where(
            np.isfinite(Pt[ht == h]).all(1), np.nan_to_num(Pt[ht == h]) @ w, np.nan
        )
    PRED[(tgt, "val")]["Stacked"], PRED[(tgt, "test")]["Stacked"] = out_v, out_t
    STACK_W[tgt] = pd.DataFrame(W, index=MEMBERS).T
    print(f"[{tgt}] 리드타임별 가중치")
    print(STACK_W[tgt].loc[[h for h in [1, 3, 6, 12, 24, 48] if h in W]].round(2))


# ======================================================================
# ## D. 평가 표 (TEST: 전체 · 값 구간별 · 리드타임별)
#
# ======================================================================

MODELS = ["Persistence", "Raw", "Tuned", "Avg", "Stacked"]
COLORS = {
    "Persistence": "tab:blue",
    "Raw": "tab:gray",
    "Tuned": "tab:red",
    "Avg": "tab:orange",
    "Stacked": "tab:green",
}


def metr(a, p):
    if len(a) == 0:
        return dict(
            n=0, RMSE=np.nan, MAE=np.nan, Bias=np.nan, relMAE_pct=np.nan, RMSLE=np.nan
        )
    e = p - a
    return dict(
        n=len(a),
        RMSE=float(np.sqrt(np.mean(e**2))),
        MAE=float(np.mean(np.abs(e))),
        Bias=float(np.mean(e)),
        relMAE_pct=float(100 * np.mean(np.abs(e)) / max(np.mean(np.abs(a)), 1e-9)),
        RMSLE=float(
            np.sqrt(
                np.mean(
                    (np.log1p(np.clip(p, 0, None)) - np.log1p(np.clip(a, 0, None))) ** 2
                )
            )
        ),
    )


SPLIT = "test"
OVERALL, BINS, LEADS = {}, {}, {}
for tgt in CORE:
    t = L[SPLIT]
    a = t[f"y_future_{tgt}"].to_numpy("float64")
    P = PRED[(tgt, SPLIT)]
    ok = np.isfinite(a) & np.isfinite(
        t[tgt].to_numpy("float64")
    )  # 현재값이 있는 행만 (모든 모델이 같은 행으로 비교)
    bins = TARGET_CFG[tgt]["bins"]
    labs = bin_labels(bins)
    b = bin_of(a, bins)
    OVERALL[tgt] = pd.DataFrame({n: metr(a[ok], P[n][ok]) for n in MODELS}).T
    BINS[tgt] = pd.concat(
        {
            lab: pd.DataFrame(
                {n: metr(a[ok & (b == i)], P[n][ok & (b == i)]) for n in MODELS}
            ).T
            for i, lab in enumerate(labs)
        },
        names=["구간", "모델"],
    )
    hs = [h for h in [1, 3, 6, 12, 24, 48] if h in HORIZONS]
    hh = t["h"].to_numpy()
    LEADS[tgt] = pd.DataFrame(
        {
            n: [metr(a[ok & (hh == h)], P[n][ok & (hh == h)])["RMSE"] for h in hs]
            for n in MODELS
        },
        index=pd.Index(hs, name="h"),
    )
    unit = TARGET_CFG[tgt]["unit"]
    print(f"\n######## {tgt} ({unit}) — {SPLIT.upper()} ########")
    print("▶ 전체")
    print(OVERALL[tgt].round(3))
    print("▶ 값 구간별 (실측 기준)")
    print(BINS[tgt].round(3))
    print("▶ 리드타임별 RMSE")
    print(LEADS[tgt].round(3))


# ======================================================================
# ## E. 산점도 — 실측 vs 예측 (리드 구간별)
#
# - 시정: 0 ~ 100km 축
# - PM: 전체 범위 + **0 ~ PM_ZOOM 확대** (작은 값에서의 변화가 보이도록)
# - 패널 안 숫자는 **그 축 범위 안의 점만으로** 계산한 RMSE / MAE / Bias
#
# ======================================================================

SCAT_MODEL = "Stacked"


def _season_of_target(df):
    mon = (df["tm"] + pd.to_timedelta(df["h"], unit="h")).dt.month.to_numpy()
    out = np.empty(len(df), dtype=object)
    for s, ms in SEASONS.items():
        out[np.isin(mon, ms)] = s
    return out


T = L["test"]
T_SEASON = _season_of_target(T)
T_H = T["h"].to_numpy()


def _valid(tgt):
    return np.isfinite(T[f"y_future_{tgt}"].to_numpy("float64")) & np.isfinite(
        T[tgt].to_numpy("float64")
    )


def _scatter(ax, a, p, lim, title):
    m = (a >= lim[0]) & (a <= lim[1]) & np.isfinite(p)
    if m.sum() == 0:
        ax.set_title(f"{title} (데이터 없음)")
        return
    ax.hexbin(
        a[m],
        np.clip(p[m], lim[0], lim[1]),
        gridsize=45,
        bins="log",
        cmap="viridis",
        mincnt=1,
        extent=(lim[0], lim[1], lim[0], lim[1]),
    )
    ax.plot(lim, lim, "r--", lw=1)
    e = p[m] - a[m]
    ax.text(
        0.03,
        0.97,
        f"n={m.sum():,}\nRMSE {np.sqrt(np.mean(e**2)):.2f}\nMAE {np.mean(np.abs(e)):.2f}\nBias {np.mean(e):+.2f}",
        transform=ax.transAxes,
        va="top",
        fontsize=9,
        bbox=dict(fc="white", alpha=0.8),
    )
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("실측")
    ax.set_ylabel("예측")


for tgt in CORE:
    unit = TARGET_CFG[tgt]["unit"]
    ok = _valid(tgt)
    a_all = T[f"y_future_{tgt}"].to_numpy("float64")
    p_all = PRED[(tgt, "test")][SCAT_MODEL]
    ranges = (
        [(0, VIS_AXIS_MAX)]
        if tgt == "visibility_km"
        else [(0, float(np.nanpercentile(a_all[ok], 99.5))), (0, PM_ZOOM)]
    )
    fig, axes = plt.subplots(
        len(ranges),
        len(LEAD_GROUPS),
        figsize=(6 * len(LEAD_GROUPS), 5.2 * len(ranges)),
        squeeze=False,
    )
    fig.suptitle(
        f"{tgt} ({unit}) — 실측 vs 예측 [{SCAT_MODEL}, TEST]",
        fontsize=14,
        fontweight="bold",
    )
    for r, lim in enumerate(ranges):
        for c, (gname, (h0, h1)) in enumerate(LEAD_GROUPS.items()):
            m = ok & (T_H >= h0) & (T_H <= h1)
            tag = "확대 " if (tgt != "visibility_km" and r == 1) else ""
            _scatter(
                axes[r, c],
                a_all[m],
                p_all[m],
                lim,
                f"{gname} | {tag}0~{lim[1]:g} {unit}",
            )
    plt.tight_layout()
    plt.show()


# ======================================================================
# ## F. 리드타임별 평가
#
# - 위: 전체 값 기준 RMSE (모델별)
# - 가운데: **낮은 값 구간만** (시정 ≤ 10km / PM ≤ PM_ZOOM) — 작은 값을 잘 맞추는지
# - 아래: Stacked 모델의 **계절별** 리드타임 RMSE
#
# ======================================================================

LOW_RANGE = {"visibility_km": (0, 10), "pm25": (0, PM_ZOOM), "pm10": (0, PM_ZOOM)}
fig, axes = plt.subplots(3, 3, figsize=(22, 14))
for j, tgt in enumerate(CORE):
    unit = TARGET_CFG[tgt]["unit"]
    ok = _valid(tgt)
    a = T[f"y_future_{tgt}"].to_numpy("float64")
    lo, hi = LOW_RANGE[tgt]
    for row, (mask_extra, ttl) in enumerate(
        [
            (np.ones_like(ok), "전체"),
            ((a >= lo) & (a <= hi), f"실측 {lo:g}~{hi:g} {unit}"),
        ]
    ):
        ax = axes[row, j]
        for n in MODELS:
            p = PRED[(tgt, "test")][n]
            rm = [
                (
                    np.sqrt(np.nanmean((p[m] - a[m]) ** 2))
                    if (m := ok & mask_extra & (T_H == h)).any()
                    else np.nan
                )
                for h in HORIZONS
            ]
            ax.plot(
                HORIZONS,
                rm,
                color=COLORS[n],
                lw=2,
                ls=":" if n == "Persistence" else "-",
                label=n,
            )
        ax.set_title(f"{tgt} — 리드별 RMSE ({ttl})")
        ax.set_xlabel("h")
        ax.set_ylabel(unit)
        ax.grid(ls="--", alpha=0.4)
    ax = axes[2, j]
    p = PRED[(tgt, "test")]["Stacked"]
    for s, col in zip(SEASONS, ["tab:green", "tab:red", "tab:orange", "tab:blue"]):
        rm = [
            (
                np.sqrt(np.nanmean((p[m] - a[m]) ** 2))
                if (m := ok & (T_SEASON == s) & (T_H == h)).any()
                else np.nan
            )
            for h in HORIZONS
        ]
        ax.plot(HORIZONS, rm, color=col, lw=2, label=s)
    ax.set_title(f"{tgt} — 계절별 리드 RMSE (Stacked)")
    ax.set_xlabel("h")
    ax.grid(ls="--", alpha=0.4)
axes[0, 0].legend(fontsize=8)
axes[2, 0].legend(fontsize=8)
plt.tight_layout()
plt.show()


# ======================================================================
# ## G. 사례 그래프
#
# ======================================================================

t = L["test"]
t0_, t1_ = t["tm"].min(), t["tm"].max()
CASES = []
for name, mon in [("Spring", 4), ("Summer", 7), ("Autumn", 10), ("Winter", 1)]:
    for yr in range(t0_.year, t1_.year + 1):
        ts = pd.Timestamp(yr, mon, 10, 1)
        if t0_ <= ts <= t1_ - pd.Timedelta(hours=48):
            CASES.append((name, ts))
            break

for tgt in CORE:
    unit = TARGET_CFG[tgt]["unit"]
    st = (
        (t["stn_id"] == CASE_STN).to_numpy()
        & np.isfinite(t[f"y_future_{tgt}"].to_numpy())
        & np.isfinite(t[tgt].to_numpy())
    )
    cnt = t.loc[st].groupby("tm").size()
    good = cnt[cnt >= 0.8 * len(HORIZONS)].index
    fig, axes = plt.subplots(2, 2, figsize=(18, 10))
    fig.suptitle(
        f"{tgt} ({unit}) — STN {CASE_STN} 48시간 사례 (TEST)",
        fontsize=14,
        fontweight="bold",
    )
    for ax, (sname, ts) in zip(axes.ravel(), CASES):
        cand = good[(good >= ts) & (good < ts + pd.Timedelta(days=10))]
        if len(cand) == 0:
            ax.set_title(f"{sname}: 데이터 없음")
            continue
        m = st & (t["tm"] == cand[0]).to_numpy()
        order = np.argsort(t.loc[m, "h"].to_numpy())
        tx = (t.loc[m, "tm"] + pd.to_timedelta(t.loc[m, "h"], unit="h")).to_numpy()[
            order
        ]
        a = t.loc[m, f"y_future_{tgt}"].to_numpy()[order]
        ax.plot(tx, a, color="black", marker=".", lw=1.5, label="Actual")
        for n in MODELS:
            pv = PRED[(tgt, "test")][n][m][order]
            ax.plot(
                tx,
                pv,
                color=COLORS[n],
                lw=1.6 if n == "Persistence" else 2,
                ls=":" if n == "Persistence" else "--",
                label=f"{n} | RMSE={np.sqrt(np.nanmean((pv - a) ** 2)):.2f}",
            )
        if LOG_Y_CASE.get(tgt):
            ax.set_yscale("log")
        elif tgt == "visibility_km":
            ax.set_ylim(0, VIS_AXIS_MAX)
        else:
            top = np.nanmax(a)
            ax.set_ylim(0, PM_ZOOM if top <= PM_ZOOM else top * 1.1)
        ax.set_title(f"{sname} — origin {cand[0]:%Y-%m-%d %H:%M}")
        ax.set_ylabel(unit)
        ax.grid(alpha=0.4)
        ax.legend(fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
    plt.tight_layout()
    plt.show()


# ======================================================================
# ## H. 계절별 성능 표
#
# ======================================================================

t = L["test"]
mon = (t["tm"] + pd.to_timedelta(t["h"], unit="h")).dt.month.to_numpy()
sea = np.empty(len(t), dtype=object)
for s, ms in SEASONS.items():
    sea[np.isin(mon, ms)] = s

SEASON_TBL = {}
for tgt in CORE:
    a = t[f"y_future_{tgt}"].to_numpy("float64")
    ok = np.isfinite(a) & np.isfinite(t[tgt].to_numpy("float64"))
    P = PRED[(tgt, "test")]
    SEASON_TBL[tgt] = pd.concat(
        {
            s: pd.DataFrame(
                {n: metr(a[ok & (sea == s)], P[n][ok & (sea == s)]) for n in MODELS}
            ).T
            for s in SEASONS
        },
        names=["계절", "모델"],
    )
    print(f"\n######## {tgt} — 계절별 (TEST) ########")
    print(SEASON_TBL[tgt][["n", "RMSE", "MAE", "Bias", "relMAE_pct", "RMSLE"]].round(3))

fig, axes = plt.subplots(2, 3, figsize=(22, 9))
x = np.arange(len(SEASONS))
w = 0.8 / len(MODELS)
for j, tgt in enumerate(CORE):
    for row, col in enumerate(["relMAE_pct", "Bias"]):
        ax = axes[row, j]
        for k, n in enumerate(MODELS):
            ax.bar(
                x + k * w,
                [SEASON_TBL[tgt].loc[(s, n), col] for s in SEASONS],
                w,
                label=n,
                color=COLORS[n],
            )
        ax.set_xticks(x + w * (len(MODELS) - 1) / 2)
        ax.set_xticklabels(list(SEASONS))
        ax.set_title(f"{tgt} — 계절별 {col}")
        ax.grid(axis="y", ls="--", alpha=0.4)
        if col == "Bias":
            ax.axhline(0, color="k", lw=0.8)
axes[0, 0].legend(fontsize=8)
plt.tight_layout()
plt.show()


# ======================================================================
# ---
#
# # I. 계절별로 작용하는 물리 요인 분석
#
# 계절은 **분석용 그룹**으로만 사용. 확인할 가설:
#
# 1. **여름 강수 → 세정(washout)**: 비가 오면 미세먼지가 씻겨 내려가고 비 그친 뒤 시정이 길어진다
# 2. **봄 편서풍 → 국외 유입**: 서풍 계열(남서~북서)일 때 PM이 높다 (황사·대륙 유입)
# 3. **바다 영향 → 해무 저시정**: 기온이 해수온보다 높을 때(따뜻한 공기가 찬 바다 위로) 저시정이 잦다 — 특히 봄·초여름
#
# I-1 ~ I-3은 **관측 데이터 자체**에서 관계를 확인하고, I-4 ~ I-5는 **모델이 그 관계를 배웠는지** 확인합니다.
#
# ======================================================================

# 분석용 관측 테이블 (지점별 1시간 축, 계절 라벨은 분석용)
A = d.copy()
A["season"] = A["tm"].dt.month.map({m: s for s, ms in SEASONS.items() for m in ms})
A = A.sort_values(["stn_id", "tm"])
g_ = A.groupby("stn_id")
A["rain_3h"] = g_["precipitation"].transform(
    lambda s: s.rolling(3, min_periods=1).sum()
)  # 최근 3시간 강수
A["rain_prev24"] = g_["precipitation"].transform(
    lambda s: s.rolling(24, min_periods=1).sum()
)  # 최근 24시간 강수
A["air_sea"] = A["temperature"] - A["sea_temp"]  # +면 따뜻한 공기가 찬 바다 위
calm = A["wind_speed"] < 0.5
sec_names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
A["wind_sector"] = pd.Categorical(
    np.where(
        calm,
        "Calm",
        np.array(sec_names)[((A["wind_dir"] + 22.5) % 360 // 45).fillna(0).astype(int)],
    ),
    categories=sec_names + ["Calm"],
)
A["westerly"] = A["wind_sector"].isin(["SW", "W", "NW"])
SEASON_ORDER = list(SEASONS)
print(
    A.groupby("season")[["visibility_km", "pm25", "pm10", "precipitation", "air_sea"]]
    .mean()
    .loc[SEASON_ORDER]
    .round(2)
)


# ======================================================================
# ### I-1. 강수 → 시정 · PM (세정 효과)
#
# ======================================================================

rain_bins = [-0.01, 0, 1, 5, np.inf]
rain_lab = ["무강수", "0~1mm", "1~5mm", "5mm+"]
A["rain_cls"] = pd.cut(A["rain_prev24"], rain_bins, labels=rain_lab)

fig, axes = plt.subplots(1, 3, figsize=(22, 5))
for ax, col, unit in zip(
    axes, ["visibility_km", "pm25", "pm10"], ["km", "㎍/m³", "㎍/m³"]
):
    tbl = (
        A.groupby(["season", "rain_cls"], observed=False)[col]
        .median()
        .unstack()
        .loc[SEASON_ORDER]
    )
    tbl.plot(kind="bar", ax=ax, rot=0, colormap="Blues")
    ax.set_title(f"최근 24h 강수량별 {col} 중앙값 (계절별)")
    ax.set_ylabel(unit)
    ax.grid(axis="y", ls="--", alpha=0.4)
    ax.legend(title="최근 24h 강수", fontsize=8)
plt.tight_layout()
plt.show()

# 비 그친 뒤 시간에 따른 회복 (강수 종료 시점 기준 0~24h 평균, 계절별)
A["rain_now"] = A["precipitation"] > 0
rows = []
for stn, gg in A.groupby("stn_id"):
    gg = gg.set_index("tm").asfreq("h")
    ends = gg.index[
        gg["rain_now"].fillna(False)
        & ~gg["rain_now"].shift(-1).fillna(False).astype(bool)
    ]
    for t0 in ends:
        seg = gg.loc[
            t0 : t0 + pd.Timedelta(hours=24), ["visibility_km", "pm25", "pm10"]
        ]
        seg = seg.assign(k=np.arange(len(seg)), season=gg.loc[t0, "season"])
        rows.append(seg)
REC = pd.concat(rows) if rows else pd.DataFrame()
if len(REC):
    fig, axes = plt.subplots(1, 3, figsize=(22, 4.5))
    for ax, col in zip(axes, ["visibility_km", "pm25", "pm10"]):
        for s, c in zip(
            SEASON_ORDER, ["tab:green", "tab:red", "tab:orange", "tab:blue"]
        ):
            r = REC[REC["season"] == s].groupby("k")[col].mean()
            ax.plot(
                r.index,
                r.values,
                color=c,
                lw=2,
                label=f"{s} (n={REC[(REC.season == s) & (REC.k == 0)].shape[0]})",
            )
        ax.set_title(f"비 그친 뒤 {col} 변화 (0 = 마지막 강수 시각)")
        ax.set_xlabel("경과 시간 (h)")
        ax.grid(ls="--", alpha=0.4)
    axes[0].legend(fontsize=8)
    plt.tight_layout()
    plt.show()


# ======================================================================
# ### I-2. 풍향 → PM (편서풍 유입)
#
# ======================================================================

fig, axes = plt.subplots(1, 3, figsize=(24, 5))
for ax, col in zip(axes, ["pm25", "pm10"]):
    tbl = (
        A.groupby(["season", "wind_sector"], observed=False)[col]
        .mean()
        .unstack()
        .loc[SEASON_ORDER]
    )
    im = ax.imshow(tbl.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(tbl.shape[1]))
    ax.set_xticklabels(tbl.columns)
    ax.set_yticks(range(tbl.shape[0]))
    ax.set_yticklabels(tbl.index)
    for i in range(tbl.shape[0]):
        for k in range(tbl.shape[1]):
            v = tbl.values[i, k]
            if np.isfinite(v):
                ax.text(k, i, f"{v:.0f}", ha="center", va="center", fontsize=9)
    ax.set_title(f"계절 × 풍향별 평균 {col} (㎍/m³)")
    plt.colorbar(im, ax=ax)
# 계절별 서풍계열 빈도
freq = A.groupby("season")["westerly"].mean().loc[SEASON_ORDER] * 100
axes[2].bar(freq.index, freq.values, color="tab:gray")
for i, v in enumerate(freq.values):
    axes[2].text(i, v + 0.5, f"{v:.0f}%", ha="center")
axes[2].set_title("계절별 서풍 계열(SW·W·NW) 빈도 (%)")
axes[2].grid(axis="y", ls="--", alpha=0.4)
plt.tight_layout()
plt.show()

# 서풍이 '먼저' 불고 나서 PM이 오르는지: t의 풍향 vs t+12h / t+24h PM (계절별)
for lag in (12, 24):
    A[f"pm10_+{lag}h"] = g_["pm10"].shift(-lag)
tbl = (
    A.groupby(["season", "westerly"])[["pm10", "pm10_+12h", "pm10_+24h"]]
    .mean()
    .loc[SEASON_ORDER]
    .round(1)
)
tbl.index = tbl.index.set_levels(["기타 풍향", "서풍 계열"], level=1)
print("t 시각 풍향에 따른 현재 / 12h 뒤 / 24h 뒤 PM10 평균 (㎍/m³)")
print(tbl)


# ======================================================================
# ### I-3. 기온−해수온 → 저시정 (해무)
#
# ======================================================================

as_bins = [-np.inf, -4, -2, 0, 2, 4, np.inf]
as_lab = ["<-4", "-4~-2", "-2~0", "0~2", "2~4", ">4"]
A["air_sea_cls"] = pd.cut(A["air_sea"], as_bins, labels=as_lab)
fig, axes = plt.subplots(1, 3, figsize=(24, 5))
for ax, thr in zip(axes[:2], [1, 3]):
    tbl = (
        A.assign(low=A["visibility_km"] < thr)
        .groupby(["season", "air_sea_cls"], observed=False)["low"]
        .mean()
        .unstack()
        .loc[SEASON_ORDER]
        * 100
    )
    im = ax.imshow(tbl.values, cmap="Blues", aspect="auto")
    ax.set_xticks(range(tbl.shape[1]))
    ax.set_xticklabels(tbl.columns)
    ax.set_yticks(range(tbl.shape[0]))
    ax.set_yticklabels(tbl.index)
    for i in range(tbl.shape[0]):
        for k in range(tbl.shape[1]):
            v = tbl.values[i, k]
            if np.isfinite(v):
                ax.text(k, i, f"{v:.1f}", ha="center", va="center", fontsize=9)
    ax.set_xlabel("기온 − 해수온 (℃)  (+: 따뜻한 공기가 찬 바다 위)")
    ax.set_title(f"계절 × 기온−해수온별 시정 < {thr}km 비율 (%)")
    plt.colorbar(im, ax=ax)
# 지점별 (백령도 · 인천 · 강화)
tbl = (
    A.assign(low=A["visibility_km"] < 3, warm=A["air_sea"] > 0)
    .groupby(["stn_id", "season", "warm"])["low"]
    .mean()
    .unstack()
    * 100
)
tbl.columns = ["기온≤해수온", "기온>해수온"]
tbl.unstack("season")["기온>해수온"][SEASON_ORDER].plot(kind="bar", ax=axes[2], rot=0)
axes[2].set_title("지점별 · 계절별: 기온>해수온일 때 시정<3km 비율 (%)")
axes[2].grid(axis="y", ls="--", alpha=0.4)
plt.tight_layout()
plt.show()
print(tbl.round(1))


# ======================================================================
# ### I-4. 모델은 계절마다 무엇을 보고 예측하나 (SHAP, 계절 피처 없이)
#
# - Tuned 모델의 SHAP 값을 TEST 표본에서 계산 → 예측 대상 시각의 계절별 평균 |SHAP| 비율
# - 계절 피처가 없어도 **여름엔 강수, 봄엔 풍향, 해무 계절엔 기온−해수온**의 비중이 커지면 모델이 물리 요인으로 계절성을 배운 것
#
# ======================================================================

SHAP_N = 20000
rng_ = np.random.default_rng(0)
SHAP = {}
for tgt in CORE:
    ok = _valid(tgt)
    idx = np.flatnonzero(ok)
    idx = rng_.choice(idx, min(SHAP_N, len(idx)), replace=False)
    m = CatBoostRegressor()
    m.load_model(str(MODEL_DIR / f"cb_tuned_{tgt}.cbm"))
    sv = m.get_feature_importance(
        Pool(T.iloc[idx][FEATURES], cat_features=["stn_id"]), type="ShapValues"
    )[:, :-1]
    SHAP[tgt] = (idx, pd.DataFrame(sv, columns=FEATURES))

fig, axes = plt.subplots(1, 3, figsize=(26, 9))
for ax, tgt in zip(axes, CORE):
    idx, sv = SHAP[tgt]
    sea_ = T_SEASON[idx]
    imp = pd.DataFrame({s: sv[sea_ == s].abs().mean() for s in SEASON_ORDER})
    imp = imp / imp.sum() * 100  # 계절 내 비율(%)
    top = imp.mean(axis=1).nlargest(18).index
    tbl = imp.loc[top]
    im = ax.imshow(tbl.values, cmap="viridis", aspect="auto")
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top, fontsize=9)
    ax.set_xticks(range(len(SEASON_ORDER)))
    ax.set_xticklabels(SEASON_ORDER)
    for i in range(tbl.shape[0]):
        for k in range(tbl.shape[1]):
            ax.text(
                k,
                i,
                f"{tbl.values[i, k]:.1f}",
                ha="center",
                va="center",
                fontsize=8,
                color="w",
            )
    ax.set_title(f"{tgt} — 계절별 피처 기여 비율 (%, |SHAP|)")
    plt.colorbar(im, ax=ax)
plt.tight_layout()
plt.show()


# ======================================================================
# ### I-5. 핵심 요인의 효과가 계절마다 다른가 (SHAP 의존도, 색 = 계절)
#
# ======================================================================

KEY = {
    "visibility_km": [
        "precipitation",
        "future_fcst_precipitation",
        "future_fcst_pop",
        "air_sea_diff",
        "f_air_sea_diff",
        "humidity",
        "f_dpd",
        "sea_air_temp_diff",
    ],
    "pm25": [
        "u",
        "v",
        "wind_dir_sin",
        "wind_dir_cos",
        "wind_speed",
        "future_fcst_wind_speed",
        "precipitation",
        "future_fcst_pm25_grade",
    ],
    "pm10": [
        "u",
        "v",
        "wind_dir_sin",
        "wind_dir_cos",
        "wind_speed",
        "future_fcst_wind_speed",
        "precipitation",
        "future_fcst_pm25_grade",
    ],
}
S_COL = dict(zip(SEASON_ORDER, ["tab:green", "tab:red", "tab:orange", "tab:blue"]))
for tgt in CORE:
    idx, sv = SHAP[tgt]
    feats = [f for f in KEY[tgt] if f in sv.columns][:6]
    if not feats:
        continue
    fig, axes = plt.subplots(
        1, len(feats), figsize=(4.6 * len(feats), 4.2), squeeze=False
    )
    xv = T.iloc[idx]
    sea_ = T_SEASON[idx]
    for ax, f in zip(axes[0], feats):
        x = xv[f].to_numpy("float64")
        y = sv[f].to_numpy()
        for s in SEASON_ORDER:
            m = (sea_ == s) & np.isfinite(x)
            ax.scatter(x[m], y[m], s=3, alpha=0.25, color=S_COL[s], label=s)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(f)
        ax.set_xlabel("값")
        ax.grid(ls="--", alpha=0.3)
    axes[0, 0].set_ylabel("SHAP (예측 Δ에 대한 기여)")
    axes[0, 0].legend(markerscale=4, fontsize=8)
    fig.suptitle(f"{tgt} — 핵심 요인 효과 (계절별 색)", fontweight="bold")
    plt.tight_layout()
    plt.show()


# ======================================================================
# ### I-6. 요인별 조건에서 모델 오차 — 어디서 틀리나
#
# 같은 계절이라도 **비 올 때 / 서풍일 때 / 기온>해수온일 때** 오차(Bias: + 과대, − 과소)가 어떻게 다른지
#
# ======================================================================

key_ = pd.MultiIndex.from_arrays([T["stn_id"].astype(str), T["tm"]])
AI = A.set_index(["stn_id", "tm"])
cond = {
    "비(최근24h>0)": AI["rain_prev24"].reindex(key_).to_numpy() > 0,
    "서풍 계열": AI["westerly"].reindex(key_).fillna(False).to_numpy(bool),
    "기온>해수온": AI["air_sea"].reindex(key_).to_numpy() > 0,
}
rows = []
for tgt in CORE:
    ok = _valid(tgt)
    a = T[f"y_future_{tgt}"].to_numpy("float64")
    p = PRED[(tgt, "test")]["Stacked"]
    for cname, cm in cond.items():
        cm = np.asarray(cm, dtype=bool)
        for s in SEASON_ORDER:
            for flag, lab in ((True, "예"), (False, "아니오")):
                m = ok & (T_SEASON == s) & (cm == flag)
                if m.sum() < 50:
                    continue
                e = p[m] - a[m]
                rows.append(
                    dict(
                        타깃=tgt,
                        조건=cname,
                        계절=s,
                        해당=lab,
                        n=int(m.sum()),
                        RMSE=np.sqrt(np.mean(e**2)),
                        Bias=np.mean(e),
                    )
                )
ERR = pd.DataFrame(rows)
print(
    ERR.pivot_table(index=["타깃", "조건", "해당"], columns="계절", values="Bias")[
        SEASON_ORDER
    ].round(2)
)
print(
    ERR.pivot_table(index=["타깃", "조건", "해당"], columns="계절", values="RMSE")[
        SEASON_ORDER
    ].round(2)
)
