#!/usr/bin/env python3
"""
Raspberry Pi Sensor > Influx Logger
-----------------------------------
Purpose:
    This script reads temperature data from a DS18B20 (1-Wire) sensor and both temperature and humidity data from a DHT sensor (e.g., DHT22).
    It writes the data as time-series points to an InfluxDB instance. This data can then be visualized using tools such as Grafana.

Usage:
    - Configure the sensor settings (e.g., DS18B20 sensor path, DHT sensor type and GPIO pin).
    - Update the InfluxDB connection settings (host, port, username, password, and database names).
    - Optionally, enable TEST_MODE to write data to a test database.
    - Run the script on a Raspberry Pi with the required sensors connected.
    - Customize the script further as needed for your environment or additional sensor types.

Dependencies:
    - Python 3
    - adafruit_dht, board (for DHT sensor)
    - InfluxDB Python client
    - A DS18B20 sensor (1-Wire) enabled on your Raspberry Pi

Future:
    - Add journal + reconcile feature for recording readings if the system is still running, but network is down. It's happened...
"""

import os
import time
import board
import adafruit_dht
from datetime import datetime
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

# TEST MODE: If enabled, data will be written to a test database
TEST_MODE = False  # Set to True to use a test database

# InfluxDB Connection Configuration
INFLUX_HOST = "xx.xx.xx.xx"      # Replace with your InfluxDB IP or hostname
INFLUX_PORT = 8086              # Replace with your InfluxDB port
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

# ---------------------------
# Initialize Sensors
# ---------------------------
if USE_DHT:
    dht_sensor = DHT_TYPE(DHT_PIN)

# ---------------------------
# Setup InfluxDB Connection
# ---------------------------
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

# ---------------------------
# Main Data Collection Loop
# ---------------------------
def main():
    print(f"📡 Starting sensor logging... Writing to database: {INFLUX_DB}")
    
    try:
        while True:
            current_time = datetime.utcnow().isoformat() + "Z"

            # Read sensor values
            water_temp = read_ds18b20()
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
                if json_body:
                    client.write_points(json_body)
                    print(f"✅ {current_time} - Data written: {json_body}")
                else:
                    print(f"⚠️ {current_time} - No valid sensor data to write.")
            except Exception as e:
                print(f"❌ Error writing to InfluxDB: {e}")

            # Wait for the next polling interval
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user.")
    finally:
        if USE_DHT:
            dht_sensor.exit()  # Release DHT sensor resources properly

if __name__ == "__main__":
    main()
