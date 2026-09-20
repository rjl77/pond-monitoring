# Pond Monitor Installation

This document describes how to deploy Pond Monitor to a Raspberry Pi from a
fresh Raspberry Pi OS installation.

## Hardware

The normal installation uses:

- Raspberry Pi
- DS18B20 1-Wire temperature sensor
- Network connectivity to the InfluxDB server
- Optional network connectivity to Hubitat
- Optional DHT22 air-temperature sensor

The DS18B20 must be physically connected before completing installation.

## Application Location

The stable application path is:

```text
/opt/pond-monitor
```

For a Git deployment, this is a symbolic link to the `temperature/` project in
the production checkout:

```text
/opt/pond-monitor -> /opt/pond-monitor-repo/temperature
```

The application must be present at `/opt/pond-monitor` before running the
installer.

## Enable 1-Wire

Pond Monitor requires the Raspberry Pi 1-Wire interface for the DS18B20.

The boot configuration should contain:

```text
dtoverlay=w1-gpio
```

On current Raspberry Pi OS installations the configuration file is:

```text
/boot/firmware/config.txt
```

After enabling 1-Wire, reboot the Pi.

Verify that a DS18B20 appears:

```bash
ls /sys/bus/w1/devices/28-*
```

Record the detected device ID. It will look similar to:

```text
28-xxxxxxxxxxxx
```

This value becomes `WATER_SENSOR_ID` in `config/pond.env`.

The installer verifies that 1-Wire is enabled and that the configured sensor
exists and is readable. It does not modify the Raspberry Pi boot configuration.

## Local Configuration

Machine-specific configuration is stored in:

```text
/opt/pond-monitor/config/pond.env
```

This file contains secrets and must not be committed to Git.

On the first installer run, if `pond.env` does not exist, the installer creates
it from:

```text
config/pond.env.example
```

The installer then exits so the configuration can be edited.

Edit:

```bash
sudo nano /opt/pond-monitor/config/pond.env
```

At minimum, configure the runtime account, DS18B20 ID, InfluxDB connection,
air-temperature source, and any required Hubitat settings.

The configuration file is restricted to mode 600 by the installer.

## Air Temperature Sources

`AIR_SOURCE` supports:

```text
hubitat
dht
none
```

### Hubitat

With:

```text
AIR_SOURCE=hubitat
```

the collector retrieves air temperature from the configured Hubitat device.

The Hubitat host, Maker API application ID, access token, and air-temperature
device ID must be configured.

### DHT22

With:

```text
AIR_SOURCE=dht
```

the collector reads a locally connected DHT22.

DHT support requires the Python modules:

```text
Adafruit-Blinka
adafruit-circuitpython-dht
```

These are optional dependencies and are not automatically installed by
`install.sh`.

The installer verifies that the modules are available when DHT mode is
selected.

### None

With:

```text
AIR_SOURCE=none
```

only water temperature is collected.

## Hubitat Publishing

Hubitat output is independent of the air-temperature source.

Set:

```text
HUBITAT_PUBLISH_ENABLED=true
```

to run the Hubitat publisher.

The publisher reads water-temperature data from InfluxDB and publishes:

- current water temperature
- rolling 24-hour high
- rolling 24-hour low
- update timestamp

Set the value to `false` to disable the publisher service.

## Installation

Run:

```bash
cd /opt/pond-monitor
sudo ./install.sh
```

The installer:

1. Installs required Debian Python packages.
2. Creates `pond.env` from the example if necessary.
3. Validates configuration.
4. Validates the configured Linux service account.
5. Verifies Raspberry Pi 1-Wire configuration.
6. Discovers DS18B20 sensors.
7. Verifies the configured water sensor.
8. Renders and installs the systemd service files.
9. Installs the `pond-monitor` administration command.
10. Enables and restarts the collector.
11. Enables/restarts or disables the Hubitat publisher according to config.
12. Verifies the running services.
13. Verifies the collector TCP health listener.

The installer is idempotent and may be rerun after code or configuration
changes. After the initial installation, the preferred interface for rerunning
it is:

```bash
sudo pond-monitor install
```

Normal Git updates should instead be performed with:

```bash
sudo pond-monitor refresh
```

## Installed Services

The installer creates:

```text
/etc/systemd/system/pond-collector.service
/etc/systemd/system/pond-hubitat.service
```

The source templates remain under:

```text
/opt/pond-monitor/systemd/
```

The templates contain `@SERVICE_USER@` and `@SERVICE_GROUP@` placeholders.
`install.sh` substitutes the values from `pond.env` when installing them.

Do not copy the templates directly into `/etc/systemd/system`.

## Installed Administration Command

The installer creates:

```text
/usr/local/bin/pond-monitor -> /opt/pond-monitor/tools/pond-monitor
```

The command provides the normal administration interface after installation:

```bash
pond-monitor status
pond-monitor version
pond-monitor logs
pond-monitor logs -f
sudo pond-monitor install
sudo pond-monitor refresh
```

The command source is maintained in the Git repository as an executable file.
The installer creates the symbolic link under `/usr/local/bin`, allowing Git
updates to update the command without maintaining a separate copy.

## Verify Installation

Perform the normal overall check:

```bash
pond-monitor status
```

This reports service state, Git deployment state, the collector TCP health
listener, and current and rolling 24-hour InfluxDB temperature data.

Verify the installed version:

```bash
pond-monitor version
```

For direct systemd verification:

```bash
systemctl is-active pond-collector.service
systemctl is-active pond-hubitat.service
```

For an enabled Hubitat publisher, both should report:

```text
active
```

Check enablement:

```bash
systemctl is-enabled pond-collector.service
systemctl is-enabled pond-hubitat.service
```

Recent logs can be viewed with:

```bash
pond-monitor logs
```

or directly through the journal:

```bash
journalctl -u pond-collector.service -n 30 --no-pager
journalctl -u pond-hubitat.service -n 30 --no-pager
```

## Reboot Test

After a new installation, perform a reboot:

```bash
sudo reboot
```

After reconnecting, verify:

```bash
pond-monitor status
```

Confirm that both expected services are active, the TCP health check passes,
and new sensor readings are reaching InfluxDB.

## Secrets

`config/pond.env` may contain:

- InfluxDB credentials
- Hubitat Maker API access token
- network addresses
- device IDs

It is excluded from Git by `.gitignore`.

Never copy secrets into `pond.env.example`, documentation, source code, or
systemd unit templates.

## Pre-Git Security Checklist

Before initializing or publishing the Git repository:

- Rotate any secrets (Hubitat Maker API token, InfluxDB credentials) if 
previously-exposed, weak or not unique.
- Identify and update any other systems that share those credentials.
- Update only the machine-local `config/pond.env` with the new Pond Monitor
  credentials.
- Verify that no real credential value occurs elsewhere in the project tree.
- Verify that the actual `config/pond.env` is ignored by Git.

**Credential rotation should be completed before the first Git commit so the
repository begins with a clean credential history.**
