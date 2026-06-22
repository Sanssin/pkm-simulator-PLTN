# 📋 Indeks Pengembangan PLTN Simulator

> Dokumen indeks untuk semua siklus pengembangan besar simulator PLTN.

---

## 🟢 Status Penyelesaian Pengembangan (v5.0)

Seluruh target pengembangan sistem telah **SELESAI** diimplementasikan ke dalam sistem berjalan (*Production/v5.0*).

| # | Nama Pengembangan | Status | File Rencana |
|---|-------------------|--------|------|
| 0 | Codebase Refactoring | ✅ Selesai | [00-codebase-refactoring.md](development/00-codebase-refactoring.md) |
| 1 | Migrasi Panel Kontrol ke Touchscreen | ✅ Selesai | [01-touchscreen-panel.md](development/01-touchscreen-panel.md) |
| 2 | Migrasi Aktuator ke RPi (Single Controller) | ✅ Selesai | [02-single-controller.md](development/02-single-controller.md) |
| 3 | LOFA Simulation (Loss of Flow Accident) | ✅ Selesai | [03-lofa-simulation.md](development/03-lofa-simulation.md) |
| 4 | CPU Optimization | ✅ Selesai | [04-cpu-optimization.md](development/04-cpu-optimization.md) |

---

## 🚀 Kilas Balik Pencapaian (Changelog Major)

1. **[00] Codebase Refactoring**
   Struktur kode Python telah dibersihkan sepenuhnya. Komponen lama yang tidak efisien telah dihapus untuk menghasilkan performa komputasi yang lincah.

2. **[01] Touchscreen Panel**
   Sebanyak 17 push button mekanik dan 9 layar kecil OLED telah dilepas dari sistem fisik, digantikan dengan antarmuka layar sentuh elegan berbasis PyQt5 dan pertukaran sinyal JSON di dalam RAM (*IPC/Inter-process Communication*).

3. **[02] Single Controller (Master RPi)**
   Arsitektur lambat seperti I2C Mux dan UART Serial dihilangkan 100%. Tidak ada lagi penggunaan mikrokontroler ESP32 sebagai komponen budak (*slave*). Program utama sekarang mengontrol seluruh hardware relai, motor, dan servo **secara langsung dari pin GPIO Raspberry Pi**.

4. **[03] LOFA Simulation**
   Skenario kecelakaan hilangnya aliran pendingin telah berhasil ditambahkan dengan kalkulator fisika (*Physics Engine*). Sistem mencakup penalti pembentukan panas berlebih jika aliran lambat dan respons *Auto-SCRAM* saat melewati 300°C.

5. **[04] CPU Optimization**
   Penyempurnaan rutinitas baca-tulis file (*caching*) dan pengaturan prioritas thread secara *realtime* di tingkat Sistem Operasi telah memuluskan kinerja keseluruhan (*Zero stutters*).

---

*Catatan: Seluruh dokumen perencanaan masa lampau tetap dipertahankan pada subfolder `/development/` sebagai arsip riwayat referensi teknis, namun panduan operasional wajib menggunakan referensi terbaru.*
