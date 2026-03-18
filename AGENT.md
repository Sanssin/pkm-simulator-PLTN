# AGENT.md — pkm-simulator-PLTN

> Baca file ini sebelum melakukan perubahan apapun di repositori ini.

## 1. Project Overview

**pkm-simulator-PLTN** adalah simulator Pembangkit Listrik Tenaga Nuklir (PLTN) tipe **PWR (Pressurized Water Reactor)** yang dikembangkan untuk kompetisi **PKM (Program Kreativitas Mahasiswa) 2024**.

Tujuan proyek:
- **Edukasi**: Memberikan pemahaman realistis tentang pengoperasian reaktor nuklir PWR kepada mahasiswa teknik nuklir
- **Simulasi interaktif**: Panel kontrol fisik dengan tombol, display OLED, buzzer alarm, servo motor (control rod), motor DC (pompa & turbin), dan efek visual (LED Cherenkov, flow animation)
- **Safety training**: Mengajarkan prosedur keselamatan nuklir (SCRAM, interlock, pump sequence) melalui hands-on experience

Sistem berjalan di **Raspberry Pi 4** sebagai master controller yang berkomunikasi dengan **2× ESP32** via **UART Binary Protocol** untuk mengontrol aktuator fisik dan visualisasi.

---

## 2. Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PANEL KONTROL OPERATOR                           │
│   17 Push Buttons (GPIO)              9 OLED Displays (I2C)        │
│   ├─ 6 Pump ON/OFF                    ├─ Pressurizer               │
│   ├─ 6 Rod UP/DOWN                    ├─ 3× Pump status            │
│   ├─ 2 Pressure UP/DOWN               ├─ 3× Rod position           │
│   ├─ 1 START_AUTO (Green)              ├─ Thermal Power             │
│   ├─ 1 RESET (Yellow)                  └─ System Status             │
│   └─ 1 EMERGENCY/SCRAM (Red)                                       │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────────────┐
│              RASPBERRY PI 4 (raspi_central_control/)                │
│                                                                     │
│  raspi_main_panel.py  ← Entry point utama, 9 threads:              │
│  ├─ ButtonPolling (5ms)     ├─ ButtonHold (50ms)                   │
│  ├─ EventProcessor (10ms)   ├─ ControlLogic (50ms)                │
│  ├─ ESP_UART_Comm (50ms)    ├─ OLED_Update (200ms)                │
│  ├─ HealthMonitor (startup) ├─ AutoSimulation                     │
│  └─ StateExport (100ms → /tmp/pltn_state.json)                    │
│                                                                     │
│  raspi_uart_master.py  ← Binary UART protocol (CRC8, ACK/NACK)    │
│  raspi_gpio_buttons.py ← Hybrid edge + level button detection     │
│  raspi_humidifier_control.py ← Staged CT1-4 activation            │
│  raspi_buzzer_alarm.py ← PWM alarm tones (5 alarm types)          │
│  raspi_oled_manager.py ← 9× SSD1306 via TCA9548A, interpolation  │
│  raspi_config.py       ← Konstanta, pin mapping, thresholds       │
│  raspi_i2c_master.py   ← Legacy I2C (tidak digunakan, dead code)  │
│  raspi_tca9548a.py     ← I2C multiplexer driver (OLED only)       │
│  raspi_system_health.py ← 8-point health check saat startup       │
└─────────┬──────────────────────────────┬────────────────────────────┘
          │ UART0 (GPIO 14 TX / 15 RX)  │ UART3 (GPIO 4 TX / 5 RX)
          │ 115200 baud, 8N1             │ 115200 baud, 8N1
          ▼                              ▼
┌─────────────────────────┐  ┌───────────────────────────────┐
│  ESP-BC (esp_utama_uart) │  │  ESP-E (esp_visualizer_uart)  │
│  Control + Actuators     │  │  LED Visualization            │
│                          │  │                               │
│  • 3× Servo (rods)      │  │  • 3× 74HC595 shift register │
│  • 4× L298N motor (3    │  │    → 24 LEDs flow animation  │
│    pumps + 1 turbine)    │  │  • 4× Power indicator LEDs   │
│  • 4× Relay (CT1-4      │  │    (PWM brightness ∝ power)  │
│    humidifiers)          │  │                               │
│  • 1× Cherenkov LED     │  │                               │
│  • Thermal power calc   │  │                               │
│  • Turbine FSM           │  │                               │
└─────────────────────────┘  └───────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│              VIDEO DISPLAY (pltn_video_display/)                    │
│  Monitor terpisah via HDMI                                         │
│                                                                     │
│  video_display_app.py ← Pygame app, 3 mode:                       │
│  ├─ IDLE: Tampilan standby                                         │
│  ├─ AUTO_VIDEO: Putar video edukasi via mpv                        │
│  └─ MANUAL_GUIDE: Panduan interaktif (pygame)                      │
│  Membaca state dari /tmp/pltn_state.json (10 Hz)                   │
│  speedometer_temp.py ← Arc gauge untuk daya output                 │
└─────────────────────────────────────────────────────────────────────┘
```

### Alur Data

1. **Input**: Operator menekan tombol fisik → GPIO interrupt (edge/level)
2. **Processing**: Event masuk Queue → EventProcessor thread memproses logic
3. **Interlock check**: Setiap aksi rod/pump dicek safety interlock terlebih dahulu
4. **UART transmit**: State dikirim ke ESP-BC dan ESP-E via binary protocol
5. **Aktuator**: ESP-BC menggerakkan servo/motor/relay, menghitung thermal power
6. **Feedback**: ESP-BC mengirim balik thermal_kw, turbine_speed, pump speeds
7. **Display**: OLED diupdate 5×/detik, video display membaca JSON 10×/detik

### Protokol Komunikasi UART

```
Frame format: [STX 0x02][CMD][LEN][PAYLOAD...][CRC8][ETX 0x03]

ESP-BC Command (15 bytes):
  CMD = 0x55 (UPDATE)
  Payload = [rod1][rod2][rod3][pump1][pump2][pump3][h1][h2][h3][h4]

ESP-BC Response (28 bytes):
  CMD = 0x06 (ACK)
  Payload = 23 bytes (thermal_kw, turbine, pump speeds, rod actuals, etc.)

ESP-E Command (lebih kecil):
  Payload = thermal_kw (float32) + pump status (3 bytes)

CRC: CRC8-MAXIM polynomial 0x31
```

---

## 3. Struktur Direktori

```
pkm-simulator-PLTN/
├── AGENT.md                        ← File ini
├── AGENTS.md                       ← Instruksi bd (beads) issue tracker
├── README.md                       ← Dokumentasi utama (63 KB, sangat detail)
├── GPIO_PIN_MAPPING.md             ← Referensi alokasi pin GPIO
│
├── raspi_central_control/          ← KODE UTAMA (Raspberry Pi)
│   ├── raspi_main_panel.py         ← Entry point (1992 baris) — PLTNPanelController
│   ├── raspi_config.py             ← Konstanta sistem (⚠️ ada bug pin mapping)
│   ├── raspi_uart_master.py        ← UART binary protocol (1215 baris)
│   ├── raspi_gpio_buttons.py       ← Handler 17 tombol (273 baris)
│   ├── raspi_humidifier_control.py ← Logika humidifier bertahap (389 baris)
│   ├── raspi_buzzer_alarm.py       ← Sistem alarm PWM (337 baris)
│   ├── raspi_oled_manager.py       ← Manager 9 OLED display
│   ├── raspi_i2c_master.py         ← ❌ Legacy I2C (dead code, 417 baris)
│   ├── raspi_tca9548a.py           ← I2C multiplexer (masih dipakai untuk OLED)
│   ├── raspi_system_health.py      ← Health check startup
│   ├── raspi_README.md             ← ⚠️ Outdated (masih deskripsi I2C 5-ESP)
│   ├── requirements.txt            ← (tidak ada — dependensi di README utama)
│   ├── PYGAME_ANIMATION_GUIDE.md   ← Panduan animasi pygame
│   └── AUDIO_HDMI_SETUP.md         ← Setup audio HDMI
│
├── esp_utama_uart/                 ← FIRMWARE ESP-BC (Control + Actuators)
│   └── esp_utama_uart.ino          ← Arduino sketch (778 baris)
│
├── esp_visualizer_uart/            ← FIRMWARE ESP-E (LED Visualizer)
│   └── esp_visualizer_uart.ino     ← Arduino sketch (564 baris)
│
├── tes_visualizer/                 ← DEVELOPMENT TEST ESP-E (DEV_MODE=true)
│   └── tes_visualizer.ino          ← Copy esp_visualizer + simulasi lokal (714 baris)
│
└── pltn_video_display/             ← VIDEO DISPLAY SYSTEM
    ├── video_display_app.py        ← Pygame display app (1447 baris)
    ├── speedometer_temp.py         ← Arc gauge component (114 baris)
    └── requirements.txt            ← pygame==2.5.2
```

---

## 4. Hardware Components

### Sensor Input

Sistem ini **tidak menggunakan sensor fisik** — semua parameter disimulasikan secara software. Input berasal dari tombol operator:

| Input | Parameter | Pin (BCM) | Tipe Deteksi | File Kode |
|-------|-----------|-----------|--------------|-----------|
| 17× Push Button | Kontrol panel operator | Lihat tabel di bawah | Edge + Level | `raspi_gpio_buttons.py` |

**Mapping Tombol (Source of Truth: `raspi_gpio_buttons.py` `ButtonPin` enum)**:

| Tombol | GPIO (BCM) | Deteksi | Fungsi |
|--------|-----------|---------|--------|
| PUMP_PRIMARY_ON | 11 | Edge | Nyalakan pompa primer |
| PUMP_PRIMARY_OFF | 6 | Edge | Matikan pompa primer |
| PUMP_SECONDARY_ON | 13 | Edge | Nyalakan pompa sekunder |
| PUMP_SECONDARY_OFF | 19 | Edge | Matikan pompa sekunder |
| PUMP_TERTIARY_ON | 26 | Edge | Nyalakan pompa tersier |
| PUMP_TERTIARY_OFF | 21 | Edge | Matikan pompa tersier |
| SAFETY_ROD_UP | 20 | Level (hold) | Naikkan rod keselamatan |
| SAFETY_ROD_DOWN | 16 | Level (hold) | Turunkan rod keselamatan |
| SHIM_ROD_UP | 12 | Level (hold) | Naikkan rod shim |
| SHIM_ROD_DOWN | 7 | Level (hold) | Turunkan rod shim |
| REGULATING_ROD_UP | 8 | Level (hold) | Naikkan rod regulasi |
| REGULATING_ROD_DOWN | 25 | Level (hold) | Turunkan rod regulasi |
| PRESSURE_UP | 24 | Level (hold) | Naikkan tekanan pressurizer |
| PRESSURE_DOWN | 23 | Level (hold) | Turunkan tekanan pressurizer |
| START_AUTO_SIMULATION | 17 | Edge | Mulai simulasi otomatis (GREEN) |
| REACTOR_RESET | 27 | Edge | Reset simulasi (YELLOW) |
| EMERGENCY | 18 | Edge | Emergency SCRAM (RED) |

### Aktuator & Output

| Komponen | Fungsi | Pin/Interface | File Kode |
|----------|--------|---------------|-----------|
| 3× Servo Motor (SG90) | Control rod: Safety, Shim, Regulating (0–180°) | ESP-BC GPIO 13, 12, 14 | `esp_utama_uart.ino` |
| 4× Motor DC + L298N | 3 pompa sirkulasi + 1 turbin | ESP-BC GPIO 4, 5, 18, 19 (PWM); GPIO 23, 15 (direction turbin) | `esp_utama_uart.ino` |
| 4× Relay Module | Cooling Tower humidifier CT1-4 | ESP-BC GPIO 27, 26, 25, 32 | `esp_utama_uart.ino` |
| 1× Blue LED (Cherenkov) | Efek visual radiasi Cherenkov | ESP-BC GPIO 33 (PWM) | `esp_utama_uart.ino` |
| 3× 74HC595 Shift Register | 24 LED flow animation (sirkulasi coolant) | ESP-E SPI: SCK=18, MOSI=23, LATCH=5 | `esp_visualizer_uart.ino` |
| 4× Power LED | Brightness ∝ daya output | ESP-E GPIO 25, 26, 27, 32 (PWM) | `esp_visualizer_uart.ino` |
| 1× Passive Buzzer | Alarm tones (5 tipe, software PWM) | RasPi GPIO 22 | `raspi_buzzer_alarm.py` |

### Display & HMI

| Komponen | Fungsi | Interface | File Kode |
|----------|--------|-----------|-----------|
| 9× OLED SSD1306 128×32 | Status real-time (pressure, pumps, rods, power) | I2C via TCA9548A 0x70, channel 0-7 | `raspi_oled_manager.py` |
| 1× Monitor HDMI | Video edukasi + panduan operasi | HDMI + ALSA plughw:1,0 | `video_display_app.py` |

OLED channel assignment:
- Ch 0: Pressurizer (bar)
- Ch 1: Pump Primary status
- Ch 2: Pump Secondary status
- Ch 3: Pump Tertiary status
- Ch 4–6: Rod positions (Safety, Shim, Regulating)
- Ch 7: Thermal Power (kW)
- Ch 8: System Status

---

## 5. Model Simulasi Reaktor

### Jenis Reaktor
**PWR (Pressurized Water Reactor)** — Reaktor air bertekanan dengan 3 loop sirkulasi (primer, sekunder, tersier) dan turbin uap.

### Parameter & Konstanta Fisika

| Parameter | Simbol | Nilai/Range | Satuan | Lokasi Kode |
|-----------|--------|-------------|--------|-------------|
| Daya thermal maks | P_th_max | 900,000 | kW | `esp_utama_uart.ino:604` |
| Daya listrik maks | P_e_max | 300,000 | kW | `esp_utama_uart.ino:614` |
| Efisiensi turbin | η | 0.34 (34%) | — | `esp_utama_uart.ino:609` |
| Tekanan operasi | P_op | 150.0 | bar | `raspi_config.py:79` |
| Tekanan minimum pompa | P_min_pump | 40.0 | bar | `raspi_config.py:78` |
| Tekanan warning | P_warn | 160.0 | bar | `raspi_config.py:80` |
| Tekanan critical | P_crit | 180.0 | bar | `raspi_config.py:81` |
| Tekanan maks | P_max | 200.0 | bar | `raspi_config.py:77` |
| Tekanan interlock rod | P_interlock | 140.0 | bar | `raspi_main_panel.py:892` |
| Range posisi rod | — | 0–100 | % | `raspi_main_panel.py:98-100` |
| Turbin threshold start | — | 50,000 | kW (thermal) | `esp_utama_uart.ino:632` |
| Turbin threshold stop | — | 20,000 | kW (thermal) | `esp_utama_uart.ino:649` |
| Turbin ramp up | — | +0.5 | %/loop | `esp_utama_uart.ino:640` |
| Turbin ramp down | — | -1.0 | %/loop | `esp_utama_uart.ino:657` |
| Pump startup delay | — | 2.0 | detik | `raspi_main_panel.py` |
| Pump shutdown delay | — | 1.0 | detik | `raspi_main_panel.py` |
| SCRAM rod drop | — | 3.0 | detik | `raspi_main_panel.py:470` |
| Turbin spin-down | — | ~12 | detik | `raspi_main_panel.py:502` |
| Auto-reset timeout | — | 900 (15 min) | detik | `raspi_main_panel.py` |
| SG threshold (shim) | — | 40.0 | % | `raspi_humidifier_control.py:49` |
| SG threshold (reg) | — | 40.0 | % | `raspi_humidifier_control.py:50` |
| SG hysteresis | — | 5.0 | % | `raspi_humidifier_control.py` |
| CT1 threshold | — | 60,000 | kW (60 MWe) | `raspi_humidifier_control.py` |
| CT2 threshold | — | 120,000 | kW (120 MWe) | `raspi_humidifier_control.py` |
| CT3 threshold | — | 180,000 | kW (180 MWe) | `raspi_humidifier_control.py` |
| CT4 threshold | — | 240,000 | kW (240 MWe) | `raspi_humidifier_control.py` |
| CT hysteresis | — | 10,000 | kW (10 MWe) | `raspi_humidifier_control.py` |

### Algoritma Simulasi

#### Daya Thermal (dihitung di ESP-BC setiap loop ~10ms)

```
avgRodPosition = (shim_actual + regulating_actual) / 2.0

IF avgRodPosition > 10%:
    reactor_thermal_kw = avgRodPosition² × 90.0
                       + shim_actual × 150.0
                       + regulating_actual × 200.0
    Cap at 900,000 kW (900 MWth)

thermal_kw_output = reactor_thermal_kw × 0.34 × (turbine_power_level / 100)
    Cap at 300,000 kW (300 MWe)
```

Lokasi: `esp_utama_uart.ino` fungsi `calculateThermalPower()` (line 594–615)

#### Kecepatan Turbin

```
turbine_speed = average(shim_actual, regulating_actual)
  IF < 10% → motor stop
  IF ≥ 10% → motor FORWARD, PWM proportional
```

#### Cherenkov LED

```
cherenkov_brightness = average(shim_actual, regulating_actual)
  IF < 0.5% → LED off
  Maps 0–100% → PWM 0–255
```

Lokasi: `esp_utama_uart.ino` (line ~804–822)

#### Pump Speed Ramping

```
Command → Target speed:
  0 (OFF)            → 0%
  1 (STARTING)       → 50%
  2 (ON)             → 100%
  3 (SHUTTING_DOWN)  → 20%

Ramp rate: +1%/loop (speed up), -2%/loop (slow down)
Full ramp 0→100% ≈ 1 detik (loop interval 10ms)
```

### Skenario Operasi

#### Mode Manual
Operator mengontrol setiap parameter secara individual:
1. Naikkan tekanan pressurizer ke ≥ 140 bar
2. Nyalakan pompa urut: Tersier → Sekunder → Primer
3. Naikkan safety rod ke 100%
4. Naikkan shim rod & regulating rod bertahap
5. Turbin auto-start di 50 MWth
6. Cooling tower auto-activate bertahap

#### Mode Auto Simulation (8 Phase)
Diaktifkan via tombol START_AUTO (GPIO 17). Menjalankan startup sequence lengkap secara otomatis:
1. Raise pressure ke 155 bar
2. Start pompa (Tertiary → Secondary → Primary, masing-masing tunggu 2 detik ON)
3. Raise safety rod ke 100%
4. Raise shim rod ke 80%
5. Raise regulating rod ke 80%
6. Tunggu turbin auto-start (thermal > 50 MWth)
7. Steady state operation
8. Auto monitoring (inactivity reset setelah 15 menit)

Lokasi: `raspi_main_panel.py` `auto_simulation_thread()` (line ~1395+)

---

## 6. Sistem Keselamatan ⚠️

> **BAGIAN INI TIDAK BOLEH DIMODIFIKASI TANPA REVIEW MENDALAM**
>
> Semua perubahan pada logika interlock, SCRAM, alarm, atau safety harus melalui
> review manusia. Kesalahan pada sistem keselamatan dapat menyebabkan perilaku
> simulator yang tidak realistis dan mengurangi nilai edukasi.

### SCRAM Conditions

| Kondisi | Threshold | Aksi | Lokasi Kode |
|---------|-----------|------|-------------|
| Emergency button press | GPIO 18 LOW | All rods drop 3s + turbine spin-down 12s + buzzer 5s | `raspi_main_panel.py:438–511` |
| Manual SCRAM | Tombol EMERGENCY | `_execute_scram_sequence()` dipanggil | `raspi_main_panel.py:438` |

#### Urutan SCRAM:
1. Semua 3 rod turun bersamaan (3 detik, smooth animation via progress curve)
2. Turbine spin-down dimulai paralel (12 detik, linear deceleration)
3. Pompa tetap ON (decay heat removal)
4. Buzzer emergency berbunyi 5 detik kemudian berhenti
5. `emergency_active = True` → interlock mencegah rod movement

### Alarm System

| Level | Kondisi | Threshold | Frekuensi | Pattern | Response |
|-------|---------|-----------|-----------|---------|----------|
| 1 - Procedure Warning | Pump start tanpa tekanan | P < 40 bar saat pump ON | 2000 Hz | 0.3s on/off | Peringatan prosedur |
| 2 - Pressure Warning | Tekanan mendekati limit | P ≥ 160 bar | 2500 Hz | 0.5s on/off | Peringatan |
| 3 - Pressure Critical | Tekanan mendekati maks | P ≥ 180 bar | 3000 Hz | Double beep (0.2/0.2/0.2/0.6s) | Alarm kritis |
| 4 - Emergency SCRAM | Shutdown darurat | Manual trigger | 4000 Hz | Rapid 0.1s on/off | SCRAM sequence |
| 5 - Interlock Violation | Rod movement tanpa izin | Interlock not satisfied | 1500 Hz | 0.2s on, 0.8s off | Tolak aksi |

Lokasi: `raspi_buzzer_alarm.py` class `BuzzerAlarm` (line 28–60)

### Interlock Logic

**Rod Movement Interlock** (harus semua terpenuhi):

```
1. Tekanan pressurizer ≥ 140 bar
2. Emergency TIDAK aktif (emergency_active == False)
3. Pompa primer ON (status == 2)
4. Pompa sekunder ON (status == 2)
5. Pompa tersier ON (status == 2)
```

Lokasi: `raspi_main_panel.py` `_check_interlock_internal()` (line 867–914)

**Pump Startup Sequence** (urutan wajib):

```
Tersier → Sekunder → Primer
- Semua pompa butuh P ≥ 40 bar
- Sekunder butuh Tersier ON (status == 2) terlebih dahulu
- Primer butuh Tersier AND Sekunder ON terlebih dahulu
```

Lokasi: `raspi_main_panel.py` `_check_pump_start_safe()` (line 916+)

**Rod Hierarchy** (prioritas keselamatan):

```
- Safety rod HARUS 100% sebelum shim/regulating bisa dinaikkan
- Safety rod TIDAK BOLEH diturunkan di bawah posisi shim/regulating
- Urutan: Safety → Shim → Regulating
```

### Fail-Safe Defaults

| Parameter | Nilai Default | Alasan |
|-----------|--------------|--------|
| Semua rod positions | 0% (inserted) | Rod di dalam = reaktor subcritical |
| Semua pump status | 0 (OFF) | Tidak ada sirkulasi paksa |
| Tekanan | 0.0 bar | Belum dipressurisasi |
| Emergency active | False | Tapi interlock tetap mencegah tanpa kondisi terpenuhi |
| Turbin state | IDLE | Belum beroperasi |
| Semua humidifier | OFF | Belum perlu pendinginan |

---

## 7. Riwayat Pengembangan Fitur

### Core System (Baseline)
Sistem inti: Panel kontrol dengan 17 tombol, 9 OLED, 2 ESP32 via UART binary protocol, model fisika reaktor PWR sederhana, turbin state machine, 3 pompa sirkulasi. Ini adalah fondasi yang sudah stabil.

**File inti**: `raspi_main_panel.py`, `raspi_uart_master.py`, `raspi_gpio_buttons.py`, `raspi_config.py`, `esp_utama_uart.ino`, `esp_visualizer_uart.ino`

---

### Pengembangan 1: UART Binary Protocol (v4.0)
- **Deskripsi**: Migrasi dari I2C/JSON ke UART binary protocol dengan CRC8-MAXIM checksum. Mengurangi ukuran paket 83% (command) dan 85% (response) dibanding JSON.
- **File terkait**: `raspi_uart_master.py`, `esp_utama_uart.ino`, `esp_visualizer_uart.ino`
- **Hardware baru**: Tidak ada (menggunakan UART0 + UART3 built-in pada Raspberry Pi)
- **Dependensi baru**: `pyserial`
- **Interaksi dengan core**: Menggantikan sepenuhnya `raspi_i2c_master.py` untuk komunikasi ESP. I2C tetap digunakan hanya untuk OLED via TCA9548A.

### Pengembangan 2: Staged Cooling Tower Control (v3.6)
- **Deskripsi**: Humidifier cooling tower diaktifkan bertahap (CT1 → CT4) berdasarkan power level, bukan semua sekaligus. Mensimulasikan manajemen kapasitas pendinginan realistis.
- **File terkait**: `raspi_humidifier_control.py`
- **Hardware baru**: 4× relay module pada ESP-BC (GPIO 27, 26, 25, 32)
- **Dependensi baru**: Tidak ada
- **Interaksi dengan core**: `ControlLogic` thread memanggil `HumidifierController.update()` setiap 50ms, mengirim command via UART ke ESP-BC

### Pengembangan 3: Video Education Display
- **Deskripsi**: Sistem display terpisah menggunakan pygame untuk menampilkan video edukasi (mpv) dan panduan interaktif. Membaca state simulator dari file JSON shared.
- **File terkait**: `pltn_video_display/video_display_app.py`, `pltn_video_display/speedometer_temp.py`
- **Hardware baru**: Monitor HDMI tambahan
- **Dependensi baru**: `pygame==2.5.2`, `mpv` (system package)
- **Interaksi dengan core**: Membaca `/tmp/pltn_state.json` yang ditulis oleh `StateExport` thread (atomic write, 10 Hz)

### Pengembangan 4: Cherenkov Radiation Effect
- **Deskripsi**: LED biru pada ESP-BC yang brightness-nya proporsional terhadap posisi rata-rata rod. Mensimulasikan efek radiasi Cherenkov pada air pendingin.
- **File terkait**: `esp_utama_uart.ino` (line ~804–822)
- **Hardware baru**: 1× Blue LED pada ESP-BC GPIO 33
- **Dependensi baru**: Tidak ada
- **Interaksi dengan core**: Menggunakan data `shim_actual` dan `regulating_actual` yang sudah ada

### Pengembangan 5: Inactivity Auto-Reset
- **Deskripsi**: Setelah 15 menit tanpa button press, simulator otomatis reset semua parameter ke 0. Untuk situasi pameran/demo tanpa operator.
- **File terkait**: `raspi_main_panel.py` (`ControlLogic` thread)
- **Hardware baru**: Tidak ada
- **Dependensi baru**: Tidak ada
- **Interaksi dengan core**: Timer di `ControlLogic` thread, memanggil `_execute_reactor_reset()`

### Pengembangan 6: Speedometer Power Gauge
- **Deskripsi**: Arc gauge visual untuk menampilkan daya listrik output pada video display. Menggunakan pygame drawing primitives.
- **File terkait**: `pltn_video_display/speedometer_temp.py`
- **Hardware baru**: Tidak ada (menggunakan monitor HDMI yang sama)
- **Dependensi baru**: Tidak ada (pygame sudah ada)
- **Interaksi dengan core**: Komponen UI yang dipanggil oleh `video_display_app.py`

### Pengembangan 7: HDMI Audio Output
- **Deskripsi**: Konfigurasi audio output via HDMI menggunakan ALSA (bukan 3.5mm jack) untuk video edukasi.
- **File terkait**: `AUDIO_HDMI_SETUP.md`, `pltn_video_display/video_display_app.py`
- **Hardware baru**: Tidak ada (built-in HDMI audio)
- **Dependensi baru**: ALSA (`plughw:1,0`)
- **Interaksi dengan core**: Hanya mempengaruhi mpv video player pada video display

### Pengembangan 8: Safety Rod Shutdown Fix
- **Deskripsi**: Perbaikan logika safety rod saat shutdown agar rod tidak bisa diturunkan di bawah posisi shim/regulating.
- **File terkait**: `raspi_main_panel.py`
- **Hardware baru**: Tidak ada
- **Dependensi baru**: Tidak ada
- **Interaksi dengan core**: Modifikasi logika rod movement di `EventProcessor`

### Pengembangan 9: UI Indicator Redesign
- **Deskripsi**: Redesign indikator UI dan penambahan indikator baru pada video display. (Branch `doel`, sudah merge ke `main`)
- **File terkait**: `pltn_video_display/video_display_app.py`
- **Hardware baru**: Tidak ada
- **Dependensi baru**: Tidak ada
- **Interaksi dengan core**: Perubahan visual-only pada video display

### Pengembangan 10: Development Test Visualizer
- **Deskripsi**: Versi development ESP-E yang bisa berjalan tanpa koneksi UART (simulasi data internal). Untuk testing hardware LED tanpa Raspberry Pi.
- **File terkait**: `tes_visualizer/tes_visualizer.ino`
- **Hardware baru**: Tidak ada (menggunakan ESP-E yang sama)
- **Dependensi baru**: Tidak ada
- **Interaksi dengan core**: Standalone — tidak terhubung ke sistem utama

---

## 8. Dependensi & Setup

### Raspberry Pi (Python)

```bash
# System packages
sudo apt update
sudo apt install python3-pip python3-dev i2c-tools

# Python libraries
pip3 install RPi.GPIO
pip3 install smbus2
pip3 install adafruit-circuitpython-ssd1306
pip3 install Pillow
pip3 install pyserial

# Enable I2C dan UART
sudo raspi-config  # → Interface Options → I2C (Enable), Serial Port (Enable)
```

| Library | Versi | Kegunaan |
|---------|-------|----------|
| RPi.GPIO | — | Kontrol GPIO (buttons, buzzer PWM) |
| smbus2 | — | Komunikasi I2C (TCA9548A, OLED) |
| adafruit-circuitpython-ssd1306 | — | Driver OLED SSD1306 |
| Pillow | — | Image rendering untuk OLED |
| pyserial | — | Komunikasi UART ke ESP32 |

### Video Display (Python — bisa di Pi yang sama atau terpisah)

```bash
pip3 install pygame==2.5.2
sudo apt install mpv  # Video player
```

| Library | Versi | Kegunaan |
|---------|-------|----------|
| pygame | 2.5.2 | UI framework untuk display edukasi |
| mpv | system | Video player untuk video edukasi |

### ESP32 (Arduino IDE)

```
Board: ESP32 Dev Module
Library: ESP32Servo (dari Library Manager)
Upload speed: 115200
```

| Library | Versi | Kegunaan |
|---------|-------|----------|
| ESP32Servo | — | Kontrol servo motor (control rods) |
| SPI (built-in) | — | Komunikasi 74HC595 shift register |
| HardwareSerial (built-in) | — | UART komunikasi dengan Raspberry Pi |

---

## 9. Cara Menjalankan

### Central Control (Raspberry Pi)

```bash
cd raspi_central_control/
python3 raspi_main_panel.py
```

Program akan:
1. Menjalankan health check (I2C, UART, GPIO)
2. Inisialisasi semua thread
3. Mulai polling tombol dan komunikasi ESP
4. Log status ke console setiap 1 detik

### Video Display (opsional, bisa di Pi yang sama)

```bash
cd pltn_video_display/
python3 video_display_app.py
```

Membaca state dari `/tmp/pltn_state.json`. Bisa dijalankan sebelum atau sesudah central control.

### ESP32 Firmware

Upload via Arduino IDE:
1. Buka `esp_utama_uart/esp_utama_uart.ino` → Upload ke ESP-BC
2. Buka `esp_visualizer_uart/esp_visualizer_uart.ino` → Upload ke ESP-E
3. Untuk testing tanpa Raspberry Pi: `tes_visualizer/tes_visualizer.ino` → Upload ke ESP-E

### Keyboard Simulation (Development)

`video_display_app.py` memiliki keyboard mapping untuk 17 tombol fisik — berguna untuk testing tanpa hardware panel.

---

## 10. Panduan untuk AI Agent

### 📚 Domain-Specific Skills

Project ini memiliki **specialized knowledge files** di `.claude/skills/` yang berisi pengetahuan mendalam untuk area tertentu.

**⚡ WAJIB**: Baca skill file yang relevan **SEBELUM** melakukan perubahan di area tersebut.

#### Quick Reference: Task → Skill Mapping

| Saya sedang bekerja pada... | Baca skill ini terlebih dahulu |
|----------------------------|-------------------------------|
| **GPIO, sensor, button detection, threading** | `.claude/skills/firmware-embedded.md` |
| **Thermal power, neutron flux, reactivity, physics formula** | `.claude/skills/nuclear-sim-physics.md` |
| **SCRAM, interlocks, alarm thresholds, safety sequence** | `.claude/skills/safety-logic.md` |
| **OLED display, UI layout, buzzer patterns, visual feedback** | `.claude/skills/hmi-display.md` |
| **Tidak paham istilah nuklir (pressurizer, xenon, dll)** | `.claude/skills/pltn-domain-knowledge.md` |

#### Automatic Triggers: File Pattern → Skill

Ketika Anda akan memodifikasi file ini, baca skill yang sesuai:

| File Pattern | Skill to Read |
|--------------|---------------|
| `raspi_gpio_*.py`, `raspi_*_buttons.py` | `firmware-embedded.md` |
| `raspi_config.py` (thresholds, timing, hardware constants) | `nuclear-sim-physics.md` + `safety-logic.md` |
| `esp_utama_uart.ino` (calculateThermalPower, model fisika) | `nuclear-sim-physics.md` + `firmware-embedded.md` |
| `raspi_main_panel.py` (interlock, SCRAM, pump sequence) | `safety-logic.md` |
| `raspi_buzzer_alarm.py`, `raspi_oled_manager.py` | `hmi-display.md` |
| `pltn_video_display/*.py` | `hmi-display.md` |

#### Keyword-Based Triggers

Jika task/issue/bug mengandung keyword ini, baca skill yang sesuai:

- **GPIO, interrupt, edge detection, level detection, threading, race condition** → `firmware-embedded.md`
- **thermal power, neutron, reactivity, delayed neutron, xenon, rod worth** → `nuclear-sim-physics.md`
- **SCRAM, interlock, alarm, threshold, safety limit, trip** → `safety-logic.md`
- **display, OLED, UI, HMI, buzzer, tone, visual feedback** → `hmi-display.md`
- **pressurizer, coolant, primary loop, secondary loop, control rod, moderator** → `pltn-domain-knowledge.md`

#### Usage Workflow

```
1. Terima task atau identifikasi file yang akan dimodifikasi
2. ✅ Cek tabel/trigger di atas → tentukan skill yang relevan
3. 📖 Gunakan `view` tool untuk membaca skill file
4. 💡 Pahami domain context, pattern, dan best practices
5. 🛠️ Lakukan modifikasi dengan pengetahuan domain yang tepat
```

#### Contoh Penggunaan

**Scenario 1**: Task = "Tambahkan alarm baru untuk xenon poisoning"
- ✅ Keyword: "alarm", "xenon" → Baca `safety-logic.md` + `nuclear-sim-physics.md`
- ✅ File target: `raspi_buzzer_alarm.py` → Baca `hmi-display.md`
- 📖 View 3 skill files untuk memahami context
- 🛠️ Implement alarm logic dengan pengetahuan domain

**Scenario 2**: Task = "Fix button debounce issue on SCRAM button"
- ✅ Keyword: "button", "debounce" → Baca `firmware-embedded.md`
- ✅ File: `raspi_gpio_buttons.py` → Baca `firmware-embedded.md`
- ✅ Context: SCRAM → Baca `safety-logic.md` untuk memahami criticality
- 📖 View 2 skill files
- 🛠️ Fix dengan mempertimbangkan safety requirements

**Scenario 3**: Task = "Optimize thermal power calculation"
- ✅ Keyword: "thermal power" → Baca `nuclear-sim-physics.md`
- ✅ File: `esp_utama_uart.ino` → Baca `firmware-embedded.md` (untuk ESP32 patterns)
- 📖 View 2 skill files
- 🛠️ Optimize dengan memahami physics model

---

### ✅ Boleh dimodifikasi bebas
- `pltn_video_display/` — UI display, animasi, tata letak visual
- `speedometer_temp.py` — Gauge visual
- `raspi_oled_manager.py` — Layout dan format tampilan OLED
- `raspi_system_health.py` — Diagnostik dan health check
- `tes_visualizer/` — Versi development/testing
- Dokumentasi `.md` (kecuali bagian safety di `AGENT.md`)
- Log format dan level di `raspi_config.py` (bagian Logging Configuration)

### ⚠️ Perlu hati-hati
- `raspi_main_panel.py` — God class, perubahan bisa berdampak luas. Selalu test threading.
- `raspi_uart_master.py` — Perubahan protocol harus sinkron dengan firmware ESP32
- `raspi_gpio_buttons.py` — Mapping pin harus sesuai wiring fisik
- `raspi_humidifier_control.py` — Threshold berpengaruh ke perilaku humidifier
- `raspi_buzzer_alarm.py` — Frekuensi dan pattern alarm
- `raspi_config.py` — Konstanta global yang dipakai banyak modul (⚠️ sudah ada bug pin mapping)
- `esp_utama_uart.ino` — Firmware + model fisika, harus di-flash ulang jika berubah
- `esp_visualizer_uart.ino` — Firmware LED, harus di-flash ulang jika berubah

### 🚫 Jangan ubah tanpa review manusia
- **Interlock logic** (`raspi_main_panel.py` `_check_interlock_internal()` line 867–914)
- **SCRAM sequence** (`raspi_main_panel.py` `_execute_scram_sequence()` line 438–511)
- **Pump startup sequence** (`raspi_main_panel.py` `_check_pump_start_safe()` line 916+)
- **Rod hierarchy rules** (safety > shim > regulating)
- **Alarm thresholds** (`raspi_buzzer_alarm.py` `ALARM_TONES`)
- **UART protocol frame format** (STX/ETX/CRC/command structure)
- **Thermal power formula** (`esp_utama_uart.ino` `calculateThermalPower()`)
- **Turbine state machine** (`esp_utama_uart.ino` `updateTurbineState()`)
- **Pressure thresholds** di `raspi_config.py` (line 76–83)

### Pola Task Umum

**Menambah tombol baru:**
1. Tambah pin di `raspi_gpio_buttons.py` `ButtonPin` enum
2. Tambah di `BUTTON_NAMES` dict (file yang sama)
3. Tentukan tipe deteksi (edge/level) di `ButtonHandler.__init__()`
4. Tambah handler di `raspi_main_panel.py` `_process_button_event()`
5. Update `GPIO_PIN_MAPPING.md`

**Menambah alarm baru:**
1. Tambah konstanta `ALARM_xxx` di `raspi_buzzer_alarm.py`
2. Tambah entry di `ALARM_TONES` dict dengan freq dan pattern
3. Panggil `self.buzzer.set_alarm(BuzzerAlarm.ALARM_xxx)` dari `raspi_main_panel.py`

**Memodifikasi parameter simulasi:**
1. Ubah konstanta di `raspi_config.py` (thresholds, timing)
2. Atau ubah di `esp_utama_uart.ino` (model fisika, turbin)
3. ⚠️ Jika mengubah protocol UART, update KEDUA sisi (Python + Arduino)

**Menambah OLED display baru:**
1. Tambah channel di `raspi_config.py` (`OLED_CHANNEL_xxx`)
2. Tambah rendering di `raspi_oled_manager.py`
3. Pastikan TCA9548A channel tersedia (max 8 per multiplexer)

**Menambah aktuator ESP-BC baru:**
1. Define pin di `esp_utama_uart.ino`
2. Tambah field di UART payload — update `UPDATE_CMD_LEN` dan `UPDATE_RESP_LEN`
3. Update encoder di `raspi_uart_master.py` `_encode_esp_bc_command()`
4. Update decoder di `raspi_uart_master.py` `_decode_esp_bc_response()`
5. ⚠️ HARUS update kedua sisi secara sinkron!

**Debugging masalah komunikasi UART:**
1. Cek `raspi_system_health.py` output — apakah UART port terdeteksi
2. Cek serial monitor ESP32 (115200 baud) — apakah menerima data
3. Cek CRC error count di log — `CRC mismatch` atau `NACK`
4. Verifikasi kabel TX↔RX cross-connected
5. Pastikan baudrate sama (115200) di kedua sisi

---

## 11. Known Issues & TODO

### ✅ Fixed Issues (v4.0)

1. **`raspi_config.py` duplicate `BTN_PUMP_PRIM_ON`** — **FIXED**
   - Removed duplicate button pin definitions (lines 54-61)
   - Button pins now exclusively defined in `raspi_gpio_buttons.py` `ButtonPin` enum
   - Config.py only contains hardware output pins (buzzer, etc.)

2. **UART3 port path mismatch** — **FIXED**
   - Was: `/dev/ttyAMA3` (incorrect)
   - Now: `/dev/ttyAMA1` (correct - matches Raspberry Pi UART3 device tree)
   - Updated in `raspi_config.py` line 11 and `raspi_uart_master.py` header

3. **`raspi_README.md` outdated** — **FIXED**
   - Completely rewritten to reflect v4.0 UART architecture
   - Now includes proper references to main README.md and AGENT.md
   - Installation guide updated with UART3 setup instructions

4. **`raspi_i2c_master.py` not marked deprecated** — **FIXED**
   - Added clear deprecation header warning
   - Notes replacement with `raspi_uart_master.py`
   - Marked as safe to delete (kept for reference only)

### Bug Aktif

None currently — all critical bugs addressed in v4.0 documentation cleanup.

### Dead Code

5. **`raspi_i2c_master.py`** (417 baris) — Legacy dari arsitektur v3.x I2C. 
   - Now marked with deprecation warning
   - Safe to delete (kept for reference)
   - Not imported by `raspi_main_panel.py`

### Duplikasi

6. **`tes_visualizer/tes_visualizer.ino`** (714 baris) — Hampir identik dengan `esp_visualizer_uart.ino` (564 baris) tetapi dengan `DEV_MODE true` dan tambahan simulasi lokal. Potensi drift jika salah satu diupdate tanpa yang lain.

### TODO / Enhancement Ideas

7. **Refactor `raspi_main_panel.py`** — 1992 baris dalam satu class (God class anti-pattern). Bisa dipecah menjadi:
   - `reactor_logic.py` — Interlock, rod hierarchy, SCRAM
   - `pump_controller.py` — Pump state machine
   - `auto_simulation.py` — Auto simulation sequence
   - `state_export.py` — JSON export

9. **Unit tests** — Tidak ada test apapun di repositori. Model fisika dan interlock logic sebaiknya punya unit test.

---

## 12. Glossary

| Term | Definisi | Konteks dalam Kode |
|------|----------|-------------------|
| PWR | Pressurized Water Reactor — tipe reaktor nuklir air bertekanan | Model reaktor yang disimulasikan |
| SCRAM | Safety Control Rod Axe Man — shutdown darurat reaktor | `_execute_scram_sequence()` di `raspi_main_panel.py` |
| Control Rod | Batang kendali yang menyerap neutron | 3 tipe: Safety, Shim, Regulating (0–100%) |
| Safety Rod | Rod keselamatan — harus 100% sebelum rod lain bisa naik | `state.safety_rod` — prioritas tertinggi |
| Shim Rod | Rod pengatur kasar — mengatur daya dalam range besar | `state.shim_rod` — kontribusi 150× ke thermal |
| Regulating Rod | Rod pengatur halus — fine-tuning daya | `state.regulating_rod` — kontribusi 200× ke thermal |
| Pressurizer | Alat pengatur tekanan sistem primer | `state.pressure` (0–200 bar) |
| Interlock | Pengunci keselamatan — syarat harus terpenuhi untuk aksi | `_check_interlock_internal()` |
| Thermal Power | Daya panas dari reaksi fisi (MWth) | `reactor_thermal_kw` di ESP-BC |
| Electrical Power | Daya listrik setelah konversi turbin (MWe) | `thermal_kw_calculated` di ESP-BC |
| Turbine FSM | Finite State Machine turbin: IDLE→STARTING→RUNNING→SHUTDOWN | `updateTurbineState()` di ESP-BC |
| ESP-BC | ESP32 Board Controller — mengontrol servo, motor, relay | `esp_utama_uart.ino` |
| ESP-E | ESP32 Effects — mengontrol LED visualisasi | `esp_visualizer_uart.ino` |
| TCA9548A | I2C multiplexer — mengizinkan 8 device I2C di satu bus | `raspi_tca9548a.py`, alamat 0x70 |
| SSD1306 | Chip driver OLED 128×32 px monochrome | 9 unit via TCA9548A |
| 74HC595 | Shift register 8-bit — memperluas output digital | 3 unit di ESP-E (24 output LED) |
| L298N | H-Bridge motor driver — mengontrol motor DC bidirectional | 4 unit di ESP-BC (3 pompa + turbin) |
| CT (Cooling Tower) | Menara pendingin — membuang panas ke atmosfer | 4 unit (CT1–CT4) dengan relay |
| SG (Steam Generator) | Generator uap — transfer panas primer→sekunder | 2 unit (SG1–SG2) |
| Cherenkov | Radiasi Cherenkov — cahaya biru saat partikel > kecepatan cahaya dalam air | LED biru GPIO 33 ESP-BC |
| CRC8-MAXIM | Cyclic Redundancy Check 8-bit polynomial 0x31 | Error detection pada UART protocol |
| STX/ETX | Start/End of Text (0x02/0x03) | Frame delimiter UART protocol |
| ACK/NACK | Acknowledge/Negative Acknowledge (0x06/0x15) | Response UART protocol |
| Edge Detection | Deteksi perubahan state (press/release) — satu aksi per tekan | Tombol pump, start, reset, emergency |
| Level Detection | Deteksi state aktif (held down) — aksi berulang selama ditahan | Tombol rod up/down, pressure up/down |
| God Class | Anti-pattern: satu class yang terlalu banyak tanggung jawab | `PLTNPanelController` (1992 baris) |
