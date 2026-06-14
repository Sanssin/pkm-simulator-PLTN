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

logger = logging.getLogger(__name__)

class LofaPhase(Enum):
    """Simulation phases for auto LOFA sequence."""
    IDLE = auto()
    PREPARE = auto()
    NORMAL_OPS = auto()
    PUMP_FAILURE = auto()
    OBSERVATION = auto()
    COMPLETE = auto()

class LOFASequence:
    """
    Automated LOFA simulation sequence.
    
    Quickly sets up the reactor to normal operating conditions,
    then deliberately fails the primary pump.
    """
    
    def __init__(self, state_manager: 'StateManager'):
        self._state_manager = state_manager
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
            time.sleep(2.0)
            if self._check_cancelled(): return
            
            # 2. NORMAL_OPS: Jump to normal operation state
            self._set_phase(LofaPhase.NORMAL_OPS, "Operasi Normal (Setup)")
            with self._state_manager as state:
                # Set pumps
                state.pump_tertiary_status = PUMP_ON
                state.pump_secondary_status = PUMP_ON
                state.pump_primary_status = PUMP_ON
                
                # Set pressure and temps
                state.pressure = 150.0
                state.condenser_pressure = 0.1
                
                # Set rods
                state.safety_rod = 100.0
                state.shim_rod = 50.0
                state.regulating_rod = 50.0
                
                # Set power
                state.thermal_kw = 250000.0  # 250 MW
                state.temperature_core = 280.0
                state.temperature_coolant_primary = 300.0
                state.reactor_active = True
                
                state.turbine_speed = 100.0
                
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
                    state.simulation_mode = 'manual'
            logger.info("--- LOFA SIMULATION SEQUENCE ENDED ---")
