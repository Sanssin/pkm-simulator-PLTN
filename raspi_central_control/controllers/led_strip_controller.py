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
        self.is_active = False # Tambahkan is_active (default False sampai pompa dihidupkan)
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
        # Warna panas bertransisi dari Biru (dingin) ke warna panas maksimum
        target_hot = (255, 0, 0)
        hot_r = int(blue[0] * (1.0 - self.heat_ratio) + target_hot[0] * self.heat_ratio)
        hot_g = int(blue[1] * (1.0 - self.heat_ratio) + target_hot[1] * self.heat_ratio)
        hot_b = int(blue[2] * (1.0 - self.heat_ratio) + target_hot[2] * self.heat_ratio)
        hot_color = (hot_r, hot_g, hot_b)

        # Aliran Tersier (Kondenser & Cooling Tower): Dihubungkan menjadi satu logika
        # Lampu 1-23 di kondenser: Biru solid (pasokan air laut dingin)
        # Sisa kondenser & tersier_out: Warna panas bergantung suhu uap sekunder
        if self.name in ['kondenser', 'tersier_out']:
            if self.heat_ratio < 0.2:
                hot_t = blue
            else:
                # Transisi bertahap, memerah jauh lebih cepat pada hr=0.65
                prog = (self.heat_ratio - 0.2) / 0.45
                prog = max(0.0, min(1.0, prog))
                t_r = int(blue[0] * (1.0 - prog) + target_hot[0] * prog)
                t_g = int(blue[1] * (1.0 - prog) + target_hot[1] * prog)
                t_b = int(blue[2] * (1.0 - prog) + target_hot[2] * prog)
                hot_t = (t_r, t_g, t_b)
                
            for i in range(self.length):
                if self.name == 'kondenser' and i < 23:
                    gradient_colors[i] = Color(blue[0], blue[1], blue[2])
                else:
                    gradient_colors[i] = Color(hot_t[0], hot_t[1], hot_t[2])
            return gradient_colors

        # Pipa air laut (tersier_in) menuju kondenser: Biru solid (dingin)
        if self.name == 'tersier_in':
            for i in range(self.length):
                gradient_colors[i] = Color(blue[0], blue[1], blue[2])
            return gradient_colors

        # Aliran balik sekunder (sekunder_in) dari kondenser: Orange meredup dan gradual
        if self.name == 'sekunder_in':
            # Sekunder baru menghangat setelah panas primer ditransfer
            if self.heat_ratio < 0.15:
                # Reaktor belum cukup panas (atau mati), air masih fase biru (Dingin)
                warm_r, warm_g, warm_b = blue
            else:
                # Transisi bertahap, mencapai maksimal jauh lebih cepat pada hr=0.60
                prog = (self.heat_ratio - 0.15) / 0.45
                prog = max(0.0, min(1.0, prog))
                
                # Target warna air hangat (Liquid): Deep Purple / Violet (R=150, G=0, B=150)
                warm_r = int(150 * prog)       
                warm_g = 0        
                warm_b = int(255 - (105 * prog)) # Turun dari 255 ke 150
            
            for i in range(self.length):
                gradient_colors[i] = Color(warm_r, warm_g, warm_b)
            return gradient_colors

        # Aliran uap sekunder (sekunder_out) menuju turbin: Warna Peach
        if self.name == 'sekunder_out':
            if self.heat_ratio <= 0.01:
                # Reaktor benar-benar mati, warna putih menyala statis
                steam_r, steam_g, steam_b = (255, 255, 255)
            else:
                # Transisi SANGAT CEPAT ke Peach saat mulai ada daya sekecil apapun
                prog = (self.heat_ratio - 0.01) / 0.04
                prog = max(0.0, min(1.0, prog))
                
                # Target warna uap panas: Peach / Soft Pink (R=200, G=80, B=100)
                steam_r = int(blue[0] * (1.0 - prog) + 200 * prog)       
                steam_g = int(blue[1] * (1.0 - prog) + 80 * prog)        
                steam_b = int(blue[2] * (1.0 - prog) + 100 * prog)
            
            for i in range(self.length):
                gradient_colors[i] = Color(steam_r, steam_g, steam_b)
            return gradient_colors



        # Pipa primer: Normalnya (hingga 320C, hr_primary ~0.83) batas merah di index 26.
        # Saat LOFA (temp > 320C, hr_primary -> 1.0), air panas tidak didinginkan sehingga 
        # titik perpotongan (batas) merah akan bergeser ke seluruh pipa (hingga self.length).
        if self.name == 'primer':
            # Jika reaktor mati/hanya hangat (< 0.05 heat ratio ~ 42C), kembalikan ke warna biru.
            # Primer menjadi aliran pertama yang berubah warna secara visual
            if self.heat_ratio < 0.05:
                primer_r, primer_g, primer_b = blue
                ret_r, ret_g, ret_b = blue
            else:
                # Transisi halus, memerah sempurna jauh lebih awal (hr=0.50)
                # Agar aliran primer dijamin merah menyala kuat saat operasi
                prog = (self.heat_ratio - 0.05) / 0.45
                prog = max(0.0, min(1.0, prog))
                primer_r = int(blue[0] * (1 - prog) + 255 * prog)
                primer_g = int(blue[1] * (1 - prog))
                primer_b = int(blue[2] * (1 - prog))
                
                # Warna balikan primer (setelah mentransfer panas) tidak dingin (biru)
                # tetapi masih hangat (Deep Purple / Violet) merepresentasikan air cair
                ret_r = int(150 * prog)
                ret_g = 0
                ret_b = int(255 - (105 * prog))
                
            hot_color = (primer_r, primer_g, primer_b)
            return_color = (ret_r, ret_g, ret_b)
            
            # Geser titik panas bertambah 2 lampu sehingga aliran panas lebih panjang
            base_boundary = 35
            hr_normal = 0.83
            
            if self.heat_ratio <= hr_normal:
                hot_boundary = base_boundary
            else:
                # Pergeseran proporsional dari 0.83 hingga 1.0 (batas self.length)
                excess_ratio = (self.heat_ratio - hr_normal) / (1.0 - hr_normal)
                hot_boundary = base_boundary + int(excess_ratio * (self.length - base_boundary))
                
            # Gradasinya digeser untuk titik perubahan suhunya
            blend_len = 16  # Mempersempit area gradasi sedikit agar transisi lebih jelas
            grad_start = hot_boundary - (blend_len // 2)
            grad_end = grad_start + blend_len
            
            for i in range(self.length):
                if i < grad_start:
                    gradient_colors[i] = Color(hot_color[0], hot_color[1], hot_color[2])
                elif i <= grad_end:
                    t = (i - grad_start) / max(1, blend_len)
                    r = int(hot_color[0] * (1-t) + return_color[0] * t)
                    g = int(hot_color[1] * (1-t) + return_color[1] * t)
                    b = int(hot_color[2] * (1-t) + return_color[2] * t)
                    gradient_colors[i] = Color(r, g, b)
                else:
                    # Akhir: Warna Balikan Primer (hangat, bukan dingin)
                    gradient_colors[i] = Color(return_color[0], return_color[1], return_color[2])
                    
            return gradient_colors

        # Default: Gradien halus untuk segmen lain (sekunder, tersier)
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
        self.color_black = Color(0, 0, 0)
        # PENTING: Jangan gunakan `* 3` — itu membuat 3 referensi ke objek yang SAMA!
        self.pump_indicators = [
            (Color(0, 0, 0), False),
            (Color(0, 0, 0), False),
            (Color(0, 0, 0), False),
        ]
        
        # Ambil index pompa langsung dari config jika tersedia
        import raspi_config as config
        pump_inds_cfg = getattr(config, 'LED_SEGMENT_PUMP_INDS', (327, 3))
        self.pump_inds_start = pump_inds_cfg[0]
        self.pump_inds_count = pump_inds_cfg[1]  # Seharusnya 3
        self.pump_inds_set = set(range(self.pump_inds_start, self.pump_inds_start + pump_inds_cfg[1]))
        
        self.running = False
        self._thread = None
        
        self.pattern_total = 10
        self.pattern_on = 5
        self.update_interval = 0.05 # 50ms updates

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
            if speed > 0.0:
                self.segments[name].is_active = True

    def set_active(self, name: str, active: bool):
        """Mengatur apakah segmen ini dirender atau digelapkan."""
        if name in self.segments:
            self.segments[name].is_active = active

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

    def set_pump_indicator(self, pump_idx: int, r: int, g: int, b: int, blink: bool):
        """Mengatur warna dan status kedip untuk indikator pompa (0=primer, 1=sekunder, 2=tersier)."""
        if 0 <= pump_idx < 3:
            self.pump_indicators[pump_idx] = (Color(r, g, b), blink)

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
                        idx = seg.start_idx + i
                        if idx < self.count:
                            # Lewati index yang dipakai pump indicators
                            if idx in self.pump_inds_set:
                                continue
                            if i < lit_count:
                                # Jika animasi berjalan, buat efek gelembung/pola
                                if seg.speed > 0.0 and ((i + int_offset) % self.pattern_total) >= self.pattern_on:
                                    self.strip.setPixelColor(idx, self.color_black)
                                else:
                                    self.strip.setPixelColor(idx, seg.fill_color)
                            else:
                                self.strip.setPixelColor(idx, self.color_black)
                else:
                    # Mode flow: update offset berdasarkan speed
                    if seg.speed > 0.0:
                        seg.offset -= (seg.speed * seg.flow_direction * dt * 20.0) 
                        
                    int_offset = int(seg.offset)
                    
                    for i in range(seg.length):
                        idx = seg.start_idx + i
                        if idx < self.count:
                            # Lewati index yang dipakai pump indicators — akan dirender terpisah
                            if idx in self.pump_inds_set:
                                continue
                                
                            if not seg.is_active:
                                self.strip.setPixelColor(idx, self.color_black)
                                continue
                                
                            # Pola aliran 5 nyala, 5 mati
                            # Jika speed 0, posisi stuck (diam)
                            # Khusus sekunder_out saat diam (belum ada uap), render solid (putih penuh) tanpa putus-putus
                            if name == 'sekunder_out' and seg.speed <= 0.0:
                                self.strip.setPixelColor(idx, seg.gradient[i])
                            elif ((i + int_offset) % self.pattern_total) < self.pattern_on:
                                self.strip.setPixelColor(idx, seg.gradient[i])
                            else:
                                self.strip.setPixelColor(idx, self.color_black)

            # Pump indicator rendering DINONAKTIFKAN SEMENTARA
            # (3 LED pompa digabung ke segmen primer untuk tes aliran)
            # Aktifkan kembali setelah konfirmasi aliran primer OK
            # blink_state = int(current_time * 4) % 2 == 0
            # for i in range(3):
            #     idx = self.pump_inds_start + i
            #     if idx < self.count:
            #         color, blink = self.pump_indicators[i]
            #         if blink and not blink_state:
            #             self.strip.setPixelColor(idx, self.color_black)
            #         else:
            #             self.strip.setPixelColor(idx, color)
            
            # Use lock to prevent hardware conflict between two PWM channels
            with ws281x_lock:
                try:
                    self.strip.show()
                except RuntimeError as e:
                    logger.error(f"WS281x render failed (DMA Error): {e}")
                    self.running = False
                    break
                
            time.sleep(self.update_interval)
