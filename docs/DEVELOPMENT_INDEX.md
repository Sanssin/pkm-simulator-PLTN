# 📋 Rencana Pengembangan PLTN Simulator

> Dokumen indeks untuk semua rencana pengembangan besar simulator PLTN.

---

## Daftar Pengembangan

| # | Nama Pengembangan | Status | File |
|---|-------------------|--------|------|
| 0 | Codebase Refactoring | ⭐ Prioritas | [00-codebase-refactoring.md](development/00-codebase-refactoring.md) |
| 1 | Migrasi Panel Kontrol ke Touchscreen | 📝 Planning | [01-touchscreen-panel.md](development/01-touchscreen-panel.md) |
| 2 | Migrasi Aktuator ke RPi (Single Controller) | 📝 Planning | [02-single-controller.md](development/02-single-controller.md) |
| 3 | LOFA Simulation (Loss of Flow Accident) | 📝 Planning | [03-lofa-simulation.md](development/03-lofa-simulation.md) |
| 4 | CPU Optimization | 📝 Planning | [04-cpu-optimization.md](development/04-cpu-optimization.md) |

---

## Quick Links

### Urutan Pengembangan (Recommended)
1. **[00] Codebase Refactoring** — Restrukturisasi kode, memudahkan pengembangan selanjutnya ⭐
2. **[01] Touchscreen Panel** — Ganti 17 push button + 9 OLED dengan 10" touchscreen
3. **[02] Single Controller** — Hapus 2 ESP32, kontrol semua aktuator langsung dari RPi
4. **[03] LOFA Simulation** — Simulasi Loss of Flow Accident dengan temperature modeling *(blocked by #01)*
5. **[04] CPU Optimization** — Optimasi performa setelah migrasi

### Beads Commands
```bash
bd ready              # Lihat task yang siap dikerjakan
bd list --status=open # Lihat semua task terbuka
bd show <id>          # Detail task tertentu
```

---

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Urutan Pengembangan                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   [00] Refactoring ──┬──────────────────────┐                       │
│   (Foundation)       │                      │                       │
│                      ▼                      ▼                       │
│               [01] Touchscreen      [02] Single Controller          │
│               (Input/Display)       (Actuator Control)              │
│                      │                      │                       │
│                      ├──────────────────────┤                       │
│                      │                      │                       │
│                      ▼                      │                       │
│               [03] LOFA Simulation          │                       │
│               (Safety Education)            │                       │
│                      │                      │                       │
│                      └──────────┬───────────┘                       │
│                                 ▼                                    │
│                         [04] CPU Optimization                        │
│                         (Performance Tuning)                         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Keterangan:**
- Pengembangan #00 sebaiknya selesai dulu (partially OK)
- Pengembangan #01 dan #02 bisa paralel setelah #00
- Pengembangan #03 (LOFA) membutuhkan #01 (touchscreen UI)
- Pengembangan #04 setelah semua fitur selesai (measure baseline)

---

## Struktur Dokumentasi

```
docs/
├── DEVELOPMENT_INDEX.md          # File ini - daftar semua pengembangan
└── development/
    ├── 00-codebase-refactoring.md    # Pengembangan #0
    ├── 01-touchscreen-panel.md       # Pengembangan #1
    ├── 02-single-controller.md       # Pengembangan #2
    ├── 03-lofa-simulation.md         # Pengembangan #3
    └── 04-cpu-optimization.md        # Pengembangan #4
```

---

*Terakhir diupdate: 2026-03-24*
