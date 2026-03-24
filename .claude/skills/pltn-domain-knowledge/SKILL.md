# Skill: PLTN Domain Knowledge — Konteks Edukasi

## Jenis Reaktor yang Disimulasikan

**PWR — Pressurized Water Reactor** (Reaktor Air Bertekanan)

PWR adalah tipe reaktor nuklir komersial yang paling umum di dunia (~65% dari seluruh reaktor). Simulator ini memodelkan PWR sederhana untuk tujuan edukasi mahasiswa teknik nuklir dalam kompetisi **PKM (Program Kreativitas Mahasiswa) 2024**.

**Level simulasi**: Simplified educational model — bukan simulator grade engineering. Parameter dan rumus telah disederhanakan agar bisa berjalan real-time di ESP32 dan dipahami oleh mahasiswa.

---

## Komponen PLTN yang Dimodelkan

### Reactor Core
```
┌──────────────────────────────┐
│        REACTOR CORE          │
│                              │
│   ┌────┐ ┌────┐ ┌────┐     │
│   │Safe│ │Shim│ │Reg │     │  ← 3 Control Rod Groups
│   │Rod │ │Rod │ │Rod │     │    (Servo motors 0-180°)
│   └──┬─┘ └──┬─┘ └──┬─┘     │
│      ▼      ▼      ▼       │
│   ═══════════════════════   │  ← Fuel Assemblies (abstracted)
│   ═══════════════════════   │
│                              │
│   💡 Cherenkov LED          │  ← Blue LED ∝ rod position
│                              │
└──────────────────────────────┘
```

- **3 kelompok batang kendali**: Safety, Shim, Regulating (masing-masing 1 servo motor)
- **Posisi rod**: 0% (fully inserted, subcritical) – 100% (fully withdrawn, supercritical)
- **Cherenkov radiation**: Visualisasi dengan LED biru, brightness ∝ avg rod position

### Sistem Pendingin (3 Loop)
```
Primary Loop ──→ Steam Generator ──→ Secondary Loop ──→ Condenser ──→ Tertiary Loop
(Pompa 1)        (Humidifier SG)     (Pompa 2)          (Turbin)      (Pompa 3)
                                                                        ↓
                                                           Cooling Tower (CT1-4)
                                                           (Humidifier units)
```

- **3 pompa sirkulasi**: Primary, Secondary, Tertiary (masing-masing 1 DC motor via L298N)
- **Sequence wajib**: Tertiary → Secondary → Primary (safety interlock)
- **Steam Generator**: 2 unit humidifier (SG1+SG2), aktif saat rod ≥ 40%
- **Cooling Tower**: 4 unit staged (CT1-CT4), aktivasi bertahap berdasarkan power level

### Pressurizer
- **Fungsi**: Menjaga tekanan sistem pendingin primer
- **Range simulasi**: 0 – 200 bar
- **Kontrol**: Manual (tombol UP/DOWN, ±1 bar per press)
- **Threshold operasi**: 40 bar (min pump), 140 bar (interlock), 150 bar (normal), 160 bar (warning), 180 bar (critical)

### Turbin & Generator
- **Turbin**: Dimodelkan sebagai FSM (Finite State Machine) — IDLE/STARTING/RUNNING/SHUTDOWN
- **Generator**: Daya listrik = thermal × efisiensi (0.34)
- **Trigger**: Otomatis start saat thermal > 50 MWth, stop saat < 20 MWth
- **Representasi fisik**: 1 DC motor (L298N) dengan speed ∝ avg rod position

---

## Siklus Operasi Normal

### Startup Sequence (Manual atau Auto)

```
Phase 1: PRESSURIZATION
├─ Naikkan tekanan ke ≥ 140 bar (via tombol PRESSURE_UP)
├─ Tunggu stabilisasi

Phase 2: PUMP STARTUP (sequence: Tertiary → Secondary → Primary)
├─ Start Tertiary pump (butuh P ≥ 40 bar)
├─ Tunggu status ON (2 detik)
├─ Start Secondary pump (butuh Tertiary ON)
├─ Tunggu status ON (2 detik)
├─ Start Primary pump (butuh Tertiary + Secondary ON)
├─ Tunggu status ON (2 detik)

Phase 3: ROD WITHDRAWAL (interlock harus satisfied: P≥140, all pumps ON)
├─ Tarik Safety Rod ke 100% (harus penuh sebelum rod lain)
├─ Naikkan Shim Rod bertahap (0→40→60→80→100%)
├─ Naikkan Regulating Rod bertahap (0→40→60→80→100%)
├─ Saat rod ≥ 40%: Steam Generator aktif → humidifier menyala

Phase 4: POWER ASCENSION
├─ Thermal power naik (quadratic + linear dari rod position)
├─ Saat thermal > 50 MWth: Turbine starts (auto FSM)
├─ Cooling Tower stages activate:
│   CT1 @ 60 MWe, CT2 @ 120 MWe, CT3 @ 180 MWe, CT4 @ 240 MWe
├─ Generator output: electrical = thermal × 0.34

Phase 5: FULL POWER
├─ All rods at 100%
├─ Thermal ≈ 900 MWth, Electrical ≈ 300 MWe
├─ All 4 CT units active
├─ Turbine RUNNING at 100%
```

### Normal Shutdown

```
Phase 1: POWER REDUCTION
├─ Turunkan Regulating Rod bertahap
├─ Turunkan Shim Rod bertahap
├─ Thermal power berkurang
├─ CT stages deactivate saat power turun

Phase 2: ROD INSERTION
├─ Semua rod ke 0%
├─ Turbine auto-shutdown (thermal < 20 MWth)

Phase 3: PUMP SHUTDOWN
├─ Tunggu decay heat turun (simplified — instant di simulator)
├─ Matikan Primary → Secondary → Tertiary (reverse order)

Phase 4: DEPRESSURIZATION
├─ Turunkan tekanan ke 0 bar
```

### Emergency Shutdown (SCRAM)

```
Trigger: Tombol EMERGENCY (GPIO 18)

Immediate Actions (parallel):
├─ ALL 3 rods drop ke 0% (3 detik, smooth animation)
├─ Turbine spin-down (12 detik, linear deceleration)
├─ Emergency buzzer (4000 Hz, 5 detik)

Post-SCRAM State:
├─ Rods: 0% (all inserted)
├─ Turbine: stopping/stopped
├─ Pumps: TETAP ON (decay heat removal)
├─ Pressure: TETAP (tidak auto-release)
├─ emergency_active: True (blocks rod movement)

Recovery:
├─ HANYA via REACTOR_RESET button
├─ Full reset semua parameter ke 0
├─ Harus restart dari Phase 1
```

---

## Sistem Keselamatan dalam Konteks Edukasi

### Defense in Depth (Konsep)

PWR nyata menerapkan **5 barrier** pertahanan berlapis:
1. Fuel pellet ceramic (menahan fission products)
2. Fuel cladding (zirconium alloy)
3. Reactor coolant pressure boundary
4. Containment building
5. Site exclusion zone

**Simulator ini memodelkan barrier #3** (pressure boundary) melalui sistem tekanan dan pompa pendingin, serta **aspek kontrol** melalui batang kendali dan interlock.

### SCRAM (Safety Control Rod Axe Man)

Di PWR nyata, SCRAM adalah insertion cepat SEMUA batang kendali oleh gravity + spring (< 2 detik). Simulator ini menggunakan servo motor dengan animasi 3 detik untuk efek visual edukasi.

### ECCS (Emergency Core Cooling System)

**Tidak dimodelkan** di simulator ini. Di PWR nyata, ECCS menyuntikkan air pendingin darurat saat LOCA (Loss of Coolant Accident). Simulator fokus pada operasi normal dan SCRAM.

### Containment

**Tidak dimodelkan**. Tidak ada skenario kecelakaan yang melibatkan breach containment.

---

## Terminologi Teknis

| Istilah Inggris | Bahasa Indonesia | Definisi | Relevansi ke Kode |
|-----------------|-----------------|----------|-------------------|
| PWR | Reaktor Air Bertekanan | Tipe reaktor nuklir komersial paling umum | Seluruh arsitektur simulator |
| Control Rod | Batang Kendali | Material penyerap neutron, mengontrol reaktivitas | `safety_rod`, `shim_rod`, `regulating_rod` |
| Safety Rod | Batang Keselamatan | Rod utama untuk SCRAM, harus 100% sebelum rod lain | `safety_rod`, SCRAM sequence |
| Shim Rod | Batang Kompensasi | Pengaturan daya kasar, posisi jarang diubah | `shim_rod`, thermal power calc |
| Regulating Rod | Batang Pengatur | Pengaturan daya halus, posisi sering diubah | `regulating_rod`, fine power control |
| Thermal Power | Daya Termal | Energi panas dari fisi nuklir (MWth) | `thermal_kw`, `reactor_thermal_kw` |
| Electrical Power | Daya Listrik | Energi listrik dari generator (MWe) | `thermal_kw_output` |
| SCRAM | Shutdown Darurat | Insertion cepat semua batang kendali | `emergency_active`, `_execute_scram_sequence()` |
| Criticality | Kekritisan | Kondisi di mana reaksi fisi self-sustaining | Rod position > 0% = mendekati critical |
| Subcritical | Subkritis | Reaksi fisi tidak self-sustaining, daya menurun | Rod 0% = subcritical (all inserted) |
| Supercritical | Superkritis | Reaksi fisi meningkat, daya naik | Rod 100% = supercritical (all withdrawn) |
| Reactivity | Reaktivitas | Ukuran seberapa jauh dari critical | Tidak dimodelkan langsung — simplified ke rod% |
| Pressurizer | Alat Penekan | Menjaga tekanan sistem primer | `pressure`, manual UP/DOWN |
| Coolant Loop | Loop Pendingin | Sirkuit fluida pendingin reaktor | 3 loops: primary, secondary, tertiary |
| Primary Loop | Loop Primer | Pendingin kontak langsung dengan fuel | `pump_primary`, highest priority |
| Steam Generator | Pembangkit Uap | Heat exchanger primer→sekunder | `humid_sg1_cmd`, `humid_sg2_cmd` |
| Turbine | Turbin | Mengubah energi uap menjadi energi mekanik | `turbine_speed`, FSM states |
| Condenser | Kondenser | Mengubah uap kembali ke air | Implicit (between secondary/tertiary) |
| Cooling Tower | Menara Pendingin | Membuang panas sisa ke atmosfer | `humid_ct1-4_cmd`, staged activation |
| Interlock | Penguncian Antar-sistem | Kondisi yang harus dipenuhi sebelum aksi | `interlock_satisfied`, checks |
| Decay Heat | Panas Peluruhan | Panas dari produk fisi setelah shutdown | Alasan pompa tetap ON saat SCRAM |
| Cherenkov Radiation | Radiasi Cherenkov | Cahaya biru dari partikel superluminal di air | `cherenkov_brightness`, blue LED |
| Fission | Fisi | Pembelahan inti atom berat | Basis seluruh thermal power |
| Neutron | Neutron | Partikel yang memicu fisi | Abstracted — diwakili rod position |
| Fuel Assembly | Perangkat Bahan Bakar | Kumpulan fuel rod di dalam core | Tidak dimodelkan individual |
| Cladding | Kelongsong | Pelapis fuel rod (zirconium) | Tidak dimodelkan |
| LOCA | Kehilangan Pendingin | Loss of Coolant Accident | Tidak disimulasikan |
| Defense in Depth | Pertahanan Berlapis | Filosofi keselamatan berlapis-lapis | Partial implementation |
| MWth | Megawatt termal | Satuan daya termal | Max 900 MWth |
| MWe | Megawatt listrik | Satuan daya listrik | Max 300 MWe |
| Bar | Bar | Satuan tekanan (1 bar ≈ 100 kPa) | 0-200 bar range |

---

## Parameter Operasional Tipikal

| Parameter | Range Simulasi | Nilai Normal Operasi | PWR Nyata (referensi) |
|-----------|---------------|---------------------|----------------------|
| Tekanan | 0 – 200 bar | 150 bar | 155 bar (15.5 MPa) |
| Daya Termal | 0 – 900 MWth | 900 MWth (full) | 2000-3400 MWth |
| Daya Listrik | 0 – 300 MWe | 300 MWe (full) | 700-1200 MWe |
| Efisiensi | Fixed 34% | 34% | 32-36% |
| Rod Position | 0 – 100% | 100% (full power) | Varies (stepped) |
| Coolant Flow | ON/OFF only | All 3 ON | ~70,000 m³/h |
| Temp Coolant | Tidak dimodelkan | — | 290°C inlet, 325°C outlet |
| Turbine Speed | 0 – 100% | 100% (running) | 1500/1800 RPM |

**Catatan**: Simulator menggunakan nilai yang disederhanakan. Tekanan 200 bar (max) mendekati PWR nyata (155 bar), tapi daya 900 MWth lebih kecil dari PWR komersial modern (2000-3400 MWth).

---

## Kejadian Abnormal yang Disimulasikan

### 1. Manual SCRAM (Emergency Shutdown)
- **Trigger**: Tombol EMERGENCY
- **Efek**: Rod drop + turbine spin-down + buzzer
- **Edukasi**: Demonstrasi sequence SCRAM dan pentingnya rod insertion cepat

### 2. Pressure Overrange
- **Trigger**: Tekanan > 160 bar (warning), > 180 bar (critical)
- **Efek**: Alarm buzzer bertingkat (2500 Hz → 3000 Hz)
- **Edukasi**: Pentingnya monitoring tekanan dan relief valve

### 3. Incorrect Pump Sequence
- **Trigger**: Start pump tanpa prerequisite (misal: start Primary tanpa Secondary ON)
- **Efek**: Prosedur ditolak + alarm 2000 Hz
- **Edukasi**: Pentingnya Standard Operating Procedure

### 4. Interlock Violation
- **Trigger**: Coba gerakkan rod tanpa interlock satisfied (P<140, pump not ON)
- **Efek**: Movement ditolak + alarm 1500 Hz
- **Edukasi**: Safety interlock sebagai barrier terakhir sebelum operator error

### 5. Low Pressure Operation
- **Trigger**: Tekanan < 40 bar saat start pump
- **Efek**: Start ditolak + alarm
- **Edukasi**: Pentingnya tekanan minimal untuk operasi pompa

### Kejadian yang TIDAK Disimulasikan

> 📝 **Planned Update (LOFA-041)**: LOFA (Loss of Flow Accident) akan ditambahkan. Lihat `docs/development/03-lofa-simulation.md`.

| Kejadian | Alasan Tidak Dimodelkan |
|----------|------------------------|
| LOCA (Loss of Coolant) | Terlalu kompleks, butuh model termodinamika |
| ~~LOFA (Loss of Flow)~~ | **Akan ditambahkan** — simulasi kegagalan pompa primer/sekunder/tersier |
| Fuel Meltdown | Tidak ada model temperatur fuel
| Steam Line Break | Tidak ada model secondary pressure |
| Reactivity Insertion Accident (RIA) | Reactivity tidak dimodelkan langsung |
| Boron Dilution | Tidak ada model boron concentration |
| Station Blackout | Power supply tidak dimodelkan |
| Earthquake/External Event | Di luar scope simulator edukasi |

---

## Batasan Edukasi vs Realita

### Simplifikasi yang Disadari

| Aspek | Simulator | PWR Nyata | Justifikasi Edukasi |
|-------|-----------|-----------|-------------------|
| **Batang kendali** | 3 kelompok, continuous 0-100% | 40-80 cluster, stepped insertion | Simplifikasi untuk demonstrasi konsep |
| **Thermal power** | Rumus quadratic buatan | Persamaan kinetika neutron (6 delayed groups) | Real-time di ESP32 tanpa overhead komputasi |
| **Pressure** | Manual control, instant response | Self-regulating dengan heater/spray | Fokus pada pemahaman efek tekanan |
| **Coolant temp** | Tidak dimodelkan | Parameter utama (T_in, T_out, ΔT) | Keterbatasan sensor di prototype |
| **Pump flow** | ON/OFF + ramping animation | Variable speed, flow rate control | Simplifikasi untuk demonstrasi sequence |
| **Turbin** | Simple FSM (4 state) | Complex governor control | Cukup untuk pemahaman konsep |
| **Reactivity** | Tidak ada — diwakili rod% | ρ = (keff-1)/keff, delayed neutron fraction | Terlalu abstrak untuk demonstrasi fisik |
| **Fuel burnup** | Tidak ada (steady state) | Berubah seiring waktu (cycle length) | Simulator stateless (no long-term tracking) |
| **Boron** | Tidak ada | Chemical shim (boron concentration) | Memerlukan model kimia tambahan |
| **Xenon** | Tidak ada | Xenon poisoning (Xe-135 buildup) | Memerlukan transient calculation |
| **Decay heat** | Abstrak (pump tetap ON) | ~6.5% rated power setelah SCRAM | Konsep diajarkan, tapi tidak dihitung |
| **SCRAM speed** | 3 detik (animated) | < 2 detik (gravity + spring) | Lebih lambat untuk efek visual edukasi |
| **Automatic SCRAM** | Tidak ada (manual only) | Banyak auto triggers (high flux, low flow, etc.) | Fokus pada manual operation procedure |
| **ECCS** | Tidak ada | Automatic injection systems | Di luar scope simulator |

### Hal yang Dibuat Lebih Jelas untuk Edukasi

1. **Staged cooling tower**: CT1-4 bertahap berdasarkan power level — di PWR nyata, cooling tower beroperasi kontinyu, tapi staging membantu mahasiswa memahami hubungan power-heat rejection
2. **Rod hierarchy visual**: Safety rod harus 100% sebelum rod lain — di PWR nyata ini lebih nuanced, tapi rule ini mengajarkan konsep safety priority
3. **Pump sequence enforcement**: Tertiary → Secondary → Primary — mengajarkan prosedur standar operasi
4. **Smooth rod animation**: Drop SCRAM 3 detik (vs <2 detik nyata) — lebih lambat agar mahasiswa bisa mengamati sequence
5. **Color-coded alarms**: 5 alarm dengan frekuensi berbeda — membantu auditory differentiation
6. **Video display edukasi**: Informasi tambahan di monitor HDMI — kombinasi visual fisik (OLED, LED, motor) dengan informasi digital
