# 공통 코딩 컨벤션

PEP8을 기반으로 한다. 자동화 도구(isort, 포맷터)로 강제할 수 있는 항목은
가능한 한 자동화하여 사람이 신경 쓸 여지를 줄인다.

## 코드 스타일 (PEP8)

- 들여쓰기: 공백 4칸 사용 (탭 금지)
- 라인 길이: **Black 기본값 88자** (변경하지 않음), 독스트링·주석 72자 권장
- 공백·따옴표 등 세부 포맷은 **Black**이 자동 정리하므로 사람이 신경 쓰지 않는다.

> **포맷터는 Black, 임포트 정렬은 isort(`profile = "black"`)로 확정.**
> VSCode 범용(Markdown·JSON·YAML 등) 포매터는 Prettier를 쓴다. 린터는 아직
> 확정되지 않았으며 새 의존성 승인 후 이 문서와 `.pre-commit-config.yaml`에 반영한다.

## 네이밍 컨벤션

| 대상 | 규칙 | 예시 |
| --- | --- | --- |
| 변수·함수 | `snake_case` | `user_name`, `calculate_total` |
| 클래스 | `PascalCase` | `UserProfile`, `WeatherLoader` |
| 상수 | `UPPER_SNAKE_CASE` | `MAX_RETRIES`, `API_BASE_URL` |
| 비공개 속성 | 앞에 `_` 하나 | `_internal_cache` |
| 파일·폴더 | `snake_case` | `data_preprocessor.py`, `visibility_model.py` |

## 임포트 순서 (isort로 자동 정렬)

파일 최상단에 작성하고, 아래 3그룹으로 나눠 그룹 사이를 한 줄 띄운다.

```python
# 1. 표준 라이브러리
import os
from pathlib import Path

# 2. 서드파티 라이브러리
import numpy as np
import pandas as pd

# 3. 로컬(프로젝트) 모듈
from weather.preprocess import clean_visibility
```

- isort 설정은 `pyproject.toml`의 `[tool.isort]`에 두며, Black과의 충돌을 막기 위해
  `profile = "black"`을 사용한다.
- VSCode에서는 저장 시 자동 정렬(`source.organizeImports`)되도록 설정되어 있다
  (`.vscode/settings.json`).

## 폴더 구조 (권장)

```
src/weather/
├── ingest/        데이터 수집
├── preprocess/    정제·결측 처리
├── features/      파생 변수
├── analysis/      분석 로직
└── viz/           시각화 유틸
notebooks/         탐색(EDA) 노트북
tests/             pytest
scripts/           파이프라인 실행 진입점
```

## 주석

- 코드 자체가 설명하도록 작성한다. 주석은 **WHY**(이유)를 설명할 때만 쓴다.
- 당연한 내용을 다시 쓰지 않는다: `# 데이터를 불러온다` (X)
- 숨은 제약, 우회책, 외부 의존성의 이유는 반드시 주석으로 남긴다.
- 공개 함수에는 독스트링을 쓴다. 내부 헬퍼에는 불필요하다.

## 데이터·비밀정보 (요약)

- API 키·비밀번호는 코드에 하드코딩하지 않는다. `.env` + 환경변수로 관리한다.
- 대용량 원본 데이터는 저장소에 커밋하지 않는다(상세는
  `docs/conventions/data.md`).

## 에이전트 자체 점검 (커밋 전 필수)

> **에이전트가 코드를 완성하기 전에** 아래를 스스로 점검한다. 스타일
> (공백·따옴표·정렬)은 Black·isort가 처리하므로 제외하고, **버그 · 가독성 · 안전**에
> 집중한다. 이 점검은 자동 린터·테스트를 대체하지 않는다. 완료 보고 시 점검 결과를 밝힌다.

**버그·정확성**

- 미사용 import·변수·함수가 없다.
- 정의되지 않은 이름·오타가 없다.
- `except:`(bare)를 쓰지 않고 구체적인 예외를 잡는다. 예외를 조용히 삼키지 않는다.
- 매직 넘버·매직 문자열은 이름 있는 상수로 뺀다.
- 반환값·타입이 일관되며, 함수 시그니처에는 가능한 한 타입 힌트를 붙인다.

**가독성**

- 변수·함수명이 역할을 드러낸다(`snake_case`). `a`, `tmp`, `data2` 같은 이름 지양.
- 함수는 한 가지 일만 한다. 너무 길거나 중첩이 깊으면 분리한다.
- 공개 함수에는 한 줄 docstring을 둔다.
- 죽은 코드·주석 처리된 코드를 남기지 않는다(YAGNI).

**안전**

- 키·비밀번호·토큰·절대경로를 하드코딩하지 않는다(환경변수·설정으로).
- 디버깅용 `print`를 남기지 않는다. 로그가 필요하면 `logging`을 쓴다.
- 파일 입출력은 인코딩을 명시하고(`encoding="utf-8"`), 경로는 `pathlib`를 쓴다.
- 외부·사용자 입력은 신뢰하지 않고 형식·범위를 검증한다.

> 이 목록은 강제 도구가 아니라 **생성 시점의 자기 검증**이다. 자동 검사로 확인할 수
> 있는 항목은 린터 도입 후 자동화하고, 에이전트는 자동화되지 않은 판단을 보완한다.
