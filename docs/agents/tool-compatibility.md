# 도구별 지침 로딩 검증 현황

이 문서는 지원 도구를 선언하기 위한 목록이 아니다. 각 도구가 프로젝트 규칙을
실제로 불러오는지 팀원 누구나 같은 방법으로 재현하기 위한 최소 운영 기록이다.

검증 단위는 모델이나 버전이 아니라 **도구 표면(Desktop / CLI)**이다. 모델과 모델
버전은 토큰 사용량과 작업 성격에 따라 바뀌므로 기록하지 않는다. 도구 버전도 고정
열로 관리하지 않고 검증일로 최신성을 판단하며, 장애를 재현할 때만 당시 버전을 실패
조사 자료에 남긴다. 공식 문서의 지원 여부와 팀 환경의 실제 동작은 구분하며, 결과는
실제 도구에서 확인한 뒤에만 갱신한다.

## 결과 기준

- `PASS`: 정해진 절차로 `AGENTS.md`의 경로와 프로젝트 고유 규칙을 모두 확인했다.
- `PARTIAL`: 규칙을 참조한 정황은 있으나 정해진 절차의 증거가 완전하지 않다.
- `FAIL`: 정해진 로딩 방식으로 `AGENTS.md`를 불러오지 못했다.
- `NOT_TESTED`: 팀 환경에서 아직 실행하지 않았다.

## 검증 현황

| 도구 | 로딩 방식 | 확인 명령·절차 | 검증일 | 결과 |
| --- | --- | --- | --- | --- |
| Google Antigravity | 활성 디렉터리의 `AGENTS.md` 자동 탐색 (별도 어댑터 불필요) | 저장소를 연 새 세션에서 아래 공통 확인 문구를 입력하고 응답의 파일 경로와 브랜치 규칙을 대조 | 2026-09-03 | `PASS` — 루트 `AGENTS.md` 직접 로딩 및 규칙 적용 확인 |
| Google Antigravity CLI | 활성 디렉터리의 `AGENTS.md` 자동 탐색 | 저장소 루트에서 `agy`를 시작한 뒤 아래 공통 확인 문구를 입력 | — | `NOT_TESTED` |
| OpenAI Codex Desktop | 저장소 계층의 `AGENTS.md`를 자동 탐색·병합 | 저장소를 연 새 작업에서 아래 공통 확인 문구를 입력 | 2026-09-03 | `PASS` — 현재 작업에서 루트 `AGENTS.md` 적용 확인 |
| OpenAI Codex CLI | 저장소 계층의 `AGENTS.md`를 자동 탐색·병합 | 저장소 루트에서 `codex --ask-for-approval never "현재 적용 중인 프로젝트 지침 파일 경로와 초기 설계 단계의 작업 브랜치를 답해줘. 추측하지 마."` 실행 | — | `NOT_TESTED` |
| Anthropic Claude Code Desktop | Code 탭이 프로젝트 `CLAUDE.md`를 읽고 `@AGENTS.md` import를 적용 | 저장소를 선택한 새 세션에서 `/memory`로 로딩 파일을 확인한 뒤 아래 공통 확인 문구를 입력 | — | `NOT_TESTED` |
| Anthropic Claude Code CLI | 프로젝트 `CLAUDE.md`를 읽고 `@AGENTS.md` import를 적용 | 저장소 루트에서 `claude`를 시작하고 `/memory`로 로딩 파일을 확인한 뒤 아래 공통 확인 문구를 입력 | 2026-09-03 | `PARTIAL` — 검토에서 내용 참조는 확인했으나 표준 절차의 출력은 기록되지 않음 |

## 공통 확인 문구

상충 규칙이나 의도적인 오류를 만들지 않는다. 기존 프로젝트 규칙과 로딩 출처를
함께 확인해 일반적인 답변을 우연히 맞히는 경우를 줄인다.

```text
현재 적용 중인 프로젝트 지침 파일의 경로와 초기 설계 단계에서 사용할 브랜치를
답해줘. 추측하지 말고 실제로 로딩한 지침만 근거로 답해줘.
```

예상 결과에는 루트 `AGENTS.md`와 초기 설계·공통 설정 단계의 `develop` 사용이 모두
포함되어야 한다. 둘 중 하나라도 확인되지 않으면 `PASS`로 기록하지 않는다.

## 갱신 원칙

- 같은 도구 안에서 모델만 변경한 경우에는 다시 검증하지 않는다.
- 도구의 로딩 방식이 바뀌었거나 규칙 누락이 의심될 때 다시 검증한다.
- 재검증하면 검증일과 결과만 최신 값으로 교체한다.
- `FAIL` 또는 `PARTIAL`이면 원인을 확인한 뒤 어댑터 추가나 수동 로딩 절차를 결정한다.
- 상세 대화와 긴 로그는 이 표에 복사하지 않고 실패 조사 자료에만 남긴다.

## 공식 확인 경로

- OpenAI: [Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- Google: [Antigravity Rules](https://antigravity.google/docs/rules-workflows/), [Antigravity CLI migration](https://www.antigravity.google/docs/cli/gcli-migration/)
- Anthropic: [Claude Code project memory](https://code.claude.com/docs/en/memory), [Claude Code Desktop](https://code.claude.com/docs/en/desktop)
