import math
import unittest

from counter.metrics import (
    CALIBRATION_STATUS_CALIBRATED,
    CALIBRATION_STATUS_UNCALIBRATED,
    DETECTOR_STATUS_MAINS_INTERFERENCE,
    DETECTOR_STATUS_NO_PULSES,
    DETECTOR_STATUS_OK,
    DETECTOR_STATUS_WARMUP,
    analyze_pattern,
    calibration_status_code,
    detector_status,
    poisson_uncertainty,
)


class MetricsTests(unittest.TestCase):
    def test_poisson_uncertainty_for_25_cpm(self):
        cpm_sigma, relative, usvh_sigma = poisson_uncertainty(25, 0.00332)
        self.assertEqual(cpm_sigma, 5.0)
        self.assertAlmostEqual(relative, 0.2)
        self.assertAlmostEqual(usvh_sigma, 0.0166)

    def test_poisson_uncertainty_zero(self):
        self.assertEqual(poisson_uncertainty(0, 0.00332), (0.0, 0.0, 0.0))

    def test_detector_status_warmup(self):
        text, code = detector_status(False, False, False, False)
        self.assertEqual(text, "WARMUP")
        self.assertEqual(code, DETECTOR_STATUS_WARMUP)

    def test_detector_status_ok(self):
        text, code = detector_status(True, False, False, False)
        self.assertEqual(text, "OK")
        self.assertEqual(code, DETECTOR_STATUS_OK)

    def test_detector_status_no_pulses(self):
        text, code = detector_status(True, True, False, False)
        self.assertEqual(text, "NO_PULSES")
        self.assertEqual(code, DETECTOR_STATUS_NO_PULSES)

    def test_mains_pattern_detection(self):
        pulse_times = [index * 0.02 for index in range(30)]
        frequency, cv, looks_like_mains = analyze_pattern(
            pulse_times,
            45.0,
            65.0,
            0.25,
        )
        self.assertTrue(looks_like_mains)
        self.assertAlmostEqual(frequency, 50.0, places=5)
        self.assertLess(cv, 0.001)

    def test_irregular_pattern_is_not_mains(self):
        intervals = [0.010, 0.030, 0.015, 0.025] * 8
        pulse_times = [0.0]
        for interval in intervals:
            pulse_times.append(pulse_times[-1] + interval)

        _, _, looks_like_mains = analyze_pattern(
            pulse_times,
            45.0,
            65.0,
            0.25,
        )
        self.assertFalse(looks_like_mains)

    def test_calibration_status_codes(self):
        self.assertEqual(
            calibration_status_code("UNCALIBRATED"),
            CALIBRATION_STATUS_UNCALIBRATED,
        )
        self.assertEqual(
            calibration_status_code("calibrated"),
            CALIBRATION_STATUS_CALIBRATED,
        )


if __name__ == "__main__":
    unittest.main()
