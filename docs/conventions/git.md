# Git 컨벤션

## 브랜치 전략 (Git Flow, release 미사용)

```
feature/*  →  develop  →  main
hotfix/*   →  main (+ develop)
```

| 브랜치 | 용도 |
| --- | --- |
| `main` | 배포 브랜치. `develop`·`hotfix/*`에서만 머지. 직접 push 금지. |
| `develop` | 다음 버전 통합 브랜치. 초기 설계·공통 설정 단계의 작업 브랜치. 직접 push 금지. |
| `feature/<기능>` | 기능 개발 (예: `feature/visibility-ingest`). `develop`에서 분기·병합. |
| `hotfix/<내용>` | 운영 긴급 수정. `main`에서 분기, `main`+`develop`에 병합. |

> `release/*` 브랜치는 사용하지 않는다. `develop`이 준비되면 바로 `main`으로 배포한다.

- 초기 설계·공통 설정이 끝나고 팀원 역할 분담과 첫 작업 배정이 시작되기 전까지는
  `develop`에서 작업한다.
- 역할 분담 이후의 새 기능은 최신 `develop`에서 `feature/*`를 분기하고, 완료 후
  `develop`으로 PR을 올린다.
- `main`·`develop`에는 로컬에서 직접 머지하지 않는다. **PR로만** 병합한다.
- 저장소 설정에서 `main`·`develop`에 Branch Protection Rules를 설정하고 리뷰 승인을
  요구한다. GitHub Actions 도입 후에는 CI 성공도 필수 검사로 연결한다.

### 최초 `develop` 부트스트랩

원격 `develop`이 아직 없으면 저장소 관리자가 GitHub에서 `main` 기준 브랜치를 만든
직후 보호 규칙을 설정한다. GitHub에서 만들 수 없는 경우에만 사용자 승인을 받아 최초
1회 push하고 즉시 보호한다. 이 절차 이후의 `develop` 직접 push는 금지한다.

## 커밋 메시지 (Conventional Commits)

형식:

```
<type>(<선택 scope>): <한글 포함 설명>
```

허용 타입:

- **`feat`** — 새로운 기능 추가
- **`fix`** — 버그 수정
- **`docs`** — 문서 변경 (README, docs/ 등)
- **`style`** — 코드 의미에 영향 없는 변경 (포맷, 공백, 세미콜론 등)
- **`refactor`** — 기능 변화 없는 코드 구조 개선
- **`test`** — 테스트 추가·수정
- **`chore`** — 기타 잡무 (설정, 패키지, 파일 정리 등)
- **`build`** — 빌드 시스템·의존성 변경
- **`ci`** — CI 설정·스크립트 변경
- **`perf`** — 성능 개선
- **`revert`** — 이전 커밋 되돌리기

규칙:

- 이모지 금지
- 설명에 한글 1자 이상 포함 (영·한 혼용 허용)
- scope는 선택이며 변경 영역을 간결하게 작성
- 제목 72자 이내(권장), 현재형 사용. 도구는 100자 초과 시에만 강제 거부한다.

예시:

```
feat: 가시도 데이터 수집 모듈 추가
feat(data): 가시도 데이터 스키마 추가
fix: 결측 습도값 처리 오류 수정
docs: AGENTS.md 데이터 출처 항목 갱신
test: 전처리 함수 단위 테스트 추가
```

> 팀이 `[Feat] 설명` 형태(대괄호 태그)를 선호하면
> `docs/conventions/git.md`, `scripts/check_commit_msg.py`, 관련 테스트를 함께
> 변경해야 한다. 현재 기본값은 Conventional Commits다.

## 로컬 커밋 검사 (pre-commit)

이 프로젝트는 **pre-commit** 프레임워크로 로컬 커밋을 검사한다. 훅을 설치한 환경에서는
규칙에 맞지 않는 커밋이 거부된다. 로컬 훅만으로 저장소 전체 규칙을 강제할 수는 없다.

- `commit-msg` 단계: 위 커밋 메시지 형식을 검사한다.
- `pre-commit` 단계: Black 포맷 · isort 정렬 및 기본 파일 점검(공백·대용량 파일·머지 충돌 등).
- `--no-verify`로 훅을 우회하는 것은 금지한다.

설치:

```bash
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

## PR 정책

- PR 제목 형식: 커밋과 동일한 Conventional Commits 형식
  (예: `feat(data): 가시도 수집 추가`)
- 병합 방향 제한: `main` ← `develop`·`hotfix/*`, `develop` ← `feature/*`
- 리뷰어를 최소 1명 지정하고 승인 후 머지한다.
- PR은 기능·화면 단위로 작게 쪼갠다(충돌 감소).
- `.github/PULL_REQUEST_TEMPLATE.md`를 사용한다.

## pytest 검사 시점 (검토 중)

테스트를 커밋/푸시 시점에 강제할지는 팀에서 결정한다. `docs/conventions/testing.md`
참조. 결정 전까지 훅에서 pytest는 비활성(주석) 상태로 둔다.

## GitHub Actions (보류)

<!--
GitHub Actions는 팀 결정 전까지 생성하지 않는다.
도입 시 .github/workflows/ci.yml에서 pre-commit과 pytest를 실행하고,
Branch Protection Rules의 필수 검사로 연결한다.
-->
