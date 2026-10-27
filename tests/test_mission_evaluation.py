import sys
from pathlib import Path

# 프로젝트 최상위 경로 등록
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.main import get_mission_evaluation


def evaluate(visibility):
    summary = None if visibility is None else {"visibility_pred_km": visibility}
    return get_mission_evaluation(
        mission_type="MARITIME_TRANSPORT",
        forecast_summary=summary,
        is_mock=False,
    )


# TEST 1: 정상
normal = evaluate(5.0)
assert normal["evaluation_status"] == "EVALUATED"
assert normal["mission_grade"] == "NORMAL"
assert normal["passed"] is True
print("PASS: 5.0km → NORMAL")

# TEST 2: 제한
restricted = evaluate(0.8)
assert restricted["evaluation_status"] == "EVALUATED"
assert restricted["mission_grade"] == "RESTRICTED"
assert restricted["passed"] is False
print("PASS: 0.8km → RESTRICTED")

# TEST 3: 예측 데이터 없음
unknown = evaluate(None)
assert unknown["evaluation_status"] == "NOT_EVALUABLE"
assert unknown["mission_grade"] == "UNKNOWN"
assert unknown["passed"] is None
print("PASS: 데이터 없음 → UNKNOWN")

print("모든 임무 판정 테스트 통과!")
