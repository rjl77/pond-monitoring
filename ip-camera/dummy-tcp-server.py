#!/usr/bin/env python3
"""
Dummy TCP Server

Listens on all available interfaces (defaults to port TCP 2525) and accepts incoming connections.
It reads and discards any incoming data. Intended to be run as a service.

I presently use this as a dummy mail server to target from commerical IP cameras w/SMTP capability, 
which then triggers a shell script (camera-motion-huibtat.sh), which also runs as a service and 
sends API calls to a Hubitat home automation hub when traffic is detected.
"""

import socket

HOST = '0.0.0.0'  # Listen on all network interfaces
PORT = 2525       # TCP port number to listen on

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        # Allow reuse of the address (helpful during rapid restarts)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen()

        print(f"Listening on {HOST}:{PORT}...")

        while True:
            client_socket, client_address = server_socket.accept()
            print(f"Accepted connection from {client_address}")

            with client_socket:
                # Read and discard incoming data until connection is closed
                while True:
                    data = client_socket.recv(1024)
                    if not data:
                        break

if __name__ == '__main__':
    main()
