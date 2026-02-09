/*
 * ESP32 Power Indicator - BINARY PROTOCOL VERSION (OPTIMIZED)
 * 
 * Fungsi:
 * - Kontrol 4 LED power indicator untuk visualisasi daya reaktor
 * - Komunikasi UART dengan Raspberry Pi menggunakan BINARY protocol
 * - LED brightness proporsional dengan daya output (0-300 MWe)
 * - Auto-switching PWM → HIGH mode untuk kecerahan maksimal (≥250 PWM)
 * 
 * LED Mode Control:
 * - PWM Mode (0-249): LED dikontrol dengan PWM (0-255) untuk brightness bertahap
 * - HIGH Mode (≥250): LED menerima 3.3V penuh untuk kecerahan maksimal
 * - Hysteresis: Switch ke HIGH di ≥250, kembali ke PWM di <240
 * 
 * Pin Configuration (NO CONFLICT):
 * - LED Power: GPIO 25, 26, 27, 32 (safe pins, no SPI conflict)
 * - SPI HSPI: SCK=14, MOSI=13 (default, no conflict with LEDs)
 * 
 * Protocol: BINARY Protocol with ACK/NACK (115200 baud, 8N1)
 * - Command: 9 bytes (vs 42 bytes JSON) - 79% reduction
 * - Response: 10 bytes (vs 45 bytes JSON) - 78% reduction
 * - CRC8 checksum for error detection
 * - ACK/NACK responses for reliability
 * - No buffer garbage issues
 * 
 * OPTIMIZATION:
 * - Fixed SPI pin conflicts
 * - Non-blocking UART processing
 * - Consistent animation timing
 * - Reduced microsecond delays
 * - Task separation with proper intervals
 */

#include <Arduino.h>
#include <SPI.h>

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
#define UPDATE_CMD_LEN 12 // [STX][CMD][LEN=7][thermal_kw (4)][pump_prim][pump_sec][pump_ter][CRC][ETX]
#define PING_RESP_LEN 5   // [STX][ACK][LEN=0][CRC][ETX]
#define UPDATE_RESP_LEN 13 // [STX][ACK][LEN=8][power_mwe (4)][pwm][pump_prim][pump_sec][pump_ter][CRC][ETX]

// ============================================
// PUMP STRUCT
// ============================================
struct Pump {
  uint8_t status;           // 0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN
  uint8_t lastStatus;       // For detecting status changes
};

// ============================================
// DEBUG Configuration
// ============================================
#define DEBUG_SHIFT_REGISTER false   // Set to true untuk debug LED animation
#define DEBUG_UART false            // Debug UART communication
#define DEBUG_TIMING false           // Debug timing performance
#define HARDWARE_TEST_MODE false    // Set TRUE untuk test kontinyu (bypass pump status)

// ============================================
// DEVELOPMENT MODE Configuration
// ============================================
#define DEV_MODE true               // Set TRUE untuk mode development (simulasi data tanpa UART)
#define DEV_UPDATE_INTERVAL 100     // Update data simulasi setiap 100ms
#define DEV_DEBUG true              // Debug output untuk development mode

// ============================================
// HARDWARE PIN ASSIGNMENT
// ============================================

// LED POWER - GPIO yang AMAN (tidak konflik dengan SPI/ADC)
const int NUM_LEDS = 4;
const int POWER_LEDS[NUM_LEDS] = {25, 26, 27, 32};  // GPIO aman, tidak konflik

// SPI Hardware Configuration
#define NUM_IC 3               // 3x 74HC595 ICs
#define SPI_CLOCK_PIN 18       // SCK - Hardware SPI
#define SPI_MOSI_PIN 23        // MOSI - Hardware SPI
#define LATCH_PIN_GLOBAL 5     // RCLK - Shared for all 74HC595 ICs

// ============================================
// SHIFT REGISTER DATA BUFFER
// ============================================
/*
  sr_data[0] -> IC #1 (Primary pump - closest to ESP32)
  sr_data[1] -> IC #2 (Secondary pump)
  sr_data[2] -> IC #3 (Tertiary pump)
*/
uint8_t sr_data[NUM_IC];

// Ring pattern for each IC (2 LEDs active, circular rotation)
uint8_t ring_pattern[NUM_IC] = {
  0b00000011,  // IC #1
  0b00000011,  // IC #2
  0b00000011   // IC #3
};

// ============================================
// TIMING CONFIGURATION
// ============================================
#define ANIM_STEP_DELAY 150       // Animation step delay (ms)
#define LED_UPDATE_INTERVAL 20    // Update LED power setiap 20ms (50Hz refresh) - FIXED GLITCH
#define UART_PROCESS_INTERVAL 10  // Proses UART setiap 10ms
#define DEBUG_INTERVAL 2000       // Debug output setiap 2 detik

// Animation timer
unsigned long lastAnimTime = 0;

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
HardwareSerial UartComm(2); // RX=16 TX=17

// Binary Message Buffer
uint8_t rx_buffer[16];
uint8_t rx_index = 0;

// State machine untuk robust frame parsing
enum RxState {
  WAIT_STX,
  IN_FRAME
};
RxState rx_state = WAIT_STX;

unsigned long last_byte_time = 0;
#define RX_TIMEOUT_MS 500

// ============================================
// DATA VARIABLES
// ============================================
float thermal_kw = 0.0;
float power_mwe = 0.0;
int current_pwm = 0;

// Pump instances
Pump pump_primary = {0, 0};
Pump pump_secondary = {0, 0};
Pump pump_tertiary = {0, 0};

// Development mode variables
unsigned long dev_start_time = 0;
float dev_cycle_duration = 43.0;  // Total cycle duration in seconds (40s + 3s shutdown)



// LED Mode Control
#define PWM_THRESHOLD_HIGH 250
#define PWM_THRESHOLD_LOW 240
bool led_mode_high = false;
int last_written_pwm = -1;  // Track last written value to avoid redundant ledcWrite

// ============================================
// SHIFT REGISTER FUNCTIONS (SPI HARDWARE)
// ============================================

/**
 * Circular ring shift - rotates 2 active LEDs
 */
uint8_t ringShift(uint8_t value) {
  uint8_t msb = (value & 0b10000000) >> 7;
  value <<= 1;
  value |= msb;  // Q7 wraps back to Q0
  return value;
}

/**
 * Update shift register buffer based on pump status
 */
void updateSRBuffer() {
  // Clear all
  for (int i = 0; i < NUM_IC; i++) {
    sr_data[i] = 0x00;
  }
  
  // Primary pump (IC #1)
  if (pump_primary.status >= 2) {
    sr_data[0] = ring_pattern[0];
  }
  
  // Secondary pump (IC #2)
  if (pump_secondary.status >= 2) {
    sr_data[1] = ring_pattern[1];
  }
  
  // Tertiary pump (IC #3)
  if (pump_tertiary.status >= 2) {
    sr_data[2] = ring_pattern[2];
  }
}

/**
 * Write data to shift registers via SPI hardware
 */
void shiftRegisterWrite() {
  SPI.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  
  noInterrupts();
  digitalWrite(LATCH_PIN_GLOBAL, LOW);
  
  // Send data from last IC to first IC
  for (int i = NUM_IC - 1; i >= 0; i--) {
    SPI.transfer(sr_data[i]);
  }
  
  digitalWrite(LATCH_PIN_GLOBAL, HIGH);
  interrupts();
  
  SPI.endTransaction();
  
  #if DEBUG_SHIFT_REGISTER
    Serial.printf("[SR] IC1=0x%02X IC2=0x%02X IC3=0x%02X\n", 
                  sr_data[0], sr_data[1], sr_data[2]);
  #endif
}



// ============================================
// BINARY PROTOCOL FUNCTIONS
// ============================================

void sendNACK() {
  uint8_t response[5];
  response[0] = STX;
  response[1] = NACK;
  response[2] = 0;
  
  uint8_t crc_data[2] = {NACK, 0};
  response[3] = crc8_maxim(crc_data, 2);
  response[4] = ETX;
  
  UartComm.write(response, 5);
  
  #if DEBUG_UART
    Serial.println("TX: NACK");
  #endif
}

void sendPongResponse() {
  uint8_t response[5];
  response[0] = STX;
  response[1] = ACK;
  response[2] = 0;
  
  uint8_t crc_data[2] = {ACK, 0};
  response[3] = crc8_maxim(crc_data, 2);
  response[4] = ETX;
  
  UartComm.write(response, 5);
  
  #if DEBUG_UART
    Serial.println("TX: Pong ACK");
  #endif
}

void sendUpdateResponse() {
  uint8_t response[13];
  response[0] = STX;
  response[1] = ACK;
  response[2] = 8;
  
  uint8_t* data = &response[3];
  memcpy(&data[0], &power_mwe, 4);
  data[4] = (uint8_t)current_pwm;
  data[5] = pump_primary.status;
  data[6] = pump_secondary.status;
  data[7] = pump_tertiary.status;
  
  response[11] = crc8_maxim(&response[1], 10);
  response[12] = ETX;
  
  UartComm.write(response, 13);
  
  #if DEBUG_UART
    Serial.println("TX: Update ACK with data");
  #endif
}

void processBinaryMessage(uint8_t* msg, uint8_t len) {
  // Validasi struktur pesan
  if (len < 5 || msg[0] != STX || msg[len-1] != ETX) {
    sendNACK();
    return;
  }
  
  uint8_t cmd = msg[1];
  uint8_t payload_len = msg[2];
  uint8_t received_crc = msg[len-2];
  
  // Validasi panjang
  uint8_t expected_len = 5 + payload_len;
  if (len != expected_len) {
    sendNACK();
    return;
  }
  
  // Validasi CRC
  uint8_t crc_len = 2 + payload_len;
  uint8_t calculated_crc = crc8_maxim(&msg[1], crc_len);
  
  if (received_crc != calculated_crc) {
    sendNACK();
    return;
  }
  
  // Process command
  if (cmd == CMD_PING) {
    if (payload_len != 0) {
      sendNACK();
      return;
    }
    
    #if DEBUG_UART
      Serial.println("RX: Ping");
    #endif
    
    sendPongResponse();
  }
  else if (cmd == CMD_UPDATE) {
    if (payload_len != 7) {
      sendNACK();
      return;
    }
    
    pump_primary.lastStatus = pump_primary.status;
    pump_secondary.lastStatus = pump_secondary.status;
    pump_tertiary.lastStatus = pump_tertiary.status;
    // Parse data
    memcpy(&thermal_kw, &msg[3], 4);
    pump_primary.status = msg[7];
    pump_secondary.status = msg[8];
    pump_tertiary.status = msg[9];
    
    // Convert kW to MWe
    power_mwe = thermal_kw / 1000.0;
    
    #if DEBUG_UART
      Serial.printf("RX: Update - Thermal=%.1f kW → Power=%.1f MWe\n", 
                    thermal_kw, power_mwe);
    #endif
    
    sendUpdateResponse();
  }
  else {
    sendNACK();
  }
}

// ============================================
// UART PROCESSING (NON-BLOCKING)
// ============================================

void processUART() {
  // Batasi jumlah byte yang diproses per panggilan untuk non-blocking
  // INCREASED: 10 -> 20 bytes untuk handle UPDATE command (12 bytes)
  uint8_t bytes_processed = 0;
  const uint8_t MAX_BYTES_PER_CALL = 20;  // Cukup untuk 1 pesan lengkap
  
  while (UartComm.available() && bytes_processed < MAX_BYTES_PER_CALL) {
    uint8_t byte = UartComm.read();
    bytes_processed++;
    
    unsigned long current_time = millis();
    
    // Timeout check
    if (rx_state == IN_FRAME && (current_time - last_byte_time > RX_TIMEOUT_MS)) {
      rx_state = WAIT_STX;
      rx_index = 0;
    }
    
    last_byte_time = current_time;
    
    // State machine
    if (rx_state == WAIT_STX) {
      if (byte == STX) {
        rx_index = 0;
        rx_buffer[rx_index++] = byte;
        rx_state = IN_FRAME;
      }
    }
    else if (rx_state == IN_FRAME) {
      if (rx_index < sizeof(rx_buffer)) {
        rx_buffer[rx_index++] = byte;
        
        if (byte == ETX) {
          processBinaryMessage(rx_buffer, rx_index);
          rx_state = WAIT_STX;
          rx_index = 0;
        }
      }
      else {
        // Buffer overflow
        rx_state = WAIT_STX;
        rx_index = 0;
      }
    }
    
    yield();  // Feed watchdog during UART processing
  }
}

// ============================================
// DEVELOPMENT MODE - DATA SIMULATION
// ============================================

/**
 * Generate simulated data for development/testing
 * Skenario:
 * - Fase 1 (0-5s): Pompa 1 ON, daya ~30 MWe
 * - Fase 2 (5-10s): Pompa 2 ON, daya ~60 MWe
 * - Fase 3 (10-15s): Pompa 3 ON, daya ~90 MWe
 * - Fase 4 (15-25s): Semua pompa ON, daya naik 90→300 MWe
 * - Fase 5 (25-35s): Semua pompa ON, daya turun 300→90 MWe
 * - Fase 6 (35-40s): Pompa mati bertahap, daya turun ke 0
 * - Fase 7 (40-43s): SHUTDOWN - Semua mati (daya = 0)
 */
void generateDevData() {
  unsigned long elapsed = millis() - dev_start_time;
  float time_sec = elapsed / 1000.0;
  
  // Loop the cycle
  if (time_sec >= dev_cycle_duration) {
    dev_start_time = millis();
    time_sec = 0;
  }
  
  // Save previous status for change detection
  pump_primary.lastStatus = pump_primary.status;
  pump_secondary.lastStatus = pump_secondary.status;
  pump_tertiary.lastStatus = pump_tertiary.status;
  
  // Phase logic
  if (time_sec < 5.0) {
    // Fase 1: Pompa 1 ON, daya ~30 MWe
    pump_primary.status = 2;    // ON
    pump_secondary.status = 0;  // OFF
    pump_tertiary.status = 0;   // OFF
    power_mwe = 30.0;
  }
  else if (time_sec < 10.0) {
    // Fase 2: Pompa 2 ON (pompa 1 tetap ON), daya ~60 MWe
    pump_primary.status = 2;    // ON
    pump_secondary.status = 2;  // ON
    pump_tertiary.status = 0;   // OFF
    power_mwe = 60.0;
  }
  else if (time_sec < 15.0) {
    // Fase 3: Pompa 3 ON (pompa 1 & 2 tetap ON), daya ~90 MWe
    pump_primary.status = 2;    // ON
    pump_secondary.status = 2;  // ON
    pump_tertiary.status = 2;   // ON
    power_mwe = 90.0;
  }
  else if (time_sec < 25.0) {
    // Fase 4: Semua pompa ON, daya naik 90→300 MWe
    pump_primary.status = 2;    // ON
    pump_secondary.status = 2;  // ON
    pump_tertiary.status = 2;   // ON
    
    // Linear interpolation: 90 MWe at t=15s → 300 MWe at t=25s
    float phase_time = time_sec - 15.0;  // 0-10 seconds
    power_mwe = 90.0 + (phase_time / 10.0) * (300.0 - 90.0);
  }
  else if (time_sec < 35.0) {
    // Fase 5: Semua pompa ON, daya turun 300→90 MWe
    pump_primary.status = 2;    // ON
    pump_secondary.status = 2;  // ON
    pump_tertiary.status = 2;   // ON
    
    // Linear interpolation: 300 MWe at t=25s → 90 MWe at t=35s
    float phase_time = time_sec - 25.0;  // 0-10 seconds
    power_mwe = 300.0 - (phase_time / 10.0) * (300.0 - 90.0);
  }
  else if (time_sec < 40.0) {
    // Fase 6: Pompa mati bertahap, daya turun ke 0
    float phase_time = time_sec - 35.0;  // 0-5 seconds
    
    if (phase_time < 1.67) {
      // Pompa 3 OFF
      pump_primary.status = 2;
      pump_secondary.status = 2;
      pump_tertiary.status = 0;
      power_mwe = 90.0 - (phase_time / 1.67) * 30.0;  // 90→60
    }
    else if (phase_time < 3.33) {
      // Pompa 2 OFF
      pump_primary.status = 2;
      pump_secondary.status = 0;
      pump_tertiary.status = 0;
      power_mwe = 60.0 - ((phase_time - 1.67) / 1.67) * 30.0;  // 60→30
    }
    else {
      // Pompa 1 OFF
      pump_primary.status = 0;
      pump_secondary.status = 0;
      pump_tertiary.status = 0;
      power_mwe = 30.0 - ((phase_time - 3.33) / 1.67) * 30.0;  // 30→0
      if (power_mwe < 0) power_mwe = 0;
    }
  }
  else {
    // Fase 7: SHUTDOWN - Semua mati selama 3 detik
    pump_primary.status = 0;
    pump_secondary.status = 0;
    pump_tertiary.status = 0;
    power_mwe = 0.0;
  }
  
  // Convert MWe to kW for consistency with UART protocol
  thermal_kw = power_mwe * 1000.0;
  
  // Debug output
  #if DEV_DEBUG
    static unsigned long last_dev_debug = 0;
    if (millis() - last_dev_debug > 1000) {
      last_dev_debug = millis();
      Serial.printf("[DEV] t=%.1fs | Power=%.1f MWe | Pumps: P%d S%d T%d\n",
                    time_sec, power_mwe,
                    pump_primary.status, pump_secondary.status, pump_tertiary.status);
    }
  #endif
}

// ============================================
// POWER LED FUNCTIONS
// ============================================

void updatePowerLED() {
  // Calculate PWM based on power output
  int target_pwm = 0;
  
  if (power_mwe > 0) {
    target_pwm = map(power_mwe, 0, 300, 0, 255);
    target_pwm = constrain(target_pwm, 0, 255);
    
    if (target_pwm < 20) {
      target_pwm = 20;
    }
  }
  
  // Smooth transition
  if (target_pwm > current_pwm) {
    current_pwm += min(5, target_pwm - current_pwm);
  } else if (target_pwm < current_pwm) {
    current_pwm -= min(5, current_pwm - target_pwm);
  }
  
  // Skip jika nilai PWM tidak berubah (eliminasi redundant register writes)
  if (current_pwm == last_written_pwm) {
    return;
  }
  
  // Mode switching dengan hysteresis
  if (!led_mode_high && current_pwm >= PWM_THRESHOLD_HIGH) {
    // Switch ke HIGH mode
    for (int i = 0; i < NUM_LEDS; i++) {
      ledcDetach(POWER_LEDS[i]);
      pinMode(POWER_LEDS[i], OUTPUT);
      digitalWrite(POWER_LEDS[i], HIGH);
    }
    led_mode_high = true;
    
    #if DEBUG_TIMING
      Serial.println("LED Mode: HIGH (full brightness)");
    #endif
  }
  else if (led_mode_high && current_pwm < PWM_THRESHOLD_LOW) {
    // Switch kembali ke PWM mode
    for (int i = 0; i < NUM_LEDS; i++) {
      ledcAttach(POWER_LEDS[i], 5000, 8);
      ledcWrite(POWER_LEDS[i], current_pwm);
    }
    led_mode_high = false;
    
    #if DEBUG_TIMING
      Serial.println("LED Mode: PWM");
    #endif
  }
  else if (!led_mode_high) {
    for (int i = 0; i < NUM_LEDS; i++) {
      ledcWrite(POWER_LEDS[i], current_pwm);
    }
  }
  
  last_written_pwm = current_pwm;
  
  // Debug output
  static unsigned long last_debug = 0;
  #if DEBUG_TIMING
    if (millis() - last_debug > DEBUG_INTERVAL) {
      last_debug = millis();
      const char* mode_str = led_mode_high ? "HIGH" : "PWM";
      Serial.printf("Power: %.1f MWe | PWM: %d | Mode: %s\n", 
                    power_mwe, current_pwm, mode_str);
    }
  #endif
}



// ============================================
// SETUP
// ============================================

void setup() {
  Serial.begin(115200);
  delay(500);
  
  Serial.println("\n\n===========================================");
  Serial.println("ESP32 Power Indicator - SPI HARDWARE VERSION");
  Serial.println("===========================================");
  Serial.println("Pin Configuration:");
  Serial.println("  Power LEDs: GPIO 25, 26, 27, 32");
  Serial.println("  SPI Hardware: MOSI=23, SCK=18, LATCH=5");
  Serial.println("  UART: RX=16, TX=17");
  Serial.println("===========================================");
  
  // Initialize UART
  UartComm.begin(UART_BAUD, SERIAL_8N1, 16, 17);
  
  // Initialize LATCH pin
  pinMode(LATCH_PIN_GLOBAL, OUTPUT);
  digitalWrite(LATCH_PIN_GLOBAL, HIGH);
  Serial.println("✓ LATCH pin initialized (GPIO 5)");
  
  // Initialize SPI Hardware
  SPI.begin(SPI_CLOCK_PIN, -1, SPI_MOSI_PIN, -1);
  Serial.println("✓ SPI Hardware initialized (1MHz, MSBFIRST, MODE0)");
  
  delay(10);
  
  // Clear all shift registers
  Serial.println("Clearing all shift registers...");
  for (int i = 0; i < NUM_IC; i++) {
    sr_data[i] = 0x00;
  }
  shiftRegisterWrite();
  Serial.println("✓ Shift registers cleared");
  
  // Initialize all power LEDs
  Serial.println("Initializing 4 power LEDs...");
  for (int i = 0; i < NUM_LEDS; i++) {
    pinMode(POWER_LEDS[i], OUTPUT);
    ledcAttach(POWER_LEDS[i], 5000, 8);
    ledcWrite(POWER_LEDS[i], 0);
    Serial.printf("  LED %d: GPIO %d\n", i+1, POWER_LEDS[i]);
  }
  
  // Quick LED test
  Serial.println("Testing power LEDs (quick flash)...");
  for (int i = 0; i < 2; i++) {
    for (int j = 0; j < NUM_LEDS; j++) {
      ledcWrite(POWER_LEDS[j], 255);
    }
    delay(100);
    for (int j = 0; j < NUM_LEDS; j++) {
      ledcWrite(POWER_LEDS[j], 0);
    }
    delay(100);
  }
  Serial.println("✓ LED test complete");
  
  Serial.println("\nUART ready at 115200 baud");
  Serial.println("Timing Configuration:");
  Serial.printf("  Animation Step: %d ms\n", ANIM_STEP_DELAY);
  Serial.printf("  LED Update: %d ms interval\n", LED_UPDATE_INTERVAL);
  Serial.println("===========================================");
  
  #if DEV_MODE
    Serial.println("⚠️  DEVELOPMENT MODE ACTIVE");
    Serial.println("   Data simulasi akan digunakan (tanpa UART)");
    Serial.println("   Skenario: Pompa 1→2→3, lalu daya naik 90→300 MWe");
    dev_start_time = millis();
  #else
    Serial.println("✓ PRODUCTION MODE - Waiting for UART data");
  #endif
  
  Serial.println("===========================================");
  Serial.println("ESP32 Power Indicator READY");
  Serial.println("===========================================\n");
}

// ============================================
// MAIN LOOP
// ============================================

void loop() {
  static unsigned long last_led_time = 0;
  static unsigned long last_uart_time = 0;
  static unsigned long last_dev_time = 0;
  
  unsigned long current_time = millis();
  
  // 1. Update ring animation at fixed interval
  if (current_time - lastAnimTime >= ANIM_STEP_DELAY) {
    // Rotate ring pattern for all ICs
    for (int i = 0; i < NUM_IC; i++) {
      ring_pattern[i] = ringShift(ring_pattern[i]);
    }
    
    // Update buffer based on pump status
    updateSRBuffer();
    
    // Write to shift registers
    shiftRegisterWrite();
    
    lastAnimTime = current_time;
  }
  
  // 2. Update LED power dengan interval terpisah
  if (current_time - last_led_time >= LED_UPDATE_INTERVAL) {
    updatePowerLED();
    last_led_time = current_time;
  }
  
  // 3. Data source: Development mode atau UART
  #if DEV_MODE
    // Development mode: Generate simulated data
    if (current_time - last_dev_time >= DEV_UPDATE_INTERVAL) {
      generateDevData();
      last_dev_time = current_time;
    }
  #else
    // Production mode: Process UART data
    if (current_time - last_uart_time >= UART_PROCESS_INTERVAL) {
      processUART();
      last_uart_time = current_time;
    }
  #endif
  
  // Yield untuk menjaga stabilitas sistem
  yield();
}