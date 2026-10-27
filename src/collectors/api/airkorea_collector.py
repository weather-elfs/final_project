# -*- coding: utf-8 -*-
"""AirKorea 3개 측정소 수집: python airkorea_collector.py --realtime"""

import argparse
import json
import logging
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

URL = (
    "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
)
STATIONS = {
    "석모리": (831481, "인천 강화군"),
    "백령도": (831492, "인천 옹진군"),
    "숭의": (823632, "인천 남구"),
}
COLUMNS = [
    "날짜",
    "시도",
    "측정소명",
    "아황산가스",
    "일산화탄소",
    "오존",
    "측정소코드",
    "이산화질소",
    "PM10",
    "PM2.5",
]
NUMBERS = ["아황산가스", "일산화탄소", "오존", "이산화질소", "PM10", "PM2.5"]


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def fetch(name, key, retries, *, on_response=None):
    params = {
        "serviceKey": key,
        "returnType": "json",
        "numOfRows": 100,
        "pageNo": 1,
        "stationName": name,
        "dataTerm": "DAILY",
        "ver": "1.3",
    }
    request = urllib.request.Request(
        URL + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "WeatherElfs-AirKoreaCollector/1.0"},
    )
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8-sig"))
            if on_response:
                on_response(payload)
            response = payload.get("response", {})
            header = response.get("header", {})
            if str(header.get("resultCode")) not in ("00", "0"):
                raise ValueError("API 결과 코드: " + str(header.get("resultCode")))
            items = response.get("body", {}).get("items", [])
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                raise ValueError("응답 items 형식 오류")
            logging.getLogger(__name__).info("[%s] 원본 %s건", name, len(items))
            return items
        except Exception as error:
            last_error = error
            if on_response and isinstance(error, urllib.error.HTTPError):
                try:
                    document = json.loads(error.read(16384))
                except (ValueError, OSError):
                    document = {
                        "response": {
                            "header": {
                                "resultCode": error.code,
                                "resultMsg": "HTTP 오류: JSON 응답 없음",
                            }
                        }
                    }
                on_response(document)
            # 인증키가 포함된 전체 요청 URL을 로그에 출력하지 않음
            logging.getLogger(__name__).warning(
                "[%s] 요청 실패 (%s/%s): %s",
                name,
                attempt,
                retries,
                type(error).__name__,
            )
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError(f"{name} 측정소 수집 실패") from last_error


def normalize(name, items):
    code, province = STATIONS[name]
    rows = []
    for item in items:
        date = str(item.get("dataTime") or "").strip()
        if not date:
            continue
        rows.append(
            {
                "날짜": date,
                "시도": province,
                "측정소명": name,
                "아황산가스": number(item.get("so2Value")),
                "일산화탄소": number(item.get("coValue")),
                "오존": number(item.get("o3Value")),
                "측정소코드": code,
                "이산화질소": number(item.get("no2Value")),
                "PM10": number(item.get("pm10Value")),
                "PM2.5": number(item.get("pm25Value")),
            }
        )
    return rows


def standardize(df):
    df = df.reindex(columns=COLUMNS)
    for col in ("날짜", "시도", "측정소명"):
        df[col] = df[col].astype("string")
    df["측정소코드"] = pd.to_numeric(df["측정소코드"], errors="coerce").astype("Int64")
    for col in NUMBERS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    return df


def collect(key, output, retries):
    rows = []
    for name in STATIONS:
        rows.extend(normalize(name, fetch(name, key, retries)))
    if not rows:
        raise RuntimeError("수집된 데이터가 없습니다.")
    incoming = standardize(pd.DataFrame(rows))
    if output.exists():
        old = standardize(
            pd.read_csv(output, encoding="utf-8-sig", dtype={"측정소코드": "string"})
        )
        df = pd.concat([old, incoming], ignore_index=True)
    else:
        df = incoming
    df = df.drop_duplicates(subset=["측정소코드", "날짜"], keep="last")
    df = df.sort_values(["측정소코드", "날짜"]).reset_index(drop=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".csv.tmp")
    try:
        df.to_csv(temp, index=False, encoding="utf-8-sig")
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    print(
        f"[저장 완료] 이번 조회 {len(incoming)}건 / 누적 {len(df)}건 → {output.resolve()}"
    )
    print("[측정소별 최신 관측(KST)]")
    print(df.groupby("측정소명")["날짜"].max().to_string())
    print("[미리보기]")
    print(df[["날짜", "측정소명", "PM10", "PM2.5"]].tail(9).to_string(index=False))


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--realtime", action="store_true", help="1회 수집 (기본값)")
    parser.add_argument("--loop", action="store_true", help="반복 수집")
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/airkorea/airkorea_realtime_3stations.csv"),
    )
    args = parser.parse_args()
    if args.interval_minutes < 1 or args.retries < 1:
        parser.error("반복 주기와 재시도 횟수는 1 이상이어야 합니다.")
    key = os.getenv("AIRKOREA_API_KEY", "").strip()
    if not key:
        parser.error("AIRKOREA_API_KEY 환경변수가 설정되지 않았습니다.")
    try:
        while True:
            collect(key, args.output, args.retries)
            if not args.loop:
                return 0
            print(f"[대기] {args.interval_minutes}분 후 재조회 (Ctrl+C 종료)")
            time.sleep(args.interval_minutes * 60)
    except KeyboardInterrupt:
        print("[종료] 사용자 중단")
        return 0
    except Exception as error:
        print(
            f"[오류] {type(error).__name__}: 수집 또는 저장에 실패했습니다.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
