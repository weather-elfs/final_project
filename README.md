# 국방 기상데이터 분석 시스템

가시도에 영향을 주는 안개·습도·미세먼지 등의 기상 데이터를 수집·전처리·분석하고,
결과를 웹 대시보드로 제공하기 위한 6인 팀 프로젝트다.

> 이 문서 묶음은 **최초 게시용 초기 설계·공통 설정 기준선**이다. 원격 `develop`에
> 게시된 이후의 실제 프로젝트 작업은 모두 `feature/*`에서 진행한다. 코드 구현 전에는
> 데이터 출처, 역할 분담, 환경·패키지 관리 도구를 먼저 확정해야 한다. 프로젝트 규칙의
> 원문은 [`AGENTS.md`](AGENTS.md)다.

## 현재 상태

| 구분 | 상태 |
| --- | --- |
| 저장소 구조 | 단일 Python 패키지 기반 모듈러 모놀리스로 확정 |
| 작업 브랜치 | 현재 문서 기준선 최초 게시까지 `develop`, 이후 프로젝트 작업은 `feature/*` |
| Python 버전·라이브러리 | Python 3.13 권고, 팀 확정·실행 검증 대기. 아래 호환성 검토 참고 |
| Python 포맷·임포트 | Black 기본 88자 + isort `profile = "black"` |
| 기타 파일 포맷 | VSCode Prettier |
| 테스트 | pytest 사용 확정, 커밋·push 강제 시점은 결정 대기 |
| 로컬 검사 | pre-commit 설정 완료, 각 개발 환경의 설치는 아직 필요 |
| 중앙 검사 | GitHub Actions 도입 보류 |
| 기상 도메인 기능 코드 | 아직 작성 전 |

확정되지 않은 항목과 결정 시점은 [`AGENTS.md`](AGENTS.md)의 TBD 표를 기준으로 한다.

## Python·라이브러리 호환성 검토

> 최신성 체크: **2026-09-20**. PM1.0 API 수집·전처리·모델링을 위한 검토 결과이며,
> Python 버전이나 새 의존성을 확정·설치한 것은 아니다. 환경·패키지 관리 도구와
> 데이터 출처도 결정 대기 상태다.

### Python 선택 권고

- **확인된 사실:** 공식 CPython은 특정 버전을 LTS로 지정하지 않고 버그 수정·보안
  지원 단계로 관리한다. 현재 저장소에는 구버전을 강제하는 프로젝트 의존성이 없다.
- **권고:** 신규 개발은 **Python 3.13의 최신 패치 버전**을 우선 검토한다. 아래 기본
  후보와 선택적 모델링 도구의 Windows 64비트 의존성 조합을 해석할 수 있었다.
- **예외:** 기존 코드를 반드시 재현해야 하고 해당 코드가 NumPy 1.x 등을 요구할
  때만 Python 3.12 등 별도 환경을 검토한다. 오래된 Python을 선택하는 것만으로
  모든 라이브러리 충돌이 해결되지는 않는다.

Python 지원 단계의 근거는 [공식 버전 지원표](https://devguide.python.org/versions/)다.
최종 결정 시 `AGENTS.md`, 관련 ADR, 설치 안내와 의존성 설정을 함께 갱신한다.

### 단계별 라이브러리 후보

| 단계 | 후보 또는 확정 도구 | 용도·도입 기준 |
| --- | --- | --- |
| API 수집 | `requests` | 공식 HTTP API 요청과 응답 처리 |
| 전처리·저장 | `numpy`, `pandas`, `pyarrow` | 시간 정렬·결측 처리·Parquet 저장 |
| 첫 예측 모델 | `scikit-learn`, `xgboost` | 학습·평가와 XGBoost 기준 모델 |
| 시각화 | `plotly` | 관측값·예측값 비교 그래프. 대시보드 프레임워크 선택과는 별개 |
| 테스트 | `pytest` | 사용은 기존 팀 결정. 설치 버전과 강제 실행 시점은 미정 |
| 선택적 확장 | `torch` 또는 `tensorflow`, `shap` | GRU 등 딥러닝과 예측 변수 영향 설명이 필요할 때 추가 |

수집·전처리·기준 모델부터 시작하고, 딥러닝 프레임워크는 필요가 확인되면 하나만
선택하는 것을 권고한다. 격자 기상자료용 `xarray`, `cfgrib`, GDAL 등은 실제 자료
형식이 정해지기 전까지 추가하지 않는다. 위 후보 목록은 설치 승인 목록이 아니다.

### 구버전 의존성 주의사항

| 사례 | 확인한 제약 | 대응 권고 |
| --- | --- | --- |
| `numpy==1.26.4` 또는 NumPy 1.x를 강제하는 기존 코드 | NumPy 1.26.4의 공식 Python 지원 범위는 3.9~3.12 | 구버전 고정 이유부터 확인하고, 재현이 필수일 때 별도 환경 검토 |
| `tensorflow==2.15.1`을 사용하는 기존 예제 | Windows 배포 파일은 Python 3.9~3.11용이며 3.12용은 없음 | 3.12로 낮추는 것만으로 해결되지 않음. 신규 코드는 현재 지원 조합으로 작성 |

근거: [NumPy 1.26.4 공식 릴리스 노트](https://numpy.org/doc/stable/release/1.26.4-notes.html),
[TensorFlow 2.15.1 공식 배포 파일](https://pypi.org/project/tensorflow/2.15.1/#files).
오래된 예제의 설치 명령이나 버전 고정은 그대로 복사하지 않고 현재 조합과 대조한다.

### 설치 전 의존성 해석 결과

이미 설치된 `uv 0.11.28`의 `uv pip compile`로 후보 목록을 표준입력에 전달했다.
대상 플랫폼은 `--python-platform x86_64-pc-windows-msvc`이며,
`--only-binary :all:`로 소스 빌드를 제외했다. `--no-cache`와
`--no-python-downloads`를 사용했고 패키지 설치나 잠금파일 생성은 하지 않았다.
검증 도구로 uv를 사용한 것이 팀의 패키지 관리 도구 확정을 의미하지는 않는다.

| Python | 점검 조합 | 결과 |
| --- | --- | --- |
| 3.13 | 기본 후보: `requests`, `numpy`, `pandas`, `pyarrow`, `scikit-learn`, `xgboost`, `plotly`, `pytest` | 의존성 해석 성공, 종료 코드 0 |
| 3.13 | 기본 후보 + `tensorflow` | 의존성 해석 성공, 종료 코드 0 |
| 3.13 | 기본 후보 + `torch`, `shap` | 의존성 해석 성공, 종료 코드 0 |
| 3.13 | `numpy==1.26.4` | 사용 가능한 설치 패키지 없음, 종료 코드 1 |
| 3.12 | `numpy==1.26.4` | 의존성 해석 성공, 종료 코드 0 |
| 3.12 | `tensorflow==2.15.1` | Python ABI가 맞는 설치 패키지 없음, 종료 코드 1 |

검증 당시 기본 후보의 선택 버전은 `requests 2.34.2`, `numpy 2.5.3`,
`pandas 3.0.6`, `pyarrow 25.0.1`, `scikit-learn 1.9.1`, `xgboost 3.4.1`,
`plotly 7.1.0`, `pytest 9.1.1`이었다. 확장 조합에서는 `tensorflow 2.21.0` 또는
`torch 2.14.0`·`shap 0.52.0`이 선택되었다. 이는 당시의 관찰 결과이며, 승인된
버전 고정 목록이나 전체 간접 의존성을 담은 잠금파일이 아니다.

**한계:** 의존성 해석 성공은 실제 실행·정확성·GPU 호환성을 보장하지 않는다.
Python 3.13 환경의 모듈 불러오기, 전처리, 모델 학습과 다른 운영체제 검증은 아직
실행하지 않았다. 따라서 “라이브러리 충돌이 가장 적다”는 확정할 수 없다.

### 충돌 예방 기준

1. 필요한 단계의 패키지만 추가하고, 새 의존성은 팀 규칙에 따라 승인받는다.
2. 패키지를 추가·갱신할 때 기존 의존성과 함께 해석하고 각 대상 환경에서 확인한다.
3. 작은 데이터로 모듈 불러오기·전처리·모델 학습을 검증한 뒤 버전을 고정한다.
4. 팀의 Python 버전을 통일하고 프로젝트별 가상환경과 검증된 잠금파일을 공유한다.
   기존 코드 재현용 환경이나 GPU 환경이 필요하면 기본 환경과의 분리를 검토한다.

## 처음 참여하는 팀원

### 1. 저장소 받기

[Git](https://git-scm.com/downloads)과
[Visual Studio Code](https://code.visualstudio.com/)를 설치한 뒤, 프로젝트를 둘 빈
폴더의 상위 위치에서 실행한다.

```bash
git clone https://github.com/weather-elfs/final_project.git
cd final_project
git config --local user.email "본인 이메일"
git config --local user.name "본인 이름 또는 닉네임"
git branch --all
```

원격 `develop`이 목록에 있으면 다음 명령으로 전환한다.

```bash
git switch develop
git pull --ff-only origin develop
```

`origin/develop`이 보이지 않으면 임의로 같은 이름의 브랜치를 만들거나 push하지 말고
저장소 관리자에게 초기 생성 여부를 확인한다. 최초 생성 절차는
[`docs/conventions/git.md`](docs/conventions/git.md)에 있다.

### 2. VSCode 열기

VSCode에서 `final_project` 폴더를 연다. 확장 추천 알림이 나타나면
`.vscode/extensions.json`의 Python, Jupyter, Black, isort, Prettier 확장을 설치한다.
터미널은 PowerShell과 Git Bash 중 익숙한 것을 사용해도 된다.

### 3. 문서 읽기

처음에는 아래 순서대로 읽는다.

1. [`AGENTS.md`](AGENTS.md) — 프로젝트 현황, 공통 규칙, 필독 문서 진입점
2. [`docs/agents/workflow.md`](docs/agents/workflow.md) — 작업 시작부터 완료 보고까지
3. [`docs/agents/boundaries.md`](docs/agents/boundaries.md) — 바로 해도 되는 일과 승인받을 일
4. [`docs/adr/0001-repository-architecture.md`](docs/adr/0001-repository-architecture.md) — 현재 구조를 선택한 이유
5. 작업에 맞는 [`docs/conventions/`](docs/conventions/) 문서
6. AI 도구를 쓴다면 [`docs/agents/tool-compatibility.md`](docs/agents/tool-compatibility.md)

### 4. Git 상태 확인하기

먼저 패키지 설치 없이 현재 브랜치와 변경 상태를 확인한다.

```bash
git branch --show-current
git status
```

Python이 이미 설치된 환경에서만 버전을 확인하고 커밋 메시지 검사 테스트를 실행한다.
Python 명령을 찾을 수 없다면 임의로 설치하지 말고 환경·패키지 관리 도구 결정을 기다린다.

```bash
python --version
python tests/test_check_commit_msg.py
```

Black, isort, pre-commit, pytest 설치 명령은 Python 버전과 환경·패키지 관리 도구가
확정된 뒤 이 문서에 추가한다.

### 5. 프로젝트 작업 브랜치 만들기

위 문서와 Git 상태를 확인한 뒤, 초기 문서 기준선이 원격 `develop`에 게시되어 있다면
최신 `develop`에서 작업에 맞는 브랜치를 만든다.

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feature/data-source-research
```

브랜치 이름은 예시다. 실제 작업 범위가 데이터 스키마라면 `feature/data-schema`,
대시보드 요구사항이라면 `feature/dashboard-requirements`처럼 목적이 드러나게 정한다.

## 작업 흐름 요약

```text
현재 문서 기준선 최초 게시까지: develop에서 작업
기준선 게시 이후 프로젝트 작업: develop → feature/작업명 → PR → develop
배포: develop → PR → main
긴급 수정: main → hotfix/작업명 → PR → main (+ develop)
```

- `main`과 `develop`에 직접 push하거나 로컬에서 직접 병합하지 않는다. 승인된 최초
  `develop` 생성 1회만 예외이며, 절차는 Git 컨벤션을 따른다.
- 커밋은 `<type>(<선택 scope>): <한글 포함 설명>` 형식을 사용한다.
- AI 에이전트는 커밋과 push 전에 사용자 승인을 받는다.
- GitHub Actions는 보류 중이며 워크플로 파일을 미리 만들지 않는다.

전체 규칙은 [`docs/conventions/git.md`](docs/conventions/git.md)를 따른다.

## 목표 아키텍처

기능 구현을 시작하면 아래 모듈 경계를 사용한다. 현재 기상 도메인의 기능 코드와
`src/weather/` 구조는 아직 없으며, 커밋 검사기와 그 테스트만 구현되어 있다.

```text
src/weather/
├── ingest/        데이터 수집
├── preprocess/    정제·결측 처리
├── features/      파생 변수
├── analysis/      분석 로직
├── viz/           시각화 유틸리티
└── dashboard/     프레임워크 확정 후 추가
notebooks/         탐색적 분석
scripts/           실행 진입점
tests/             자동 테스트
```

대시보드에 독립 배포·의존성·릴리스 주기가 실제로 필요해질 때만 다중 패키지 모노레포를
검토한다. 자세한 조건은
[`ADR-0001`](docs/adr/0001-repository-architecture.md)에 기록되어 있다.

## 문서 지도

| 문서 | 내용 | 상태 |
| --- | --- | --- |
| [`AGENTS.md`](AGENTS.md) | 모든 AI 에이전트의 전역 규칙과 현재 결정 | 사용 중 |
| [`docs/agents/workflow.md`](docs/agents/workflow.md) | 표준 작업 절차 | 사용 중 |
| [`docs/agents/boundaries.md`](docs/agents/boundaries.md) | Always / Ask first / Never | 사용 중 |
| [`docs/agents/tool-compatibility.md`](docs/agents/tool-compatibility.md) | 도구별 규칙 로딩 검증 | 일부 도구 검증 대기 |
| [`docs/conventions/general.md`](docs/conventions/general.md) | Python 코드 스타일과 자체 점검 | 사용 중 |
| [`docs/conventions/git.md`](docs/conventions/git.md) | 브랜치, 커밋, PR | 사용 중 |
| [`docs/conventions/testing.md`](docs/conventions/testing.md) | 테스트 원칙 | 커밋·push 강제 시점 결정 대기 |
| [`docs/conventions/data.md`](docs/conventions/data.md) | 데이터 계층, 보안, 재현성 | 출처별 세부사항 대기 |
| `docs/conventions/dashboard.md` | 대시보드 규칙 | 프레임워크 확정 후 작성 |
| `docs/agents/division-of-labor.md` | 6인 역할 분담 | 역할 확정 후 작성 |
| `docs/research/` | 데이터 출처 조사 근거 | 출처 조사 시 작성 |

## 커밋 히스토리로 설계 공부하기

이 저장소는 처음 보는 팀원도 결정 과정을 따라갈 수 있도록 설계 변경을 작은 커밋으로
나눴다.

```bash
git log --reverse --oneline develop
git show 638cb78 --stat
git show 638cb78
```

권장 학습 순서는 다음과 같다.

| 단계 | 커밋 | 확인할 내용 |
| --- | --- | --- |
| 1 | `9ab189a`, `fa99062` | 저장소 시작과 Git 기초 안내 |
| 2 | `638cb78` | 모듈러 모놀리스 선택 이유와 분리 조건 |
| 3 | `fb7875b`, `d327916` | Python·테스트·데이터 규칙 |
| 4 | `3b4ce9e`, `54e7cea`, `ee13fa4`, `0e9077c` | 편집기, 검사기, pre-commit, Git 협업 설정 |
| 5 | `9826d4a` | `AGENTS.md` 중심의 AI 에이전트 규칙 |
| 6 | `dd2d182`, `3cac467`, `34c759c`, `540cf64` | 외부 도구 검증 뒤 반영한 보완 과정 |
| 7 | `ca7a9e1` | 최종 검토에서 정리한 환경·테스트·브랜치 부트스트랩 전제 |
| 8 | `680c236` | 최초 게시 후 실제 프로젝트 작업을 `feature/*`로 전환한 결정 |

각 커밋에서 `git show`로 “무엇이 바뀌었는지”를 보고, 연결된 문서에서 “왜 그렇게
정했는지”를 확인하면 된다.

## 다음 필수 결정

기능 개발 전에 아래 세 항목을 확정하고 `AGENTS.md`와 관련 문서를 함께 갱신한다.

1. 사용할 기상·가시도 데이터의 공식 출처와 이용 조건
2. 6인 역할 분담과 첫 작업 배정
3. Python 버전과 환경·패키지 관리 도구

위 결정을 조사·설계하거나 실제 데이터·코드를 다루는 작업도 초기 문서 기준선 게시
이후에는 각각 `feature/*` 브랜치에서 진행한다.

대시보드 프레임워크, Python 린터, pytest 강제 시점은 기능 착수 후 결정할 수 있다.
GitHub Actions는 팀 합의 전까지 보류한다.

## 관련 링크

- [GitHub 저장소](https://github.com/weather-elfs/final_project)
- [FigJam 기획 보드](https://www.figma.com/board/bjllnWtHwHH2VdgdkcXl5T/%EC%B5%9C%EC%A2%85?node-id=1-754&t=tyPIqYALkTtN42ga-0)
