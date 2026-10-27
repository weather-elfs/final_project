"""최신 튜닝 가중치와 노트북의 재학습 구간 출력 복원 계수를 저장한다. 학습하지 않는다."""

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from backend.model_predict import MODEL_VERSION
from catboost import CatBoostRegressor

TARGETS = ("visibility_km", "pm25", "pm10")
OUTPUT = Path(__file__).resolve().parent / "models" / "forecast_tuned"


def import_models(archive, weights_directory, notebook):
    """재학습(Train+Val) 리드 표준편차를 복원하고 검증한 모델을 저장한다."""
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
            "version": MODEL_VERSION,
            "observation_archive_sha256": hashlib.sha256(
                Path(archive).read_bytes()
            ).hexdigest(),
            "observation_parquet_sha256": hashlib.sha256(
                bundle.read(entry)
            ).hexdigest(),
            "recipe": "관측소별_저시정개선학습.ipynb cells 12, 15, 17 (refit Tuned)",
            "recipe_sha256": hashlib.sha256(Path(notebook).read_bytes()).hexdigest(),
            "train_start": "2022-04-01",
            "train_end_exclusive": "2025-04-01",
            "transform": "log1p_residual_horizon_normalized",
            "ensemble": "Tuned (Switch/Stacked weights not exported)",
            "targets": {},
        }
        artifacts = {}
        for target in TARGETS:
            coefficients, clip_max = {}, None
            sample_count = 0
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
                    sample_count += int(valid.sum())
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
            if sample_count != 3_136_858:
                raise ValueError(
                    f"노트북 재학습 표본 수 불일치: {target} / {sample_count}"
                )
            model_bytes = (
                Path(weights_directory) / f"cb_tuned_{target}.cbm"
            ).read_bytes()
            model = CatBoostRegressor().load_model(blob=model_bytes)
            if len(model.feature_names_) != 89:
                raise ValueError("최신 모델은 89개 입력이어야 합니다.")
            if "features" in metadata and metadata["features"] != model.feature_names_:
                raise ValueError("튜닝 모델들의 입력 순서가 다릅니다.")
            metadata["features"] = model.feature_names_
            filename = f"cb_tuned_{target}.cbm"
            artifacts[filename] = model_bytes
            metadata["targets"][target] = {
                "file": filename,
                "sha256": hashlib.sha256(model_bytes).hexdigest(),
                "sigma_by_h": coefficients,
                "clip_max": clip_max,
                "refit_sample_count": sample_count,
            }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        for filename, blob in artifacts.items():
            (OUTPUT / filename).write_bytes(blob)
        path = OUTPUT / "metadata.json"
        text = json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("weights_directory", type=Path)
    parser.add_argument("notebook", type=Path)
    args = parser.parse_args()
    info = import_models(args.archive, args.weights_directory, args.notebook)
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
