"""[백엔드 1] 구글 드라이브 Parquet 캐시 데이터셋 다운로드 유틸리티."""

import re
from pathlib import Path

import gdown

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "processed"
OUTPUT_FILE = OUTPUT_DIR / "mart_base_anchor.parquet"

# 구글 드라이브 공유 링크 또는 파일 ID
GDRIVE_FILE_ID = "1iVzSTUolL5ucGS-ReHyNgSfpqMWRK6vc"


def get_clean_id(raw_val: str) -> str:
    """전체 URL이 들어와도 순수 파일 ID만 자동 추출한다."""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", raw_val)
    if match:
        return match.group(1)
    return raw_val.strip()


def download_dataset():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    file_id = get_clean_id(GDRIVE_FILE_ID)

    print(f"[다운로드 시작] 파일 ID: {file_id}")
    print(f" -> 대상 경로: {OUTPUT_FILE}")

    # gdown의 id 기반 직접 다운로드 사용
    gdown.download(id=file_id, output=str(OUTPUT_FILE), quiet=False)

    if OUTPUT_FILE.exists():
        size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
        print(f"\n[완료] {OUTPUT_FILE} 다운로드 성공! (용량: {size_mb:.2f} MB)")
    else:
        print(
            "\n[실패] 파일 다운로드에 실패함. 구글 드라이브 권한(링크가 있는 모든 사용자-뷰어)을 확인해야 함."
        )


if __name__ == "__main__":
    download_dataset()
