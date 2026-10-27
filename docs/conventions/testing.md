# 테스트 컨벤션

## 도구

- **pytest**를 사용한다.
- 테스트는 `tests/` 아래에 두고, 파일명은 `test_*.py` 형식을 따른다.
- 테스트 함수명은 `test_<검증대상>_<상황>` 형태로 의도를 드러낸다.

## 원칙

- 분석·전처리 함수 등 **로직이 있는 코드**에는 정상 동작과 실제로 발생 가능한
  경계값·오류 동작을 검증하는 테스트를 둔다. 테스트 개수보다 보호하는 동작을 명확히 한다.
- 외부 API·파일 I/O는 목(mock)이나 고정 샘플 데이터로 대체해 재현 가능하게 한다.
- 노트북(EDA)은 테스트 대상이 아니다. 재사용할 로직은 `src/weather/`로 승격한 뒤
  테스트를 붙인다.

현재 `tests/test_check_commit_msg.py`는 패키지 관리 도구 확정 전에도 실행할 수 있도록
표준 라이브러리 `unittest`와 호환되게 작성했다. 이후 `pytest`를 설치하면 같은 테스트를
그대로 수집해 실행할 수 있다.

## 실행

```bash
python tests/test_check_commit_msg.py   # 현재 의존성 설치 없이 실행 가능
pytest              # 전체 실행
pytest tests/test_check_commit_msg.py   # 현재 특정 파일 실행
pytest -k commit_message          # 현재 이름 필터
```

## 커밋/푸시 시 pytest 강제 여부 (결정 대기)

세 가지 선택지를 두고 팀이 결정한다.

| 방식 | 장점 | 단점 |
| --- | --- | --- |
| pre-commit 단계에서 실행 | 잘못된 코드가 커밋에 못 들어감 | 매 커밋이 느려짐 |
| pre-push 단계에서 실행 (권장) | 공유(push) 전에만 검사, 커밋은 빠름 | 로컬 커밋엔 미적용 |
| 강제 안 함(CI에서만) | 로컬 부담 없음 | 로컬에서 깨진 채 push 가능 |

- 결정 전까지 `.pre-commit-config.yaml`에 pytest 훅을 추가하지 않는다.
- 결정되면 이 표의 선택을 반영하고, 선택한 단계의 local 훅을 추가한다.
- GitHub Actions 도입은 현재 보류한다. 도입이 확정되면 별도 워크플로에서 pytest를
  실행하고 Branch Protection Rules의 필수 검사로 연결한다.
