# Pengembangan 2: Migrasi Aktuator ke Raspberry Pi (Single Controller)

> **Status**: 📝 Planning  
> **Prioritas**: High  
> **Dibuat**: 2026-03-23  
> **Dependency**: Setelah Pengembangan #1 (Touchscreen Panel) — GPIO freed

---

## 📋 Ringkasan

**Tujuan**: Menghapus 2 ESP32 (ESP-BC dan ESP-E) dan memindahkan kontrol semua aktuator langsung ke Raspberry Pi 4 untuk mengurangi latency dan menyederhanakan arsitektur.

**Perubahan Arsitektur**:
- ❌ **Dihapus**: ESP-BC (servo, motor, relay, cherenkov) + ESP-E (LED flow)
- ❌ **Dihapus**: UART communication protocol (raspi_uart_master.py)
- ✅ **Ditambah**: Direct GPIO control dengan pigpio dan rpi_ws281x

**Benefit**:
- ⚡ Latency lebih rendah (tidak ada UART roundtrip ~10-20ms)
- 🔧 Arsitektur lebih sederhana (1 codebase vs 3)
- 🛠️ Lebih mudah debug dan maintain

---

## 🔧 Spesifikasi Hardware

### Aktuator yang Dimigrasi

| Aktuator | Qty | Dari | Ke | Library |
|----------|-----|------|-----|---------|
| Servo Motor (control rod) | 3 | ESP-BC | RPi GPIO + pigpio | pigpio |
| Motor DC (pump + turbine) | 4 | ESP-BC | RPi GPIO + pigpio | pigpio |
| Relay (Cooling Tower) | 4 | ESP-BC | RPi GPIO | RPi.GPIO |
| Cherenkov LED | 1 | ESP-BC | RPi GPIO + pigpio | pigpio |
| WS2812 LED Strip | 3 | ESP-E (74HC595) | RPi GPIO | rpi_ws281x |

### Hardware Baru/Berubah

| Item | Sebelum | Sesudah |
|------|---------|---------|
| Motor Driver | L298N | VNH2SP30 (2 module dual-channel) |
| Flow LED | 3× 74HC595 + 24 LED | 3× WS2812 LED Strip |
| Servo Driver | ESP32 internal | pigpio (DMA-based PWM) |

### GPIO Mapping (Final)

| Aktuator | GPIO (BCM) | Tipe | Notes |
|----------|------------|------|-------|
| Servo Safety | GPIO 12 | PWM (pigpio) | 50Hz servo signal |
| Servo Shim | GPIO 13 | PWM (pigpio) | 50Hz servo signal |
| Servo Regulating | GPIO 16 | PWM (pigpio) | 50Hz servo signal |
| Motor Pump Primary | GPIO 17 | PWM (pigpio) | VNH2SP30 Ch1 |
| Motor Pump Secondary | GPIO 20 | PWM (pigpio) | VNH2SP30 Ch2 |
| Motor Pump Tertiary | GPIO 21 | PWM (pigpio) | VNH2SP30 Ch3 |
| Motor Turbine | GPIO 26 | PWM (pigpio) | VNH2SP30 Ch4 |
| Relay CT1 | GPIO 6 | Digital | Cooling Tower 1 |
| Relay CT2 | GPIO 7 | Digital | Cooling Tower 2 |
| Relay CT3 | GPIO 8 | Digital | Cooling Tower 3 |
| Relay CT4 | GPIO 25 | Digital | Cooling Tower 4 |
| Cherenkov LED | GPIO 24 | PWM (pigpio) | Blue LED brightness |
| WS2812 Primary | GPIO 18 | Data (PWM) | Flow animation loop 1 |
| WS2812 Secondary | GPIO 19 | Data | Flow animation loop 2 |
| WS2812 Tertiary | GPIO 10 | Data (SPI MOSI) | Flow animation loop 3 |
| Buzzer | GPIO 22 | PWM | Existing, tidak berubah |
| **Total Used** | **16** | | |

**GPIO Reserved (tidak dipakai):**
- GPIO 2, 3 — I2C (available jika tidak ada device)
- GPIO 4, 5 — UART3 (freed, tidak perlu lagi)
- GPIO 14, 15 — UART0 (freed, tidak perlu lagi)

---

## 🎯 Keputusan Teknis

### ✅ Library: pigpio untuk PWM

**Alasan**:
- DMA-based PWM, presisi tinggi
- Support unlimited software PWM channels
- Jitter minimal untuk servo control
- Well-maintained library

**Contoh penggunaan**:
```python
import pigpio

pi = pigpio.pi()

# Servo control (50Hz, 500-2500µs pulse)
SERVO_SAFETY = 12
pi.set_servo_pulsewidth(SERVO_SAFETY, 1500)  # Center position

# Motor PWM (5kHz)
MOTOR_PUMP_PRIMARY = 17
pi.set_PWM_frequency(MOTOR_PUMP_PRIMARY, 5000)
pi.set_PWM_dutycycle(MOTOR_PUMP_PRIMARY, 128)  # 50% duty

# Cleanup
pi.stop()
```

### ✅ Library: rpi_ws281x untuk LED Strip

**Alasan**:
- Native support untuk WS2812B
- Menggunakan PWM/PCM/SPI hardware
- Reliable timing

**Contoh penggunaan**:
```python
from rpi_ws281x import PixelStrip, Color

# Konfigurasi per strip
LED_COUNT = 30  # LED per meter, sesuaikan
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 255

strip_primary = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, False, LED_BRIGHTNESS)
strip_primary.begin()

# Set color dengan animasi
def flow_animation(strip, color, speed):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
        strip.show()
        time.sleep(speed)
```

### ✅ Motor Driver: VNH2SP30

**Spesifikasi**:
- 30A continuous, 41A peak
- PWM control up to 20kHz
- Built-in protection (overcurrent, thermal)

**Konfigurasi**:
- 2 module dual-channel untuk 4 motor
- Direction di-set fixed (hardware)
- Hanya butuh 1 PWM pin per motor

### ✅ Turbine Direction: Fixed

Turbine motor direction di-set permanent ke satu arah (forward). Tidak perlu GPIO untuk direction control.

---

## 📐 Arsitektur Sistem Baru

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Raspberry Pi 4                                │
├─────────────────────────────────────────────────────────────────────┤
│  Process 1: touch_panel.py (dari Pengembangan #1)                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ PyQt5 Application - HDMI0 (10" touchscreen 1280x800)           │ │
│  │ ├─ Touch Input Handler                                          │ │
│  │ ├─ UI Displays (pengganti OLED)                                │ │
│  │ ├─ Write: /tmp/pltn_input.json                                  │ │
│  │ └─ Read: /tmp/pltn_state.json                                   │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│                    JSON IPC  │                                       │
│                              ▼                                       │
│  Process 2: raspi_main_panel.py (SIGNIFICANTLY MODIFIED)           │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Control Logic + Actuator Control (ALL IN ONE)                  │ │
│  │ ├─ InputReader: Read /tmp/pltn_input.json                      │ │
│  │ ├─ EventProcessor                                               │ │
│  │ ├─ ControlLogic (reactor simulation)                           │ │
│  │ ├─ ActuatorController (NEW):                                    │ │
│  │ │   ├─ ServoController (pigpio) → 3 servos                     │ │
│  │ │   ├─ MotorController (pigpio) → 4 motors (VNH2SP30)          │ │
│  │ │   ├─ RelayController (RPi.GPIO) → 4 relays                   │ │
│  │ │   ├─ CherenkovController (pigpio) → 1 LED                    │ │
│  │ │   └─ LEDStripController (rpi_ws281x) → 3 WS2812 strips       │ │
│  │ ├─ BuzzerAlarm (GPIO 22)                                        │ │
│  │ └─ StateExport: Write /tmp/pltn_state.json                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│                    JSON IPC  │                                       │
│                              ▼                                       │
│  Process 3: video_display_app.py (unchanged)                        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Pygame Application - HDMI1                                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│  Direct GPIO Control (NO MORE UART)                                  │
│  ├─ pigpio daemon (PWM/Servo)                                       │
│  ├─ RPi.GPIO (Digital outputs)                                      │
│  └─ rpi_ws281x (LED strips)                                         │
└─────────────────────────────────────────────────────────────────────┘

Hardware Connections:
┌────────────────────────────────────────────────────────────────────┐
│  AKTUATOR                                                           │
│  ├─ 3× Servo Motor (Safety, Shim, Regulating) ← GPIO 12, 13, 16   │
│  ├─ 4× Motor DC via VNH2SP30 ← GPIO 17, 20, 21, 26                 │
│  │   └─ 3× Pump (Primary, Secondary, Tertiary) + 1× Turbine       │
│  ├─ 4× Relay (CT1-4) ← GPIO 6, 7, 8, 25                            │
│  ├─ 1× Cherenkov LED ← GPIO 24                                      │
│  ├─ 3× WS2812 LED Strip ← GPIO 18, 19, 10                          │
│  └─ 1× Buzzer ← GPIO 22                                             │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Detail Implementasi

### Servo Controller

```python
import pigpio

class ServoController:
    """Control 3 servo motors untuk control rods menggunakan pigpio"""
    
    # Servo GPIO pins
    SERVO_PINS = {
        'safety': 12,
        'shim': 13,
        'regulating': 16
    }
    
    # Servo pulse width range (µs)
    PULSE_MIN = 500   # 0% position
    PULSE_MAX = 2500  # 100% position
    
    def __init__(self, pi):
        self.pi = pi
        self.current_positions = {'safety': 0, 'shim': 0, 'regulating': 0}
    
    def set_position(self, rod_name, position_percent):
        """Set rod position (0-100%)"""
        position_percent = max(0, min(100, position_percent))
        
        # Convert percentage to pulse width
        pulse_width = self.PULSE_MIN + (position_percent / 100.0) * (self.PULSE_MAX - self.PULSE_MIN)
        
        pin = self.SERVO_PINS[rod_name]
        self.pi.set_servo_pulsewidth(pin, int(pulse_width))
        self.current_positions[rod_name] = position_percent
    
    def smooth_move(self, rod_name, target_percent, step=1, delay=0.02):
        """Smooth movement dengan interpolasi"""
        current = self.current_positions[rod_name]
        
        while abs(current - target_percent) > 0.5:
            if current < target_percent:
                current = min(current + step, target_percent)
            else:
                current = max(current - step, target_percent)
            
            self.set_position(rod_name, current)
            time.sleep(delay)
    
    def stop_all(self):
        """Release all servos"""
        for pin in self.SERVO_PINS.values():
            self.pi.set_servo_pulsewidth(pin, 0)
```

### Motor Controller

```python
class MotorController:
    """Control 4 DC motors via VNH2SP30 menggunakan pigpio PWM"""
    
    MOTOR_PINS = {
        'pump_primary': 17,
        'pump_secondary': 20,
        'pump_tertiary': 21,
        'turbine': 26
    }
    
    PWM_FREQUENCY = 5000  # 5kHz
    
    def __init__(self, pi):
        self.pi = pi
        
        # Initialize PWM untuk semua motor
        for pin in self.MOTOR_PINS.values():
            pi.set_PWM_frequency(pin, self.PWM_FREQUENCY)
            pi.set_PWM_dutycycle(pin, 0)
    
    def set_speed(self, motor_name, speed_percent):
        """Set motor speed (0-100%)"""
        speed_percent = max(0, min(100, speed_percent))
        duty_cycle = int(speed_percent * 2.55)  # Convert to 0-255
        
        pin = self.MOTOR_PINS[motor_name]
        self.pi.set_PWM_dutycycle(pin, duty_cycle)
    
    def stop_all(self):
        """Stop all motors"""
        for pin in self.MOTOR_PINS.values():
            self.pi.set_PWM_dutycycle(pin, 0)
```

### Relay Controller

```python
import RPi.GPIO as GPIO

class RelayController:
    """Control 4 relays untuk Cooling Tower humidifier"""
    
    RELAY_PINS = {
        'CT1': 6,
        'CT2': 7,
        'CT3': 8,
        'CT4': 25
    }
    
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        for pin in self.RELAY_PINS.values():
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
    
    def set_relay(self, relay_name, state):
        """Set relay ON/OFF"""
        pin = self.RELAY_PINS[relay_name]
        GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
    
    def cleanup(self):
        """Release GPIO"""
        for pin in self.RELAY_PINS.values():
            GPIO.output(pin, GPIO.LOW)
```

### LED Strip Controller

```python
from rpi_ws281x import PixelStrip, Color
import threading

class LEDStripController:
    """Control 3 WS2812 LED strips untuk flow visualization"""
    
    STRIP_CONFIG = {
        'primary': {'pin': 18, 'count': 30},    # Sesuaikan count
        'secondary': {'pin': 19, 'count': 30},
        'tertiary': {'pin': 10, 'count': 30}
    }
    
    LED_FREQ_HZ = 800000
    LED_DMA = 10
    LED_BRIGHTNESS = 255
    
    def __init__(self):
        self.strips = {}
        for name, config in self.STRIP_CONFIG.items():
            strip = PixelStrip(
                config['count'], config['pin'],
                self.LED_FREQ_HZ, self.LED_DMA,
                False, self.LED_BRIGHTNESS
            )
            strip.begin()
            self.strips[name] = strip
        
        self.animation_running = {}
        self.animation_threads = {}
    
    def flow_animation(self, strip_name, color, speed, pump_status):
        """Animate flow berdasarkan pump status"""
        strip = self.strips[strip_name]
        
        if pump_status == 0:  # OFF
            self.clear_strip(strip_name)
            return
        
        # Animation speed berdasarkan pump status
        # 1=STARTING (slow), 2=ON (fast), 3=SHUTTING_DOWN (very slow)
        speed_map = {1: 0.1, 2: 0.03, 3: 0.2}
        delay = speed_map.get(pump_status, 0.05)
        
        # Chase animation
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, color)
            if i > 0:
                strip.setPixelColor(i - 2, Color(0, 0, 0))
            strip.show()
            time.sleep(delay)
    
    def clear_strip(self, strip_name):
        """Turn off all LEDs on strip"""
        strip = self.strips[strip_name]
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()
```

---

## 📝 Task Breakdown

### Phase 1: Setup & Infrastructure
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| AC-001 | pkm-simulator-PLTN-byi | Install pigpio daemon | Setup pigpio service di RPi |
| AC-002 | pkm-simulator-PLTN-qxv | Install rpi_ws281x | Install library untuk WS2812 |
| AC-003 | pkm-simulator-PLTN-zai | GPIO Wiring | Wiring semua aktuator ke GPIO RPi |
| AC-004 | pkm-simulator-PLTN-hhe | Power Supply Setup | Setup power untuk motor, LED, relay |

### Phase 2: Individual Actuator Modules
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| AC-010 | pkm-simulator-PLTN-c7c | ServoController | Implement servo control dengan pigpio |
| AC-011 | pkm-simulator-PLTN-0tg | MotorController | Implement motor control untuk VNH2SP30 |
| AC-012 | pkm-simulator-PLTN-e2j | RelayController | Implement relay control untuk CT |
| AC-013 | pkm-simulator-PLTN-u3e | LEDStripController | Implement WS2812 flow animation |
| AC-014 | pkm-simulator-PLTN-tvn | CherenkovController | Implement LED brightness control |

### Phase 3: Integration
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| AC-020 | pkm-simulator-PLTN-r0p | ActuatorManager | Unified manager untuk semua controller |
| AC-021 | pkm-simulator-PLTN-80n | Update Control Logic | Integrasikan ActuatorManager ke control logic |
| AC-022 | pkm-simulator-PLTN-5i2 | Remove ESP-BC Communication | Hapus/disable UART ke ESP-BC |
| AC-023 | pkm-simulator-PLTN-mvd | Remove ESP-E Communication | Hapus/disable UART ke ESP-E |
| AC-024 | pkm-simulator-PLTN-oco | Update Main Panel Entry | Update raspi_main_panel.py |

### Phase 4: Testing
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| AC-030 | pkm-simulator-PLTN-laf | Servo Test | Test semua servo smooth movement |
| AC-031 | pkm-simulator-PLTN-23l | Motor Test | Test semua motor speed control |
| AC-032 | pkm-simulator-PLTN-9pz | LED Strip Test | Test flow animation |
| AC-033 | pkm-simulator-PLTN-82p | Integration Test | Test full system |
| AC-034 | pkm-simulator-PLTN-1yv | SCRAM Test | Test emergency sequence |

### Phase 5: Cleanup
| ID | Beads ID | Task | Deskripsi |
|----|----------|------|-----------|
| AC-040 | pkm-simulator-PLTN-t3m | Remove ESP Code | Archive esp_utama_uart, esp_led_flow |
| AC-041 | pkm-simulator-PLTN-bnu | Update GPIO Mapping | Update GPIO_PIN_MAPPING.md |
| AC-042 | pkm-simulator-PLTN-ce7 | Update AGENT.md | Update dokumentasi arsitektur |
| AC-043 | pkm-simulator-PLTN-mnk | Update Skills | Update .claude/skills

---

## ⚠️ Pertimbangan Teknis

### WS2812 Timing Constraint

WS2812 memerlukan timing presisi. Di RPi, gunakan:
- **GPIO 18** (PWM0) — Recommended untuk strip pertama
- **GPIO 10** (SPI MOSI) — Alternative untuk strip lain
- **GPIO 19** (PWM1) — Alternative

**Note**: Tidak semua GPIO bisa dipakai untuk WS2812. Perlu test compatibility.

### pigpio Daemon

pigpio harus dijalankan sebagai daemon:
```bash
sudo pigpiod
```

Atau auto-start via systemd:
```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

### Power Considerations

| Komponen | Arus | Power Supply |
|----------|------|--------------|
| 3× Servo | ~1A total | 5V 2A |
| 4× Motor (VNH2SP30) | Up to 30A per motor! | 12V/24V sesuai motor |
| WS2812 LED Strip | ~60mA per LED | 5V |
| Relay module | ~150mA total | 5V |

**PENTING**: Jangan supply aktuator dari RPi GPIO! Gunakan power supply terpisah dengan common ground.

---

## 🚧 Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| PWM jitter dari Linux | Servo gerak tidak smooth | pigpio DMA-based PWM |
| WS2812 timing issues | LED tidak nyala/flicker | Gunakan GPIO 18 (PWM), test sebelum deploy |
| CPU overload | Sistem lag | Optimasi di Pengembangan #4 |
| GPIO conflict | Aktuator tidak work | Plan GPIO mapping dengan hati-hati |
| Power issues | Aktuator tidak stabil | Power supply dedicated, common ground |

---

## 📅 Dependency dengan Pengembangan Lain

- **Setelah Pengembangan #1** (Touchscreen): GPIO freed dari buttons
- **Sebelum Pengembangan #4** (CPU Optimization): Establish baseline load

---

*Terakhir diupdate: 2026-03-23*
