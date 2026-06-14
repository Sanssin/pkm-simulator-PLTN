import os
import logging

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logger = logging.getLogger(__name__)

class CpuManager:
    """
    Manages CPU affinity and process priority to ensure hardware tasks
    (like WS2812 LED timing and physical simulations) run without interruption.
    """

    @staticmethod
    def setup_hardware_node():
        """
        Mengoptimalkan process saat ini sebagai node Hardware/Backend.
        - Membatasi eksekusi pada Core 0 dan Core 1.
        - Meningkatkan prioritas proses.
        """
        logger.info("Setting up CPU optimization for Hardware Node...")
        CpuManager.set_affinity([0, 1])
        CpuManager.set_high_priority()
        CpuManager.setup_os_optimizations()

    @staticmethod
    def setup_os_optimizations():
        """
        [CPU-023] System startup optimization.
        Set CPU governor to performance and pin IRQs to Core 0.
        Requires root/sudo privileges on Linux.
        """
        if os.name == 'nt':
            return
            
        logger.info("Menerapkan OS-level optimizations (Governor & IRQ Affinity)...")
        try:
            # 1. Set CPU Governor ke performance (menghilangkan lag / dynamic scaling latency)
            # Akan memaksa CPU Raspberry Pi berjalan pada clock maksimal terus-menerus.
            os.system("echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null 2>&1")
            logger.info("CPU scaling governor diatur ke 'performance'.")
            
            # 2. IRQ Affinity: Mengarahkan semua interupsi hardware (USB/Network/Touch) ke Core 0
            # Mask '1' dalam hex merepresentasikan Core 0.
            # Ini membebaskan Core 1, 2, 3 dari interupsi acak OS sehingga simulasi lebih stabil.
            os.system("find /proc/irq/ -name smp_affinity -exec sh -c 'echo 1 > {}' \\; > /dev/null 2>&1")
            logger.info("Hardware IRQ affinity dikunci ke Core 0.")
        except Exception as e:
            logger.warning(f"Gagal menerapkan OS optimizations (mungkin butuh akses sudo): {e}")

    @staticmethod
    def setup_ui_node():
        """
        Mengoptimalkan process UI/Video Player.
        - Membatasi eksekusi pada Core 2 dan Core 3.
        - Prioritas standar.
        """
        logger.info("Setting up CPU optimization for UI Node...")
        CpuManager.set_affinity([2, 3])
        CpuManager.set_normal_priority()

    @staticmethod
    def set_affinity(cores: list):
        """Membatasi process ini agar hanya berjalan di core tertentu."""
        if not HAS_PSUTIL:
            logger.warning("psutil module not installed. Cannot set CPU affinity. Run: pip install psutil")
            return
            
        try:
            p = psutil.Process()
            if hasattr(p, 'cpu_affinity'):
                p.cpu_affinity(cores)
                logger.info(f"CPU Affinity berhasil diatur ke core: {cores}")
            else:
                logger.warning("OS saat ini tidak mendukung pengaturan CPU Affinity via psutil.")
        except Exception as e:
            logger.error(f"Gagal mengatur CPU Affinity: {e}")

    @staticmethod
    def set_high_priority():
        """Mengatur prioritas proses menjadi tinggi (High / Real-time)."""
        if not HAS_PSUTIL:
            logger.warning("psutil module not installed. Cannot set High Priority.")
            return
            
        try:
            p = psutil.Process()
            if os.name == 'nt':
                p.nice(psutil.HIGH_PRIORITY_CLASS)
            else:
                p.nice(-10) # Semakin negatif semakin tinggi prioritasnya (butuh akses sudo/root)
            logger.info("Prioritas proses CPU ditingkatkan (High Priority).")
        except psutil.AccessDenied:
            logger.warning("Gagal menaikkan prioritas CPU: Akses ditolak (Jalankan dengan sudo).")
        except Exception as e:
            logger.error(f"Gagal mengatur prioritas tinggi: {e}")

    @staticmethod
    def set_normal_priority():
        """Mengatur prioritas proses kembali ke normal."""
        if not HAS_PSUTIL:
            return
            
        try:
            p = psutil.Process()
            if os.name == 'nt':
                p.nice(psutil.NORMAL_PRIORITY_CLASS)
            else:
                p.nice(0)
            logger.info("Prioritas proses CPU dikembalikan ke Normal.")
        except Exception as e:
            logger.error(f"Gagal mengatur prioritas normal: {e}")
