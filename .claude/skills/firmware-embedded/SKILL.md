---
name: Firmware-Embedded-Systems
description: Raspberry Pi single-controller architecture, hardware IO, threading patterns
---

# Skill: Firmware & Embedded Systems — Single Controller Architecture

## Konteks Proyek

Simulator PLTN (PWR) saat ini menggunakan **Arsitektur Single Controller** (migrasi dari ESP32). Semua pemrosesan logika, kontrol aktuator fisik, dan interaksi UI dikendalikan langsung oleh **Satu Raspberry Pi 4**.

- **Sistem Operasi**: Raspberry Pi OS (Linux)
- **Aplikasi Utama**: Python 3.7+
- **Pembagian CPU (Affinity)**:
  - Core 0: IO Export / OS interrupts / State Exporter
  - Core 1: Control Logic calculations & Input polling (High Priority)
  - Core 2 & 3: Touch UI rendering & Video rendering (Normal Priority)

Arsitektur ini menghilangkan latensi komunikasi UART dan mempermudah debugging karena *source of truth* hanya ada di memori Python.

---

## Hardware Interface Patterns

Seluruh aktuator dikelola secara terpusat oleh `ActuatorManager` (`raspi_central_control/controllers/actuator_manager.py`). Komponen ini menjembatani logika dengan *hardware* via beberapa *sub-controller*.

### Pattern 1: Button Input (RPi.GPIO)

Semua 17 tombol fisik menggunakan **pull-up internal** dan bersifat **active LOW** (tombol ditekan = menghubungkan pin ke GND).

```python
# raspi_gpio_buttons.py — Enum untuk mapping pin BCM
class ButtonPin(IntEnum):
    PUMP_PRIMARY_ON = 11
    # ...
```

Proyek ini menggunakan 2 tipe deteksi tombol:
1. **EDGE DETECTION**: Trigger SEKALI per tekan (untuk tombol *toggle* seperti pompa, START, EMERGENCY). Menggunakan *2-sample confirmation* untuk *debouncing*.
2. **LEVEL DETECTION**: Trigger BERULANG selama ditahan (untuk pergerakan kontinu seperti *control rods* naik/turun, tekanan naik/turun).

### Pattern 2: Servo Motor (Control Rods)

Digunakan untuk 3 aktuator Batang Kendali (Safety, Shim, Regulating).
Awalnya menggunakan `ESP32Servo`, kini menggunakan `gpiozero` atau `pigpio` via `ServoController`.

```python
# ActuatorManager inisiasi
self.servos = ServoController(
    safety_pin=23,
    shim_pin=24,
    reg_pin=25
)

# Penggunaan di Control Logic
self.actuators.servos.set_positions(
    safety_actual,
    shim_actual,
    regulating_actual
)
```

### Pattern 3: Motor DC & Pompa (Hardware PWM via pigpio)

Motor driver L298N atau Mosfet untuk menggerakkan: Pompa Primer, Sekunder, Tersier, dan Turbin.
Menggunakan `pigpio` untuk mendapatkan *Hardware PWM* yang stabil dan tidak *jittery* (jitter terjadi bila pakai RPi.GPIO standard software PWM).

```python
# ActuatorManager memanggil MotorController
self.motors.set_motor_speed('pump_primary', speed_percent)
```

### Pattern 4: Neopixel / WS2812B LED Strip (DMA)

Mensimulasikan aliran air dan status tabung reaktor (Cerenkov radiation) menggunakan *Addressable LEDs*.
Menggunakan library `rpi_ws281x` dengan Direct Memory Access (DMA) channel 10 agar tidak membebani CPU.

```python
self.led_strip = LedStripController(pin=18, count=592, channel=0, dma=10)
self.led_strip.add_segment('primer', start=21, length=190)

# Animasi warna/alir
self.led_strip.set_flow_speed('primer', speed)
```

### Pattern 5: Relay (Active LOW)

Untuk mengendalikan komponen on/off absolut (seperti kipas *Cooling Tower*).

```python
# RelayController (berbasis RPi.GPIO atau gpiozero)
self.relays.set_relay('ct1', state=True) # Aktif jika thermal tinggi
```

---

## Inter-Process Communication (IPC) Patterns

Karena UI Layar Sentuh (`touch_panel_app.py`), UI Monitor Video (`video_display_app.py`), dan Logika Reaktor (`raspi_main_panel.py`) adalah **tiga proses (proses/aplikasi) yang berjalan terpisah**, maka IPC digunakan:

### 1. State Export (JSON Polling)

Digunakan oleh Backend (Core 0/1) untuk mengirim data sensor & aktuator terkini ke proses UI (Core 2/3).
- **Backend Thread** (`StateExporter`): Secara periodik mengekspor class dataclass `PanelState` ke JSON.
- **Atomic Write Pattern**: File ditulis sebagai `.tmp` terlebih dahulu, lalu di-`rename` ke ekstensi akhir agar UI yang sedang membaca tidak *crash* karena membaca JSON yang setengah jadi.
  
```python
temp_file = self.state_export_file.with_suffix('.tmp')
temp_file.write_text(json.dumps(state_dict))
temp_file.rename(self.state_export_file)  # Atomic operation di Linux
```

### 2. UI Actions Export (Interactions JSON)

Digunakan oleh Layar Sentuh untuk mengirim perintah/event kembali ke Backend.
- Layar Sentuh mencatat kapan tombol di layar disentuh ke `interactions.json`.
- `TouchPollingThread` di Backend terus memonitor file ini dan menerjemahkannya ke dalam `ButtonEvent` yang masuk ke `button_event_queue`.

---

## Threading & Concurrency Patterns

Modul kontrol utama (`raspi_main_panel.py`) adalah *multi-threaded*:

### Thread-Safe Button Event Queue

Semua input (baik dari tombol fisik via interupsi maupun tombol sentuh via JSON) akan dimasukkan ke antrean (*queue*) tersentralisasi.

```python
self.button_event_queue = Queue(maxsize=100)

# Processor thread:
event = self.button_event_queue.get()
with self.state_lock:
    self.process_event(event)
```

### Lock Hierarchy

Proyek ini mendewakan efisiensi.
- **Aturan 1**: Dilarang melakukan operasi I/O (menulis file, print log panjang, sleep) saat masih memegang `self.state_lock`.
- **Aturan 2**: `state_lock` tidak boleh tumpang tindih dengan lock eksternal lainnya yang dapat menyebabkan *Deadlock*.

---

## Error Handling & Graceful Degradation

Proyek ini didesain agar tetap bisa dijalankan pada PC/Laptop biasa untuk pengembangan antarmuka, tanpa *crash* meskipun pin GPIO tidak ada.

### MOCK Mode

Modul-modul *hardware* seperti `ActuatorManager` akan mendeteksi apabila *library* seperti `RPi.GPIO` atau `pigpio` gagal di-`import` atau diinisialisasi.
Bila gagal, sistem akan masuk ke **MOCK MODE**, di mana perintah ke motor/servo hanya akan dicetak sebagai `logger.info()` di Terminal, dan simulasi fisika reaktor tetap berjalan 100% normal.

```python
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

if not GPIO_AVAILABLE:
    logger.info("Running in MOCK mode (No RPi.GPIO)")
```

---

## Common Debugging Steps

### Motor/Servo Jitter atau Tidak Bergerak
1. Pastikan daemon `pigpiod` sudah berjalan di latar belakang Linux (`sudo systemctl start pigpiod`). Modul hardware PWM bergantung pada ini.
2. Cek catu daya 5V untuk Servo dan 12V untuk motor driver. Raspberry Pi tidak boleh mem-power motor secara langsung.
3. Cek pembagian affinity CPU. Hardware I/O idealnya tidak terganggu oleh UI render loop.

### Layar Sentuh Tidak Menggerakkan Reaktor
1. Pastikan file `interactions.json` dapat ditulis oleh `touch_panel_app.py`.
2. Pastikan `raspi_main_panel.py` membacanya secara berkala.
3. Cek *Permissions* jika berjalan di bawah `sudo`.

### High CPU Usage
1. Periksa `cpu_dashboard.py` untuk melihat proses mana yang memakan resource.
2. Pastikan animasi LED WS2812 tidak berjalan pada loop *blocking* dan frekuensi framerate dibatasi.
