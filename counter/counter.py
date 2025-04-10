import time
import datetime
from collections import deque
import RPi.GPIO as GPIO
from influxdb_client import InfluxDBClient, Point, WriteOptions

# ------------------- Config -------------------

# InfluxDB 2.x settings
url = "http://influxdb:8086"
token = "mysecrettoken"
org = "balena"
bucket = "balena-sense"

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=WriteOptions(batch_size=1))

# Geiger counter settings
PULSE_PIN = 7
usvh_ratio = 0.00812
counts = deque()
loop_count = 0

# ------------------- Setup -------------------

GPIO.setmode(GPIO.BOARD)
GPIO.setup(PULSE_PIN, GPIO.IN)

def countme(channel):
    timestamp = datetime.datetime.now()
    counts.append(timestamp)

GPIO.add_event_detect(PULSE_PIN, GPIO.FALLING, callback=countme)

# ------------------- Main Loop -------------------

while True:
    loop_count += 1

    # Remove pulses older than 60 seconds
    now = datetime.datetime.now()
    while counts and counts[0] < now - datetime.timedelta(seconds=60):
        counts.popleft()

    cpm = len(counts)
    usvh = round(cpm * usvh_ratio, 2)

    # Every 10 seconds, write to InfluxDB
    if loop_count == 10:
        point = Point("balena-sense") \
            .field("cpm", cpm) \
            .field("usvh", usvh) \
            .time(datetime.datetime.utcnow())

        write_api.write(bucket=bucket, org=org, record=point)
        print(f"[{datetime.datetime.now()}] Sent to InfluxDB → CPM: {cpm}, uSv/h: {usvh}")
        loop_count = 0

    time.sleep(1)
