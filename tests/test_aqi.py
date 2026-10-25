"""EPA May 2026 NowCast/AQI examples and service display boundaries."""

import unittest

from backend.aqi import calculate_current_aqi, nowcast, pm_to_aqi


class AqiTests(unittest.TestCase):
    def test_official_nowcast_example_preserves_missing_hour_weight(self):
        samples = [21, None, 35, 49.2, 48.6, 53.7, 66.2, 69.2, 64.9, 50, 43, 34.9]
        self.assertAlmostEqual(nowcast(samples), 28.409801367632692)
        self.assertEqual(pm_to_aqi(nowcast(samples), "pm25"), 87)

    def test_recent_three_hours_need_two_real_observations(self):
        self.assertIsNone(nowcast([10, None, None, 20, 30]))
        self.assertIsNotNone(nowcast([10, None, 20]))
        self.assertIsNone(nowcast([]))
        self.assertEqual(nowcast([0] * 12), 0)
        self.assertEqual(nowcast([10] * 12 + [10000]), 10)

    def test_official_breakpoints_and_constant_series(self):
        cases = {
            "pm25": [
                (0, 0),
                (9, 50),
                (9.1, 51),
                (35.4, 100),
                (35.5, 101),
                (55.4, 150),
                (55.5, 151),
                (125.4, 200),
                (125.5, 201),
                (225.4, 300),
                (225.5, 301),
                (325.4, 500),
            ],
            "pm10": [
                (0, 0),
                (54, 50),
                (55, 51),
                (154, 100),
                (155, 101),
                (254, 150),
                (255, 151),
                (354, 200),
                (355, 201),
                (424, 300),
                (425, 301),
                (604, 500),
            ],
        }
        for pollutant, pairs in cases.items():
            for concentration, expected in pairs:
                with self.subTest(pollutant=pollutant, concentration=concentration):
                    self.assertEqual(pm_to_aqi(concentration, pollutant), expected)
                    self.assertEqual(
                        pm_to_aqi(nowcast([concentration] * 12), pollutant), expected
                    )

    def test_truncation_and_half_up_rounding(self):
        self.assertEqual(pm_to_aqi(9.09, "pm25"), 50)
        self.assertEqual(pm_to_aqi(9.19, "pm25"), 51)
        self.assertEqual(pm_to_aqi(54.99, "pm10"), 50)
        self.assertEqual(pm_to_aqi(0.9, "pm25"), 5)

    def test_above_500_uses_last_interval_slope(self):
        self.assertEqual(pm_to_aqi(400, "pm25"), 649)
        self.assertEqual(pm_to_aqi(700, "pm10"), 607)
        self.assertEqual(
            calculate_current_aqi([400] * 12, [0] * 12)["display_level"], 5
        )

    def test_invalid_values_do_not_crash_or_create_valid_samples(self):
        for value in (None, -1, float("nan"), float("inf"), "invalid"):
            with self.subTest(value=value):
                self.assertIsNone(pm_to_aqi(value, "pm25"))
                self.assertIsNone(nowcast([value, value, 10]))

    def test_maximum_subindex_and_missing_pollutant_policy(self):
        result = calculate_current_aqi([3] * 12, [19] * 12)
        self.assertEqual(result["value"], 18)
        self.assertEqual(result["dominant_pollutant"], "PM10")
        result = calculate_current_aqi([3] * 12, [None] * 12)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["value"])


if __name__ == "__main__":
    unittest.main()
