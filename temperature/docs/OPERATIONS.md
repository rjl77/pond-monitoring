# Pond Monitor Operations

This document covers normal operation and maintenance of Pond Monitor after
installation.

## Services

Pond Monitor normally consists of two systemd services:

```text
pond-collector.service
pond-hubitat.service
```

The collector is the core service.

The Hubitat publisher is optional and is controlled by
`HUBITAT_PUBLISH_ENABLED` in `config/pond.env`.

## Service Status

Check both services:

```bash
systemctl status pond-collector.service pond-hubitat.service
```

For a concise check:

```bash
systemctl is-active pond-collector.service
systemctl is-active pond-hubitat.service
```

Check whether they start automatically at boot:

```bash
systemctl is-enabled pond-collector.service
systemctl is-enabled pond-hubitat.service
```

## Restart Services

Restart the collector:

```bash
sudo systemctl restart pond-collector.service
```

Restart the Hubitat publisher:

```bash
sudo systemctl restart pond-hubitat.service
```

After application or configuration changes, the preferred method is to rerun
the installer:

```bash
cd /opt/pond-monitor
sudo ./install.sh
```

This revalidates configuration and hardware, reinstalls the systemd units, and
verifies the services.

## Logs

Collector logs:

```bash
journalctl -u pond-collector.service -n 50 --no-pager
```

Follow collector logs live:

```bash
journalctl -u pond-collector.service -f
```

Hubitat publisher logs:

```bash
journalctl -u pond-hubitat.service -n 50 --no-pager
```

Follow publisher logs live:

```bash
journalctl -u pond-hubitat.service -f
```

Logs from the current boot only:

```bash
journalctl -b -u pond-collector.service
journalctl -b -u pond-hubitat.service
```

## Collector Schedule

The collector normally starts one collection cycle every 60 seconds.

The interval is controlled by:

```text
POLL_INTERVAL
```

in `config/pond.env`.

Each cycle runs in a child process with a hard timeout. This prevents a blocked
sensor or network operation from permanently hanging the collector.

After repeated cycle-process failures, the collector exits so systemd can
restart it.

## Health Check

The collector provides a lightweight TCP health listener.

The default port is:

```text
9991
```

The configured value is `HEALTH_PORT` in `config/pond.env`.

A local check can be performed with Bash:

```bash
timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/9991'
echo $?
```

Exit status `0` indicates that the TCP listener accepted the connection.

The installer performs this check automatically after starting the collector.

## Offline Journal

If InfluxDB cannot be reached or a write fails, readings are retained locally
in the runtime journal rather than immediately discarded.

The journal is:

```text
/opt/pond-monitor/runtime/sensor_journal.log
```

It uses newline-delimited JSON.

When InfluxDB becomes available again, the collector attempts to flush queued
records before writing the current reading.

The journal is runtime state and is excluded from Git.

Do not manually edit or delete an active journal unless intentionally
performing recovery or cleanup.

## InfluxDB

The collector writes environmental readings to the configured InfluxDB
database.

The current deployment normally uses:

```text
database: pond_data
measurement: temperature
```

Water and air readings are distinguished by the `sensor` tag.

The Hubitat publisher also queries InfluxDB for the current water temperature
and rolling 24-hour minimum and maximum.

Because high and low values are calculated from InfluxDB rather than held only
in process memory, restarting the Hubitat publisher does not reset the
24-hour statistics.

## Hubitat Publishing

The Hubitat publisher is a separate process from the collector.

Its interval is controlled by:

```text
HUBITAT_PUBLISH_INTERVAL
```

The normal value is 900 seconds (15 minutes).

When enabled, it publishes:

- current water temperature
- rolling 24-hour high
- rolling 24-hour low
- last-updated timestamp

Disabling the publisher does not stop sensor collection or InfluxDB storage.

To change whether it runs, edit:

```text
HUBITAT_PUBLISH_ENABLED
```

in `config/pond.env`, then rerun:

```bash
sudo ./install.sh
```

## Configuration Changes

Local configuration is stored in:

```text
/opt/pond-monitor/config/pond.env
```

After changing configuration, run:

```bash
cd /opt/pond-monitor
sudo ./install.sh
```

This validates the new configuration before completing deployment.

Do not put passwords or Hubitat access tokens into source files,
documentation, or `pond.env.example`.

## DS18B20 Sensor

List detected DS18B20 sensors:

```bash
ls -1 /sys/bus/w1/devices/28-*
```

Read the configured sensor directly by replacing the example ID as needed:

```bash
cat /sys/bus/w1/devices/28-xxxxxxxxxxxx/w1_slave
```

A valid DS18B20 response should contain:

```text
YES
```

on the CRC/status line and a `t=` temperature value on the data line.

If the physical probe is replaced, update `WATER_SENSOR_ID` in `pond.env` and
rerun `install.sh`.

## Reboot

Pond Monitor is intended to recover automatically after a normal reboot.

Reboot:

```bash
sudo reboot
```

After reconnecting:

```bash
systemctl is-active pond-collector.service
systemctl is-active pond-hubitat.service
```

Then check recent collector output:

```bash
journalctl -b -u pond-collector.service -n 30 --no-pager
```

## Application Updates

After updating the files under `/opt/pond-monitor`, run:

```bash
sudo ./install.sh
```

The installer is designed to be rerunnable and preserves the existing local
`config/pond.env`.

## Important Local State

The important machine-local files are:

```text
config/pond.env
runtime/sensor_journal.log
```

`pond.env` contains configuration and secrets.

`sensor_journal.log`, when present, contains readings waiting to be reconciled
with InfluxDB.

Historical measurement data itself resides in InfluxDB rather than on the
Raspberry Pi.

## Backup and Recovery

Pond Monitor is designed so that the Raspberry Pi can be rebuilt rather than
requiring restoration of a complete system image.

### What Is Stored Where

Historical sensor measurements are stored in InfluxDB and are not dependent on
the Raspberry Pi SD card after they have been successfully written.

The application source and documentation should be recoverable from the Git
repository once the project is placed under version control.

Machine-local configuration is stored in:

```text
/opt/pond-monitor/config/pond.env
```

This file contains secrets and is intentionally excluded from Git.

Readings waiting for delivery to InfluxDB may exist in:

```text
/opt/pond-monitor/runtime/sensor_journal.log
```

The journal is also excluded from Git.

### Configuration Backup

Maintain a secure backup of `config/pond.env` outside the Git repository.

Because this file contains credentials, do not place an unencrypted copy in a
public or shared source repository.

`config/pond.env.example` documents the required configuration fields without
containing the machine's actual credentials.

### Runtime Journal

Under normal operation there may be no journal to preserve.

If replacing or rebuilding a Pi while
`runtime/sensor_journal.log` contains queued records, preserve the journal
before removing the old installation if possible.

This prevents measurements collected during an InfluxDB outage from being
lost before they can be reconciled.

### InfluxDB Backup

InfluxDB should be backed up independently of the Raspberry Pi.

The Pi should not be considered the authoritative backup location for
historical pond measurements.

### Raspberry Pi Recovery

For a replacement or freshly imaged Pi:

1. Install Raspberry Pi OS and configure networking.
2. Install or copy the Pond Monitor project to `/opt/pond-monitor`.
3. Enable the Raspberry Pi 1-Wire interface.
4. Reboot if required by the 1-Wire configuration change.
5. Connect the DS18B20 sensor.
6. Discover its `28-*` device ID.
7. Create or restore `config/pond.env`.
8. Set `WATER_SENSOR_ID` to the installed probe.
9. Run `sudo ./install.sh`.
10. Verify both service state and new InfluxDB readings.
11. Restore a preserved runtime journal if recovery of queued readings is
    required.

A full SD-card image can be maintained as an additional disaster-recovery
option, but the application is intended to be reproducibly deployable without
one.
