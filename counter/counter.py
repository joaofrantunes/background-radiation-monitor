import datetime
import os
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

PULSE_PIN = 7
USVH_RATIO = 0.00812
counts = deque()
loop_count = 0

GPIO.setmode(GPIO.BOARD)
GPIO.setup(PULSE_PIN, GPIO.IN)


def countme(channel):
    counts.append(datetime.datetime.now())


GPIO.add_event_detect(PULSE_PIN, GPIO.FALLING, callback=countme)

while True:
    loop_count += 1

    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(seconds=60)

    while counts and counts[0] < cutoff:
        counts.popleft()

    cpm = len(counts)
    usvh = round(cpm * USVH_RATIO, 2)

    if loop_count >= 10:
        point = (
            Point("balena-sense")
            .field("cpm", cpm)
            .field("usvh", usvh)
            .time(datetime.datetime.now(datetime.timezone.utc))
        )

        try:
            write_api.write(bucket=bucket, org=org, record=point)
            print(
                f"[{datetime.datetime.now()}] Sent to InfluxDB -> "
                f"CPM: {cpm}, uSv/h: {usvh}"
            )
        except Exception as exc:
            print(f"[{datetime.datetime.now()}] InfluxDB write failed: {exc}")

        loop_count = 0

    time.sleep(1)
