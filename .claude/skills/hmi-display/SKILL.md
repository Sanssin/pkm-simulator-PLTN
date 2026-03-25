---
name: HMI & Display Interface
description: UI updates, display management, visual/audio feedback
---

# Skill: HMI & Display Interface

## Komponen Display yang Digunakan

Sistem ini memiliki **3 jenis HMI**:

| Komponen | Jumlah | Teknologi | Library | File Kode |
|----------|--------|-----------|---------|-----------|
| OLED SSD1306 | 9 unit | 128×32 px, I2C | `adafruit_ssd1306`, `Pillow` | `raspi_oled_manager.py` |
| Video Display | 1 unit | Monitor HDMI, 4K | `pygame`, `mpv` (subprocess) | `video_display_app.py`, `speedometer_temp.py` |
| Buzzer Alarm | 1 unit | Passive buzzer, PWM | `RPi.GPIO` (software PWM) | `raspi_buzzer_alarm.py` |

**Tidak ada touchscreen** — semua input via 17 push buttons fisik (GPIO).

---

## Arsitektur UI & Refresh Pattern

### OLED System (9 displays)

```
                 I2C Bus (SDA=GPIO 2, SCL=GPIO 3)
                           │
              ┌────────────┴────────────┐
              │                         │
        TCA9548A #1 (0x70)        TCA9548A #2 (0x71)
        ├─ Ch1: Pressurizer       ├─ Ch1: Thermal Power
        ├─ Ch2: Pump Primary      └─ Ch2: System Status
        ├─ Ch3: Pump Secondary
        ├─ Ch4: Pump Tertiary
        ├─ Ch5: Safety Rod
        ├─ Ch6: Shim Rod
        └─ Ch7: Regulating Rod
```

**Refresh rate**: Thread `OLEDUpdate` berjalan setiap **200ms** (5 Hz) di mode normal, bisa turun ke **100ms** (10 Hz) saat interpolasi aktif.

**Optimasi I2C**: Skip update jika value belum berubah sejak last render — mengurangi traffic I2C.

### Video Display System

```
raspi_main_panel.py                     video_display_app.py
StateExport thread (100ms)              Main pygame loop (10 Hz)
      │                                       │
      ├─ Atomic write:                        ├─ Read JSON
      │  temp file → rename                   ├─ Hash compare
      │  /tmp/pltn_state.json                 ├─ Update gauges
      │                                       └─ Render frame
      └─ JSON contains ALL state vars
```

**Inter-process communication**: JSON file di `/tmp/pltn_state.json`, ditulis atomic (write to temp → os.rename). Ini menghindari partial read.

---

## Layout Layar OLED

Setiap OLED berukuran **128×32 pixel**, ditampilkan dengan font monospace via Pillow.

### Pressurizer Display
```
┌────────────────────────┐
│  PRESS: 155.0 bar      │
│  ████████████████░░░░   │  ← Progress bar 0-200 bar
└────────────────────────┘
```
- Update: `update_pressurizer_display(pressure: float)`
- Range: 0.0 – 200.0 bar
- Progress bar proportional

### Pump Display (×3: Primary, Secondary, Tertiary)
```
┌────────────────────────┐
│  PUMP PRI: ON          │  ← Status text: OFF/STARTING/ON/SHUTDOWN
│  ████████████████████   │  ← Bar penuh saat ON
└────────────────────────┘
```
- Update: `update_pump_display(pump_name, status_int, speed_pct)`
- Status mapping: 0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN
- Speed ditampilkan sebagai progress bar (0-100%)

### Rod Display (×3: Safety, Shim, Regulating)
```
┌────────────────────────┐
│  SAFETY: 100%          │  ← Posisi rod 0-100%
│  ████████████████████   │  ← Bar penuh = fully withdrawn
└────────────────────────┘
```
- Update: `update_rod_display(rod_name, position_pct)`
- 0% = fully inserted (subcritical), 100% = fully withdrawn (critical)

### Thermal Power Display
```
┌────────────────────────┐
│  THERMAL: 450 MWth     │
│  ██████████░░░░░░░░░░   │  ← Progress bar 0-900 MWth
└────────────────────────┘
```
- Update: `update_thermal_display(thermal_kw)`
- Conversion: kW → MWth (÷1000) untuk display

### System Status Display
```
┌────────────────────────┐
│  MODE: MANUAL          │  ← MANUAL / AUTO
│  INTERLOCK: OK / FAIL  │  ← Status interlock
└────────────────────────┘
```

---

## DisplayValueInterpolator — Smooth OLED Transitions

```python
# raspi_oled_manager.py — DisplayValueInterpolator class
class DisplayValueInterpolator:
    def __init__(self, speed=50.0):
        self.display_value = 0.0     # Current rendered value
        self.target_value = 0.0      # Target from state
        self.speed = speed           # Units per second (default 50)

    def set_target(self, new_target):
        self.target_value = new_target

    def update(self, dt):
        # Move display_value toward target at constant speed
        diff = self.target_value - self.display_value
        max_change = self.speed * dt

        if abs(diff) <= max_change:
            self.display_value = self.target_value
        elif diff > 0:
            self.display_value += max_change
        else:
            self.display_value -= max_change

        return self.display_value
```

**Karakteristik**:
- Speed: 50 units/second (pressure: 50 bar/s, rod: 50%/s)
- Linear movement, NOT exponential ease
- dt dihitung dari `time.time()` delta antar frame
- Mencegah display "jump" yang membingungkan operator

---

## Non-Blocking Update Pattern

### OLED Update Thread

```python
# raspi_main_panel.py — oled_update_thread(), line 1358-1389
def oled_update_thread(self):
    interval = 0.2  # 200ms base interval

    while self.running:
        start = time.time()

        with self.state_lock:
            # Copy state values (fast, under lock)
            pressure = self.state.pressure
            pump_pri = self.state.pump_primary_status
            # ... (semua state di-copy)

        # Render di LUAR lock (slow I2C operations)
        if self.oled_manager:
            try:
                self.oled_manager.update_all_displays(
                    pressure, pump_pri, pump_sec, pump_ter,
                    safety, shim, reg, thermal_kw,
                    interlock, emergency, mode
                )
            except Exception as e:
                logger.error(f"OLED update error: {e}")

        elapsed = time.time() - start
        sleep_time = max(0, interval - elapsed)
        time.sleep(sleep_time)
```

**Pattern kunci**:
1. Lock state hanya untuk **copy values** (microseconds)
2. Render OLED di **luar lock** (I2C write bisa 5-10ms per display)
3. Self-adjusting sleep: compensate untuk render time
4. Try/except: I2C error tidak crash thread

### Video Display State Export

```python
# raspi_main_panel.py — state_export_thread(), interval 100ms
def state_export_thread(self):
    while self.running:
        with self.state_lock:
            state_dict = self.state.to_dict()

        # Atomic write: temp file → rename (prevents partial reads)
        temp_path = '/tmp/pltn_state.json.tmp'
        final_path = '/tmp/pltn_state.json'

        with open(temp_path, 'w') as f:
            json.dump(state_dict, f)
        os.rename(temp_path, final_path)

        time.sleep(0.1)
```

---

## Alarm Visual & Audio

### Buzzer PWM System

```python
# raspi_buzzer_alarm.py — Software PWM
class BuzzerAlarm:
    BUZZER_PIN = 22  # GPIO 22

    def __init__(self):
        GPIO.setup(self.BUZZER_PIN, GPIO.OUT)
        self.pwm = GPIO.PWM(self.BUZZER_PIN, 440)  # Initial 440 Hz

    def _play_tone(self, frequency, duration):
        self.pwm.ChangeFrequency(frequency)
        self.pwm.start(50)   # 50% duty cycle
        time.sleep(duration)
        self.pwm.stop()
```

### Alarm Sound Patterns (from code)

```python
# raspi_buzzer_alarm.py line 46-71
ALARM_TONES = {
    ALARM_PROCEDURE_WARNING: {
        'frequency': 2000,
        'pattern': [0.3, 0.3]           # 0.3s on, 0.3s off, repeat
    },
    ALARM_PRESSURE_WARNING: {
        'frequency': 2500,
        'pattern': [0.5, 0.5]           # 0.5s on, 0.5s off, repeat
    },
    ALARM_PRESSURE_CRITICAL: {
        'frequency': 3000,
        'pattern': [0.2, 0.2, 0.2, 0.6]  # double beep, pause, repeat
    },
    ALARM_EMERGENCY: {
        'frequency': 4000,
        'pattern': [0.1, 0.1]           # rapid beep
    },
    ALARM_INTERLOCK: {
        'frequency': 1500,
        'pattern': [0.2, 0.8]           # short beep, long pause
    }
}
```

### Alarm Thread Architecture

```python
# raspi_buzzer_alarm.py — _alarm_loop(), line 119-166
def _alarm_loop(self):
    """Background thread yang terus play pattern selama alarm aktif."""
    while self.running:
        if self.current_alarm == self.ALARM_NONE:
            time.sleep(0.05)
            continue

        tone = self.ALARM_TONES.get(self.current_alarm)
        if not tone:
            continue

        pattern = tone['pattern']
        freq = tone['frequency']

        # Play pattern: alternating on/off durations
        for i, duration in enumerate(pattern):
            if self.current_alarm == self.ALARM_NONE:
                break
            if i % 2 == 0:  # Even index = sound ON
                self._play_tone(freq, duration)
            else:            # Odd index = silence
                time.sleep(duration)
```

**Non-blocking**: Alarm loop berjalan di daemon thread terpisah. `set_alarm()` dan `clear_alarm()` hanya mengubah `current_alarm` variable — loop thread yang menangani playback.

---

## User Input Handling

### Physical Buttons (Production)

```python
# raspi_gpio_buttons.py — ButtonPin enum
class ButtonPin(IntEnum):
    PUMP_PRIM_ON   = 11    # Edge detection (rising)
    PUMP_PRIM_OFF  = 9     # Edge detection (rising)
    PUMP_SEC_ON    = 25    # Edge detection (rising)
    PUMP_SEC_OFF   = 8     # Edge detection (rising)
    PUMP_TER_ON    = 7     # Edge detection (rising)
    PUMP_TER_OFF   = 5     # Edge detection (rising) [*migrated to UART3]

    SAFETY_ROD_UP  = 6     # Level detection (continuous while held)
    SAFETY_ROD_DN  = 12    # Level detection
    SHIM_ROD_UP    = 13    # Level detection
    SHIM_ROD_DN    = 16    # Level detection
    REGUL_ROD_UP   = 19    # Level detection
    REGUL_ROD_DN   = 20    # Level detection

    PRESSURE_UP    = 24    # Level detection
    PRESSURE_DN    = 21    # Level detection

    START_AUTO     = 26    # Edge detection
    RESET          = 27    # Edge detection
    EMERGENCY      = 18    # Edge detection (SCRAM button)
```

**Two detection modes**:
- **Edge detection** (tombol tekan sekali): Pump ON/OFF, START, RESET, EMERGENCY
- **Level detection** (tombol tahan): Rod UP/DOWN, Pressure UP/DOWN — continuous action selama ditahan

### Edge vs Level Implementation

```python
# raspi_gpio_buttons.py — check_all_buttons()
EDGE_BUTTONS = [
    (ButtonPin.PUMP_PRIM_ON, ButtonEvent.PUMP_PRIMARY_ON),
    # ... etc
]
LEVEL_BUTTONS = [
    (ButtonPin.SAFETY_ROD_UP, ButtonEvent.SAFETY_ROD_UP),
    # ... etc
]

def check_all_buttons(self):
    events = []

    # Edge: detect state CHANGE (0→1 transition only)
    for pin, event in EDGE_BUTTONS:
        current = GPIO.input(pin)
        if current == 1 and self.prev_state[pin] == 0:
            events.append(event)
        self.prev_state[pin] = current

    # Level: fire event AS LONG AS button is pressed
    # (handled by ButtonHold thread at 50ms interval)
    for pin, event in LEVEL_BUTTONS:
        if GPIO.input(pin) == 1:
            events.append(event)

    return events
```

### Keyboard Simulation (Development)

```python
# video_display_app.py — KEYBOARD_MAPPING, line 40-71
KEYBOARD_MAPPING = {
    pygame.K_q: ButtonEvent.PUMP_PRIMARY_ON,
    pygame.K_a: ButtonEvent.PUMP_PRIMARY_OFF,
    pygame.K_w: ButtonEvent.PUMP_SECONDARY_ON,
    pygame.K_s: ButtonEvent.PUMP_SECONDARY_OFF,
    pygame.K_e: ButtonEvent.PUMP_TERTIARY_ON,
    pygame.K_d: ButtonEvent.PUMP_TERTIARY_OFF,
    pygame.K_r: ButtonEvent.SAFETY_ROD_UP,
    pygame.K_f: ButtonEvent.SAFETY_ROD_DOWN,
    pygame.K_t: ButtonEvent.SHIM_ROD_UP,
    pygame.K_g: ButtonEvent.SHIM_ROD_DOWN,
    pygame.K_y: ButtonEvent.REGULATING_ROD_UP,
    pygame.K_h: ButtonEvent.REGULATING_ROD_DOWN,
    pygame.K_u: ButtonEvent.PRESSURE_UP,
    pygame.K_j: ButtonEvent.PRESSURE_DOWN,
    pygame.K_SPACE: ButtonEvent.START_AUTO,
    pygame.K_BACKSPACE: ButtonEvent.REACTOR_RESET,
    pygame.K_ESCAPE: ButtonEvent.EMERGENCY,
}
```

---

## Pengembangan HMI Tambahan

### 1. Speedometer Gauge (commit `6241898`)
- **File**: `speedometer_temp.py` (114 lines)
- **Fungsi**: Arc gauge visualization untuk daya output di video display
- **Rendering**: Pygame drawing (arc, lines, text) — tidak menggunakan gambar bitmap
- **Range**: 0 – 300 MWe
- **Color**: Gradient hijau→kuning→merah sesuai power level

### 2. UI Redesign Indikator (commits `6ac9766`, `36e58e3`)
- **Branch**: `doel`
- **Perubahan**: Redesign layout indikator + penambahan indikator baru
- **File**: `video_display_app.py` — perubahan di rendering methods

### 3. HDMI Audio Integration
- **File**: `AUDIO_HDMI_SETUP.md`, `video_display_app.py`
- **Fungsi**: Audio output via ALSA → HDMI untuk video edukasi
- **Config**: `plughw:1,0` (HDMI audio device)
- **Usage**: mpv subprocess menggunakan `--ao=alsa --audio-device=alsa/plughw:1,0`

### 4. 4K Scaling Support
- **File**: `video_display_app.py`
- **Fungsi**: Automatic scaling dari base 1920×1080 ke resolusi monitor aktual
- **Implementation**: `scale_factor = screen_width / 1920`
- **Semua koordinat dan font** dikalikan scale_factor

### 5. Color Palette — Nuclear Blue Theme
```python
# video_display_app.py — color constants
COLORS = {
    'bg_dark':      (28, 35, 48),    # #1C2330 dark navy
    'bg_panel':     (35, 44, 58),    # panel background
    'accent_blue':  (0, 150, 255),   # nuclear blue
    'accent_green': (0, 200, 100),   # status OK
    'accent_red':   (255, 60, 60),   # alarm/warning
    'text_primary': (220, 225, 230), # main text
    'text_dim':     (120, 130, 140), # secondary text
}
```

---

## Cara Menambah Elemen Display Baru

### Menambah Display OLED Baru

1. **Hardware**: Sambung OLED ke channel TCA9548A yang tersedia (max 8 per MUX)

2. **Konfigurasi** di `raspi_config.py`:
```python
OLED_NEW_DISPLAY = {
    'mux_address': 0x71,   # TCA9548A address
    'channel': 3,           # Channel number (0-7)
    'address': 0x3C,        # OLED I2C address (biasanya 0x3C)
}
```

3. **Buat render method** di `raspi_oled_manager.py`:
```python
def update_new_display(self, value):
    display = self.displays.get('new_display')
    if not display:
        return

    display.clear()
    display.draw_text(0, 0, f"NEW: {value}")
    display.draw_progress_bar(0, 20, 128, 12, value, max_value=100)
    display.show()
```

4. **Register di `init_all_displays()`**:
```python
self.displays['new_display'] = OLEDDisplay(
    mux=self.mux1, channel=3,
    oled_address=0x3C
)
```

5. **Panggil dari `update_all_displays()`** — tambah parameter dan panggil render method

6. **Tambah interpolator** jika transisi smooth diperlukan:
```python
self.interpolators['new_display'] = DisplayValueInterpolator(speed=50.0)
```

### Menambah Elemen di Video Display

1. **Buat komponen baru** di file terpisah (ikuti pola `speedometer_temp.py`):
```python
class NewGauge:
    def __init__(self, x, y, width, height, scale_factor=1.0):
        self.rect = pygame.Rect(x, y, width, height)
        self.scale = scale_factor

    def draw(self, surface, value):
        # Render logic here
        pass
```

2. **Import dan instantiate** di `video_display_app.py`:
```python
from new_gauge import NewGauge
self.new_gauge = NewGauge(x=100, y=200, width=300, height=200,
                           scale_factor=self.scale_factor)
```

3. **Panggil draw** di render method yang sesuai (misalnya di mode MANUAL_GUIDE)

4. **Perhatikan 4K scaling** — semua koordinat harus dikalikan `self.scale_factor`

### Menambah Alarm Baru

1. **Definisikan konstanta** di `raspi_buzzer_alarm.py`:
```python
ALARM_NEW_TYPE = 6  # Next available number

ALARM_TONES[ALARM_NEW_TYPE] = {
    'frequency': 1800,          # Hz
    'pattern': [0.4, 0.4]      # on/off pattern in seconds
}
```

2. **Buat trigger method**:
```python
def sound_new_alarm(self, duration=2.0):
    def _play():
        self.set_alarm(self.ALARM_NEW_TYPE)
        time.sleep(duration)
        self.clear_alarm()
    threading.Thread(target=_play, daemon=True).start()
```

3. **Panggil dari event processing** atau control logic:
```python
if condition_for_new_alarm:
    if self.buzzer:
        self.buzzer.sound_new_alarm(duration=2.0)
```

4. **Tentukan priority** relative di `check_alarms()` jika alarm ini continuous
