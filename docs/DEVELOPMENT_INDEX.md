# 📋 Rencana Pengembangan PLTN Simulator

> Dokumen indeks untuk semua rencana pengembangan besar simulator PLTN.

---

## Daftar Pengembangan

| # | Nama Pengembangan | Status | File |
|---|-------------------|--------|------|
| 1 | Migrasi Panel Kontrol ke Touchscreen | 📝 Planning | [01-touchscreen-panel.md](development/01-touchscreen-panel.md) |
| 2 | Migrasi Aktuator ke RPi (Single Controller) | 📝 Planning | [02-single-controller.md](development/02-single-controller.md) |
| 3 | (TBD) | - | - |
| 4 | CPU Optimization | 📝 Planned | - |

---

## Quick Links

### Pengembangan Aktif
- **[01] Touchscreen Panel** — Ganti 17 push button + 9 OLED dengan 10" touchscreen
- **[02] Single Controller** — Hapus 2 ESP32, kontrol semua aktuator langsung dari RPi
- **[04] CPU Optimization** — Optimasi performa setelah migrasi (planned)

### Beads Commands
```bash
bd ready              # Lihat task yang siap dikerjakan
bd list --status=open # Lihat semua task terbuka
bd show <id>          # Detail task tertentu
```

---

## Struktur Dokumentasi

```
docs/
├── DEVELOPMENT_INDEX.md      # File ini - daftar semua pengembangan
└── development/
    ├── 01-touchscreen-panel.md   # Pengembangan #1
    ├── 02-xxx.md                 # Pengembangan #2 (TBD)
    └── ...
```

---

*Terakhir diupdate: 2026-03-23*
