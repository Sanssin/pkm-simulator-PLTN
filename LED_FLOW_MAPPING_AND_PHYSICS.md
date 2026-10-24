# 🌊 Dokumentasi Pemetaan & Karakteristik Aliran LED Simulator PLTN PWR v5.0

> **Dokumen Teknis:** Pemetaan Segmen LED WS2812B, Representasi Warna, Dinamika Kecepatan Aliran, dan Komparasi dengan Sistem Aliran PLTN PWR Nyata.  
> **Arsitektur:** Single Controller (Raspberry Pi 4 Master).  
> **Status:** Aktif (v5.0). Digunakan sebagai panduan *cross-check* fisik perangkat keras maket.

---

## 1. Arsitektur Perangkat Lunak Pengendali LED

Sistem visualisasi aliran fluida maket dikendalikan secara bertingkat oleh modul-modul berikut:

```
┌─────────────────────────────────────────────────────────────┐
│                       STATE MANAGER                         │
│   (Suhu Reaktor, Tekanan, Status Pompa, Mode Simulasi)      │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│        PHYSICS ENGINE        │ │      ACTUATOR MANAGER      │
│  • Termodinamika 3 Loop      │ │  • Konversi Ramping Pompa  │
│  • Saturasi Uap (T_sat)      │ │  • Hitung Heat Ratio &     │
│  • Kalkulasi LOFA & SCRAM    │ │    Flow Speed per Pipa     │
└──────────────┬───────────────┘ └────────────┬───────────────┘
               │                              │
               └──────────────┬───────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LED STRIP CONTROLLER                     │
│  • Driver: rpi_ws281x (DMA Channel 10, PWM0, GPIO 18, 800kHz)│
│  • Thread Animasi: 50 ms (20 FPS)                           │
│  • Pola Aliran: Chasing Bubbles (5 Pixel ON / 5 Pixel OFF)  │
│  • Perhitungan Warna Dinamis (_generate_gradient)           │
│  • Isolasi Rendering Lampu Indikator Pompa                  │
└─────────────────────────────┬───────────────────────────────┘
                              │ DIN (Data Line GPIO 18)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│             RANTAI FISIK 444 LED STRIP WS2812B              │
│  Tersier In → Kondenser → Tersier Out → Sekunder In →       │
│  Sekunder Out → Indikator Pompa → Primer → Pressurizer      │
└─────────────────────────────────────────────────────────────┘
```

### Rincian File Pengendali:
* [**`raspi_central_control/raspi_config.py`**](file:///D:/Project%202026/pkm-simulator-PLTN/raspi_central_control/raspi_config.py): Mendefinisikan nomor pin GPIO, panjang total LED (`LED_STRIP_COUNT = 444`), dan batas indeks masing-masing segmen `(start_index, length)`.
* [**`raspi_central_control/controllers/led_strip_controller.py`**](file:///D:/Project%202026/pkm-simulator-PLTN/raspi_central_control/controllers/led_strip_controller.py): Mengelola perangkat keras WS2812B, memelihara *background thread* animasi 50 ms, mengatur pergeseran offset pola aliran, modulasi gradien termal, dan isolasi lampu indikator pompa.
* [**`raspi_central_control/controllers/actuator_manager.py`**](file:///D:/Project%202026/pkm-simulator-PLTN/raspi_central_control/controllers/actuator_manager.py): Menerjemahkan kurva akselerasi pompa (7,0 detik) ke kecepatan visual LED, memetakan suhu aktual reaktor ke rasio panas (`heat_ratio`), mengontrol level bar pressurizer, dan mengendalikan PWM lampu non-strip.
* [**`raspi_central_control/controllers/physics_engine.py`**](file:///D:/Project%202026/pkm-simulator-PLTN/raspi_central_control/controllers/physics_engine.py): Menghitung suhu pendingin primer, sekunder, dan tersier serta tekanan sistem secara waktu nyata.
* [**`raspi_central_control/test_pump_leds.py`**](file:///D:/Project%202026/pkm-simulator-PLTN/raspi_central_control/test_pump_leds.py): Skrip diagnostik mandiri untuk menguji warna dan kedipan LED pompa langsung pada strip.

---

## 2. Tabel Pemetaan Lengkap Segmen LED Strip (WS2812B)

Total LED strip yang dipasang pada maket adalah **444 LED**. Seluruh segmen tersambung secara seri satu kabel data (*daisy-chained*) dari pin **GPIO 18 (Pin Fisik 12)**.

| No | Nama Segmen | Jalur / Komponen Maket | Indeks Awal | Jumlah LED | Rentang Indeks Fisik | Arah Aliran (*Direction*) |
|:--:|:------------|:-----------------------|:-----------:|:----------:|:--------------------:|:-------------------------:|
| **1** | `tersier_in` | Pipa pasokan air pendingin dari laut/menara pendingin menuju kondenser | 0 | 95 | **LED 0 s/d LED 94** | Maju (`+1`) |
| **2** | `kondenser` | Jalur pipa penukar panas kondensasi uap turbin | 95 | 46 | **LED 95 s/d LED 140** | Maju (`+1`) |
| **3** | `tersier_out` | Pipa buangan air panas tersier dari kondenser menuju cooling tower | 141 | 21 | **LED 141 s/d LED 161** | Maju (`+1`) |
| **4** | `sekunder_in` | Pipa air kondensat dingin/hangat dari kondenser kembali ke Steam Generator | 162 | 69 | **LED 162 s/d LED 230** | Maju (`+1`) |
| **5** | `sekunder_out` | Pipa uap utama (*Main Steam Line*) dari Steam Generator menuju Turbin | 231 | 72 | **LED 231 s/d LED 302** | Maju (`+1`) |
| **-** | `pump_inds` | **3 Lampu Indikator Pompa Fisik Terintegrasi**:<br>• Indeks 303: Pompa Tersier<br>• Indeks 304: Pompa Sekunder<br>• Indeks 305: Pompa Primer | 303 | 3 | **LED 303 s/d LED 305** | Terisolasi (Non-flow) |
| **6** | `primer` | Pipa sirkulasi pendingin reaktor utama (*Reactor Coolant Loop*): Teras $\to$ Steam Generator $\to$ Pompa Primer $\to$ Teras | 306 | 117 | **LED 306 s/d LED 422** | Maju (`+1`) |
| **7** | `pressurizer` | Bejana penstabil tekanan loop primer (*Pressurizer*) | 423 | 21 | **LED 423 s/d LED 443** | Maju (`+1`) (Mode Bar Level) |
| **TOTAL** | | **Seluruh Jalur Terpasang Fisik** | **0** | **444 LED** | **LED 0 s/d LED 443** | |

> ⚠️ **Catatan Penting Pengkabelan:** Indeks 303, 304, dan 305 adalah LED indikator status pompa yang tersambung secara fisik dalam satu deret strip antara pipa sekunder dan pipa primer. Driver `led_strip_controller.py` secara otomatis melewati (*skip*) ketiga indeks ini saat menganimasikan aliran pipa agar status lampu pompa tidak tertimpa oleh animasi air.

---

## 3. Rincian Warna dan Kondisi Transisi Termal

Warna LED berubah secara dinamis berdasarkan parameter temperatur dan tekanan dari `PhysicsEngine`:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             KODE WARNA DINAMIS                                   │
├─────────────────┬──────────────────────┬─────────────────────────────────────────┤
│ Kondisi         │ Nilai RGB            │ Penampilan Visual                       │
├─────────────────┼──────────────────────┼─────────────────────────────────────────┤
│ Dingin          │ (0, 0, 255)          │ Biru Murni                              │
│ Hangat (Cair)   │ (150, 0, 150)        │ Ungu Tua / Deep Violet                  │
│ Panas Reaktor   │ (255, 0, 0)          │ Merah Terang                            │
│ Uap Turbin      │ (200, 80, 100)       │ Peach / Soft Pink                       │
│ Uap Dingin/Mati │ (255, 255, 255)      │ Putih Statis                            │
│ Tekanan Normal  │ (255, 255, 255)      │ Putih (Menembus filamen biru maket)     │
│ Tekanan Kritis  │ (0, 255, 255)        │ Biru Terang / Cyan                      │
└─────────────────┴──────────────────────┴─────────────────────────────────────────┘
```

### Rincian Perilaku Masing-Masing Bagian Pipa:

### 1. Pipa Tersier Masuk (`tersier_in` | LED 0 – 94)
* **Warna:** **Biru Murni** `RGB(0, 0, 255)` solid.
* **Perilaku:** Tidak berubah oleh suhu karena menyimulasikan pasokan air pendingin dingin dari sumber lingkungan/laut.

### 2. Jalur Kondenser (`kondenser` | LED 95 – 140)
* Terbagi menjadi 2 zona internal sepanjang 46 LED:
  * **LED 95 s/d 117 (23 LED pertama):** **Biru Murni** `RGB(0, 0, 255)` solid (sisi inlet air pendingin masuk).
  * **LED 118 s/d 140 (23 LED berikutnya):** Bergradasi mengikuti perpindahan kalor uap turbin. Jika dingin (`heat_ratio < 0.2`): Biru. Jika uap turbin memanaskan kondenser (`heat_ratio >= 0.2`): Berubah gradual dari Biru ke **Merah** `RGB(255, 0, 0)` seiring pelepasan kalor laten uap ke air pendingin.

### 3. Pipa Tersier Keluar (`tersier_out` | LED 141 – 161)
* **Warna:** **Merah Panas** `RGB(255, 0, 0)` saat reaktor beroperasi.
* **Perilaku:** Mengalirkan air hangat hasil penyerapan kondensasi menuju *Cooling Tower* untuk didinginkan dan diuapkan melalui unit humidifier.

### 4. Pipa Balikan Sekunder (`sekunder_in` | LED 162 – 230)
* **Warna:** 
  * Saat reaktor dingin ($T_{\text{sec}} < 50^\circ\text{C}$): **Biru** `RGB(0, 0, 255)`.
  * Saat reaktor beroperasi dan mentransfer panas ($T_{\text{sec}} \ge 50^\circ\text{C}$): Berubah bertahap menjadi **Ungu Tua / Deep Violet** `RGB(150, 0, 150)`.
* **Tujuan Edukasi:** Menunjukkan bahwa air kondensat yang dipompa kembali ke Steam Generator adalah air cair yang telah melewati proses pemanasan awal (*feedwater preheating*), bukan air dingin suhu lingkungan.

### 5. Pipa Uap Sekunder (`sekunder_out` | LED 231 – 302)
* **Warna:**
  * Suhu $T_{\text{sec}} \le 80^\circ\text{C}$ (*Cold/No Steam*): **Putih Solid** `RGB(255, 255, 255)` tanpa pola gerak.
  * Suhu $T_{\text{sec}} > 80^\circ\text{C}$ (*Steam Generation Active*): Seketika berubah penuh menjadi **Peach / Soft Pink** `RGB(200, 80, 100)` dan mulai bergerak mengalir mengikuti putaran turbin.
* **Tujuan Edukasi:** Memberikan pembeda kontras yang jelas antara fase uap sekunder (Peach) dan fase air cair primer (Merah).

### 6. Pipa Sirkulasi Utama Primer (`primer` | LED 306 – 422)
* Terdiri dari 117 LED dengan pembagian zona:
  * **Kondisi Reaktor Dingin ($T < 50^\circ\text{C}$):** Seluruh pipa berwarna **Biru** `RGB(0, 0, 255)`.
  * **Kondisi Operasi Normal ($T \approx 100^\circ\text{C} - 345^\circ\text{C}$):**
    * *Hot Leg* (LED 306 s/d ~340): **Merah Terang** `RGB(255, 0, 0)` (air panas keluar dari teras reaktor menuju Steam Generator).
    * *Zona Transisi* (~16 LED): Gradasi halus dari Merah ke Violet.
    * *Cold Leg* (s/d LED 422): **Ungu Tua / Deep Violet** `RGB(150, 0, 150)` (air pendingin bertekanan tinggi setelah melepas panas di Steam Generator, masih bersuhu $\approx 290^\circ\text{C}$).
  * **Kondisi Abnormal / LOFA ($T > 345^\circ\text{C}$ hingga $380^\circ\text{C}$):**
    * Batas merah (*hot boundary*) merambat memanjang hingga menutupi **100% seluruh pipa primer** (LED 306 s/d 422 menjadi merah menyala total) karena panas teras reaktor tidak lagi diserap oleh Steam Generator akibat matinya pompa.

### 7. Pressurizer (`pressurizer` | LED 423 – 443)
* **Mode Operasi:** *Fill Level Bar* (bukan aliran putus-putus, melainkan bar ketinggian yang terisi dari bawah ke atas proporsional terhadap nilai tekanan $0 - 200\text{ bar}$).
* **Warna:**
  * $P \le 155\text{ bar}$ (Normal): **Putih Terang** `RGB(255, 255, 255)` (cahaya putih berpadu dengan filamen biru akrilik menghasilkan pendaran biru muda stabil).
  * $155 < P \le 165\text{ bar}$ (Peringatan): Bertransisi gradual dari Putih ke **Cyan** `RGB(0, 255, 255)`.
  * $P > 165\text{ bar}$ (Kritis / Overpressure): **Cyan Solid** `RGB(0, 255, 255)`.

---

## 4. Karakteristik Kecepatan & Pola Aliran

### A. Formula Kecepatan Aliran
Sistem memperbarui animasi setiap $\Delta t = 0,05\text{ detik}$ (20 FPS). Pergeseran posisi pola dihitung dengan persamaan:
$$\Delta \text{Offset} = \text{speed} \times \text{flow\_direction} \times \Delta t \times 20.0$$

* Pada kecepatan penuh (`speed = 1.0` / Pompa 100% ON):
  * Laju pergeseran = **20 LED per detik** (1 LED per frame 50 ms).
* Pola aliran menggunakan formasi **5 LED Menyala dan 5 LED Padam** (*chasing bubble pattern*) yang bergeser maju terus-menerus.

### B. Transisi Inersia Pompa (7,0 Detik)
Saat operator menekan tombol pompa ON atau OFF di layar sentuh:
* Kecepatan motor dan animasi LED tidak melompat seketika, melainkan mengalami percepatan (*ramp up*) atau perlambatan (*ramp down*) linier selama **7,0 detik**.
* Hal ini menyimulasikan inersia mekanis pompa sirkulasi reaktor (*Reactor Coolant Pump*) dunia nyata.

### C. Kondisi Pompa Mati (OFF / Freeze)
* Saat pompa dimatikan pada sesi aktif, kecepatan LED menjadi `0.0`.
* Pola LED **berhenti bergerak di tempat (*freeze/statis*)** dan **TETAP MENYALA**. Hal ini menandakan bahwa fluida di dalam pipa fisik tetap terisi air (tidak kosong).
* Lampu LED hanya akan padam total (*blank*) jika sistem di-*reset* ke mode *idle*.

### D. Kecepatan Khusus Pressurizer
Pressurizer memiliki animasi ombak riak air internal dengan kecepatan yang berbanding lurus dengan tekanan:
$$\text{speed}_{\text{pressurizer}} = 0,5 + \left(\frac{\text{Pressure}}{200} \times 2,0\right)$$
Kecepatan berkisar antara 0,5 (tekanan 0 bar) hingga 2,5 (tekanan 200 bar, setara laju hingga 50 LED/detik).

---

## 5. Pemetaan LED Indikator Pompa & LED Non-Strip

### A. Lampu Indikator Status Pompa (LED Strip 303 – 305)
Ketiga LED kecil ini terpasang di panel fisik dekat motor pompa:

| Indeks LED | Representasi Pompa | Kondisi OFF | Kondisi Transisi (Start/Stop) | Kondisi ON | Kondisi Gangguan (LOFA) |
|:---:|:---|:---:|:---:|:---:|:---:|
| **LED 303** | Pompa Tersier | Merah Solid | Kuning Kedip (4 Hz) | Hijau Solid | Merah Kedip (4 Hz) |
| **LED 304** | Pompa Sekunder | Merah Solid | Kuning Kedip (4 Hz) | Hijau Solid | Merah Kedip (4 Hz) |
| **LED 305** | Pompa Primer | Merah Solid | Kuning Kedip (4 Hz) | Hijau Solid | Merah Kedip (4 Hz) |

### B. LED Diskret & Dekoratif (GPIO Non-Strip)
Dikendalikan melalui jalur GPIO independen di Raspberry Pi:

| Indikator | Pin GPIO (BCM) | Pin Fisik RPi | Tipe Sinyal | Logika Kendali | Representasi Fisik |
|:---|:---:|:---:|:---:|:---|:---|
| **Cherenkov Glow** | **GPIO 16** | Pin 36 | Hardware PWM | $Duty = (P_{\text{thermal\_ratio}})^{1,5} \times 100\%$ | Pendaran cahaya biru reaktif di sekitar bejana reaktor. |
| **Turbin Ambience** | **GPIO 12** | Pin 32 | Hardware PWM | $Duty = P_{\text{thermal\_ratio}} \times 100\%$ | Lampu dekoratif iluminasi generator turbin. |
| **Daya Output (MWe)** | **GPIO 13** | Pin 33 | Hardware PWM | $Duty = P_{\text{thermal\_ratio}} \times 100\%$ | Lampu indikator tingkat daya listrik yang dihasilkan. |
| **Relief Valve Normal** | **GPIO 5** | Pin 29 | Digital OUT | HIGH saat $P \le 165\text{ bar}$ | Lampu **Hijau** (katup pengaman tertutup, tekanan normal). |
| **Relief Valve Buka** | **GPIO 6** | Pin 31 | Digital OUT | HIGH saat $P > 165\text{ bar}$ | Lampu **Merah** (katup pelepas darurat terbuka membuang uap). |

---

## 6. Komparasi Mendalam dengan PLTN PWR Dunia Nyata

```
+====================================================================================================+
|                              MATRIKS KOMPARASI: SIMULATOR VS PWR NYATA                             |
+======================+======================================+======================================+
| ASPEK TERMODINAMIKA  | PLTN PWR NYATA (KOMERSIAL)           | SIMULATOR MAKET PKM (v5.0)           |
+======================+======================================+======================================+
| Tekanan Operasi      | ~155 bar (15,5 MPa) konstan          | 150 bar normal (rentang 0 - 200 bar) |
+----------------------+--------------------------------------+--------------------------------------+
| Sirkulasi Primer     | Suhu Hot Leg: ~325°C                 | Hot Leg: Merah (255, 0, 0)           |
| (Warna & Fase)       | Suhu Cold Leg: ~290°C                | Cold Leg: Violet (150, 0, 150)       |
|                      | Fluida 100% cair jenuh (tidak didih) | Menunjukkan fluida tetap cair hangat |
+----------------------+--------------------------------------+--------------------------------------+
| Sirkulasi Sekunder   | Air masuk SG ~220°C (cair)           | Sekunder In: Ungu Violet cair hangat |
| (Warna & Fase)       | Keluar SG uap jenuh kering ~280°C    | Sekunder Out: Peach Soft Pink uap    |
|                      | Menggerakkan turbin & kondensasi     | Uap terbentuk saat T > 80°C          |
+----------------------+--------------------------------------+--------------------------------------+
| Sirkulasi Tersier    | Air laut/sungai masuk ~25°C          | Tersier In: Biru solid dingin        |
| (Warna & Fase)       | Keluar kondenser hangat ~40°C        | Tersier Out: Merah hangat            |
|                      | Membuang panas ke cooling tower      | Kondenser: Gradasi penyerapan panas  |
+----------------------+--------------------------------------+--------------------------------------+
| Pressurizer          | Dua fasa: 60% air cair, 40% uap      | Bar Level LED (21 LED)               |
|                      | Level air dijaga konstan 50-60%      | Mengindikasikan besaran tekanan      |
+----------------------+--------------------------------------+--------------------------------------+
| Kecepatan Fluida     | Primer: 10 - 15 m/s                  | Diseragamkan: ~20 LED/s (maksimal)   |
|                      | Uap Sekunder: 30 - 50 m/s            | Dibatasi untuk ergonomi visual mata  |
|                      | Tersier: 2 - 3 m/s                   | Ramping 7 detik untuk inersia pompa  |
+----------------------+--------------------------------------+--------------------------------------+
| Interlock Pompa      | Wajib Tersier -> Sekunder -> Primer  | Wajib Tersier -> Sekunder -> Primer  |
+----------------------+--------------------------------------+--------------------------------------+
```

### Analisis Evaluasi:
1. **Representasi Warna (Sangat Sesuai & Edukatif)**:
   * Penggunaan warna Ungu/Violet untuk balikan primer dan sekunder adalah keputusan desain yang sangat tepat. Hal ini mendidik audiens bahwa air yang kembali ke reaktor bukanlah air dingin suhu kamar, melainkan air bersuhu $\approx 290^\circ\text{C}$ yang dipertahankan berfase cair oleh tekanan 155 bar.
   * Warna Peach untuk uap membedakan secara tegas antara uap sekunder dan air cair primer.
2. **Representasi Kecepatan (Optimal untuk Maket Visual)**:
   * Secara fisis nyata, kecepatan uap di pipa sekunder ($\approx 40\text{ m/s}$) jauh lebih cepat daripada air primer ($\approx 12\text{ m/s}$).
   * Namun, pada strip LED WS2812B, jika kecepatan dinaikkan melebihi 20–30 LED/detik, mata manusia akan mengalami fenomena *motion blur / persistence of vision* sehingga pipa hanya tampak menyala statis tanpa terlihat arah alirannya. Kecepatan 20 LED/detik adalah titik optimum agar pergerakan gelembung dapat diamati dengan nyaman dan jelas oleh mata.
3. **Inersia Mekanis (Sangat Sesuai)**:
   * Fitur *ramping* 7 detik merefleksikan kenyataan bahwa motor pompa pendingin reaktor berdaya megawatt memiliki *flywheel* bermassa puluhan ton untuk menghasilkan sirkulasi sisa saat terjadi trip listrik (*coasting flow*).

---

## 7. Panduan Diagnostik & Pengujian Fisik (*Cross-Check* Maket)

Untuk memverifikasi kesesuaian antara program dan kondisi fisik maket, lakukan langkah berikut:

### 1. Uji Mandiri LED Pompa (Index 303 – 305)
Jalankan skrip tes perangkat keras khusus:
```bash
sudo python3 raspi_central_control/test_pump_leds.py
```
* **Verifikasi Visual:** Pastikan tepat 3 buah lampu indikator kecil menyala bergantian: Merah $\to$ Hijau $\to$ Kuning $\to$ Biru $\to$ Kedip Merah.
* Jika yang menyala adalah bagian pipa primer atau sekunder, sesuaikan indeks pada variabel `LED_SEGMENT_PUMP_INDS` di `raspi_config.py`.

### 2. Uji Aliran Pipa Sekunder & Uap
1. Masuk ke mode manual melalui touchscreen.
2. Hidupkan Pompa Tersier $\to$ Sekunder. Pipa sekunder masuk (`sekunder_in`) akan mengalir warna biru/violet.
3. Naikkan batang kendali hingga suhu melampaui $80^\circ\text{C}$. Pipa uap (`sekunder_out`) harus seketika berubah warna menjadi **Peach/Pink** dan mulai mengalir menuju turbin.

### 3. Uji Skenario LOFA (Overheating Pipa Primer)
1. Jalankan mode simulasi otomatis (*Cinematic LOFA* atau *LOFA Sequence*).
2. Saat pompa primer trip/mati, perhatikan pipa primer: warna merah pada *hot leg* (LED 306-340) akan merambat perlahan ke arah *cold leg* hingga seluruh pipa primer (LED 306-422) menyala merah total.
3. Indikator pompa primer (LED 305) harus berkedip merah (4 Hz).

---
*Dokumen ini disusun sebagai acuan teknis resmi Simulator PLTN PWR v5.0 (PKM 2024/2026).*
