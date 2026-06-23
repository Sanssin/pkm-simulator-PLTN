"""
AutoSimulator - Automated PWR startup sequence for PLTN Panel Simulator.

This module handles the automatic startup simulation that demonstrates
the correct procedure for starting a PWR nuclear reactor.

Phases:
1. System Initialization
2. Pressurizer to 45 bar
3. Pump Startup (Tertiary → Secondary → Primary)
4A. Pressure to 140 bar
4B. Safety Rod Withdrawal
4C. Shim Rod to 50%
4D. Regulating Rod to 50%
4E. Power Ramp to 100%
5. Steam Generator Operation
6. Turbine-Generator Startup
7. Power Generation
8. Cooling Tower Activation
9. Stable Operation
"""

import time
import logging
import threading
from enum import Enum, auto
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from controllers.state_manager import StateManager

logger = logging.getLogger(__name__)


class SimPhase(Enum):
    """Simulation phases for auto startup sequence."""
    IDLE = auto()
    INIT = auto()
    PRESSURE_45 = auto()
    PUMPS = auto()
    PRESSURE_140 = auto()
    SAFETY_ROD = auto()
    SHIM_ROD_50 = auto()
    REG_ROD_50 = auto()
    MAX_POWER = auto()
    STEAM_GEN = auto()
    TURBINE = auto()
    POWER_GEN = auto()
    COOLING_TOWER = auto()
    STABLE = auto()
    COMPLETE = auto()


class AutoSimulator:
    """
    Automated PWR startup sequence simulator.
    
    Runs through a realistic 9-phase startup procedure with smooth
    animations for educational purposes.
    
    Usage:
        simulator = AutoSimulator(
            state_manager=state_manager
        )
        
        # Start simulation (non-blocking)
        simulator.start()
        
        # Cancel if needed
        simulator.cancel()
        
        # Check status
        if simulator.is_running:
            print(f"Current phase: {simulator.current_phase}")
    """
    
    UPDATE_INTERVAL = 0.05  # 50ms for smooth animation
    
    def __init__(self, state_manager: 'StateManager'):
        """
        Initialize AutoSimulator.
        
        Args:
            state_manager: StateManager instance for state access
        """
        self._state_manager = state_manager
        self._current_phase = SimPhase.IDLE
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None
    
    @property
    def is_running(self) -> bool:
        """Check if simulation is currently running."""
        return self._running
    
    @property
    def current_phase(self) -> SimPhase:
        """Get current simulation phase."""
        return self._current_phase
    
    def start(self) -> threading.Thread:
        """
        Start the auto simulation.
        
        Returns:
            Thread object running the simulation
        """
        if self._running:
            logger.warning("Auto simulation already running!")
            return self._thread
        
        self._cancelled = False
        self._thread = threading.Thread(target=self._simulation_thread, daemon=True)
        self._thread.start()
        return self._thread
    
    def cancel(self) -> None:
        """Cancel the running simulation."""
        self._cancelled = True
        with self._state_manager as state:
            state.auto_sim_running = False
            state.simulation_mode = 'manual'
            state.auto_sim_phase = ""
        logger.warning("Auto simulation cancelled by user")
    
    def _check_cancelled(self) -> bool:
        """Check if simulation was cancelled."""
        if self._cancelled:
            return True
        with self._state_manager as state:
            return not state.auto_sim_running
    
    def _set_phase(self, phase: SimPhase, label: str) -> None:
        """Set current phase and update state."""
        self._current_phase = phase
        with self._state_manager as state:
            state.auto_sim_phase = label
    
    def _ramp_value(self, field: str, start: float, target: float, 
                    duration: float, is_int: bool = False) -> bool:
        """
        Smoothly ramp a state field from start to target.
        
        Args:
            field: State field name to update
            start: Starting value
            target: Target value
            duration: Duration in seconds
            is_int: If True, convert to int
            
        Returns:
            False if cancelled, True if completed
        """
        start_time = time.time()
        
        while time.time() - start_time < duration:
            if self._check_cancelled():
                return False
            
            elapsed = time.time() - start_time
            progress = elapsed / duration
            current = start + (target - start) * progress
            
            if is_int:
                current = int(current)
            
            with self._state_manager as state:
                setattr(state, field, current)
            
            time.sleep(self.UPDATE_INTERVAL)
        
        # Ensure exact final value
        final_value = int(target) if is_int else target
        with self._state_manager as state:
            setattr(state, field, final_value)
        
        return True
    
    def _simulation_thread(self) -> None:
        """Main simulation execution thread."""
        try:
            self._running = True
            
            # Mark state as auto simulation running
            with self._state_manager as state:
                state.simulation_mode = 'auto'
                state.auto_sim_running = True
                
                # Reset state at the beginning
                state.pump_primary_status = 0
                state.pump_secondary_status = 0
                state.pump_tertiary_status = 0
                state.pressure = 1.0
                state.safety_rod = 0
                state.shim_rod = 0
                state.regulating_rod = 0
                state.thermal_kw = 0.0
            
            logger.info("=" * 70)
            logger.info("AUTO SIMULATION MODE - Synchronized with Video")
            logger.info("=" * 70)
            
            start_time = time.time()
            
            def wait_until(target_seconds: float) -> bool:
                while time.time() - start_time < target_seconds:
                    if self._check_cancelled():
                        return False
                    time.sleep(0.1)
                return True

            # 0.28 (28s) - Pompa tersier
            if not wait_until(28.0): return
            self._set_phase(SimPhase.PUMPS, "Pompa Tersier")
            logger.info("0:28 - Starting Tertiary Pump")
            with self._state_manager as state:
                state.pump_tertiary_status = 1
                
            # 1.16 (76s) - Pompa sekunder
            if not wait_until(76.0): return
            self._set_phase(SimPhase.PUMPS, "Pompa Sekunder")
            logger.info("1:16 - Starting Secondary Pump")
            with self._state_manager as state:
                state.pump_secondary_status = 1
                
            # 1.43 (103s) - Pressurizer
            if not wait_until(103.0): return
            self._set_phase(SimPhase.PRESSURE_140, "Pressurizer")
            logger.info("1:43 - Pressurizer Activation (Ramp to 155 bar)")
            # Ramp pressure from 1.43 to 2.18 (138s). Duration = 35s
            if not self._ramp_value('pressure', 1.0, 155.0, 35.0): return
            
            # 2.19 (139s) - Pompa primer
            if not wait_until(139.0): return
            self._set_phase(SimPhase.PUMPS, "Pompa Primer")
            logger.info("2:19 - Starting Primary Pump")
            with self._state_manager as state:
                state.pump_primary_status = 1
                
            # 3.25 (205s) - Safety rod (5 detik)
            if not wait_until(205.0): return
            self._set_phase(SimPhase.SAFETY_ROD, "Safety Rod")
            logger.info("3:25 - Safety Rod Withdrawal (5s)")
            if not self._ramp_value('safety_rod', 0, 100, 5.0, is_int=True): return
            
            # 3.48 (228s) - Shim rod (5 detik)
            if not wait_until(228.0): return
            self._set_phase(SimPhase.SHIM_ROD_50, "Shim Rod")
            logger.info("3:48 - Shim Rod Withdrawal (5s)")
            start_time_ramp = time.time()
            while time.time() - start_time_ramp < 5.0:
                if self._check_cancelled(): return
                prog = (time.time() - start_time_ramp) / 5.0
                with self._state_manager as state:
                    state.shim_rod = 100.0 * prog
                    state.thermal_kw = 150000.0 * prog
                    state.turbine_speed = 50.0 * prog
                time.sleep(0.1)
            with self._state_manager as state:
                state.shim_rod = 100.0
                state.thermal_kw = 150000.0
            
            # 4.26 (266s) - Regulating rod (5 detik)
            if not wait_until(266.0): return
            self._set_phase(SimPhase.REG_ROD_50, "Reg Rod")
            logger.info("4:26 - Regulating Rod Withdrawal (5s)")
            start_time_ramp = time.time()
            while time.time() - start_time_ramp < 5.0:
                if self._check_cancelled(): return
                prog = (time.time() - start_time_ramp) / 5.0
                with self._state_manager as state:
                    state.regulating_rod = 100.0 * prog
                    state.thermal_kw = 150000.0 + (150000.0 * prog)
                    state.turbine_speed = 50.0 + (50.0 * prog)
                time.sleep(0.1)
            with self._state_manager as state:
                state.regulating_rod = 100.0
                state.thermal_kw = 300000.0
                state.turbine_speed = 100.0
            
            # Mematikan reaktor: 6.36 (396s)
            if not wait_until(396.0): return
            self._set_phase(SimPhase.STABLE, "Shutdown")
            logger.info("6:36 - Normal Shutdown (Mematikan reaktor)")
            # Lower rods slowly
            def lower_rods():
                steps = 170
                for i in range(steps):
                    if self._check_cancelled(): return False
                    with self._state_manager as state:
                        prog = 1.0 - (i/steps)
                        state.shim_rod = int(100 * prog)
                        state.regulating_rod = int(100 * prog)
                        # Turunkan daya juga secara bertahap
                        state.thermal_kw = 300000.0 * prog
                        state.turbine_speed = 100.0 * prog
                    time.sleep(17.0/steps)
                with self._state_manager as state:
                    state.shim_rod = 0
                    state.regulating_rod = 0
                    state.thermal_kw = 0.0
                return True
            
            if not lower_rods(): return
            
            # Scram: 6.54 (414s)
            if not wait_until(414.0): return
            self._set_phase(SimPhase.COMPLETE, "Scram")
            logger.info("6:54 - SCRAM! (Emergency shutdown)")
            with self._state_manager as state:
                state.emergency_active = True
                state.pump_primary_status = 3
                state.pump_secondary_status = 3
                state.pump_tertiary_status = 3
            if not self._ramp_value('safety_rod', 100, 0, 3.0, is_int=True): return
                
            # Finish simulation at video end: 7.14 (434s)
            if not wait_until(434.0): return
            logger.info("7:14 - Video Complete. Returning to IDLE mode.")
            
        except Exception as e:
            logger.error(f"Error in auto simulation: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self._running = False
            self._current_phase = SimPhase.IDLE
            with self._state_manager as state:
                state.auto_sim_running = False
                state.emergency_active = False # Reset emergency just in case
                if not self._cancelled:
                    state.simulation_mode = 'idle' # Kembalikan ke mode idle jika tidak dicancel
                state.auto_sim_phase = ""
            logger.info("Auto simulation thread stopped")
