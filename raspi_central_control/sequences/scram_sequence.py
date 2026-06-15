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
    
    Performs simultaneous insertion of all control rods with smooth animation.
    Also initiates turbine spin-down.
    
    Usage:
        scram = SCRAMSequence(
            state_manager=state_manager
        )
        scram.execute()  # Non-blocking, runs in separate thread
        
        # Or blocking:
        scram.execute_blocking()
    
    Timing:
        - Rod insertion: 3 seconds (smooth descent)
        - Turbine spin-down: 12 seconds (runs in parallel)
    """
    
    ROD_DROP_DURATION = 3.0      # seconds
    TURBINE_SPINDOWN_DURATION = 12.0  # seconds
    UPDATE_INTERVAL = 0.05       # 50ms for smooth animation
    
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
        thread = threading.Thread(target=self._scram_thread, daemon=True)
        thread.start()
        return thread
    
    def execute_blocking(self) -> None:
        """Execute SCRAM sequence synchronously (blocks caller)."""
        self._scram_thread()
    
    def _scram_thread(self) -> None:
        """Main SCRAM execution thread."""
        try:
            self._running = True
            logger.critical("SCRAM SEQUENCE INITIATED")
            logger.critical("Emergency rod insertion: ALL RODS DROPPING SIMULTANEOUSLY")
            
            # Capture initial values and set snap-to-zero / emergency states
            with self._state_manager as state:
                initial_turbine_speed = state.turbine_speed
                
                # Snap to zero immediately
                state.safety_rod = 0
                state.shim_rod = 0
                state.regulating_rod = 0
                
                # Motor stop (all pumps OFF)
                state.pump_primary_status = 0
                state.pump_secondary_status = 0
                state.pump_tertiary_status = 0
                
                # Alarm trigger
                state.emergency_active = True
            
            # Start turbine spin-down in parallel
            if initial_turbine_speed > 0:
                turbine_thread = threading.Thread(
                    target=self._turbine_spindown,
                    args=(initial_turbine_speed,),
                    daemon=True
                )
                turbine_thread.start()
            
            # Since we snapped to zero, we don't need to call _drop_all_rods
            # self._drop_all_rods(start_safety, start_shim, start_regulating)
            
            logger.critical("SCRAM SEQUENCE COMPLETE - All rods inserted")
            logger.critical("Turbine spin-down continues (~12 seconds total)")
            
            if self._on_complete:
                self._on_complete()
                
        except Exception as e:
            logger.error(f"SCRAM sequence error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self._running = False
    
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
                elapsed = time.time() - start_time
                if elapsed >= self.TURBINE_SPINDOWN_DURATION:
                    break
                
                # Linear deceleration
                progress = elapsed / self.TURBINE_SPINDOWN_DURATION
                current_speed = initial_speed * (1 - progress)
                
                with self._state_manager as state:
                    state.turbine_speed = max(0.0, current_speed)
                
                time.sleep(0.05)  # 100ms update rate
            
            # Ensure final speed is exactly 0
            with self._state_manager as state:
                state.turbine_speed = 0.0
            
            logger.info("Turbine spin-down complete (0%)")
            
        except Exception as e:
            logger.error(f"Turbine spin-down error: {e}")
            import traceback
            logger.error(traceback.format_exc())
