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

            # 1. 00:00 - 00:28 (Opening: Startup Bertahap Menuju Operasi Normal)
            # Fase ini meniru urutan startup AutoSimulator
            
            # 1a. t=0~5s: Naikkan tekanan awal (pre-pressurize)
            logger.info("--- 00:00 OPENING: Pre-pressurize ---")
            with self._state_manager as state:
                state.auto_sim_phase = "Startup: Menaikkan Tekanan..."
                state.reactor_active = True
            while time.time() - start_time < 5.0:
                if self._cancelled: return
                elapsed = time.time() - start_time
                progress = min(elapsed / 5.0, 1.0)
                with self._state_manager as state:
                    state.pressure = 45.0 * progress
                time.sleep(0.1)

            # 1b. t=5s: Pompa Tersier ON
            logger.info("--- 00:05 Pompa Tersier ON ---")
            with self._state_manager as state:
                state.pump_tertiary_status = PUMP_ON
                state.auto_sim_phase = "Startup: Pompa Tersier Aktif"
            if not wait_until(10.0): return

            # 1c. t=10s: Pompa Sekunder ON
            logger.info("--- 00:10 Pompa Sekunder ON ---")
            with self._state_manager as state:
                state.pump_secondary_status = PUMP_ON
                state.auto_sim_phase = "Startup: Pompa Sekunder Aktif"
            if not wait_until(15.0): return

            # 1d. t=15s: Pompa Primer ON
            logger.info("--- 00:15 Pompa Primer ON ---")
            with self._state_manager as state:
                state.pump_primary_status = PUMP_ON
                state.auto_sim_phase = "Startup: Pompa Primer Aktif"
            if not wait_until(18.0): return

            # 1e. t=18~28s: Ramp semua parameter ke kondisi operasi normal (10 detik)
            logger.info("--- 00:18 Ramping to full power ---")
            with self._state_manager as state:
                state.auto_sim_phase = "Startup: Menuju Operasi Normal..."
            while time.time() - start_time < 28.0:
                if self._cancelled: return
                elapsed = time.time() - start_time
                progress = min((elapsed - 18.0) / 10.0, 1.0)
                
                # Sequential rod raising
                safety_prog = min(max(progress / 0.333, 0.0), 1.0)
                shim_prog = min(max((progress - 0.333) / 0.333, 0.0), 1.0)
                reg_prog = min(max((progress - 0.666) / 0.334, 0.0), 1.0)
                
                # Power generation starts only when shim & reg rods are pulled
                power_prog = (shim_prog + reg_prog) / 2.0
                
                with self._state_manager as state:
                    state.safety_rod = 100.0 * safety_prog
                    state.shim_rod = 100.0 * shim_prog
                    state.regulating_rod = 100.0 * reg_prog
                    
                    # Power follows the rod heights
                    state.pressure = 45.0 + (150.0 - 45.0) * power_prog
                    state.thermal_kw = 300000.0 * power_prog
                    state.turbine_speed = 100.0 * power_prog
                    
                    # Artificially sync temperatures so pipe colors match turbine speed immediately
                    # Physics engine will naturally take over after this
                    state.temperature_core = max(state.temperature_core, 25.0 + (320.0 - 25.0) * power_prog)
                    state.temperature_fuel_cladding = max(state.temperature_fuel_cladding, 25.0 + (310.0 - 25.0) * power_prog)
                    state.temperature_coolant_primary = max(state.temperature_coolant_primary, 25.0 + (300.0 - 25.0) * power_prog)
                    state.temperature_coolant_secondary = max(state.temperature_coolant_secondary, 25.0 + (280.0 - 25.0) * power_prog)
                    state.temperature_coolant = state.temperature_coolant_primary
                time.sleep(0.1)

            if not wait_until(29.0): return

            # 2. 00:29 - Mulai LOFA (Primary Pump fails)
            logger.warning("--- 00:29 LOFA TRIGGERED ---")
            with self._state_manager as state:
                state.pump_primary_status = PUMP_OFF
                state.lofa_primary = True    # Flag LOFA aktif untuk indikator LED/display
                state.auto_sim_phase = "LOFA: Kegagalan Pompa Primer!"
                
            if not wait_until(120.0): return

            # 3. 02:00 - Batang Kendali Turun (SCRAM internal)
            logger.warning("--- 02:00 SCRAM: Batang Kendali Turun ---")
            with self._state_manager as state:
                state.auto_sim_phase = "LOFA: Batang Kendali Turun (SCRAM)"
                state.emergency_active = True
            
            # Animasi drop rod & power secara cepat selama 3 detik
            scram_start = time.time()
            while time.time() - scram_start < 3.0:
                if self._cancelled: return
                elapsed = time.time() - scram_start
                progress = min(elapsed / 3.0, 1.0)
                with self._state_manager as state:
                    state.safety_rod = 100.0 * (1.0 - progress)
                    state.shim_rod = 100.0 * (1.0 - progress)
                    state.regulating_rod = 100.0 * (1.0 - progress)
                    state.thermal_kw = 300000.0 * (1.0 - progress)
                    state.turbine_speed = 100.0 * (1.0 - progress)
                time.sleep(0.1)

            if not wait_until(185.0): return

            # 4. 03:05 - Selesai LOFA (pump sekunder & tersier mati)
            logger.warning("--- 03:05 SHUTDOWN SEQUENCE ---")
            with self._state_manager as state:
                state.pump_secondary_status = PUMP_OFF
                state.pump_tertiary_status = PUMP_OFF
                state.auto_sim_phase = "LOFA: Selesai"

            # 5. 03:06-03:29 - Closing (Tunggu video habis)
            if not wait_until(209.0): return
            
            logger.info("--- 03:29 CINEMATIC LOFA ENDED ---")
            
            # Setelah video selesai, baru trigger SCRAM secara sistem (agar lampu sirine nyala)
            with self._state_manager as state:
                state.emergency_active = True
                state.auto_sim_phase = "Simulasi Selesai"
            
        except Exception as e:
            logger.error(f"Cinematic LOFA Sequence error: {e}")
        finally:
            self._running = False
            with self._state_manager as state:
                if not self._cancelled:
                    state.reset()
                    # Set mode ke idle agar tampilan kembali ke menu utama
                    state.simulation_mode = 'idle'
                # Clear emergency agar UI tidak terjebak di status bahaya
                state.emergency_active = False
                state.auto_sim_phase = ""

