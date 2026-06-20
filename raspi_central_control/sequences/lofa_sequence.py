"""
LOFASequence - Automated Loss of Flow Accident simulation sequence.

This module handles the automatic setup of a LOFA scenario.
It brings the reactor to a normal operating state, and then simulates
a primary pump failure to demonstrate the system's safety response.
"""

import time
import logging
import threading
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING
from controllers.interlock_validator import PUMP_ON, PUMP_OFF

if TYPE_CHECKING:
    from controllers.state_manager import StateManager
from controllers.physics_engine import PhysicsEngine
from .base_sequence import SimulationSequence

logger = logging.getLogger(__name__)

class LofaPhase(Enum):
    """Simulation phases for auto LOFA sequence."""
    IDLE = auto()
    PREPARE = auto()
    NORMAL_OPS = auto()
    PUMP_FAILURE = auto()
    OBSERVATION = auto()
    COMPLETE = auto()

class LOFASequence(SimulationSequence):
    """
    Automated LOFA simulation sequence.
    
    Quickly sets up the reactor to normal operating conditions,
    then deliberately fails the primary pump.
    """
    
    def __init__(self, state_manager: 'StateManager', physics_engine: PhysicsEngine):
        super().__init__(state_manager)
        self.physics_engine = physics_engine
        self._current_phase = LofaPhase.IDLE
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None
        
    @property
    def is_running(self) -> bool:
        return self._running
        
    def start(self) -> threading.Thread:
        if self._running:
            logger.warning("LOFA sequence already running!")
            return self._thread
            
        self._cancelled = False
        self._thread = threading.Thread(target=self._simulation_thread, daemon=True, name="LOFASequenceThread")
        self._thread.start()
        return self._thread
        
    def cancel(self) -> None:
        self._cancelled = True
        with self._state_manager as state:
            state.auto_sim_running = False
            state.simulation_mode = 'manual'
            state.auto_sim_phase = ""
        logger.warning("LOFA sequence cancelled by user")
        
    def _check_cancelled(self) -> bool:
        if self._cancelled:
            return True
        with self._state_manager as state:
            return not state.auto_sim_running
            
    def _set_phase(self, phase: LofaPhase, label: str) -> None:
        self._current_phase = phase
        with self._state_manager as state:
            state.auto_sim_phase = label

    def _ramp_value(self, field: str, start: float, target: float, 
                    duration: float, is_int: bool = False) -> bool:
        start_time = time.time()
        while time.time() - start_time < duration:
            if self._check_cancelled(): return False
            elapsed = time.time() - start_time
            progress = elapsed / duration
            current = start + (target - start) * progress
            if is_int: current = int(current)
            with self._state_manager as state:
                setattr(state, field, current)
            time.sleep(0.05)
        
        final_value = int(target) if is_int else target
        with self._state_manager as state:
            setattr(state, field, final_value)
        return True

    def _simulation_thread(self) -> None:
        """Main sequence logic."""
        self._running = True
        logger.info("--- STARTING LOFA SIMULATION SEQUENCE ---")
        
        try:
            # 1. PREPARE: Reset and set to Auto mode
            with self._state_manager as state:
                state.reset()
                state.simulation_mode = 'auto'
                state.auto_sim_running = True
                
            self._set_phase(LofaPhase.PREPARE, "Menyiapkan Skenario...")
            time.sleep(1.0)
            if self._check_cancelled(): return
            
            # 2. NORMAL_OPS: Fast Ramp to Normal Operation (approx 10 seconds)
            self._set_phase(LofaPhase.NORMAL_OPS, "Mempercepat ke Operasi Normal...")
            
            # Start Pumps safely (Tertiary -> Secondary -> Primary)
            with self._state_manager as state:
                state.pump_tertiary_status = PUMP_ON
            time.sleep(0.5)
            with self._state_manager as state:
                state.pump_secondary_status = PUMP_ON
            time.sleep(0.5)
            with self._state_manager as state:
                state.pump_primary_status = PUMP_ON
            time.sleep(0.5)
            
            if self._check_cancelled(): return
            
            # We can run multiple ramps in parallel threads for speed, or sequentially if fast enough
            # To avoid jumps, let's ramp safety rod, pressure, shim, reg, and power
            # We'll use a fast 5-second ramp for all of them together
            start_time = time.time()
            duration = 5.0
            while time.time() - start_time < duration:
                if self._check_cancelled(): return
                progress = (time.time() - start_time) / duration
                with self._state_manager as state:
                    state.pressure = 0.0 + 150.0 * progress
                    state.safety_rod = 0.0 + 100.0 * progress
                    state.shim_rod = 0.0 + 50.0 * progress
                    state.regulating_rod = 0.0 + 50.0 * progress
                    state.thermal_kw = 0.0 + 250000.0 * progress
                    state.temperature_core = 25.0 + (280.0 - 25.0) * progress
                    state.temperature_coolant_primary = 25.0 + (300.0 - 25.0) * progress
                    state.turbine_speed = 0.0 + 100.0 * progress
                    state.reactor_active = True
                time.sleep(0.05)
                
            # Finalize values
            with self._state_manager as state:
                state.pressure = 150.0
                state.safety_rod = 100.0
                state.shim_rod = 50.0
                state.regulating_rod = 50.0
                state.thermal_kw = 250000.0
                state.temperature_core = 280.0
                state.temperature_coolant_primary = 300.0
                state.turbine_speed = 100.0
                
            self._set_phase(LofaPhase.NORMAL_OPS, "Operasi Normal Stabil")
            time.sleep(5.0)  # Let user observe normal operation
            if self._check_cancelled(): return
            
            # 3. PUMP FAILURE: Trip the primary pump
            self._set_phase(LofaPhase.PUMP_FAILURE, "KEGAGALAN POMPA PRIMER!")
            with self._state_manager as state:
                state.pump_primary_status = PUMP_OFF
                logger.critical("LOFA SEQUENCE: Primary pump manually tripped!")
                
            # 4. OBSERVATION: Let lofa_simulator.py detect and SCRAM naturally
            self._set_phase(LofaPhase.OBSERVATION, "Mengamati Suhu...")
            
            # We wait until emergency is active (SCRAM triggered by lofa_simulator)
            wait_time = 0
            while wait_time < 15.0:
                with self._state_manager as state:
                    if state.emergency_active:
                        break
                time.sleep(0.5)
                wait_time += 0.5
                if self._check_cancelled(): return
                
            self._set_phase(LofaPhase.COMPLETE, "SCRAM Otomatis Berhasil")
            time.sleep(3.0)
            
        except Exception as e:
            logger.error(f"LOFA Sequence error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        finally:
            self._running = False
            with self._state_manager as state:
                if state.auto_sim_running:
                    state.auto_sim_running = False
                    state.simulation_mode = 'idle'
            logger.info("--- LOFA SIMULATION SEQUENCE ENDED ---")
