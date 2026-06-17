import time
import logging
import threading
import math

# Global lock to prevent concurrent DMA hardware access from multiple LedStripController threads
ws281x_lock = threading.Lock()

# Fallback for environments without rpi_ws281x (like Windows/Mac development)
try:
    from rpi_ws281x import PixelStrip, Color
except ImportError:
    class Color:
        def __new__(cls, r, g, b):
            return (r, g, b)
    
    class PixelStrip:
        def __init__(self, *args, **kwargs):
            self._numPixels = args[0] if args else kwargs.get('num', 0)
            
        def begin(self): pass
        def show(self): pass
        def setPixelColor(self, n, color): pass
        def numPixels(self): return self._numPixels


logger = logging.getLogger(__name__)

class LEDSegment:
    def __init__(self, name: str, start_idx: int, length: int, flow_direction: int = 1):
        self.name = name
        self.start_idx = start_idx
        self.length = length
        self.flow_direction = flow_direction # 1 for forward, -1 for backward
        self.offset = 0.0
        self.speed = 0.0 # 0.0 = stopped, >0 = moving
        self.fill_level = -1.0 # -1.0 means flow mode, 0.0-1.0 means fill mode
        self.fill_color = Color(255, 100, 0)
        self.heat_ratio = 0.0  # 0.0 = cold (full blue), 1.0 = hot (red end)
        
        # Pre-compute gradient for this segment
        self.gradient = self._generate_gradient()

    def update_heat_ratio(self, ratio: float):
        ratio = max(0.0, min(1.0, ratio))
        if abs(self.heat_ratio - ratio) > 0.05:
            self.heat_ratio = ratio
            self.gradient = self._generate_gradient()

    def _generate_gradient(self):
        gradient_colors = [Color(0,0,0)] * self.length
        
        blue = (0, 0, 255)
        # Warna panas bertransisi dari Biru (dingin) ke Merah (panas maksimum)
        hot_r = int(blue[0] * (1.0 - self.heat_ratio) + 255 * self.heat_ratio)
        hot_g = int(blue[1] * (1.0 - self.heat_ratio) + 0 * self.heat_ratio)
        hot_b = int(blue[2] * (1.0 - self.heat_ratio) + 0 * self.heat_ratio)
        hot_color = (hot_r, hot_g, hot_b)

        # Khusus untuk kondenser: transisi warna tajam di tengah (perpotongan)
        # Lampu 1-23 (index 0-22) Biru: air pasokan dingin dari tersier
        # Lampu 24-46 (index 23-45) Merah/Panas: setelah mengambil panas uap turbin
        if self.name == 'kondenser':
            for i in range(self.length):
                if i < 23:
                    gradient_colors[i] = Color(blue[0], blue[1], blue[2])
                else:
                    gradient_colors[i] = Color(hot_color[0], hot_color[1], hot_color[2])
            return gradient_colors

        # Pipa air laut (tersier_in) menuju kondenser: Biru solid (dingin)
        # Atau aliran balik sekunder (sekunder_in) dari kondenser: Biru solid (dingin)
        if self.name in ('tersier_in', 'sekunder_in'):
            for i in range(self.length):
                gradient_colors[i] = Color(blue[0], blue[1], blue[2])
            return gradient_colors

        # Keluaran kondenser (tersier_out) ke cooling tower: Panas solid
        if self.name == 'tersier_out':
            for i in range(self.length):
                gradient_colors[i] = Color(hot_color[0], hot_color[1], hot_color[2])
            return gradient_colors

        # Default: Gradien halus untuk segmen lain (primer, sekunder, tersier)
        grad_len = min(71, self.length) # Use 71 or max length
        grad_start = (self.length - grad_len) // 2
        grad_end = grad_start + grad_len - 1

        for i in range(self.length):
            if i < grad_start:
                # Awal: Biru (dingin — air masuk)
                gradient_colors[i] = Color(blue[0], blue[1], blue[2])
            elif i <= grad_end:
                # Tengah: Blend dari Biru ke Warna Panas
                t = (i - grad_start) / (max(1, grad_len - 1))
                r = int(blue[0] * (1 - t) + hot_color[0] * t)
                g = int(blue[1] * (1 - t) + hot_color[1] * t)
                b = int(blue[2] * (1 - t) + hot_color[2] * t)
                gradient_colors[i] = Color(r, g, b)
            else:
                # Akhir: Warna Panas (dingin/panas — air keluar)
                gradient_colors[i] = Color(hot_color[0], hot_color[1], hot_color[2])
                
        return gradient_colors


class LedStripController:
    """
    Mengontrol WS2812 LED strip untuk memvisualisasikan aliran air.
    LED strip dibagi menjadi beberapa segmen (primer, sekunder, tersier).
    Masing-masing segmen dapat mengalir dengan kecepatan berbeda berdasarkan status pompa.
    """
    
    def __init__(self, pin: int = 18, count: int = 571, channel: int = 0, dma: int = 10):
        self.pin = pin
        self.count = count
        
        self.freq_hz = 800000
        self.dma = dma
        self.brightness = 255
        self.invert = False
        self.channel = channel
        
        try:
            self.strip = PixelStrip(
                self.count, self.pin, self.freq_hz, self.dma, 
                self.invert, self.brightness, self.channel
            )
            self.strip.begin()
        except RuntimeError as e:
            logger.error(f"WS281x C library failed: {e}. (Run as sudo for /dev/mem access). Running in mock mode.")
            self.strip = None
        except Exception as e:
            logger.error(f"Failed to initialize WS281x: {e}. Running in mock mode.")
            self.strip = None
        
        self.segments = {}
        self.running = False
        self._thread = None
        
        self.pattern_total = 10
        self.pattern_on = 5
        self.update_interval = 0.05 # 50ms updates
        
        self.color_black = Color(0, 0, 0)

    def add_segment(self, name: str, start_idx: int, length: int, flow_direction: int = 1):
        """Menambahkan segmen aliran baru pada strip."""
        if start_idx + length > self.count:
            logger.error(f"Segment {name} exceeds LED count!")
            return
            
        self.segments[name] = LEDSegment(name, start_idx, length, flow_direction)
        logger.info(f"Added LED segment '{name}' at index {start_idx} (len: {length})")

    def set_flow_speed(self, name: str, speed: float):
        """Mengatur kecepatan aliran segmen. 0 = berhenti."""
        if name in self.segments:
            self.segments[name].speed = speed

    def set_heat_ratio(self, name: str, ratio: float):
        """Mengatur rasio panas (0.0 = biru total, 1.0 = ada gradien merah)."""
        if name in self.segments:
            self.segments[name].update_heat_ratio(ratio)

    def set_fill_level(self, name: str, level: float, r: int, g: int, b: int):
        """Mengatur mode segment sebagai bar level terisi warna tertentu."""
        if name in self.segments:
            self.segments[name].fill_level = max(0.0, min(1.0, level))
            self.segments[name].fill_color = Color(r, g, b)
            self.segments[name].fill_rgb = (r, g, b)

    def clear(self):
        """Mematikan seluruh LED."""
        for i in range(self.count):
            self.strip.setPixelColor(i, self.color_black)
        self.strip.show()

    def start(self):
        """Memulai thread animasi LED."""
        if self._thread is not None and self._thread.is_alive():
            return
            
        self.running = True
        self.clear()
        self._thread = threading.Thread(target=self._animation_loop, daemon=True, name="LedStripAnimation")
        self._thread.start()
        logger.info("LED Strip Animation started.")

    def stop(self):
        """Menghentikan thread animasi LED."""
        self.running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.clear()
        logger.info("LED Strip Animation stopped.")

    def _animation_loop(self):
        last_time = time.time()
        
        while self.running:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            
            # Matikan semua pixel dulu sebagai base
            for i in range(self.count):
                self.strip.setPixelColor(i, self.color_black)
                
            # Render setiap segmen
            for name, seg in self.segments.items():
                if seg.fill_level >= 0.0:
                    # Mode fill: nyalakan lampu sejumlah fill_level
                    lit_count = int(seg.fill_level * seg.length)
                    
                    # Tambahkan animasi jika speed > 0
                    if seg.speed > 0.0:
                        seg.offset -= (seg.speed * seg.flow_direction * dt * 20.0)
                    int_offset = int(seg.offset)

                    for i in range(seg.length):
                        if i < lit_count:
                            # Jika animasi berjalan, buat efek gelembung/pola
                            if seg.speed > 0.0 and ((i + int_offset) % self.pattern_total) >= self.pattern_on:
                                # Matikan lampu untuk pola "mati" agar efek gelembung/ombak sangat kontras terlihat
                                self.strip.setPixelColor(seg.start_idx + i, self.color_black)
                            else:
                                self.strip.setPixelColor(seg.start_idx + i, seg.fill_color)
                        else:
                            self.strip.setPixelColor(seg.start_idx + i, self.color_black)
                else:
                    # Mode flow: update offset berdasarkan speed
                    if seg.speed <= 0.0:
                        # Jika pompa mati (speed 0), matikan semua LED di segmen ini
                        for i in range(seg.length):
                            self.strip.setPixelColor(seg.start_idx + i, self.color_black)
                    else:
                        seg.offset -= (seg.speed * seg.flow_direction * dt * 20.0) 
                        int_offset = int(seg.offset)
                        
                        for i in range(seg.length):
                            # Pola aliran 5 nyala, 5 mati
                            if ((i + int_offset) % self.pattern_total) < self.pattern_on:
                                # Pixel nyala, gunakan warna gradien segmen
                                self.strip.setPixelColor(seg.start_idx + i, seg.gradient[i])
            
            # Use lock to prevent hardware conflict between two PWM channels
            with ws281x_lock:
                try:
                    self.strip.show()
                except RuntimeError as e:
                    logger.error(f"WS281x render failed (DMA Error): {e}")
                    self.running = False
                    break
                
            time.sleep(self.update_interval)
