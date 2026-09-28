import math
import statistics


DETECTOR_STATUS_WARMUP = 0
DETECTOR_STATUS_OK = 1
DETECTOR_STATUS_NO_PULSES = 2
DETECTOR_STATUS_HIGH_CPM = 3
DETECTOR_STATUS_MAINS_INTERFERENCE = 4
DETECTOR_STATUS_MULTIPLE_WARNINGS = 5

CALIBRATION_STATUS_UNKNOWN = -1
CALIBRATION_STATUS_UNCALIBRATED = 0
CALIBRATION_STATUS_CALIBRATED = 1
CALIBRATION_STATUS_REFERENCE_CHECKED = 2


def analyze_pattern(
    pulse_times,
    mains_min_hz,
    mains_max_hz,
    mains_max_cv,
):
    if len(pulse_times) < 3:
        return 0.0, 0.0, False

    intervals = [
        current - previous
        for previous, current in zip(pulse_times, pulse_times[1:])
        if current > previous
    ]
    if len(intervals) < 2:
        return 0.0, 0.0, False

    mean_interval = statistics.fmean(intervals)
    if mean_interval <= 0:
        return 0.0, 0.0, False

    frequency_hz = 1.0 / mean_interval
    interval_cv = statistics.pstdev(intervals) / mean_interval
    looks_like_mains = (
        len(intervals) >= 20
        and mains_min_hz <= frequency_hz <= mains_max_hz
        and interval_cv <= mains_max_cv
    )
    return frequency_hz, interval_cv, looks_like_mains


def poisson_uncertainty(cpm, usvh_ratio):
    if cpm <= 0:
        return 0.0, 0.0, 0.0

    cpm_sigma = math.sqrt(cpm)
    cpm_relative = cpm_sigma / cpm
    usvh_sigma = cpm_sigma * usvh_ratio
    return cpm_sigma, cpm_relative, usvh_sigma


def detector_status(counter_ready, no_pulses, high_cpm, mains_pattern):
    warnings = []
    if no_pulses:
        warnings.append("NO_PULSES")
    if high_cpm:
        warnings.append("HIGH_CPM")
    if mains_pattern:
        warnings.append("POSSIBLE_MAINS_INTERFERENCE")

    if not counter_ready:
        text = "WARMUP"
        if warnings:
            text += "," + ",".join(warnings)
        return text, DETECTOR_STATUS_WARMUP

    if not warnings:
        return "OK", DETECTOR_STATUS_OK

    if len(warnings) > 1:
        return ",".join(warnings), DETECTOR_STATUS_MULTIPLE_WARNINGS

    warning = warnings[0]
    if warning == "NO_PULSES":
        return warning, DETECTOR_STATUS_NO_PULSES
    if warning == "HIGH_CPM":
        return warning, DETECTOR_STATUS_HIGH_CPM

    return warning, DETECTOR_STATUS_MAINS_INTERFERENCE


def calibration_status_code(status):
    normalized = status.strip().upper()
    mapping = {
        "UNCALIBRATED": CALIBRATION_STATUS_UNCALIBRATED,
        "CALIBRATED": CALIBRATION_STATUS_CALIBRATED,
        "REFERENCE_CHECKED": CALIBRATION_STATUS_REFERENCE_CHECKED,
    }
    return mapping.get(normalized, CALIBRATION_STATUS_UNKNOWN)
