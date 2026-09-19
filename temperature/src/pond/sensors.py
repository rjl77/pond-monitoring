import time
from pathlib import Path


W1_BASE_PATH = Path("/sys/bus/w1/devices")


def water_sensor_path(sensor_id):
    return W1_BASE_PATH / sensor_id / "w1_slave"


def read_water_temperature(sensor_id, retries=3, retry_delay=0.2):
    """
    Read a DS18B20 sensor and return temperature in Fahrenheit.

    Raises RuntimeError if the sensor cannot produce a valid reading.
    """

    path = water_sensor_path(sensor_id)

    if not path.is_file():
        raise RuntimeError(f"DS18B20 sensor not found: {path}")

    for attempt in range(1, retries + 1):
        try:
            lines = path.read_text().splitlines()
        except OSError as exc:
            if attempt == retries:
                raise RuntimeError(
                    f"Unable to read DS18B20 sensor {sensor_id}: {exc}"
                ) from exc

            time.sleep(retry_delay)
            continue

        if len(lines) >= 2 and lines[0].strip().endswith("YES"):
            marker = "t="
            position = lines[1].find(marker)

            if position != -1:
                try:
                    celsius = float(lines[1][position + len(marker):]) / 1000.0
                except ValueError as exc:
                    raise RuntimeError(
                        f"Invalid DS18B20 temperature from {sensor_id}"
                    ) from exc

                fahrenheit = celsius * 9.0 / 5.0 + 32.0
                return round(fahrenheit, 2)

        if attempt < retries:
            time.sleep(retry_delay)

    raise RuntimeError(
        f"DS18B20 sensor {sensor_id} did not return a valid reading"
    )
