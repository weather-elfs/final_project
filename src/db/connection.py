"""데이터베이스 접속 및 커넥션 풀 관리 모듈.

.env 파일의 POSTGRES_* 환경변수를 로드하여 psycopg2 커넥션 및 SQLAlchemy Engine을 제공한다.
"""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# 프로젝트 루트의 .env 로드
BASE_DIR = Path(__file__).resolve().parent.parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(env_path)

# .env에서만 환경변수 조회
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")

# 필수 환경변수 검증
required_vars = {
    "POSTGRES_HOST": DB_HOST,
    "POSTGRES_PORT": DB_PORT,
    "POSTGRES_DB": DB_NAME,
    "POSTGRES_USER": DB_USER,
    "POSTGRES_PASSWORD": DB_PASSWORD,
}

missing = [key for key, val in required_vars.items() if not val]
if missing:
    raise EnvironmentError(
        f"[오류] .env 파일이 없거나 필수 환경변수가 누락되었습니다: {', '.join(missing)}\n"
        f"경로를 확인하십시오: {env_path}"
    )


def get_db_engine() -> Engine:
    """SQLAlchemy Engine 객체 반환."""
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url, pool_pre_ping=True)


def get_raw_connection():
    """초고속 벌크 적재를 위한 psycopg2 순수 커넥션 반환."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


if __name__ == "__main__":
    try:
        conn = get_raw_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, inet_server_port();")
            db, user, port = cur.fetchone()
            print(f"[연결 성공] DB: {db}, 계정: {user}, 포트: {port}")
        conn.close()
    except Exception as e:
        print(f"[연결 실패] {e}")
