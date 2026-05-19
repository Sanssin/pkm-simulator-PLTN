# Pengembangan 1: Migrasi Panel Kontrol ke Touchscreen

> **Status**: 📝 Planning  
> **Prioritas**: High  
> **Dibuat**: 2026-03-23

---

## 📋 Ringkasan

**Tujuan**: Mengganti panel kontrol fisik (17 push button + 9 OLED) dengan 10" HDMI capacitive touchscreen untuk interface yang lebih modern dan mengurangi kompleksitas hardware.

**Perubahan Arsitektur**:
- ❌ **Dihapus**: 17 push button GPIO + 9 OLED I2C displays
- ✅ **Ditambah**: 1× 10" HDMI touchscreen (1280x800) dengan USB HID input

## 🔧 Spesifikasi Hardware

| Item | Spesifikasi |
|------|-------------|
| Display | 10" HDMI Capacitive Touchscreen |
| Resolusi | 1280×800 pixel |
| Koneksi Display | HDMI0 |
| Koneksi Touch Input | USB (HID device, auto-detected oleh Linux) |
| Total Display | 2 (Touchscreen panel + Monitor video edukasi) |

## 🎯 Keputusan Teknis

### ✅ Framework UI: PyQt5

**Alasan pemilihan**:
- Widget bawaan cocok untuk industrial control panel style
- Touch handling built-in (tap = mouse click)
- Hold button mudah dengan QTimer
- Customizable via QSS (mirip CSS)
- Good performance di Raspberry Pi 4
- Native touchscreen support di Linux

**Alternatif yang dipertimbangkan**:
| Framework | Kelebihan | Kekurangan | Keputusan |
|-----------|-----------|------------|-----------|
| Pygame | Tim familiar, konsisten dengan video_display | Build semua dari scratch | ❌ |
| Kivy | Khusus multi-touch | Performa variabel di RPi | ❌ |
| Electron | Mudah dari Figma | Memory overhead, IPC kompleks | ❌ |

**Keputusan TS-002**: PyQt5 dipilih sebagai framework utama untuk touchscreen panel.

### ✅ Arsitektur: 3-Process

**Alasan pemilihan**:
- Clean separation of concerns
- Existing video_display tidak perlu diubah
- Restart satu proses tidak crash yang lain
- IPC via JSON file sudah proven (dipakai video_display)

**Trade-off**: Latency ~10-20ms (acceptable untuk kontrol manusia)

### ✅ Multi-Display Setup

- **HDMI0**: Touchscreen panel (PyQt5) - 1280×800
- **HDMI1**: Monitor video edukasi (Pygame existing) - 1920×1080

### ✅ Touch Input Handling

| Behavior | Implementation |
|----------|---------------|
| Tap (pump, start, reset, emergency) | `clicked.connect()` - built-in |
| Hold (rod, pressure) | QTimer dengan interval 50ms |
| Visual feedback | QSS `:pressed` state |

### ✅ Buzzer Alarm

**Keputusan**: Tetap menggunakan GPIO 22 (buzzer fisik) karena touchscreen tidak memiliki speaker internal. Mungkin migrasi ke speaker eksternal di masa depan.

## 📐 Arsitektur Sistem Baru

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Raspberry Pi 4                                │
├─────────────────────────────────────────────────────────────────────┤
│  Process 1: touch_panel.py (NEW)                                    │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ PyQt5 Application - HDMI0 (10" touchscreen 1280x800)           │ │
│  │ ├─ Touch Input Handler (Qt events → mouse events)              │ │
│  │ │   - Tap buttons: PUMP ON/OFF, START, RESET, EMERGENCY        │ │
│  │ │   - Hold buttons: ROD UP/DOWN, PRESSURE UP/DOWN (QTimer)     │ │
│  │ ├─ UI Displays (pengganti 9 OLED)                              │ │
│  │ │   - Pressurizer (bar), 3× Pump status, 3× Rod position       │ │
│  │ │   - Thermal Power (kW), System Status                        │ │
│  │ ├─ Write: /tmp/pltn_input.json (touch events ke controller)    │ │
│  │ └─ Read: /tmp/pltn_state.json (state untuk update display)     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│                    JSON IPC  │ (/tmp/pltn_*.json)                   │
│                              ▼                                       │
│  Process 2: raspi_main_panel.py (MODIFIED)                          │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Control Logic (headless - no display)                          │ │
│  │ ├─ InputReader Thread: Read /tmp/pltn_input.json               │ │
│  │ │   (replaces ButtonPolling + ButtonHold threads)              │ │
│  │ ├─ EventProcessor (existing)                                    │ │
│  │ ├─ ControlLogic (existing)                                      │ │
│  │ ├─ ESP_UART_Comm → ESP-BC + ESP-E                              │ │
│  │ ├─ Buzzer Alarm (GPIO 22 - tetap dipertahankan)                │ │
│  │ └─ StateExport: Write /tmp/pltn_state.json                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│                    JSON IPC  │                                       │
│                              ▼                                       │
│  Process 3: video_display_app.py (EXISTING - unchanged)            │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Pygame Application - HDMI1 (monitor video edukasi)             │ │
│  │ ├─ Read: /tmp/pltn_state.json                                   │ │
│  │ ├─ Video player (mpv)                                           │ │
│  │ └─ Speedometer gauge                                            │ │
│  └────────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│  UART Communication (unchanged)                                      │
│  ├─ UART0 (GPIO 14/15) → ESP-BC (servo, motor, relay, cherenkov)   │
│  └─ UART3 (GPIO 4/5) → ESP-E (LED flow, power indicators)          │
└─────────────────────────────────────────────────────────────────────┘
```

## 🔌 IPC File Format

### `/tmp/pltn_input.json` (Touch Panel → Controller)

```json
{
  "timestamp": 1234567890.123,
  "events": [
    {"type": "PUMP_ON", "target": "PRIMARY"},
    {"type": "PUMP_OFF", "target": "SECONDARY"},
    {"type": "ROD_MOVE", "rod": "SAFETY", "direction": "UP"},
    {"type": "PRESSURE", "direction": "DOWN"},
    {"type": "START_AUTO"},
    {"type": "RESET"},
    {"type": "EMERGENCY"},
    {"type": "LOFA_SIMULATE", "target": "PRIMARY"},
    {"type": "LOFA_CANCEL"}
  ]
}
```

### `/tmp/pltn_state.json` (Controller → Displays)

Format extended untuk LOFA support:
```json
{
  "timestamp": 1234567890.456,
  "pressure": 155.5,
  "rod_safety": 100,
  "rod_shim": 75,
  "rod_regulating": 60,
  "pump_primary": 2,
  "pump_secondary": 2,
  "pump_tertiary": 2,
  "thermal_kw": 450000,
  "turbine_speed": 85,
  "emergency_active": false,
  
  "coolant_temp_primary": 295.5,
  "coolant_temp_secondary": 252.0,
  "fuel_cladding_temp": 420.0,
  "condenser_pressure": 0.05,
  "lofa_primary": false,
  "lofa_secondary": false,
  "lofa_tertiary": false,
  "pressurizer_relief_open": false,
  "pressurizer_spray_active": false
}
```

## 🛠️ Detail Implementasi

### PyQt5 Touch Handling

**Tap Buttons** (Pump, Start, Reset, Emergency):
```python
# Touch tap = mouse click, handled automatically oleh Qt
button = QPushButton("PUMP ON")
button.clicked.connect(self.on_pump_on)
```

**Hold Buttons** (Rod, Pressure) dengan QTimer:
```python
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QPushButton

class HoldButton(QPushButton):
    """Button yang trigger terus selama ditahan"""
    
    def __init__(self, label, callback, hold_interval=50):
        super().__init__(label)
        self.callback = callback
        
        # Timer untuk continuous trigger
        self.hold_timer = QTimer()
        self.hold_timer.setInterval(hold_interval)  # 50ms = 20 Hz
        self.hold_timer.timeout.connect(self.callback)
        
        # Connect press/release
        self.pressed.connect(self._start_hold)
        self.released.connect(self._stop_hold)
    
    def _start_hold(self):
        self.callback()  # Trigger pertama
        self.hold_timer.start()
    
    def _stop_hold(self):
        self.hold_timer.stop()

# Penggunaan:
rod_up_btn = HoldButton("ROD ▲", lambda: self.move_rod("safety", +1))
pressure_down_btn = HoldButton("PRESS ▼", lambda: self.change_pressure(-1))
```

**Styling dengan QSS** (mirip CSS):
```python
button.setStyleSheet("""
    QPushButton {
        background-color: #2E7D32;  /* Hijau */
        color: white;
        border: 3px solid #1B5E20;
        border-radius: 8px;
        font-size: 18px;
        font-weight: bold;
        min-width: 120px;
        min-height: 60px;
    }
    QPushButton:pressed {
        background-color: #1B5E20;  /* Lebih gelap saat ditekan */
    }
    QPushButton:disabled {
        background-color: #757575;
    }
""")
```

### Multi-Display Configuration

Edit `/boot/config.txt` di Raspberry Pi:
```bash
# Enable dual HDMI
# HDMI0 - Touchscreen 1280x800
hdmi_group:0=2
hdmi_mode:0=87
hdmi_cvt:0=1280 800 60

# HDMI1 - Video Display (sesuaikan dengan monitor)
hdmi_group:1=2
hdmi_mode:1=82  # 1920x1080 @ 60Hz
```

### Touch Calibration

Jika touch tidak akurat setelah setup:
```bash
# Install calibrator
sudo apt install xinput-calibrator

# Jalankan kalibrasi
xinput_calibrator

# Ikuti instruksi tap 4 titik di layar
# Output config akan ditampilkan, simpan ke /etc/X11/xorg.conf.d/
```

### Menjalankan App di Display Tertentu

```python
from PyQt5.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
screens = app.screens()

# screens[0] = HDMI0 (touchscreen)
# screens[1] = HDMI1 (video display)

window = TouchPanelWindow()
window.setScreen(screens[0])  # Touchscreen
window.showFullScreen()
```

## 📋 GPIO yang Dibebaskan

Setelah migrasi touchscreen:

```
FREED (17 pin dari buttons):
GPIO 6, 7, 8, 11, 12, 13, 16, 17, 18, 19, 20, 21, 23, 24, 25, 26, 27

FREED (I2C untuk OLED):
GPIO 2, 3 - I2C Bus 1 (jika tidak ada device lain)

STILL USED:
GPIO 4, 5   - UART3 → ESP-E
GPIO 14, 15 - UART0 → ESP-BC  
GPIO 22     - Buzzer PWM
```

## 🚧 Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| Touchscreen latency tinggi | UX buruk, kontrol tidak responsif | Test hardware sebelum development |
| Touch & hold tidak presisi | Rod/pressure control sulit | Implement visual feedback saat hold |
| USB HID tidak terdeteksi | Panel tidak bisa dioperasikan | Test compatibility, siapkan driver |
| Performa rendering | Lag di RPi4 | Optimize rendering, gunakan hardware acceleration |
| Multi-display config | Display tidak terdeteksi | Test config sebelum development |

## 📝 Task Breakdown

### Phase 1: Persiapan & Prototyping
| ID | Task | Status |
|----|------|--------|
| TS-001 | Hardware Setup Touchscreen 10" | Ready |
| TS-002 | Framework Decision (PyQt5 ✅) | Ready |
| TS-003 | Input Handler Prototype USB HID | Prototype ready |
| TS-004 | UI Mockup Review dari Figma | Ready |

### Phase 2: Core Touch Panel App
| ID | Task | Status | Notes |
|----|------|--------|-------|
| TS-010 | Touch Panel Base App | Blocked | |
| TS-011 | Virtual Button Components (18 tombol) | Blocked | +1 tombol SIMULASI LOFA |
| TS-012 | Status Display Components | Blocked | +temperature displays untuk LOFA |
| TS-013 | UI Layout Implementation | Blocked | +LOFA area |

### Phase 3: Integrasi dengan Core System
| ID | Task | Status | Notes |
|----|------|--------|-------|
| TS-020 | Event Queue Integration | Blocked | +LOFA event types |
| TS-021 | State Binding ke UI | Blocked | |
| TS-022 | Remove GPIO Button Code | Blocked | |
| TS-023 | Remove OLED Code | Blocked | |
| TS-024 | Update Main Panel Architecture | Blocked | |

### Phase 4: Testing & Refinement
| ID | Task | Status |
|----|------|--------|
| TS-030 | Touch Responsiveness Test | Blocked |
| TS-031 | Hold Button Test | Blocked |
| TS-032 | Integration Test ESP-BC dan ESP-E | Blocked |
| TS-033 | Emergency SCRAM Test | Blocked |

### Phase 5: Cleanup & Documentation
| ID | Task | Status |
|----|------|--------|
| TS-040 | Code Cleanup | Blocked |
| TS-041 | Update Documentation | Blocked |
| TS-042 | Update Skills Files | Blocked |

**Lihat beads untuk detail dan dependency**: `bd list`

### Evaluasi TS-001

Setelah hardware touchscreen siap, jalankan evaluasi berikut untuk memastikan environment dasar tidak error:

```bash
python touch_panel/touch_panel_app.py --check-hardware
```

Jika later UI stack sudah siap, file ini akan jadi entrypoint utama untuk app touchscreen.

## 📅 Urutan Pengerjaan

1. **TS-001** → Hardware Setup (blocking untuk hampir semua task)
2. **TS-004** → UI Mockup Review (bisa parallel dengan TS-001)
3. **TS-002** → Framework Decision (setelah hardware ready)
4. **TS-003** → Input Handler Prototype
5. **Phase 2** → Core Touch Panel App
6. **Phase 3** → Integrasi dengan sistem existing
7. **Phase 4** → Testing
8. **Phase 5** → Cleanup & Dokumentasi

---

## Catatan Tambahan

### Dependencies Baru

```bash
# PyQt5 untuk touch panel
pip3 install PyQt5

# Optional: untuk gauge/graph
pip3 install pyqtgraph
```

### File Baru yang Akan Dibuat

```
raspi_central_control/
├─ touch_panel/              # NEW - folder untuk touch panel app
│  ├─ __init__.py
│  ├─ touch_panel_app.py     # Main PyQt5 application
│  ├─ input_handler.py       # TS-003 touch input prototype
│  ├─ components/
│  │  ├─ buttons.py          # TapButton, HoldButton classes
│  │  ├─ displays.py         # StatusDisplay, PressureGauge, etc.
│  │  └─ styles.py           # QSS styling
│  └─ ipc/
│     ├─ input_writer.py     # Write touch events to JSON
│     └─ state_reader.py     # Read state from JSON
```

### File yang Akan Dimodifikasi

- `raspi_main_panel.py` — Tambah InputReader, hapus ButtonPolling/ButtonHold/OLED threads
- `raspi_config.py` — Hapus button pin definitions (atau mark deprecated)

### File yang Akan Dihapus/Deprecated

- `raspi_gpio_buttons.py` — Tidak lagi digunakan
- `raspi_oled_manager.py` — Tidak lagi digunakan
- `raspi_tca9548a.py` — Tidak lagi digunakan (kecuali ada I2C device lain)

---

*Terakhir diupdate: 2026-03-23*
