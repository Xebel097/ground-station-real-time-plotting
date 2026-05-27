A real-time telemetry dashboard for the Hyperion model rocket. Built in Python using Dash, it receives sensor data from an Arduino over USB/XBee serial, displays all channels as live scrolling graphs, tracks the rocket on a GPS map, logs everything to CSV, and allows command uplink back to the vehicle.

---

## Features

| Feature | Details |
|---|---|
| Live graphs | Accelerometer (X/Y/Z), Gyroscope (R/P/Y), Altitude, Voltage, Current, Ultrasonic — all 6 update every second |
| GPS map | Live marker + cyan trail polyline on OpenStreetMap via Dash Leaflet |
| CSV logging | Every telemetry frame written to `telemetry_log.csv` with flush + fsync — no data loss on crash |
| State persistence | Mission clock and packet count saved to `mission_state.json` every second; survives laptop restarts |
| Pre-launch checklist | 5-item checklist gates the ARM button; telemetry cannot be armed before jury clearance |
| Battery monitor | Countdown bar from 100 % over the required 2-hour runtime; turns yellow at 40 %, red at 15 % |
| Antenna range | Slant-range estimator using rocket altitude + 1 km horizontal distance to pad |
| Command uplink | Send preset or custom commands to the Arduino over serial; echo verification shown in the UI |
| CSV download | Download the full log as a timestamped file directly from the browser at any point during flight |
| Simulator mode | Works with no hardware connected — generates realistic fake sensor data so the UI can be tested anywhere |
| Port selector | Switch serial port live from the UI dropdown without restarting Python |

---

## Requirements Compliance

| Req | Description | Status |
|---|---|---|
| 5.4 | Telemetry command only after jury inspection & clearance | ✅ ARM button locked behind 5-item checklist |
| 5.5 / 5.7 | Antenna elevated from ground level | ✅ Checklist item; operator-verified |
| 5.6 | Ground station physically stable | ✅ Checklist item; operator-verified |
| 5.8 | Ground station generates CSV of all sensor data | ✅ Auto-logged to `telemetry_log.csv` |
| 5.9 | Mission time with ≤ 1-second resolution | ✅ 1 Hz update interval |
| 5.10 | Mission clock & state maintained across processor resets | ✅ `mission_state.json` persists every second |
| 5.11 | All telemetry fields plotted in real-time | ✅ 6 live graphs covering all 13 sensor channels |
| 5.12 | Laptop with minimum 2-hour battery operation | ✅ Battery countdown bar with colour-coded warnings |
| 5.13 | Ground station portable, operable from flight line | ✅ Runs on any laptop; single Python file, no installation beyond pip |
| 5.14 | Antenna range adequate for 1 km launch pad distance | ✅ Slant-range indicator computed from altitude |

---

## Hardware

| Component | Purpose |
|---|---|
| Arduino (Uno / Nano / Mega) | Reads all sensors, formats telemetry string, sends over serial |
| MPU-6050 | 3-axis accelerometer + 3-axis gyroscope |
| GPS module (NMEA, e.g. Neo-6M) | Position, altitude, satellite count |
| HC-SR04 ultrasonic sensor | Distance to ground |
| XBee radio + hand-held antenna | Wireless telemetry link at competition site |
| Laptop | Runs `GCS_code.py`; must have ≥ 2 h battery |

---

## Telemetry Packet Format

The Arduino sends one comma-separated line per second at **9600 baud**:

```
TEAM_ID, MISSION_TIME, PACKET_COUNT, MODE, STATE,
ALT, VOLTAGE, CURRENT,
ACCEL_X, ACCEL_Y, ACCEL_Z,
GYRO_R, GYRO_P, GYRO_Y,
GPS_TIME, GPS_LAT, GPS_LON, GPS_ALT, GPS_SATS,
ULTRASONIC_DIST, CMD_ECHO
```

Example:
```
1001,00:01:23,83,FLIGHT,ASCENT,142.30,7.85,0.42,-0.02,0.01,9.81,-1.2,0.4,0.1,00:01:23,37.774935,-122.419381,147.20,9,0.45,CMD_TEL_ON
```

---

## CSV Log Format

`telemetry_log.csv` is created automatically in the same folder as `GCS_code.py` the first time the script is run. Columns:

```
mission_time, packet_count, mode, state, alt,
voltage, current,
accel_x, accel_y, accel_z,
gyro_r, gyro_p, gyro_y,
gps_time, gps_lat, gps_lon, gps_alt, gps_sats,
ultrasonic_dist, cmd_echo
```

To download a timestamped copy mid-flight, click **"⬇ Download Telemetry CSV"** in the command terminal panel.

---

## Installation

**Python 3.8 or later required.**

Install all dependencies in one command:

```bash
pip install dash dash-bootstrap-components dash-leaflet plotly pyserial
```

---

## Running the GCS

```bash
python GCS_code.py
```

Then open your browser and go to:

```
http://127.0.0.1:8050
```

The dashboard starts in **Simulator mode** automatically if no Arduino is detected. Fake sensor data will stream in so you can verify the UI without hardware.

### With hardware connected

1. Flash `MPU6050_gcs.ino` to the Arduino using the Arduino IDE.
2. Connect the Arduino via USB.
3. Run `python GCS_code.py` — it auto-detects the port.
4. If auto-detect fails, use the **Serial Port** dropdown in the UI to select the correct port manually and click **Connect**.

### Port names by OS

| OS | Typical port name |
|---|---|
| Windows | `COM3`, `COM4`, … |
| macOS | `/dev/cu.usbmodem…`, `/dev/cu.usbserial…` |
| Linux | `/dev/ttyUSB0`, `/dev/ttyACM0` |

---

## Pre-Launch Checklist (REQ 5.4)

Before the ARM button becomes available, an operator must tick all five items:

- [ ] Antenna elevated from ground level
- [ ] Ground station physically stable
- [ ] Battery ≥ 2 h runtime verified
- [ ] Antenna range adequate for 1 km
- [ ] Jury inspection and clearance obtained

The software enforces this — the **ARM Telemetry** button remains greyed out until every box is checked.

---

## Configuring for Your Team

Open `GCS_code.py` and edit the constants at the top of the file:

```python
TEAM_ID             = "1001"      # Your assigned team ID
BATTERY_MAX_HOURS   = 2.0         # Required minimum runtime (hours)
ANTENNA_RANGE_KM    = 1.0         # Horizontal distance to launch pad (km)
BATTERY_CAPACITY_WH = 59.2        # Your battery pack capacity (V × Ah)
```

No other changes are needed for a standard competition setup.

---

## Troubleshooting

**Browser shows "127.0.0.1 refused to connect"**
The Python server is not running yet. Run `python GCS_code.py` in a terminal first, wait for the line `Dash is running on http://127.0.0.1:8050/`, then open the browser.

**`ModuleNotFoundError` on startup**
A dependency is missing. Run `pip install dash dash-bootstrap-components dash-leaflet plotly pyserial` and try again.

**Arduino connected but no live data**
- Check that `MPU6050_gcs.ino` is flashed and the Arduino's Serial Monitor shows data at 9600 baud.
- If auto-detect failed, pick the correct port from the dropdown and click **Connect**.
- On Linux you may need `sudo usermod -aG dialout $USER` (then log out and back in) to access serial ports without root.

**Download button produces an empty CSV**
The file is created the moment you run the script. If you click download before the first telemetry tick arrives (within the first second), it will contain only the header row. Wait a few seconds and try again.

**Port 8050 already in use**
Change the port at the bottom of `GCS_code.py`:
```python
app.run(debug=True, use_reloader=False, port=8060)
```
Then visit `http://127.0.0.1:8060`.

---

## Dependencies

| Package | Version tested | Purpose |
|---|---|---|
| `dash` | 2.x | Web framework and callback engine |
| `dash-bootstrap-components` | 1.x | Dark-themed UI components |
| `dash-leaflet` | 0.x | Interactive GPS map |
| `plotly` | 5.x | Live scrolling graphs |
| `pyserial` | 3.x | USB serial communication with Arduino |

All are installable via `pip`; no system-level packages required.

---

## License

This project was developed for the IN-SPACe Model Rocketry India Student Competition 2026 by SEDS BPHC, Team ID 1001. All rights reserved.
