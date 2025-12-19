#!/usr/bin/env python3
"""
Raspberry Pi Sensor > Influx Logger
-----------------------------------
Purpose:
    This script reads temperature data from a DS18B20 (1-Wire) sensor and optionally
    air temperature from a DHT sensor or an external API. It writes data to InfluxDB
    and uses a local journal to buffer readings if Influx is unavailable, for later
    reconciliation.

    It also exposes a dummy TCP health check port (default 9991) for availability 
    monitoring.

    This version also runs each sensor cycle in a separate process in case of "stuck" reads.

Usage:
    - Configure the sensor settings (e.g., DS18B20 sensor path, DHT sensor type and GPIO pin).
    - Update the InfluxDB connection settings (host, port, username, password, and database 
      names).
    - Optionally, enable TEST_MODE to write data to a test database.
    - Run the script on a Raspberry Pi with the required sensors connected.
    - Customize the script further as needed for your environment or additional sensor types.

Dependencies:
    - Python 3
    - InfluxDB Python client
    - A DS18B20 sensor (1-Wire) enabled on your Raspberry Pi
    - (Optional) a DHT temperature/humidity sensor
        - adafruit_dht, board (for DHT sensor)

To-Do:
    - Move all variables to an external configuration file

Note:

    If running as a service, configure the top of the unit file as such:

    [Unit]
    Description=Environmental Sensor Reading Import to InfluxDB
    After=network-online.target
    Wants=network-online.target

    This was added as an additional help, as there have been issues post-reboot where the service starts,
    runs, but does not report.
    
"""

import os
import time
import json
import socket
import threading
import logging
from datetime import datetime, timezone
from multiprocessing import Process, Queue
from queue import Empty as QueueEmpty

from influxdb import InfluxDBClient

try:
    import board
    import adafruit_dht
except ImportError:
    board = None
    adafruit_dht = None

USE_DHT = False  # Toggle
USE_API = True   # Toggle
try:
    import requests
except ImportError:
    requests = None

# ---------------------------
# Configuration
# ---------------------------

# DS18B20 (1-Wire) Sensor Path - update with your sensor ID
DS18B20_PATH = "/sys/bus/w1/devices/28-xxxxxxxxxxx/w1_slave"
DHT_TYPE = adafruit_dht.DHT22 if adafruit_dht is not None else None
DHT_PIN = board.D17 if board is not None else None

API_URL = "http://xx.xx.xx.xx/xyz"

INFLUX_HOST = "xx.xx.xx.xx"      # Replace with your InfluxDB IP or hostname
INFLUX_PORT = 8086               # Replace with your InfluxDB port
INFLUX_USER = "writer"           # InfluxDB username
INFLUX_PASSWORD = "password"     # InfluxDB password

TEST_MODE = False
INFLUX_DB = "pond_data_test" if TEST_MODE else "pond_data"

POLL_INTERVAL = 60
CYCLE_TIMEOUT = max(10, POLL_INTERVAL - 5)  # hard timeout for child cycle
JOURNAL_FILE = "sensor_journal.log"
HEALTH_PORT = 9991  # Change to your desired port

# Circuit breaker (lets systemd restart us if we get stuck repeatedly)
MAX_CONSECUTIVE_CYCLE_FAILURES = 3  # timeouts/kill/failures in a row before exit(1)

# ---------------------------
# Logging Setup
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pond_collector")

# ---------------------------
# TCP Health Check
# ---------------------------
def start_health_check_server(port=HEALTH_PORT):
    def _server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.listen()
            while True:
                try:
                    conn, _ = s.accept()
                    conn.close()
                except Exception:
                    pass

    threading.Thread(target=_server, daemon=True).start()

# ---------------------------
# InfluxDB Connection
# ---------------------------
def get_influx_client():
    client = InfluxDBClient(
        host=INFLUX_HOST,
        port=INFLUX_PORT,
        username=INFLUX_USER,
        password=INFLUX_PASSWORD,
    )
    databases = client.get_list_database()
    if not any(db.get("name") == INFLUX_DB for db in databases):
        client.create_database(INFLUX_DB)
    client.switch_database(INFLUX_DB)
    client.ping()
    return client

def safe_get_influx_client(retries=5, delay=5):
    last_err = None
    for i in range(retries):
        try:
            return get_influx_client()
        except Exception as e:
            last_err = e
            log.error(f"InfluxDB connection attempt {i+1} failed: {e}")
            time.sleep(delay)
    raise RuntimeError(f"Failed to initialize InfluxDB client after {retries} attempts: {last_err}")

# ---------------------------
# Journal Functions
# ---------------------------
def append_to_journal(points):
    """
    Accepts either a single dict point or a list of dict points.
    Writes ONE dict per line.
    """
    try:
        if points is None:
            return
        if isinstance(points, dict):
            points = [points]
        if not isinstance(points, list):
            raise TypeError(f"journal points must be dict or list[dict], got {type(points)}")

        with open(JOURNAL_FILE, "a") as f:
            for p in points:
                if isinstance(p, dict):
                    f.write(json.dumps(p) + "\n")
                else:
                    log.warning(f"Skipping non-dict journal entry: {type(p)}")
        log.info("📓 Appended data to journal.")
    except Exception as e:
        log.error(f"Failed to write to journal: {e}")

def flush_journal(client):
    """
    Reads journal file and writes points to Influx.
    Supports historical buggy lines where a JSON list was written on one line.
    """
    if not os.path.exists(JOURNAL_FILE):
        return

    try:
        with open(JOURNAL_FILE, "r") as f:
            lines = f.readlines()

        points = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)

            if isinstance(item, dict):
                points.append(item)
            elif isinstance(item, list):
                # Old bug: list of points on one line
                points.extend([x for x in item if isinstance(x, dict)])
            else:
                log.warning(f"Skipping unknown journal item type: {type(item)}")

        if points:
            result = client.write_points(points)
            log.info(f"✅ Flushed {len(points)} points from journal: {result}")
            open(JOURNAL_FILE, "w").close()
    except Exception as e:
        log.error(f"Error flushing journal: {e}")

# ---------------------------
# Sensor Readers
# ---------------------------
def read_ds18b20():
    try:
        with open(DS18B20_PATH, "r") as file:
            lines = file.readlines()
            if lines and "YES" in lines[0]:
                temp_output = lines[1].split("t=")[-1]
                temp_c = float(temp_output) / 1000.0
                return round(temp_c * 9.0 / 5.0 + 32.0, 2)
    except Exception as e:
        log.warning(f"DS18B20 read error: {e}")
    return None

def read_dht(dht_sensor):
    for _ in range(3):
        try:
            temp_c = dht_sensor.temperature
            humidity = dht_sensor.humidity
            if temp_c is not None and humidity is not None:
                return round(temp_c * 9.0 / 5.0 + 32.0, 2), round(humidity, 2)
        except RuntimeError as e:
            log.warning(f"DHT sensor read retry: {e}")
            time.sleep(2)
        except Exception as e:
            log.error(f"DHT sensor error: {e}")
            break
    return None, None

def read_api_temp():
    try:
        resp = requests.get(API_URL, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        # Hubitat usually returns {"value": "..."}; keep flexible
        val = body["value"] if isinstance(body, dict) and "value" in body else body
        return float(val)
    except Exception as e:
        log.error(f"API read error: {e}")
        return None

# ---------------------------
# Cycle Worker (runs in child process)
# ---------------------------
def cycle_worker(result_q: Queue):
    """
    Runs one full cycle and reports back via result_q.
    This is in a separate process so we can terminate it if it hangs.
    """
    dht_sensor = None
    try:
        client = safe_get_influx_client()

        # Flush journal first
        flush_journal(client)

        current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Sensor reads
        water_temp = read_ds18b20()

        air_temp = None
        humidity = None
        if USE_API:
            air_temp = read_api_temp()
        elif USE_DHT:
            if board is None or adafruit_dht is None or DHT_TYPE is None or DHT_PIN is None:
                log.error("DHT enabled but libraries unavailable.")
            else:
                # Initialize DHT inside the child (avoid cross-process object issues)
                try:
                    dht_sensor = DHT_TYPE(DHT_PIN)
                    air_temp, humidity = read_dht(dht_sensor)
                except Exception as e:
                    log.error(f"❌ Failed to init/read DHT in child: {e}")

        if water_temp is None and air_temp is None:
            log.warning("⚠️ No valid sensor readings; skipping cycle.")
            append_to_journal({
                "measurement": "error",
                "tags": {"reason": "no_data"},
                "time": current_time,
                "fields": {"status": 0},
            })
            result_q.put(("ok", "no_data"))
            return

        points = []
        if water_temp is not None:
            points.append({
                "measurement": "temperature",
                "tags": {"sensor": "water"},
                "time": current_time,
                "fields": {"value": water_temp},
            })
        if air_temp is not None:
            points.append({
                "measurement": "temperature",
                "tags": {"sensor": "air"},
                "time": current_time,
                "fields": {"value": air_temp},
            })
        if humidity is not None:
            points.append({
                "measurement": "humidity",
                "tags": {"sensor": "air"},
                "time": current_time,
                "fields": {"value": humidity},
            })

        try:
            client.write_points(points)
            log.info(f"✅ {current_time} - Data written to InfluxDB.")
            result_q.put(("ok", "written"))
            return
        except Exception as e:
            log.error(f"❌ Write error: {e}. Retrying with new connection...")
            try:
                client = safe_get_influx_client()
                client.write_points(points)
                log.info(f"✅ {current_time} - Data written on retry.")
                result_q.put(("ok", "written_retry"))
                return
            except Exception as conn_error:
                log.error(f"❌ Retry failed: {conn_error}. Appending to journal.")
                append_to_journal(points)
                result_q.put(("ok", "journaled"))
                return

    except Exception as e:
        # Any unexpected exception in the child
        try:
            result_q.put(("error", str(e)))
        except Exception:
            pass
    finally:
        try:
            if dht_sensor:
                dht_sensor.exit()
        except Exception:
            pass

# ---------------------------
# Main Loop
# ---------------------------
def main():
    log.info(f"✅ Running in {'TEST' if TEST_MODE else 'LIVE'} MODE: {INFLUX_DB}")
    start_health_check_server()

    if USE_API and requests is None:
        log.error("USE_API=True but 'requests' is not installed.")
        raise SystemExit(1)

    if USE_DHT and (board is None or adafruit_dht is None or DHT_TYPE is None or DHT_PIN is None):
        log.error("USE_DHT=True but DHT libraries are not installed.")
        raise SystemExit(1)

    # Basic sanity checks
    if not os.path.exists(DS18B20_PATH):
        log.warning(f"⚠️ DS18B20 path not found: {DS18B20_PATH}")
    if not USE_DHT and not USE_API:
        log.warning("⚠️ No air temperature source enabled.")
    if not os.path.exists(DS18B20_PATH) and not USE_DHT and not USE_API:
        log.error("❌ No data sources available. Exiting.")
        raise SystemExit(1)

    log.info("📡 Starting sensor logging loop...")

    consecutive_failures = 0

    while True:
        q = Queue()
        p = Process(target=cycle_worker, args=(q,), daemon=True)
        p.start()

        p.join(timeout=CYCLE_TIMEOUT)

        if p.is_alive():
            # Hard kill hung cycle
            log.error("❌ Sensor cycle timed out (process still alive). Terminating...")
            p.terminate()
            p.join(timeout=5)
            if p.is_alive():
                log.error("💀 Cycle process refused to terminate. Killing...")
                p.kill()
                p.join(timeout=5)

            consecutive_failures += 1
            log.error(f"❌ Cycle killed due to timeout. Consecutive failures: {consecutive_failures}")
        else:
            # Process exited; check result
            try:
                status, detail = q.get_nowait()
                if status == "ok":
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    log.error(f"❌ Cycle reported error: {detail}. Consecutive failures: {consecutive_failures}")
            except QueueEmpty:
                # No result; treat as failure but not catastrophic
                consecutive_failures += 1
                log.error(f"❌ Cycle exited without reporting. Consecutive failures: {consecutive_failures}")

        if consecutive_failures >= MAX_CONSECUTIVE_CYCLE_FAILURES:
            log.error("💥 Too many consecutive cycle failures/timeouts. Exiting for systemd restart.")
            raise SystemExit(1)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()

