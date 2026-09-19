# Pond Monitor Development Notes

## Architecture

Pond Monitor has two intentionally separate processes:

- `src/collector.py` is the core sensor collector.
- `src/hubitat.py` is an optional Hubitat publisher.

Do not combine these processes. Hubitat publishing must remain optional and
must not be required for core sensor collection.

Air-temperature input and Hubitat publishing are separate concerns.
`AIR_SOURCE` may be `hubitat`, `dht`, or `none` regardless of whether Hubitat
publishing is enabled.

## Configuration

Machine-specific configuration and secrets belong in:

```text
config/pond.env
```

This file must never be committed.

Non-secret configuration examples belong in:

```text
config/pond.env.example
```

Do not hard-code IP addresses, credentials, device IDs, sensor IDs, or tokens
in Python source, systemd templates, or documentation.

## Runtime State

Runtime state belongs under:

```text
runtime/
```

Runtime files must not be committed.

The offline sensor journal is expected at:

```text
runtime/sensor_journal.log
```

## Reliability Requirements

Preserve these collector behaviors:

- one child process per collection cycle
- hard cycle timeout
- systemd restart after repeated process failures
- local journaling when InfluxDB writes fail
- automatic journal reconciliation when InfluxDB returns
- independent water and air acquisition
- TCP health listener
- failure to bind the health port is fatal at startup

Temporary InfluxDB or network failure must not cause sensor readings to be
silently discarded.

## Dependencies

Normal deployment uses Debian packages for required Python dependencies:

```text
python3
python3-influxdb
python3-requests
```

Do not introduce a Python virtual environment unless the deployment design is
intentionally changed.

DHT/Blinka support is optional. Do not make it a mandatory dependency for
installations using Hubitat or no air-temperature source.

## Deployment

The supported deployment entry point is:

```bash
sudo ./install.sh
```

Keep the installer idempotent.

Systemd source files under `systemd/` are templates. Runtime user/group values
are substituted by `install.sh`.

Do not manually maintain separate production copies of application code.

## Target Hardware

The target is a resource-constrained Raspberry Pi Zero-class system.

Avoid adding heavyweight resident processes or development tooling to the Pi.
Development should normally occur on another computer and be deployed to the
Pi.

## Documentation

Update the relevant documentation when behavior, configuration, installation,
or recovery procedures change:

- `README.md`
- `docs/INSTALL.md`
- `docs/OPERATIONS.md`
- `docs/TROUBLESHOOTING.md`

Keep fresh-Pi reproducibility as a design requirement.
