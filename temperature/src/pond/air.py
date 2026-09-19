import time

from pond.config import get, get_int, require
from pond.hubitat_api import get_device_attribute


def read_air_temperature():
    """
    Return the configured air temperature in Fahrenheit.

    Returns None when AIR_SOURCE=none.
    """

    source = get("AIR_SOURCE", "none").strip().lower()

    if source == "none":
        return None

    if source == "hubitat":
        device_id = require("HUBITAT_AIR_DEVICE_ID")
        value = get_device_attribute(device_id, "temperature")

        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Invalid air temperature returned by Hubitat: {value!r}"
            ) from exc

    if source == "dht":
        return _read_dht_temperature()

    raise RuntimeError(f"Unsupported AIR_SOURCE: {source}")


def _read_dht_temperature(retries=3, retry_delay=2):
    """
    Read a DHT22 and return temperature in Fahrenheit.

    DHT/Board libraries are imported only when this source is used.
    """

    try:
        import board
        import adafruit_dht
    except ImportError as exc:
        raise RuntimeError(
            "DHT support requires Adafruit Blinka and "
            "adafruit-circuitpython-dht"
        ) from exc

    gpio = get_int("DHT_GPIO", 17)

    try:
        pin = getattr(board, f"D{gpio}")
    except AttributeError as exc:
        raise RuntimeError(
            f"Unsupported DHT GPIO: {gpio}"
        ) from exc

    sensor = adafruit_dht.DHT22(pin)

    try:
        last_error = None

        for _ in range(retries):
            try:
                temp_c = sensor.temperature

                if temp_c is not None:
                    return round(
                        temp_c * 9.0 / 5.0 + 32.0,
                        2,
                    )

            except RuntimeError as exc:
                last_error = exc
                time.sleep(retry_delay)

        if last_error is not None:
            raise RuntimeError(
                f"DHT22 read failed after {retries} attempts: "
                f"{last_error}"
            )

        raise RuntimeError(
            f"DHT22 returned no temperature after {retries} attempts"
        )

    finally:
        try:
            sensor.exit()
        except Exception:
            pass
