#!/usr/bin/env python3

import logging
import socket
import threading
import time
from datetime import datetime, timezone
from multiprocessing import Process, Queue
from queue import Empty as QueueEmpty

from pond.air import read_air_temperature
from pond.config import get_int, load_env, require
from pond.influx import connect
from pond.journal import append as journal_append
from pond.journal import flush as journal_flush
from pond.sensors import read_water_temperature


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pond_collector")

MAX_CONSECUTIVE_CYCLE_FAILURES = 3


def start_health_server(port):
    """Start the lightweight TCP health-check listener."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind(("0.0.0.0", port))
        sock.listen()
    except Exception:
        sock.close()
        raise

    def server():
        with sock:
            while True:
                try:
                    conn, _ = sock.accept()
                    conn.close()
                except Exception:
                    log.exception("Health-check listener failed.")
                    return

    threading.Thread(
        target=server,
        name="health-check",
        daemon=True,
    ).start()

def make_points(water_temp, air_temp, timestamp):
    """Build InfluxDB measurement points from available readings."""

    points = []

    if water_temp is not None:
        points.append(
            {
                "measurement": "temperature",
                "tags": {"sensor": "water"},
                "time": timestamp,
                "fields": {"value": water_temp},
            }
        )

    if air_temp is not None:
        points.append(
            {
                "measurement": "temperature",
                "tags": {"sensor": "air"},
                "time": timestamp,
                "fields": {"value": air_temp},
            }
        )

    return points


def cycle_worker(result_q):
    """Perform one complete collection/write cycle."""

    timestamp = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    water_temp = None
    air_temp = None

    try:
        sensor_id = require("WATER_SENSOR_ID")
        water_temp = read_water_temperature(sensor_id)
    except Exception as exc:
        log.error("Water temperature read failed: %s", exc)

    try:
        air_temp = read_air_temperature()
    except Exception as exc:
        log.error("Air temperature read failed: %s", exc)

    if water_temp is None and air_temp is None:
        log.warning("No valid sensor readings; skipping cycle.")

        journal_append(
            {
                "measurement": "error",
                "tags": {"reason": "no_data"},
                "time": timestamp,
                "fields": {"status": 0},
            }
        )

        result_q.put(("ok", "no_data"))
        return

    points = make_points(
        water_temp=water_temp,
        air_temp=air_temp,
        timestamp=timestamp,
    )

    client = None

    try:
        client = connect(retries=2, delay=2)
    except Exception as exc:
        log.error(
            "InfluxDB unavailable: %s. Journaling points.",
            exc,
        )
        journal_append(points)
        result_q.put(("ok", "journaled_no_client"))
        return

    try:
        try:
            journal_flush(client)
        except Exception as exc:
            log.error(
                "Unable to flush offline journal (non-fatal): %s",
                exc,
            )

        try:
            result = client.write_points(points)

            if not result:
                raise RuntimeError(
                    "InfluxDB did not confirm write"
                )

            log.info(
                "%s - Data written to InfluxDB.",
                timestamp,
            )

            result_q.put(("ok", "written"))

        except Exception as exc:
            log.error(
                "InfluxDB write failed: %s. Journaling points.",
                exc,
            )
            journal_append(points)
            result_q.put(("ok", "journaled_write_fail"))

    finally:
        try:
            client.close()
        except Exception:
            pass


def main():
    load_env()

    poll_interval = get_int("POLL_INTERVAL", 60)
    health_port = get_int("HEALTH_PORT", 9991)
    cycle_timeout = max(10, poll_interval - 5)

    sensor_id = require("WATER_SENSOR_ID")

    log.info("Starting Pond Collector.")
    log.info("Water sensor: %s", sensor_id)
    log.info("Poll interval: %d seconds", poll_interval)

    start_health_server(health_port)

    consecutive_failures = 0

    while True:
        cycle_started = time.monotonic()

        result_q = Queue()
        process = Process(
            target=cycle_worker,
            args=(result_q,),
            daemon=True,
        )
        process.start()

        process.join(timeout=cycle_timeout)

        if process.is_alive():
            log.error(
                "Sensor cycle timed out. Terminating child process."
            )

            process.terminate()
            process.join(timeout=5)

            if process.is_alive():
                log.error(
                    "Cycle process refused to terminate. Killing it."
                )
                process.kill()
                process.join(timeout=5)

            consecutive_failures += 1

            log.error(
                "Cycle killed due to timeout. "
                "Consecutive failures: %d",
                consecutive_failures,
            )

        else:
            try:
                status, detail = result_q.get_nowait()

                if status == "ok":
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    log.error(
                        "Cycle reported error: %s. "
                        "Consecutive failures: %d",
                        detail,
                        consecutive_failures,
                    )

            except QueueEmpty:
                consecutive_failures += 1
                log.error(
                    "Cycle exited without reporting. "
                    "Consecutive failures: %d",
                    consecutive_failures,
                )

        if (
            consecutive_failures
            >= MAX_CONSECUTIVE_CYCLE_FAILURES
        ):
            log.error(
                "Too many consecutive cycle failures. "
                "Exiting for systemd restart."
            )
            raise SystemExit(1)

        # Maintain approximately poll_interval seconds from
        # the start of one cycle to the start of the next.
        elapsed = time.monotonic() - cycle_started
        sleep_time = max(0, poll_interval - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
