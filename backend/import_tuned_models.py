"""전달 ZIP의 튜닝 모델과 학습 당시 출력 복원 계수만 추출한다. 학습은 하지 않는다."""

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

TARGETS = ("visibility_km", "pm25", "pm10")
OUTPUT = Path(__file__).resolve().parent / "models" / "forecast_tuned"


def import_models(archive):
    """원본 노트북의 train-only 리드 표준편차를 복원하고 모델과 함께 저장한다."""
    with zipfile.ZipFile(archive) as bundle:
        entry = next(
            n for n in bundle.namelist() if n.endswith("mart_tide_anchor_obs.parquet")
        )
        data = pd.read_parquet(
            io.BytesIO(bundle.read(entry)), columns=["tm", "stn_id", *TARGETS]
        )
        data["tm"] = pd.to_datetime(data["tm"])
        data = data.drop_duplicates(["stn_id", "tm"]).sort_values(["stn_id", "tm"])
        grouped = [g.set_index("tm").asfreq("h") for _, g in data.groupby("stn_id")]
        metadata = {
            "name": "catboost_observation_forecast_tuned",
            "archive_sha256": hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
            "recipe": "피처확인_관측예보_분석.ipynb cells 13, 14, 17, 19",
            "train_start": "2022-04-01",
            "train_end_exclusive": "2024-04-01",
            "transform": "log1p_residual_horizon_normalized",
            "targets": {},
        }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for target in TARGETS:
            coefficients, clip_max = {}, None
            for h in range(1, 49):
                residuals = []
                for g in grouped:
                    future = g.index + pd.Timedelta(hours=h)
                    cur = g[target].to_numpy(np.float32)
                    y = g[target].reindex(future).to_numpy(np.float32)
                    valid = (
                        (g.index >= metadata["train_start"])
                        & (future < metadata["train_end_exclusive"])
                        & np.isfinite(cur)
                        & np.isfinite(y)
                    )
                    residuals.append(
                        np.log1p(np.maximum(y[valid].astype(float), 0))
                        - np.log1p(np.maximum(cur[valid].astype(float), 0))
                    )
                    if target == "visibility_km":
                        # 상한은 현재값 결측 여부와 무관한 train 타깃 전체의 최대값이다.
                        train = (g.index >= metadata["train_start"]) & (
                            future < metadata["train_end_exclusive"]
                        )
                        values = y[train & np.isfinite(y)]
                        if len(values):
                            clip_max = max(clip_max or 0, float(values.max()))
                sigma = float(pd.Series(np.concatenate(residuals)).std())
                if not np.isfinite(sigma):
                    raise ValueError(f"복원 계수의 자료 부족: {target} h={h}")
                coefficients[str(h)] = max(sigma, 1e-6)
            entry = next(
                n for n in bundle.namelist() if n.endswith(f"/cb_tuned_{target}.cbm")
            )
            model_bytes = bundle.read(entry)
            model = CatBoostRegressor().load_model(blob=model_bytes)
            if "features" in metadata and metadata["features"] != model.feature_names_:
                raise ValueError("튜닝 모델들의 입력 순서가 다릅니다.")
            metadata["features"] = model.feature_names_
            filename = f"cb_tuned_{target}.cbm"
            path = OUTPUT / filename
            if path.exists() and path.read_bytes() != model_bytes:
                raise FileExistsError(f"기존 모델 덮어쓰기 금지: {filename}")
            path.write_bytes(model_bytes)
            metadata["targets"][target] = {
                "file": filename,
                "sha256": hashlib.sha256(model_bytes).hexdigest(),
                "sigma_by_h": coefficients,
                "clip_max": clip_max,
            }
        path = OUTPUT / "metadata.json"
        text = json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise FileExistsError("기존 모델 메타데이터 덮어쓰기 금지")
        path.write_text(text, encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    info = import_models(parser.parse_args().archive)
    print(
        json.dumps(
            {
                "model": info["name"],
                "features": len(info["features"]),
                "targets": list(info["targets"]),
                "trained": False,
            },
            ensure_ascii=False,
        )
    )
