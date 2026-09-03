"""커밋 메시지 검사기의 사용자 관찰 동작을 검증한다."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKER = Path(__file__).parents[1] / "scripts" / "check_commit_msg.py"


def run_checker(subject: str) -> subprocess.CompletedProcess[str]:
    """임시 커밋 메시지 파일을 실제 검사기에 전달한다."""
    with tempfile.TemporaryDirectory() as temp_dir:
        message_path = Path(temp_dir) / "COMMIT_EDITMSG"
        message_path.write_text(f"{subject}\n", encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(CHECKER), str(message_path)],
            capture_output=True,
            check=False,
            text=True,
        )


class CheckCommitMessageTest(unittest.TestCase):
    """Conventional Commits 제목 규칙을 검증한다."""

    def test_accepts_scope_with_hangul_description(self) -> None:
        """선택 scope와 한글 설명이 있는 정상 메시지를 허용한다."""
        result = run_checker("feat(data): 가시도 스키마 추가")

        self.assertEqual(result.returncode, 0, result.stdout)

    def test_rejects_message_when_only_scope_contains_hangul(self) -> None:
        """한글이 scope에만 있으면 설명 규칙 위반으로 거부한다."""
        result = run_checker("feat(데이터): english only")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("설명에 한글이 1자 이상 포함되어야 합니다.", result.stdout)

    def test_rejects_description_without_hangul(self) -> None:
        """한글이 없는 설명은 규칙 위반으로 거부한다."""
        result = run_checker("fix: handle missing values")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("설명에 한글이 1자 이상 포함되어야 합니다.", result.stdout)

    def test_rejects_non_conventional_format(self) -> None:
        """Conventional Commits가 아닌 제목을 거부한다."""
        result = run_checker("[기능] 가시도 스키마 추가")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("형식 오류", result.stdout)


if __name__ == "__main__":
    unittest.main()
