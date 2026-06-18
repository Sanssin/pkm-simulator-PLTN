"""
Cinematic LOFA Sequence
Designed to match the exactly 3:29 (209 seconds) simulasi_lofa.mp4 video.
"""

import time
import logging
import threading
from typing import Optional, TYPE_CHECKING
from controllers.interlock_validator import PUMP_ON, PUMP_OFF

if TYPE_CHECKING:
    from controllers.state_manager import StateManager

logger = logging.getLogger(__name__)

class CinematicLOFASequence:
    def __init__(self, state_manager: 'StateManager'):
        self._state_manager = state_manager
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> threading.Thread:
        if self._running:
            return self._thread
        
        self._cancelled = False
        self._thread = threading.Thread(target=self._simulation_thread, daemon=True, name="CinematicLOFASequenceThread")
        self._thread.start()
        return self._thread

    def cancel(self) -> None:
        self._cancelled = True
        with self._state_manager as state:
            if state.simulation_mode == 'cinematic_lofa':
                state.simulation_mode = 'manual'
        logger.warning("Cinematic LOFA sequence cancelled")

    def _simulation_thread(self) -> None:
        self._running = True
        logger.info("--- STARTING CINEMATIC LOFA SIMULATION (3:29) ---")
        start_time = time.time()
        
        try:
            # 0. INITIALIZATION - semua OFF, mode siap
            with self._state_manager as state:
                state.reset()
                state.simulation_mode = 'cinematic_lofa'
                state.auto_sim_phase = "Inisialisasi Sistem..."
                # Pompa masih OFF saat init - akan dihidupkan bertahap
                state.pump_tertiary_status = PUMP_OFF
                state.pump_secondary_status = PUMP_OFF
                state.pump_primary_status = PUMP_OFF

            # Helper to wait until exactly `target_seconds` have passed since start
            def wait_until(target_seconds: float) -> bool:
                while time.time() - start_time < target_seconds:
                    if self._cancelled: return False
                    time.sleep(0.1)
                return True

            # 1. 00:00 - 00:16 (Opening: Startup Bertahap Menuju Operasi Normal)
            # Fase ini meniru urutan startup AutoSimulator:
            # Tekanan naik → Pompa Tersier ON → Pompa Sekunder ON → Pompa Primer ON
            # → Parameter naik ke nilai normal
            
            # 1a. t=0~3s: Naikkan tekanan awal (pre-pressurize)
            logger.info("--- 00:00 OPENING: Pre-pressurize ---")
            with self._state_manager as state:
                state.auto_sim_phase = "Startup: Menaikkan Tekanan..."
                state.reactor_active = True
            while time.time() - start_time < 3.0:
                if self._cancelled: return
                elapsed = time.time() - start_time
                progress = min(elapsed / 3.0, 1.0)
                with self._state_manager as state:
                    state.pressure = 45.0 * progress
                time.sleep(0.1)

            # 1b. t=3s: Pompa Tersier ON (pertama)
            logger.info("--- 00:03 Pompa Tersier ON ---")
            with self._state_manager as state:
                state.pump_tertiary_status = PUMP_ON
                state.auto_sim_phase = "Startup: Pompa Tersier Aktif"
            if not wait_until(6.0): return

            # 1c. t=6s: Pompa Sekunder ON
            logger.info("--- 00:06 Pompa Sekunder ON ---")
            with self._state_manager as state:
                state.pump_secondary_status = PUMP_ON
                state.auto_sim_phase = "Startup: Pompa Sekunder Aktif"
            if not wait_until(9.0): return

            # 1d. t=9s: Pompa Primer ON
            logger.info("--- 00:09 Pompa Primer ON ---")
            with self._state_manager as state:
                state.pump_primary_status = PUMP_ON
                state.auto_sim_phase = "Startup: Pompa Primer Aktif"
            if not wait_until(11.0): return

            # 1e. t=11~16s: Ramp semua parameter ke kondisi operasi normal
            logger.info("--- 00:11 Ramping to full power ---")
            with self._state_manager as state:
                state.auto_sim_phase = "Startup: Menuju Operasi Normal..."
            while time.time() - start_time < 16.0:
                if self._cancelled: return
                elapsed = time.time() - start_time
                # progress 0→1 selama 11~16 detik
                progress = min((elapsed - 11.0) / 5.0, 1.0)
                with self._state_manager as state:
                    state.pressure = 45.0 + (150.0 - 45.0) * progress
                    state.safety_rod = 100.0 * progress
                    state.shim_rod = 50.0 * progress
                    state.regulating_rod = 50.0 * progress
                    state.thermal_kw = 250000.0 * progress
                    state.temperature_core = 25.0 + (280.0 - 25.0) * progress
                    state.temperature_coolant_primary = 25.0 + (300.0 - 25.0) * progress
                    state.turbine_speed = 100.0 * progress
                time.sleep(0.1)

            if not wait_until(17.0): return

            # 2. 00:17 - Mulai LOFA (Primary Pump fails)
            # NOTE: Kita TIDAK men-set emergency_active = True di sini karena
            # itu akan menyebabkan display app beralih dari mode VIDEO ke MANUAL.
            # Biarkan video selesai terlebih dahulu (sampai t=209s).
            logger.warning("--- 00:17 LOFA TRIGGERED ---")
            with self._state_manager as state:
                state.pump_primary_status = PUMP_OFF
                state.lofa_primary = True    # Flag LOFA aktif untuk indikator LED/display
                state.auto_sim_phase = "LOFA: Kegagalan Pompa Primer!"
                
            # Biarkan fisika LOFA berjalan alami, tapi JANGAN trigger SCRAM/emergency
            # sampai video hampir selesai (mendekati akhir video 3:29).
            # Kita simulasikan panas naik perlahan untuk animasi LED.
            if not wait_until(185.0): return

            # 3. 03:05 - Mulai menutup (pump sekunder & tersier mati)
            # Masih dalam mode cinematic_lofa, BELUM ubah ke emergency
            logger.warning("--- 03:05 SHUTDOWN SEQUENCE ---")
            with self._state_manager as state:
                state.pump_secondary_status = PUMP_OFF
                state.pump_tertiary_status = PUMP_OFF
                state.auto_sim_phase = "LOFA: Shutdown Sistem..."

            # 4. Tunggu hingga video benar-benar selesai di 03:29 (209s)
            if not wait_until(209.0): return
            
            logger.info("--- 03:29 CINEMATIC LOFA ENDED ---")
            
            # 5. Setelah video selesai, baru trigger SCRAM dan pindah ke manual
            with self._state_manager as state:
                state.emergency_active = True
                state.auto_sim_phase = "LOFA Selesai: SCRAM Darurat"
            
            # Beri waktu 1 detik agar display sempat mendeteksi emergency sebelum reset
            time.sleep(1.0)
            
        except Exception as e:
            logger.error(f"Cinematic LOFA Sequence error: {e}")
        finally:
            self._running = False
            with self._state_manager as state:
                state.reset()
                # Set mode ke manual agar tampilan kembali ke menu utama
                state.simulation_mode = 'manual'
                # Clear emergency agar UI tidak terjebak di status bahaya
                state.emergency_active = False
                state.auto_sim_phase = ""

