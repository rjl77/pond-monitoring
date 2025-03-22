# Capture background frames to assist w/new object differentiation...

# (Clean this up.)

import cv2

# RTSP Stream URL
RTSP_URL = 'rtsp://<username>:<password>@<host>:<port>'

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
