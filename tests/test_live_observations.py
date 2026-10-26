"""외부 API를 고정하고 DB 연결 없이 최신 수집·예측 순서를 검증한다."""

import math
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend import live_observations as live
from backend import main


class LiveCollectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(live.KST)
        self.base = self.now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
        live._sessions.clear()
        self.addCleanup(live._sessions.clear)
        for name, rows in (
            (
                "collect_kma",
                [
                    dict(
                        base_time_kst=self.base - timedelta(hours=1),
                        fcst_time_kst=self.base + timedelta(hours=h),
                        tmp_1h=17,
                        reh=80,
                        wsd=4,
                        vec=270,
                        pcp_1h=0,
                        pop=10,
                        pty=0,
                        sky=3,
                    )
                    for h in range(1, 49)
                ],
            ),
            (
                "collect_air",
                [
                    dict(
                        announce_time=self.base - timedelta(hours=1),
                        target_date=(self.base + timedelta(days=d)).date(),
                        fcst_pm25_grade=1,
                    )
                    for d in range(3)
                ],
            ),
        ):
            stub = patch.object(live, name, return_value=rows)
            stub.start()
            self.addCleanup(stub.stop)
        self.asos = [
            {"tm": self.base, "stn_id": "112", "temp": 21.0, "visibility": 3000}
        ]
        self.air = [
            {"tm": self.base, "station_code": "823632", "pm25": 10.0, "pm10": 20.0}
        ]
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

    def test_missing_current_baseline_keeps_other_measurements_and_is_retryable(self):
        self.air[0]["pm25"] = None
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live, "collect_airkorea", return_value=self.air
        ), patch.object(live, "collect_marine", return_value=self.marine):
            result = live.refresh_observations("112")
        self.assertEqual(result["errors"]["AIRKOREA"], "BASELINE_MISSING")
        self.assertEqual(result["observations"]["AIRKOREA"][0]["pm10"], 20)
        self.assertIn("AIRKOREA", result["retryable_sources"])

    def test_phase_timeout_discards_pending_results_and_returns_partial_state(self):
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live, "collect_airkorea", return_value=self.air
        ), patch.object(live, "collect_marine", return_value=self.marine), patch.object(
            live, "wait", side_effect=lambda futures, timeout: (set(), set(futures))
        ):
            result = live.refresh_observations("112")
        self.assertTrue(
            all(reason == "TIMEOUT" for reason in result["errors"].values())
        )
        self.assertEqual(len(result["errors"]), 5)

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
            result = live.refresh_observations("112")
        connect.assert_not_called()
        self.assertEqual(result["errors"]["AIRKOREA"], "COLLECTION_FAILED")
        self.assertEqual(result["observations"]["ASOS"], self.asos)
        self.assertNotIn("secret", str(result))

    def test_no_aligned_source_does_not_ingest(self):
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live,
            "collect_airkorea",
            return_value=[{"tm": self.base + timedelta(seconds=1)}],
        ), patch.object(live, "collect_marine", return_value=self.marine), patch.object(
            main, "get_connection"
        ) as connect:
            result = live.refresh_observations("112")
        connect.assert_not_called()
        self.assertEqual(result["observations"]["AIRKOREA"], [])
        self.assertIn("AIRKOREA", result["retryable_sources"])

    def test_forecast_failure_is_reported_without_database(self):
        with patch.object(live, "collect_asos", return_value=self.asos), patch.object(
            live, "collect_airkorea", return_value=self.air
        ), patch.object(live, "collect_marine", return_value=self.marine), patch.object(
            main, "get_connection"
        ), patch.object(
            live,
            "collect_air",
            side_effect=live.CollectionError("AIRKOREA_FORECAST", "EMPTY_DATA"),
        ):
            result = live.refresh_observations("112")
        self.assertEqual(result["errors"]["AIRKOREA_FORECAST"], "EMPTY_DATA")
        self.assertTrue(
            math.isnan(result["forecast_inputs"][3]["values"]["future_fcst_pm25_grade"])
        )

    def test_retry_calls_only_failed_source_and_preserves_successful_data(self):
        with patch.object(
            live, "collect_asos", return_value=self.asos
        ) as asos, patch.object(
            live, "collect_airkorea", return_value=self.air
        ) as air, patch.object(
            live, "collect_marine", side_effect=TimeoutError()
        ):
            first = live.refresh_observations("112")
            with patch.object(
                live, "collect_marine", return_value=self.marine
            ) as marine, patch.object(
                live, "collect_kma", side_effect=AssertionError("must not refetch")
            ), patch.object(
                live, "collect_air", side_effect=AssertionError("must not refetch")
            ):
                second = live.refresh_observations(
                    "112", collection_id=first["id"], retry_source="TIDE_OBSERVATORY"
                )
        self.assertEqual(asos.call_count, 1)
        self.assertEqual(air.call_count, 1)
        marine.assert_called_once()
        self.assertEqual(first["fetched_at"]["ASOS"], second["fetched_at"]["ASOS"])
        self.assertEqual(second["errors"], {})
        for station, horizons, source, reason in (
            ("102", (3, 6, 9, 12), "TIDE_OBSERVATORY", "RETRY_CONTEXT_MISMATCH"),
            ("112", (1, 2, 3, 4), "TIDE_OBSERVATORY", "RETRY_CONTEXT_MISMATCH"),
            ("112", (3, 6, 9, 12), "ASOS", "SOURCE_NOT_RETRYABLE"),
        ):
            with self.assertRaises(live.CollectionError) as raised:
                live.refresh_observations(
                    station, horizons, collection_id=first["id"], retry_source=source
                )
            self.assertEqual(raised.exception.reason, reason)
        live._sessions[first["id"]]["created"] -= live.SESSION_SECONDS
        with self.assertRaises(live.CollectionError) as raised:
            live.refresh_observations(
                "112", collection_id=first["id"], retry_source="TIDE_OBSERVATORY"
            )
        self.assertEqual(raised.exception.reason, "COLLECTION_EXPIRED")

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
                    {"tm": self.base - timedelta(hours=73), "visibility": 1000},
                    {"tm": self.base - timedelta(hours=1), "visibility": 2500},
                    {
                        "tm": self.base,
                        "visibility": None,
                        "humidity": 70,
                        "sea_press": 1010,
                        "temp": 20,
                        "dew_point": 14,
                        "wind_speed": 2,
                        "rainfall": 0.5,
                    },
                    {"tm": self.base + timedelta(hours=1), "visibility": 1000},
                ],
                "AIRKOREA": self.air,
                "TIDE_OBSERVATORY": [{"tm": self.base, "water_temp": 19}],
            },
            self.base,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["visibility_km"], 25)
        self.assertIsNone(rows[0]["pm25"])
        self.assertEqual(rows[1]["pm25"], 10)
        self.assertEqual(rows[1]["pressure"], 1010)
        self.assertIsNone(rows[1]["visibility_km"])
        self.assertEqual(rows[1]["temperature"], 20)
        self.assertEqual(rows[1]["dewpoint"], 14)
        self.assertEqual(rows[1]["sea_temp"], 19)
        self.assertEqual(rows[1]["precipitation"], 0.5)
        self.assertIsNone(rows[0]["sea_temp"])


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

    def test_missing_marine_keeps_current_and_degraded_predictions(self):
        self.collection["observations"]["TIDE_OBSERVATORY"] = []
        self.collection["model_input_observed_at"]["TIDE_OBSERVATORY"] = None
        self.collection["errors"] = {"TIDE_OBSERVATORY": "COLLECTION_FAILED"}
        with patch.object(
            main, "refresh_observations", return_value=self.collection
        ), patch.object(
            main, "get_connection", return_value=self.connection()
        ), patch.object(
            main,
            "predict_visibility_pm",
            return_value={"visibility_km": 22.0, "pm25": 11.0, "pm10": 22.0},
        ) as predict:
            response = self.client.get("/api/v1/stations/112/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["current"]["temperature_c"], 21)
        self.assertTrue(
            all(
                p["status"] == "degraded"
                for p in response.json()["data"]["forecast_timeline"]
            )
        )
        self.assertIsNone(response.json()["data"]["mission_evaluation"]["passed"])
        self.assertEqual(predict.call_count, 4)

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
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(
            all(
                p["status"] == "unavailable"
                for p in response.json()["data"]["forecast_timeline"]
            )
        )
        self.assertEqual(response.json()["data"]["current"]["temperature_c"], 21)

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
        self.assertEqual(response.status_code, 200, response.text)
        points = response.json()["data"]["forecast_timeline"]
        self.assertTrue(
            all(
                p["visibility_pred_km"] is None and p["pm25_pred_ug_m3"] == 10
                for p in points
            )
        )

    def test_invalid_request_does_not_collect_or_write(self):
        with patch.object(main, "refresh_observations") as collect:
            for url in (
                "/api/v1/stations/999/dashboard",
                "/api/v1/stations/112/dashboard?forecast_interval_h=2",
            ):
                self.assertIn(self.client.get(url).status_code, (404, 422))
        collect.assert_not_called()

    def test_retry_http_route_preserves_good_sources_and_recovers_only_marine(self):
        weather = [
            dict(
                base_time_kst=self.base - timedelta(hours=1),
                fcst_time_kst=self.base + timedelta(hours=h),
                tmp_1h=17,
                reh=80,
                wsd=4,
                vec=270,
                pcp_1h=0,
                pop=10,
                pty=0,
                sky=3,
            )
            for h in range(1, 49)
        ]
        air_forecast = [
            dict(
                announce_time=self.base - timedelta(hours=1),
                target_date=(self.base + timedelta(days=d)).date(),
                fcst_pm25_grade=1,
            )
            for d in range(3)
        ]
        with patch.object(
            live, "collect_asos", return_value=[self.asos]
        ) as asos, patch.object(
            live,
            "collect_airkorea",
            return_value=self.collection["observations"]["AIRKOREA"],
        ) as air, patch.object(
            live, "collect_marine", side_effect=[TimeoutError(), [self.marine]]
        ) as marine, patch.object(
            live, "collect_kma", return_value=weather
        ) as kma, patch.object(
            live, "collect_air", return_value=air_forecast
        ) as air_pred, patch.object(
            main, "get_connection", side_effect=AssertionError("DB must not be used")
        ) as db, patch.object(
            main,
            "fetch_realtime_weather",
            side_effect=AssertionError("must not fetch extra API"),
        ):
            first = self.client.get("/api/v1/stations/112/dashboard")
            self.assertEqual(first.status_code, 200, first.text)
            data = first.json()["data"]
            second = self.client.get(
                "/api/v1/stations/112/dashboard",
                params={
                    "collection_id": data["meta"]["collection"]["id"],
                    "retry_source": "TIDE_OBSERVATORY",
                },
            )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["data"]["meta"]["collection"]["errors"], {})
        self.assertEqual(data["current"], second.json()["data"]["current"])
        self.assertEqual(marine.call_count, 2)
        for call in (asos, air, kma, air_pred):
            self.assertEqual(call.call_count, 1)
        db.assert_not_called()

    def test_missing_asos_keeps_air_measurements_and_pm_predictions(self):
        self.collection["observations"]["ASOS"] = []
        self.collection["errors"] = {"ASOS": "TIMEOUT"}
        self.collection["model_input_observed_at"]["ASOS"] = None
        with patch.object(main, "refresh_observations", return_value=self.collection):
            response = self.client.get("/api/v1/stations/112/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertIsNone(data["current"]["observed_at"])
        self.assertIsNone(data["current"]["visibility_km"])
        self.assertEqual(data["current"]["pm25_ug_m3"], 10)
        self.assertEqual(data["meta"]["model"]["origin_at"], self.iso)
        self.assertTrue(
            all(
                p["visibility_pred_km"] is None and p["pm25_pred_ug_m3"] is not None
                for p in data["forecast_timeline"]
            )
        )


if __name__ == "__main__":
    unittest.main()
