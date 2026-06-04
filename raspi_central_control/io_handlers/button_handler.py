"""
ButtonIOHandler - Button input handling for PLTN Panel Simulator.

This module handles:
- Button polling thread
- Button hold detection thread
- Event queue integration
"""

import time
import logging
import threading
from queue import Queue
from typing import Optional, Set, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from raspi_gpio_buttons import ButtonHandler, ButtonPin

logger = logging.getLogger(__name__)


class ButtonEvent(Enum):
    """Button event types for queue-based processing."""
    PRESSURE_UP = "PRESSURE_UP"
    PRESSURE_DOWN = "PRESSURE_DOWN"
    PRESSURE_UP_FAST = "PRESSURE_UP_FAST"
    PRESSURE_DOWN_FAST = "PRESSURE_DOWN_FAST"
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


class ButtonIOHandler:
    """
    Handles button input polling and hold detection.
    
    Runs two threads:
    - Polling thread (5ms): Checks all buttons for state changes
    - Hold thread (50ms): Detects held buttons for continuous input
    
    Events are pushed to a queue for processing by EventProcessor.
    
    Usage:
        handler = ButtonIOHandler(
            button_manager=button_manager,
            event_queue=event_queue,
            running_flag=lambda: state.running
        )
        
        # Start threads
        handler.start()
        
        # Stop threads
        handler.stop()
    """
    
    POLLING_INTERVAL = 0.005   # 5ms
    HOLD_INTERVAL = 0.01       # 10ms
    HOLD_REPEAT_INTERVAL = 0.05  # 50ms between hold events
    
    def __init__(self,
                 button_manager: 'ButtonHandler',
                 event_queue: Queue,
                 running_flag: callable):
        """
        Initialize ButtonIOHandler.
        
        Args:
            button_manager: ButtonHandler instance for GPIO access
            event_queue: Queue to push button events
            running_flag: Callable returning True while system is running
        """
        self._button_manager = button_manager
        self._event_queue = event_queue
        self._running_flag = running_flag
        self._polling_thread: Optional[threading.Thread] = None
        self._hold_thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        """Start polling and hold detection threads."""
        self._polling_thread = threading.Thread(
            target=self._polling_thread_func,
            daemon=True
        )
        self._hold_thread = threading.Thread(
            target=self._hold_thread_func,
            daemon=True
        )
        
        self._polling_thread.start()
        self._hold_thread.start()
    
    def stop(self) -> None:
        """Stop threads (they will stop when running_flag returns False)."""
        if self._polling_thread:
            self._polling_thread.join(timeout=1.0)
        if self._hold_thread:
            self._hold_thread.join(timeout=1.0)
    
    def _polling_thread_func(self) -> None:
        """Button polling thread - checks all buttons at 5ms intervals."""
        logger.info("Button polling thread started")
        
        loop_count = 0
        while self._running_flag():
            try:
                self._button_manager.check_all_buttons()
                time.sleep(self.POLLING_INTERVAL)
                
                # Log heartbeat every 10 seconds (2000 loops x 5ms)
                loop_count += 1
                if loop_count >= 2000:
                    logger.debug("Button polling thread: alive (2000 loops)")
                    loop_count = 0
                
            except Exception as e:
                logger.error(f"Error in button polling thread: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(0.05)
        
        logger.info("Button polling thread stopped")
    
    def _hold_thread_func(self) -> None:
        """Button hold detection thread - detects held buttons for rod/pressure control."""
        logger.info("Button hold detection thread started")
        
        # Import ButtonPin here to avoid circular imports
        try:
            from raspi_gpio_buttons import ButtonPin
        except ImportError:
            logger.error("Could not import ButtonPin, hold thread disabled")
            return
        
        # Define which buttons support hold
        hold_buttons = {
            ButtonPin.SAFETY_ROD_UP,
            ButtonPin.SAFETY_ROD_DOWN,
            ButtonPin.SHIM_ROD_UP,
            ButtonPin.SHIM_ROD_DOWN,
            ButtonPin.REGULATING_ROD_UP,
            ButtonPin.REGULATING_ROD_DOWN,
            ButtonPin.PRESSURE_UP,
            ButtonPin.PRESSURE_DOWN
        }
        
        # Mapping from ButtonPin to ButtonEvent
        pin_to_event = {
            ButtonPin.SAFETY_ROD_UP: ButtonEvent.SAFETY_ROD_UP,
            ButtonPin.SAFETY_ROD_DOWN: ButtonEvent.SAFETY_ROD_DOWN,
            ButtonPin.SHIM_ROD_UP: ButtonEvent.SHIM_ROD_UP,
            ButtonPin.SHIM_ROD_DOWN: ButtonEvent.SHIM_ROD_DOWN,
            ButtonPin.REGULATING_ROD_UP: ButtonEvent.REGULATING_ROD_UP,
            ButtonPin.REGULATING_ROD_DOWN: ButtonEvent.REGULATING_ROD_DOWN,
            ButtonPin.PRESSURE_UP: ButtonEvent.PRESSURE_UP,
            ButtonPin.PRESSURE_DOWN: ButtonEvent.PRESSURE_DOWN
        }
        
        while self._running_flag():
            try:
                # Check which buttons are held
                pressed = self._button_manager.check_hold_buttons(
                    hold_interval=self.HOLD_REPEAT_INTERVAL
                )
                
                # Process only hold-supported buttons
                for pin in pressed & hold_buttons:
                    if pin in pin_to_event:
                        self._event_queue.put(pin_to_event[pin])
                
                time.sleep(self.HOLD_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in button hold thread: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(0.05)
        
        logger.info("Button hold detection thread stopped")


# Helper function for mapping ButtonPin to ButtonEvent
def get_button_event(pin_name: str) -> Optional[ButtonEvent]:
    """
    Get ButtonEvent from pin name string.
    
    Args:
        pin_name: Name of the button pin (e.g., "SAFETY_ROD_UP")
        
    Returns:
        Corresponding ButtonEvent or None if not found
    """
    try:
        return ButtonEvent[pin_name]
    except KeyError:
        return None
