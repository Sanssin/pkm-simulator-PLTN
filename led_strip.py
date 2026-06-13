from rpi_ws281x import PixelStrip, Color
import time
import sys

# --- KONFIGURASI LED ---
LED_COUNT      = 571
LED_PIN        = 18
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_BRIGHTNESS = 255
LED_INVERT     = False
LED_CHANNEL    = 0

# --- KONFIGURASI POLA ---
PATTERN_TOTAL  = 10   # Total siklus (misal: 10)
PATTERN_ON     = 5    # Jumlah LED nyala (misal: 5 nyala, 5 mati)
SPEED_DELAY    = 0.05 # Kecepatan pergerakan (detik)

def generate_gradient(num_leds):
    """
    Fungsi untuk menghitung gradien. 
    Mengembalikan list berisi nilai 'Color' yang sudah dikompilasi.
    """
    gradient_colors = [0] * num_leds
    
    grad_len = 71
    grad_start = (num_leds - grad_len) // 2
    grad_end = grad_start + grad_len - 1

    red = (255, 0, 0)
    blue = (0, 0, 255)

    for i in range(num_leds):
        if i < grad_start:
            # Kiri: Merah
            gradient_colors[i] = Color(red[0], red[1], red[2])
        elif i <= grad_end:
            # Tengah: Blend RGB
            t = (i - grad_start) / (grad_len - 1)
            r = int(red[0] * (1 - t) + blue[0] * t)
            g = int(red[1] * (1 - t) + blue[1] * t)
            b = int(red[2] * (1 - t) + blue[2] * t)
            gradient_colors[i] = Color(r, g, b)
        else:
            # Kanan: Biru
            gradient_colors[i] = Color(blue[0], blue[1], blue[2])
            
    return gradient_colors

def clear_strip(strip):
    """Mematikan seluruh LED."""
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()

def main():
    # 1. Inisialisasi Strip
    strip = PixelStrip(
        LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, 
        LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
    )
    strip.begin()

    # 2. Pra-Komputasi Warna
    # Menyimpan warna dalam format objek Color() terlebih dahulu
    gradient = generate_gradient(LED_COUNT)
    color_black = Color(0, 0, 0)

    offset = 0

    print("Program LED berjalan... (Tekan Ctrl+C untuk berhenti)")

    # 3. Main Loop dengan Error Handling
    try:
        while True:
            for i in range(LED_COUNT):
                # Pola 5 nyala, 5 mati
                if ((i + offset) % PATTERN_TOTAL) < PATTERN_ON:
                    # Menggunakan warna yang sudah dihitung sebelumnya
                    strip.setPixelColor(i, gradient[i])
                else:
                    strip.setPixelColor(i, color_black)

            strip.show()
            offset -= 1
            time.sleep(SPEED_DELAY)

    # 4. Safe Exit
    except KeyboardInterrupt:
        print("\nProgram dihentikan. Mematikan LED...")
        clear_strip(strip)
        sys.exit(0)

if __name__ == '__main__':
    main()
