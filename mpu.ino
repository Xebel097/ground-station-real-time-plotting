// ============================================================
//  ROCKET TELEMETRY SIMULATOR — CAN-7USAT / IN-SPACe 2026
//  TM Format (per spec):
//  TEAM_ID, TIME_STAMP, PKT_COUNT, ALTITUDE, PRESSURE, TEMP,
//  VOLTAGE, GNSS_TIME, GNSS_LAT, GNSS_LON, GNSS_ALT,
//  GNSS_SATS, AX;AY;AZ, GYRO, FLIGHT_STATE, OPTIONAL
// ============================================================

// ---- Mission identity --------------------------------------
#define TEAM_ID       "2026 IN-SPACe-007"   // change XXX to your number

// ---- Simulation timing -------------------------------------
#define BAUD_RATE     115200
#define TICK_MS       250           // real-world ms between packets (4 Hz)
#define SIM_SPEED     5.0f          // 1.0 = real-time; 5.0 = 5x fast-forward

// ---- Mission event timestamps (simulation seconds) ---------
#define T_IGNITION    0.5f
#define T_BURNOUT     10.0f
#define T_APOGEE      18.0f
#define T_DROGUE      20.0f
#define T_MAIN        40.0f
#define T_LAND        195.0f
#define T_END         197.0f

// ---- Launch site (Ghaziabad area as placeholder) -----------
#define BASE_LAT      28.5000f      // 0.0001 deg resolution per spec
#define BASE_LON      77.3500f
#define BASE_ALT_MSL  200.0f        // ground elevation MSL (m)

// ---- Flight software states --------------------------------
typedef enum {
  STATE_BOOT    = 0,   // before ignition detected
  STATE_IDLE,          // pad wait
  STATE_LAUNCH_DETECT, // ignition confirmed
  STATE_POWERED_ASCENT,
  STATE_COAST,
  STATE_APOGEE,
  STATE_DROGUE_DEPLOY,
  STATE_MAIN_DEPLOY,
  STATE_LAND
} FlightState;

const char* STATE_NAMES[] = {
  "BOOT",
  "IDLE",
  "LAUNCH_DETECT",
  "POWERED_ASCENT",
  "COAST",
  "APOGEE",
  "DROGUE_DEPLOY",
  "MAIN_DEPLOY",
  "LAND"
};

// ---- Payload health states ---------------------------------
typedef enum {
  PL_INIT     = 0,
  PL_STANDBY,
  PL_ACTIVE,
  PL_NOMINAL,
  PL_FAULT
} PayloadState;

const char* PL_NAMES[] = {
  "PL:INIT",
  "PL:STANDBY",
  "PL:ACTIVE",
  "PL:NOMINAL",
  "PL:FAULT"
};

// ---- Runtime globals ---------------------------------------
static uint32_t packetCount  = 0;
static float    simTime      = 0.0f;   // sim clock (seconds since power-on)
static uint32_t wallMs       = 0;
static bool     missionDone  = false;

// ---- Lightweight PRNG (no stdlib) --------------------------
static uint32_t _seed = 42317UL;
float frand() {
  _seed ^= _seed << 13;
  _seed ^= _seed >> 17;
  _seed ^= _seed << 5;
  return (float)(_seed & 0x7FFF) / 32767.0f;   // 0.0 .. 1.0
}
float noise(float scale) { return (frand() - 0.5f) * 2.0f * scale; }

// ---- Math helpers ------------------------------------------
float lerpf(float a, float b, float t) { return a + (b - a) * t; }
float clampf(float v, float lo, float hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

// ---- Quantise to spec resolution ---------------------------
// altitude   : 0.1 m
// pressure   : 1 Pa   (integer)
// temperature: 0.1 °C
// voltage    : 0.01 V
// gnss lat/lon: 0.0001 deg
// gnss alt   : 0.1 m
float q1(float v)  { return (float)((int)(v * 10.0f + 0.5f)) / 10.0f; }   // 0.1 resolution
float q2(float v)  { return (float)((int)(v * 100.0f + 0.5f)) / 100.0f; } // 0.01 resolution
float q4(float v)  { return (float)((int)(v * 10000.0f + 0.5f)) / 10000.0f; } // 0.0001 deg

// ---- Flight models (tuned to chart) ------------------------

float altitudeModel(float t) {
  if (t < T_IGNITION) return 0.0f;
  if (t < T_APOGEE) {
    float pct = (t - T_IGNITION) / (T_APOGEE - T_IGNITION);
    return 1050.0f * (1.0f - pow(1.0f - pct, 1.6f));
  }
  if (t < T_DROGUE) return lerpf(1050.0f, 1040.0f, (t - T_APOGEE) / (T_DROGUE - T_APOGEE));
  if (t < T_MAIN)   return lerpf(1040.0f, 600.0f,  (t - T_DROGUE) / (T_MAIN   - T_DROGUE));
  if (t < T_LAND)   return lerpf(600.0f,   0.0f,   (t - T_MAIN)   / (T_LAND   - T_MAIN));
  return 0.0f;
}

float lateralDistModel(float t) {
  if (t < T_IGNITION) return 0.0f;
  if (t < T_BURNOUT)  return lerpf(0.0f,   5.0f,  (t - T_IGNITION) / (T_BURNOUT - T_IGNITION));
  if (t < T_APOGEE)   return lerpf(5.0f,  80.0f,  (t - T_BURNOUT)  / (T_APOGEE  - T_BURNOUT));
  if (t < T_DROGUE)   return lerpf(80.0f, 45.0f,  (t - T_APOGEE)   / (T_DROGUE  - T_APOGEE));
  if (t < 62.0f)      return lerpf(45.0f,  5.0f,  (t - T_DROGUE)   / (62.0f     - T_DROGUE));
  if (t < T_LAND)     return lerpf(5.0f, 275.0f,  (t - 62.0f)      / (T_LAND    - 62.0f));
  return 275.0f;
}

float pressureModel(float alt) {
  // ISA barometric formula
  return 101325.0f * pow(1.0f - 2.2557e-5f * alt, 5.2559f);
}

float temperatureModel(float alt) {
  // ISA standard lapse: 6.5 °C / 1000 m
  return 25.0f - alt * 0.0065f;
}

float voltageModel(float t) {
  // Slow drain over mission; spike recovery systems cause brief dips
  float base = 8.40f - t * 0.003f;
  if (t >= T_DROGUE && t < T_DROGUE + 0.5f) base -= 0.12f; // drogue pyro draw
  if (t >= T_MAIN   && t < T_MAIN   + 0.5f) base -= 0.10f; // main pyro draw
  return clampf(base, 7.00f, 8.40f);
}

// Accelerometer: dominant axis is Z (thrust axis)
float accelZ(float t) {
  if (t >= T_IGNITION && t < T_BURNOUT)
    return 9.81f + lerpf(45.0f, 2.0f, (t - T_IGNITION) / (T_BURNOUT - T_IGNITION)) + noise(1.5f);
  if (t >= T_DROGUE && t < T_DROGUE + 0.3f) return 9.81f + 18.0f + noise(3.0f); // drogue snap
  if (t >= T_MAIN   && t < T_MAIN   + 0.3f) return 9.81f + 12.0f + noise(2.0f); // main snap
  return 9.81f + noise(0.4f);
}
float accelX(float t) { (void)t; return noise(0.5f); }
float accelY(float t) { (void)t; return noise(0.5f); }

float gyroModel(float t) {
  if (t >= T_IGNITION && t < T_BURNOUT)      return 14.0f + noise(4.0f);
  if (t >= T_DROGUE   && t < T_DROGUE + 1.0f) return 35.0f + noise(8.0f);
  if (t >= T_MAIN     && t < T_MAIN   + 1.0f) return 22.0f + noise(6.0f);
  return 0.4f + noise(0.2f);
}

// ---- State machine resolver --------------------------------
FlightState resolveState(float t) {
  if (t < 0.2f)        return STATE_BOOT;
  if (t < T_IGNITION)  return STATE_IDLE;
  if (t < T_IGNITION + 0.5f) return STATE_LAUNCH_DETECT;
  if (t < T_BURNOUT)   return STATE_POWERED_ASCENT;
  if (t < T_APOGEE)    return STATE_COAST;
  if (t < T_DROGUE)    return STATE_APOGEE;
  if (t < T_MAIN)      return STATE_DROGUE_DEPLOY;
  if (t < T_LAND)      return STATE_MAIN_DEPLOY;
  return STATE_LAND;
}

// ---- Payload state resolver --------------------------------
// Optional data: payload working status
PayloadState resolvePayload(float t) {
  if (t < 0.2f)       return PL_INIT;
  if (t < T_IGNITION) return PL_STANDBY;
  if (t < T_APOGEE)   return PL_ACTIVE;
  if (t < T_LAND)     return PL_NOMINAL;
  // simulate a random fault 5% of land packets
  if (frand() < 0.05f) return PL_FAULT;
  return PL_NOMINAL;
}

// ---- GNSS time: seconds since midnight UTC -----------------
// Spec says: seconds. We output integer seconds from 08:00:00.
uint32_t gnssTimeSec(float t) {
  return (uint32_t)(8UL * 3600UL) + (uint32_t)t;
}

// ---- Print one telemetry line to Serial --------------------
void sendPacket(float t) {
  packetCount++;

  // --- compute all values ---
  float alt   = clampf(q1(altitudeModel(t)   + noise(0.3f)), 0.0f, 1200.0f);
  float pres  = (float)((long)(pressureModel(alt) + noise(5.0f)));  // 1 Pa resolution
  float temp  = q1(temperatureModel(alt)     + noise(0.2f));
  float volt  = q2(voltageModel(t)           + noise(0.005f));
  float ld    = clampf(lateralDistModel(t)   + noise(0.1f), 0.0f, 400.0f);
  float ax    = accelX(t);
  float ay    = accelY(t);
  float az    = accelZ(t);
  float gyro  = gyroModel(t);

  // GNSS — quantised to 0.0001 deg; altitude 0.1 m
  float gLat  = q4(BASE_LAT + ld * 9e-6f);
  float gLon  = q4(BASE_LON + ld * 5e-6f);
  float gAlt  = q1(BASE_ALT_MSL + alt + noise(1.5f));
  uint8_t gSats = (alt > 80.0f) ? 10 : 8;
  uint32_t gTime = gnssTimeSec(t);

  FlightState   fState  = resolveState(t);
  PayloadState  pState  = resolvePayload(t);

  // ---- Field 1: TEAM ID -----------------------------------
  Serial.print(TEAM_ID);             Serial.print(',');

  // ---- Field 2: TIME STAMP (seconds since power-on) -------
  Serial.print(t, 1);                Serial.print(',');

  // ---- Field 3: PACKET COUNT ------------------------------
  Serial.print(packetCount);         Serial.print(',');

  // ---- Field 4: ALTITUDE (0.1 m, relative to ground) -----
  Serial.print(alt, 1);              Serial.print(',');

  // ---- Field 5: PRESSURE (1 Pa) ---------------------------
  Serial.print((long)pres);          Serial.print(',');

  // ---- Field 6: TEMPERATURE (0.1 °C) ----------------------
  Serial.print(temp, 1);             Serial.print(',');

  // ---- Field 7: VOLTAGE (0.01 V) --------------------------
  Serial.print(volt, 2);             Serial.print(',');

  // ---- Field 8: GNSS TIME (seconds) -----------------------
  Serial.print(gTime);               Serial.print(',');

  // ---- Field 9: GNSS LATITUDE (0.0001 deg) ----------------
  Serial.print(gLat, 4);             Serial.print(',');

  // ---- Field 10: GNSS LONGITUDE (0.0001 deg) --------------
  Serial.print(gLon, 4);             Serial.print(',');

  // ---- Field 11: GNSS ALTITUDE (0.1 m) --------------------
  Serial.print(gAlt, 1);             Serial.print(',');

  // ---- Field 12: GNSS SATS --------------------------------
  Serial.print(gSats);               Serial.print(',');

  // ---- Field 13: ACCELEROMETER DATA (AX;AY;AZ in m/s²) ---
  Serial.print(ax, 2); Serial.print(';');
  Serial.print(ay, 2); Serial.print(';');
  Serial.print(az, 2);               Serial.print(',');

  // ---- Field 14: GYRO SPIN RATE (deg/s) -------------------
  Serial.print(gyro, 2);             Serial.print(',');

  // ---- Field 15: FLIGHT SOFTWARE STATE -------------------
  Serial.print(STATE_NAMES[fState]); Serial.print(',');

  // ---- Field 16: OPTIONAL — payload working status --------
  Serial.print(PL_NAMES[pState]);

  Serial.println();   // CRLF end of packet
}

// ============================================================
void setup() {
  Serial.begin(BAUD_RATE);
  while (!Serial) { ; }   // wait for USB-Serial (Leonardo / Due / ESP32)

  Serial.println(F("# CAN-7USAT TELEMETRY SIMULATOR"));
  Serial.println(F("# IN-SPACe 2026 — Simulation 1 / Custom profile"));
  Serial.println(F("# Fields: TEAM_ID,TIME,PKT,ALT,PRES,TEMP,VOLT,GNSS_T,LAT,LON,GNSS_ALT,SATS,AX;AY;AZ,GYRO,STATE,OPTIONAL"));
  Serial.println(F("# ---"));

  wallMs = millis();
}

void loop() {
  if (missionDone) return;

  uint32_t now = millis();
  if (now - wallMs < TICK_MS) return;
  wallMs = now;

  simTime += (TICK_MS / 1000.0f) * SIM_SPEED;

  if (simTime >= T_END) {
    simTime = T_END;
    missionDone = true;
    sendPacket(simTime);
    Serial.println(F("# MISSION COMPLETE"));
    return;
  }

  sendPacket(simTime);
}
