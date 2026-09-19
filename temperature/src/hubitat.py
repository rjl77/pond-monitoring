#!/usr/bin/env python3

import logging
import time
from datetime import datetime

from pond.config import get_bool, get_int, load_env, require
from pond.hubitat_api import send_device_command
from pond.influx import get_water_stats_24h


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pond_hubitat")

PUBLISH_INTERVAL = 900


def publish():
    """Publish current and rolling 24-hour water statistics to Hubitat."""

    stats = get_water_stats_24h()

    current = round(stats["current"])
    high = round(stats["maximum"])
    low = round(stats["minimum"])

    updated = datetime.now().strftime("%-m/%-d/%Y\n%-H:%M")

    send_device_command(
        require("HUBITAT_CURRENT_DEVICE_ID"),
        "setTemperature",
        current,
    )

    send_device_command(
        require("HUBITAT_HIGH_DEVICE_ID"),
        "setTemperature",
        high,
    )

    send_device_command(
        require("HUBITAT_LOW_DEVICE_ID"),
        "setTemperature",
        low,
    )

    send_device_command(
        require("HUBITAT_UPDATED_DEVICE_ID"),
        "setVariable",
        updated,
    )

    log.info(
        "Published to Hubitat: current=%d F, high=%d F, low=%d F",
        current,
        high,
        low,
    )


def main():
    load_env()

    if not get_bool("HUBITAT_PUBLISH_ENABLED", True):
        log.info("Hubitat publishing is disabled.")
        return

    interval = get_int(
        "HUBITAT_PUBLISH_INTERVAL",
        PUBLISH_INTERVAL,
    )

    log.info(
        "Starting Hubitat publisher; interval=%d seconds.",
        interval,
    )

    while True:
        try:
            publish()
        except Exception:
            log.exception("Hubitat publishing cycle failed.")

        time.sleep(interval)


if __name__ == "__main__":
    main()
