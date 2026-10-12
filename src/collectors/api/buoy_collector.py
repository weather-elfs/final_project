"""KMA marine buoy hourly collector. All timestamps are Korea Standard Time (KST)."""
import argparse
import io
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

API_URL = 'https://apihub.kma.go.kr/api/typ01/url/kma_buoy2.php'
STATIONS = {'연평도': '22522', '인천': '22185', '덕적도': '22101', '풍도': '22303'}
COLUMNS = ['TM', 'STN', 'WD1', 'WS1', 'WS1_GST', 'WD2', 'WS2', 'WS2_GST',
           'PA', 'HM', 'TA', 'TW', 'WH_MAX', 'WH_SIG', 'WH_AVE', 'WP', 'WO']
DEFAULT_OUTPUT = Path('data/raw/buoy/해양실시간데이터.csv')
MISSING = {'-99', '-99.0', '-999', '-999.0', '-9', '-9.0', '-9999', '-9999.0', ''}


def parse_buoy_data(raw_text: str, station_id: str) -> pd.DataFrame:
    """Parse KMA text. Reject error pages and malformed rows rather than saving them."""
    rows = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or line.startswith('7777END'):
            continue
        parts = [x.strip() for x in line.split(',')] if ',' in line else line.split()
        if len(parts) < len(COLUMNS):
            continue
        parts = parts[:len(COLUMNS)]
        if not (parts[0].isdigit() and len(parts[0]) == 12 and parts[1] == station_id):
            continue
        rows.append([None if x in MISSING else x for x in parts])
    return pd.DataFrame(rows, columns=COLUMNS)


def fetch_buoy(session, station_id, start, end, auth_key, retries=3):
    params = {'tm1': start.strftime('%Y%m%d%H%M'),
              'tm2': end.strftime('%Y%m%d%H%M'),
              'stn': station_id, 'authKey': auth_key}
    for attempt in range(1, retries + 1):
        try:
            response = session.get(API_URL, params=params, timeout=120)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'euc-kr'
            return parse_buoy_data(response.text, station_id)
        except requests.RequestException as exc:
            status = exc.response.status_code if isinstance(exc, requests.HTTPError) and exc.response is not None else None
            if status is not None and status not in (429, 500, 502, 503, 504):
                raise RuntimeError(f'HTTP {status}: API 권한/인증키 및 요청 조건을 확인하세요') from exc
            if attempt == retries:
                raise
            wait = 5 * attempt
            print(f'  요청 실패 ({exc}); {wait}초 후 재시도 ({attempt}/{retries})', file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError('API 요청 실패')


def format_dataframe(df):
    if df.empty:
        return df
    df = df.copy()
    df['TM'] = pd.to_datetime(df['TM'], format='%Y%m%d%H%M', errors='coerce')
    for col in COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df[df['TM'].notna() & df['TM'].dt.minute.eq(0)].copy()
    df = df.drop_duplicates(subset=['STN', 'TM'], keep='last')
    return df.sort_values(['STN', 'TM']).reset_index(drop=True)


def collect_all(session, auth_key, start, end):
    all_data = []
    failed = []
    for station_name, station_id in STATIONS.items():
        print(f'[{station_name} {station_id}] 조회 시작')
        chunks = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=1) - timedelta(minutes=1), end)
            try:
                part = fetch_buoy(session, station_id, cursor, chunk_end, auth_key)
                print(f'  {cursor:%Y-%m-%d %H:%M} ~ {chunk_end:%Y-%m-%d %H:%M}: 원본 {len(part)}건')
                if not part.empty:
                    chunks.append(part)
            except Exception as exc:
                print(f'  수집 실패: {exc}', file=sys.stderr)
                failed.append(station_name)
                break
            cursor = chunk_end + timedelta(minutes=1)
        if station_name in failed:
            continue
        if not chunks:
            print(f'  데이터 없음: {station_name}', file=sys.stderr)
            failed.append(station_name)
            continue
        station_df = format_dataframe(pd.concat(chunks, ignore_index=True))
        if station_df.empty:
            failed.append(station_name)
            continue
        station_df.insert(0, 'station_name', station_name)
        all_data.append(station_df)
        print(f'  정시 데이터 {len(station_df)}건, 최신 관측 {station_df.TM.max()}')
    if failed:
        raise RuntimeError(f'4개 부이 중 수집 실패: {", ".join(failed)}. 기존 CSV는 변경하지 않습니다.')
    combined = pd.concat(all_data, ignore_index=True)
    actual = set(combined['STN'].dropna().astype(int).astype(str))
    if actual != set(STATIONS.values()):
        raise RuntimeError(f'지점 검증 실패: {actual}. 기존 CSV는 변경하지 않습니다.')
    return combined.sort_values(['station_name', 'TM']).reset_index(drop=True)


def save_data(df, output, mode):
    output.parent.mkdir(parents=True, exist_ok=True)
    if mode == 'append' and output.exists():
        existing = pd.read_csv(output, encoding='utf-8-sig', dtype={'STN': 'Int64'})
        if not set(['STN', 'TM', 'station_name']).issubset(existing.columns):
            raise ValueError('기존 CSV 스키마가 달라 병합을 중단합니다. 기존 파일은 유지됩니다.')
        existing['TM'] = pd.to_datetime(existing['TM'], errors='coerce')
        if existing['TM'].isna().any():
            raise ValueError('기존 CSV에 해석 불가능한 TM 값이 있어 병합을 중단합니다.')
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(['STN', 'TM'], keep='last')
        df = df.sort_values(['station_name', 'TM']).reset_index(drop=True)
    temp = output.with_name(output.name + '.tmp')
    try:
        df.to_csv(temp, index=False, encoding='utf-8-sig', date_format='%Y-%m-%d %H:%M:%S')
        temp.replace(output)
    finally:
        if temp.exists():
            temp.unlink()
    print(f'[저장 완료] {len(df):,}건 → {output.resolve()}')
    print('[부이별 최신 관측(KST)]')
    print(df.groupby('station_name')['TM'].max().to_string())
    print('[미리보기]')
    print(df[['station_name', 'STN', 'TM', 'WS1', 'WH_SIG', 'TA', 'HM']].tail(8).to_string(index=False))


def next_wait(target_minute):
    now = datetime.now()
    target = now.replace(minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(hours=1)
    return max(1, (target - now).total_seconds())


def main():
    parser = argparse.ArgumentParser(description='기상청 해양부이 정시 관측자료 수집기 (KST)')
    parser.add_argument('--realtime', '-r', action='store_true', help='최근 기간 수집 (기본 3일)')
    parser.add_argument('--loop', action='store_true', help='매시 지정 분에 반복 수집 (Ctrl+C 종료)')
    parser.add_argument('--days', type=int, default=3, help='최근 조회 일수 (기본 3일)')
    parser.add_argument('--start', help='수집 시작 KST (YYYYMMDDHHMM)')
    parser.add_argument('--end', help='수집 종료 KST (YYYYMMDDHHMM)')
    parser.add_argument('--minute', type=int, default=20, help='반복 실행 분 (기본 매시 20분)')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help='CSV 출력 경로')
    parser.add_argument('--save-mode', choices=['append', 'overwrite'], default='append')
    parser.add_argument('--auth-key', default=None, help='API 키 (권장: KMA_AUTH_KEY 환경변수)')
    args = parser.parse_args()
    key = args.auth_key or os.getenv('KMA_AUTH_KEY')
    if not key:
        parser.error('API 인증키가 없습니다. PowerShell에서 $env:KMA_AUTH_KEY 를 설정하세요.')
    if args.days < 1 or not 0 <= args.minute <= 59:
        parser.error('--days는 1 이상, --minute은 0~59여야 합니다.')
    if (args.start or args.end) and (args.realtime or args.loop):
        parser.error('--start/--end는 --realtime 또는 --loop와 함께 사용할 수 없습니다.')
    if bool(args.start) != bool(args.end):
        parser.error('--start와 --end를 함께 입력하세요.')
    try:
        with requests.Session() as session:
            while True:
                if args.start:
                    start = datetime.strptime(args.start, '%Y%m%d%H%M')
                    end = datetime.strptime(args.end, '%Y%m%d%H%M')
                else:
                    end = datetime.now().replace(minute=0, second=0, microsecond=0)
                    start = end - timedelta(days=args.days)
                if start > end:
                    parser.error('시작 시각이 종료 시각보다 늦습니다.')
                print(f'\n[해양부이] 수집 기간(KST): {start:%Y%m%d%H%M} ~ {end:%Y%m%d%H%M}')
                try:
                    df = collect_all(session, key, start, end)
                    save_data(df, args.output, args.save_mode)
                except Exception as exc:
                    print(f'[수집 오류] {exc}', file=sys.stderr)
                    if not args.loop:
                        return 1
                if not args.loop:
                    break
                wait = next_wait(args.minute)
                print(f'[대기] 다음 수집까지 약 {wait / 60:.1f}분 (Ctrl+C 종료)')
                time.sleep(wait)
    except KeyboardInterrupt:
        print('\n[종료] 사용자 요청으로 중단했습니다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
