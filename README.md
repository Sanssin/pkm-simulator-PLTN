# 🏭 PKM PLTN Simulator - Nuclear Power Plant Training Simulator

**Simulator PWR (Pressurized Water Reactor) v5.0**

[![Status](https://img.shields.io/badge/status-production%20ready-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.7%2B-blue)]()
[![Architecture](https://img.shields.io/badge/architecture-Single%20Controller%20(RPi)-success)]()

---

## 🎯 Overview

Simulator PLTN tipe **PWR (Pressurized Water Reactor)** ini sepenuhnya digerakkan menggunakan **Raspberry Pi 4** sebagai *Master Controller* tunggal. Sistem secara otomatis dan serentak merender antarmuka layar sentuh (*touchscreen*), layar pemutaran video edukasi (dashboard status), serta mengendalikan seluruh hardware I/O (Motor, Servo, Relay, LED Strip) secara langsung tanpa mikrokontroler eksternal.

---

## 🚀 Arsitektur Utama (v5.0)

Arsitektur simulator dirancang menjadi sangat efisien dan bebas *delay* (Zero Latency) dengan menghilangkan komunikasi I2C/UART lama (menghapus sistem ESP32) dan sepenuhnya beralih ke kontrol perangkat keras langsung melalui pin GPIO Raspberry Pi.

### Komponen Perangkat Keras
| Komponen | Jumlah | Fungsi |
|----------|--------|--------|
| **Raspberry Pi 4** | 1 | Otak utama yang menjalankan logika fisika, merender UI, dan melakukan kontrol I/O langsung. |
| **Touchscreen HMI** | 1 | Layar sentuh 1024x600 untuk kendali panel operator (pengganti penuh tombol-tombol fisik). |
| **Monitor Display** | 1 | Layar biasa berukuran 19-inch untuk menampilkan panduan video edukasi dan *dashboard* real-time. |
| **Servo Motor** | 3 | Menyimulasikan pergerakan mekanis dari Batang Kendali (*Safety, Shim, Regulating*). |
| **Motor Driver (L298N)**| 4 | Mengatur 3 aktuator pompa sirkulasi air dan 1 dinamo motor turbin menggunakan PWM. |
| **Modul Relay** | 4 | Bertugas menyalakan dan mematikan 4 unit *Humidifier* (pembuat uap) pada area *Cooling Tower*. |
| **LED Strip (WS2812)** | - | Animasi visualisasi aliran fluida di dalam rangkaian Pipa Primer, Sekunder, Tersier, dan Kondenser. |

---

## 🧠 Struktur Perangkat Lunak

Aplikasi simulator berjalan dengan tiga program paralel (*multi-process*) yang saling bertukar data secara instan dalam wujud *file* JSON berkecepatan tinggi yang ditempatkan di RAM disk sistem (`/tmp`).

```text
1. Touchscreen HMI (touch_panel/base_app.py)
   - Antarmuka sentuh interaktif untuk operator.
   - Bertugas menangani ketukan tombol (Pompa, Batang Kendali, Simulasi).
   - Program mengirimkan interaksi operator tersebut ke `/tmp/pltn_input.json`.

2. Main Controller (raspi_central_control/raspi_main_panel.py)
   - Ini adalah mesin fisika (*Physics Engine*) utama.
   - Membaca perintah operator dari `/tmp/pltn_input.json`.
   - Mengkalkulasi tekanan, suhu teras reaktor, persentase daya listrik, dan sistem pengaman (interlock).
   - Mengirim pulsa listrik ke hardware (Servo, Motor, Relay, LED Strip) lewat pin GPIO.
   - Memublikasikan kondisi terkini mesin tersebut ke `/tmp/pltn_state.json`.

3. Video Dashboard (pltn_video_display/video_display_app.py)
   - Antarmuka pemantauan jarak jauh untuk layar 19-Inch.
   - Bertugas membaca laporan kondisi dari `/tmp/pltn_state.json`.
   - Menerjemahkan angka-angka fisika tersebut menjadi animasi jarum meteran, tingkat air, dan memutar video cinematic.
```

---

## ⚡ Fitur Kunci Sistem

### 1. 🔐 Sistem Safety Interlock
Pengaman berbasis logika(*failsafe*). Upaya untuk menarik Batang Kendali (*Control Rod*) akan secara otomatis dicegah jika prosedur prasyarat tidak dipenuhi:
- ❌ Pompa Primer harus menyala.
- ❌ Pompa Sekunder harus menyala.
- ❌ Reaktor tidak boleh berada di tengah mode Darurat (SCRAM).

### 2. 🔥 Simulasi Termodinamika & Auto-SCRAM LOFA
Dilengkapi dengan perhitungan fisika termal:
- Panas teras reaktor (*thermal power*) dikalkulasi menggunakan kombinasi matematis posisi Batang Kendali (*Shim* & *Regulating*).
- **Simulasi LOFA (*Loss of Flow Accident*)**: Jika skenario darurat terjadi di mana aliran Pompa Primer dihentikan paksa, suhu inti reaktor akan meningkat secara ekstrem. Saat sistem mendeteksi suhu melebihi 300°C, fitur **Auto-SCRAM** otomatis memutus seluruh daya penahan agar batang pengaman jatuh gravitasi ke angka 0% secara seketika demi mencegah pelelehan (*meltdown*).

### 3. 🌊 Pemetaan Cerdas Humidifier
Sistem efek visualisasi kabut uap dipecah menjadi dua pemetaan kontrol tanpa beban histeresis berat:
- **Steam Generator (2 Unit)**: Aktif bereaksi secara sinkron terhadap elevasi posisi Batang Kendali. Saat reaktor dipanaskan, SG otomatis menyemburkan efek didih uap sebelum turbin sempat berputar.
- **Cooling Tower (4 Unit)**: Dikendalikan secara *Staged Activation* (berjenjang). Humidifier di masing-masing dari 4 Cooling Tower akan berturut-turut dihidupkan seiring dengan naiknya total daya listrik (MWe) yang diproduksi sistem; menciptakan efek visualisasi menara pendingin reaktor raksasa di dunia nyata.

### 4. 💡 Visualisasi Pipa LED Sinkron
Sistem tak lagi menggunakan lampu statis melainkan lampu WS2812 (Smart Addressable LED) di sepanjang rangkaian pipa.
Kecepatan putaran efek cairan (*flow ring*) pada LED tersebut diikat lurus pada persentase RPM pompa air secara mandiri, memberikan umpan balik optik super halus.

---

## 🔄 Alur Operasi Standar (Standard Operating Procedure)

1. **INISIASI**: Operator bersiaga dan memulai sesi pada layar sentuh. Seluruh batang tertanam 0%.
2. **SIRKULASI AIR PENDINGIN**: Operator berkewajiban menghidupkan jalur pompa urut mundur (Tersier → Sekunder → Primer).
3. **PENGANGKATAN BATANG KENDALI**: Operator menarik Batang *Shim* dan *Regulating* perlahan menjauh dari teras (up to 40-50%).
4. **PEMBUATAN UAP**: Suhu air mulai memanas dan memicu turbin uap untuk mulai mempercepat laju (*Spooling*). Uap keluar di *Steam Generator*.
5. **PRODUKSI DAYA LISTRIK**: Rotasi konstan turbin akan menstabilkan *Power Generation*. Angka MWe yang tinggi mulai memaksa *Cooling Tower* untuk mengeluarkan uap sisa panas.
6. **SCRAM (Mode Darurat)**: Saat tombol darurat raksasa ditekan, seketika batang meluncur nol persen, pompa memelankan RPM ke nol, daya hilang, dan semua sistem dikunci demi pencegahan paparan nuklir lanjutan.

---

## 📥 Panduan Menjalankan Simulasi (Mode Pengembangan)

Apabila sistem simulator utama tidak otomatis *boot*, Anda dapat menjalankan 3 komponen modular ini di Terminal Linux/PowerShell terpisah:

**Terminal 1 (Physics Engine & I/O Perangkat Keras):**
```bash
cd raspi_central_control
python raspi_main_panel.py
```

**Terminal 2 (Aplikasi Layar Touchscreen):**
```bash
cd touch_panel
python base_app.py
```

**Terminal 3 (Aplikasi Monitor Tambahan 19 Inch):**
```bash
cd pltn_video_display
python video_display_app.py
```

> **Catatan Teknis Perangkat Keras:** Untuk meninjau letak pasti pin-pin kabel yang wajib dicolokkan antara Raspberry Pi dan motor/relay, Anda dapat membacanya secara detail pada berkas `GPIO_PIN_MAPPING.md`.
