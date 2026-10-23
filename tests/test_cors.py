import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

response = client.options(
    "/api/v1/stations/112/dashboard",
    headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    },
)

assert response.status_code == 200, response.text

assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

assert "GET" in response.headers.get("access-control-allow-methods", "")

print("PASS: CORS 사전 요청 HTTP 200")
print("PASS: 프런트엔드 Origin 허용")
print("PASS: GET 메서드 허용")
print("CORS 자동화 테스트 통과!")
