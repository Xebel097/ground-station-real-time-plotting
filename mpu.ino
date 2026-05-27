#include <Wire.h>

#define MPU_ADDR 0x68

int16_t raw_ax, raw_ay, raw_az;
int16_t raw_gx, raw_gy, raw_gz;
int16_t temp_raw;

unsigned long packetCount = 0;
String lastCmd = "NONE";

void setup() {
  Serial.begin(9600);
  Wire.begin();

  // Wake up the MPU6050 (it starts in sleep mode)
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0); // write 0 to wake it up
  Wire.endTransmission(true);

  Serial.println("MPU6050 initialized. Reading data...");
  delay(1000);
}

void loop() {
  if (Serial.available()) {
    lastCmd = Serial.readStringUntil('\n');
    lastCmd.trim();
  }

  // 1. Point to the starting register for data (ACCEL_XOUT_H)
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  Wire.endTransmission(false); // Restart condition for reading

  // 2. Request 14 bytes of data (7 measurements, 2 bytes each)
  Wire.requestFrom(MPU_ADDR, 14, true);

  // 3. Read and combine the high and low bytes for each measurement
  raw_ax = Wire.read() << 8 | Wire.read();
  raw_ay = Wire.read() << 8 | Wire.read();
  raw_az = Wire.read() << 8 | Wire.read();
  temp_raw = Wire.read() << 8 | Wire.read();
  raw_gx = Wire.read() << 8 | Wire.read();
  raw_gy = Wire.read() << 8 | Wire.read();
  raw_gz = Wire.read() << 8 | Wire.read();

  //calliberate the accel and gyro
  float ax = raw_ax / 16384.0 +0.01;
  float ay = raw_ay / 16384.0 +0.02;
  float az = raw_az / 16384.0 -0.939;
  float gx = raw_gx / 131.0 +1.36;
  float gy = raw_gy / 131.0 +2.40;
  float gz = raw_gz / 131.0 -0.9;

  String missionTime = getMissionTime();
  String gpsTime = "00:00:00";

  // initialise other values for the comma separated string
  float altitude = 0.0;
  float voltage = 7.4;
  float current = 0.5;
  float gpsLat = 0.0;
  float gpsLon = 0.0;
  float gpsAlt = altitude;
  int gpsSats = 0;
  float ultrasonic = 0.0;

  // 4. Print the raw values to the Serial Monitor
  Serial.print("1001");
  Serial.print(",");
  Serial.print(missionTime);
  Serial.print(",");
  Serial.print(packetCount++);
  Serial.print(",");
  Serial.print("FLIGHT");
  Serial.print(",");
  Serial.print("ASCENT");
  Serial.print(",");
  Serial.print(altitude, 2);
  Serial.print(",");
  Serial.print(voltage, 2);
  Serial.print(",");
  Serial.print(current, 2);
  Serial.print(",");
  Serial.print(ax, 3);
  Serial.print(",");
  Serial.print(ay, 3);
  Serial.print(",");
  Serial.print(az, 3);
  Serial.print(",");
  Serial.print(gx, 3);
  Serial.print(",");
  Serial.print(gy, 3);
  Serial.print(",");
  Serial.print(gz, 3);
  Serial.print(",");
  Serial.print(gpsTime);
  Serial.print(",");
  Serial.print(gpsLat, 6);
  Serial.print(",");
  Serial.print(gpsLon, 6);
  Serial.print(",");
  Serial.print(gpsAlt, 2);
  Serial.print(",");
  Serial.print(gpsSats);
  Serial.print(",");
  Serial.print(ultrasonic, 2);
  Serial.print(",");
  Serial.println(lastCmd);

  delay(200);
}

String getMissionTime() {
  unsigned long totalSeconds = millis() / 1000;

  unsigned int hours = totalSeconds / 3600;
  unsigned int minutes = (totalSeconds % 3600) / 60;
  unsigned int seconds = totalSeconds % 60;

  char buf[10];
  sprintf(buf, "%02u:%02u:%02u", hours, minutes, seconds);
  return String(buf);
}
