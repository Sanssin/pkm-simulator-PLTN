---
name: Safety-Systems-SCRAM-Logic
description: SCRAM, alarms, interlocks, safety thresholds
---

# Skill: Safety Systems & SCRAM Logic

> ⚠️ Skill ini berhubungan dengan safety-critical code.
> Setiap saran perubahan harus diverifikasi sangat teliti.
> Jangan pernah memodifikasi logika di bagian ini tanpa review manusia.

## Arsitektur Sistem Keselamatan

Sistem keselamatan simulator PLTN diimplementasikan di **3 layer**:

```
Layer 1: PREVENTION (Interlock & Sequence Enforcement)
├─ Rod movement interlock     → raspi_main_panel.py _check_interlock_internal()
├─ Pump startup sequence      → raspi_main_panel.py _check_pump_start_safe()
├─ Safety rod priority        → raspi_main_panel.py process_button_event()
└─ Safety rod guard           → raspi_main_panel.py process_button_event()

Layer 2: WARNING (Alarm System)
├─ Pressure warning (≥160)    → raspi_buzzer_alarm.py check_alarms()
├─ Pressure critical (≥180)   → raspi_buzzer_alarm.py check_alarms()
├─ Procedure violation        → raspi_buzzer_alarm.py sound_procedure_warning()
└─ Interlock violation        → raspi_buzzer_alarm.py sound_interlock_warning()

Layer 3: PROTECTION (SCRAM & Emergency)
├─ Manual SCRAM button        → raspi_main_panel.py process_button_event() EMERGENCY
├─ SCRAM rod drop sequence    → raspi_main_panel.py _execute_scram_sequence()
├─ Turbine spin-down          → raspi_main_panel.py _turbine_spindown()
└─ Emergency buzzer (timed)   → raspi_buzzer_alarm.py trigger_emergency_beep()
```

**Tidak ada automatic SCRAM** — SCRAM hanya bisa dipicu manual oleh operator via tombol EMERGENCY (GPIO 18). Ini adalah simplifikasi edukasi; PWR nyata memiliki banyak automatic SCRAM triggers.

> 📝 **Planned Update (LOFA-040)**: Automatic SCRAM akan ditambahkan sebagai bagian dari fitur LOFA Simulation. Auto-SCRAM akan trigger saat:
> - Fuel cladding temp > 900°C
> - Coolant temp > 380°C
> - Lihat `docs/development/03-lofa-simulation.md` untuk detail.

**File-file safety-critical** (🚫 jangan ubah tanpa review):
- `raspi_main_panel.py` lines 438–511 (SCRAM), 560–796 (event processing), 867–1004 (interlock)
- `raspi_buzzer_alarm.py` (seluruh file — 337 lines)
- `esp_utama_uart.ino` lines 594–665 (thermal power + turbine FSM)

---

## SCRAM Logic — Detail Lengkap

### Trigger

```python
# raspi_main_panel.py — process_button_event(), line 728-747
elif event == ButtonEvent.EMERGENCY:
    self.state.emergency_active = True
    logger.critical("EMERGENCY SCRAM ACTIVATED!")
    logger.critical("   Pumps remain ON for decay heat removal")
    self._execute_scram_sequence()

    if self.buzzer:
        self.buzzer.trigger_emergency_beep()  # 5 detik, non-blocking
```

Satu-satunya trigger: **Tombol EMERGENCY** (GPIO 18, edge detection).
Tidak ada automatic SCRAM dari pressure, temperature, atau kondisi lain.

### Sequence Detail

**Fase 1: Rod Drop (3 detik, smooth animation)**

```python
# raspi_main_panel.py — _execute_scram_sequence(), line 438-511
def scram_thread():
    start_safety = self.state.safety_rod
    start_shim = self.state.shim_rod
    start_regulating = self.state.regulating_rod

    start_time = time.time()
    duration = 3.0  # 3 detik total

    while time.time() - start_time < duration:
        elapsed = time.time() - start_time
        progress = elapsed / duration  # 0.0 → 1.0

        current_safety = int(start_safety * (1 - progress))
        current_shim = int(start_shim * (1 - progress))
        current_regulating = int(start_regulating * (1 - progress))

        with self.state_lock:
            self.state.safety_rod = max(0, current_safety)
            self.state.shim_rod = max(0, current_shim)
            self.state.regulating_rod = max(0, current_regulating)

        self.esp_send_immediate.set()  # Trigger UART update
        time.sleep(0.05)  # 50ms update rate = smooth animation

    # Ensure final = 0
    with self.state_lock:
        self.state.safety_rod = 0
        self.state.shim_rod = 0
        self.state.regulating_rod = 0
```

Karakteristik:
- Semua 3 rod turun **bersamaan** (bukan sequential)
- Linear descent: `position = start × (1 - elapsed/3.0)`
- Update rate 50ms = 60 step dalam 3 detik = smooth visual
- Runs in **separate daemon thread** (non-blocking)

**Fase 2: Turbine Spin-Down (12 detik, parallel)**

```python
# raspi_main_panel.py — _turbine_spindown(), line 513-553
def _turbine_spindown(self, initial_speed):
    duration = 12.0
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed >= duration:
            break

        progress = elapsed / duration
        current_speed = initial_speed * (1 - progress)  # Linear deceleration

        with self.state_lock:
            self.state.turbine_speed = max(0, current_speed)

        self.esp_send_immediate.set()
        time.sleep(0.1)  # 100ms update rate

    with self.state_lock:
        self.state.turbine_speed = 0
```

Karakteristik:
- **Dimulai paralel** dengan rod drop (bukan setelah rod selesai)
- Linear deceleration: `speed = initial × (1 - elapsed/12.0)`
- Runs in separate daemon thread
- 12 detik >> 3 detik rod drop → turbin masih berputar setelah rod inserted

**Fase 3: Pompa tetap ON**

```python
# Tidak ada kode yang mematikan pompa saat SCRAM
# Ini intentional: pompa harus tetap jalan untuk decay heat removal
```

**Fase 4: Emergency Buzzer (5 detik)**

```python
# raspi_buzzer_alarm.py — trigger_emergency_beep(), line 222-251
def trigger_emergency_beep(self, duration=5.0):
    def beep_for_duration():
        self.emergency_beep_active = True    # Protect from check_alarms() clearing
        self.set_alarm(self.ALARM_EMERGENCY)  # 4000 Hz, rapid 0.1s beep
        time.sleep(duration)                  # 5 detik
        self.emergency_beep_active = False    # Release protection
        self.clear_alarm()                    # Auto-stop

    threading.Thread(target=beep_for_duration, daemon=True).start()
```

Karakteristik:
- `emergency_beep_active` flag **melindungi** dari `check_alarms()` yang bisa clear alarm
- Auto-stop setelah 5 detik (bukan continuous)
- Non-blocking (daemon thread)

### Recovery

```python
# raspi_main_panel.py — process_button_event() REACTOR_RESET, line 749-778
elif event == ButtonEvent.REACTOR_RESET:
    self.state.auto_sim_running = False
    self.state.simulation_mode = 'manual'
    self.state.emergency_active = False       # ← Clears emergency flag
    self.state.pressure = 0.0
    self.state.thermal_kw = 0.0
    self.state.pump_primary_status = 0        # All pumps OFF
    self.state.pump_secondary_status = 0
    self.state.pump_tertiary_status = 0
    self.state.safety_rod = 0                 # All rods at 0%
    self.state.shim_rod = 0
    self.state.regulating_rod = 0
    self.state.humid_ct1_cmd = 0              # All humidifiers OFF
    # ... etc
    self.state.interlock_satisfied = False
```

Recovery HANYA via **REACTOR_RESET** button (GPIO 27). Full reset semua parameter ke 0.

---

## Semua Alarm Thresholds

| Parameter | Warning | Critical/SCRAM | Aksi | Lokasi Kode |
|-----------|---------|---------------|------|-------------|
| Tekanan | ≥ 160 bar | ≥ 180 bar | Buzzer 2500 Hz / 3000 Hz | `raspi_buzzer_alarm.py:210-217` |
| Tekanan (pompa) | < 40 bar saat start pump | — | Buzzer 2000 Hz, tolak start | `raspi_main_panel.py:933` |
| Tekanan (interlock) | < 140 bar | — | Tolak rod movement | `raspi_main_panel.py:892` |
| Pump sequence | Wrong order | — | Buzzer 2000 Hz, tolak start | `raspi_main_panel.py:952-999` |
| Rod interlock | Not satisfied | — | Buzzer 1500 Hz, tolak movement | `raspi_main_panel.py:616-628` |
| Safety rod priority | < 100% saat raise shim/reg | — | Buzzer 1500 Hz, tolak raise | `raspi_main_panel.py:652-664` |
| Safety rod guard | Lower below shim/reg | — | Buzzer 1500 Hz, tolak lower | `raspi_main_panel.py:634-645` |
| Emergency | Manual button | — | SCRAM + Buzzer 4000 Hz (5s) | `raspi_main_panel.py:728-747` |

### Alarm Priority (dalam `check_alarms()`)

```python
# raspi_buzzer_alarm.py — check_alarms(), line 187-220
# Priority order (highest first, only one alarm at a time):

# 1. Emergency beep active → DO NOT TOUCH (protected)
if self.emergency_beep_active:
    return

# 2. Pressure CRITICAL ≥ 180 bar → ALARM_PRESSURE_CRITICAL (3000 Hz)
if state.pressure >= 180.0:
    self.set_alarm(self.ALARM_PRESSURE_CRITICAL)
    return

# 3. Pressure WARNING ≥ 160 bar → ALARM_PRESSURE_WARNING (2500 Hz)
if state.pressure >= 160.0:
    self.set_alarm(self.ALARM_PRESSURE_WARNING)
    return

# 4. All clear → Silent
self.clear_alarm()
```

**Catatan penting**: `check_alarms()` dipanggil setiap 50ms dari `ControlLogic` thread. Alarm procedure warning dan interlock violation dipicu langsung dari event processing (bukan dari `check_alarms()`).

### Detail Alarm Tones

| Alarm Type | Konstanta | Freq | Pattern | Durasi Default |
|-----------|-----------|------|---------|---------------|
| Silent | `ALARM_NONE = 0` | 0 | — | — |
| Procedure Warning | `ALARM_PROCEDURE_WARNING = 1` | 2000 Hz | 0.3s on, 0.3s off | 2.0s (timed) |
| Pressure Warning | `ALARM_PRESSURE_WARNING = 2` | 2500 Hz | 0.5s on, 0.5s off | Continuous |
| Pressure Critical | `ALARM_PRESSURE_CRITICAL = 3` | 3000 Hz | 0.2s, 0.2s, 0.2s, 0.6s (double beep) | Continuous |
| Emergency SCRAM | `ALARM_EMERGENCY = 4` | 4000 Hz | 0.1s on, 0.1s off (rapid) | 5.0s (timed) |
| Interlock Violation | `ALARM_INTERLOCK = 5` | 1500 Hz | 0.2s on, 0.8s off | 1.5s (timed) |

---

## Interlock Dependencies

### Rod Movement Interlock Map

```
                  ┌─ Pressure ≥ 140 bar? ──── NO → BLOCK (buzzer 1500 Hz)
                  │
Rod UP request ───┼─ Emergency active? ──── YES → BLOCK
                  │
                  ├─ Primary pump ON (==2)? ── NO → BLOCK
                  ├─ Secondary pump ON (==2)? ─ NO → BLOCK
                  └─ Tertiary pump ON (==2)? ── NO → BLOCK
                  │
                  └─ ALL YES → CHECK ROD HIERARCHY
```

### Rod Hierarchy Map

```
Safety Rod UP:    Interlock check only (no hierarchy constraint upward)
Safety Rod DOWN:  BLOCKED if new_pos < shim_rod OR new_pos < regulating_rod

Shim Rod UP:      BLOCKED if safety_rod < 100% (must be fully withdrawn first)
Shim Rod DOWN:    No interlock check (always allowed)

Regulating UP:    BLOCKED if safety_rod < 100% (must be fully withdrawn first)
Regulating DOWN:  No interlock check (always allowed)
```

**Implikasi**: Rod TURUN (insertion = menuju subcritical) **selalu diizinkan** untuk shim dan regulating — ini fail-safe. Yang di-block adalah rod NAIK (withdrawal = menuju critical) tanpa kondisi terpenuhi.

### Pump Startup Sequence Map

```
                          ┌─ Pressure ≥ 40 bar? ── NO → BLOCK (buzzer 2000 Hz)
                          │
Tertiary Pump ON ─────────┤
                          └─ YES → ALLOWED (no prerequisites)

                          ┌─ Pressure ≥ 40 bar? ── NO → BLOCK
                          │
Secondary Pump ON ────────┼─ Tertiary ON (==2)? ── NO → BLOCK (buzzer 2000 Hz)
                          │
                          └─ YES → ALLOWED

                          ┌─ Pressure ≥ 40 bar? ── NO → BLOCK
                          │
Primary Pump ON ──────────┼─ Tertiary ON (==2)? ── NO → BLOCK
                          │
                          ├─ Secondary ON (==2)? ── NO → BLOCK (buzzer 2000 Hz)
                          │
                          └─ YES → ALLOWED
```

**Catatan**: Pump OFF (shutdown) **selalu diizinkan** — tidak ada sequence check untuk mematikan pompa. Ini intentional: operator harus bisa mematikan pompa kapan saja.

### Cross-System Dependencies

```
Pressure ──affects──→ Pump start permission (≥40 bar)
Pressure ──affects──→ Rod movement permission (≥140 bar)
Pressure ──triggers──→ Alarm warning (≥160 bar) / critical (≥180 bar)

Pumps ────affects──→ Rod movement permission (all 3 must be ON)
Pumps ────affected_by──→ SCRAM (pumps stay ON for decay heat)

Rods ─────affects──→ Thermal power (quadratic formula in ESP-BC)
Rods ─────affects──→ Turbine speed (avg rod → motor PWM)
Rods ─────affects──→ Cherenkov LED brightness
Rods ─────affects──→ Steam Generator humidifier (shim≥40% + reg≥40%)

Thermal ──affects──→ Turbine FSM (start at 50 MWth, stop at 20 MWth)
Thermal ──affects──→ Cooling Tower staged activation (CT1-4)
Thermal ──affects──→ ESP-E LED brightness (power indicator)

Emergency ─sets───→ emergency_active flag
Emergency ─triggers→ SCRAM sequence (rod drop + turbine spin-down)
Emergency ─blocks──→ ALL rod movement (via interlock check)
Reset ─────clears──→ emergency_active + semua parameter ke 0
```

---

## Fail-Safe States

| Komponen | Default State | Fail-Safe Behavior | Lokasi Kode |
|----------|-------------|-------------------|-------------|
| Control Rods | 0% (fully inserted) | Rods in = reactor subcritical | `PanelState` default values |
| Tekanan | 0.0 bar | No pressure = no pump start | `PanelState.pressure = 0.0` |
| Pompa | OFF (status=0) | No forced circulation | `PanelState.pump_*_status = 0` |
| Turbin | IDLE, power=0% | No power generation | `TurbineState = STATE_IDLE` |
| Humidifier | OFF (cmd=0) | No cooling (not needed at 0 power) | `PanelState.humid_*_cmd = 0` |
| Emergency flag | False | Tapi interlock tetap mencegah tanpa kondisi | `PanelState.emergency_active = False` |
| Interlock | Not satisfied | Rod movement blocked by default | `PanelState.interlock_satisfied = False` |
| Buzzer | Silent | No alarm | `BuzzerAlarm.current_alarm = ALARM_NONE` |
| Cherenkov LED | OFF | No radiation visualization | ESP-BC `cherenkov_brightness = 0` |
| Relay (CT) | HIGH (inactive) | Active LOW relay → default OFF | ESP-BC `digitalWrite(RELAY, HIGH)` |
| Servo | 0° | Rod fully inserted | ESP-BC `servo.write(0)` |
| Motor | PWM 0 | Pump/turbine stopped | ESP-BC `ledcWrite(pin, 0)` |

**Catatan penting**: Relay menggunakan **active LOW** logic. `digitalWrite(pin, HIGH)` = relay OFF, `digitalWrite(pin, LOW)` = relay ON. Ini adalah standar industri untuk relay module — relay default OFF saat power loss.

---

## Pengembangan Safety Tambahan

### Safety Rod Shutdown Fix (commit `13f5c8c`)
- **Masalah**: Safety rod bisa diturunkan di bawah posisi shim/regulating
- **Perbaikan**: Guard check `new_pos < shim_rod || new_pos < regulating_rod`
- **Lokasi**: `raspi_main_panel.py` line 633-645
- **Efek**: Operator harus turunkan shim/regulating terlebih dahulu sebelum safety rod

### Emergency Beep Protection (di `raspi_buzzer_alarm.py`)
- **Masalah**: `check_alarms()` bisa clear emergency buzzer sebelum 5 detik
- **Perbaikan**: `emergency_beep_active` flag yang mencegah `check_alarms()` mengubah alarm
- **Lokasi**: `raspi_buzzer_alarm.py` line 206-207, 236-243

### Inactivity Auto-Reset (commit `e055160`)
- **Fungsi**: Reset simulator setelah 15 menit tanpa button press
- **Safety relevance**: Mencegah simulator tertinggal dalam state berbahaya saat demo
- **Lokasi**: `raspi_main_panel.py` line 1073-1105

---

## Checklist Sebelum Modifikasi Safety Code

### Sebelum Coding

- [ ] Baca SEMUA interlock conditions di `_check_interlock_internal()` (line 867-914)
- [ ] Baca SEMUA pump sequence checks di `_check_pump_start_safe()` (line 916-1004)
- [ ] Baca SCRAM sequence di `_execute_scram_sequence()` (line 438-511)
- [ ] Baca alarm priority di `check_alarms()` (line 187-220)
- [ ] Identifikasi SEMUA caller dari fungsi yang akan diubah (grep untuk nama fungsi)
- [ ] Pahami thread mana yang memanggil kode ini dan lock apa yang digunakan
- [ ] Verifikasi bahwa perubahan tidak mengubah fail-safe defaults

### Selama Coding

- [ ] JANGAN ubah threshold tanpa justifikasi tertulis
- [ ] JANGAN hapus interlock check — hanya tambah jika perlu
- [ ] JANGAN ubah lock ordering (`state_lock` sebelum `uart_lock`)
- [ ] Pastikan rod DOWN (insertion) selalu diizinkan untuk shim/regulating
- [ ] Pastikan pump OFF selalu diizinkan
- [ ] Jika menambah alarm baru, tentukan priority relative terhadap yang ada
- [ ] Jika mengubah UART payload, update KEDUA sisi (Python + Arduino)

### Setelah Coding

- [ ] Verifikasi interlock masih mencegah rod movement tanpa kondisi terpenuhi
- [ ] Verifikasi SCRAM masih menjatuhkan semua rod ke 0%
- [ ] Verifikasi pump sequence masih enforced (Tertiary → Secondary → Primary)
- [ ] Verifikasi safety rod priority (harus 100% sebelum shim/reg naik)
- [ ] Verifikasi safety rod guard (tidak boleh turun di bawah shim/reg)
- [ ] Verifikasi alarm priority (emergency > critical > warning > none)
- [ ] Verifikasi emergency beep protection masih berfungsi
- [ ] Test: Tekan EMERGENCY → semua rod harus turun, buzzer 5 detik
- [ ] Test: Tekan RESET → semua parameter harus ke 0

---

## Anti-Patterns

### 🚫 JANGAN: Ubah alarm di dalam state_lock

```python
# SALAH — alarm thread bisa deadlock dengan state_lock
with self.state_lock:
    self.buzzer.set_alarm(...)  # ← alarm_lock di dalam state_lock!
```

```python
# BENAR — alarm di luar state_lock, atau gunakan convenience method
if self.buzzer:
    try:
        self.buzzer.sound_interlock_warning(duration=1.5)
    except Exception:
        pass
```

### 🚫 JANGAN: Bypass interlock di process_button_event()

```python
# SALAH — langsung set rod tanpa interlock check
elif event == ButtonEvent.SHIM_ROD_UP:
    self.state.shim_rod = min(self.state.shim_rod + 1, 100)  # ← NO INTERLOCK!
```

```python
# BENAR — selalu cek safety rod priority + interlock
elif event == ButtonEvent.SHIM_ROD_UP:
    if self.state.safety_rod < 100:
        # buzzer warning + return
        return
    if not self._check_interlock_internal():
        # buzzer warning + return
        return
    self.state.shim_rod = min(self.state.shim_rod + 1, 100)
```

### 🚫 JANGAN: Matikan pompa saat SCRAM

```python
# SALAH — pompa harus tetap ON untuk decay heat removal
def _execute_scram_sequence(self):
    self.state.pump_primary_status = 0    # ← BERBAHAYA!
    self.state.pump_secondary_status = 0  # ← Decay heat tidak dibuang!
```

### 🚫 JANGAN: Gunakan continuous alarm untuk emergency

```python
# SALAH — alarm continuous tidak akan berhenti
self.buzzer.set_alarm(self.ALARM_EMERGENCY)  # ← Never stops!
```

```python
# BENAR — gunakan timed beep
self.buzzer.trigger_emergency_beep(duration=5.0)  # ← Auto-stops after 5s
```

### 🚫 JANGAN: Clear emergency_active tanpa full reset

```python
# SALAH — hanya clear flag tanpa reset parameter lain
self.state.emergency_active = False  # ← Rods masih di 0%, state inconsistent!
```

```python
# BENAR — gunakan REACTOR_RESET yang reset SEMUA parameter
self.button_event_queue.put(ButtonEvent.REACTOR_RESET)
```

### 🚫 JANGAN: Tambah automatic SCRAM tanpa hysteresis

```python
# SALAH — bisa oscillate jika pressure fluctuates di threshold
if state.pressure >= 190:
    self._execute_scram_sequence()  # ← Triggered every 50ms!
```

```python
# BENAR — gunakan flag atau one-shot mechanism
if state.pressure >= 190 and not self.state.emergency_active:
    self.state.emergency_active = True
    self._execute_scram_sequence()  # ← Only once
```
