import datetime
import os
import signal
import statistics
import threading
import time
from collections import deque

import RPi.GPIO as GPIO
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


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

NO_PULSE_WARNING_SECONDS = int(os.getenv("NO_PULSE_WARNING_SECONDS", "300"))
HIGH_CPM_WARNING = int(os.getenv("HIGH_CPM_WARNING", "1000"))
MAINS_MIN_HZ = float(os.getenv("MAINS_MIN_HZ", "45"))
MAINS_MAX_HZ = float(os.getenv("MAINS_MAX_HZ", "65"))
MAINS_MAX_CV = float(os.getenv("MAINS_MAX_CV", "0.25"))
PATTERN_WINDOW_SECONDS = float(os.getenv("PATTERN_WINDOW_SECONDS", "2.0"))

counts = deque()
counts_lock = threading.Lock()
loop_count = 0
running = True
started_at = time.monotonic()
last_pulse_at = None

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

    pulse_time = time.monotonic()
    with counts_lock:
        counts.append(pulse_time)
        last_pulse_at = pulse_time


def request_shutdown(_signum, _frame):
    global running
    running = False


def analyze_pattern(pulse_times):
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
        and MAINS_MIN_HZ <= frequency_hz <= MAINS_MAX_HZ
        and interval_cv <= MAINS_MAX_CV
    )
    return frequency_hz, interval_cv, looks_like_mains


GPIO.add_event_detect(
    PULSE_PIN,
    edge_modes[GPIO_EDGE],
    callback=countme,
)
signal.signal(signal.SIGTERM, request_shutdown)
signal.signal(signal.SIGINT, request_shutdown)

print(
    "Counter configuration -> "
    f"tube={GEIGER_TUBE_MODEL}, "
    f"pin={PULSE_PIN} (BOARD), "
    f"edge={GPIO_EDGE}, "
    f"pull={GPIO_PULL}, "
    f"CPM-to-uSv/h ratio={USVH_RATIO:.8f}"
)
print(
    "GPIO safety -> software pull resistors do not level-shift a 5 V signal. "
    "Verify the detector output is safe for a 3.3 V Raspberry Pi GPIO."
)

try:
    while running:
        loop_count += 1
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

        pattern_hz, pattern_cv, mains_pattern = analyze_pattern(pattern_times)
        usvh = cpm * USVH_RATIO
        gpio_level = int(GPIO.input(PULSE_PIN))

        uptime = now_monotonic - started_at
        no_pulse_age = (
            now_monotonic - last_pulse_snapshot
            if last_pulse_snapshot is not None
            else uptime
        )

        warnings = []
        if no_pulse_age >= NO_PULSE_WARNING_SECONDS:
            warnings.append("NO_PULSES")
        if cpm >= HIGH_CPM_WARNING:
            warnings.append("HIGH_CPM")
        if mains_pattern:
            warnings.append("POSSIBLE_MAINS_INTERFERENCE")

        signal_warning = ",".join(warnings) if warnings else "OK"
        signal_anomaly = 1 if warnings else 0

        if loop_count >= 10:
            point = (
                Point("balena-sense")
                .field("cpm", cpm)
                .field("cps", cps)
                .field("usvh", usvh)
                .field("usvh_ratio", USVH_RATIO)
                .field("tube_model", GEIGER_TUBE_MODEL)
                .field("gpio_level", gpio_level)
                .field("signal_anomaly", signal_anomaly)
                .field("signal_warning", signal_warning)
                .field("pattern_hz", pattern_hz)
                .field("pattern_cv", pattern_cv)
                .time(datetime.datetime.now(datetime.timezone.utc))
            )

            try:
                write_api.write(bucket=bucket, org=org, record=point)
                print(
                    f"[{datetime.datetime.now()}] Sent to InfluxDB -> "
                    f"CPM: {cpm}, CPS: {cps}, "
                    f"estimated uSv/h: {usvh:.3f}, "
                    f"GPIO: {gpio_level}, status: {signal_warning}, "
                    f"pattern: {pattern_hz:.2f} Hz (CV={pattern_cv:.3f})"
                )
            except Exception as exc:
                print(f"[{datetime.datetime.now()}] InfluxDB write failed: {exc}")

            loop_count = 0

        time.sleep(1)
finally:
    GPIO.remove_event_detect(PULSE_PIN)
    GPIO.cleanup()
    write_api.close()
    client.close()
