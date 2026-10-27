"""ASOS CSV 데이터를 PostgreSQL에 적재하기 위한 도구."""

import argparse
from contextlib import nullcontext
from pathlib import Path

import pandas as pd

DEFAULT_CSV = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "collectors"
    / "api"
    / "data"
    / "raw"
    / "asos"
    / "asos_test_20261021.csv"
)


def validate_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV 파일을 찾을 수 없습니다: {csv_path}")

    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    if len(df.columns) != 19:
        raise ValueError(f"CSV 컬럼 수 오류: 19개 예상, {len(df.columns)}개 확인")

    if df.empty:
        raise ValueError("CSV에 관측 데이터가 없습니다.")

    column_mapping = {
        "지점": "stn_id",
        "station_name": "stn_ko",
        "일시": "tm",
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

    missing = set(column_mapping) - set(df.columns)
    if missing:
        raise ValueError(f"필수 CSV 컬럼 누락: {sorted(missing)}")

    df = df.rename(columns=column_mapping)

    df["stn_id"] = df["stn_id"].astype(str)
    df["tm"] = pd.to_datetime(df["tm"], errors="raise")

    numeric_columns = [
        col for col in column_mapping.values() if col not in ("stn_id", "stn_ko", "tm")
    ]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # 일사량의 음수 값은 유효한 관측값이 아니므로 결측 처리

    df.loc[df["solar_radiation"] < 0, "solar_radiation"] = float("nan")

    if df.duplicated(subset=["tm", "stn_id"]).any():
        raise ValueError("관측시각과 관측소 ID가 중복된 행이 있습니다.")

    return df


def prepare_records(df: pd.DataFrame) -> list[dict]:
    """검증된 DataFrame을 DB 적재용 레코드로 변환한다."""
    records = df.astype(object).where(pd.notna(df), None).to_dict("records")

    for record in records:
        record["tm"] = record["tm"].to_pydatetime()
        record["stn_id"] = str(record["stn_id"])

    return records


def insert_records(records: list[dict], apply: bool = False, connection=None) -> int:
    """ASOS 관측자료 적재. 기본값은 DB에 쓰지 않는 dry-run."""
    if not apply:
        print(f"[DRY-RUN] 적재 후보 {len(records)}건 / DB 변경 없음")
        return 0

    from backend.database import get_connection

    columns = [
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

    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)

    sql = f"""
    INSERT INTO public.raw_weather_asos_realtime ({column_sql})
    VALUES ({placeholders})
    ON CONFLICT (tm, stn_id) DO UPDATE SET
    {', '.join(f'{col} = EXCLUDED.{col}' for col in columns if col not in ('tm', 'stn_id'))}
    """

    inserted = 0

    with (
        nullcontext(connection) if connection is not None else get_connection()
    ) as conn:
        with conn.cursor() as cur:
            for record in records:
                cur.execute(sql, tuple(record[col] for col in columns))
                inserted += cur.rowcount

    print(f"[DB 적재 완료] 반영 {inserted}건")
    return inserted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ASOS CSV DB 적재 도구")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help="적재할 ASOS CSV 파일 경로",
    )
    args = parser.parse_args()

    data = validate_csv(args.csv)
    records = prepare_records(data)

    print(f"[CSV 검증 성공] {len(records)}건")
    insert_records(records)  # 기본 dry-run
