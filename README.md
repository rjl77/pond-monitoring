# Pond Monitoring Project

A collection of projects for monitoring and automating various aspects of a
backyard koi pond, including environmental conditions and potential threats
such as predators.

The project combines Raspberry Pi systems, environmental sensors, Hubitat home
automation, InfluxDB, IP cameras, and computer vision. Some components are
production services running continuously, while others are experiments,
utilities, or works in progress.

## Project Overview

The repository currently contains several related projects:

### Temperature Monitoring

The `temperature/` project is a Raspberry Pi-based environmental monitoring
system that collects water temperature from a DS18B20 1-Wire sensor and writes
readings to InfluxDB.

Air temperature can optionally be obtained from Hubitat or a locally connected
DHT22 sensor. This will probably be updated to allow for different sources
(other sensors, API calls, etc.).

Failed InfluxDB writes are retained in a local journal and
reconciled when the database becomes available again.

An optional Hubitat publisher reads current and rolling 24-hour water
temperature statistics from InfluxDB and publishes them to Hubitat devices
and dashboards.

The application runs as systemd services and includes a `pond-monitor`
administration command for routine management:

```bash
pond-monitor status
pond-monitor version
pond-monitor logs
sudo pond-monitor install
sudo pond-monitor refresh
```

See [`temperature/README.md`](temperature/README.md) for architecture,
installation, configuration, and operational documentation.

### Predator Detection via Computer Vision

The `computer-vision/` project contains machine-learning and computer-vision
work for detecting and alerting on potential pond predators and other wildlife.

It includes model-training and testing tools, object-detection experiments,
video-stream analysis, and supporting utilities. Current work includes custom
object-detection models for animals such as herons and raccoons.

### IP Camera Integration

The `ip-camera/` project contains utilities for integrating consumer IP cameras
with Hubitat and other automation systems.

These include a lightweight TCP listener that can receive connections generated
by camera events and scripts that detect those connections and trigger Hubitat
virtual devices through API calls.

### Water Level Monitoring

(Planned) Monitor pond water level, reporting status and alerting on situations 
requiring attention.