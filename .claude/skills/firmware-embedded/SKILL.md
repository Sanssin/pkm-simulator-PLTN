---
name: Firmware-Embedded-Systems
description: GPIO, sensors, threading, ESP32/Raspberry Pi embedded patterns
---

# Skill: Firmware & Embedded Systems — Raspberry Pi + ESP32

## Konteks Proyek

Simulator PLTN (PWR) menggunakan arsitektur 3-tier:
- **Raspberry Pi 4** (Python 3.7+): Master controller, 9 threads, event queue pattern
- **ESP32 #1 (ESP-BC)** (C++/Arduino): Aktuator fisik (servo, motor, relay, LED)
- **ESP32 #2 (ESP-E)** (C++/Arduino): LED visualisasi (shift register, power LEDs)

Komunikasi Raspi→ESP via **UART Binary Protocol** (115200 baud, CRC8-MAXIM, ACK/NACK).
I2C hanya digunakan untuk 9× OLED SSD1306 via TCA9548A multiplexer.

---

## GPIO & Hardware Interface Patterns

### Pattern 1: Button Input (Pull-Up, Active LOW)

Semua 17 tombol menggunakan pull-up internal, active LOW (tombol hubungkan pin ke GND).

```python
# raspi_gpio_buttons.py — AUTHORITATIVE pin mapping
class ButtonPin(IntEnum):
    PUMP_PRIMARY_ON = 11
    PUMP_PRIMARY_OFF = 6
    PUMP_SECONDARY_ON = 13
    PUMP_SECONDARY_OFF = 19
    PUMP_TERTIARY_ON = 26
    PUMP_TERTIARY_OFF = 21
    SAFETY_ROD_UP = 20
    SAFETY_ROD_DOWN = 16
    SHIM_ROD_UP = 12
    SHIM_ROD_DOWN = 7
    REGULATING_ROD_UP = 8
    REGULATING_ROD_DOWN = 25
    PRESSURE_UP = 24
    PRESSURE_DOWN = 23
    START_AUTO_SIMULATION = 17
    REACTOR_RESET = 27
    EMERGENCY = 18

# Setup pattern — BCM mode, pull-up, active LOW
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
for pin in ButtonPin:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
```

⚠️ **PENTING**: `raspi_config.py` juga mendefinisikan button pins tapi OUTDATED dan TIDAK DIGUNAKAN. `raspi_gpio_buttons.py` `ButtonPin` enum adalah **satu-satunya source of truth** untuk pin mapping tombol.

### Pattern 2: Hybrid Button Detection (Edge + Level)

Proyek ini menggunakan 2 tipe deteksi tombol, bukan satu:

```python
# raspi_gpio_buttons.py — ButtonHandler.__init__()

# EDGE DETECTION: Trigger SEKALI per tekan (toggle actions)
self.EDGE_BUTTONS = {
    ButtonPin.PUMP_PRIMARY_ON, ButtonPin.PUMP_PRIMARY_OFF,
    ButtonPin.PUMP_SECONDARY_ON, ButtonPin.PUMP_SECONDARY_OFF,
    ButtonPin.PUMP_TERTIARY_ON, ButtonPin.PUMP_TERTIARY_OFF,
    ButtonPin.START_AUTO_SIMULATION, ButtonPin.REACTOR_RESET,
    ButtonPin.EMERGENCY
}

# LEVEL DETECTION: Trigger BERULANG selama ditahan (continuous actions)
self.LEVEL_BUTTONS = {
    ButtonPin.SAFETY_ROD_UP, ButtonPin.SAFETY_ROD_DOWN,
    ButtonPin.SHIM_ROD_UP, ButtonPin.SHIM_ROD_DOWN,
    ButtonPin.REGULATING_ROD_UP, ButtonPin.REGULATING_ROD_DOWN,
    ButtonPin.PRESSURE_UP, ButtonPin.PRESSURE_DOWN
}
```

Edge detection menggunakan 2-sample confirmation:
```python
# raspi_gpio_buttons.py — check_all_buttons()
if current_state == GPIO.LOW and self.last_state[pin] == GPIO.HIGH:
    time.sleep(0.002)  # Wait 2ms
    if GPIO.input(pin) == GPIO.LOW:  # Still pressed? (2-sample confirm)
        if time_since_last > self.debounce_time:  # 30ms debounce
            # Trigger callback
```

### Pattern 3: Buzzer PWM Output (Software PWM)

```python
# raspi_buzzer_alarm.py — GPIO 22, software PWM
BUZZER_PIN = 22  # Passive buzzer
# Setup: GPIO.setup(BUZZER_PIN, GPIO.OUT)
# Tone generation via software PWM (RPi.GPIO.PWM)
```

### Pattern 4: ESP32 Servo (ESP32Servo library)

```cpp
// esp_utama_uart.ino — 3 servo untuk control rods
#include <ESP32Servo.h>

Servo servo_safety;      // GPIO 13
Servo servo_shim;        // GPIO 12
Servo servo_regulating;  // GPIO 14

// Mapping: 0-100% → 0-180°
int angle = (int)map(rod_actual, 0, 100, 0, 180);
servo_safety.write(angle);
```

### Pattern 5: ESP32 Motor PWM (LEDC)

```cpp
// esp_utama_uart.ino — L298N motor driver
#define MOTOR_PUMP_PRIMARY    4
#define MOTOR_PUMP_SECONDARY  5
#define MOTOR_PUMP_TERTIARY   18
#define MOTOR_TURBINE         19
#define MOTOR_TURBINE_IN1     23  // Direction control
#define MOTOR_TURBINE_IN2     15

#define PWM_FREQ       5000   // 5 kHz
#define PWM_RESOLUTION 8      // 8-bit (0-255)

// Mapping: 0-100% → 0-255 PWM
int pwm_value = map((int)pump_actual, 0, 100, 0, 255);
ledcWrite(MOTOR_PUMP_PRIMARY, pwm_value);
```

### Pattern 6: ESP32 Relay Output (Active LOW)

```cpp
// esp_utama_uart.ino — Cooling Tower relays
const int RELAY_CT1 = 27;
const int RELAY_CT2 = 26;
const int RELAY_CT3 = 25;
const int RELAY_CT4 = 32;

// Active LOW! (cmd=1 → relay ON → LOW)
digitalWrite(RELAY_CT1, humid_ct1_cmd ? LOW : HIGH);
```

### Pattern 7: ESP32 Shift Register (74HC595)

```cpp
// esp_visualizer_uart.ino — 3× 74HC595 daisy-chained
#define SR_DATA  23   // SPI MOSI
#define SR_CLOCK 18   // SPI SCK
#define SR_LATCH 5    // Latch pin

// 24-bit output (3 bytes, MSB first)
digitalWrite(SR_LATCH, LOW);
shiftOut(SR_DATA, SR_CLOCK, MSBFIRST, byte3);  // Third register
shiftOut(SR_DATA, SR_CLOCK, MSBFIRST, byte2);  // Second register
shiftOut(SR_DATA, SR_CLOCK, MSBFIRST, byte1);  // First register
digitalWrite(SR_LATCH, HIGH);
```

---

## Sensor Reading Patterns

Proyek ini **tidak menggunakan sensor fisik** — semua parameter disimulasikan via software. Input hanya dari tombol operator.

"Sensor" dalam konteks ini adalah **feedback dari ESP-BC** yang mengirim data kalkulasi:

```python
# raspi_uart_master.py — Data dari ESP-BC
@dataclass
class ESP_BC_Data:
    safety_actual: int = 0       # Posisi rod aktual (0-100%)
    shim_actual: int = 0
    regulating_actual: int = 0
    kw_thermal: float = 0.0      # Daya thermal (kW)
    power_level: float = 0.0     # Level daya turbin (0-100%)
    turbine_speed: float = 0.0   # Kecepatan turbin (0-100%)
    state: int = 0               # Turbine FSM state
    # ... pump speeds, humidifier status
```

```python
# raspi_main_panel.py — esp_communication_thread() membaca data dari ESP-BC
with self.uart_lock:
    response = self.uart_master.send_update_esp_bc(...)
    if response:
        with self.state_lock:
            esp_data = self.uart_master.get_esp_bc_data()
            self.state.thermal_kw = esp_data.kw_thermal
            self.state.turbine_speed = esp_data.turbine_speed
```

Error handling untuk pembacaan UART:
```python
# raspi_uart_master.py — Retry dengan exponential backoff
MAX_RETRIES = 3
RETRY_DELAYS = [0.03, 0.05, 0.1]  # 30ms, 50ms, 100ms

for attempt in range(MAX_RETRIES):
    try:
        # Send command, read response
        response = self._send_binary_command(...)
        if response:
            return response  # Success
    except Exception as e:
        logger.warning(f"Attempt {attempt+1} failed: {e}")
        time.sleep(RETRY_DELAYS[attempt])
```

---

## Main Loop Architecture

### Raspberry Pi: Multi-Threaded, Event Queue Pattern

Entry point: `raspi_main_panel.py` → `PLTNPanelController.run()`

9 threads dijalankan sebagai daemon threads:

```python
# raspi_main_panel.py — run()
threads = [
    Thread(target=self.button_polling_thread,         name="ButtonThread"),     # 5ms
    Thread(target=self.button_hold_thread,             name="ButtonHoldThread"), # 50ms
    Thread(target=self.button_event_processor_thread,  name="EventThread"),      # 10ms
    Thread(target=self.control_logic_thread,           name="ControlThread"),    # 50ms
    Thread(target=self.esp_communication_thread,       name="ESPCommThread"),    # 50ms
    Thread(target=self.oled_update_thread,             name="OLEDThread"),       # 200ms
    Thread(target=self.health_monitoring_thread,       name="HealthThread"),     # One-shot
    Thread(target=self.auto_simulation_thread,         name="AutoSimThread"),    # On demand
    Thread(target=self.state_export_thread,            name="StateExportThread") # 100ms
]
for t in threads:
    t.daemon = True
    t.start()
```

Alur data non-blocking:
```
ButtonPolling (5ms) → Queue.put(event) → EventProcessor (10ms) → state update
                                                                → esp_send_immediate.set()
                                                                        ↓
ESPCommThread (50ms / immediate) → UART send/receive → state feedback update
ControlLogic (50ms) → interlock, humidifier, alarm, pump timing
OLEDUpdate (200ms) → display refresh with interpolation
StateExport (100ms) → JSON file for video display
```

### ESP32: Single-Threaded `loop()` (~10ms cycle

```cpp
// esp_utama_uart.ino — loop()
void loop() {
    // 1. Check for incoming UART commands
    processUART();          // Parse binary frames, update targets

    // 2. Smooth rod interpolation
    updateControlRods();    // Gradual servo movement

    // 3. Calculate reactor physics
    calculateThermalPower(); // Quadratic thermal model
    updateTurbineState();    // FSM: IDLE→STARTING→RUNNING→SHUTDOWN

    // 4. Update actuators
    updatePumpSpeeds();     // Gradual PWM ramping
    updateTurbineSpeed();   // PWM based on rod average
    updateHumidifiers();    // Relay ON/OFF
    updateCherenkovLED();   // Blue LED brightness

    // 5. Send response back
    sendUpdateResponse();   // Binary response with all actuals

    delay(10);  // 10ms loop = ~100 Hz
}
```

---

## Threading & Concurrency

### 2 Locks, 9 Threads

```python
# raspi_main_panel.py — PLTNPanelController.__init__()
self.state_lock = threading.Lock()   # Protects PanelState dataclass
self.uart_lock = threading.Lock()    # Protects UART serial port access
```

**Lock ordering** (untuk menghindari deadlock):
- `state_lock` HARUS diambil SEBELUM `uart_lock` jika butuh keduanya
- Tidak pernah hold `uart_lock` kemudian acquire `state_lock`

### Event Queue Pattern (Thread-Safe Button Handling)

```python
# raspi_main_panel.py
self.button_event_queue = Queue(maxsize=100)

# CALLBACK (dalam interrupt context) — ringan, tanpa lock:
def on_pressure_up(self):
    self.button_event_queue.put(ButtonEvent.PRESSURE_UP)  # Non-blocking

# PROCESSOR (dalam thread terpisah) — berat, dengan lock:
def button_event_processor_thread(self):
    while self.state.running:
        event = self.button_event_queue.get(timeout=0.01)  # 10ms
        self.process_button_event(event)  # Acquires state_lock
        self.esp_send_immediate.set()     # Trigger ESP update
```

### Immediate ESP Communication Trigger

```python
# threading.Event() untuk bypass timer 50ms saat ada button press
self.esp_send_immediate = threading.Event()

# Di ESP comm thread:
def esp_communication_thread(self):
    while self.state.running:
        self.esp_send_immediate.wait(timeout=0.05)  # 50ms or immediate
        self.esp_send_immediate.clear()
        # ... send UART data
```

### Shared State Pattern

```python
# SELALU gunakan state_lock saat akses PanelState:
with self.state_lock:
    self.state.pressure = min(self.state.pressure + 1.0, 200.0)

# MINIMAL lock hold time — jangan lakukan I/O atau sleep di dalam lock!
with self.state_lock:
    local_copy = self.state.pressure  # Copy keluar
# Lakukan I/O di luar lock
logger.info(f"Pressure: {local_copy}")
```

---

## Error Handling Patterns

### Pattern 1: Graceful Degradation (Hardware Init)

Hardware diinisialisasi dalam 2 fase — critical dan optional:

```python
# raspi_main_panel.py — __init__()

# CRITICAL: Gagal = raise exception (program berhenti)
try:
    self.init_multiplexers()
    self.init_uart_master()
    self.init_buttons()
except Exception as e:
    logger.error(f"Critical hardware initialization failed: {e}")
    raise  # Program tidak bisa jalan tanpa ini

# OPTIONAL: Gagal = warning, set None (program tetap jalan)
self.init_humidifier()   # Won't raise
self.init_buzzer()       # Won't raise
self.init_oled_displays()  # Timeout 5s, won't raise
```

Setiap akses ke komponen optional dicek `None`:
```python
if self.buzzer:
    try:
        self.buzzer.sound_interlock_warning(duration=1.5)
    except Exception:
        pass  # Silent fail — buzzer bukan critical
```

### Pattern 2: Thread Error Isolation

Setiap thread memiliki try/except sendiri yang tidak crash thread lain:

```python
def control_logic_thread(self):
    while self.state.running:
        try:
            with self.state_lock:
                # ... all control logic
            time.sleep(0.05)
        except Exception as e:
            logger.error(f"Error in control logic thread: {e}")
            import traceback
            logger.error(traceback.format_exc())
            time.sleep(0.1)  # Slow down on error to prevent tight loop
```

### Pattern 3: UART Retry with Backoff

```python
# raspi_uart_master.py
MAX_RETRIES = 3
RETRY_DELAYS = [0.03, 0.05, 0.1]  # Exponential-ish backoff

for attempt in range(MAX_RETRIES):
    try:
        # ... send and receive
        if crc_valid:
            return response
        else:
            logger.warning(f"CRC mismatch (attempt {attempt+1})")
    except serial.SerialException as e:
        logger.error(f"Serial error: {e}")
    time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)-1)])
```

### Pattern 4: Timeout pada OLED Init

```python
# raspi_main_panel.py — init_oled_displays()
init_thread = threading.Thread(target=init_displays, daemon=True)
init_thread.start()
init_thread.join(timeout=5.0)  # Max 5 detik

if init_thread.is_alive():
    logger.warning("OLED initialization timeout - continuing without displays")
    self.oled_manager = None
```

---

## Library-Specific Notes

### RPi.GPIO
- **Mode**: BCM (bukan BOARD) — `GPIO.setmode(GPIO.BCM)`
- **Button input**: Pull-up internal, active LOW — `GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)`
- **Buzzer output**: Software PWM pada GPIO 22 — `GPIO.PWM(pin, freq)`
- **Import guard**: `try: import RPi.GPIO ... except ImportError: GPIO_AVAILABLE = False`
- **Cleanup**: `GPIO.cleanup()` dipanggil di `shutdown()`
- **Warning suppressed**: `GPIO.setwarnings(False)` — karena re-init saat restart

### pyserial
- **2 port bersamaan**: `/dev/ttyAMA0` (ESP-BC) + `/dev/ttyAMA3` (ESP-E)
- **Binary mode**: Semua komunikasi via `bytes`, bukan string
- **Timeout**: 0.5 detik — `serial.Serial(port, baudrate=115200, timeout=0.5)`
- **Flush setelah write**: `ser.write(data); ser.flush()`

### smbus2
- **Bus 1**: `SMBus(1)` — I2C bus default Raspberry Pi
- **Hanya untuk OLED** via TCA9548A multiplexer
- **Tidak digunakan untuk ESP** (sudah migrasi ke UART)

### adafruit-circuitpython-ssd1306
- **9 display** via TCA9548A multiplexer (alamat 0x70)
- **Resolusi**: 128×32 pixel (0.91 inch OLED)
- **I2C address**: 0x3C (semua display sama, dibedakan via multiplexer channel)

### ESP32Servo (Arduino)
- **3 servo**: GPIO 13, 12, 14
- **Range**: 0–180° (mapped dari 0–100% rod position)
- **Smooth interpolation**: Rod actual mendekati target secara gradual per loop

### Pillow (PIL)
- **Digunakan oleh**: `raspi_oled_manager.py`
- **Fungsi**: Render text/grafik ke image buffer → kirim ke OLED
- **Mode**: `Image.new("1", (128, 32))` — 1-bit monochrome

---

## Pola per Pengembangan

### Pengembangan 1: UART Binary Protocol
**Pola firmware**: Frame-based binary protocol dengan state machine parsing
```cpp
// esp_utama_uart.ino — Frame parser
enum RxState { WAIT_STX, IN_FRAME };
// Cari STX → buffer payload → cek ETX → verify CRC → process
```
**Pola Python**: Encoder/decoder dataclass → bytes
```python
# raspi_uart_master.py — Encode command
def _encode_esp_bc_command(self, data: ESP_BC_Data) -> bytes:
    payload = struct.pack('BBBBBBBBBBB', ...)
    crc = crc8_maxim(bytes([CMD_UPDATE, len(payload)]) + payload)
    return bytes([STX, CMD_UPDATE, len(payload)]) + payload + bytes([crc, ETX])
```

### Pengembangan 2: Staged Cooling Tower
**Pola firmware**: Relay ON/OFF berdasarkan command dari Raspi
```cpp
digitalWrite(RELAY_CT1, humid_ct1_cmd ? LOW : HIGH);  // Active LOW relay
```
**Pola Python**: Threshold-based activation dengan hysteresis
```python
# raspi_humidifier_control.py
if thermal_kw >= 60000:   ct1 = True   # 60 MWe
if thermal_kw >= 120000:  ct2 = True   # 120 MWe
if thermal_kw >= 180000:  ct3 = True   # 180 MWe
if thermal_kw >= 240000:  ct4 = True   # 240 MWe
```

### Pengembangan 3: Video Display
**Pola**: State export via JSON file (decoupled, atomic write)
```python
# raspi_main_panel.py — state_export_thread()
state_dict = asdict(self.state)
temp_file = self.state_export_file.with_suffix('.tmp')
temp_file.write_text(json.dumps(state_dict))
temp_file.rename(self.state_export_file)  # Atomic rename
```

### Pengembangan 4: Cherenkov LED
**Pola firmware**: PWM brightness proporsional terhadap posisi rod
```cpp
float avg = (shim_actual + regulating_actual) / 2.0;
if (avg < 0.5) avg = 0.0;  // Threshold
int pwm = map((int)avg, 0, 100, 0, 255);
ledcWrite(LED_CHERENKOV, pwm);
```

### Pengembangan 5: Inactivity Auto-Reset
**Pola**: Timer di control logic thread, inject event ke queue
```python
# raspi_main_panel.py — control_logic_thread()
if current_time - self.last_button_time >= 900:  # 15 min
    self.button_event_queue.put(ButtonEvent.REACTOR_RESET)
    self.last_button_time = current_time  # Reset timer
```

---

## Contoh Kode Referensi

### Menambah Tombol Baru (Contoh: tombol MUTE_ALARM)

```python
# 1. raspi_gpio_buttons.py — Tambah pin
class ButtonPin(IntEnum):
    # ... existing pins ...
    MUTE_ALARM = 9  # Pilih GPIO yang belum dipakai

# 2. raspi_gpio_buttons.py — Tambah nama
BUTTON_NAMES = {
    # ... existing names ...
    ButtonPin.MUTE_ALARM: "Mute Alarm",
}

# 3. raspi_gpio_buttons.py — Tentukan tipe deteksi di __init__()
self.EDGE_BUTTONS.add(ButtonPin.MUTE_ALARM)  # Edge karena toggle

# 4. raspi_main_panel.py — Tambah ButtonEvent enum
class ButtonEvent(Enum):
    MUTE_ALARM = "mute_alarm"

# 5. raspi_main_panel.py — Tambah callback ringan
def on_mute_alarm(self):
    self.button_event_queue.put(ButtonEvent.MUTE_ALARM)

# 6. raspi_main_panel.py — Register callback di init_buttons()
self.button_manager.register_callback(ButtonPin.MUTE_ALARM, self.on_mute_alarm)

# 7. raspi_main_panel.py — Handle event di process_button_event()
elif event == ButtonEvent.MUTE_ALARM:
    if self.buzzer:
        self.buzzer.mute_toggle()
```

### Menambah Aktuator ESP-BC Baru (Contoh: LED tambahan)

```cpp
// 1. esp_utama_uart.ino — Define pin
const int LED_NEW = 2;  // GPIO yang tersedia

// 2. esp_utama_uart.ino — Setup di setup()
ledcAttach(LED_NEW, PWM_FREQ, PWM_RESOLUTION);

// 3. esp_utama_uart.ino — Update command length
#define UPDATE_CMD_LEN 16  // +1 byte dari 15

// 4. esp_utama_uart.ino — Parse byte baru di processUpdateCommand()
uint8_t new_led_value = rx_buffer[13];  // Index setelah payload terakhir

// 5. raspi_uart_master.py — Update encoder
# Tambah byte ke payload struct.pack()
```

⚠️ Setiap perubahan protocol HARUS di-update di KEDUA sisi (Python + Arduino) secara sinkron!

---

## Common Debugging Steps

### UART Communication Failure
1. Cek health check output: `python3 raspi_main_panel.py` — lihat "✓ UART Master initialized"
2. Cek device exists: `ls -la /dev/ttyAMA0 /dev/ttyAMA3`
3. Cek permissions: `sudo usermod -a -G dialout $USER`
4. Cek kabel: TX Raspi → RX ESP, RX Raspi → TX ESP (cross!)
5. Cek serial monitor ESP: `Serial.begin(115200)` untuk debug output
6. Cek CRC errors di log: grep "CRC mismatch" atau "NACK"

### Button Tidak Responsif
1. Cek GPIO mode: harus BCM (`GPIO.setmode(GPIO.BCM)`)
2. Cek pull-up: `GPIO.input(pin)` harus HIGH saat tidak ditekan
3. Cek debounce: default 30ms (`debounce_time=0.03`)
4. Cek tipe deteksi: edge vs level (salah tipe = perilaku aneh)
5. Cek event queue: `button_event_queue.qsize()` — kalau penuh (100), ada bottleneck

### Motor/Servo Tidak Bergerak
1. Cek UART communication (langkah di atas)
2. Cek power supply L298N: butuh 12V terpisah untuk motor
3. Cek ESP serial monitor: apakah menerima command values
4. Cek PWM channel conflicts: `ledcAttach()` tidak boleh duplikat channel
5. Servo jitter: cek power supply 5V cukup arus (3 servo × ~500mA)

### OLED Tidak Menampilkan
1. Cek I2C: `i2cdetect -y 1` — harus terlihat 0x70 (TCA9548A)
2. Cek multiplexer channel: tiap OLED di channel berbeda (0-7)
3. Cek timeout: init timeout 5 detik — bisa terlalu pendek jika banyak display
4. Cek address: semua OLED harus 0x3C

### Thread Deadlock
1. Cek lock ordering: `state_lock` sebelum `uart_lock`
2. Cek nested locks: jangan acquire lock yang sudah dipegang
3. Cek heartbeat log: setiap thread log heartbeat — yang berhenti = stuck
4. Gejala: program freeze, tidak ada output log baru
