"""외부 API를 고정하고 DB 연결 없이 최신 수집·예측 순서를 검증한다."""

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend import live_observations as live
from backend import main


class LiveCollectionTests(unittest.TestCase):
    def setUp(self):
        stub = patch.object(
            live,
            "collect_forecasts",
            return_value={
                "inputs": {},
                "records": {"KMA_FORECAST": [1] * 4, "AIRKOREA_FORECAST": [1] * 3},
            },
        )
        stub.start()
        self.addCleanup(stub.stop)
        self.now = datetime.now(live.KST)
        self.base = self.now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        self.asos = [{"tm": self.base, "stn_id": "112", "temp": 21.0}]
        self.air = [{"tm": self.base, "station_code": "823632", "pm25": 10.0}]
        self.marine = [
            {
                "tm": self.base,
                "stn_name": "인천",
                **dict.fromkeys(live.MARINE_FIELDS.values(), 1.0),
            }
        ]

    def test_stale_future_negative_and_nonfinite_are_rejected(self):
        for row in (
            {"tm": self.base - timedelta(days=1)},
            {"tm": self.now.replace(tzinfo=None) + timedelta(minutes=1)},
            {"tm": self.base, "pm25": -1},
            {"tm": self.base, "pm25": float("inf")},
            {"tm": self.base, "humidity": 101},
            {"tm": self.base, "wind_dir": 361},
        ):
            with self.subTest(row=row), self.assertRaises(live.CollectionError):
                live.validate_records([row], self.now, "TEST")
        with self.assertRaises(live.CollectionError):
            live.validate_records([], self.now, "TEST")
        live.validate_records(
            [{"tm": self.base, "pm25": None, "pm10": 0}], self.now, "TEST"
        )

    def test_air_future_rows_are_excluded_without_replacing_real_observations(self):
        future = self.now.replace(tzinfo=None) + timedelta(hours=1)
        records = [*self.air, {"tm": future, "pm25": None, "pm10": None, "so2": 0.003}]
        with patch.dict("os.environ", {"AIRKOREA_API_KEY": "test-only"}), patch.object(
            live.airkorea_collector, "fetch", return_value=[]
        ), patch.object(live, "prepare_air_records", return_value=(records, 0)):
            self.assertEqual(live.collect_airkorea("112", self.now), self.air)
            records[-1]["pm25"] = 1
            self.assertEqual(live.collect_airkorea("112", self.now), self.air)

    def test_all_sources_return_in_memory_without_database(self):
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live, "collect_airkorea", return_value=self.air
        ), patch.object(live, "collect_marine", return_value=self.marine), patch.object(
            main, "get_connection", side_effect=AssertionError("DB must not be used")
        ) as connect:
            result = live.refresh_observations("112")
        connect.assert_not_called()
        self.assertEqual(result["observations"]["ASOS"], self.asos)
        self.assertEqual(result["storage"], "memory")
        self.assertEqual(result["base_time"], self.base)
        self.assertEqual(
            set(result["collected_rows"]),
            {
                "ASOS",
                "AIRKOREA",
                "TIDE_OBSERVATORY",
                "KMA_FORECAST",
                "AIRKOREA_FORECAST",
            },
        )
        self.assertEqual(
            set(result["model_input_observed_at"].values()),
            {self.base.replace(tzinfo=live.KST).isoformat()},
        )

    def test_source_failure_does_not_touch_database_or_expose_secret(self):
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live, "collect_airkorea", side_effect=RuntimeError("secret-request-url")
        ), patch.object(live, "collect_marine", return_value=self.marine), patch.object(
            main, "get_connection"
        ) as connect:
            with self.assertRaises(live.CollectionError) as raised:
                live.refresh_observations("112")
        connect.assert_not_called()
        self.assertEqual(raised.exception.source, "AIRKOREA")
        self.assertNotIn("secret", str(raised.exception))

    def test_no_aligned_source_does_not_ingest(self):
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live,
            "collect_airkorea",
            return_value=[{"tm": self.base + timedelta(seconds=1)}],
        ), patch.object(live, "collect_marine", return_value=self.marine), patch.object(
            main, "get_connection"
        ) as connect:
            with self.assertRaises(live.CollectionError):
                live.refresh_observations("112")
        connect.assert_not_called()

    def test_forecast_failure_is_reported_without_database(self):
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live, "collect_airkorea", return_value=self.air
        ), patch.object(live, "collect_marine", return_value=self.marine), patch.object(
            main, "get_connection"
        ), patch.object(
            live,
            "collect_forecasts",
            side_effect=live.ForecastError("FORECAST", "TARGET_MISSING_OR_STALE"),
        ):
            with self.assertRaises(live.CollectionError) as raised:
                live.refresh_observations("112")
        self.assertEqual(raised.exception.reason, "TARGET_MISSING_OR_STALE")

    def test_marine_mapping_and_missing_values(self):
        payload = {
            "header": {"resultCode": "00"},
            "body": {
                "totalCount": 1,
                "items": {
                    "item": [
                        {
                            "obsvtrNm": "옹진소청초",
                            "obsrvnDt": self.base.isoformat(),
                            "wtem": 19.1,
                            "slntQty": None,
                        }
                    ]
                },
            },
        }
        response = MagicMock()
        response.__enter__.return_value = response
        with patch.dict("os.environ", {"DATA_API_KEY": "test-only"}), patch.object(
            live.urllib.request,
            "urlopen",
            side_effect=[TimeoutError(), response, response],
        ) as fetch, patch.object(live.json, "load", return_value=payload):
            rows = live.collect_marine("102", self.now)
        self.assertIn("obsCode=IE_0062", fetch.call_args.args[0])
        self.assertEqual(rows[0]["stn_name"], "소청초")
        self.assertEqual(rows[0]["water_temp"], 19.1)
        self.assertIsNone(rows[0]["salinity"])

    def test_history_exact_hour_join_units_and_missing_slots(self):
        rows = live.observation_history(
            {
                "ASOS": [
                    {"tm": self.base - timedelta(hours=25), "visibility": 1000},
                    {"tm": self.base - timedelta(hours=1), "visibility": 2500},
                    {
                        "tm": self.base,
                        "visibility": None,
                        "humidity": 70,
                        "sea_press": 1010,
                    },
                    {"tm": self.base + timedelta(hours=1), "visibility": 1000},
                ],
                "AIRKOREA": self.air,
            },
            self.base,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["visibility_km"], 25)
        self.assertIsNone(rows[0]["pm25"])
        self.assertEqual(rows[1]["pm25"], 10)
        self.assertEqual(rows[1]["pressure"], 1010)
        self.assertIsNone(rows[1]["visibility_km"])


class DashboardLatestTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.base = datetime.now(main.KST).replace(
            minute=0, second=0, microsecond=0, tzinfo=None
        )
        self.iso = self.base.replace(tzinfo=main.KST).isoformat()
        self.forecasts = {
            h: {
                "values": {},
                "valid_at": (self.base + timedelta(hours=h))
                .replace(tzinfo=main.KST)
                .isoformat(),
                "kma_issued_at": self.iso,
                "airkorea_issued_at": self.iso,
            }
            for h in range(1, 49)
        }
        for name, value in (
            ("read_forecasts", self.forecasts),
            ("read_model_history", []),
        ):
            stub = patch.object(main, name, return_value=value)
            stub.start()
            self.addCleanup(stub.stop)
        self.asos = {
            "tm": self.base,
            "stn_id": "112",
            "stn_ko": "인천",
            "temp": 21.0,
            "humidity": 70,
            "dew_point": 15.0,
            "wind_speed": 2.0,
            "wind_dir": 90,
            "sea_press": 1013.0,
            "rainfall": None,
            "cloud": None,
            "visibility": 3000,
        }
        self.air = {
            "tm": self.base,
            "station_name": "숭의",
            "station_code": "823632",
            "pm25": 10.0,
            "pm10": 20.0,
            "so2": 0.001,
            "no2": 0.01,
            "o3": 0.02,
            "co": 0.2,
        }
        self.marine = {
            "tm": self.base,
            "stn_name": "인천",
            "water_temp": 19.0,
            "salinity": 30.0,
            "temp": 20.0,
            "air_press": 1013.0,
            "wind_speed": 3.0,
            "wind_dir": 100,
            "gust_speed": 4.0,
        }
        self.collection = {
            "base_time": self.base,
            "collected_at": self.iso,
            "storage": "memory",
            "observations": {
                "ASOS": [self.asos],
                "AIRKOREA": [
                    {**self.air, "tm": self.base - timedelta(hours=i)}
                    for i in range(12)
                ],
                "TIDE_OBSERVATORY": [self.marine],
            },
            "forecast_inputs": self.forecasts,
            "model_input_observed_at": dict.fromkeys(
                ["ASOS", "AIRKOREA", "TIDE_OBSERVATORY"], self.iso
            ),
        }

    def connection(self):
        conn = MagicMock()
        conn.__enter__.return_value = conn
        cursors = []
        for row in [self.asos, self.air, None, self.marine]:
            cursor = MagicMock()
            cursor.__enter__.return_value = cursor
            cursor.fetchone.return_value = row
            cursor.fetchall.return_value = [{"pm25": 10.0, "pm10": 20.0}] * 12
            cursors.append(cursor)
        conn.cursor.side_effect = cursors
        return conn

    def test_collect_predict_four_horizons_without_database(self):
        with patch.object(
            main, "refresh_observations", return_value=self.collection
        ) as collect, patch.object(
            main, "get_connection", side_effect=AssertionError("DB must not be used")
        ) as connect, patch.object(
            main, "fetch_realtime_weather", return_value=None
        ), patch.object(
            main,
            "predict_visibility_pm",
            return_value={"visibility_km": 22.0, "pm25": 11.0, "pm10": 22.0},
        ) as predict:
            response = self.client.get(
                "/api/v1/stations/112/dashboard?forecast_interval_h=3"
            )
        self.assertEqual(response.status_code, 200, response.text)
        connect.assert_not_called()
        data = response.json()["data"]
        collect.assert_called_once_with("112", horizons=[3, 6, 9, 12])
        self.assertEqual([c.kwargs["h"] for c in predict.call_args_list], [3, 6, 9, 12])
        for call in predict.call_args_list:
            self.assertEqual(call.kwargs["asos"]["tm"], self.base)
            self.assertEqual(call.kwargs["airkorea"]["observed_at"], self.iso)
            self.assertEqual(call.kwargs["marine"]["observed_at"], self.iso)
        self.assertEqual(data["current"]["pm25_ug_m3"], 10.0)
        self.assertEqual(data["current"]["aqi"]["status"], "calculated")
        self.assertEqual(data["meta"]["collection"]["storage"], "memory")
        self.assertNotIn("observations", data["meta"]["collection"])
        self.assertNotIn("forecast_inputs", data["meta"]["collection"])
        self.assertTrue(all(s["status"] == "fresh" for s in data["source_status"]))
        self.assertEqual(
            data["meta"]["collection"]["model_input_observed_at"],
            self.collection["model_input_observed_at"],
        )

    def test_collection_failure_never_reads_old_data_or_calls_model(self):
        with patch.object(
            main,
            "refresh_observations",
            side_effect=live.CollectionError("ASOS", "STALE"),
        ), patch.object(main, "get_connection") as connect, patch.object(
            main, "predict_visibility_pm"
        ) as predict:
            response = self.client.get("/api/v1/stations/112/dashboard")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "LATEST_DATA_UNAVAILABLE")
        connect.assert_not_called()
        predict.assert_not_called()

    def test_collected_input_mismatch_stops_model(self):
        self.marine["tm"] -= timedelta(days=1)
        with patch.object(
            main, "refresh_observations", return_value=self.collection
        ), patch.object(
            main, "get_connection", return_value=self.connection()
        ), patch.object(
            main, "predict_visibility_pm"
        ) as predict:
            response = self.client.get("/api/v1/stations/112/dashboard")
        self.assertEqual(response.status_code, 503)
        predict.assert_not_called()

    def test_nowcast_preserves_missing_hour_slots(self):
        self.collection["observations"]["AIRKOREA"] = [self.air]
        with patch.object(
            main, "refresh_observations", return_value=self.collection
        ), patch.object(
            main, "get_connection", return_value=self.connection()
        ), patch.object(
            main,
            "predict_visibility_pm",
            return_value={"visibility_km": 22.0, "pm25": 11.0, "pm10": 22.0},
        ), patch.object(
            main, "fetch_realtime_weather", return_value=None
        ):
            response = self.client.get("/api/v1/stations/112/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["data"]["current"]["aqi"]["status"], "insufficient_data"
        )

    def test_model_failure_is_not_reported_as_success(self):
        with patch.object(
            main, "refresh_observations", return_value=self.collection
        ), patch.object(
            main, "get_connection", return_value=self.connection()
        ), patch.object(
            main, "predict_visibility_pm", side_effect=ValueError("test failure")
        ):
            response = self.client.get("/api/v1/stations/112/dashboard")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "FORECAST_FAILED")

    def test_historical_query_does_not_collect_or_ingest(self):
        with patch.object(main, "refresh_observations") as collect, patch.object(
            main, "get_connection", return_value=self.connection()
        ), patch.object(
            main, "fetch_realtime_weather", return_value=None
        ), patch.object(
            main,
            "predict_visibility_pm",
            return_value={"visibility_km": 22.0, "pm25": 11.0, "pm10": 22.0},
        ):
            response = self.client.get(
                "/api/v1/stations/112/dashboard", params={"as_of": self.iso}
            )
        self.assertEqual(response.status_code, 200, response.text)
        collect.assert_not_called()

    def test_nonfinite_model_output_is_not_turned_into_zero(self):
        with patch.object(
            main, "refresh_observations", return_value=self.collection
        ), patch.object(
            main, "get_connection", return_value=self.connection()
        ), patch.object(
            main,
            "predict_visibility_pm",
            return_value={"visibility_km": float("nan"), "pm25": 10.0, "pm10": 20.0},
        ):
            response = self.client.get("/api/v1/stations/112/dashboard")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "FORECAST_FAILED")

    def test_invalid_request_does_not_collect_or_write(self):
        with patch.object(main, "refresh_observations") as collect:
            for url in (
                "/api/v1/stations/999/dashboard",
                "/api/v1/stations/112/dashboard?forecast_interval_h=2",
            ):
                self.assertIn(self.client.get(url).status_code, (404, 422))
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
