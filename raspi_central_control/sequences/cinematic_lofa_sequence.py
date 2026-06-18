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
            # 0. INITIALIZATION
            with self._state_manager as state:
                state.reset()
                state.simulation_mode = 'cinematic_lofa'
                state.auto_sim_phase = "Opening..."
                # Mark as running so display knows not to return to IDLE
                state.auto_sim_running = True
                state.pump_tertiary_status = PUMP_ON
                state.pump_secondary_status = PUMP_ON
                state.pump_primary_status = PUMP_ON

            # Helper to wait until exactly `target_seconds` have passed since start
            def wait_until(target_seconds: float) -> bool:
                while time.time() - start_time < target_seconds:
                    if self._cancelled: return False
                    time.sleep(0.1)
                return True

            # 1. 00:00 - 00:16 (Opening: Ramp to Normal)
            # Ramp parameters linearly up to 16 seconds
            while time.time() - start_time < 16.0:
                if self._cancelled: return
                elapsed = time.time() - start_time
                progress = min(elapsed / 16.0, 1.0)
                
                with self._state_manager as state:
                    state.pressure = 150.0 * progress
                    state.safety_rod = 100.0 * progress
                    state.shim_rod = 50.0 * progress
                    state.regulating_rod = 50.0 * progress
                    state.thermal_kw = 250000.0 * progress
                    state.temperature_core = 25.0 + (280.0 - 25.0) * progress
                    state.temperature_coolant_primary = 25.0 + (300.0 - 25.0) * progress
                    state.turbine_speed = 100.0 * progress
                    state.reactor_active = True
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
                state.user_interacted = True   # Cegah display kembali ke IDLE
                # Clear emergency agar UI tidak terjebak di status bahaya
                state.emergency_active = False
                state.auto_sim_phase = ""

