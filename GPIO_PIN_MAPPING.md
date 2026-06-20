# Peta Pin GPIO Raspberry Pi - Simulator PLTN v5.0

> **✅ STATUS:** Dokumen ini menampilkan pemetaan pin AKTIF untuk arsitektur Single Controller (v5.0).
> Seluruh komunikasi antarmuka lawas (UART/I2C) serta penggunaan mikrokontroler eksternal (ESP32) telah DITANGGALKAN.
> Semua aktuator mekanik dan indikator kelistrikan dikontrol langsung oleh pin pada Raspberry Pi 4.

---

## 📌 Ringkasan Penggunaan Pin GPIO (Sistem Penomoran: BCM)

### 1. Motor & Aktuator (via Driver L298N / VNH2SP30)
| Fungsi | Pin GPIO (BCM) | Keterangan |
|--------|---------------|------------|
| Pompa Primer | **GPIO 17** | Sirkulasi air utama reaktor (PWM) |
| Pompa Sekunder | **GPIO 20** | Sirkulasi menuju penukar panas / *Heat Exchanger* (PWM) |
| Pompa Tersier | **GPIO 27** | Sirkulasi panas buangan ke menara pendingin (PWM) |
| Motor Turbin | **GPIO 26** | Menggerakkan turbin putar (PWM) |

### 2. Servo Motor (Sistem Batang Kendali)
| Fungsi | Pin GPIO (BCM) | Keterangan |
|--------|---------------|------------|
| Safety Rod | **GPIO 23** | Batang Pengaman (Otomatis jatuh pada mode Darurat/SCRAM) |
| Shim Rod | **GPIO 24** | Batang Penyesuai Daya Tingkat Kasar |
| Regulating Rod | **GPIO 25** | Batang Pengatur Daya Tingkat Halus |

### 3. Relay Modul (Humidifier / Pembuat Uap Air)
| Fungsi | Pin GPIO (BCM) | Keterangan |
|--------|---------------|------------|
| Cooling Tower 1 (CT1) | **GPIO 2** | Otomatis dihidupkan (Aktif LOW/HIGH mengikuti relay) bergantung MWe |
| Cooling Tower 2 (CT2) | **GPIO 3** | Bergabung ke kontrol sekunsial pelepasan energi panas |
| Cooling Tower 3 (CT3) | **GPIO 9** | Bergabung ke kontrol sekunsial pelepasan energi panas |
| Cooling Tower 4 (CT4) | **GPIO 22** | Bergabung ke kontrol sekunsial pelepasan energi panas |

### 4. Visualisasi LED & Indikator Status
| Fungsi | Pin GPIO (BCM) | Keterangan |
|--------|---------------|------------|
| LED Strip (WS2812) | **GPIO 18** | Visualisasi laju pergerakan air di pipa (Terkunci ke hardware PWM0) |
| Indikator Daya Output | **GPIO 13** | Lampu tingkat produksi MWe (PWM1) |
| Efek Cherenkov (Biru) | **GPIO 16** | Pendaran cahaya biru reaktif di sekitar inti reaktor |
| Dekorasi Turbin | **GPIO 12** | Cahaya ambien untuk generator turbin |
| Relief Valve Aman | **GPIO 5** | Hijau (Tekanan Normal/Stabil) |
| Relief Valve Darurat| **GPIO 6** | Merah (Tekanan Melebihi Batas/Overpressure) |

---

## 🚫 Pin Usang / Dihapus (DO NOT USE)
Pin-pin berikut ini **sudah tidak lagi digunakan** karena komponen fisiknya telah dibongkar sepenuhnya dalam versi *Single Controller*:

- **GPIO 14 & 15 (UART0 TX/RX)**: Tidak lagi terhubung ke papan sirkuit ESP-BC.
- **GPIO 4 & 5 (UART3 TX/RX)**: Tidak lagi terhubung ke papan sirkuit ESP-E.
- **20+ Pin Input Tersebar**: Seluruh *push button* fisik mekanis (tombol Pompa, Tekanan, Batang, Reset) telah **dihapus** karena sistem pengoperasian kini 100% beralih menggunakan *Touchscreen Panel*.

---

## 🔌 Detail Konfigurasi Tambahan

1. **Dukungan Catu Daya Eksternal (WS2812 & Servo)**:
   Pin Raspberry Pi murni hanya untuk mengirimkan aliran data kelistrikan (Data/Signal). Jangan pernah mengambil daya (VCC) 5V dari Pin Raspberry Pi secara berlebihan untuk menarik beban Servo Motor atau ratusan lampu LED WS2812. Selalu gunakan PSU (Power Supply Unit) berkapasitas daya tinggi eksternal.

2. **Pentingnya Common Ground**:
   Sinyal kontrol PWM dari Raspberry Pi akan mengalami distorsi parah, atau tidak terbaca sama sekali oleh *Motor Driver* (L298N/VNH2SP30), jika Ground (`GND`) dari sirkuit tegangan 12V/24V milik perangkat keras tidak diikat secara fisik (*Jumper*) menyatu dengan pin Ground (`GND`) milik Raspberry Pi.
