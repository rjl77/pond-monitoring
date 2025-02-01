#!/usr/bin/env python3
"""
Cacti Temperature Charting Script

This script reads air and water temperatures from 1-Wire sensors on a Raspberry Pi,
converts the readings to Fahrenheit, and prints the values along with a warning threshold.
This output can be used for charting via Cacti (for example).

Before deploying, update these placeholders:
  - AIR_SENSOR_ID: The hardware address for your air temperature sensor.
  - WATER_SENSOR_ID: The hardware address for your water temperature sensor.

Configuration:
  - POLLING_INTERVAL: The time (in seconds) between sensor polls. Defaults to 60 seconds.
  
Notes:
  - Requires Python 3.9+.
  - Loads the 1-Wire kernel modules.
"""

import os
import glob
import time
from datetime import datetime

# Load kernel modules for the 1-Wire interface
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

# Base directory where sensor devices are located
base_dir = '/sys/bus/w1/devices/'

# TODO: Replace with your actual sensor hardware addresses
AIR_SENSOR_ID = '28-XXXXXXXXXXXX'    # e.g., for air temperature sensor
WATER_SENSOR_ID = '28-YYYYYYYYYYYY'  # e.g., for water temperature sensor

# Locate the sensor directories
device_folder_air = glob.glob(base_dir + AIR_SENSOR_ID)[0]
device_folder_water = glob.glob(base_dir + WATER_SENSOR_ID)[0]
device_file_air = device_folder_air + '/w1_slave'
device_file_water = device_folder_water + '/w1_slave'

def air_temp_raw():
    """Read raw data from the air temperature sensor."""
    with open(device_file_air, 'r') as f:
        lines = f.readlines()
    return lines

def air_temp():
    """
    Parse the air sensor data and return the temperature in Fahrenheit (as a string
    formatted to two decimal places).
    """
    lines = air_temp_raw()
    # Wait until sensor output is valid
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = air_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        a_temp_string = lines[1][equals_pos + 2:]
        a_temp_c = float(a_temp_string) / 1000.0
        a_temp_f = a_temp_c * 9.0 / 5.0 + 32.0
        return f"{round(a_temp_f, 2):.2f}"
    return "N/A"

def water_temp_raw():
    """Read raw data from the water temperature sensor."""
    with open(device_file_water, 'r') as f:
        lines = f.readlines()
    return lines

def water_temp():
    """
    Parse the water sensor data and return the temperature in Fahrenheit (as a string
    formatted to two decimal places).
    """
    lines = water_temp_raw()
    # Wait until sensor output is valid
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = water_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        w_temp_string = lines[1][equals_pos + 2:]
        w_temp_c = float(w_temp_string) / 1000.0
        w_temp_f = w_temp_c * 9.0 / 5.0 + 32.0
        return f"{round(w_temp_f, 2):.2f}"
    return "N/A"

# Configurable polling interval (in seconds)
POLLING_INTERVAL = 60  # Default: 60 seconds

# Get the current date/time for logging purposes (if needed)
now = datetime.now()

# Main loop: Print temperatures once per polling interval.
# For Cacti, this output can be captured and charted.
while True:
    # Print the air and water temperatures.
    # "warn:50.00" is included as a static warning threshold (modify as needed).
    print('air:' + air_temp(), 'water:' + water_temp(), 'warn:50.00')
    
    # For debugging, you might uncomment the following to run only once:
    # break

    time.sleep(POLLING_INTERVAL)
