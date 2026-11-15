import unittest
from unittest.mock import patch

import collector
from collector import (
    collect_points,
    forecast_status,
    normalize_rows,
    parse_float,
    parse_kp,
    proton_point,
    solar_magnetic_point,
    solar_plasma_point,
    solar_wind_point,
    status_point,
    weather_point,
)


class ExternalContextParsingTests(unittest.TestCase):
    def test_normalize_current_object_format(self):
        payload = [{"time_tag": "2026-11-15T00:00:00", "Kp": 2.0}]
        self.assertEqual(normalize_rows(payload), payload)

    def test_normalize_legacy_table_format(self):
        payload = [
            ["time_tag", "Kp"],
            ["2026-11-15T00:00:00", "2.0"],
        ]
        rows = normalize_rows(payload)
        self.assertEqual(rows[0]["Kp"], "2.0")

    def test_parse_kp_accepts_upper_and_lowercase(self):
        self.assertEqual(parse_kp({"Kp": 3.33}), 3.33)
        self.assertEqual(parse_kp({"kp": 4.0}), 4.0)

    def test_parse_kp_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            parse_kp({"kp": 10})

    def test_forecast_status(self):
        self.assertEqual(
            forecast_status({"observed": "observed"}),
            "observed",
        )
        self.assertEqual(
            forecast_status({"observed": "estimated"}),
            "estimated",
        )
        self.assertEqual(
            forecast_status({"observed": "predicted"}),
            "predicted",
        )

    def test_solar_wind_parses_current_rtsw_feeds(self):
        plasma = [
            {
                "time_tag": "2026-11-15T20:00:00Z",
                "source": "DSCOVR",
                "active": True,
                "proton_density": 5.0,
                "proton_speed": 410.2,
            },
            {
                "time_tag": "2026-11-15T20:01:00Z",
                "source": "ACE",
                "active": False,
                "proton_density": 9.0,
                "proton_speed": 999.0,
            },
        ]
        magnetic = [
            {
                "time_tag": "2026-11-15T20:00:00Z",
                "source": "DSCOVR",
                "active": True,
                "bz_gsm": -3.5,
                "bt": 5.2,
            }
        ]
        self.assertIsNotNone(solar_plasma_point(plasma))
        self.assertIsNotNone(solar_magnetic_point(magnetic))
        self.assertIsNotNone(solar_wind_point(plasma, magnetic))

    def test_parse_float_rejects_nan(self):
        with self.assertRaises(ValueError):
            parse_float("NaN")

    def test_proton_selects_10_mev_channel(self):
        payload = [
            {
                "time_tag": "2026-11-15T20:00:00Z",
                "energy": ">=10 MeV",
                "flux": 1.25,
            }
        ]
        self.assertIsNotNone(proton_point(payload))

    def test_weather_point_accepts_current_payload(self):
        payload = {
            "current": {
                "time": "2026-11-15T20:00",
                "temperature_2m": 17.2,
                "relative_humidity_2m": 81,
                "surface_pressure": 1008.5,
                "precipitation": 0.1,
                "rain": 0.1,
            }
        }
        location = {
            "latitude": 38.7,
            "longitude": -9.1,
            "source": "ip",
            "city": "Example",
            "region": "",
            "country": "Example",
        }
        self.assertIsNotNone(weather_point(payload, location))

    def test_status_point_is_created_for_partial_sources(self):
        point = status_point({"kp": 1, "weather": 0})
        self.assertIsNotNone(point)

    @patch("collector.collect_weather")
    @patch("collector.fetch_json")
    def test_one_failed_source_does_not_block_others(
        self,
        mock_fetch_json,
        mock_collect_weather,
    ):
        kp_payload = [
            {
                "time_tag": "2026-11-15T20:00:00Z",
                "Kp": 2.0,
            }
        ]

        def fake_fetch(url):
            if url == collector.KP_OBSERVED_URL:
                return kp_payload
            raise RuntimeError("simulated upstream failure")

        mock_fetch_json.side_effect = fake_fetch
        mock_collect_weather.side_effect = RuntimeError(
            "simulated weather failure"
        )

        points, statuses = collect_points()

        self.assertGreaterEqual(len(points), 1)
        self.assertEqual(statuses["kp_observed"], 1)
        self.assertEqual(statuses["kp_forecast"], 0)
        self.assertEqual(statuses["weather"], 0)


if __name__ == "__main__":
    unittest.main()
