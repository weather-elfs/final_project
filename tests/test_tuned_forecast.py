"""전달 튜닝형의 시각 매칭·단위·이력·출력 복원과 API 파서를 검증한다."""

import math
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np

from backend import forecast_inputs as fc
from backend import model_predict as model


class TunedModelTests(unittest.TestCase):
    def setUp(self):
        self.origin = datetime(2026, 10, 25, 18)
        self.asos = dict(
            temp=20,
            dew_point=14,
            humidity=70,
            wind_speed=2,
            wind_dir=9,
            sea_press=1013,
            rainfall=None,
            cloud=None,
            visibility=3000,
        )
        self.air = dict(
            pm25_ug_m3=10, pm10_ug_m3=20, so2=0.001, no2=0.01, o3=0.02, co=0.2
        )
        self.marine = dict(
            water_temperature_c=19,
            air_temperature_c=21,
            salinity_psu=30,
            wind_speed_m_s=3,
            wind_direction_deg=180,
            air_pressure_hpa=1014,
        )
        self.history = [
            dict(
                tm=self.origin - timedelta(hours=i),
                visibility_km=30 - i / 10,
                pm25=10 - i / 10,
                pm10=20 - i / 10,
                humidity=70 - i,
                pressure=1013 - i,
            )
            for i in range(25)
        ]
        self.forecast = {
            "valid_at": (self.origin + timedelta(hours=3))
            .replace(tzinfo=fc.KST)
            .isoformat(),
            "kma_issued_at": self.origin.replace(hour=17, tzinfo=fc.KST).isoformat(),
            "airkorea_issued_at": self.origin.replace(
                hour=17, tzinfo=fc.KST
            ).isoformat(),
            "values": {
                "future_fcst_temp": 17,
                "future_fcst_humidity": 80,
                "future_fcst_wind_speed": 4,
                "future_fcst_wind_dir": 270,
                "future_fcst_wind_dir_sin": -1,
                "future_fcst_wind_dir_cos": 0,
                "future_fcst_precipitation": 0,
                "future_fcst_pop": 10,
                "future_fcst_pty": 0,
                "future_fcst_sky": 3,
                "future_fcst_pm25_grade": 1,
                "fcst_age_h": 1,
            },
        }

    def inputs(self, h=3):
        return model.build_model_input(
            "112",
            self.origin,
            h,
            self.asos,
            self.air,
            self.marine,
            self.history,
            self.forecast,
        )

    def test_original_models_and_feature_order_are_used(self):
        models, meta = model.load_forecast_model()
        self.assertEqual(set(models), set(model.TARGETS))
        self.assertEqual(len(meta["features"]), 76)
        self.assertTrue(
            all(m.feature_names_ == meta["features"] for m in models.values())
        )
        self.assertTrue(
            all(
                set(t["sigma_by_h"]) == {str(h) for h in range(1, 49)}
                for t in meta["targets"].values()
            )
        )

    def test_units_history_and_derived_forecast_features_match_recipe(self):
        row = self.inputs().iloc[0]
        self.assertEqual(row.wind_dir, 90)
        self.assertAlmostEqual(row.wind_dir_sin, 1)
        self.assertAlmostEqual(row.extinction_coef, 0.0999)
        self.assertAlmostEqual(row.lag_1h_visibility_km, 29.9, places=4)
        self.assertAlmostEqual(row.diff_3h_visibility_km, 0.3, places=4)
        self.assertAlmostEqual(row.min_24h_visibility_km, 27.7, places=4)
        self.assertAlmostEqual(row.same_hour_prev_visibility_km, 27.9, places=4)
        self.assertEqual(row.f_dtemp, -3)
        self.assertEqual(row.f_air_sea_diff, -2)
        self.assertAlmostEqual(row.f_dpd, 17 - model.dewpoint(17, 80), places=5)
        self.assertTrue(math.isnan(row.pm1))
        self.assertTrue(math.isnan(row.buoy_wave_height))
        self.assertTrue(math.isnan(row.buoy_wave_period))
        self.assertEqual(row.precipitation, 0)

    def test_hour_48_uses_current_same_hour_not_future_data(self):
        self.forecast["valid_at"] = (
            (self.origin + timedelta(hours=48)).replace(tzinfo=fc.KST).isoformat()
        )
        self.assertEqual(self.inputs(h=48).iloc[0].same_hour_prev_visibility_km, 30)

    def test_missing_hour_is_nan_not_forward_filled(self):
        self.history = [
            r for r in self.history if r["tm"] != self.origin - timedelta(hours=1)
        ]
        self.assertTrue(math.isnan(self.inputs().iloc[0].lag_1h_visibility_km))

    def test_future_or_wrong_target_inputs_and_missing_baseline_are_rejected(self):
        original = self.forecast.copy()
        for field in ["valid_at", "kma_issued_at", "airkorea_issued_at"]:
            self.forecast = {
                **original,
                field: (self.origin + timedelta(hours=6))
                .replace(tzinfo=fc.KST)
                .isoformat(),
            }
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.inputs()
        self.forecast = original
        self.air["pm25_ug_m3"] = None
        with self.assertRaises(ValueError):
            self.inputs()

    def test_predictions_restore_log_residual_using_training_sigma(self):
        inputs = self.inputs()
        models, meta = model.load_forecast_model()
        actual = model.predict_visibility_pm(
            "112",
            self.origin,
            3,
            self.asos,
            self.air,
            self.marine,
            self.history,
            self.forecast,
        )
        for target, m in models.items():
            z = float(m.predict(inputs)[0])
            expected = np.expm1(
                np.log1p(float(inputs[target].iloc[0]))
                + z * meta["targets"][target]["sigma_by_h"]["3"]
            )
            maximum = meta["targets"][target]["clip_max"]
            if maximum is not None:
                expected = min(expected, maximum)
            self.assertAlmostEqual(actual[target], max(0, expected), places=8)
        self.assertIn("pm1", actual["missing_features"])


class ForecastParserTests(unittest.TestCase):
    def test_precipitation_uses_training_lower_bound_rule(self):
        for text, value in [
            ("강수없음", 0),
            ("1mm 미만", 0),
            ("2.5mm", 2.5),
            ("30~50mm", 30),
            ("50mm 이상", 50),
            ("0", 0),
        ]:
            self.assertEqual(fc.precipitation(text), value)
        with self.assertRaises(ValueError):
            fc.precipitation("알 수 없음")

    def test_pagination_reads_all_pages(self):
        response = MagicMock()
        response.__enter__.return_value = response
        pages = [
            {
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"totalCount": 2, "items": {"item": [{"i": i}]}},
                }
            }
            for i in range(2)
        ]
        with patch.object(
            fc.urllib.request, "urlopen", return_value=response
        ), patch.object(fc.json, "load", side_effect=pages):
            self.assertEqual(len(fc.request_items("https://example.test", {})), 2)

    def test_kma_checks_grid_issue_category_and_complete_fields(self):
        origin = datetime(2026, 10, 25, 18)
        items = [
            dict(
                nx=54,
                ny=125,
                baseDate="20261025",
                baseTime="1700",
                fcstDate="20261025",
                fcstTime="2100",
                category=c,
                fcstValue={
                    "TMP": "17",
                    "REH": "80",
                    "WSD": "4",
                    "VEC": "270",
                    "PCP": "강수없음",
                    "POP": "10",
                    "PTY": "0",
                    "SKY": "3",
                }[c],
            )
            for c in fc.FIELDS
        ]
        with patch.dict("os.environ", {"DATA_API_KEY": "test-only"}), patch.object(
            fc, "request_items", return_value=items
        ):
            self.assertEqual(fc.collect_kma("112", origin)[0]["tmp_1h"], 17)
            items[0]["nx"] = 55
            with self.assertRaises(ValueError):
                fc.collect_kma("112", origin)
            items[0]["nx"] = 54
            items.pop()
            with self.assertRaises(ValueError):
                fc.collect_kma("112", origin)

    def test_air_forecast_keeps_own_issue_time_and_incheon_grade(self):
        items = [
            dict(
                dataTime="2026-10-25 17시 발표",
                informCode="PM25",
                informData="2026-10-26",
                informGrade="서울 : 나쁨,인천 : 좋음",
            ),
            dict(
                dataTime="2026-10-25 23시 발표",
                informCode="PM25",
                informData="2026-10-26",
                informGrade="인천 : 매우나쁨",
            ),
        ]
        with patch.dict("os.environ", {"DATA_API_KEY": "test-only"}), patch.object(
            fc, "request_items", return_value=items
        ):
            rows = fc.collect_air(datetime(2026, 10, 25, 18))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fcst_pm25_grade"], 1)
        self.assertEqual(rows[0]["announce_time"].hour, 17)

    def test_missing_target_never_reuses_neighboring_forecast(self):
        origin = datetime(2026, 10, 25, 18)
        kma = [
            dict(
                base_time_kst=origin - timedelta(hours=1),
                fcst_time_kst=origin + timedelta(hours=3),
            )
        ]
        air = [
            dict(announce_time=origin - timedelta(hours=1), target_date=origin.date())
        ]
        with patch.object(fc, "collect_kma", return_value=kma), patch.object(
            fc, "collect_air", return_value=air
        ):
            with self.assertRaises(fc.ForecastError):
                fc.collect_forecasts("112", origin, [3, 6])


if __name__ == "__main__":
    unittest.main()
