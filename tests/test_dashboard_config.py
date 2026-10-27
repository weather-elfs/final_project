from unittest.mock import patch

from backend.main import STATIONS, app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_config_without_bounds():
    with patch(
        "backend.main.get_connection", side_effect=AssertionError("DB must not be used")
    ) as connect:
        response = client.get("/api/v1/dashboard/config")

    assert response.status_code == 200, response.text
    connect.assert_not_called()

    result = response.json()
    assert result["code"] == "SUCCESS"

    data = result["data"]
    assert len(data["stations"]) == len(STATIONS)
    assert all(station["current_status"] == "UNKNOWN" for station in data["stations"])
    assert data["forecast_interval_options_h"] == [1, 3, 6, 12]
    assert data["forecast_slots"] == 4
    assert isinstance(data["mission_types"], list)

    print("PASS: config without bounds")


def test_config_with_bounds():
    station = STATIONS[0]

    params = {
        "south": station["latitude"] - 0.01,
        "north": station["latitude"] + 0.01,
        "west": station["longitude"] - 0.01,
        "east": station["longitude"] + 0.01,
    }

    with patch(
        "backend.main.get_connection", side_effect=AssertionError("DB must not be used")
    ) as connect:
        response = client.get(
            "/api/v1/dashboard/config",
            params=params,
        )

    assert response.status_code == 200, response.text
    connect.assert_not_called()

    data = response.json()["data"]
    assert len(data["stations"]) == 1

    print("PASS: config with bounds")


def test_config_partial_bounds():
    response = client.get(
        "/api/v1/dashboard/config",
        params={"south": 37},
    )

    assert response.status_code == 422
    print("PASS: partial bounds")


def test_config_invalid_bounds():
    response = client.get(
        "/api/v1/dashboard/config",
        params={
            "south": 40,
            "north": 30,
            "west": 125,
            "east": 130,
        },
    )

    assert response.status_code == 422
    print("PASS: invalid bounds")


if __name__ == "__main__":
    test_config_without_bounds()
    test_config_with_bounds()
    test_config_partial_bounds()
    test_config_invalid_bounds()

    print("ALL CONFIG TESTS PASSED")
