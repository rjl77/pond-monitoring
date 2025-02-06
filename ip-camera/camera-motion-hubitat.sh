#!/bin/bash
# =============================================================================
# Pond Monitoring: Hubitat API Trigger via TCPDump
#
# This script continuously monitors network traffic on a specified port (default: 2525)
# for incoming SYN packets. When a packet is detected from a known device, the script
# triggers a corresponding Hubitat API endpoint via curl.
#
# The Hubitat device that I presently trigger this way is a Virtual Motion Sensor.
#
# This script works in conjunction with a dummy TCP server (running as a service) that
# listens on the same port. For example, the TCP dummy server can stand in as a mail server
# for IP cameras with SMTP functionality.
#
# Configuration:
#   - HUBITAT_API_BASE: The base URL for your Hubitat hub's API.
#   - ACCESS_TOKEN: Your Hubitat API access token.
#   - DEVICE_x: A name for your device.
#		- Also specify the hardware/MAC address (for each camera) and Hubitat device ID (for
#                 example, a Virtual Motion Sensor).
#
# Device Configuration:
#   Map generic device names to identifiers (hostnames or MAC addresses) and Hubitat device IDs.
#
# Requirements:
#   - tcpdump must be installed and have the appropriate permissions.
#   - bash version 4 or later
# =============================================================================

# Hubitat API configuration (update these placeholders)
HUBITAT_API_BASE="http://YOUR_HUB_IP/apps/api/9/devices"
ACCESS_TOKEN="YOUR_ACCESS_TOKEN"

# Declare associative arrays mapping generic device names to their MAC addresses and Hubitat device IDs.
declare -A DEVICE_MACS=(
    # Format: ["GENERIC_DEVICE_NAME"]="MAC_ADDRESS", ex.: ["Pond-PTZ"]="aa:bb:cc:00:11:22".
    ["DEVICE_A"]="XX:XX:XX:XX:XX:XX"
    ["DEVICE_B"]="YY:YY:YY:YY:YY:YY"
    ["DEVICE_C"]="ZZ:ZZ:ZZ:ZZ:ZZ:ZZ"
)

declare -A DEVICE_IDS=(
    # Format: ["GENERIC_DEVICE_NAME"]="HUBITAT_DEVICE_ID", ex.: ["Pond-PTZ"]="101"
    ["DEVICE_A"]="101"
    ["DEVICE_B"]="102"
    ["DEVICE_C"]="103"
)

# Define the network interface and port to monitor.
# Ensure that the dummy TCP server (running as a service) is also listening on this port.
INTERFACE="any"
PORT="2525"

# Infinite loop to continuously capture SYN packets on the specified port.
while true; do
    # Capture a single packet with the SYN flag set on the given port.
    # Suppress error messages for cleaner output.
    line=$(tcpdump -Qin --immediate-mode -i "$INTERFACE" -c1 port "$PORT" and "tcp[tcpflags] & tcp-syn != 0" 2>/dev/null)
    
    triggered=0

    # Loop through all configured devices.
    for device in "${!DEVICE_MACS[@]}"; do
        mac_address="${DEVICE_MACS[$device]}"
        if [[ $line == *"$mac_address"* ]]; then
            hubitat_id="${DEVICE_IDS[$device]}"
            echo "Detected $device (MAC: $mac_address, Hubitat ID: $hubitat_id)"
            # Trigger the Hubitat API for the corresponding device.
            curl -s "${HUBITAT_API_BASE}/${hubitat_id}/active?access_token=${ACCESS_TOKEN}" >/dev/null
            triggered=1
            break  # Only trigger one device per captured packet.
        fi
    done

    if [ $triggered -eq 0 ]; then
        # Optionally, handle unmatched packets (currently silent).
        :
    fi
done
