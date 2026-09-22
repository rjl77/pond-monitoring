#!/bin/bash

set -euo pipefail

APP_DIR="/opt/pond-collector"
CONFIG_FILE="$APP_DIR/config/pond.env"
CONFIG_EXAMPLE="$APP_DIR/config/pond.env.example"

log() {
    printf '[pond-monitor] %s\n' "$*"
}

die() {
    printf '[pond-monitor] ERROR: %s\n' "$*" >&2
    exit 1
}


# ----------------------------------------------------------------------
# Privileges
# ----------------------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
    die "Run this installer with sudo: sudo ./install.sh"
fi


# ----------------------------------------------------------------------
# Application files
# ----------------------------------------------------------------------

if [[ ! -d "$APP_DIR" ]]; then
    die "Application directory not found: $APP_DIR"
fi

if [[ ! -f "$CONFIG_EXAMPLE" ]]; then
    die "Configuration template not found: $CONFIG_EXAMPLE"
fi


# ----------------------------------------------------------------------
# Required OS packages
# ----------------------------------------------------------------------

log "Installing required Debian packages..."

apt-get update

apt-get install -y \
    python3 \
    python3-influxdb \
    python3-requests


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

if [[ ! -f "$CONFIG_FILE" ]]; then
    log "No local configuration found."
    log "Creating $CONFIG_FILE from template."

    cp "$CONFIG_EXAMPLE" "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"

    log "Configuration created: $CONFIG_FILE"
    log "Edit the configuration and rerun this installer."
    exit 0
else
    log "Existing configuration found; leaving it unchanged."
    chmod 600 "$CONFIG_FILE"
fi

# ----------------------------------------------------------------------
# Configuration validation
# ----------------------------------------------------------------------

log "Validating configuration..."

# Load pond.env into this process.
set -a
# shellcheck disable=SC1090
source "$CONFIG_FILE"
set +a

required_values=(
    SERVICE_USER
    SERVICE_GROUP
    WATER_SENSOR_ID
    POLL_INTERVAL
    HEALTH_PORT
    INFLUX_HOST
    INFLUX_PORT
    INFLUX_USER
    INFLUX_PASSWORD
    INFLUX_DATABASE
    AIR_SOURCE
)

for name in "${required_values[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        die "Required configuration value is missing: $name"
    fi
done

case "$AIR_SOURCE" in
    hubitat)
        [[ -n "${HUBITAT_HOST:-}" ]] ||
            die "HUBITAT_HOST is required when AIR_SOURCE=hubitat"
        [[ -n "${HUBITAT_APP_ID:-}" ]] ||
            die "HUBITAT_APP_ID is required when AIR_SOURCE=hubitat"
        [[ -n "${HUBITAT_TOKEN:-}" ]] ||
            die "HUBITAT_TOKEN is required when AIR_SOURCE=hubitat"
        [[ -n "${HUBITAT_AIR_DEVICE_ID:-}" ]] ||
            die "HUBITAT_AIR_DEVICE_ID is required when AIR_SOURCE=hubitat"
        ;;

    dht)
        [[ -n "${DHT_GPIO:-}" ]] ||
            die "DHT_GPIO is required when AIR_SOURCE=dht"
        ;;

    none)
        ;;

    *)
        die "AIR_SOURCE must be hubitat, dht, or none"
        ;;
esac

case "${HUBITAT_PUBLISH_ENABLED:-false}" in
    true|false)
        ;;

    *)
        die "HUBITAT_PUBLISH_ENABLED must be true or false"
        ;;
esac

if [[ "${HUBITAT_PUBLISH_ENABLED:-false}" == "true" ]]; then
    hubitat_publish_values=(
        HUBITAT_HOST
        HUBITAT_APP_ID
        HUBITAT_TOKEN
        HUBITAT_CURRENT_DEVICE_ID
        HUBITAT_HIGH_DEVICE_ID
        HUBITAT_LOW_DEVICE_ID
        HUBITAT_UPDATED_DEVICE_ID
        HUBITAT_PUBLISH_INTERVAL
    )

    for name in "${hubitat_publish_values[@]}"; do
        if [[ -z "${!name:-}" ]]; then
            die "Required Hubitat publishing value is missing: $name"
        fi
    done
fi

for name in POLL_INTERVAL HEALTH_PORT INFLUX_PORT; do
    value="${!name}"

    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        die "$name must be an integer"
    fi
done

log "Configuration is valid."

# ----------------------------------------------------------------------
# Optional DHT support
# ----------------------------------------------------------------------

if [[ "$AIR_SOURCE" == "dht" ]]; then
    log "Checking optional DHT dependencies..."

    if ! python3 -c 'import board, adafruit_dht' >/dev/null 2>&1; then
        die "AIR_SOURCE=dht requires Adafruit Blinka and adafruit-circuitpython-dht."
    fi

    log "DHT dependencies are available."
fi

# ----------------------------------------------------------------------
# Runtime account validation
# ----------------------------------------------------------------------

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    die "Configured service user does not exist: $SERVICE_USER"
fi

if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
    die "Configured service group does not exist: $SERVICE_GROUP"
fi

log "Runtime account is valid: $SERVICE_USER:$SERVICE_GROUP"

# Ensure the service account can read its local configuration.
chown "$SERVICE_USER:$SERVICE_GROUP" "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"

log "Configuration ownership set for runtime account."

# Ensure the runtime directory exists and is writable by the service account.
install -d \
    -o "$SERVICE_USER" \
    -g "$SERVICE_GROUP" \
    -m 750 \
    "$APP_DIR/runtime"

log "Runtime directory is ready."

# ----------------------------------------------------------------------
# 1-Wire
# ----------------------------------------------------------------------

BOOT_CONFIG="/boot/firmware/config.txt"

if [[ ! -f "$BOOT_CONFIG" ]]; then
    die "Raspberry Pi boot configuration not found: $BOOT_CONFIG"
fi

if grep -Eq '^[[:space:]]*dtoverlay=w1-gpio([[:space:]]|$|,)' "$BOOT_CONFIG"; then
    log "1-Wire overlay is enabled."
else
    die "1-Wire is not enabled. Add 'dtoverlay=w1-gpio' to $BOOT_CONFIG and reboot."
fi


# ----------------------------------------------------------------------
# DS18B20 discovery
# ----------------------------------------------------------------------

shopt -s nullglob
sensors=(/sys/bus/w1/devices/28-*)
shopt -u nullglob

if (( ${#sensors[@]} == 0 )); then
    die "No DS18B20 sensor detected under /sys/bus/w1/devices."
fi

log "Detected DS18B20 sensor(s):"

for sensor in "${sensors[@]}"; do
    log "  $(basename "$sensor")"
done

CONFIGURED_SENSOR="/sys/bus/w1/devices/$WATER_SENSOR_ID"

if [[ ! -d "$CONFIGURED_SENSOR" ]]; then
    die "Configured WATER_SENSOR_ID '$WATER_SENSOR_ID' was not detected."
fi

if [[ ! -r "$CONFIGURED_SENSOR/w1_slave" ]]; then
    die "Configured DS18B20 cannot be read: $CONFIGURED_SENSOR/w1_slave"
fi

log "Configured water sensor detected: $WATER_SENSOR_ID"

log "Prerequisite checks complete."

# ----------------------------------------------------------------------
# systemd services
# ----------------------------------------------------------------------

COLLECTOR_UNIT="$APP_DIR/systemd/pond-collector.service"
HUBITAT_UNIT="$APP_DIR/systemd/pond-hubitat.service"
WATCHDOG_UNIT="$APP_DIR/systemd/pond-network-watchdog.service"

for unit in "$COLLECTOR_UNIT" "$HUBITAT_UNIT"; do
    if [[ ! -f "$unit" ]]; then
        die "systemd unit template not found: $unit"
    fi

    if ! grep -q '@SERVICE_USER@' "$unit"; then
        die "SERVICE_USER placeholder missing from: $unit"
    fi

    if ! grep -q '@SERVICE_GROUP@' "$unit"; then
        die "SERVICE_GROUP placeholder missing from: $unit"
    fi
done

if [[ ! -f "$WATCHDOG_UNIT" ]]; then
    die "systemd unit template not found: $WATCHDOG_UNIT"
fi

log "Installing systemd service files..."

sed \
    -e "s|@SERVICE_USER@|$SERVICE_USER|g" \
    -e "s|@SERVICE_GROUP@|$SERVICE_GROUP|g" \
    "$COLLECTOR_UNIT" \
    > /etc/systemd/system/pond-collector.service

sed \
    -e "s|@SERVICE_USER@|$SERVICE_USER|g" \
    -e "s|@SERVICE_GROUP@|$SERVICE_GROUP|g" \
    "$HUBITAT_UNIT" \
    > /etc/systemd/system/pond-hubitat.service

cp "$WATCHDOG_UNIT" \
    /etc/systemd/system/pond-network-watchdog.service

chmod 644 \
    /etc/systemd/system/pond-collector.service \
    /etc/systemd/system/pond-hubitat.service \
    /etc/systemd/system/pond-network-watchdog.service

systemctl daemon-reload

log "systemd service files installed."

# ----------------------------------------------------------------------
# Install administration command
# ----------------------------------------------------------------------

POND_COLLECTOR_TOOL="$APP_DIR/tools/pond-collector"
POND_COLLECTOR_COMMAND="/usr/local/bin/pond-collector"
POND_MONITOR_COMPAT_COMMAND="/usr/local/bin/pond-monitor"

if [[ ! -f "$POND_COLLECTOR_TOOL" ]]; then
    die "Pond Collector administration tool not found: $POND_COLLECTOR_TOOL"
fi

chmod 755 "$POND_COLLECTOR_TOOL"

ln -sfn "$POND_COLLECTOR_TOOL" "$POND_COLLECTOR_COMMAND"
ln -sfn "$POND_COLLECTOR_COMMAND" "$POND_MONITOR_COMPAT_COMMAND"

log "Administration command installed: $POND_COLLECTOR_COMMAND"
log "Compatibility command installed: $POND_MONITOR_COMPAT_COMMAND"

# ----------------------------------------------------------------------
# Enable and start services
# ----------------------------------------------------------------------

log "Enabling Pond Monitor collector..."

systemctl enable pond-collector.service
systemctl restart pond-collector.service

if [[ "$HUBITAT_PUBLISH_ENABLED" == "true" ]]; then
    log "Enabling Hubitat publisher..."

    systemctl enable pond-hubitat.service
    systemctl restart pond-hubitat.service
else
    log "Hubitat publishing is disabled."

    systemctl disable pond-hubitat.service 2>/dev/null || true
    systemctl stop pond-hubitat.service 2>/dev/null || true
fi

log "Enabling network diagnostic watchdog..."

systemctl enable pond-network-watchdog.service
systemctl restart pond-network-watchdog.service

log "Pond Monitor services configured."

# ----------------------------------------------------------------------
# Post-install verification
# ----------------------------------------------------------------------

log "Verifying Pond Monitor services..."

# Give the services a moment to complete startup.
sleep 2

if ! systemctl is-active --quiet pond-collector.service; then
    systemctl status pond-collector.service --no-pager || true
    die "Pond Monitor collector failed to start."
fi

log "Collector service is active."

if [[ "$HUBITAT_PUBLISH_ENABLED" == "true" ]]; then
    if ! systemctl is-active --quiet pond-hubitat.service; then
        systemctl status pond-hubitat.service --no-pager || true
        die "Hubitat publisher failed to start."
    fi

    log "Hubitat publisher service is active."
fi

if ! systemctl is-active --quiet pond-network-watchdog.service; then
    systemctl status pond-network-watchdog.service --no-pager || true
    die "Network diagnostic watchdog failed to start."
fi

log "Network diagnostic watchdog service is active."

# ----------------------------------------------------------------------
# Health check
# ----------------------------------------------------------------------

if ! timeout 2 bash -c \
    "exec 3<>/dev/tcp/127.0.0.1/$HEALTH_PORT"
then
    journalctl \
        -u pond-collector.service \
        -n 20 \
        --no-pager || true

    die "Collector health check failed on TCP port $HEALTH_PORT."
fi

log "Collector health check passed on TCP port $HEALTH_PORT."

log "Installation completed successfully."
