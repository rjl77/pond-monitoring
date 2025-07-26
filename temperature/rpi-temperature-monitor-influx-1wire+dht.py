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
"""

import os
import time
import json
import socket
import threading
import logging
from datetime import datetime, timezone
from influxdb import InfluxDBClient

# Optional imports, based on configuration
import board
import adafruit_dht
if os.environ.get("USE_API", "true").lower() == "true":
    import requests

# ---------------------------
# Configuration
# ---------------------------

# DS18B20 (1-Wire) Sensor Path - update with your sensor ID
DS18B20_PATH = "/sys/bus/w1/devices/28-xxxxxxxxxxx/w1_slave"

USE_DHT = False # Toggle 
DHT_TYPE = adafruit_dht.DHT22
DHT_PIN = board.D17

USE_API = True  # Toggle
API_URL = "http://xx.xx.xx.xx/xyz"

INFLUX_HOST = "xx.xx.xx.xx"      # Replace with your InfluxDB IP or hostname
INFLUX_PORT = XXXX              # Replace with your InfluxDB port
INFLUX_USER = "writer"          # InfluxDB username
INFLUX_PASSWORD = "password"    # InfluxDB password

TEST_MODE = False
INFLUX_DB = "pond_data_test" if TEST_MODE else "pond_data"

POLL_INTERVAL = 60
JOURNAL_FILE = "sensor_journal.log"
HEALTH_PORT = 9991 # Change to your desired port

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
            s.bind(('0.0.0.0', port))  # 127.0.0.1 if monitoring locally
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
    if not any(db["name"] == INFLUX_DB for db in databases):
        client.create_database(INFLUX_DB)
    client.switch_database(INFLUX_DB)
    client.ping()
    return client

def safe_get_influx_client(retries=5, delay=5):
    for i in range(retries):
        try:
            return get_influx_client()
        except Exception as e:
            log.error(f"InfluxDB connection attempt {i+1} failed: {e}")
            time.sleep(delay)
    raise RuntimeError("Failed to initialize InfluxDB client after multiple attempts")

# ---------------------------
# Journal Functions
# ---------------------------
def append_to_journal(data):
    try:
        with open(JOURNAL_FILE, "a") as f:
            f.write(json.dumps(data) + "\n")
        log.info("📓 Appended data to journal.")
    except Exception as e:
        log.error(f"Failed to write to journal: {e}")

def flush_journal(client):
    if not os.path.exists(JOURNAL_FILE):
        return
    try:
        with open(JOURNAL_FILE, "r") as f:
            lines = f.readlines()
        flat_points = [item for line in lines if (item := json.loads(line.strip()))]
        if flat_points:
            result = client.write_points(flat_points)
            log.info(f"✅ Flushed {len(flat_points)} points from journal: {result}")
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
            if "YES" in lines[0]:
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
        return float(resp.json()["value"])
    except Exception as e:
        log.error(f"API read error: {e}")
        return None

# ---------------------------
# Main Loop
# ---------------------------
def main():
    global USE_DHT

    log.info(f"✅ Running in {'TEST' if TEST_MODE else 'LIVE'} MODE: {INFLUX_DB}")
    start_health_check_server()
    client = safe_get_influx_client()

    dht_sensor = None
    if USE_DHT:
        try:
            dht_sensor = DHT_TYPE(DHT_PIN)
            log.info("✅ DHT sensor initialized.")
        except Exception as e:
            log.error(f"❌ Failed to initialize DHT sensor: {e}")
            USE_DHT = False

    # Sensor availability checks
    if not os.path.exists(DS18B20_PATH):
        log.warning(f"⚠️ DS18B20 path not found: {DS18B20_PATH}")
    if not USE_DHT and not USE_API:
        log.warning("⚠️ No air temperature source enabled.")
    if not os.path.exists(DS18B20_PATH) and not USE_DHT and not USE_API:
        log.error("❌ No data sources available. Exiting.")
        return

    log.info("📡 Starting sensor logging loop...")

    try:
        while True:
            current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            flush_journal(client)

            water_temp = read_ds18b20()
            air_temp, humidity = (read_api_temp(), None) if USE_API else read_dht(dht_sensor)

            if water_temp is None and air_temp is None:
                log.warning("⚠️ No valid sensor readings; skipping cycle.")
                time.sleep(POLL_INTERVAL)
                continue

            json_body = []
            if water_temp is not None:
                json_body.append({"measurement": "temperature", "tags": {"sensor": "water"}, "t
ime": current_time, "fields": {"value": water_temp}})
            if air_temp is not None:
                json_body.append({"measurement": "temperature", "tags": {"sensor": "air"}, "tim
e": current_time, "fields": {"value": air_temp}})
            if humidity is not None:
                json_body.append({"measurement": "humidity", "tags": {"sensor": "air"}, "time":
 current_time, "fields": {"value": humidity}})

            try:
                client.write_points(json_body)
                log.info(f"✅ {current_time} - Data written to InfluxDB.")
            except Exception as e:
                log.error(f"❌ Write error: {e}. Retrying...")
                try:
                    client = safe_get_influx_client()
                    client.write_points(json_body)
                    log.info(f"✅ {current_time} - Data written on retry.")
                except Exception as conn_error:
                    log.error(f"❌ Retry failed: {conn_error}. Appending to journal.")
                    append_to_journal(json_body)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info("🛑 Stopped by user.")
    finally:
        if dht_sensor:
            dht_sensor.exit()

if __name__ == "__main__":
    main()
