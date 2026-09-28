import datetime
import os
import signal
import threading
import time
from collections import deque

import RPi.GPIO as GPIO
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from metrics import (
    analyze_pattern,
    calibration_status_code,
    detector_status,
    poisson_uncertainty,
)


url = os.getenv("INFLUX_URL", "http://influxdb:8086")
token = os.environ["INFLUX_TOKEN"]
org = os.getenv("INFLUX_ORG", "balena")
bucket = os.getenv("INFLUX_BUCKET", "balena-sense")

client = InfluxDBClient(url=url, token=token, org=org, timeout=10000)
write_api = client.write_api(write_options=SYNCHRONOUS)

PULSE_PIN = int(os.getenv("PULSE_PIN", "7"))
GPIO_PULL = os.getenv("GPIO_PULL", "off").strip().lower()
GPIO_EDGE = os.getenv("GPIO_EDGE", "falling").strip().lower()

# Default for a modern J305 glass tube specified at 44 CPS/(mR/h) with Co-60.
# This is an estimate, not a substitute for calibration against a reference meter.
# Reference:
# https://iot-devices.com.ua/en/geiger-tube-j305-how-to-calculate-the-conversion-factor-of-cpm-technical-note-en/
DEFAULT_USVH_RATIO = 0.00332
USVH_RATIO = float(os.getenv("USVH_RATIO", str(DEFAULT_USVH_RATIO)))
GEIGER_TUBE_MODEL = os.getenv("GEIGER_TUBE_MODEL", "J305")
SENSOR_ID = (
    os.getenv("SENSOR_ID")
    or os.getenv("BALENA_DEVICE_UUID")
    or "geiger-j305"
)
CALIBRATION_STATUS = os.getenv(
    "CALIBRATION_STATUS",
    "UNCALIBRATED",
).strip() or "UNCALIBRATED"
CALIBRATION_STATUS_CODE = calibration_status_code(CALIBRATION_STATUS)

WARMUP_SECONDS = float(os.getenv("WARMUP_SECONDS", "60"))
WRITE_INTERVAL_SECONDS = float(os.getenv("WRITE_INTERVAL_SECONDS", "10"))
NO_PULSE_WARNING_SECONDS = int(os.getenv("NO_PULSE_WARNING_SECONDS", "180"))
HIGH_CPM_WARNING = int(os.getenv("HIGH_CPM_WARNING", "1000"))
MAINS_MIN_HZ = float(os.getenv("MAINS_MIN_HZ", "45"))
MAINS_MAX_HZ = float(os.getenv("MAINS_MAX_HZ", "65"))
MAINS_MAX_CV = float(os.getenv("MAINS_MAX_CV", "0.25"))
PATTERN_WINDOW_SECONDS = float(os.getenv("PATTERN_WINDOW_SECONDS", "2.0"))
INFLUX_WRITE_RETRIES = max(
    1,
    int(os.getenv("INFLUX_WRITE_RETRIES", "3")),
)
INFLUX_RETRY_DELAY_SECONDS = max(
    0.0,
    float(os.getenv("INFLUX_RETRY_DELAY_SECONDS", "1.0")),
)

counts = deque()
counts_lock = threading.Lock()
running = True
started_at = time.monotonic()
next_write_at = started_at + WRITE_INTERVAL_SECONDS
last_pulse_at = None
pulse_total = 0
write_failures_total = 0

GPIO.setmode(GPIO.BOARD)

pull_modes = {
    "up": GPIO.PUD_UP,
    "down": GPIO.PUD_DOWN,
    "off": GPIO.PUD_OFF,
    "none": GPIO.PUD_OFF,
}
if GPIO_PULL not in pull_modes:
    raise ValueError("GPIO_PULL must be one of: up, down, off")

edge_modes = {
    "falling": GPIO.FALLING,
    "rising": GPIO.RISING,
}
if GPIO_EDGE not in edge_modes:
    raise ValueError("GPIO_EDGE must be one of: falling, rising")

GPIO.setup(PULSE_PIN, GPIO.IN, pull_up_down=pull_modes[GPIO_PULL])


def countme(_channel):
    global last_pulse_at
    global pulse_total

    pulse_time = time.monotonic()
    with counts_lock:
        counts.append(pulse_time)
        last_pulse_at = pulse_time
        pulse_total += 1


def request_shutdown(_signum, _frame):
    global running
    running = False


def write_with_retries(point):
    global write_failures_total

    for attempt in range(1, INFLUX_WRITE_RETRIES + 1):
        try:
            write_api.write(bucket=bucket, org=org, record=point)
            return True
        except Exception as exc:
            write_failures_total += 1
            print(
                f"[{datetime.datetime.now()}] InfluxDB write attempt "
                f"{attempt}/{INFLUX_WRITE_RETRIES} failed: {exc}",
                flush=True,
            )

            if attempt < INFLUX_WRITE_RETRIES and running:
                time.sleep(INFLUX_RETRY_DELAY_SECONDS * attempt)

    return False


GPIO.add_event_detect(
    PULSE_PIN,
    edge_modes[GPIO_EDGE],
    callback=countme,
)
signal.signal(signal.SIGTERM, request_shutdown)
signal.signal(signal.SIGINT, request_shutdown)

print(
    "Counter configuration -> "
    f"sensor={SENSOR_ID}, "
    f"tube={GEIGER_TUBE_MODEL}, "
    f"pin={PULSE_PIN} (BOARD), "
    f"edge={GPIO_EDGE}, "
    f"pull={GPIO_PULL}, "
    f"CPM-to-uSv/h ratio={USVH_RATIO:.8f}, "
    f"calibration={CALIBRATION_STATUS}, "
    f"warmup={WARMUP_SECONDS:.0f}s",
    flush=True,
)
print(
    "GPIO safety -> software pull resistors do not level-shift a 5 V signal. "
    "Verify the detector output is safe for a 3.3 V Raspberry Pi GPIO.",
    flush=True,
)

try:
    while running:
        now_monotonic = time.monotonic()
        cutoff_60s = now_monotonic - 60.0
        cutoff_1s = now_monotonic - 1.0
        pattern_cutoff = now_monotonic - PATTERN_WINDOW_SECONDS

        with counts_lock:
            while counts and counts[0] < cutoff_60s:
                counts.popleft()

            pulse_snapshot = list(counts)
            cpm = len(pulse_snapshot)
            cps = sum(
                1 for pulse_time in pulse_snapshot if pulse_time >= cutoff_1s
            )
            pattern_times = [
                pulse_time
                for pulse_time in pulse_snapshot
                if pulse_time >= pattern_cutoff
            ]
            last_pulse_snapshot = last_pulse_at
            pulse_total_snapshot = pulse_total

        pattern_hz, pattern_cv, mains_pattern = analyze_pattern(
            pattern_times,
            MAINS_MIN_HZ,
            MAINS_MAX_HZ,
            MAINS_MAX_CV,
        )
        usvh = cpm * USVH_RATIO
        cpm_sigma, cpm_relative, usvh_sigma = poisson_uncertainty(
            cpm,
            USVH_RATIO,
        )
        gpio_level = int(GPIO.input(PULSE_PIN))

        uptime = now_monotonic - started_at
        counter_ready = 1 if uptime >= WARMUP_SECONDS else 0
        last_pulse_age_s = (
            now_monotonic - last_pulse_snapshot
            if last_pulse_snapshot is not None
            else uptime
        )

        no_pulses = (
            bool(counter_ready)
            and last_pulse_age_s >= NO_PULSE_WARNING_SECONDS
        )
        high_cpm = cpm >= HIGH_CPM_WARNING

        detector_status_text, detector_status_code = detector_status(
            bool(counter_ready),
            no_pulses,
            high_cpm,
            mains_pattern,
        )
        signal_anomaly = (
            1
            if detector_status_code not in (0, 1)
            else 0
        )

        if now_monotonic >= next_write_at:
            while next_write_at <= now_monotonic:
                next_write_at += WRITE_INTERVAL_SECONDS

            point = (
                Point("balena-sense")
                .field("cpm", cpm)
                .field("cpm_sigma", cpm_sigma)
                .field("cpm_relative_uncertainty", cpm_relative)
                .field("cpm_relative_uncertainty_pct", cpm_relative * 100.0)
                .field("cps", cps)
                .field("usvh", usvh)
                .field("usvh_sigma", usvh_sigma)
                .field("usvh_ratio", USVH_RATIO)
                .field("tube_model", GEIGER_TUBE_MODEL)
                .field("sensor_id", SENSOR_ID)
                .field("calibration_status", CALIBRATION_STATUS)
                .field("calibration_status_code", CALIBRATION_STATUS_CODE)
                .field("gpio_level", gpio_level)
                .field("counter_ready", counter_ready)
                .field("last_pulse_age_s", last_pulse_age_s)
                .field("pulse_total", pulse_total_snapshot)
                .field("uptime_s", uptime)
                .field("write_failures_total", write_failures_total)
                .field("signal_anomaly", signal_anomaly)
                .field("signal_warning", detector_status_text)
                .field("detector_status", detector_status_text)
                .field("detector_status_code", detector_status_code)
                .field("pattern_hz", pattern_hz)
                .field("pattern_cv", pattern_cv)
                .time(datetime.datetime.now(datetime.timezone.utc))
            )

            if write_with_retries(point):
                print(
                    f"[{datetime.datetime.now()}] "
                    f"sensor={SENSOR_ID} "
                    f"CPM={cpm} "
                    f"sigma={cpm_sigma:.2f} "
                    f"rel_unc={cpm_relative * 100.0:.1f}% "
                    f"CPS={cps} "
                    f"est_uSv_h={usvh:.4f} "
                    f"est_sigma={usvh_sigma:.4f} "
                    f"GPIO={gpio_level} "
                    f"last_pulse_s={last_pulse_age_s:.1f} "
                    f"total={pulse_total_snapshot} "
                    f"status={detector_status_text} "
                    f"pattern_hz={pattern_hz:.2f} "
                    f"pattern_cv={pattern_cv:.3f}",
                    flush=True,
                )

        time.sleep(1)
finally:
    GPIO.remove_event_detect(PULSE_PIN)
    GPIO.cleanup()
    write_api.close()
    client.close()
