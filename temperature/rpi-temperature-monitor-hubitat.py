#!/usr/bin/env python3
"""
Simple RPi Temperature Monitor Script for Hubitat

This script polls a temperature sensor via the 1-Wire interface,
calculates the current temperature along with the highest and lowest
temperatures over a rolling 24-hour window, and sends these values to a
Hubitat home automation hub via API calls.

Before deploying, populate these placeholders with the appropriate values:
  - SENSOR_ID: The hardware address for your temperature sensor.
  - API_BASE_URL: The base URL for your Habitat hub's API.
  - ACCESS_TOKEN: Your API access token.
  - CURRENT_DEVICE_ID, HIGHEST_DEVICE_ID, LOWEST_DEVICE_ID, TIMESTAMP_DEVICE_ID:
    The device IDs for the virtual sensors on the Habitat hub.

Notes:
 - Python 3.9.2
 - Can be configured as a service
    
"""

import os
import glob
import time
import subprocess
from datetime import datetime
import urllib.parse

# Load kernel modules for the 1-Wire interface
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

# Base directory where sensor devices are located
base_dir = '/sys/bus/w1/devices/'

# TODO: Replace with your actual sensor hardware address (e.g., '28-XXXXXXXXXXXX')
SENSOR_ID = '28-XXXXXXXXXXXX'
device_folder_water = glob.glob(base_dir + SENSOR_ID)[0]
device_file_water = device_folder_water + '/w1_slave'

def water_temp_raw():
    """Read raw data from the temperature sensor."""
    with open(device_file_water, 'r') as f:
        lines = f.readlines()
    return lines

def water_temp():
    """
    Parse the raw sensor data and return the temperature in Fahrenheit (as an integer).
    The sensor outputs temperature in Celsius, which is converted to Fahrenheit.
    """
    lines = water_temp_raw()
    # Wait until the sensor output is valid
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = water_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos + 2:]
        temp_c = float(temp_string) / 1000.0
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        return int(round(temp_f, 0))
    return None

# Initialize current, highest, and lowest temperatures using the first sensor reading
current_temperature = water_temp()
highest_temperature = current_temperature
lowest_temperature = current_temperature

# Maintain a history of temperature readings as tuples (temperature, timestamp)
temperature_history = [(current_temperature, time.time())]

while True:
    temperature = water_temp()
    current_timestamp = time.time()

    # Append current temperature to history
    temperature_history.append((temperature, current_timestamp))

    # Remove entries older than 24 hours
    temperature_history = [
        (temp, ts) for temp, ts in temperature_history
        if current_timestamp - ts <= 24 * 60 * 60
    ]

    # Determine highest and lowest temperatures in the past 24 hours
    highest_temperature = max(temp for temp, _ in temperature_history)
    lowest_temperature = min(temp for temp, _ in temperature_history)

    # Format the current timestamp into a date string
    dt = datetime.fromtimestamp(current_timestamp)
    date_str = dt.strftime('%-m/%-d/%Y\n%-H:%M')
    encoded_date_str = urllib.parse.quote(date_str, safe='')

    # TODO: Update these values with your Habitat hub details
    API_BASE_URL = "http://YOUR_HUB_IP/apps/api/9/devices"
    ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
    CURRENT_DEVICE_ID = "CURRENT_DEVICE_ID"
    HIGHEST_DEVICE_ID = "HIGHEST_DEVICE_ID"
    LOWEST_DEVICE_ID = "LOWEST_DEVICE_ID"
    TIMESTAMP_DEVICE_ID = "TIMESTAMP_DEVICE_ID"

    # Construct API URLs for current, highest, and lowest temperatures, and the timestamp
    current_url = f"{API_BASE_URL}/{CURRENT_DEVICE_ID}/setTemperature/{temperature}?access_token={ACCESS_TOKEN}"
    highest_url = f"{API_BASE_URL}/{HIGHEST_DEVICE_ID}/setTemperature/{highest_temperature}?access_token={ACCESS_TOKEN}"
    lowest_url = f"{API_BASE_URL}/{LOWEST_DEVICE_ID}/setTemperature/{lowest_temperature}?access_token={ACCESS_TOKEN}"
    timestamp_url = f"{API_BASE_URL}/{TIMESTAMP_DEVICE_ID}/setVariable/{encoded_date_str}?access_token={ACCESS_TOKEN}"

    # Send API calls using curl
    subprocess.run(f'curl {current_url}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(f'curl {highest_url}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(f'curl {lowest_url}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(f'curl {timestamp_url}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # Output the temperature readings to the console for debugging/logging purposes
    print(f"Current Temperature: {temperature}°F")
    print(f"Highest Temperature (last 24 hours): {highest_temperature}°F")
    print(f"Lowest Temperature (last 24 hours): {lowest_temperature}°F")

    # Wait for 15 minutes before the next reading
    time.sleep(900)
