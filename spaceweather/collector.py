import datetime
import json
import math
import os
import time
import urllib.parse
import urllib.request

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS


APP_VERSION = "1.11.2"

KP_OBSERVED_URL = os.getenv(
    "NOAA_KP_OBSERVED_URL",
    "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
)
KP_FORECAST_URL = os.getenv(
    "NOAA_KP_FORECAST_URL",
    "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json",
)
SOLAR_WIND_PLASMA_URL = os.getenv(
    "NOAA_SOLAR_WIND_PLASMA_URL",
    "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json",
)
SOLAR_WIND_MAG_URL = os.getenv(
    "NOAA_SOLAR_WIND_MAG_URL",
    "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json",
)
DST_URL = os.getenv(
    "NOAA_DST_URL",
    "https://services.swpc.noaa.gov/products/kyoto-dst.json",
)
PROTON_URL = os.getenv(
    "NOAA_PROTON_URL",
    "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-3-day.json",
)

IP_GEOLOCATION_URL = os.getenv(
    "IP_GEOLOCATION_URL",
    "https://ipwho.is/",
)
OPEN_METEO_URL = os.getenv(
    "OPEN_METEO_URL",
    "https://api.open-meteo.com/v1/forecast",
)

FETCH_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("NOAA_FETCH_INTERVAL_SECONDS", "300")),
)
HTTP_TIMEOUT_SECONDS = max(
    5,
    int(os.getenv("NOAA_HTTP_TIMEOUT_SECONDS", "20")),
)
WEATHER_LATITUDE = os.getenv("WEATHER_LATITUDE")
WEATHER_LONGITUDE = os.getenv("WEATHER_LONGITUDE")
WEATHER_LOCATION_MODE = os.getenv(
    "WEATHER_LOCATION_MODE",
    "auto",
).strip().lower()

INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
INFLUX_ORG = os.getenv("INFLUX_ORG", "balena")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "balena-sense")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def log(message):
    print(f"[{utc_now().isoformat()}] {message}", flush=True)


def normalize_rows(payload):
    if not isinstance(payload, list):
        raise ValueError("Payload must be a JSON array")

    if not payload:
        return []

    if isinstance(payload[0], dict):
        return payload

    if isinstance(payload[0], list):
        header = payload[0]
        return [
            dict(zip(header, values))
            for values in payload[1:]
            if isinstance(values, list)
        ]

    raise ValueError("Unsupported JSON array format")


def parse_timestamp(value):
    if not value:
        raise ValueError("Missing timestamp")

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)

    return parsed.astimezone(datetime.timezone.utc)


def parse_float(value, minimum=None, maximum=None):
    if value in (None, ""):
        raise ValueError("Missing numeric value")

    number = float(value)

    if not math.isfinite(number):
        raise ValueError(f"Non-finite numeric value: {value}")

    if minimum is not None and number < minimum:
        raise ValueError(f"Value below minimum: {number}")
    if maximum is not None and number > maximum:
        raise ValueError(f"Value above maximum: {number}")

    return number


def parse_kp(row):
    return parse_float(
        row.get("Kp", row.get("kp")),
        minimum=0.0,
        maximum=9.0,
    )


def forecast_status(row):
    raw = (
        row.get("observed")
        or row.get("status")
        or row.get("type")
        or "predicted"
    )
    text = str(raw).strip().lower()

    aliases = {
        "observation": "observed",
        "observation/estimated": "estimated",
        "estimate": "estimated",
        "forecast": "predicted",
        "prediction": "predicted",
    }
    text = aliases.get(text, text)

    if text not in ("observed", "estimated", "predicted"):
        return "predicted"

    return text


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"background-radiation-monitor/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(
        request,
        timeout=HTTP_TIMEOUT_SECONDS,
    ) as response:
        return json.load(response)


def first_value(row, field):
    if isinstance(field, tuple):
        for name in field:
            value = row.get(name)
            if value not in (None, ""):
                return value
        return None
    return row.get(field)


def is_active_value(value):
    if value is True or value == 1:
        return True
    return str(value).strip().lower() in ("true", "1", "yes")


def latest_valid_row(payload, required_fields, prefer_active=False):
    rows = normalize_rows(payload)

    if prefer_active and any("active" in row for row in rows):
        rows = [
            row
            for row in rows
            if is_active_value(row.get("active"))
        ]

    best = None
    for row in rows:
        try:
            timestamp = parse_timestamp(row.get("time_tag"))
            for field in required_fields:
                parse_float(first_value(row, field))
        except (TypeError, ValueError):
            continue

        if best is None or timestamp > best[0]:
            best = (timestamp, row)

    return best[1] if best is not None else None


def observed_points(payload):
    points = []
    for row in normalize_rows(payload):
        try:
            timestamp = parse_timestamp(row.get("time_tag"))
            kp = parse_kp(row)
        except (TypeError, ValueError):
            continue

        point = (
            Point("space-weather-kp")
            .tag("provider", "NOAA_SWPC")
            .tag("feed", "observed")
            .tag("status", "observed")
            .field("kp", kp)
        )

        station_count = row.get("station_count")
        if station_count is not None:
            try:
                point = point.field("station_count", int(station_count))
            except (TypeError, ValueError):
                pass

        points.append(point.time(timestamp))

    return points


def forecast_points(payload):
    points = []
    for row in normalize_rows(payload):
        try:
            timestamp = parse_timestamp(row.get("time_tag"))
            kp = parse_kp(row)
        except (TypeError, ValueError):
            continue

        status = forecast_status(row)
        point = (
            Point("space-weather-kp")
            .tag("provider", "NOAA_SWPC")
            .tag("feed", "forecast")
            .tag("status", status)
            .field("kp", kp)
        )

        noaa_scale = row.get("noaa_scale")
        if noaa_scale not in (None, ""):
            point = point.field("noaa_scale", str(noaa_scale))

        points.append(point.time(timestamp))

    return points


def solar_plasma_point(payload):
    row = latest_valid_row(
        payload,
        (("proton_speed", "speed"),),
        prefer_active=True,
    )
    if row is None:
        return None

    point = (
        Point("space-weather-solar-wind")
        .tag("provider", "NOAA_SWPC")
        .tag("source", str(row.get("source") or "unknown"))
        .field(
            "speed_km_s",
            parse_float(
                first_value(row, ("proton_speed", "speed")),
                minimum=0.0,
            ),
        )
    )

    density = first_value(row, ("proton_density", "density"))
    if density not in (None, ""):
        point = point.field(
            "density_p_cm3",
            parse_float(density, minimum=0.0),
        )

    return point.time(parse_timestamp(row.get("time_tag")))


def solar_magnetic_point(payload):
    row = latest_valid_row(
        payload,
        ("bz_gsm",),
        prefer_active=True,
    )
    if row is None:
        return None

    point = (
        Point("space-weather-solar-wind")
        .tag("provider", "NOAA_SWPC")
        .tag("source", str(row.get("source") or "unknown"))
        .field("bz_gsm_nt", parse_float(row.get("bz_gsm")))
    )

    bt = row.get("bt")
    if bt not in (None, ""):
        point = point.field(
            "bt_nt",
            parse_float(bt, minimum=0.0),
        )

    return point.time(parse_timestamp(row.get("time_tag")))


def solar_wind_point(plasma_payload, magnetic_payload):
    plasma = solar_plasma_point(plasma_payload)
    magnetic = solar_magnetic_point(magnetic_payload)
    return plasma or magnetic


def dst_point(payload):
    row = latest_valid_row(payload, ("dst",))
    if row is None:
        return None

    return (
        Point("space-weather-dst")
        .tag("provider", "NOAA_SWPC")
        .field("dst_nt", parse_float(row.get("dst")))
        .time(parse_timestamp(row.get("time_tag")))
    )


def proton_point(payload):
    rows = normalize_rows(payload)
    best = None

    for row in reversed(rows):
        energy = str(row.get("energy", "")).replace(" ", "")
        if energy not in (">=10MeV", ">10MeV", "10MeV"):
            continue

        try:
            timestamp = parse_timestamp(row.get("time_tag"))
            flux = parse_float(row.get("flux"), minimum=0.0)
        except (TypeError, ValueError):
            continue

        best = (timestamp, flux)
        break

    if best is None:
        return None

    timestamp, flux = best
    return (
        Point("space-weather-protons")
        .tag("provider", "NOAA_SWPC")
        .tag("energy", ">=10MeV")
        .field("flux_pfu", flux)
        .time(timestamp)
    )


def resolve_location():
    if WEATHER_LATITUDE and WEATHER_LONGITUDE:
        return {
            "latitude": parse_float(
                WEATHER_LATITUDE,
                minimum=-90.0,
                maximum=90.0,
            ),
            "longitude": parse_float(
                WEATHER_LONGITUDE,
                minimum=-180.0,
                maximum=180.0,
            ),
            "source": "manual",
            "city": "",
            "region": "",
            "country": "",
        }

    if WEATHER_LOCATION_MODE == "manual":
        raise RuntimeError(
            "WEATHER_LOCATION_MODE=manual requires WEATHER_LATITUDE "
            "and WEATHER_LONGITUDE"
        )

    payload = fetch_json(IP_GEOLOCATION_URL)
    if payload.get("success") is False:
        raise RuntimeError(
            f"IP geolocation failed: {payload.get('message', 'unknown error')}"
        )

    return {
        "latitude": parse_float(
            payload.get("latitude"),
            minimum=-90.0,
            maximum=90.0,
        ),
        "longitude": parse_float(
            payload.get("longitude"),
            minimum=-180.0,
            maximum=180.0,
        ),
        "source": "ip",
        "city": str(payload.get("city") or ""),
        "region": str(payload.get("region") or ""),
        "country": str(payload.get("country") or ""),
    }


def weather_url(location):
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "current": (
            "temperature_2m,relative_humidity_2m,surface_pressure,"
            "precipitation,rain"
        ),
        "timezone": "UTC",
    }
    return OPEN_METEO_URL + "?" + urllib.parse.urlencode(params)


def weather_point(payload, location):
    current = payload.get("current")
    if not isinstance(current, dict):
        raise ValueError("Open-Meteo response missing current weather")

    timestamp = parse_timestamp(current.get("time"))

    point = (
        Point("local-weather")
        .tag("provider", "Open-Meteo")
        .tag("location_source", location["source"])
        .field(
            "temperature_c",
            parse_float(current.get("temperature_2m")),
        )
        .field(
            "relative_humidity_pct",
            parse_float(
                current.get("relative_humidity_2m"),
                minimum=0.0,
                maximum=100.0,
            ),
        )
        .field(
            "surface_pressure_hpa",
            parse_float(
                current.get("surface_pressure"),
                minimum=100.0,
            ),
        )
        .field(
            "precipitation_mm",
            parse_float(
                current.get("precipitation"),
                minimum=0.0,
            ),
        )
        .field(
            "rain_mm",
            parse_float(
                current.get("rain"),
                minimum=0.0,
            ),
        )
        .field("latitude", float(location["latitude"]))
        .field("longitude", float(location["longitude"]))
    )

    if location["city"]:
        point = point.tag("location_city", location["city"])
    if location["region"]:
        point = point.tag("location_region", location["region"])
    if location["country"]:
        point = point.tag("location_country", location["country"])

    return point.time(timestamp)


def as_points(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [point for point in value if point is not None]
    return [value]


def collect_source(name, callback, points, statuses):
    try:
        produced = as_points(callback())
        if not produced:
            raise RuntimeError("no valid points returned")

        points.extend(produced)
        statuses[name] = 1
        log(f"source={name} status=OK points={len(produced)}")
    except Exception as exc:
        statuses[name] = 0
        log(
            f"source={name} status=ERROR "
            f"error={type(exc).__name__}: {exc}"
        )


def collect_weather():
    location = resolve_location()
    log(f"weather location source={location['source']}")
    return weather_point(
        fetch_json(weather_url(location)),
        location,
    )


def status_point(statuses):
    sources_ok = sum(statuses.values())
    sources_total = len(statuses)
    sources_failed = sources_total - sources_ok

    if sources_ok == 0:
        status_code = 0
        status_text = "NO_EXTERNAL_DATA"
    elif sources_failed:
        status_code = 1
        status_text = "PARTIAL"
    else:
        status_code = 2
        status_text = "OK"

    return (
        Point("external-context-status")
        .tag("collector", "spaceweather")
        .field("status_code", status_code)
        .field("status_text", status_text)
        .field("sources_ok", sources_ok)
        .field("sources_failed", sources_failed)
        .field("sources_total", sources_total)
        .field("influx_token_configured", 1 if INFLUX_TOKEN else 0)
        .field("version", APP_VERSION)
        .time(utc_now())
    )


def collect_points():
    points = []
    statuses = {}

    collect_source(
        "kp_observed",
        lambda: observed_points(fetch_json(KP_OBSERVED_URL)),
        points,
        statuses,
    )
    collect_source(
        "kp_forecast",
        lambda: forecast_points(fetch_json(KP_FORECAST_URL)),
        points,
        statuses,
    )
    collect_source(
        "solar_plasma",
        lambda: solar_plasma_point(fetch_json(SOLAR_WIND_PLASMA_URL)),
        points,
        statuses,
    )
    collect_source(
        "solar_magnetic",
        lambda: solar_magnetic_point(fetch_json(SOLAR_WIND_MAG_URL)),
        points,
        statuses,
    )
    collect_source(
        "dst",
        lambda: dst_point(fetch_json(DST_URL)),
        points,
        statuses,
    )
    collect_source(
        "goes_protons",
        lambda: proton_point(fetch_json(PROTON_URL)),
        points,
        statuses,
    )
    collect_source(
        "weather",
        collect_weather,
        points,
        statuses,
    )

    return points, statuses


def run_once(write_api):
    points, statuses = collect_points()
    points.append(status_point(statuses))

    write_api.write(
        bucket=INFLUX_BUCKET,
        org=INFLUX_ORG,
        record=points,
    )

    sources_ok = sum(statuses.values())
    sources_failed = len(statuses) - sources_ok
    log(
        "External context update complete -> "
        f"points={len(points)}, "
        f"sources_ok={sources_ok}, "
        f"sources_failed={sources_failed}"
    )


def main():
    log(
        "External context collector starting -> "
        f"version={APP_VERSION}, "
        f"interval={FETCH_INTERVAL_SECONDS}s, "
        f"token_configured={'yes' if INFLUX_TOKEN else 'no'}, "
        f"weather_location_mode={WEATHER_LOCATION_MODE}"
    )

    if not INFLUX_TOKEN:
        raise RuntimeError(
            "INFLUX_TOKEN is required to write external context to InfluxDB"
        )

    client = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG,
        timeout=10000,
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    try:
        while True:
            try:
                run_once(write_api)
            except Exception as exc:
                log(
                    "External context cycle failed -> "
                    f"{type(exc).__name__}: {exc}"
                )

            time.sleep(FETCH_INTERVAL_SECONDS)
    finally:
        write_api.close()
        client.close()


if __name__ == "__main__":
    main()
