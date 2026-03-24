# Pengembangan 3: Implementasi LOFA (Loss of Flow Accident)

> **Status**: 📝 Planning  
> **Prioritas**: Medium (blocked by touchscreen panel)  
> **Dibuat**: 2026-03-24  
> **Dependency**: `01-touchscreen-panel.md` harus selesai terlebih dahulu

---

## 📋 Ringkasan

**Tujuan**: Menambahkan simulasi kondisi LOFA (Loss of Flow Accident) ke simulator PLTN untuk edukasi. LOFA terjadi ketika pompa pendingin gagal, menyebabkan akumulasi panas dan berpotensi kerusakan fuel.

**Fitur Utama**:
- Simulasi kegagalan pompa (primer, sekunder, tersier) dengan **respons berbeda**
- Model temperature sederhana untuk coolant dan fuel cladding
- Mitigasi otomatis (pressurizer relief valve, spray)
- Auto-SCRAM saat kondisi critical
- UI di touchscreen panel untuk memilih skenario LOFA

## 🔬 Koreksi Fisika PWR untuk Referensi

### Terminologi
- **FISI** (bukan FUSI) — Reaktor nuklir menggunakan reaksi fisi (pembelahan U-235)
- **LOFA** = Loss of Flow Accident (kegagalan aliran pendingin)

### Mekanisme Pressurizer
| Kondisi | Aksi Pressurizer |
|---------|------------------|
| Tekanan tinggi | Relief valve BUKA → lepas steam |
| Tekanan rendah | Heater ON → panaskan air |
| Suhu tinggi | Spray nozzle aktif → kondensasi |

### Dampak LOFA per Loop
| Loop | Kegagalan | Dampak | Severitas |
|------|-----------|--------|-----------|
| **Primer** | Pompa primer mati | Core overheating, fuel damage risk | ⚠️ KRITIS |
| **Sekunder** | Pompa sekunder mati | Heat sink hilang, primer overpressure | ⚠️ TINGGI |
| **Tersier** | Pompa tersier mati | Kondenser tidak efektif, turbin shutdown | ⚡ SEDANG |

## 🎯 Keputusan Teknis

### ✅ Respons Berbeda per Pompa

**Alasan**: Nilai edukasi tinggi — mengajarkan bahwa tidak semua kegagalan sama dan ada respons proporsional.

| Loop | Alarm | Temp Rise | Auto-SCRAM | Turbin |
|------|-------|-----------|------------|--------|
| **Primer** | CRITICAL (3500 Hz) | CEPAT | Ya (fuel >900°C) | Tetap jalan |
| **Sekunder** | WARNING → CRITICAL | SEDANG | Ya (dengan delay) | Auto shutdown |
| **Tersier** | WARNING saja | LAMBAT | Tidak (kecuali prolonged) | Auto shutdown |

### ✅ Temperature Model di Python

**Alasan**: Simpler, no ESP firmware changes, easier to tune untuk edukasi.

- Linear temperature rise (bukan eksponensial)
- Fixed cooling rate dari pressurizer spray
- Instant SCRAM effect

### ✅ UI di Touchscreen Panel

**Alasan**: Touchscreen sudah direncanakan, LOFA akan menggunakan UI tersebut untuk:
- Tombol "SIMULASI LOFA"
- Dialog pemilihan pompa (Primer/Sekunder/Tersier)
- Temperature display indicators

## 📐 State Variables Baru

```python
# Temperature modeling
coolant_temp_primary: float = 290.0      # °C
coolant_temp_secondary: float = 250.0    # °C
condenser_pressure: float = 0.05         # bar
fuel_cladding_temp: float = 400.0        # °C

# LOFA status
lofa_primary: bool = False
lofa_secondary: bool = False
lofa_tertiary: bool = False

# Pressurizer mitigation
pressurizer_relief_open: bool = False
pressurizer_spray_active: bool = False

# Simulation control
lofa_simulation_active: bool = False
lofa_simulation_target: str = ""
```

## 🛠️ Konstanta Baru

```python
# Temperature thresholds (°C)
TEMP_COOLANT_NORMAL = 290.0
TEMP_COOLANT_WARNING = 340.0
TEMP_COOLANT_CRITICAL = 360.0
TEMP_COOLANT_SCRAM = 380.0

TEMP_FUEL_NORMAL = 400.0
TEMP_FUEL_WARNING = 600.0
TEMP_FUEL_CRITICAL = 800.0
TEMP_FUEL_SCRAM = 900.0

# Rise rates per 100ms (berbeda per pompa)
TEMP_RISE_RATE_PRIMARY = 5.0   # Cepat
TEMP_RISE_RATE_SECONDARY = 2.0 # Sedang
TEMP_RISE_RATE_TERTIARY = 0.5  # Lambat

# Mitigation rates
RELIEF_VALVE_RATE = 2.0        # bar per 100ms
SPRAY_COOLING_RATE = 3.0       # °C per 100ms
```

## 📁 Files yang Dimodifikasi

| File | Perubahan |
|------|-----------|
| `raspi_config.py` | Tambah konstanta temperature & LOFA |
| `raspi_main_panel.py` | Extend PanelState, LOFA detection, mitigation, auto-SCRAM |
| `raspi_buzzer_alarm.py` | Tambah alarm tones LOFA |
| `touch_panel/touch_panel_app.py` | Tombol SIMULASI LOFA, dialog pemilihan |
| `video_display_app.py` | Temperature readout, LOFA indicators |
| `.claude/skills/safety-logic.md` | Dokumentasi LOFA logic |

## 📋 Task Breakdown

### Phase 1: State & Config (Blocked by Touchscreen)
| ID | Task | Status |
|----|------|--------|
| LOFA-001 | Extend PanelState dengan temperature & LOFA vars | Blocked |
| LOFA-002 | Tambah konstanta threshold di raspi_config.py | Blocked |

### Phase 2: Core Logic
| ID | Task | Status |
|----|------|--------|
| LOFA-010 | LOFA detection di control_logic_thread | Blocked |
| LOFA-011 | Temperature model per pompa | Blocked |
| LOFA-012 | Pressurizer relief/spray mitigation | Blocked |
| LOFA-013 | Auto-SCRAM dengan kondisi berbeda | Blocked |

### Phase 3: Alarms & UI
| ID | Task | Status |
|----|------|--------|
| LOFA-020 | Alarm tones LOFA di buzzer | Blocked |
| LOFA-021 | Tombol SIMULASI LOFA di touchscreen | Blocked |
| LOFA-022 | Dialog pemilihan pompa | Blocked |
| LOFA-023 | Temperature readout di video_display | Blocked |
| LOFA-024 | Visual indicators LOFA | Blocked |

### Phase 4: Testing & Docs
| ID | Task | Status |
|----|------|--------|
| LOFA-030 | Test LOFA primer scenario | Blocked |
| LOFA-031 | Test LOFA sekunder scenario | Blocked |
| LOFA-032 | Test LOFA tersier scenario | Blocked |
| LOFA-033 | Test pressurizer mitigation | Blocked |
| LOFA-040 | Update safety-logic.md | Blocked |
| LOFA-041 | Update pltn-domain-knowledge.md | Blocked |

## 🚧 Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| Temperature model tidak realistis | Edukasi kurang akurat | Review dengan dosen fisika reaktor |
| Auto-SCRAM terlalu sensitif | Demo terganggu | Tuning threshold, tambah hysteresis |
| Alarm terlalu banyak | Noise | Priority system, mute option |

## 📅 Urutan Pengerjaan

1. **Touchscreen Panel harus selesai dulu** (blocking)
2. State & config
3. Core logic (sequential: detection → temp model → mitigation → SCRAM)
4. UI & alarms (parallel setelah detection)
5. Testing semua scenario
6. Dokumentasi

**Lihat beads untuk tracking**: `bd list`

---

*Terakhir diupdate: 2026-03-24*
