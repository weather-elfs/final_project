# 백엔드 API 실행 가이드

## 1. 개요

본 백엔드는 FastAPI 기반으로 해양·기상 관측 데이터를 조회하고 CatBoost 모델을 활용하여 시정거리, PM2.5, PM10 예측 결과를 제공합니다.

주요 기능:

- ASOS, AirKorea 및 해양 관측 데이터 조회
- CatBoost 기반 예측
- 1·3·6·12시간 예측 간격 지원
- 해상 수송·보급 임무 판정(MVP)
- Swagger API 문서 제공

## 2. 실행 환경

- Python 3.12
- PostgreSQL 데이터베이스 접속 필요
- 백엔드 의존성: `requirements-backend.txt`

## 3. 프로젝트 설치

GitHub에서 프로젝트를 가져옵니다.

```powershell
git clone https://github.com/weather-elfs/final_project.git
cd final_project
```

백엔드 작업 브랜치로 전환합니다.

```powershell
git switch feature/backend-api
```

Python 가상환경을 생성합니다.

```powershell
python -m venv .venv
```

가상환경에 패키지를 설치합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.txt
```

의존성 충돌 여부를 확인합니다.

```powershell
.\.venv\Scripts\python.exe -m pip check
```

## 4. 데이터베이스 환경변수 설정

백엔드는 PostgreSQL에 연결하기 위해 다음 환경변수를 사용합니다.

| 변수        | 설명              |
| ----------- | ----------------- |
| DB_HOST     | DB 서버 주소      |
| DB_PORT     | DB 접속 포트      |
| DB_NAME     | 데이터베이스 이름 |
| DB_USER     | DB 사용자         |
| DB_PASSWORD | DB 비밀번호       |

PowerShell 예시:

```powershell
$env:DB_HOST = "실제_DB_주소"
$env:DB_PORT = "실제_DB_포트"
$env:DB_NAME = "실제_DB_이름"
$env:DB_USER = "실제_DB_사용자"
$env:DB_PASSWORD = Read-Host "DB Password"
```

실제 DB 접속 정보는 담당자에게 별도로 전달받아야 합니다.

**주의사항**

- DB 비밀번호를 GitHub에 업로드하지 않습니다.
- 환경변수는 서버를 실행할 PowerShell 세션에서 설정합니다.
- PostgreSQL 서버에 대한 네트워크 접근 권한이 필요합니다.

## 5. 예측 모델 파일 확인

실제 예측 기능을 사용하려면 백엔드 코드에서 참조하는 CatBoost 모델 파일이 필요합니다.

모델 파일의 위치와 GitHub 포함 여부는 담당자에게 확인합니다.

## 6. 백엔드 서버 실행

프로젝트 최상위 폴더에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

기본 접속 주소:

- API 서버: http://127.0.0.1:8000
- Swagger 문서: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

서버 종료: `Ctrl + C`

## 7. 주요 API

**GET `/api/v1/stations/{station_id}/dashboard`**

주요 요청 파라미터:

| 파라미터            | 예시                      | 설명                   |
| ------------------- | ------------------------- | ---------------------- |
| station_id          | 112                       | 관측소 ID              |
| forecast_interval_h | 3                         | 예측 간격(1, 3, 6, 12) |
| mission_type        | MARITIME_TRANSPORT        | 임무 유형              |
| as_of               | 2022-01-01T01:00:00+09:00 | 기준 시각              |
| mock                | false                     | 모의 데이터 사용 여부  |

지원 관측소:

- 102: 백령도
- 112: 인천
- 201: 강화도

응답에는 현재 관측값, 해양 관측값, 예측 타임라인, 예측 요약, 임무 판정 및 진단 정보 등이 포함됩니다.

## 8. API 테스트

서버 실행 후 Swagger에 접속합니다.

1. `GET /api/v1/stations/{station_id}/dashboard` 선택
2. `Try it out` 클릭
3. 요청 파라미터 입력
4. `Execute` 클릭
5. HTTP 상태 코드와 JSON 응답 확인

실제 데이터 조회는 DB 연결 상태와 해당 기준 시각의 데이터 존재 여부에 따라 달라집니다.

## 9. 프런트엔드 연동

개발용 CORS 허용 주소:

- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `http://localhost:3000`
- `http://127.0.0.1:3000`

프런트엔드에서 API를 호출할 때는 접근 가능한 백엔드 서버 주소를 사용해야 합니다.

**주의:** `127.0.0.1`은 API를 호출하는 컴퓨터 자신을 의미합니다. 프런트엔드와 백엔드가 서로 다른 컴퓨터에서 실행된다면 별도의 접근 가능한 서버 주소와 네트워크 설정이 필요합니다.

## 10. 현재 구현 범위

- 시정거리 및 PM 예측: 구현
- 해상 수송·보급 임무 판정: MVP 구현
- API 오류 응답 처리: 구현
- CORS 설정: 구현
- AQI 산출: 팀 협의 후 추가 예정
- 추가 임무 판정 기준: 팀 협의 후 확장 예정

현재 해상 수송·보급 임무 판정의 시정거리 기준 1km는 임시 MVP 기준으로, 최종 운영 기준은 아닙니다.
