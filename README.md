# ground-station-real-time-plotting
Built in Python using Dash, it receives sensor data from an Arduino over USB/XBee serial, displays all channels as live scrolling graphs, tracks the rocket on a GPS map, logs everything to CSV, and allows command uplink back to the vehicle.
Features
Feature
DetailsLive graphsAccelerometer (X/Y/Z), Gyroscope (R/P/Y), Altitude, Voltage, Current, Ultrasonic — all 6 update every secondGPS mapLive marker + cyan trail polyline on OpenStreetMap via Dash LeafletCSV loggingEvery telemetry frame written to telemetry_log.csv with flush + fsync — no data loss on crashState persistenceMission clock and packet count saved to mission_state.json every second; survives laptop restartsPre-launch checklist5-item checklist gates the ARM button; telemetry cannot be armed before jury clearanceBattery monitorCountdown bar from 100 % over the required 2-hour runtime; turns yellow at 40 %, red at 15 %Antenna rangeSlant-range estimator using rocket altitude + 1 km horizontal distance to padCommand uplinkSend preset or custom commands to the Arduino over serial; echo verification shown in the UICSV downloadDownload the full log as a timestamped file directly from the browser at any point during flightSimulator modeWorks with no hardware connected — generates realistic fake sensor data so the UI can be tested anywherePort selectorSwitch serial port live from the UI dropdown without restarting Python

Requirements Compliance
ReqDescriptionStatus5.4Telemetry command only after jury inspection & clearance✅ ARM button locked behind 5-item checklist5.5 / 5.7Antenna elevated from ground level✅ Checklist item; operator-verified5.6Ground station physically stable✅ Checklist item; operator-verified5.8Ground station generates CSV of all sensor data✅ Auto-logged to telemetry_log.csv5.9Mission time with ≤ 1-second resolution✅ 1 Hz update interval5.10Mission clock & state maintained across processor resets✅ mission_state.json persists every second5.11All telemetry fields plotted in real-time✅ 6 live graphs covering all 13 sensor channels5.12Laptop with minimum 2-hour battery operation✅ Battery countdown bar with colour-coded warnings5.13Ground station portable, operable from flight line✅ Runs on any laptop; single Python file, no installation beyond pip5.14Antenna range adequate for 1 km launch pad distance✅ Slant-range indicator computed from altitude

Hardware
ComponentPurposeArduino (Uno / Nano / Mega)Reads all sensors, formats telemetry string, sends over serialMPU-60503-axis accelerometer + 3-axis gyroscopeGPS module (NMEA, e.g. Neo-6M)Position, altitude, satellite countHC-SR04 ultrasonic sensorDistance to groundXBee radio + hand-held antennaWireless telemetry link at competition siteLaptopRuns GCS_code.py; must have ≥ 2 h battery

Telemetry Packet Format
The Arduino sends one comma-separated line per second at 9600 baud:
TEAM_ID, MISSION_TIME, PACKET_COUNT, MODE, STATE,
ALT, VOLTAGE, CURRENT,
ACCEL_X, ACCEL_Y, ACCEL_Z,
GYRO_R, GYRO_P, GYRO_Y,
GPS_TIME, GPS_LAT, GPS_LON, GPS_ALT, GPS_SATS,
ULTRASONIC_DIST, CMD_ECHO
Example:
1001,00:01:23,83,FLIGHT,ASCENT,142.30,7.85,0.42,-0.02,0.01,9.81,-1.2,0.4,0.1,00:01:23,37.774935,-122.419381,147.20,9,0.45,CMD_TEL_ON

CSV Log Format
telemetry_log.csv is created automatically in the same folder as GCS_code.py the first time the script is run. Columns:
mission_time, packet_count, mode, state, alt,
voltage, current,
accel_x, accel_y, accel_z,
gyro_r, gyro_p, gyro_y,
gps_time, gps_lat, gps_lon, gps_alt, gps_sats,
ultrasonic_dist, cmd_echo
To download a timestamped copy mid-flight, click "⬇ Download Telemetry CSV" in the command terminal panel.

Installation
Python 3.8 or later required.
Install all dependencies in one command:
bashpip install dash dash-bootstrap-components dash-leaflet plotly pyserial

Running the GCS
bashpython GCS_code.py
Then open your browser and go to:
http://127.0.0.1:8050
The dashboard starts in Simulator mode automatically if no Arduino is detected. Fake sensor data will stream in so you can verify the UI without hardware.
With hardware connected

Flash MPU6050_gcs.ino to the Arduino using the Arduino IDE.
Connect the Arduino via USB.
Run python GCS_code.py — it auto-detects the port.
If auto-detect fails, use the Serial Port dropdown in the UI to select the correct port manually and click Connect.

Port names by OS
OSTypical port nameWindowsCOM3, COM4, …macOS/dev/cu.usbmodem…, /dev/cu.usbserial…Linux/dev/ttyUSB0, /dev/ttyACM0

Pre-Launch Checklist (REQ 5.4)
Before the ARM button becomes available, an operator must tick all five items:

 Antenna elevated from ground level
 Ground station physically stable
 Battery ≥ 2 h runtime verified
 Antenna range adequate for 1 km
 Jury inspection and clearance obtained

The software enforces this — the ARM Telemetry button remains greyed out until every box is checked.

Configuring for Your Team
Open GCS_code.py and edit the constants at the top of the file:
pythonTEAM_ID             = "1001"      # Your assigned team ID
BATTERY_MAX_HOURS   = 2.0         # Required minimum runtime (hours)
ANTENNA_RANGE_KM    = 1.0         # Horizontal distance to launch pad (km)
BATTERY_CAPACITY_WH = 59.2        # Your battery pack capacity (V × Ah)
No other changes are needed for a standard competition setup.

Troubleshooting
Browser shows "127.0.0.1 refused to connect"
The Python server is not running yet. Run python GCS_code.py in a terminal first, wait for the line Dash is running on http://127.0.0.1:8050/, then open the browser.
ModuleNotFoundError on startup
A dependency is missing. Run pip install dash dash-bootstrap-components dash-leaflet plotly pyserial and try again.
Arduino connected but no live data

Check that MPU6050_gcs.ino is flashed and the Arduino's Serial Monitor shows data at 9600 baud.
If auto-detect failed, pick the correct port from the dropdown and click Connect.
On Linux you may need sudo usermod -aG dialout $USER (then log out and back in) to access serial ports without root.

Download button produces an empty CSV
The file is created the moment you run the script. If you click download before the first telemetry tick arrives (within the first second), it will contain only the header row. Wait a few seconds and try again.
Port 8050 already in use
Change the port at the bottom of GCS_code.py:
pythonapp.run(debug=True, use_reloader=False, port=8060)
Then visit http://127.0.0.1:8060.

Dependencies
PackageVersion testedPurposedash2.xWeb framework and callback enginedash-bootstrap-components1.xDark-themed UI componentsdash-leaflet0.xInteractive GPS mapplotly5.xLive scrolling graphspyserial3.xUSB serial communication with Arduino
All are installable via pip; no system-level packages required.

License
This project was developed for the IN-SPACe Model Rocketry India Student Competition 2026 by SEDS BPHC, Team ID 1001. All rights reserved.
