"""
Script diagnostik untuk menguji lampu LED indikator pompa secara langsung.
Jalankan dengan: sudo python3 raspi_central_control/test_pump_leds.py
"""
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import raspi_config as config
    print(f"[OK] raspi_config dimuat")
    print(f"     LED_STRIP_COUNT    = {config.LED_STRIP_COUNT}")
    print(f"     LED_SEGMENT_PUMP_INDS = {config.LED_SEGMENT_PUMP_INDS}")
    print(f"     LED_SEGMENT_SEKUNDER_OUT = {config.LED_SEGMENT_SEKUNDER_OUT}")
    print(f"     LED_SEGMENT_PRIMER = {config.LED_SEGMENT_PRIMER}")
    pump_start = config.LED_SEGMENT_PUMP_INDS[0]
    pump_count = config.LED_SEGMENT_PUMP_INDS[1]
    total      = config.LED_STRIP_COUNT
except Exception as e:
    print(f"[ERROR] Gagal load raspi_config: {e}")
    sys.exit(1)

# Cek apakah indeks pompa masuk akal
sek_out_end = config.LED_SEGMENT_SEKUNDER_OUT[0] + config.LED_SEGMENT_SEKUNDER_OUT[1]
primer_start = config.LED_SEGMENT_PRIMER[0]
print(f"\n[INFO] Cek urutan fisik LED:")
print(f"       sekunder_out berakhir di  : LED {sek_out_end - 1}")
print(f"       pump_inds mulai dari      : LED {pump_start}")
print(f"       pump_inds berakhir di     : LED {pump_start + pump_count - 1}")
print(f"       primer mulai dari         : LED {primer_start}")

if sek_out_end != pump_start:
    print(f"[WARNING] ADA GAP atau OVERLAP antara sekunder_out dan pump_inds!")
if pump_start + pump_count != primer_start:
    print(f"[WARNING] ADA GAP atau OVERLAP antara pump_inds dan primer!")

try:
    from rpi_ws281x import PixelStrip, Color
    print(f"\n[OK] Library rpi_ws281x ditemukan")
    HARDWARE = True
except ImportError:
    print(f"\n[WARNING] rpi_ws281x tidak tersedia - running in mock mode")
    HARDWARE = False
    class Color:
        def __new__(cls, r, g, b): return (r, g, b)
    class PixelStrip:
        def __init__(self, *a, **k): self._n = a[0]
        def begin(self): pass
        def show(self): pass
        def setPixelColor(self, n, c): pass
        def numPixels(self): return self._n

if not HARDWARE:
    print("[INFO] Tidak ada hardware. Hanya cek konfigurasi saja.")
    print("\n=== HASIL DIAGNOSTIK ===")
    ok = True
    if sek_out_end != pump_start:
        print(f"[MASALAH] Urutan LED TIDAK BERURUTAN: sekunder_out berakhir {sek_out_end-1}, pump_inds mulai {pump_start}")
        ok = False
    if pump_start + pump_count != primer_start:
        print(f"[MASALAH] Urutan LED TIDAK BERURUTAN: pump_inds berakhir {pump_start+pump_count-1}, primer mulai {primer_start}")
        ok = False
    if ok:
        print("[OK] Urutan konfigurasi LED sudah benar secara logika software.")
        print("     Kemungkinan masalah ada di KABEL FISIK (putusnya daisy-chain).")
    sys.exit(0)

# Kalau ada hardware, jalankan tes nyala-mati langsung
print(f"\n[TEST] Menginisialisasi strip ({total} LED) di pin {config.LED_STRIP_PIN}...")
try:
    strip = PixelStrip(total, config.LED_STRIP_PIN, 800000, 10, False, 255, 0)
    strip.begin()
    print("[OK] Strip berhasil diinisialisasi")
except Exception as e:
    print(f"[ERROR] Gagal inisialisasi strip: {e}")
    sys.exit(1)

# Matikan semua LED dulu
for i in range(total):
    strip.setPixelColor(i, Color(0, 0, 0))
strip.show()
print(f"\n[TEST] Semua LED dimatikan. Mulai tes pompa di LED {pump_start}-{pump_start+pump_count-1}...")
time.sleep(1)

COLORS = [
    ("MERAH (Pompa Mati)", Color(255, 0, 0)),
    ("HIJAU (Pompa Hidup)", Color(0, 255, 0)),
    ("KUNING (Starting)", Color(255, 255, 0)),
    ("MATI (Off)", Color(0, 0, 0)),
]

for label, color in COLORS:
    print(f"  -> Menyalakan {label} di LED {pump_start},{pump_start+1},{pump_start+2}...")
    for i in range(pump_count):
        strip.setPixelColor(pump_start + i, color)
    strip.show()
    time.sleep(2)

print("\n[TEST] Tes selesai. Matikan semua LED.")
for i in range(total):
    strip.setPixelColor(i, Color(0, 0, 0))
strip.show()
print("Selesai. Periksa apakah lampu 327, 328, 329 menyala sesuai warna di atas.")
