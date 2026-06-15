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
from typing import Callable, Optional, TYPE_CHECKING

from .interlock_validator import InterlockValidator, PUMP_ON, PUMP_OFF, PUMP_STARTING, PUMP_SHUTTING_DOWN

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
                 event_queue: Queue,
                 interlock_validator: InterlockValidator,
                 scram_sequence: Optional['SCRAMSequence'] = None,
                 auto_simulator: Optional['AutoSimulator'] = None,
                 lofa_sequence = None,
                 buzzer = None):
        """
        Initialize EventProcessor.
        
        Args:
            state_manager: StateManager instance for state access
            event_queue: Queue to read button events from
            interlock_validator: InterlockValidator for safety checks
            scram_sequence: SCRAMSequence for emergency shutdown
            auto_simulator: AutoSimulator for auto startup
            buzzer: BuzzerAlarm instance for audio feedback
        """
        self._state_manager = state_manager
        self._event_queue = event_queue
        self._interlock_validator = interlock_validator
        
        from controllers.rod_controller import RodController
        self._rod_controller = RodController(self._interlock_validator)
        self._scram_sequence = scram_sequence
        self._auto_simulator = auto_simulator
        self._lofa_sequence = lofa_sequence
        self._buzzer = buzzer
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_button_time = time.time()
    
    @property
    def last_button_time(self) -> float:
        """Time of last button press (for inactivity tracking)."""
        return self._last_button_time
    
    def start(self) -> threading.Thread:
        """
        Start event processing thread.
        
        Returns:
            Thread object running the processor
        """
        self._running = True
        self._thread = threading.Thread(
            target=self._processor_thread,
            daemon=True
        )
        self._thread.start()
        return self._thread
    
    def stop(self) -> None:
        """Stop event processing thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _sound_warning(self, duration: float = 1.5) -> None:
        """Play interlock warning buzzer."""
        if self._buzzer:
            try:
                self._buzzer.sound_interlock_warning(duration=duration)
            except Exception:
                pass
    
    def _sound_procedure_warning(self, duration: float = 2.0) -> None:
        """Play procedure violation buzzer."""
        if self._buzzer:
            try:
                self._buzzer.sound_procedure_warning(duration=duration)
            except Exception:
                pass
    
    def _processor_thread(self) -> None:
        """Main event processing thread."""
        try:
            logger.info("Button event processor thread STARTING...")
            logger.info("Button event processor thread started - waiting for events...")
            
            loop_count = 0
            while self._running:
                try:
                    # Heartbeat every 60 seconds
                    loop_count += 1
                    if loop_count >= 6000:  # 6000 * 10ms = 60s
                        logger.info(f"Event processor alive - Queue size: {self._event_queue.qsize()}")
                        loop_count = 0
                    
                    # Wait for event with timeout
                    try:
                        event = self._event_queue.get(timeout=self.QUEUE_TIMEOUT)
                    except Empty:
                        continue
                    
                    # Process event
                    self._process_event(event)
                    
                    # Mark task done
                    self._event_queue.task_done()
                    
                except Exception as e:
                    logger.error(f"Event processor error: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info("Button event processor thread stopped")
            
        except Exception as e:
            logger.critical(f"FATAL: Event processor thread crashed: {e}")
            import traceback
            logger.critical(traceback.format_exc())
    
    def _process_event(self, event) -> None:
        """
        Process a single button event.
        
        Args:
            event: ButtonEvent to process
        """
        from io_handlers.button_handler import ButtonEvent
        
        # Update last button time
        self._last_button_time = time.time()
        
        with self._state_manager as state:
            # Pressure events
            if event == ButtonEvent.PRESSURE_UP:
                state.pressure = min(state.pressure + 1.0, 200.0)
            
            elif event == ButtonEvent.PRESSURE_DOWN:
                state.pressure = max(state.pressure - 1.0, 0.0)
            
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
                
                # Trigger emergency buzzer
                if self._buzzer:
                    logger.critical("   Triggering emergency buzzer...")
                    try:
                        self._buzzer.trigger_emergency_beep()
                        logger.critical("Emergency buzzer triggered")
                    except Exception as e:
                        logger.error(f"Buzzer trigger failed: {e}")
            
            # Reset
            elif event == ButtonEvent.REACTOR_RESET:
                # Stop auto simulation if running
                if self._auto_simulator and self._auto_simulator.is_running:
                    self._auto_simulator.cancel()
                if self._lofa_sequence and self._lofa_sequence.is_running:
                    self._lofa_sequence.cancel()
                
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
            
            else:
                logger.warning(f"Unknown event: {event}")
