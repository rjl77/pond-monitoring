# Hubitat Virtual Motion Sensor Trigger

These two scripts that work to monitor camera activity and trigger a Hubitat Virtual Motion Sensor via API calls. This should work with any off-the-shelf IP camera that can either send an e-mail or ftp a file. The first script is a dummy TCP server that can be targeted in place of an SMTP or FTP server. The second script monitors any incoming connections to the dummy server (via `tcpdump`) from specified devices and triggers the specified Hubitat device API endpoint (via `curl`).

## Dummy TCP Server (Python Script)
- **Purpose:**  
  Listens on all available network interfaces (default: port 2525) and accepts incoming TCP connections. It reads and discards any data received.  
  This server acts as a dummy mail or ftp server for IP cameras with SMTP or FTP capability.

  Run this script as a service to continuously accept connections.

- **Configuration:**  
  - **HOST:** Defaults to `0.0.0.0` (all interfaces).  
  - **PORT:** Defaults to `2525`.

## Hubitat API Trigger via TCPDump (Bash Script)
- **Purpose:**  
  Monitors network traffic on a specified port (default: 2525) for incoming SYN packets. When a packet from a known device (by MAC address) is detected, it triggers the corresponding Hubitat API endpoint via `curl`.
    
  This method is used to activate a Hubitat device, typically a Virtual Motion Sensor.

  Run this script as a service.
  
- **Configuration:**  
  - **HUBITAT_API_BASE:** The base URL for your Hubitat hub's API.  
  - **ACCESS_TOKEN:** Your Hubitat API access token.  
  - **DEVICE_x Mappings:**  
    - **DEVICE_MACS:** Maps generic device names to their MAC addresses.  
    - **DEVICE_IDS:** Maps generic device names to Hubitat device IDs.
  - **INTERFACE & PORT:** Specify the network interface (default: "any") and port (default: "2525") to monitor.

- **Requirements:**  
  - `tcpdump` must be installed and have the necessary permissions.  
  - Bash version 4 or later.

