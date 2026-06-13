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
