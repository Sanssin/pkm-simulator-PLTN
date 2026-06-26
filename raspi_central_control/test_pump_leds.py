"""
Script diagnostik untuk menguji lampu LED indikator pompa secara langsung.
Jalankan dengan: sudo python3 raspi_central_control/test_pump_leds.py

CATATAN: Script ini akan otomatis menghentikan service jika sedang berjalan,
         menjalankan tes, lalu TIDAK merestart service (restart manual).
"""
import time
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Pastikan tidak ada service lain yang memakai DMA
print("[INIT] Menghentikan service sementara untuk akses DMA eksklusif...")
subprocess.run(['systemctl', 'stop', 'pkm-simulator.service'], 
               capture_output=True, timeout=10)
time.sleep(2)

try:
    import raspi_config as config
    print(f"[OK] raspi_config dimuat")
    print(f"     LED_STRIP_COUNT       = {config.LED_STRIP_COUNT}")
    print(f"     LED_SEGMENT_PUMP_INDS = {config.LED_SEGMENT_PUMP_INDS}")
    pump_start = config.LED_SEGMENT_PUMP_INDS[0]
    pump_count = config.LED_SEGMENT_PUMP_INDS[1]
    total      = config.LED_STRIP_COUNT
    strip_pin  = config.LED_STRIP_PIN
except Exception as e:
    print(f"[ERROR] Gagal load raspi_config: {e}")
    sys.exit(1)

print(f"\n[INFO] Konfigurasi LED:")
print(f"       Total LED strip : {total}")
print(f"       Pin data        : GPIO {strip_pin}")
print(f"       Pump ind start  : LED {pump_start}")
print(f"       Pump ind end    : LED {pump_start + pump_count - 1}")
print(f"       Primer start    : LED {config.LED_SEGMENT_PRIMER[0]}")
print(f"       Pressurizer end : LED {config.LED_SEGMENT_PRESSURIZER[0] + config.LED_SEGMENT_PRESSURIZER[1] - 1}")

try:
    from rpi_ws281x import PixelStrip, Color
    print(f"\n[OK] Library rpi_ws281x tersedia (hardware mode)")
except ImportError:
    print(f"\n[ERROR] Library rpi_ws281x tidak tersedia. Harus dijalankan di Raspberry Pi dengan sudo.")
    sys.exit(1)

print(f"\n[INIT] Menginisialisasi strip ({total} LED) di GPIO {strip_pin}...")
try:
    strip = PixelStrip(total, strip_pin, 800000, 10, False, 100, 0)  # brightness=100 for safety
    strip.begin()
    print(f"[OK] Strip berhasil diinisialisasi")
except Exception as e:
    print(f"[ERROR] Gagal inisialisasi strip: {e}")
    sys.exit(1)

def all_off():
    for i in range(total):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()

def set_pump_inds(r, g, b):
    for i in range(pump_count):
        strip.setPixelColor(pump_start + i, Color(r, g, b))
    strip.show()

# --- MULAI TES ---
print(f"\n{'='*50}")
print(f"[TEST] Memulai tes. Matikan semua LED...")
all_off()
time.sleep(1)

print(f"\n[TEST 1] MERAH SOLID di LED {pump_start}-{pump_start+pump_count-1}")
print(f"         Apakah TEPAT 3 lampu (pompa primer/sekunder/tersier) menyala MERAH?")
set_pump_inds(255, 0, 0)
time.sleep(3)

print(f"\n[TEST 2] HIJAU SOLID")
print(f"         Apakah 3 lampu yang sama menyala HIJAU?")
set_pump_inds(0, 255, 0)
time.sleep(3)

print(f"\n[TEST 3] KUNING SOLID")
set_pump_inds(255, 255, 0)
time.sleep(3)

print(f"\n[TEST 4] BIRU SOLID - memastikan tidak ada konflik dengan segmen primer (LED 330+)")
set_pump_inds(0, 0, 255)
# Juga nyalakan LED 330 (awal primer) dengan MERAH untuk membedakan
strip.setPixelColor(330, Color(255, 0, 0))
strip.setPixelColor(331, Color(255, 0, 0))
strip.setPixelColor(332, Color(255, 0, 0))
strip.show()
print(f"         LED 327-329 = BIRU, LED 330-332 = MERAH (awal primer)")
print(f"         Pastikan warna sesuai posisi fisik!")
time.sleep(4)

print(f"\n[TEST 5] Kedip 10x untuk memastikan respon")
for _ in range(10):
    set_pump_inds(255, 0, 0)
    time.sleep(0.3)
    set_pump_inds(0, 0, 0)
    time.sleep(0.3)

print(f"\n[SELESAI] Matikan semua LED.")
all_off()
print(f"""
{'='*50}
HASIL YANG DIHARAPKAN:
  Test 1: LED 327, 328, 329 = MERAH (3 lampu kecil di maket)
  Test 2: LED 327, 328, 329 = HIJAU
  Test 3: LED 327, 328, 329 = KUNING
  Test 4: LED 327-329 = BIRU, LED 330+ = MERAH (pisah jelas)
  Test 5: Ketiga lampu kedip merah

Jika warna yang menyala TIDAK SESUAI posisi fisik lampu pompa,
kemungkinan indeks 327-329 di raspi_config.py perlu disesuaikan.

CATATAN: Service sudah dihentikan. Restart manual dengan:
  sudo systemctl start pkm-simulator.service
{'='*50}
""")
