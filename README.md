# Pond Monitoring Project

Scripts (mostly Python, so far) to monitor various aspects of a backyard koi pond - environmental conditions, including temperature, water level, and potential threats (e.g., predators). Nothing terribly fancy or intelligent, just some messing around with a mixture of Raspberry Pi, sensor devices, a Hubitat home automation hub, IP cameras and computer vision.

## Project Overview

The project consists of several components:

- **Temperature Monitoring:**  
  The `temperature/` subfolder contains three scripts:
  - **Hubitat Temperature Monitor:**  
    Polls a water temperature sensor, calculates current, high, and low temperatures over a rolling 24-hour window, and sends the data to a Hubitat home automation hub via API calls.
  - **Cacti Temperature Collection Script:**  
    Reads air and water temperatures from 1-Wire sensors and prints the values (formatted for charting via Cacti or a similar platform).
  - **InfluxDB Temperature Collection Script:**  
    Reads air and water temperatures from 1-Wire sensors and/or DHT sensors and sends them to an InfluxDB server as time series data. Update: DHT sensors can be flaky, so I added an option to retrieve air temperature via API call.    

- **Predator Detection via Computer Vision:**  
  (Coming soon) Scripts that use machine learning and computer vision to identity & alert for potential predators (focussing on Herons for now): training models/weights, analyzing video feeds, testing tools, etc. 

- **IP Camera:**  
  Some simple scripts written to work with consumer IP cameras to trigger Hubitat API calls when motion is detected.

  The `ip-camera/` subfolder contains two scripts:
  - **Dummy TCP Server:**  
    A simple Python script, intended to be run as a service, that creates a basic TCP listener. Useful for consumer IP cameras who can connect to other devices (such as SMTP or FTP) when motion is detected. This works in conjunction with:
  - **Hubitat Motion Trigger**
    A bash script, also intended to be run as a service, that monitors when SYN packets are sent to a specific port (via `tcpdump`), and then sends an API call to a Hubitat virtual device (such as a Virtual Switch or Motion Sensor). Can manage multiple source devices and Hubitat virtual devices. Can obviously be adapted for whatever target. 

- **Water Level Monitoring:**  
  (Planned) Future scripts to monitor the water level in the pond.



