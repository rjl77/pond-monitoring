#!/usr/bin/env python3
"""
Raspberry Pi Sensor > Influx Logger
-----------------------------------
Purpose:
    This script reads temperature data from a DS18B20 (1-Wire) sensor and both temperature and humidity data from a DHT sensor (e.g., DHT22).
    Alternately, air temperature can be polled via API call.
    It writes the data as time-series points to an InfluxDB instance. This data can then be visualized using tools such as Grafana.

    If the InfluxDB server is unavailable, write JSON-formatted readings to a journal file and attempt to reconcile logged readings when
    connectivity has been restored.

Usage:
    - Configure the sensor settings (e.g., DS18B20 sensor path, DHT sensor type and GPIO pin).
    - Toggle air temperature source - API or DHT sensor.
    - Update the InfluxDB connection settings (host, port, username, password, and database names).
    - Optionally, enable TEST_MODE to write data to a test database.
    - Run the script on a Raspberry Pi with the required sensors connected.
    - Customize the script further as needed for your environment or additional sensor types.

Dependencies:
    - Python 3
    - InfluxDB Python client
    - A DS18B20 sensor (1-Wire) enabled on your Raspberry Pi
    - (Optional) a DHT temperature/humidity sensor
        - adafruit_dht, board (for DHT sensor)
    - (Optional) an API to pull temperature data from a home automation device or website
"""

import os
import time
import board
import adafruit_dht
import json
from datetime import datetime, timezone
from influxdb import InfluxDBClient

# ---------------------------
# Configuration
# ---------------------------

# DS18B20 (1-Wire) Sensor Path - update with your sensor ID
DS18B20_PATH = "/sys/bus/w1/devices/28-xxxxxxxxxxx/w1_slave"

# DHT Sensor Configuration
USE_DHT = True
DHT_TYPE = adafruit_dht.DHT22   # Change to DHT11 if needed
DHT_PIN = board.D17             # GPIO pin where the DHT sensor data pin is connected

# API Configuration
USE_API = True
API_URL = "http://xx.xx.xx.xx/xyz"

if USE_API:
     import requests

# TEST MODE: If enabled, data will be written to a test database
TEST_MODE = False  # Set to True to use a test database

# InfluxDB Connection Configuration
INFLUX_HOST = "xx.xx.xx.xx"      # Replace with your InfluxDB IP or hostname
INFLUX_PORT = XXXX              # Replace with your InfluxDB port
INFLUX_USER = "writer"          # InfluxDB username
INFLUX_PASSWORD = "password"    # InfluxDB password

# Select database based on test mode
if TEST_MODE:
    INFLUX_DB = "pond_data_test"
    print("⚠️ Running in TEST MODE: Writing to pond_data_test")
else:
    INFLUX_DB = "pond_data"
    print("✅ Running in LIVE MODE: Writing to pond_data")

# Polling interval in seconds (how often to read sensors)
POLL_INTERVAL = 60

# Journal configuration: local file to cache sensor data when InfluxDB is unreachable
JOURNAL_FILE = "sensor_journal.log"

# ---------------------------
# Initialize Sensors
# ---------------------------
if USE_DHT:
    dht_sensor = DHT_TYPE(DHT_PIN)

# ---------------------------
# InfluxDB Connection Setup Function
# ---------------------------
def get_influx_client():
    client = InfluxDBClient(
        host=INFLUX_HOST,
        port=INFLUX_PORT,
        username=INFLUX_USER,
        password=INFLUX_PASSWORD,
    )
    # Create the database if it doesn't exist
    databases = client.get_list_database()
    if not any(db["name"] == INFLUX_DB for db in databases):
        client.create_database(INFLUX_DB)
    client.switch_database(INFLUX_DB)
    
    # Test the connection with a ping
    try:
        ping_response = client.ping()
        if ping_response:
            print("✅ InfluxDB ping successful.")
        else:
            raise Exception("Empty response from InfluxDB ping.")
    except Exception as e:
        print(f"❌ InfluxDB connection test failed: {e}")
        raise e

    return client

# Initialize the InfluxDB client
client = get_influx_client()

# ---------------------------
# Local Journal Functions
# ---------------------------
def append_to_journal(data):
    """Appends a JSON-encoded sensor reading to the local journal."""
    try:
        with open(JOURNAL_FILE, "a") as f:   # Open the journal file in 'append' mode.
            f.write(json.dumps(data) + "\n")
        print("📓 Sensor reading appended to local journal.")
    except Exception as e:
        print(f"❌ Failed to write to journal: {e}")

def flush_journal():
    """Attempts to write all cached sensor readings from the journal to InfluxDB.
       Clears the journal file upon successful write.
    """
    if not os.path.exists(JOURNAL_FILE):
        print("🔍 Journal file not found.")
        return  # No journal to flush
    try:
        with open(JOURNAL_FILE, "r") as f:
            lines = f.readlines()
        if not lines: # Journal is present but empty
            print("🔍 Journal file is empty.")
            return

        # Parse each line as a JSON object
        cached_data = [json.loads(line.strip()) for line in lines if line.strip()]

        # Flatten the list: combine logged entries prior to import
        flat_points = []
        for entry in cached_data:
            if isinstance(entry, list):
                flat_points.extend(entry)
            else:
                flat_points.append(entry)

        if flat_points:
            result = client.write_points(flat_points)
            print(f"DEBUG: write_points returned: {result}")
            print("✅ Flushed cached sensor readings from journal to InfluxDB.")
            # Clear the journal after a successful flush
            open(JOURNAL_FILE, "w").close()
        else:
            print("🔍 No valid cached data parsed from journal.")
    except Exception as e:
        print(f"❌ Error flushing journal: {e}")

# ---------------------------
# Sensor Reading Functions
# ---------------------------
def read_ds18b20():
    """Reads temperature from the DS18B20 sensor (1-Wire)."""
    try:
        with open(DS18B20_PATH, "r") as file:
            lines = file.readlines()
            if "YES" in lines[0]:  # Check for valid CRC
                temp_output = lines[1].split("t=")[-1]
                temp_c = float(temp_output) / 1000.0
                temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 2)  # Convert to Fahrenheit
                return temp_f
    except FileNotFoundError:
        print("DS18B20 sensor not found! Check wiring or sensor ID.")
    except Exception as e:
        print(f"Error reading DS18B20: {e}")
    return None

def read_dht():
    """Reads temperature and humidity from the DHT sensor with retry logic."""
    if not USE_DHT:
        return None, None

    for _ in range(3):  # Attempt up to 3 retries
        try:
            temp_c = dht_sensor.temperature
            humidity = dht_sensor.humidity

            if temp_c is not None and humidity is not None:
                temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 2)  # Convert to Fahrenheit
                return temp_f, round(humidity, 2)

        except RuntimeError as e:
            print(f"⚠️ DHT sensor read error (retrying): {e}")
            time.sleep(2)  # Delay before retrying
        except Exception as e:
            print(f"❌ DHT sensor error: {e}")
            return None, None  # On critical error, return None

    print("❌ DHT sensor failed after multiple attempts")
    return None, None

def read_api_temp():
    """Fetches air temperature from JSON API via requests."""
    try:
        resp = requests.get(API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        temp = data["value"] # Name of data item
        return float(temp)
    except Exception as e:
        print(f"❌ API read error: {e}")
        return None


# ---------------------------
# Main Data Collection Loop
# ---------------------------
# ---------------------------
# Main Data Collection Loop
# ---------------------------
def main():
    global client  # To allow reinitializing the global client variable
    print(f"📡 Starting sensor logging... Writing to database: {INFLUX_DB}")
    
    try:
        while True:
            current_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            # Attempt to reconcile any journaled readings first
            try:
                flush_journal()
            except Exception as e:
                print(f"❌ Error flushing journal: {e}")

            # Read sensor values
            water_temp = read_ds18b20()
            
            # Read air temp & humidity via API or DHT sensor
            if USE_API:
                air_temp = read_api_temp()
                humidity = None
            else:
                air_temp, humidity = read_dht()

            # If no valid readings, skip this cycle
            if water_temp is None and air_temp is None:
                print("⚠️ No valid sensor readings; skipping this cycle.")
                time.sleep(POLL_INTERVAL)
                continue

            # Prepare data points for InfluxDB
            json_body = []

            if water_temp is not None:
                json_body.append({
                    "measurement": "temperature",
                    "tags": {"sensor": "water"},
                    "time": current_time,
                    "fields": {"value": water_temp}
                })
            
            if air_temp is not None:
                json_body.append({
                    "measurement": "temperature",
                    "tags": {"sensor": "air"},
                    "time": current_time,
                    "fields": {"value": air_temp}
                })
            
            if humidity is not None:
                json_body.append({
                    "measurement": "humidity",
                    "tags": {"sensor": "air"},
                    "time": current_time,
                    "fields": {"value": humidity}
                })

            # Write data to InfluxDB
            try:
                client.write_points(json_body)
                print(f"✅ {current_time} - Data written: {json_body}")
            except Exception as e:
                print(f"❌ Error writing to InfluxDB: {e}")
                # First, attempt to reconnect and re-try the write.
                try:
                    client = get_influx_client()
                    print("🔄 Reconnected to InfluxDB. Retrying write...")
                    client.write_points(json_body)
                    print(f"✅ {current_time} - Data written on retry: {json_body}")
                except Exception as conn_error:
                    print(f"❌ Retry failed: {conn_error}")
                    # If retry still fails, append the current reading to the journal for later back-fill.
                    append_to_journal(json_body)

            # Wait for the next polling interval
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user.")
    finally:
        if USE_DHT:
            dht_sensor.exit()  # Release DHT sensor resources properly

if __name__ == "__main__":
    main()
