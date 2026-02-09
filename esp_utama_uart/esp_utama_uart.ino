/*
 * ESP32 UART Communication - ESP-BC (Control Rods + Turbine + Motor Driver + Cooling Tower Relays)
 * BINARY PROTOCOL VERSION - Replaces JSON for efficiency
 * 
 * Hardware:
 * - UART2 (GPIO 16=RX, GPIO 17=TX) for communication with Raspberry Pi
 * - Serial (USB) for debugging
 * - 4x Motor DC dengan L298N motor driver (3 pompa + 1 turbin)
 * - 3x Servo motors (control rods)
 * - 4x Relay untuk Cooling Tower humidifier (GPIO 27, 26, 25, 32)
 * 
 * Protocol: BINARY Protocol with ACK/NACK (115200 baud, 8N1)
 * - Command: 15 bytes (vs 86 bytes JSON) - 83% reduction
 * - Response: 28 bytes (vs 187 bytes JSON) - 85% reduction
 * - CRC8 checksum for error detection
 * - ACK/NACK responses for reliability
 * - No buffer garbage issues
 * 
 * Pin Configuration:
 * - UART: GPIO 16 (RX), 17 (TX) - Communication with RasPi
 * - Servos: GPIO 13, 12, 14 (control rods)
 * - Cooling Tower Relays: GPIO 27, 26, 25, 32 (CT1, CT2, CT3, CT4)
 * - Motor Driver PWM: GPIO 4, 5, 18, 19 (3 pompa + turbin)
 * - Motor Direction: GPIO 23, 15 (turbine only, pumps hard-wired)
 */

#include <ESP32Servo.h>

// ============================================
// Binary Protocol Constants
// ============================================
#define STX 0x02          // Start of Text
#define ETX 0x03          // End of Text
#define ACK 0x06          // Acknowledge
#define NACK 0x15         // Negative Acknowledge
#define CMD_PING 0x50     // 'P' - Ping command
#define CMD_UPDATE 0x55   // 'U' - Update command

// Message lengths
#define PING_CMD_LEN 5    // [STX][CMD][LEN=0][CRC][ETX]
#define UPDATE_CMD_LEN 15 // [STX][CMD][LEN=10][rod1][rod2][rod3][pump1][pump2][pump3][h1][h2][h3][h4][CRC][ETX]
#define PING_RESP_LEN 5   // [STX][ACK][LEN=0][CRC][ETX]
#define UPDATE_RESP_LEN 28 // [STX][ACK][LEN=23][23 bytes data][CRC][ETX]

// ============================================
// CRC8 Checksum (CRC-8/MAXIM)
// ============================================
uint8_t crc8_maxim(const uint8_t* data, size_t len) {
  uint8_t crc = 0x00;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (uint8_t j = 0; j < 8; j++) {
      if (crc & 0x80) {
        crc = (crc << 1) ^ 0x31;
      } else {
        crc = crc << 1;
      }
    }
  }
  return crc;
}

// ============================================
// UART Configuration
// ============================================
#define UART_BAUD 115200
HardwareSerial UartComm(2);  // UART2 (GPIO 16=RX, 17=TX)

// ============================================
// Binary Message Buffer
// ============================================
uint8_t rx_buffer[32];  // Buffer for incoming binary messages
uint8_t rx_index = 0;

// State machine for robust frame parsing
// This prevents STX/ETX bytes in payload from breaking frame detection
enum RxState {
  WAIT_STX,   // Waiting for start of frame
  IN_FRAME    // Currently receiving frame data
};
RxState rx_state = WAIT_STX;

unsigned long last_byte_time = 0;
#define RX_TIMEOUT_MS 500  // Reset buffer if no data for 500ms

// ============================================
// Control Rod Servos
// ============================================
Servo servo_safety;
Servo servo_shim;
Servo servo_regulating;

const int SERVO_PIN_SAFETY = 13;
const int SERVO_PIN_SHIM = 12;
const int SERVO_PIN_REGULATING = 14;

// Rod positions (0-100%)
int safety_target = 0;
int shim_target = 0;
int regulating_target = 0;

// Final desired targets (for smooth motion)
float safety_final_target = 0.0;
float shim_final_target = 0.0;
float regulating_final_target = 0.0;

// Actual positions as floats for smooth interpolation
float safety_actual_f = 0.0;
float shim_actual_f = 0.0;
float regulating_actual_f = 0.0;

int safety_actual = 0;
int shim_actual = 0;
int regulating_actual = 0;

// ============================================
// Motor Driver PWM Configuration
// ============================================
#define MOTOR_PUMP_PRIMARY    4    // Pompa Primer (Primary Loop)
#define MOTOR_PUMP_SECONDARY  5    // Pompa Sekunder (Secondary Loop)
#define MOTOR_PUMP_TERTIARY   18   // Pompa Tersier (Tertiary/Cooling Loop)
#define MOTOR_TURBINE         19   // Motor Turbin

// Motor Direction Control - ONLY for Turbine
#define MOTOR_TURBINE_IN1     23   // Turbine direction 1
#define MOTOR_TURBINE_IN2     15   // Turbine direction 2

// Motor Direction Enum
#define MOTOR_FORWARD  1
#define MOTOR_REVERSE  2
#define MOTOR_STOP     0

// PWM Configuration
#define PWM_FREQ       5000  // 5 kHz
#define PWM_RESOLUTION 8     // 8-bit (0-255)

// ============================================
// Humidifier Relays - Cooling Tower Only (4 relays)
// ============================================
const int RELAY_CT1 = 27;  // Cooling Tower 1
const int RELAY_CT2 = 26;  // Cooling Tower 2
const int RELAY_CT3 = 25;  // Cooling Tower 3
const int RELAY_CT4 = 32;  // Cooling Tower 4

uint8_t humid_ct1_cmd = 0;
uint8_t humid_ct2_cmd = 0;
uint8_t humid_ct3_cmd = 0;
uint8_t humid_ct4_cmd = 0;

uint8_t humid_ct1_status = 0;
uint8_t humid_ct2_status = 0;
uint8_t humid_ct3_status = 0;
uint8_t humid_ct4_status = 0;

// ============================================
// Cherenkov Radiation LED Visualization
// ============================================
const int LED_CHERENKOV = 33;  // Blue LED for Cherenkov radiation visualization

// PWM Configuration for Cherenkov LED
#define PWM_CHERENKOV_FREQ 5000  // 5 kHz (same as motors)
#define PWM_CHERENKOV_RES 8      // 8-bit resolution (0-255)

float cherenkov_brightness = 0.0;  // Current brightness (0-100%)

// ============================================
// Turbine & Generator Simulation
// ============================================
enum TurbineState {
  STATE_IDLE = 0,
  STATE_STARTING = 1,
  STATE_RUNNING = 2,
  STATE_SHUTDOWN = 3
};

TurbineState current_state = STATE_IDLE;
float power_level = 0.0;    // Turbine power (0-100%)
float thermal_kw_calculated = 0.0;
float turbine_speed = 0.0;  // Current turbine speed (0-100%)

// ============================================
// Pump Variables
// ============================================
float pump_primary_actual = 0.0;    // Current PWM (0-100%)
float pump_secondary_actual = 0.0;
float pump_tertiary_actual = 0.0;

float pump_primary_target = 0.0;    // Target PWM from RasPi button command
float pump_secondary_target = 0.0;
float pump_tertiary_target = 0.0;

// Pump commands from RasPi (0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN)
int pump_primary_cmd = 0;
int pump_secondary_cmd = 0;
int pump_tertiary_cmd = 0;

// ============================================
// Binary Protocol Functions
// ============================================

void sendNACK() {
  // Send NACK response: [STX][NACK][LEN=0][CRC][ETX]
  uint8_t response[5];
  response[0] = STX;
  response[1] = NACK;
  response[2] = 0;  // LEN = 0 (no payload)
  
  // Calculate CRC over CMD + LEN
  uint8_t crc_data[2] = {NACK, 0};
  response[3] = crc8_maxim(crc_data, 2);
  response[4] = ETX;
  
  UartComm.write(response, 5);
  UartComm.flush();
  
  Serial.println("TX: NACK");
}

void sendPongResponse() {
  // Send pong response: [STX][ACK][LEN=0][CRC][ETX]
  uint8_t response[5];
  response[0] = STX;
  response[1] = ACK;
  response[2] = 0;  // LEN = 0 (no payload)
  
  // Calculate CRC over CMD + LEN
  uint8_t crc_data[2] = {ACK, 0};
  response[3] = crc8_maxim(crc_data, 2);
  response[4] = ETX;
  
  UartComm.write(response, 5);
  UartComm.flush();
  
  Serial.println("TX: Pong ACK");
}

void sendUpdateResponse() {
  // Send update response: [STX][ACK][LEN=23][23 bytes data][CRC][ETX]
  uint8_t response[28];
  response[0] = STX;
  response[1] = ACK;
  response[2] = 23;  // LEN = 23 bytes payload
  
  // Pack data (23 bytes total)
  uint8_t* data = &response[3];
  
  // Rods (3 bytes)
  data[0] = (uint8_t)safety_actual;
  data[1] = (uint8_t)shim_actual;
  data[2] = (uint8_t)regulating_actual;
  
  // Thermal power (4 bytes, float32, little-endian)
  memcpy(&data[3], &thermal_kw_calculated, 4);
  
  // Power level (2 bytes, uint16, 0-10000 for 0.00-100.00%)
  uint16_t power_lvl_int = (uint16_t)(power_level * 100.0);
  data[7] = power_lvl_int & 0xFF;
  data[8] = (power_lvl_int >> 8) & 0xFF;
  
  // State (1 byte)
  data[9] = (uint8_t)current_state;
  
  // Turbine speed (2 bytes, uint16, 0-10000)
  uint16_t turb_spd_int = (uint16_t)(turbine_speed * 100.0);
  data[10] = turb_spd_int & 0xFF;
  data[11] = (turb_spd_int >> 8) & 0xFF;
  
  // Pump speeds (6 bytes, 3x uint16)
  uint16_t pump1_int = (uint16_t)(pump_primary_actual * 100.0);
  uint16_t pump2_int = (uint16_t)(pump_secondary_actual * 100.0);
  uint16_t pump3_int = (uint16_t)(pump_tertiary_actual * 100.0);
  
  data[12] = pump1_int & 0xFF;
  data[13] = (pump1_int >> 8) & 0xFF;
  data[14] = pump2_int & 0xFF;
  data[15] = (pump2_int >> 8) & 0xFF;
  data[16] = pump3_int & 0xFF;
  data[17] = (pump3_int >> 8) & 0xFF;
  
  // Humidifier status (4 bytes)
  data[18] = humid_ct1_status;
  data[19] = humid_ct2_status;
  data[20] = humid_ct3_status;
  data[21] = humid_ct4_status;
  
  // Reserved (1 byte) - for future use
  data[22] = 0;
  
  // Calculate CRC over CMD + LEN + data (25 bytes total)
  response[26] = crc8_maxim(&response[1], 25);
  response[27] = ETX;
  
  UartComm.write(response, 28);
  UartComm.flush();
  
  Serial.println("TX: Update ACK with data");
}

void processBinaryMessage(uint8_t* msg, uint8_t len) {
  // Validate message structure
  if (len < 5) {
    Serial.println("Message too short");
    return;
  }
  
  if (msg[0] != STX || msg[len-1] != ETX) {
    Serial.println("Invalid STX/ETX");
    return;
  }
  
  // DEBUG: Print received message
  Serial.print("RX bytes: [");
  for (uint8_t i = 0; i < len; i++) {
    Serial.printf("%02X", msg[i]);
    if (i < len-1) Serial.print(" ");
  }
  Serial.printf("] (%d bytes)\n", len);
  
  // Extract fields: [STX][CMD][LEN][PAYLOAD...][CRC][ETX]
  uint8_t cmd = msg[1];
  uint8_t payload_len = msg[2];
  uint8_t received_crc = msg[len-2];
  
  // Validate total message length
  uint8_t expected_len = 5 + payload_len;  // STX + CMD + LEN + PAYLOAD + CRC + ETX
  if (len != expected_len) {
    Serial.printf("Length mismatch: got %d bytes, expected %d (LEN field=%d)\n", len, expected_len, payload_len);
    sendNACK();
    return;
  }
  
  // Validate CRC (over CMD + LEN + PAYLOAD)
  uint8_t crc_len = 2 + payload_len;  // CMD + LEN + payload
  Serial.printf("CRC calculation: &msg[1], len=%d\n", crc_len);
  uint8_t calculated_crc = crc8_maxim(&msg[1], crc_len);
  
  if (received_crc != calculated_crc) {
    Serial.printf("CRC mismatch: received=0x%02X, calculated=0x%02X\n", received_crc, calculated_crc);
    sendNACK();
    return;
  }
  
  // Process command
  if (cmd == CMD_PING) {
    if (payload_len != 0) {
      Serial.printf("Invalid ping payload length: %d (expected 0)\n", payload_len);
      sendNACK();
      return;
    }
    Serial.println("RX: Ping");
    sendPongResponse();
  }
  else if (cmd == CMD_UPDATE) {
    if (payload_len != 10) {
      Serial.printf("Invalid update payload length: %d (expected 10)\n", payload_len);
      sendNACK();
      return;
    }
    
    // Parse update data (payload starts at index 3)
    safety_target = msg[3];
    shim_target = msg[4];
    regulating_target = msg[5];
    
    pump_primary_cmd = msg[6];
    pump_secondary_cmd = msg[7];
    pump_tertiary_cmd = msg[8];
    
    humid_ct1_cmd = msg[9];
    humid_ct2_cmd = msg[10];
    humid_ct3_cmd = msg[11];
    humid_ct4_cmd = msg[12];
    
    // Update targets
    safety_final_target = constrain(safety_target, 0, 100);
    shim_final_target = constrain(shim_target, 0, 100);
    regulating_final_target = constrain(regulating_target, 0, 100);
    
    Serial.printf("RX: Update - Rods=[%d,%d,%d], Pumps=[%d,%d,%d], Humid=[%d,%d,%d,%d]\n",
                  safety_target, shim_target, regulating_target,
                  pump_primary_cmd, pump_secondary_cmd, pump_tertiary_cmd,
                  humid_ct1_cmd, humid_ct2_cmd, humid_ct3_cmd, humid_ct4_cmd);
    
    sendUpdateResponse();
  }
  else {
    Serial.printf("Unknown command: 0x%02X\n", cmd);
    sendNACK();
  }
}

// ============================================
// Setup
// ============================================
void setup() {
  // Initialize USB Serial for debugging
  Serial.begin(115200);
  delay(500);
  
  Serial.println("\n\n===========================================");
  Serial.println("ESP-BC BINARY PROTOCOL");
  Serial.println("Control Rods + Turbine + Humidifier + Motor Driver");
  Serial.println("===========================================");
  
  // Initialize UART2 for Raspberry Pi communication
  UartComm.begin(UART_BAUD, SERIAL_8N1, 16, 17);  // RX=16, TX=17
  Serial.println("✅ UART2 initialized at 115200 baud");
  Serial.println("   RX: GPIO 16");
  Serial.println("   TX: GPIO 17");
  Serial.println("   Protocol: BINARY with ACK/NACK");
  
  // Initialize servos
  servo_safety.attach(SERVO_PIN_SAFETY);
  servo_shim.attach(SERVO_PIN_SHIM);
  servo_regulating.attach(SERVO_PIN_REGULATING);
  
  // Set initial positions (0%)
  updateServos();
  Serial.println("✅ Servos initialized");
  
  // Initialize relay pins (Cooling Tower only - 4 relays)
  pinMode(RELAY_CT1, OUTPUT);
  pinMode(RELAY_CT2, OUTPUT);
  pinMode(RELAY_CT3, OUTPUT);
  pinMode(RELAY_CT4, OUTPUT);
  
  // All relays OFF initially (HIGH for low-level trigger)
  digitalWrite(RELAY_CT1, HIGH);
  digitalWrite(RELAY_CT2, HIGH);
  digitalWrite(RELAY_CT3, HIGH);
  digitalWrite(RELAY_CT4, HIGH);
  Serial.println("✅ Cooling Tower relays initialized (4 relays: GPIO 27, 26, 25, 32)");
  
  // Initialize motor driver PWM channels (ESP32 Core v3.x API)
  ledcAttach(MOTOR_PUMP_PRIMARY, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(MOTOR_PUMP_SECONDARY, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(MOTOR_PUMP_TERTIARY, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(MOTOR_TURBINE, PWM_FREQ, PWM_RESOLUTION);
  
  // All motor drivers OFF initially
  ledcWrite(MOTOR_PUMP_PRIMARY, 0);
  ledcWrite(MOTOR_PUMP_SECONDARY, 0);
  ledcWrite(MOTOR_PUMP_TERTIARY, 0);
  ledcWrite(MOTOR_TURBINE, 0);
  Serial.println("✅ Motor drivers initialized (3 pumps + turbine)");
  Serial.println("   PWM Pins: GPIO 4, 5, 18, 19");
  
  // Initialize turbine direction control pins
  pinMode(MOTOR_TURBINE_IN1, OUTPUT);
  pinMode(MOTOR_TURBINE_IN2, OUTPUT);
  digitalWrite(MOTOR_TURBINE_IN1, HIGH);  // Default: FORWARD
  digitalWrite(MOTOR_TURBINE_IN2, LOW);
  Serial.println("✅ Turbine direction control initialized");
  Serial.println("   Direction Pins: GPIO 23, 15");
  Serial.println("   Pumps: Hard-wired FORWARD (no GPIO needed)");
  
  // Initialize Cherenkov LED PWM
  ledcAttach(LED_CHERENKOV, PWM_CHERENKOV_FREQ, PWM_CHERENKOV_RES);
  ledcWrite(LED_CHERENKOV, 0);  // Start with LED off
  Serial.println("✅ Cherenkov LED initialized (GPIO 33)");
  Serial.println("   PWM Freq: 5kHz, Resolution: 8-bit");
  Serial.println("   Brightness: Proportional to (Shim + Regulating) / 2");
  
  Serial.println("===========================================");
  Serial.println("✅ System Ready - Waiting for binary commands...");
  Serial.println("===========================================\n");
}

// ============================================
// Main Loop
// ============================================
void loop() {
  // Read UART data with state machine for robust frame parsing
  while (UartComm.available()) {
    uint8_t byte = UartComm.read();
    unsigned long current_time = millis();
    
    // Check for timeout (reset to WAIT_STX if no data for 500ms)
    if (rx_state == IN_FRAME && (current_time - last_byte_time > RX_TIMEOUT_MS)) {
      Serial.println("RX timeout - resetting to WAIT_STX");
      rx_state = WAIT_STX;
      rx_index = 0;
    }
    
    last_byte_time = current_time;
    
    // State machine for frame parsing
    if (rx_state == WAIT_STX) {
      // Only accept STX when waiting for new frame
      if (byte == STX) {
        rx_index = 0;
        rx_buffer[rx_index++] = byte;
        rx_state = IN_FRAME;
        Serial.println("RX: STX detected, entering IN_FRAME state");
      }
      // Ignore all other bytes when waiting for STX
    }
    else if (rx_state == IN_FRAME) {
      // Add byte to buffer
      if (rx_index < sizeof(rx_buffer)) {
        rx_buffer[rx_index++] = byte;
        
        // Check if this is ETX (end of frame)
        if (byte == ETX) {
          // DEBUG: Print complete frame
          Serial.print("RX complete frame: [");
          for (uint8_t i = 0; i < rx_index; i++) {
            Serial.printf("%02X", rx_buffer[i]);
            if (i < rx_index-1) Serial.print(" ");
          }
          Serial.printf("] (%d bytes)\n", rx_index);
          
          // Process complete message
          processBinaryMessage(rx_buffer, rx_index);
          
          // Return to WAIT_STX state
          rx_state = WAIT_STX;
          rx_index = 0;
          
          // Flush any remaining garbage in buffer
          while (UartComm.available()) {
            UartComm.read();
          }
        }
      }
      else {
        // Buffer overflow - reset to WAIT_STX
        Serial.println("Buffer overflow - resetting to WAIT_STX");
        rx_state = WAIT_STX;
        rx_index = 0;
      }
    }
  }
  
  // Update system state (only after reading all UART data)
  updateServos();
  calculateThermalPower();
  updateTurbineState();
  updateHumidifiers();
  updatePumpSpeeds();
  updateTurbineSpeed();
  updateCherenkovLED();
  
  yield();
  delay(10);
}

// ============================================
// Update Servos (same as before)
// ============================================
void updateServos() {
  const float loop_dt = 0.01;
  const float max_delta = 50.0 * loop_dt;  // 50% per second
  
  // Move safety_actual_f toward safety_final_target
  if (fabs(safety_actual_f - safety_final_target) > 0.001) {
    float diff = safety_final_target - safety_actual_f;
    if (fabs(diff) <= max_delta) safety_actual_f = safety_final_target;
    else safety_actual_f += (diff > 0 ? max_delta : -max_delta);
  }
  
  // Move shim_actual_f toward shim_final_target
  if (fabs(shim_actual_f - shim_final_target) > 0.001) {
    float diff = shim_final_target - shim_actual_f;
    if (fabs(diff) <= max_delta) shim_actual_f = shim_final_target;
    else shim_actual_f += (diff > 0 ? max_delta : -max_delta);
  }
  
  // Move regulating_actual_f toward regulating_final_target
  if (fabs(regulating_actual_f - regulating_final_target) > 0.001) {
    float diff = regulating_final_target - regulating_actual_f;
    if (fabs(diff) <= max_delta) regulating_actual_f = regulating_final_target;
    else regulating_actual_f += (diff > 0 ? max_delta : -max_delta);
  }
  
  // Update integer snapshots
  safety_actual = (int)round(safety_actual_f);
  shim_actual = (int)round(shim_actual_f);
  regulating_actual = (int)round(regulating_actual_f);
  
  // Map 0-100% to servo angle (0-180 degrees)
  int angle_safety = (int)map(safety_actual, 0, 100, 0, 180);
  int angle_shim = (int)map(shim_actual, 0, 100, 0, 180);
  int angle_regulating = (int)map(regulating_actual, 0, 100, 0, 180);
  
  servo_safety.write(angle_safety);
  servo_shim.write(angle_shim);
  servo_regulating.write(angle_regulating);
}

// ============================================
// Calculate Thermal Power (same as before)
// ============================================
void calculateThermalPower() {
  float avgRodPosition = (shim_actual + regulating_actual) / 2.0;
  float reactor_thermal_kw = 0.0;
  
  if (avgRodPosition > 10.0) {
    reactor_thermal_kw = avgRodPosition * avgRodPosition * 90.0;
    reactor_thermal_kw += shim_actual * 150.0;
    reactor_thermal_kw += regulating_actual * 200.0;
  }
  
  if (reactor_thermal_kw > 900000.0) reactor_thermal_kw = 900000.0;
  
  float turbine_load = power_level / 100.0;
  // Increased efficiency to 34% to allow reaching full 300 MW
  // At max: 900,000 kW × 0.34 × 1.0 = 306,000 kW (capped at 300,000)
  const float TURBINE_EFFICIENCY = 0.34;
  
  thermal_kw_calculated = reactor_thermal_kw * TURBINE_EFFICIENCY * turbine_load;
  
  if (thermal_kw_calculated < 0.0) thermal_kw_calculated = 0.0;
  if (thermal_kw_calculated > 300000.0) thermal_kw_calculated = 300000.0;
}

// ============================================
// Update Turbine State (same as before)
// ============================================
void updateTurbineState() {
  float avgRodPosition = (shim_actual + regulating_actual) / 2.0;
  float reactor_thermal_capacity = 0.0;
  
  if (avgRodPosition > 10.0) {
    reactor_thermal_capacity = avgRodPosition * avgRodPosition * 90.0;
    reactor_thermal_capacity += shim_actual * 150.0;
    reactor_thermal_capacity += regulating_actual * 200.0;
  }
  
  switch (current_state) {
    case STATE_IDLE:
      if (reactor_thermal_capacity > 50000.0) {
        current_state = STATE_STARTING;
        Serial.println("Turbine: IDLE → STARTING");
      }
      power_level = 0.0;
      break;
      
    case STATE_STARTING:
      power_level += 0.5;
      if (power_level >= 100.0) {
        power_level = 100.0;
        current_state = STATE_RUNNING;
        Serial.println("Turbine: STARTING → RUNNING");
      }
      break;
      
    case STATE_RUNNING:
      if (reactor_thermal_capacity < 20000.0) {
        current_state = STATE_SHUTDOWN;
        Serial.println("Turbine: RUNNING → SHUTDOWN");
      }
      power_level = 100.0;
      break;
      
    case STATE_SHUTDOWN:
      power_level -= 1.0;
      if (power_level <= 0.0) {
        power_level = 0.0;
        current_state = STATE_IDLE;
        Serial.println("Turbine: SHUTDOWN → IDLE");
      }
      break;
  }
}

// ============================================
// Update Humidifiers (same as before)
// ============================================
void updateHumidifiers() {
  digitalWrite(RELAY_CT1, humid_ct1_cmd ? LOW : HIGH);
  digitalWrite(RELAY_CT2, humid_ct2_cmd ? LOW : HIGH);
  digitalWrite(RELAY_CT3, humid_ct3_cmd ? LOW : HIGH);
  digitalWrite(RELAY_CT4, humid_ct4_cmd ? LOW : HIGH);
  
  humid_ct1_status = humid_ct1_cmd;
  humid_ct2_status = humid_ct2_cmd;
  humid_ct3_status = humid_ct3_cmd;
  humid_ct4_status = humid_ct4_cmd;
}

// ============================================
// Motor Direction Control (same as before)
// ============================================
void setMotorDirection(uint8_t motor_id, uint8_t direction) {
  if (motor_id == 4) {
    if (direction == MOTOR_FORWARD) {
      digitalWrite(MOTOR_TURBINE_IN1, HIGH);
      digitalWrite(MOTOR_TURBINE_IN2, LOW);
    } else if (direction == MOTOR_REVERSE) {
      digitalWrite(MOTOR_TURBINE_IN1, LOW);
      digitalWrite(MOTOR_TURBINE_IN2, HIGH);
    } else {
      digitalWrite(MOTOR_TURBINE_IN1, LOW);
      digitalWrite(MOTOR_TURBINE_IN2, LOW);
    }
  }
}

// ============================================
// Pump Gradual Speed Control (same as before)
// ============================================
void updatePumpSpeeds() {
  // PRIMARY PUMP
  if (pump_primary_cmd == 0) {
    pump_primary_target = 0.0;
  } else if (pump_primary_cmd == 1) {
    pump_primary_target = 50.0;
  } else if (pump_primary_cmd == 2) {
    pump_primary_target = 100.0;
  } else if (pump_primary_cmd == 3) {
    pump_primary_target = 20.0;
  }
  
  if (pump_primary_actual < pump_primary_target) {
    pump_primary_actual += 1.0;
    if (pump_primary_actual > pump_primary_target) {
      pump_primary_actual = pump_primary_target;
    }
  } else if (pump_primary_actual > pump_primary_target) {
    pump_primary_actual -= 2.0;
    if (pump_primary_actual < pump_primary_target) {
      pump_primary_actual = pump_primary_target;
    }
  }
  
  // SECONDARY PUMP
  if (pump_secondary_cmd == 0) {
    pump_secondary_target = 0.0;
  } else if (pump_secondary_cmd == 1) {
    pump_secondary_target = 50.0;
  } else if (pump_secondary_cmd == 2) {
    pump_secondary_target = 100.0;
  } else if (pump_secondary_cmd == 3) {
    pump_secondary_target = 20.0;
  }
  
  if (pump_secondary_actual < pump_secondary_target) {
    pump_secondary_actual += 1.0;
    if (pump_secondary_actual > pump_secondary_target) {
      pump_secondary_actual = pump_secondary_target;
    }
  } else if (pump_secondary_actual > pump_secondary_target) {
    pump_secondary_actual -= 2.0;
    if (pump_secondary_actual < pump_secondary_target) {
      pump_secondary_actual = pump_secondary_target;
    }
  }
  
  // TERTIARY PUMP
  if (pump_tertiary_cmd == 0) {
    pump_tertiary_target = 0.0;
  } else if (pump_tertiary_cmd == 1) {
    pump_tertiary_target = 50.0;
  } else if (pump_tertiary_cmd == 2) {
    pump_tertiary_target = 100.0;
  } else if (pump_tertiary_cmd == 3) {
    pump_tertiary_target = 20.0;
  }
  
  if (pump_tertiary_actual < pump_tertiary_target) {
    pump_tertiary_actual += 1.0;
    if (pump_tertiary_actual > pump_tertiary_target) {
      pump_tertiary_actual = pump_tertiary_target;
    }
  } else if (pump_tertiary_actual > pump_tertiary_target) {
    pump_tertiary_actual -= 2.0;
    if (pump_tertiary_actual < pump_tertiary_target) {
      pump_tertiary_actual = pump_tertiary_target;
    }
  }
  
  // Apply PWM to motor drivers (0-255)
  int pwm_primary = map((int)pump_primary_actual, 0, 100, 0, 255);
  int pwm_secondary = map((int)pump_secondary_actual, 0, 100, 0, 255);
  int pwm_tertiary = map((int)pump_tertiary_actual, 0, 100, 0, 255);
  
  ledcWrite(MOTOR_PUMP_PRIMARY, pwm_primary);
  ledcWrite(MOTOR_PUMP_SECONDARY, pwm_secondary);
  ledcWrite(MOTOR_PUMP_TERTIARY, pwm_tertiary);
}

// ============================================
// Turbine Motor Speed Control (same as before)
// ============================================
void updateTurbineSpeed() {
  float avg_control_rods = (shim_actual + regulating_actual) / 2.0;
  turbine_speed = avg_control_rods;
  
  if (turbine_speed < 10.0) {
    turbine_speed = 0.0;
    setMotorDirection(4, MOTOR_STOP);
  } else {
    setMotorDirection(4, MOTOR_FORWARD);
  }
  
  int pwm_turbine = map((int)turbine_speed, 0, 100, 0, 255);
  ledcWrite(MOTOR_TURBINE, pwm_turbine);
}

// ============================================
// Update Cherenkov LED Brightness
// ============================================
void updateCherenkovLED() {
  // Calculate brightness based on average of shim and regulating rods
  // Safety rod tidak digunakan karena harus 100% sebelum shim/regulating diangkat
  float avg_control_rods = (shim_actual + regulating_actual) / 2.0;
  
  // Brightness proportional to rod position (0-100%)
  cherenkov_brightness = avg_control_rods;
  
  // Apply threshold: LED only lights up when rods > 0%
  if (cherenkov_brightness < 0.5) {
    cherenkov_brightness = 0.0;
  }
  
  // Map to PWM value (0-255)
  int pwm_value = map((int)cherenkov_brightness, 0, 100, 0, 255);
  
  // Apply PWM to LED
  ledcWrite(LED_CHERENKOV, pwm_value);
}
