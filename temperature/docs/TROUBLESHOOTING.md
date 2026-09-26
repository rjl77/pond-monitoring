# Pond Collector Troubleshooting

This document covers common Pond Collector failure modes and diagnostic steps.

## Start With Service Status

Check all three services:

```bash
systemctl status pond-collector.service pond-hubitat.service pond-network-watchdog.service
```

For a combined chronological view of the service logs:

```bash
pond-collector diag
```

To inspect a specific time window:

```bash
pond-collector diag --since "2026-09-23 19:00" --until "2026-09-23 21:40"
```

For problems following a reboot, restrict the logs to the current boot:

```bash
journalctl -b -u pond-collector.service
journalctl -b -u pond-hubitat.service
journalctl -b -u pond-network-watchdog.service
```

## Collector Will Not Start

Run the installer first:

```bash
sudo pond-collector install
```

The installer validates the configuration, runtime account, 1-Wire setup,
DS18B20 sensor, service installation, and collector health listener.

If the collector still fails, inspect:

```bash
journalctl -u pond-collector.service -n 100 --no-pager
```

Also verify the installed unit:

```bash
systemctl cat pond-collector.service
```

## DS18B20 Not Detected

List 1-Wire devices:

```bash
ls -l /sys/bus/w1/devices/
```

A DS18B20 should appear with an ID beginning with:

```text
28-
```

Check that the 1-Wire overlay is configured:

```bash
grep -E '^[[:space:]]*dtoverlay=w1-gpio([[:space:]]|$)' \
    /boot/firmware/config.txt
```

If the overlay was newly enabled, reboot before troubleshooting further.

Check loaded 1-Wire modules:

```bash
lsmod | grep -E 'w1|wire'
```

If no `28-*` device appears after 1-Wire is enabled, investigate the physical
sensor wiring and connections.

## Configured Sensor ID Is Wrong

Compare the configured ID:

```bash
grep '^WATER_SENSOR_ID=' /opt/pond-collector/config/pond.env
```

with detected sensors:

```bash
ls -1 /sys/bus/w1/devices/28-*
```

If the probe was replaced, update `WATER_SENSOR_ID` and rerun:

```bash
sudo pond-collector install
```

## Test the DS18B20 Directly

Read the sensor:

```bash
cat /sys/bus/w1/devices/28-xxxxxxxxxxxx/w1_slave
```

Replace the example ID with the actual sensor ID.

A healthy response should report:

```text
YES
```

on the CRC/status line and include a `t=` value on the data line.

## InfluxDB Is Unavailable

The collector is designed to tolerate temporary InfluxDB or network outages.

When a reading cannot be written to InfluxDB, it is stored in:

```text
/opt/pond-collector/runtime/sensor_journal.log
```

Check whether a journal exists:

```bash
ls -lh /opt/pond-collector/runtime/sensor_journal.log
```

Inspect recent entries without modifying it:

```bash
tail -20 /opt/pond-collector/runtime/sensor_journal.log
```

When InfluxDB becomes reachable again, the collector attempts to flush queued
records before writing the current reading.

Do not delete the journal merely because InfluxDB is temporarily unavailable.

## Network Problems and Watchdog Diagnostics

The network watchdog monitors LAN connectivity independently of the collector.
It records diagnostic information after repeated connectivity failures and logs
when connectivity recovers.

Check its status and recent logs:

```bash
systemctl status pond-network-watchdog.service
journalctl -u pond-network-watchdog.service -n 100 --no-pager
```

For an incident affecting multiple Pond Collector services, prefer the combined
chronological view:

```bash
pond-collector diag --since "1 hour ago"
```

The watchdog is currently diagnostic only. It does not automatically reconnect
the network interface or reboot the Raspberry Pi. Use its logs to determine the
failure mode before taking recovery action.

## Journal Does Not Flush

First confirm that InfluxDB is reachable again and inspect the collector log:

```bash
journalctl -u pond-collector.service -n 100 --no-pager
```

If the journal contains malformed data, the collector may log a journal error.

Preserve a copy of the journal before manually modifying or deleting it.

## Health Check Fails

The configured health port is normally:

```text
9991
```

Test it locally:

```bash
timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/9991'
echo $?
```

A result of `0` indicates that the collector accepted the TCP connection.

If it fails, check whether the collector is running:

```bash
systemctl status pond-collector.service
```

Then check whether something else owns the configured port:

```bash
sudo ss -ltnp | grep ':9991'
```

The collector treats failure to bind its health port as a startup failure.

## Air Temperature Missing

Check the configured source:

```bash
grep '^AIR_SOURCE=' /opt/pond-collector/config/pond.env
```

Supported values are:

```text
hubitat
dht
none
```

### Hubitat Air Source

If `AIR_SOURCE=hubitat`, inspect collector logs for Maker API errors:

```bash
journalctl -u pond-collector.service -n 100 --no-pager
```

Check network connectivity to the configured Hubitat host.

Do not print or paste the Hubitat access token while troubleshooting.

### DHT Air Source

If `AIR_SOURCE=dht`, verify the optional Python modules:

```bash
python3 -c 'import board, adafruit_dht; print("DHT dependencies OK")'
```

If this fails, the optional Blinka/DHT Python dependencies are not available
to the Python environment used by Pond Collector.

DHT dependencies are intentionally not installed automatically by
`install.sh`.

### No Air Source

If:

```text
AIR_SOURCE=none
```

missing air-temperature readings are expected.

## Hubitat Publisher Problems

Check whether publishing is enabled:

```bash
grep '^HUBITAT_PUBLISH_ENABLED=' /opt/pond-collector/config/pond.env
```

If enabled, check the service:

```bash
systemctl status pond-hubitat.service
```

and its logs:

```bash
journalctl -u pond-hubitat.service -n 100 --no-pager
```

The publisher depends on InfluxDB for current and rolling 24-hour water
temperature statistics.

A Hubitat publishing failure does not stop the collector.

## Hubitat High or Low Looks Wrong

The Hubitat high and low are rolling 24-hour values queried from InfluxDB.

They are not maintained only in the publisher's memory, so restarting the
publisher should not reset them.

Check the underlying InfluxDB water-temperature data for the previous
24 hours if the published values appear incorrect.

## Configuration Error

Run:

```bash
sudo pond-collector install
```

The installer validates required configuration fields and numeric values before
reinstalling the services.

The local configuration file is:

```text
/opt/pond-collector/config/pond.env
```

Do not replace it with `pond.env.example` unless intentionally rebuilding the
machine-specific configuration.

## Service Restart Loop

Check:

```bash
systemctl status pond-collector.service
journalctl -u pond-collector.service -n 100 --no-pager
```

For a collector timeout or restart loop, use the combined diagnostic view for
the affected time window:

```bash
pond-collector diag --since "2026-09-23 19:00" --until "2026-09-23 21:40"
```

The collector logs diagnostic `Cycle stage:` messages around operations that
can block. If a cycle reaches a stage but does not log its corresponding
completion message before the hard timeout, that identifies the operation that
was still in progress when the cycle was terminated.

The collector uses `Restart=on-failure`.

Repeated child-process failures can intentionally cause the collector process
to exit so systemd can restart it.

Investigate the underlying sensor, configuration, network, or database error
rather than disabling the restart behavior.

## After Editing Code

Check Python syntax where appropriate, then deploy through:

```bash
sudo pond-collector refresh
```

This updates the production checkout, runs the installer, restarts the services,
and verifies the deployment.

## Raspberry Pi Becomes Very Slow or SSH Stops Responding

Check memory, swap, CPU wait, and disk activity:

```bash
free -h
vmstat 1 10
```

This Raspberry Pi is intended to be a lightweight runtime host.

Avoid running VS Code Remote-SSH or other memory-heavy development tooling
directly on a Pi Zero-class system. Development should normally occur on
another machine, with the resulting code deployed to the Pi.

High swap activity and I/O wait can make SSH appear hung even when the Pi has
not crashed.

## Reboot Recovery

If a reboot was required, verify:

```bash
systemctl is-active pond-collector.service
systemctl is-active pond-hubitat.service
systemctl is-active pond-network-watchdog.service
```

Then inspect current-boot logs:

```bash
journalctl -b -u pond-collector.service -n 50 --no-pager
journalctl -b -u pond-hubitat.service -n 50 --no-pager
journalctl -b -u pond-network-watchdog.service -n 50 --no-pager
```

The collector's local journal provides protection for readings that could not
be delivered to InfluxDB during temporary network/database outages.
