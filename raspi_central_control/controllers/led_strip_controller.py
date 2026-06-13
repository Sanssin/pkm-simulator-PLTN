import time
import logging
import threading
from rpi_ws281x import PixelStrip, Color

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
        
        # Pre-compute gradient for this segment
        self.gradient = self._generate_gradient()

    def _generate_gradient(self):
        gradient_colors = [Color(0,0,0)] * self.length
        
        grad_len = min(71, self.length) # Use 71 or max length
        grad_start = (self.length - grad_len) // 2
        grad_end = grad_start + grad_len - 1

        red = (255, 0, 0)
        blue = (0, 0, 255)

        for i in range(self.length):
            if i < grad_start:
                gradient_colors[i] = Color(red[0], red[1], red[2])
            elif i <= grad_end:
                t = (i - grad_start) / (max(1, grad_len - 1))
                r = int(red[0] * (1 - t) + blue[0] * t)
                g = int(red[1] * (1 - t) + blue[1] * t)
                b = int(red[2] * (1 - t) + blue[2] * t)
                gradient_colors[i] = Color(r, g, b)
            else:
                gradient_colors[i] = Color(blue[0], blue[1], blue[2])
                
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
        
        self.strip = PixelStrip(
            self.count, self.pin, self.freq_hz, self.dma, 
            self.invert, self.brightness, self.channel
        )
        self.strip.begin()
        
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

    def set_fill_level(self, name: str, level: float, r: int, g: int, b: int):
        """Mengatur mode segment sebagai bar level terisi warna tertentu."""
        if name in self.segments:
            self.segments[name].fill_level = max(0.0, min(1.0, level))
            self.segments[name].fill_color = Color(r, g, b)

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
                    for i in range(seg.length):
                        if i < lit_count:
                            self.strip.setPixelColor(seg.start_idx + i, seg.fill_color)
                        else:
                            self.strip.setPixelColor(seg.start_idx + i, self.color_black)
                else:
                    # Mode flow: update offset berdasarkan speed
                    seg.offset -= (seg.speed * seg.flow_direction * dt * 20.0) 
                    int_offset = int(seg.offset)
                    
                    for i in range(seg.length):
                        # Pola aliran 5 nyala, 5 mati
                        if ((i + int_offset) % self.pattern_total) < self.pattern_on:
                            # Pixel nyala, gunakan warna gradien segmen
                            self.strip.setPixelColor(seg.start_idx + i, seg.gradient[i])
            
            self.strip.show()
            time.sleep(self.update_interval)

