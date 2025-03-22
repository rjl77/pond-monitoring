#!/usr/bin/env python3
"""
RTSP Frame Capture Script
-------------------------
Purpose:
    This script captures a specified number of frames from an RTSP stream and saves them as image (.jpg) files.
    The captured frames are intended to serve as a static baseline for later detection tasks,
    such as background subtraction or differentiation. 
    
Usage:
    1. Set the RTSP connection parameters (username, password, host, port, and optional path).
    2. Run the script to capture frames from the RTSP stream.
    
Dependencies:
    - Python 3
    - OpenCV (cv2)

Notes:
    - If no optional path is provided, the URL will default to the root.
    - An empty string for RTSP_PATH is treated as no additional path.
"""

import cv2

# RTSP Stream URL
RTSP_USER = 'user'          # Camera user username
RTSP_PASS = 'password'      # Camera user's password
RTSP_HOST = 'xx.xx.xx.xx'   # Hostname or IP address of camera
RTSP_PORT = 'xxxx'          # TCP Port used for RTSP (as string)
RTSP_PATH = ''              # (Optional) Additional path beyond root. Do not add a leading slash.

RTSP_URL = f'rtsp://{RTSP_USER}:{RTSP_PASS}@{RTSP_HOST}:{RTSP_PORT}' + (f'/{RTSP_PATH.lstrip("/")}' if RTSP_PATH else '')

# Number of frames to capture
NUM_FRAMES = 10

# Create a VideoCapture object for the RTSP stream
cap = cv2.VideoCapture(RTSP_URL)

if not cap.isOpened():
    print("Error: Cannot open RTSP stream.")
    exit()

# Loop to capture frames
for i in range(NUM_FRAMES):
    success, frame = cap.read()
    if not success:
        print(f"Error: Unable to capture frame {i}")
        break

    # Save each frame as an image file
    filename = f'frame_{i+1}.jpg'
    cv2.imwrite(filename, frame)
    print(f'Saved: {filename}')

cap.release()
print("Finished capturing frames.")
