import time

from influxdb import InfluxDBClient

from pond.config import get_int, require


def create_client():
    """Create an InfluxDB client using the configured connection settings."""

    return InfluxDBClient(
        host=require("INFLUX_HOST"),
        port=get_int("INFLUX_PORT", 8086),
        username=require("INFLUX_USER"),
        password=require("INFLUX_PASSWORD"),
        database=require("INFLUX_DATABASE"),
    )


def connect(retries=5, delay=5):
    """
    Connect to InfluxDB and verify the configured database exists.

    Returns a ready client. Raises RuntimeError after all retries fail.
    """

    last_error = None

    for attempt in range(1, retries + 1):
        client = None

        try:
            client = create_client()

            databases = client.get_list_database()
            database = require("INFLUX_DATABASE")

            if not any(db.get("name") == database for db in databases):
                client.create_database(database)

            client.switch_database(database)
            client.ping()

            return client

        except Exception as exc:
            last_error = exc

            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

            if attempt < retries:
                time.sleep(delay)

    raise RuntimeError(
        f"Failed to connect to InfluxDB after {retries} attempts: {last_error}"
    )


def ping():
    """Verify that the configured InfluxDB server is reachable."""

    client = create_client()

    try:
        client.ping()
    finally:
        client.close()


def write_points(client, points):
    """Write measurement points to InfluxDB."""

    return client.write_points(points)


def get_temperature_stats_24h(sensor):
    """
    Return the latest, minimum, and maximum temperatures
    recorded for a sensor during the previous 24 hours.
    """

    if sensor not in ("water", "air"):
        raise ValueError(f"Unsupported temperature sensor: {sensor}")

    client = create_client()

    try:
        latest_result = client.query(
            "SELECT LAST(value) AS value "
            "FROM temperature "
            f"WHERE sensor='{sensor}' AND time >= now() - 24h"
        )

        stats_result = client.query(
            "SELECT MIN(value) AS minimum, MAX(value) AS maximum "
            "FROM temperature "
            f"WHERE sensor='{sensor}' AND time >= now() - 24h"
        )

        latest = next(latest_result.get_points(), None)
        stats = next(stats_result.get_points(), None)

        if latest is None or stats is None:
            raise RuntimeError(
                f"InfluxDB contains no {sensor}-temperature data "
                "for the last 24 hours"
            )

        return {
            "current": latest["value"],
            "current_time": latest["time"],
            "minimum": stats["minimum"],
            "maximum": stats["maximum"],
        }

    finally:
        client.close()


def get_water_stats_24h():
    """Return 24-hour water-temperature statistics."""

    return get_temperature_stats_24h("water")
