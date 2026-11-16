"""
SCRAMSequence - Emergency shutdown sequence for PLTN Panel Simulator.

This module handles:
- Emergency rod insertion (all rods drop simultaneously)
- Turbine spin-down simulation

Safety Note:
- This is safety-critical code
- Changes require thorough testing
- SCRAM must always complete successfully
"""

import time
import logging
import threading
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from controllers.state_manager import StateManager

logger = logging.getLogger(__name__)


class SCRAMSequence:
    """
    Emergency SCRAM (Safety Control Rod Axe Man) sequence.

    Performs immediate rod insertion, parallel turbine spin-down,
    initial decay heat cooling hold, and sequential pump shutdown
    (Primary -> Secondary -> Tertiary) within ~35 seconds total.
    """

    ROD_DROP_DURATION = 3.0      # seconds (kept for compatibility)
    TURBINE_SPINDOWN_DURATION = 12.0  # seconds
    DECAY_HEAT_COOLING_DURATION = 12.5  # seconds before sequential pump shutdown
    PUMP_SHUTDOWN_DURATION = 7.0  # matches PumpController.shutdown_time
    PUMP_STEP_GAP = 0.75         # seconds between each pump shutdown
    UPDATE_INTERVAL = 0.05       # 50ms check/update interval

    def __init__(self,
                 state_manager: 'StateManager',
                 on_complete: Optional[Callable[[], None]] = None):
        """
        Initialize SCRAM sequence.

        Args:
            state_manager: StateManager instance for state access
            on_complete: Callback when SCRAM sequence completes
        """
        self._state_manager = state_manager
        self._on_complete = on_complete
        self._running = False
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        """Check if SCRAM sequence is currently running."""
        return self._running

    def execute(self) -> threading.Thread:
        """
        Execute SCRAM sequence asynchronously.

        Returns:
            Thread object running the SCRAM sequence
        """
        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                return self._thread
            self._running = True
            self._cancel_event.clear()
            self._thread = threading.Thread(target=self._scram_thread, daemon=True, name="SCRAMSequenceThread")
            self._thread.start()
            return self._thread

    def execute_blocking(self) -> None:
        """Execute SCRAM sequence synchronously (blocks caller)."""
        self._cancel_event.clear()
        self._scram_thread()

    def cancel(self) -> None:
        """Cancel an in-progress SCRAM sequence (e.g., on REACTOR_RESET)."""
        self._cancel_event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _wait_cancellable(self, duration: float) -> bool:
        """Wait for duration seconds; returns False if cancelled early."""
        if duration <= 0:
            return not self._cancel_event.is_set()
        return not self._cancel_event.wait(timeout=duration)

    def _scram_thread(self) -> None:
        """Main SCRAM execution thread."""
        try:
            self._running = True
            logger.critical("SCRAM SEQUENCE INITIATED")
            logger.critical("Emergency rod insertion: ALL RODS DROPPING SIMULTANEOUSLY")

            with self._state_manager as state:
                initial_turbine_speed = state.turbine_speed

                # Snap all 3 control rods to 0 immediately
                state.safety_rod = 0
                state.shim_rod = 0
                state.regulating_rod = 0
                state.emergency_active = True

                any_pump_active = (
                    state.pump_primary_status != 0
                    or state.pump_secondary_status != 0
                    or state.pump_tertiary_status != 0
                )

            # Start turbine spin-down in parallel
            if initial_turbine_speed > 0:
                turbine_thread = threading.Thread(
                    target=self._turbine_spindown,
                    args=(initial_turbine_speed,),
                    daemon=True
                )
                turbine_thread.start()

            logger.critical("SCRAM: All rods inserted (0%) - Decay heat removal active")

            if any_pump_active:
                # Hold pumps ON briefly to remove initial decay heat while turbine spins down
                if not self._wait_cancellable(self.DECAY_HEAT_COOLING_DURATION):
                    logger.info("SCRAM sequence cancelled during decay heat cooling hold")
                    return

                if not self._shutdown_pumps_sequentially():
                    logger.info("SCRAM sequence cancelled during sequential pump shutdown")
                    return

            logger.critical("SCRAM SEQUENCE COMPLETE - All rods inserted and pumps shut down")

            if not self._cancel_event.is_set() and self._on_complete:
                self._on_complete()

        except Exception as e:
            logger.error(f"SCRAM sequence error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self._running = False

    def _shutdown_pumps_sequentially(self) -> bool:
        """
        Shut down active pumps in reverse startup order:
        Primary -> Secondary -> Tertiary.
        Returns False if cancelled before completion.
        """
        pump_order = ('primary', 'secondary', 'tertiary')
        active_pumps = []
        with self._state_manager as state:
            for name in pump_order:
                if getattr(state, f'pump_{name}_status', 0) != 0:
                    active_pumps.append(name)

        for idx, name in enumerate(active_pumps):
            status_attr = f'pump_{name}_status'
            trans_attr = f'pump_{name}_transition_start'

            with self._state_manager as state:
                current_status = getattr(state, status_attr, 0)
                if current_status == 0:
                    continue
                if current_status in (1, 2):  # STARTING or ON -> begin shutdown ramp
                    setattr(state, status_attr, 3)  # PUMP_SHUTTING_DOWN
                    setattr(state, trans_attr, 0.0)
                    logger.critical(f"SCRAM: Shutting down {name.upper()} pump...")

            # Wait for PumpController (or fallback timeout) to bring pump to OFF (0)
            start_wait = time.monotonic()
            max_wait = self.PUMP_SHUTDOWN_DURATION + 0.5
            while True:
                if self._cancel_event.wait(timeout=self.UPDATE_INTERVAL):
                    return False

                with self._state_manager as state:
                    if getattr(state, status_attr, 0) == 0:
                        break
                    if time.monotonic() - start_wait >= self.PUMP_SHUTDOWN_DURATION:
                        # Ensure OFF when PumpController is not running (e.g. unit tests)
                        if time.monotonic() - start_wait >= max_wait or self.PUMP_SHUTDOWN_DURATION < 1.0:
                            setattr(state, status_attr, 0)
                            setattr(state, trans_attr, 0.0)
                            break

            logger.critical(f"SCRAM: {name.upper()} pump OFF")

            if idx < len(active_pumps) - 1:
                if not self._wait_cancellable(self.PUMP_STEP_GAP):
                    return False

        return True
    
    def _drop_all_rods(self, start_safety: int, start_shim: int, 
                       start_regulating: int) -> None:
        """
        Drop all rods from their starting positions to 0.
        Deprecated: SCRAM now uses snap-to-zero.
        
        Args:
            start_safety: Initial safety rod position (%)
            start_shim: Initial shim rod position (%)
            start_regulating: Initial regulating rod position (%)
        """
        logger.critical("Lowering all control rods...")
        start_time = time.time()
        
        while time.time() - start_time < self.ROD_DROP_DURATION:
            elapsed = time.time() - start_time
            progress = elapsed / self.ROD_DROP_DURATION  # 0.0 to 1.0
            
            # Calculate current positions (all rods dropping together)
            current_safety = int(start_safety * (1 - progress))
            current_shim = int(start_shim * (1 - progress))
            current_regulating = int(start_regulating * (1 - progress))
            
            # Update all rods atomically
            with self._state_manager as state:
                state.safety_rod = max(0, current_safety)
                state.shim_rod = max(0, current_shim)
                state.regulating_rod = max(0, current_regulating)
            
            time.sleep(self.UPDATE_INTERVAL)
        
        # Ensure all rods are at exactly 0%
        with self._state_manager as state:
            state.safety_rod = 0
            state.shim_rod = 0
            state.regulating_rod = 0
        
        logger.critical("Safety rod inserted (0%)")
        logger.critical("Shim rod inserted (0%)")
        logger.critical("Regulating rod inserted (0%)")
    
    def _turbine_spindown(self, initial_speed: float) -> None:
        """
        Gradually reduce turbine speed to 0.
        
        Simulates turbine inertia and residual steam energy.
        Uses linear deceleration over 12 seconds.
        
        Args:
            initial_speed: Starting turbine speed (%)
        """
        try:
            logger.info(f"Turbine spin-down started (initial: {initial_speed:.1f}%)")
            
            start_time = time.time()
            
            while True:
                if self._cancel_event.is_set():
                    return

                elapsed = time.time() - start_time
                if elapsed >= self.TURBINE_SPINDOWN_DURATION:
                    break

                # Linear deceleration
                progress = elapsed / self.TURBINE_SPINDOWN_DURATION
                current_speed = initial_speed * (1 - progress)

                with self._state_manager as state:
                    state.turbine_speed = max(0.0, current_speed)

                if self._cancel_event.wait(timeout=0.05):
                    return

            # Ensure final speed is exactly 0
            with self._state_manager as state:
                state.turbine_speed = 0.0
            
            logger.info("Turbine spin-down complete (0%)")
            
        except Exception as e:
            logger.error(f"Turbine spin-down error: {e}")
            import traceback
            logger.error(traceback.format_exc())
