"""[백엔드 1] 구글 드라이브 Parquet 캐시 데이터셋 고속 다운로드 유틸리티.

1. 관측 마트: mart_tide_anchor_obs.parquet (mart_tide_anchor_obs_fixed.parquet 호환)
   - 파일 ID: 1o8wV5c-Gfigr4U9zfbc0CU8rptkGeHfy
2. 48시간 단기예보 전용 마트: mart_forecast_pit_48h.parquet
   - 파일 ID: 1yFYhYMZeE3E9wsGcs8kgIXqZtBqSbZkl
위 2개 핵심 정제 마트를 data/processed/ 디렉토리로 안전하게 다운로드한다.
"""

import re
import shutil
from pathlib import Path
import gdown

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "processed"

# 최신 2종 마트 구글 드라이브 파일 ID 및 저장 파일명
DATASET_CONFIG = {
    "obs": {
        "file_id": "1o8wV5c-Gfigr4U9zfbc0CU8rptkGeHfy",
        "output_file": OUTPUT_DIR / "mart_tide_anchor_obs.parquet",
        "fixed_output_file": OUTPUT_DIR / "mart_tide_anchor_obs_fixed.parquet",
        "desc": "순수 관측 마트 (mart_tide_anchor_obs / fixed)",
    },
    "fcst": {
        "file_id": "1yFYhYMZeE3E9wsGcs8kgIXqZtBqSbZkl",
        "output_file": OUTPUT_DIR / "mart_forecast_pit_48h.parquet",
        "desc": "48시간 단기예보 전용 마트 (mart_forecast_pit_48h)",
    },
}


def get_clean_id(raw_val: str) -> str:
    """전체 URL이 들어와도 순수 파일 ID만 자동 추출한다."""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", raw_val)
    if match:
        return match.group(1)
    return raw_val.strip()


def download_single_dataset(target_key: str) -> None:
    """특정 데이터셋을 다운로드하고 호환 사본을 생성한다."""
    cfg = DATASET_CONFIG.get(target_key)
    if not cfg:
        print(f"[오류] 유효하지 않은 데이터셋 키: {target_key} (가능: obs, fcst)")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_id = get_clean_id(cfg["file_id"])
    output_file = cfg["output_file"]

    print(f"\n[{cfg['desc']} 다운로드 시작]")
    print(f" -> 구글 드라이브 파일 ID: {file_id}")
    print(f" -> 저장 대상 경로: {output_file}")

    gdown.download(id=file_id, output=str(output_file), quiet=False)

    if output_file.exists():
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f" -> [성공] {output_file.name} 다운로드 완료! (용량: {size_mb:.2f} MB)")

        # obs_fixed 호환용 사본 자동 생성
        if "fixed_output_file" in cfg:
            fixed_file = cfg["fixed_output_file"]
            shutil.copy2(output_file, fixed_file)
            print(f" -> [호환 완료] {fixed_file.name} 사본 생성 완료")
    else:
        print(f" -> [실패] {output_file.name} 다운로드 실패. 구글 드라이브 공유 권한을 확인하세요.")


def download_all_datasets() -> None:
    """2종의 필수 Parquet 데이터셋을 일괄 다운로드한다."""
    print("=" * 70)
    print("2종 Parquet 마트 데이터셋 다운로드 시작...")
    print("=" * 70)
    for key in DATASET_CONFIG:
        download_single_dataset(key)
    print("\n" + "=" * 70)
    print("[전체 완료] 모든 데이터셋 다운로드 및 호환 파일 동기화가 종료되었습니다.")
    print("=" * 70)


if __name__ == "__main__":
    download_all_datasets()
