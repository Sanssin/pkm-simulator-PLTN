"""
EventProcessor - Button event processing for PLTN Panel Simulator.

This module handles:
- Processing button events from the queue
- Coordinating with InterlockValidator for safety checks
- Updating state via StateManager
- Triggering SCRAM and auto simulation sequences
"""

import time
import logging
import threading
from queue import Queue, Empty
from enum import Enum

class ButtonEvent(Enum):
    """Button event types for queue-based processing."""
    PRESSURE_UP = "PRESSURE_UP"
    PRESSURE_DOWN = "PRESSURE_DOWN"
    PUMP_PRIMARY_ON = "PUMP_PRIMARY_ON"
    PUMP_PRIMARY_OFF = "PUMP_PRIMARY_OFF"
    PUMP_SECONDARY_ON = "PUMP_SECONDARY_ON"
    PUMP_SECONDARY_OFF = "PUMP_SECONDARY_OFF"
    PUMP_TERTIARY_ON = "PUMP_TERTIARY_ON"
    PUMP_TERTIARY_OFF = "PUMP_TERTIARY_OFF"
    SAFETY_ROD_UP = "SAFETY_ROD_UP"
    SAFETY_ROD_DOWN = "SAFETY_ROD_DOWN"
    SHIM_ROD_UP = "SHIM_ROD_UP"
    SHIM_ROD_DOWN = "SHIM_ROD_DOWN"
    REGULATING_ROD_UP = "REGULATING_ROD_UP"
    REGULATING_ROD_DOWN = "REGULATING_ROD_DOWN"
    REACTOR_RESET = "REACTOR_RESET"
    EMERGENCY = "EMERGENCY"
    START_AUTO_SIMULATION = "START_AUTO_SIMULATION"
    START_CINEMATIC_LOFA = "START_CINEMATIC_LOFA"
    LOFA_SIMULATE_PRIMARY = "LOFA_SIMULATE_PRIMARY"
    LOFA_SIMULATE_SECONDARY = "LOFA_SIMULATE_SECONDARY"
    LOFA_SIMULATE_TERTIARY = "LOFA_SIMULATE_TERTIARY"
    TOGGLE_CREDITS = "TOGGLE_CREDITS"
from typing import Callable, Optional, TYPE_CHECKING, Any

from .interlock_validator import InterlockValidator, PUMP_ON, PUMP_OFF, PUMP_STARTING, PUMP_SHUTTING_DOWN
import raspi_config as config

if TYPE_CHECKING:
    from .state_manager import StateManager
    from sequences.scram_sequence import SCRAMSequence
    from sequences.auto_simulation import AutoSimulator

logger = logging.getLogger(__name__)


class EventProcessor:
    """
    Processes button events and updates system state.
    
    Runs in a dedicated thread, processing events from a queue.
    Coordinates with InterlockValidator for safety checks.
    
    Usage:
        processor = EventProcessor(
            state_manager=state_manager,
            event_queue=event_queue,
            interlock_validator=interlock_validator,
            scram_sequence=scram_sequence,
            auto_simulator=auto_simulator,
            buzzer=buzzer,
        )
        
        # Start processing thread
        processor.start()
        
        # Stop
        processor.stop()
    """
    
    QUEUE_TIMEOUT = 0.01  # 10ms
    
    def __init__(self,
                 state_manager: 'StateManager',
                 interlock_validator: InterlockValidator,
                 scram_sequence: Optional['SCRAMSequence'] = None,
                 auto_simulator: Optional['AutoSimulator'] = None,
                 lofa_sequence: Optional[Any] = None,
                 cinematic_lofa_sequence: Optional[Any] = None):
        """
        Initialize EventProcessor.
        
        Args:
            state_manager: StateManager instance for state access
            interlock_validator: InterlockValidator for safety checks
            scram_sequence: SCRAMSequence for emergency shutdown
            auto_simulator: AutoSimulator for auto startup
            cinematic_lofa_sequence: CinematicLOFASequence instance
        """
        self._state_manager = state_manager
        self._interlock_validator = interlock_validator
        
        from controllers.rod_controller import RodController
        self._rod_controller = RodController(self._interlock_validator)
        self._scram_sequence = scram_sequence
        self._auto_simulator = auto_simulator
        self._lofa_sequence = lofa_sequence
        self._cinematic_lofa_sequence = cinematic_lofa_sequence
        
        self._last_button_time = time.time()
    
    @property
    def last_button_time(self) -> float:
        """Time of last button press (for inactivity tracking)."""
        return self._last_button_time
    
    def _sound_warning(self, duration: float = 1.5) -> None:
        """Log interlock warning."""
        pass
    
    def _sound_procedure_warning(self, duration: float = 2.0) -> None:
        """Log procedure violation."""
        pass
    
    def process_event(self, event) -> None:
        """
        Process a single button event.
        
        Args:
            event: ButtonEvent to process
        """

        
        # Update last button time
        self._last_button_time = time.time()
        
        with self._state_manager as state:
            # Pressure events
            if event == ButtonEvent.PRESSURE_UP:
                state.pressure = min(state.pressure + config.PRESS_INCREMENT_SLOW, 200.0)
            
            elif event == ButtonEvent.PRESSURE_UP_FAST:
                state.pressure = min(state.pressure + config.PRESS_INCREMENT_FAST, 200.0)
            
            elif event == ButtonEvent.PRESSURE_DOWN:
                state.pressure = max(state.pressure - config.PRESS_INCREMENT_SLOW, 0.0)
            
            elif event == ButtonEvent.PRESSURE_DOWN_FAST:
                state.pressure = max(state.pressure - config.PRESS_INCREMENT_FAST, 0.0)
            
            # Pump events
            elif event == ButtonEvent.PUMP_PRIMARY_ON:
                if state.pump_primary_status == PUMP_OFF:
                    if self._interlock_validator.check_pump_start(state, "Primary"):
                        state.pump_primary_status = PUMP_STARTING
                        logger.info("Primary pump starting (safety checks passed)")
            
            elif event == ButtonEvent.PUMP_PRIMARY_OFF:
                if state.pump_primary_status == PUMP_ON:
                    state.pump_primary_status = PUMP_SHUTTING_DOWN
            
            elif event == ButtonEvent.PUMP_SECONDARY_ON:
                if state.pump_secondary_status == PUMP_OFF:
                    if self._interlock_validator.check_pump_start(state, "Secondary"):
                        state.pump_secondary_status = PUMP_STARTING
                        logger.info("Secondary pump starting (safety checks passed)")
            
            elif event == ButtonEvent.PUMP_SECONDARY_OFF:
                if state.pump_secondary_status == PUMP_ON:
                    state.pump_secondary_status = PUMP_SHUTTING_DOWN
            
            elif event == ButtonEvent.PUMP_TERTIARY_ON:
                if state.pump_tertiary_status == PUMP_OFF:
                    if self._interlock_validator.check_pump_start(state, "Tertiary"):
                        state.pump_tertiary_status = PUMP_STARTING
                        logger.info("Tertiary pump starting (safety checks passed)")
            
            elif event == ButtonEvent.PUMP_TERTIARY_OFF:
                if state.pump_tertiary_status == PUMP_ON:
                    state.pump_tertiary_status = PUMP_SHUTTING_DOWN
                    
            elif event == ButtonEvent.START_CINEMATIC_LOFA:
                if self._cinematic_lofa_sequence:
                    self._cinematic_lofa_sequence.start()
                    logger.info("Cinematic LOFA simulation sequence initiated")

            # LOFA Simulation events
            elif event == ButtonEvent.LOFA_SIMULATE_PRIMARY:
                if state.pump_primary_status == PUMP_ON:
                    state.pump_primary_status = PUMP_SHUTTING_DOWN
                    logger.warning("Simulating Primary LOFA: Pump shutting down manually")
                else:
                    logger.warning("Cannot simulate Primary LOFA: Pump is not running")
            
            elif event == ButtonEvent.LOFA_SIMULATE_SECONDARY:
                if state.pump_secondary_status == PUMP_ON:
                    state.pump_secondary_status = PUMP_SHUTTING_DOWN
                    logger.warning("Simulating Secondary LOFA: Pump shutting down")
                    
            elif event == ButtonEvent.LOFA_SIMULATE_TERTIARY:
                if state.pump_tertiary_status == PUMP_ON:
                    state.pump_tertiary_status = PUMP_SHUTTING_DOWN
                    logger.warning("Simulating Tertiary LOFA: Pump shutting down")
            
            # Rod events are handled by RodController
            elif event in [ButtonEvent.SAFETY_ROD_UP, ButtonEvent.SAFETY_ROD_DOWN,
                           ButtonEvent.SHIM_ROD_UP, ButtonEvent.SHIM_ROD_DOWN,
                           ButtonEvent.REGULATING_ROD_UP, ButtonEvent.REGULATING_ROD_DOWN]:
                self._rod_controller.process_rod_event(state, event, warning_callback=self._sound_warning)
            
            # Emergency SCRAM
            elif event == ButtonEvent.EMERGENCY:
                state.emergency_active = True
                logger.critical("EMERGENCY SCRAM ACTIVATED!")
                logger.critical("   Pumps remain ON for decay heat removal")
                
                # Execute SCRAM sequence
                if self._scram_sequence:
                    self._scram_sequence.execute()
                logger.critical("Emergency sequence initiated")
            
            # Reset
            elif event == ButtonEvent.REACTOR_RESET:
                # Stop auto simulation if running
                if self._auto_simulator:
                    self._auto_simulator.cancel()
                if self._lofa_sequence:
                    self._lofa_sequence.cancel()
                if self._cinematic_lofa_sequence:
                    self._cinematic_lofa_sequence.cancel()
                
                # Reset state
                state.reset()
                
                logger.info("=" * 60)
                logger.info("SIMULATION RESET")
                logger.info("All parameters reset. Press START to begin.")
                logger.info("=" * 60)
            
            # Start auto simulation
            elif event == ButtonEvent.START_AUTO_SIMULATION:
                if state.auto_sim_running:
                    logger.warning("Auto simulation already running!")
                    return
                
                # Start auto simulation
                if self._auto_simulator:
                    self._auto_simulator.start()
                    logger.info("=" * 60)
                    logger.info("AUTO SIMULATION MODE ACTIVATED")
                    logger.info("Simulasi akan berjalan otomatis dengan kecepatan lambat")
                    logger.info("untuk memudahkan pemahaman cara kerja PLTN")
                    logger.info("=" * 60)
            
            # Toggle credits
            elif event == ButtonEvent.TOGGLE_CREDITS:
                current = getattr(state, "show_credits", False)
                setattr(state, "show_credits", not current)
                logger.info(f"Toggled credits display to: {not current}")
            
            else:
                logger.warning(f"Unknown event: {event}")
