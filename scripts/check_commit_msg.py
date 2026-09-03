"""커밋 메시지 형식 검사기 (pre-commit의 commit-msg 단계에서 실행).

규칙 (docs/conventions/git.md 기준):
  형식      : <type>(<선택 scope>): <설명>
  허용 타입 : feat, fix, docs, style, refactor, test, chore, build, ci,
              perf, revert
  설명      : 한글 1자 이상 포함, 이모지 금지

규칙을 바꾸면 docs/conventions/git.md, PATTERN, 관련 테스트를 함께 갱신한다.
"""

import re
import sys
from pathlib import Path

TYPES = "feat|fix|docs|style|refactor|test|chore|build|ci|perf|revert"

# 예: "feat: 가시도 수집 추가", "test(preprocess): 결측 처리 테스트"
PATTERN = re.compile(rf"^(?:{TYPES})(?:\([^)]+\))?: (?P<description>.+)$")

# 설명의 한글 포함 여부
HANGUL = re.compile(r"[가-힣]")

# 이모지(주요 구간) 탐지
EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]")


def main() -> int:
    if len(sys.argv) < 2:
        print("commit-msg 파일 경로가 전달되지 않았습니다.")
        return 1

    msg = Path(sys.argv[1]).read_text(encoding="utf-8")
    subject = next((line for line in msg.splitlines() if line.strip()), "")

    errors = []
    match = PATTERN.fullmatch(subject)
    if match is None:
        errors.append(
            "형식 오류: '<type>(<선택 scope>): <설명>' 이어야 합니다. "
            f"허용 타입: {TYPES.replace('|', ', ')}"
        )
    description = match.group("description") if match is not None else ""
    if not HANGUL.search(description):
        errors.append("설명에 한글이 1자 이상 포함되어야 합니다.")
    if EMOJI.search(subject):
        errors.append("이모지는 사용할 수 없습니다.")
    if len(subject) > 100:
        errors.append("제목은 100자 이내여야 합니다.")

    if errors:
        print("커밋 메시지 규칙 위반:")
        print(f"  입력: {subject!r}")
        for e in errors:
            print(f"  - {e}")
        print("예시: feat: 가시도 데이터 수집 모듈 추가")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
