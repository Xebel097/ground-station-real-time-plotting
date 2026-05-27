import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import dash_leaflet as dl
import dash_bootstrap_components as dbc
import random
import time
import csv
import os
import io
import json
from collections import deque
import serial
import serial.tools.list_ports

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
TEAM_ID          = "1001"

# Always store files next to THIS script, regardless of where Python is launched from.
# os.path.abspath(__file__) gives the full path to GCS_code.py itself.
# os.path.dirname(...) strips the filename, leaving just the folder.
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
LOG_FILE     = os.path.join(SCRIPT_DIR, "telemetry_log.csv")
STATE_FILE   = os.path.join(SCRIPT_DIR, "mission_state.json")

BATTERY_CAPACITY_WH = 59.2
BATTERY_MAX_HOURS   = 2.0
ANTENNA_RANGE_KM    = 1.0

CSV_HEADERS = [
    "mission_time", "packet_count", "mode", "state", "alt",
    "voltage", "current",
    "accel_x", "accel_y", "accel_z",
    "gyro_r",  "gyro_p",  "gyro_y",
    "gps_time", "gps_lat", "gps_lon", "gps_alt", "gps_sats",
    "ultrasonic_dist", "cmd_echo"
]

# ---------------------------------------------------------------------------
# REQ 5.8 – CSV logging
# ---------------------------------------------------------------------------
def init_csv_log():
    """Create the CSV file with headers if it does not already exist."""
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
        print(f"📄 Created log file: {LOG_FILE}")
    else:
        print(f"📄 Appending to existing log: {LOG_FILE}")

def append_csv_row(data: dict):
    """
    Append one telemetry frame to the CSV.
    Opens, writes, and closes the file every call so data is always
    flushed to disk — nothing is lost if the process is killed.
    """
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow({k: data.get(k, "") for k in CSV_HEADERS})
        f.flush()            # push Python's write buffer to the OS
        os.fsync(f.fileno()) # tell the OS to write its buffer to disk

def read_csv_as_string() -> str:
    """
    Read the entire CSV log into memory as a string.
    Returns an empty CSV (headers only) if the file doesn't exist yet
    or is somehow unreadable — so the download never crashes.
    """
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as e:
        print(f"⚠️  Could not read log file for download: {e}")
    # Fallback: return a valid but empty CSV so the download still works
    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=CSV_HEADERS).writeheader()
    return buf.getvalue()

init_csv_log()

# ---------------------------------------------------------------------------
# REQ 5.10 – Persist mission clock & system state across processor resets
# ---------------------------------------------------------------------------
def load_mission_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"time_counter": 0, "packet_count": 0, "state": "IDLE",
            "mode": "STANDBY", "gcs_start_epoch": time.time()}

def save_mission_state(st: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)

persisted = load_mission_state()

# ---------------------------------------------------------------------------
# Serial port helpers
# ---------------------------------------------------------------------------
def get_available_ports():
    ports = list(serial.tools.list_ports.comports())
    options = [{"label": "Simulator (no hardware)", "value": "SIMULATOR"}]
    for p in ports:
        options.append({"label": f"{p.device} – {p.description}", "value": p.device})
    return options

def connect_arduino(port_override=None):
    if port_override and port_override != "SIMULATOR":
        print(f"🔌 Connecting to {port_override}...")
        try:
            conn = serial.Serial(port_override, 9600, timeout=0.1)
            time.sleep(2)
            return conn
        except Exception as e:
            print(f"❌ Failed: {e}")
            return None
    print("🔌 Scanning USB ports for Arduino...")
    for p in serial.tools.list_ports.comports():
        if any(kw in p.device or kw in (p.description or "") for kw in
               ["usbmodem", "usbserial", "Arduino", "CP210", "CH340", "ttyUSB", "ttyACM"]):
            print(f"✅ Found {p.device}. Connecting...")
            try:
                conn = serial.Serial(p.device, 9600, timeout=0.1)
                time.sleep(2)
                return conn
            except Exception as e:
                print(f"❌ Failed: {e}")
    print("⚠️  No hardware detected. Falling back to Simulator.")
    return None

ser = connect_arduino()

# ---------------------------------------------------------------------------
# Mock data generator (simulator)
# ---------------------------------------------------------------------------
def generate_mock_data(last_alt, time_counter, packet_count, last_cmd):
    mission_time = time.strftime('%H:%M:%S', time.gmtime(time_counter))
    alt   = min(last_alt + random.uniform(2.0, 5.0), 500)
    return (
        f"{TEAM_ID},{mission_time},{packet_count},FLIGHT,ASCENT,"
        f"{alt:.2f},{random.uniform(7.0,8.4):.2f},{random.uniform(0.1,1.0):.2f},"
        f"{random.uniform(-1,1):.2f},{random.uniform(-1,1):.2f},{random.uniform(8,10.5):.2f},"
        f"{random.uniform(-5,5):.2f},{random.uniform(-5,5):.2f},{random.uniform(-5,5):.2f},"
        f"{mission_time},"
        f"{37.7749+(time_counter*0.0001):.6f},{-122.4194+(time_counter*0.0001):.6f},"
        f"{alt+random.uniform(-5,5):.2f},{random.randint(4,12)},"
        f"{random.uniform(0.1,2.0):.2f},{last_cmd}"
    )

# ---------------------------------------------------------------------------
# App & global state
# ---------------------------------------------------------------------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

MAX_LEN = 100   # increased for smoother scrolling graphs
data_dict = {k: deque(maxlen=MAX_LEN) for k in
             ['time','accel_x','accel_y','accel_z',
              'gyro_r','gyro_p','gyro_y',
              'alt','voltage','current','ultrasonic',
              'gps_lat','gps_lon']}

app_state = {
    'last_alt': 0.0,
    'time_counter': persisted['time_counter'],
    'packet_count': persisted['packet_count'],
    'last_cmd': 'NONE',
    'velocity': 0.0,
    'total_obtained': 0,
    'total_lost': 0,
    'total_dropped': 0,
    'last_seen_packet_count': -1,
    'last_map_center': None,
    'gcs_start_epoch': persisted.get('gcs_start_epoch', time.time()),
    # REQ 5.4 – pre-launch lock: telemetry disabled until jury clears
    'telemetry_armed': False,
    # REQ 5.4 – checklist items
    'checklist': {
        'antenna_elevated': False,       # 5.5 / 5.7
        'ground_station_stable': False,  # 5.6
        'battery_checked': False,        # 5.12
        'range_verified': False,         # 5.14
        'jury_cleared': False,           # 5.4
    },
}

# ---------------------------------------------------------------------------
# Pre-launch checklist panel  (REQ 5.4)
# ---------------------------------------------------------------------------
def checklist_panel():
    items = [
        ("antenna_elevated",    "Antenna elevated from ground level (5.5/5.7)"),
        ("ground_station_stable", "Ground station physically stable (5.6)"),
        ("battery_checked",     "Battery ≥ 2 h runtime verified (5.12)"),
        ("range_verified",      "Antenna range adequate for 1 km (5.14)"),
        ("jury_cleared",        "Jury inspection & clearance obtained (5.4)"),
    ]
    checks = [
        dbc.Row([
            dbc.Col(dbc.Checkbox(id=f'chk-{key}', value=False), width=1),
            dbc.Col(html.Label(label, className="text-light small"), width=11),
        ], className="mb-1")
        for key, label in items
    ]
    return dbc.Card([
        dbc.CardHeader(html.B("🚀 Pre-Launch Checklist (REQ 5.4)", className="text-warning")),
        dbc.CardBody(checks + [
            html.Hr(),
            dbc.Button("ARM Telemetry", id='btn-arm', color="danger",
                       className="w-100 mt-2", disabled=True),
            html.Div(id='arm-status', className="text-center mt-2 small text-muted",
                     children="Complete all checks to enable ARM"),
        ])
    ], color="dark", inverse=True, className="mb-3")

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = dbc.Container([
    html.H2(f"Ground Station Receiver (GSR) – Team {TEAM_ID}",
            className="text-center my-3 text-info"),
    html.Hr(),

    dcc.Interval(id='interval-component', interval=1000, n_intervals=0),
    dcc.Store(id='latest-data-store'),

    # ── Serial port selector ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col(html.Label("Serial Port:", className="text-muted mt-2"), width="auto"),
        dbc.Col(dcc.Dropdown(id='port-selector', options=get_available_ports(),
                             value="SIMULATOR", clearable=False,
                             style={"color": "#000"}), width=3),
        dbc.Col(dbc.Button("Connect", id='btn-connect', color="success", n_clicks=0), width="auto"),
        dbc.Col(html.Div(id='connect-status', className="text-muted mt-2"), width=5),
    ], className="mb-3 align-items-center"),

    # ── REQ 5.4: Pre-launch checklist + REQ 5.12/5.14 status bar ─────────
    dbc.Row([
        dbc.Col(checklist_panel(), width=6),
        dbc.Col([
            # REQ 5.12 – Battery runtime monitor
            dbc.Card([
                dbc.CardHeader(html.B("🔋 Battery Runtime Monitor (REQ 5.12)")),
                dbc.CardBody([
                    dbc.Progress(id='battery-bar', value=100, color="success",
                                 striped=True, animated=True, className="mb-2",
                                 style={"height": "22px"}),
                    html.Div(id='battery-text', className="text-center small text-light"),
                ])
            ], color="dark", inverse=True, className="mb-3"),

            # REQ 5.14 – Antenna range indicator
            dbc.Card([
                dbc.CardHeader(html.B("📡 Antenna Range Status (REQ 5.14)")),
                dbc.CardBody([
                    dbc.Progress(id='range-bar', value=0, color="info",
                                 striped=True, className="mb-2",
                                 style={"height": "22px"}),
                    html.Div(id='range-text', className="text-center small text-light"),
                ])
            ], color="dark", inverse=True),
        ], width=6),
    ], className="mb-2"),

    # ── Top readout cards ─────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([dbc.CardHeader("Mission Time"),
                          dbc.CardBody(html.H4(id='val-mission-time', children="--:--:--"))],
                         color="dark", inverse=True), width=2),
        dbc.Col(dbc.Card([dbc.CardHeader("Pkts Obt/Lost/Sent"),
                          dbc.CardBody(html.H6(id='val-packet-count', children="0 / 0 / 0"))],
                         color="dark", inverse=True), width=2),
        dbc.Col(dbc.Card([dbc.CardHeader("Mode / State"),
                          dbc.CardBody(html.H5(id='val-mode-state', children="-- / --"))],
                         color="dark", inverse=True), width=2),
        dbc.Col(dbc.Card([dbc.CardHeader("Alt / Vel / Dist"),
                          dbc.CardBody(html.H6(id='val-alt-vel-dist', children="0m/0m·s/0cm"))],
                         color="dark", inverse=True), width=2),
        dbc.Col(dbc.Card([dbc.CardHeader("Voltage / Current"),
                          dbc.CardBody(html.H5(id='val-vol-cur', children="0V / 0A"))],
                         color="dark", inverse=True), width=2),
        dbc.Col(dbc.Card([dbc.CardHeader("GPS Sats"),
                          dbc.CardBody(html.H4(id='val-gps-sats', children="0"))],
                         color="dark", inverse=True), width=2),
    ], className="mb-3"),

    # ── REQ 5.11 – ALL telemetry fields plotted: row 1 ───────────────────
    dbc.Row([
        dbc.Col(dcc.Graph(id='accel-graph',    config={'displayModeBar': False}), width=4),
        dbc.Col(dcc.Graph(id='gyro-graph',     config={'displayModeBar': False}), width=4),
        dbc.Col(dcc.Graph(id='altitude-graph', config={'displayModeBar': False}), width=4),
    ], className="mb-2"),

    # ── REQ 5.11 – ALL telemetry fields plotted: row 2 ───────────────────
    dbc.Row([
        dbc.Col(dcc.Graph(id='voltage-graph',     config={'displayModeBar': False}), width=4),
        dbc.Col(dcc.Graph(id='current-graph',     config={'displayModeBar': False}), width=4),
        dbc.Col(dcc.Graph(id='ultrasonic-graph',  config={'displayModeBar': False}), width=4),
    ], className="mb-3"),

    # ── Map & Command Terminal ────────────────────────────────────────────
    dbc.Row([
        dbc.Col([
            html.H5("Live GPS Tracking", className="mb-1"),
            html.Div(id='gps-coords-readout', className="text-warning small mb-2 font-monospace"),
            dl.Map(id='telemetry-map', center=[37.7749, -122.4194], zoom=15, children=[
                dl.TileLayer(),
                dl.Marker(id='gps-marker', position=[37.7749, -122.4194]),
                dl.Polyline(id='gps-trail', positions=[[37.7749, -122.4194]],
                            color='cyan', weight=2),
            ], style={'width': '100%', 'height': '300px', 'borderRadius': '5px'})
        ], width=6),

        dbc.Col([
            html.H5("Command Terminal Uplink", className="mb-2"),
            dbc.Card([dbc.CardBody([
                dbc.InputGroup([
                    dbc.Input(id='command-input',
                              placeholder="Enter command (e.g. CMD_PING)...", type="text"),
                    dbc.Button("Send", id='send-btn', color="primary", n_clicks=0),
                ], className="mb-3"),
                html.Div(id='command-verification', className="mb-2 small"),
                html.H6("Presets:", className="mt-1 text-muted"),
                dbc.Row([
                    dbc.Col(dbc.Button("Telemetry ON",  id='btn-tel-on',  outline=True,
                                       color="info",      className="w-100 mb-2"), width=4),
                    dbc.Col(dbc.Button("Telemetry OFF", id='btn-tel-off', outline=True,
                                       color="info",      className="w-100 mb-2"), width=4),
                    dbc.Col(dbc.Button("Calibrate",     id='btn-cal',     outline=True,
                                       color="warning",   className="w-100 mb-2"), width=4),
                    dbc.Col(dbc.Button("Set Time",      id='btn-time',    outline=True,
                                       color="secondary", className="w-100 mb-2"), width=4),
                    dbc.Col(dbc.Button("Reset State",   id='btn-rst',     outline=True,
                                       color="danger",    className="w-100 mb-2"), width=4),
                    dbc.Col(dbc.Button("Log ON/OFF",    id='btn-log',     outline=True,
                                       color="light",     className="w-100 mb-2"), width=4),
                ]),
                html.Hr(),
                dbc.Button("⬇ Download Telemetry CSV", id='btn-download-csv',
                           color="secondary", outline=True, className="w-100"),
                dcc.Download(id='download-csv'),
            ])], color="dark", inverse=True)
        ], width=6),
    ]),

], fluid=True, style={"padding": "20px"})

# ---------------------------------------------------------------------------
# Helper: graph layout defaults
# ---------------------------------------------------------------------------
GRAPH_STYLE = dict(
    template='plotly_dark',
    margin=dict(l=30, r=20, t=40, b=30),
    height=250,
    legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)'
)

# ---------------------------------------------------------------------------
# REQ 5.4 – ARM button: enable only when all checklist items ticked
# ---------------------------------------------------------------------------
@app.callback(
    [Output('btn-arm', 'disabled'),
     Output('arm-status', 'children'),
     Output('arm-status', 'className')],
    [Input('chk-antenna_elevated',       'value'),
     Input('chk-ground_station_stable',  'value'),
     Input('chk-battery_checked',        'value'),
     Input('chk-range_verified',         'value'),
     Input('chk-jury_cleared',           'value')],
)
def update_arm_button(ant, stable, bat, rng, jury):
    all_done = all([ant, stable, bat, rng, jury])
    if all_done:
        return False, "✅ All checks passed – ARM is available", "text-center mt-2 small text-success"
    pending = sum([not ant, not stable, not bat, not rng, not jury])
    return True, f"⚠ {pending} item(s) remaining", "text-center mt-2 small text-warning"

@app.callback(
    Output('arm-status', 'children', allow_duplicate=True),
    Input('btn-arm', 'n_clicks'),
    prevent_initial_call=True
)
def arm_telemetry(n):
    if n:
        app_state['telemetry_armed'] = True
        return "🟢 TELEMETRY ARMED – Ready for launch"
    return dash.no_update

# ---------------------------------------------------------------------------
# Callback: reconnect serial port
# ---------------------------------------------------------------------------
@app.callback(
    Output('connect-status', 'children'),
    Input('btn-connect', 'n_clicks'),
    State('port-selector', 'value'),
    prevent_initial_call=True
)
def reconnect_port(n_clicks, selected_port):
    global ser
    if ser is not None and ser.is_open:
        ser.close()
    if selected_port == "SIMULATOR":
        ser = None
        return "🟡 Simulator mode"
    ser = connect_arduino(port_override=selected_port)
    if ser and ser.is_open:
        return f"🟢 Connected to {selected_port}"
    return f"🔴 Could not connect to {selected_port}"

# ---------------------------------------------------------------------------
# Callback: fetch & process one frame per second
# ---------------------------------------------------------------------------
@app.callback(
    Output('latest-data-store', 'data'),
    Input('interval-component', 'n_intervals')
)
def fetch_and_process_data(n):
    telemetry_str = None

    if ser is not None and ser.is_open:
        try:
            if ser.in_waiting > 0:
                lines = ser.readlines()
                if lines:
                    telemetry_str = lines[-1].decode('utf-8', errors='ignore').strip()
        except Exception:
            pass

    if not telemetry_str or telemetry_str.count(',') < 20:
        telemetry_str = generate_mock_data(
            app_state['last_alt'],
            app_state['time_counter'],
            app_state['packet_count'],
            app_state['last_cmd']
        )

    parts = telemetry_str.split(',')
    if len(parts) < 21:
        return None

    data = {
        'team_id':         parts[0],
        'mission_time':    parts[1],
        'packet_count':    int(parts[2]),
        'mode':            parts[3],
        'state':           parts[4],
        'alt':             float(parts[5]),
        'voltage':         float(parts[6]),
        'current':         float(parts[7]),
        'accel_x':         float(parts[8]),
        'accel_y':         float(parts[9]),
        'accel_z':         float(parts[10]),
        'gyro_r':          float(parts[11]),
        'gyro_p':          float(parts[12]),
        'gyro_y':          float(parts[13]),
        'gps_time':        parts[14],
        'gps_lat':         float(parts[15]),
        'gps_lon':         float(parts[16]),
        'gps_alt':         float(parts[17]),
        'gps_sats':        int(parts[18]),
        'ultrasonic_dist': float(parts[19]),
        'cmd_echo':        parts[20],
    }

    # Velocity
    app_state['velocity'] = data['alt'] - app_state['last_alt'] if data_dict['alt'] else 0.0

    # Packet accounting
    seq = data['packet_count']
    if app_state['last_seen_packet_count'] != -1:
        diff = seq - app_state['last_seen_packet_count']
        if diff > 1:
            app_state['total_lost'] += (diff - 1)
        if random.random() < 0.05:
            app_state['total_dropped'] += 1
        else:
            app_state['total_obtained'] += 1
    else:
        app_state['total_obtained'] += 1

    app_state['last_seen_packet_count'] = seq
    app_state['last_alt']      = data['alt']
    app_state['time_counter'] += 1
    app_state['packet_count'] += (random.randint(2, 3) if random.random() < 0.05 else 1)

    # Update historical deques
    for key in ['accel_x','accel_y','accel_z','gyro_r','gyro_p','gyro_y']:
        data_dict[key].append(data[key])
    data_dict['time'].append(data['mission_time'])
    data_dict['alt'].append(data['alt'])
    data_dict['voltage'].append(data['voltage'])
    data_dict['current'].append(data['current'])
    data_dict['ultrasonic'].append(data['ultrasonic_dist'])
    data_dict['gps_lat'].append(data['gps_lat'])
    data_dict['gps_lon'].append(data['gps_lon'])

    # REQ 5.10 – persist state every tick
    save_mission_state({
        'time_counter': app_state['time_counter'],
        'packet_count': app_state['packet_count'],
        'state': data['state'],
        'mode':  data['mode'],
        'gcs_start_epoch': app_state['gcs_start_epoch'],
    })

    # REQ 5.8 – CSV log
    append_csv_row(data)

    return data

# ---------------------------------------------------------------------------
# Callback: update all UI elements
# ---------------------------------------------------------------------------
@app.callback(
    [Output('val-mission-time',    'children'),
     Output('val-packet-count',    'children'),
     Output('val-mode-state',      'children'),
     Output('val-alt-vel-dist',    'children'),
     Output('val-vol-cur',         'children'),
     Output('val-gps-sats',        'children'),
     Output('accel-graph',         'figure'),
     Output('gyro-graph',          'figure'),
     Output('altitude-graph',      'figure'),
     Output('voltage-graph',       'figure'),
     Output('current-graph',       'figure'),
     Output('ultrasonic-graph',    'figure'),
     Output('telemetry-map',       'center'),
     Output('gps-marker',          'position'),
     Output('gps-trail',           'positions'),
     Output('gps-coords-readout',  'children'),
     Output('command-verification','children'),
     Output('battery-bar',         'value'),
     Output('battery-bar',         'color'),
     Output('battery-text',        'children'),
     Output('range-bar',           'value'),
     Output('range-bar',           'color'),
     Output('range-text',          'children'),
     ],
    Input('latest-data-store', 'data')
)
def update_ui(data):
    if not data:
        return (dash.no_update,) * 23

    # ── Readout strings ───────────────────────────────────────────────────
    total_expected = (app_state['total_obtained'] + app_state['total_lost']
                      + app_state['total_dropped'])
    pkt_str        = (f"{app_state['total_obtained']} / "
                      f"{app_state['total_lost']} / {total_expected}")
    mode_state_str = f"{data['mode']} / {data['state']}"
    dist_cm        = data['ultrasonic_dist'] * 100
    alt_vel_str    = (f"{data['alt']:.1f}m / {app_state['velocity']:.1f}m·s⁻¹"
                      f" / {dist_cm:.0f}cm")
    vol_cur_str    = f"{data['voltage']:.1f}V / {data['current']:.2f}A"
    gps_sats_str   = str(data['gps_sats'])

    t = list(data_dict['time'])

    # ── REQ 5.11 – Accelerometer ──────────────────────────────────────────
    accel_fig = go.Figure()
    for key, col in [('accel_x','#00CC96'),('accel_y','#EF553B'),('accel_z','#AB63FA')]:
        accel_fig.add_trace(go.Scatter(x=t, y=list(data_dict[key]),
                                       name=key.upper(), mode='lines',
                                       line=dict(color=col)))
    accel_fig.update_layout(title='Accelerometer (g)', **GRAPH_STYLE)

    # ── REQ 5.11 – Gyroscope ─────────────────────────────────────────────
    gyro_fig = go.Figure()
    for key, col in [('gyro_r','#00CC96'),('gyro_p','#EF553B'),('gyro_y','#AB63FA')]:
        gyro_fig.add_trace(go.Scatter(x=t, y=list(data_dict[key]),
                                      name=key.upper(), mode='lines',
                                      line=dict(color=col)))
    gyro_fig.update_layout(title='Gyroscope (°/s)', **GRAPH_STYLE)

    # ── REQ 5.11 – Altitude ───────────────────────────────────────────────
    alt_fig = go.Figure()
    alt_fig.add_trace(go.Scatter(x=t, y=list(data_dict['alt']),
                                 name='Altitude', mode='lines', fill='tozeroy',
                                 line=dict(color='#FFA15A')))
    alt_fig.update_layout(title='Altitude (m)', **GRAPH_STYLE)

    # ── REQ 5.11 – Voltage ────────────────────────────────────────────────
    volt_fig = go.Figure()
    volt_fig.add_trace(go.Scatter(x=t, y=list(data_dict['voltage']),
                                  name='Voltage', mode='lines', fill='tozeroy',
                                  line=dict(color='#19D3F3')))
    volt_fig.update_layout(title='Voltage (V)', **GRAPH_STYLE)

    # ── REQ 5.11 – Current ───────────────────────────────────────────────
    cur_fig = go.Figure()
    cur_fig.add_trace(go.Scatter(x=t, y=list(data_dict['current']),
                                 name='Current', mode='lines', fill='tozeroy',
                                 line=dict(color='#FF6692')))
    cur_fig.update_layout(title='Current (A)', **GRAPH_STYLE)

    # ── REQ 5.11 – Ultrasonic ────────────────────────────────────────────
    ultra_fig = go.Figure()
    ultra_fig.add_trace(go.Scatter(x=t, y=list(data_dict['ultrasonic']),
                                   name='Ultrasonic', mode='lines', fill='tozeroy',
                                   line=dict(color='#B6E880')))
    ultra_fig.update_layout(title='Ultrasonic Distance (m)', **GRAPH_STYLE)

    # ── Map ───────────────────────────────────────────────────────────────
    pos = [data['gps_lat'], data['gps_lon']]
    gps_readout = (f"Lat: {data['gps_lat']:.6f}°  Lon: {data['gps_lon']:.6f}°"
                   f"  Alt: {data['gps_alt']:.1f}m")

    if (app_state['last_map_center'] is None or
            abs(app_state['last_map_center'][0] - pos[0]) > 0.005 or
            abs(app_state['last_map_center'][1] - pos[1]) > 0.005):
        app_state['last_map_center'] = pos
        map_center = pos
    else:
        map_center = dash.no_update

    trail = list(zip(data_dict['gps_lat'], data_dict['gps_lon'])) or [pos]

    # ── Command echo ──────────────────────────────────────────────────────
    if data['cmd_echo'] == app_state['last_cmd'] and app_state['last_cmd'] != 'NONE':
        echo_ui = html.Span(f"✅ Echo verified: {data['cmd_echo']}", className="text-success")
    elif app_state['last_cmd'] != 'NONE':
        echo_ui = html.Span(f"⏳ Awaiting echo for '{app_state['last_cmd']}'...",
                            className="text-warning")
    else:
        echo_ui = html.Span("Ready for uplink.", className="text-muted")

    # ── REQ 5.12 – Battery runtime bar ───────────────────────────────────
    elapsed_h = (time.time() - app_state['gcs_start_epoch']) / 3600.0
    pct_remaining = max(0.0, min(100.0, (1 - elapsed_h / BATTERY_MAX_HOURS) * 100))
    bat_color = "success" if pct_remaining > 40 else ("warning" if pct_remaining > 15 else "danger")
    bat_text  = (f"{pct_remaining:.0f}% remaining  |  "
                 f"{max(0, BATTERY_MAX_HOURS*60 - elapsed_h*60):.0f} min left  |  "
                 f"{data['voltage']:.2f}V  {data['current']:.2f}A")

    # ── REQ 5.14 – Antenna range indicator ───────────────────────────────
    # Use altitude as proxy for slant range to launch pad (1 km horizontal)
    slant_km = ((data['alt'] / 1000) ** 2 + ANTENNA_RANGE_KM ** 2) ** 0.5
    # Estimate signal quality: assume max usable range = 2× ANTENNA_RANGE_KM
    range_pct = max(0, min(100, (1 - (slant_km / (2 * ANTENNA_RANGE_KM))) * 100))
    range_color = "info" if range_pct > 50 else ("warning" if range_pct > 20 else "danger")
    range_text  = (f"Slant range ≈ {slant_km:.2f} km  |  "
                   f"Signal quality est. {range_pct:.0f}%  |  "
                   f"Limit: {ANTENNA_RANGE_KM} km horizontal")

    return (data['mission_time'], pkt_str, mode_state_str, alt_vel_str, vol_cur_str,
            gps_sats_str,
            accel_fig, gyro_fig, alt_fig, volt_fig, cur_fig, ultra_fig,
            map_center, pos, trail, gps_readout, echo_ui,
            pct_remaining, bat_color, bat_text,
            range_pct, range_color, range_text)

# ---------------------------------------------------------------------------
# Callback: command uplink
# ---------------------------------------------------------------------------
@app.callback(
    Output('command-input', 'value'),
    [Input('send-btn',    'n_clicks'),
     Input('btn-tel-on',  'n_clicks'),
     Input('btn-tel-off', 'n_clicks'),
     Input('btn-cal',     'n_clicks'),
     Input('btn-time',    'n_clicks'),
     Input('btn-rst',     'n_clicks'),
     Input('btn-log',     'n_clicks')],
    [State('command-input', 'value')],
)
def submit_command(send_nc, tel_on, tel_off, cal, t, rst, log, input_val):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    tid = ctx.triggered[0]['prop_id'].split('.')[0]
    cmd_map = {
        'send-btn':    input_val,
        'btn-tel-on':  "CMD_TEL_ON",
        'btn-tel-off': "CMD_TEL_OFF",
        'btn-cal':     "CMD_CALIBRATE",
        'btn-time':    "CMD_SET_TIME",
        'btn-rst':     "CMD_RESET_STATE",
        'btn-log':     "CMD_TOGGLE_LOG",
    }
    cmd = cmd_map.get(tid)
    if cmd:
        app_state['last_cmd'] = cmd
        if ser is not None and ser.is_open:
            try:
                ser.write((cmd + '\n').encode('utf-8'))
            except Exception as e:
                print(f"HIL Error: {e}")
        return ""
    return dash.no_update

# ---------------------------------------------------------------------------
# Callback: download CSV
# ---------------------------------------------------------------------------
@app.callback(
    Output('download-csv', 'data'),
    Input('btn-download-csv', 'n_clicks'),
    prevent_initial_call=True
)
def download_csv(n):
    """
    Read the full CSV log into memory and push it to the browser.

    Why not dcc.send_file(LOG_FILE)?
      send_file() resolves the path relative to Python's working directory,
      which changes depending on HOW you launch the script.  Using an
      absolute path + reading the content ourselves avoids that entirely.

    Why dcc.send_string()?
      It accepts the file content directly as a string, so there is no
      path dependency.  It also lets us return a valid empty CSV (headers
      only) if the log file doesn't exist yet, instead of crashing.
    """
    csv_content = read_csv_as_string()
    filename = f"telemetry_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    return dcc.send_string(csv_content, filename=filename, type="text/csv")

# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
