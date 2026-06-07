---
name: Nuclear Reactor Simulation Physics
description: Reactor physics formulas and simulation parameters
---

# Skill: Nuclear Reactor Simulation Physics

## Jenis Reaktor & Level Simulasi

**Jenis**: PWR (Pressurized Water Reactor) — Reaktor air bertekanan
**Level simulasi**: Simplified educational model — bukan high-fidelity nuclear engineering simulation.

Model ini dirancang untuk **edukasi mahasiswa teknik nuklir** dalam konteks PKM 2024. Fisika disederhanakan secara intentional agar:
- Respons cukup cepat untuk demo interaktif (real-time feedback)
- Operator bisa merasakan hubungan kualitatif antara parameter
- Prosedur keselamatan tetap realistis (interlock, SCRAM, pump sequence)

Kalkulasi fisika utama dilakukan di **ESP-BC** (`esp_utama_uart.ino`) setiap ~10ms loop cycle. Raspberry Pi hanya mengelola state management, interlock, dan UI — tidak menghitung fisika.

---

## Semua Parameter & Konstanta

### Konstanta Fisika Reaktor (ESP-BC)

| Konstanta | Nilai | Satuan | Penjelasan | Lokasi Kode |
|-----------|-------|--------|------------|-------------|
| MAX_THERMAL_POWER | 900,000 | kW | Daya thermal maksimum reaktor (900 MWth) | `esp_utama_uart.ino:604` |
| MAX_ELECTRICAL_POWER | 300,000 | kW | Daya listrik maksimum (300 MWe) | `esp_utama_uart.ino:614` |
| TURBINE_EFFICIENCY | 0.34 | — | Efisiensi konversi thermal→elektrik (34%) | `esp_utama_uart.ino:609` |
| Koefisien quadratic | 90.0 | kW/%² | Faktor posisi rod rata-rata kuadrat | `esp_utama_uart.ino:599` |
| Koefisien shim linear | 150.0 | kW/% | Kontribusi linear rod shim | `esp_utama_uart.ino:600` |
| Koefisien reg linear | 200.0 | kW/% | Kontribusi linear rod regulating | `esp_utama_uart.ino:601` |
| ROD_THRESHOLD_MIN | 10.0 | % | Posisi rod minimum untuk menghasilkan thermal | `esp_utama_uart.ino:598` |
| TURBINE_START_THRESHOLD | 50,000 | kW | Thermal capacity untuk turbin auto-start | `esp_utama_uart.ino:632` |
| TURBINE_STOP_THRESHOLD | 20,000 | kW | Thermal capacity untuk turbin auto-shutdown | `esp_utama_uart.ino:649` |
| TURBINE_RAMP_UP | +0.5 | %/loop | Kenaikan power level turbin per loop (~10ms) | `esp_utama_uart.ino:640` |
| TURBINE_RAMP_DOWN | -1.0 | %/loop | Penurunan power level turbin per loop | `esp_utama_uart.ino:657` |
| CHERENKOV_THRESHOLD | 0.5 | % | Minimum rod average untuk LED menyala | `esp_utama_uart.ino:813` |
| PWM_FREQ | 5000 | Hz | Frekuensi PWM motor & LED | `esp_utama_uart.ino:134` |
| PWM_RESOLUTION | 8 | bit | Resolusi PWM (0-255) | `esp_utama_uart.ino:135` |
| TURBINE_SPEED_MIN | 10.0 | % | Rod average minimum untuk motor turbin berputar | `esp_utama_uart.ino:790` |

### Konstanta Sistem Tekanan (Raspberry Pi)

| Konstanta | Nilai | Satuan | Penjelasan | Lokasi Kode |
|-----------|-------|--------|------------|-------------|
| PRESS_MIN | 0.0 | bar | Tekanan minimum | `raspi_config.py:76` |
| PRESS_MAX | 200.0 | bar | Tekanan maksimum absolut | `raspi_config.py:77` |
| PRESS_MIN_ACTIVATE_PUMP1 | 40.0 | bar | Tekanan minimum untuk nyalakan pompa | `raspi_config.py:78` |
| PRESS_NORMAL_OPERATION | 150.0 | bar | Tekanan operasi normal | `raspi_config.py:79` |
| PRESS_WARNING_ABOVE | 160.0 | bar | Threshold alarm peringatan tekanan | `raspi_config.py:80` |
| PRESS_CRITICAL_HIGH | 180.0 | bar | Threshold alarm kritis tekanan | `raspi_config.py:81` |
| PRESS_INTERLOCK | 140.0 | bar | Tekanan minimum untuk interlock rod movement | `raspi_main_panel.py:892` |
| PRESS_INCREMENT | 1.0 | bar/press | Kenaikan tekanan per button press | `raspi_main_panel.py:571` |

### Konstanta Pompa (Raspberry Pi + ESP-BC)

| Konstanta | Nilai | Satuan | Penjelasan | Lokasi Kode |
|-----------|-------|--------|------------|-------------|
| PUMP_OFF | 0 | — | Status pompa mati | `raspi_config.py:86` |
| PUMP_STARTING | 1 | — | Status pompa sedang start | `raspi_config.py:87` |
| PUMP_ON | 2 | — | Status pompa nyala penuh | `raspi_config.py:88` |
| PUMP_SHUTTING_DOWN | 3 | — | Status pompa sedang mati | `raspi_config.py:89` |
| PUMP_STARTUP_DELAY | 2.0 | detik | Durasi transisi STARTING→ON | `raspi_main_panel.py:1132` |
| PUMP_SHUTDOWN_DELAY | 1.0 | detik | Durasi transisi SHUTTING_DOWN→OFF | `raspi_main_panel.py:1140` |
| PUMP_TARGET_OFF | 0.0 | % | Target speed saat OFF | `esp_utama_uart.ino:706` |
| PUMP_TARGET_STARTING | 50.0 | % | Target speed saat STARTING | `esp_utama_uart.ino:708` |
| PUMP_TARGET_ON | 100.0 | % | Target speed saat ON | `esp_utama_uart.ino:710` |
| PUMP_TARGET_SHUTTING | 20.0 | % | Target speed saat SHUTTING_DOWN | `esp_utama_uart.ino:712` |
| PUMP_RAMP_UP | +1.0 | %/loop | Kenaikan speed per loop (~10ms) | `esp_utama_uart.ino:716` |
| PUMP_RAMP_DOWN | -2.0 | %/loop | Penurunan speed per loop (~10ms) | `esp_utama_uart.ino:721` |

### Konstanta Humidifier (Raspberry Pi)

| Konstanta | Nilai | Satuan | Penjelasan | Lokasi Kode |
|-----------|-------|--------|------------|-------------|
| SG_SHIM_THRESHOLD | 40.0 | % | Minimum shim rod untuk Steam Generator ON | `raspi_humidifier_control.py:49` |
| SG_REG_THRESHOLD | 40.0 | % | Minimum regulating rod untuk SG ON | `raspi_humidifier_control.py:50` |
| SG_HYSTERESIS | 5.0 | % | Hysteresis untuk SG (prevent flapping) | `raspi_humidifier_control.py` |
| CT1_THRESHOLD | 60,000 | kW | Threshold aktivasi Cooling Tower 1 (60 MWe) | `raspi_humidifier_control.py` |
| CT2_THRESHOLD | 120,000 | kW | Threshold aktivasi Cooling Tower 2 (120 MWe) | `raspi_humidifier_control.py` |
| CT3_THRESHOLD | 180,000 | kW | Threshold aktivasi Cooling Tower 3 (180 MWe) | `raspi_humidifier_control.py` |
| CT4_THRESHOLD | 240,000 | kW | Threshold aktivasi Cooling Tower 4 (240 MWe) | `raspi_humidifier_control.py` |
| CT_HYSTERESIS | 10,000 | kW | Hysteresis untuk CT (10 MWe) | `raspi_humidifier_control.py` |

### Konstanta Timing

| Konstanta | Nilai | Satuan | Penjelasan | Lokasi Kode |
|-----------|-------|--------|------------|-------------|
| ESP_LOOP_INTERVAL | ~10 | ms | Loop cycle ESP32 | `esp_utama_uart.ino: delay(10)` |
| SCRAM_ROD_DROP | 3.0 | detik | Durasi semua rod turun ke 0% | `raspi_main_panel.py:470` |
| SCRAM_ROD_UPDATE_RATE | 50 | ms | Update rate rod saat SCRAM | `raspi_main_panel.py:488` |
| TURBINE_SPINDOWN | 12.0 | detik | Durasi turbin berhenti | `raspi_main_panel.py:525` |
| TURBINE_SPINDOWN_RATE | 100 | ms | Update rate turbin saat spin-down | `raspi_main_panel.py:541` |
| INACTIVITY_TIMEOUT | 900 | detik | Auto-reset setelah 15 menit | `raspi_main_panel.py:174` |
| EMERGENCY_BEEP | 5.0 | detik | Durasi buzzer emergency | `raspi_buzzer_alarm.py` |

---

## Rumus & Algoritma yang Diimplementasikan

### 1. Daya Thermal Reaktor

**Lokasi**: `esp_utama_uart.ino` `calculateThermalPower()` (line 594–615)

```
INPUT:
  shim_actual     = posisi aktual rod shim (0-100%)
  regulating_actual = posisi aktual rod regulating (0-100%)

PROSES:
  avgRodPosition = (shim_actual + regulating_actual) / 2.0

  IF avgRodPosition > 10.0%:
    reactor_thermal_kw = avgRodPosition² × 90.0     ← komponen quadratic
                       + shim_actual × 150.0          ← kontribusi linear shim
                       + regulating_actual × 200.0    ← kontribusi linear regulating
    
    Cap: reactor_thermal_kw = min(reactor_thermal_kw, 900000.0)

  ELSE:
    reactor_thermal_kw = 0.0

OUTPUT (daya listrik):
  thermal_kw_calculated = reactor_thermal_kw × 0.34 × (power_level / 100.0)
  Cap: thermal_kw_calculated = clamp(thermal_kw_calculated, 0.0, 300000.0)
```

**Asal rumus**: Simplified educational model. Komponen quadratic (`rod² × 90`) mensimulasikan hubungan non-linear antara posisi rod dan reaktivitas. Komponen linear mensimulasikan kontribusi individual rod. Ini BUKAN neutron transport equation atau point kinetics — intentionally simplified.

**Contoh output**:
- Shim=50%, Reg=50%: avg=50, thermal = 50²×90 + 50×150 + 50×200 = 225,000 + 7,500 + 10,000 = 242,500 kW
- Shim=80%, Reg=80%: avg=80, thermal = 80²×90 + 80×150 + 80×200 = 576,000 + 12,000 + 16,000 = 604,000 kW
- Shim=100%, Reg=100%: avg=100, thermal = 100²×90 + 100×150 + 100×200 = 900,000 + 15,000 + 20,000 → capped 900,000 kW

### 2. Turbin State Machine

**Lokasi**: `esp_utama_uart.ino` `updateTurbineState()` (line 620–665)

```
STATE TRANSITIONS:
                    thermal_capacity > 50,000 kW
  ┌──────┐  ──────────────────────────────────▶  ┌───────────┐
  │ IDLE │                                        │ STARTING  │
  │ P=0% │  ◀──────────────────────────────────  │ P+=0.5%   │
  └──────┘     power_level ≤ 0%                   └─────┬─────┘
      ▲                                                  │ P ≥ 100%
      │                                                  ▼
  ┌──────────┐    thermal_capacity < 20,000 kW   ┌──────────┐
  │ SHUTDOWN │  ◀───────────────────────────────  │ RUNNING  │
  │ P-=1.0%  │                                    │ P=100%   │
  └──────────┘                                    └──────────┘

thermal_capacity dihitung ulang setiap loop:
  IF avgRodPosition > 10:
    thermal_capacity = avgRodPosition² × 90 + shim × 150 + reg × 200
```

**Timing**:
- IDLE → STARTING: Instant ketika thermal capacity > 50 MWth
- STARTING: power_level += 0.5% per 10ms loop → full power dalam ~2 detik (200 loops)
- RUNNING → SHUTDOWN: Instant ketika thermal capacity < 20 MWth
- SHUTDOWN: power_level -= 1.0% per 10ms loop → full stop dalam ~1 detik (100 loops)

### 3. Kecepatan Turbin (Motor Fisik)

**Lokasi**: `esp_utama_uart.ino` `updateTurbineSpeed()` (line 786–798)

```
turbine_speed = (shim_actual + regulating_actual) / 2.0

IF turbine_speed < 10.0:
    motor STOP (direction = 0)
    turbine_speed = 0
ELSE:
    motor FORWARD
    PWM = map(turbine_speed, 0-100, 0-255)
```

**Catatan**: `turbine_speed` langsung proporsional ke posisi rod average — BUKAN berdasarkan `power_level` dari FSM. Ini berarti motor fisik langsung merespons rod, tidak menunggu turbin "start" secara logical.

### 4. Pump Speed Ramping

**Lokasi**: `esp_utama_uart.ino` `updatePumpSpeeds()` (line 703–781)

```
STEP 1: Map command ke target speed
  cmd 0 (OFF)            → target = 0%
  cmd 1 (STARTING)       → target = 50%
  cmd 2 (ON)             → target = 100%
  cmd 3 (SHUTTING_DOWN)  → target = 20%

STEP 2: Gradual ramping
  IF actual < target:
    actual += 1.0 per loop (speed up: +1%/10ms = full ramp 0→100% dalam ~1 detik)
  IF actual > target:
    actual -= 2.0 per loop (slow down: -2%/10ms = full ramp 100→0% dalam ~0.5 detik)

STEP 3: PWM output
  pwm_value = map(actual, 0-100, 0-255)
  ledcWrite(motor_pin, pwm_value)
```

**Asimetri intentional**: Slow down (2%/loop) lebih cepat daripada speed up (1%/loop) untuk keselamatan — pompa harus bisa berhenti lebih cepat daripada start.

### 5. Cherenkov LED Brightness

**Lokasi**: `esp_utama_uart.ino` `updateCherenkovLED()` (line 804–822)

```
avg = (shim_actual + regulating_actual) / 2.0

IF avg < 0.5:
    brightness = 0 (LED off)
ELSE:
    pwm = map(avg, 0-100, 0-255)
    ledcWrite(LED_CHERENKOV, pwm)
```

### 6. Humidifier Staged Activation

**Lokasi**: `raspi_humidifier_control.py` class `HumidifierController`

```
STEAM GENERATOR (2 unit):
  IF shim_rod ≥ 40% AND regulating_rod ≥ 40%:
    SG1 = ON, SG2 = ON
  ELIF shim_rod < 35% OR regulating_rod < 35%:  (hysteresis 5%)
    SG1 = OFF, SG2 = OFF

COOLING TOWER (4 unit, staged):
  IF thermal_kw ≥ 60,000 kW:   CT1 = ON
  IF thermal_kw ≥ 120,000 kW:  CT2 = ON
  IF thermal_kw ≥ 180,000 kW:  CT3 = ON
  IF thermal_kw ≥ 240,000 kW:  CT4 = ON

  Hysteresis: 10,000 kW (off threshold = on threshold - 10,000)
  e.g., CT1 ON at 60,000 kW, OFF at 50,000 kW
```

### 7. SCRAM Sequence

**Lokasi**: `raspi_main_panel.py` `_execute_scram_sequence()` (line 438–511)

```
FASE 1 (0-3 detik, parallel): Rod Drop
  FOR t in 0..3 detik (update setiap 50ms):
    progress = t / 3.0    (0.0 → 1.0)
    safety_rod    = start_safety    × (1 - progress)
    shim_rod      = start_shim      × (1 - progress)
    regulating_rod = start_regulating × (1 - progress)
  END → semua rod = 0%

FASE 2 (0-12 detik, parallel): Turbine Spin-Down
  FOR t in 0..12 detik (update setiap 100ms):
    progress = t / 12.0
    turbine_speed = initial_speed × (1 - progress)  (linear deceleration)
  END → turbine_speed = 0%

FASE 3: Pompa tetap ON (decay heat removal)
FASE 4: Buzzer emergency 5 detik lalu berhenti otomatis
```

---

## State Variables Reaktor

Semua state disimpan dalam `PanelState` dataclass (`raspi_main_panel.py` line 73–122):

| Variabel | Tipe | Range | Default | Dimodifikasi Oleh |
|----------|------|-------|---------|-------------------|
| `pressure` | float | 0.0–200.0 bar | 0.0 | Button PRESSURE_UP/DOWN (+1/-1 bar) |
| `safety_rod` | int | 0–100 % | 0 | Button SAFETY_ROD_UP/DOWN (+1/-1 %) |
| `shim_rod` | int | 0–100 % | 0 | Button SHIM_ROD_UP/DOWN (+1/-1 %) |
| `regulating_rod` | int | 0–100 % | 0 | Button REG_ROD_UP/DOWN (+1/-1 %) |
| `pump_primary_status` | int | 0,1,2,3 | 0 | Button + timer (0→1→2, 2→3→0) |
| `pump_secondary_status` | int | 0,1,2,3 | 0 | Button + timer |
| `pump_tertiary_status` | int | 0,1,2,3 | 0 | Button + timer |
| `thermal_kw` | float | 0.0–300,000.0 kW | 0.0 | ESP-BC feedback (calculated) |
| `turbine_speed` | float | 0.0–100.0 % | 0.0 | ESP-BC feedback |
| `emergency_active` | bool | True/False | False | Emergency button / SCRAM |
| `interlock_satisfied` | bool | True/False | False | ControlLogic thread (computed) |
| `humid_ct1_cmd` | int | 0,1 | 0 | HumidifierController (computed) |
| `humid_ct2_cmd` | int | 0,1 | 0 | HumidifierController (computed) |
| `humid_ct3_cmd` | int | 0,1 | 0 | HumidifierController (computed) |
| `humid_ct4_cmd` | int | 0,1 | 0 | HumidifierController (computed) |
| `simulation_mode` | str | 'manual','auto' | 'manual' | START_AUTO button |
| `auto_sim_running` | bool | True/False | False | AutoSimulation thread |
| `auto_sim_phase` | str | free text | "" | AutoSimulation thread |
| `running` | bool | True/False | True | Shutdown signal |

State ESP-BC (di `esp_utama_uart.ino`, dikirim balik via UART):

| Variabel | Tipe | Range | Computed From |
|----------|------|-------|---------------|
| `safety_actual` | int | 0–100% | Smooth interpolation dari target |
| `shim_actual` | int | 0–100% | Smooth interpolation dari target |
| `regulating_actual` | int | 0–100% | Smooth interpolation dari target |
| `thermal_kw_calculated` | float | 0–300,000 kW | Formula thermal power |
| `power_level` | float | 0–100% | Turbine FSM |
| `current_state` | int | 0–3 | Turbine FSM (IDLE/STARTING/RUNNING/SHUTDOWN) |
| `turbine_speed` | float | 0–100% | Average rod positions |
| `pump_*_actual` | float | 0–100% | Gradual ramping |
| `cherenkov_brightness` | float | 0–100% | Average rod positions |

---

## Dinamika Temporal

### Update Frequencies

| Komponen | Interval | Timing Source | Catatan |
|----------|----------|---------------|---------|
| ESP-BC loop | ~10ms | `delay(10)` | Physics + actuator update |
| Button polling | 5ms | Raspi thread | GPIO read |
| Button hold repeat | 50ms | Raspi thread | Level detection repeat rate |
| Event processing | 10ms | Queue timeout | Button→action latency |
| Control logic | 50ms | Raspi thread | Interlock, humidifier, alarm |
| ESP UART comm | 50ms / immediate | Raspi thread + Event trigger | State sync |
| OLED display | 200ms | Raspi thread | With smooth interpolation |
| State JSON export | 100ms | Raspi thread | For video display |
| Main loop log | 1000ms | Main thread | Status output |
| Inactivity check | 10s | Control thread | Auto-reset timer |

### Rate of Change

| Parameter | Rate | Pemicu |
|-----------|------|--------|
| Tekanan | ±1 bar/press (50ms hold interval → ~20 bar/detik max) | Button PRESSURE_UP/DOWN |
| Rod position | ±1%/press (50ms hold interval → ~20%/detik max) | Button ROD_UP/DOWN |
| Pump speed (ESP) | +1%/10ms (speed up), -2%/10ms (slow down) | Automatic ramping |
| Turbin power_level | +0.5%/10ms (start), -1.0%/10ms (shutdown) | Turbine FSM |
| SCRAM rod drop | 100→0% dalam 3 detik (smooth) | Emergency button |
| Turbine spin-down | 100→0% dalam 12 detik (linear) | SCRAM sequence |
| Thermal power | Responds every 10ms loop | Follows rod position |

### Stability
- **Tekanan**: Manual-only control. Tidak ada feedback loop — hanya naik/turun via tombol. Stabil karena discrete.
- **Rod positions**: Discrete (integer 0-100). Servo smooth interpolation di ESP side.
- **Thermal power**: Instantaneous calculation (no delay, no inertia) — berubah langsung saat rod berubah.
- **Turbin**: FSM provides hysteresis (start at 50 MWth, stop at 20 MWth — gap 30 MWth prevents oscillation).
- **Humidifier**: Hysteresis (5% untuk SG, 10 MWe untuk CT) prevents relay flapping.

---

## Skenario Operasi

### Normal Startup (Manual Mode)

```
Phase 1: Pressurize
  → Tahan PRESSURE_UP sampai ≥ 140 bar (operasi) atau minimal 40 bar (pompa)

Phase 2: Start Pumps (urutan wajib!)
  → PUMP_TERTIARY_ON   (butuh P ≥ 40 bar)
  → Tunggu 2 detik (STARTING → ON)
  → PUMP_SECONDARY_ON  (butuh Tertiary ON)
  → Tunggu 2 detik
  → PUMP_PRIMARY_ON    (butuh Tertiary + Secondary ON)
  → Tunggu 2 detik

Phase 3: Withdraw Control Rods (butuh interlock: P ≥ 140, semua pompa ON)
  → SAFETY_ROD_UP sampai 100%
  → SHIM_ROD_UP sampai target (e.g., 80%)
  → REGULATING_ROD_UP sampai target (e.g., 80%)

Phase 4: Power Generation (otomatis)
  → Thermal power naik mengikuti formula quadratic
  → Turbin auto-start di 50 MWth
  → Humidifier SG auto-ON di shim ≥ 40% + reg ≥ 40%
  → CT1-4 auto-ON bertahap berdasarkan power level

Phase 5: Steady State
  → Fine-tune regulating rod untuk adjust power
  → Monitor tekanan (alarm di 160 bar, critical di 180 bar)
```

### Auto Simulation (8-Phase)

Diaktifkan via tombol START_AUTO (GPIO 17):

```
Phase 1: Init (3s delay)
Phase 2: Pressure to 45 bar (3s smooth ramp)
Phase 3: Pumps (Tertiary→Secondary→Primary, 3s each)
Phase 4: Pressure to 155 bar (5s smooth ramp)
Phase 5: Safety rod to 100% (smooth)
Phase 6: Shim rod to 80% (smooth)
Phase 7: Regulating rod to 80% (smooth)
Phase 8: Monitoring (wait for turbine auto-start, inactivity reset)
```

Lokasi: `raspi_main_panel.py` `auto_simulation_thread()` (line 1395+)

### Emergency SCRAM

```
Trigger: EMERGENCY button (GPIO 18)

1. emergency_active = True
2. All 3 rods drop: 3 detik smooth animation (parallel)
3. Turbine spin-down: 12 detik linear (parallel)
4. Buzzer: 5 detik emergency tone (4000 Hz)
5. Pumps: TETAP ON (decay heat removal)
6. Interlock: Mencegah rod movement (emergency_active == True)

Recovery: REACTOR_RESET button → semua parameter ke 0
```

### Normal Shutdown

Tidak ada dedicated "shutdown" prosedur — operator menurunkan rod secara manual:
```
1. Turunkan regulating rod ke 0% (REGULATING_ROD_DOWN)
2. Turunkan shim rod ke 0% (SHIM_ROD_DOWN)
3. Turunkan safety rod ke 0% (SAFETY_ROD_DOWN — guarded by rod hierarchy)
4. Turbin auto-shutdown di thermal < 20 MWth
5. Matikan pompa (reverse sequence recommended tapi not enforced)
6. Turunkan tekanan ke 0
```

### Inactivity Auto-Reset

```
Trigger: 15 menit (900 detik) tanpa button press
Action: Inject REACTOR_RESET event ke queue
Effect: Semua parameter ke 0, simulation mode ke manual
```

---

## Asumsi & Simplifikasi

### Hal yang Disederhanakan dari Fisika Nyata

1. **Tidak ada neutron kinetics**: Daya thermal langsung dihitung dari posisi rod (algebraic, bukan differential equation). Di PWR nyata, ada delayed neutrons, reactivity feedback, xenon poisoning, dll.

2. **Tidak ada thermal-hydraulics**: Tidak ada kalkulasi perpindahan panas, tidak ada boiling, tidak ada DNBR. Tekanan diatur manual (bukan dari kalkulasi steam generation).

3. **Tekanan manual-only**: Di PWR nyata, tekanan ditentukan oleh keseimbangan thermal-hydraulic. Di sini, operator menekan tombol naik/turun.

4. **Tidak ada temperature tracking**: Tidak ada variabel temperature coolant, fuel, cladding. Semua efek termal direpresentasikan oleh "thermal_kw" saja.

5. **Turbin simplified**: Turbin FSM hanya berdasarkan thermal capacity threshold, bukan actual steam conditions. Tidak ada steam generator model.

6. **Rod worth equal**: Semua rod (safety, shim, regulating) memiliki efek sama per persen posisi. Di PWR nyata, rod worth bervariasi per posisi (integral/differential rod worth curves).

7. **Instant thermal response**: Perubahan posisi rod langsung mempengaruhi thermal power. Di PWR nyata, ada time constant (delayed neutrons ~seconds, thermal ~minutes).

8. **Tidak ada decay heat**: Setelah SCRAM, thermal power langsung turun ke 0. Di PWR nyata, decay heat ~7% langsung setelah SCRAM, menurun perlahan selama berjam-jam.

9. **Pump cavitation simplified**: Hanya cek tekanan ≥ 40 bar. Di PWR nyata, cavitation tergantung NPSH, temperature, flow rate.

10. **Efisiensi turbin tetap**: 34% constant. Di PWR nyata, efisiensi bervariasi berdasarkan load, vacuum, steam conditions.

---

## Pengembangan Fisika Tambahan

### Dari Pengembangan yang Sudah Ada

1. **Staged Cooling Tower** (`raspi_humidifier_control.py`):
   - Menambah model manajemen kapasitas pendinginan bertahap
   - Parameter baru: CT1-4 thresholds, hysteresis values
   - Lebih realistis dari model "semua CT ON/OFF sekaligus"

2. **Cherenkov LED** (`esp_utama_uart.ino`):
   - Brightness ∝ rata-rata posisi rod → representasi visual tingkat radiasi
   - Threshold 0.5% → LED tidak menyala saat subcritical
   - Simplifikasi: di PWR nyata, Cherenkov tergantung flux neutron, bukan posisi rod

3. **Turbine FSM Hysteresis** (`esp_utama_uart.ino`):
   - Start threshold (50 MWth) ≠ stop threshold (20 MWth)
   - Gap 30 MWth mencegah oscillation on/off turbin
   - Realistis: turbin nyata memiliki minimum load requirement

4. **Pump Speed Ramping** (`esp_utama_uart.ino`):
   - Gradual speed change (bukan instant 0→100%)
   - Asimetri: speed up (+1%/loop) lebih lambat dari slow down (-2%/loop)
   - Simulasi inersia motor dan keselamatan

---

## Cara Menambah Parameter Baru

### Contoh: Menambah "Temperature Coolant" sebagai parameter simulasi

**Step 1: Tambah state variable** (`raspi_main_panel.py`)
```python
@dataclass
class PanelState:
    # ... existing fields ...
    coolant_temp: float = 25.0  # °C, default ambient
```

**Step 2: Tambah kalkulasi di ESP-BC** (`esp_utama_uart.ino`)
```cpp
float coolant_temp = 25.0;  // Default ambient

void calculateCoolantTemp() {
    // Simple model: temp rises with thermal power, drops with pump flow
    float heat_input = thermal_kw_calculated * 0.001;  // Scale factor
    float cooling = (pump_primary_actual / 100.0) * 50.0;  // Cooling rate
    coolant_temp = 25.0 + heat_input - cooling;
    coolant_temp = constrain(coolant_temp, 25.0, 350.0);
}
```

**Step 3: Tambah ke UART response** (`esp_utama_uart.ino`)
- Increment `UPDATE_RESP_LEN` by bytes needed (e.g., +4 for float32)
- Pack `coolant_temp` into response payload
- Update `raspi_uart_master.py` decoder to unpack new field

**Step 4: Update feedback loop** (`raspi_main_panel.py`)
```python
# Di esp_communication_thread():
self.state.coolant_temp = esp_data.coolant_temp
```

**Step 5: Tambah OLED display** (`raspi_oled_manager.py`)
- Tambah rendering untuk channel OLED baru
- Atau tambah ke display yang sudah ada

**Step 6: Tambah alarm** (`raspi_buzzer_alarm.py`)
```python
# Di check_alarms():
if state.coolant_temp >= 320.0:
    self.set_alarm(self.ALARM_TEMP_CRITICAL)
```

**Step 7: Tambah ke state export** — Otomatis via `asdict(self.state)` (dataclass auto-serializes)

⚠️ **PENTING**: Setiap perubahan UART payload HARUS di-update di KEDUA sisi (Python encoder/decoder + Arduino parser/builder) secara sinkron. Panjang payload (`UPDATE_CMD_LEN` / `UPDATE_RESP_LEN`) harus exact match.
