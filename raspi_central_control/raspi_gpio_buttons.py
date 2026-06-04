#!/usr/bin/env python3
"""
Raspberry Pi GPIO Button Handler for PLTN Control Panel
Handles 18 physical push buttons with debouncing

Button Layout:
- 6 Pump Control buttons (Primary, Secondary, Tertiary ON/OFF)
- 6 Rod Control buttons (Safety, Shim, Regulating UP/DOWN)
- 2 Pressure Control buttons (UP/DOWN)
- 3 System Control buttons (START, RESET, AUTO_SIMULATION)
- 1 Emergency button (SCRAM)
"""

import RPi.GPIO as GPIO
import time
import logging
from enum import IntEnum

logger = logging.getLogger(__name__)

# ============================================
# GPIO Pin Mapping (BCM Mode)
# ============================================

class ButtonPin(IntEnum):
    """GPIO pin assignments for buttons"""
    # Pump Control (6 buttons)
    PUMP_PRIMARY_ON = 11   # MOVED from GPIO 5 (UART3 conflict)
    PUMP_PRIMARY_OFF = 6
    PUMP_SECONDARY_ON = 13
    PUMP_SECONDARY_OFF = 19
    PUMP_TERTIARY_ON = 26
    PUMP_TERTIARY_OFF = 21
    
    # Rod Control (6 buttons)
    SAFETY_ROD_UP = 20
    SAFETY_ROD_DOWN = 16
    SHIM_ROD_UP = 12
    SHIM_ROD_DOWN = 7
    REGULATING_ROD_UP = 8
    REGULATING_ROD_DOWN = 25
    
    # Pressurizer Control (2 buttons)
    PRESSURE_UP = 24
    PRESSURE_DOWN = 23
    
    # System Control (2 buttons) - v4.0: Simplified
    START_AUTO_SIMULATION = 17 # GREEN button - Start auto simulation
    REACTOR_RESET = 27         # YELLOW button - Reset simulation
    
    # Emergency (1 button)
    EMERGENCY = 18  # RED button - Emergency shutdown!

# Button names for logging
BUTTON_NAMES = {
    ButtonPin.PUMP_PRIMARY_ON: "Pump Primary ON",
    ButtonPin.PUMP_PRIMARY_OFF: "Pump Primary OFF",
    ButtonPin.PUMP_SECONDARY_ON: "Pump Secondary ON",
    ButtonPin.PUMP_SECONDARY_OFF: "Pump Secondary OFF",
    ButtonPin.PUMP_TERTIARY_ON: "Pump Tertiary ON",
    ButtonPin.PUMP_TERTIARY_OFF: "Pump Tertiary OFF",
    ButtonPin.SAFETY_ROD_UP: "Safety Rod UP",
    ButtonPin.SAFETY_ROD_DOWN: "Safety Rod DOWN",
    ButtonPin.SHIM_ROD_UP: "Shim Rod UP",
    ButtonPin.SHIM_ROD_DOWN: "Shim Rod DOWN",
    ButtonPin.REGULATING_ROD_UP: "Regulating Rod UP",
    ButtonPin.REGULATING_ROD_DOWN: "Regulating Rod DOWN",
    ButtonPin.PRESSURE_UP: "Pressure UP",
    ButtonPin.PRESSURE_DOWN: "Pressure DOWN",
    ButtonPin.START_AUTO_SIMULATION: "START AUTO SIMULATION",
    ButtonPin.REACTOR_RESET: "REACTOR RESET",
    ButtonPin.EMERGENCY: "EMERGENCY SHUTDOWN",
}

# ============================================
# Button Handler Class
# ============================================

class ButtonHandler:
    """Handles all physical push buttons with debouncing"""
    
    def __init__(self, debounce_time=0.03):
        """
        Initialize GPIO buttons with HYBRID detection
        
        Args:
            debounce_time: Debounce delay in seconds (default: 30ms - optimized for responsiveness)
        """
        self.debounce_time = debounce_time
        self.last_press_time = {}
        self.last_state = {}
        self.callbacks = {}
        
        # ============================================
        # HYBRID DETECTION: Classify buttons by behavior
        # ============================================
        
        # EDGE DETECTION: Trigger once per press (toggle actions)
        # Best for: ON/OFF, START/STOP, RESET, EMERGENCY
        self.EDGE_BUTTONS = {
            ButtonPin.PUMP_PRIMARY_ON,
            ButtonPin.PUMP_PRIMARY_OFF,
            ButtonPin.PUMP_SECONDARY_ON,
            ButtonPin.PUMP_SECONDARY_OFF,
            ButtonPin.PUMP_TERTIARY_ON,
            ButtonPin.PUMP_TERTIARY_OFF,
            ButtonPin.START_AUTO_SIMULATION,
            ButtonPin.REACTOR_RESET,
            ButtonPin.EMERGENCY
        }
        
        # LEVEL DETECTION: Trigger while held (continuous actions)
        # Best for: Rod control (hold for continuous change)
        self.LEVEL_BUTTONS = {
            ButtonPin.SAFETY_ROD_UP,
            ButtonPin.SAFETY_ROD_DOWN,
            ButtonPin.SHIM_ROD_UP,
            ButtonPin.SHIM_ROD_DOWN,
            ButtonPin.REGULATING_ROD_UP,
            ButtonPin.REGULATING_ROD_DOWN
        }
        
        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # Setup all button pins as INPUT with PULL_UP
        # (Buttons connect pin to GND when pressed)
        self.button_press_times = {}  # pin -> press_time
        self.button_held_flags = {}   # pin -> is_held
        for pin in ButtonPin:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self.last_press_time[pin] = 0
            self.last_state[pin] = GPIO.HIGH
            
        logger.info("GPIO Button Handler initialized (HYBRID mode)")
        logger.info(f"  - Edge detection: {len(self.EDGE_BUTTONS)} buttons (toggle)")
        logger.info(f"  - Level detection: {len(self.LEVEL_BUTTONS)} buttons (continuous)")
        logger.info(f"  - Debounce time: {debounce_time*1000:.0f}ms")
    
    def register_callback(self, button_pin, callback):
        """
        Register callback function for button press
        
        Args:
            button_pin: ButtonPin enum value
            callback: Function to call when button pressed (no arguments)
        """
        self.callbacks[button_pin] = callback
        logger.info(f"Callback registered: {BUTTON_NAMES[button_pin]}")
    
    def check_all_buttons(self):
        """
        Check all buttons with HYBRID detection (edge + level)
        Should be called frequently (e.g., every 5ms) in main loop
        """
        current_time = time.time()
        
        for pin in ButtonPin:
            current_state = GPIO.input(pin)
            
            # ============================================
            # EDGE DETECTION (for toggle buttons)
            # ============================================
            if pin in self.EDGE_BUTTONS:
                # Detect HIGH to LOW transition (button press)
                if current_state == GPIO.LOW and self.last_state[pin] == GPIO.HIGH:
                    # 2-sample confirmation to filter bounce noise
                    time.sleep(0.002)  # Wait 2ms
                    if GPIO.input(pin) == GPIO.LOW:  # Still pressed?
                        # Check debounce
                        time_since_last = current_time - self.last_press_time[pin]
                        
                        if time_since_last > self.debounce_time:
                            self.last_press_time[pin] = current_time
                            
                            logger.info(f"✓ Button pressed (EDGE): {BUTTON_NAMES[pin]}")
                            
                            # Trigger callback if registered
                            if pin in self.callbacks:
                                try:
                                    self.callbacks[pin]()
                                except Exception as e:
                                    logger.error(f"Error in callback for {BUTTON_NAMES[pin]}: {e}")
                            else:
                                logger.warning(f"⚠ No callback registered for {BUTTON_NAMES[pin]}")
            
            # ============================================
            # PRESSURE CLICK VS HOLD DETECTION
            # ============================================
            elif pin in [ButtonPin.PRESSURE_UP, ButtonPin.PRESSURE_DOWN]:
                # Press down (HIGH -> LOW)
                if current_state == GPIO.LOW and self.last_state[pin] == GPIO.HIGH:
                    self.button_press_times[pin] = current_time
                    self.button_held_flags[pin] = False
                    self.last_press_time[pin] = current_time
                    logger.debug(f"Pressure button pressed down: {BUTTON_NAMES[pin]}")
                
                # Button is currently being held down (LOW)
                elif current_state == GPIO.LOW:
                    press_time = self.button_press_times.get(pin)
                    if press_time is not None:
                        hold_duration = current_time - press_time
                        if hold_duration > 0.30:  # 300ms hold threshold
                            self.button_held_flags[pin] = True
                            
                            # Repeat trigger every 50ms while held
                            time_since_last = current_time - self.last_press_time[pin]
                            if time_since_last > 0.05:
                                self.last_press_time[pin] = current_time
                                logger.debug(f"✓ Button held (LEVEL): {BUTTON_NAMES[pin]}")
                                if pin in self.callbacks:
                                    try:
                                        self.callbacks[pin](is_held=True)
                                    except Exception as e:
                                        logger.error(f"Error in callback for {BUTTON_NAMES[pin]}: {e}")
                
                # Button release (LOW -> HIGH)
                elif current_state == GPIO.HIGH and self.last_state[pin] == GPIO.LOW:
                    press_time = self.button_press_times.pop(pin, None)
                    is_held = self.button_held_flags.pop(pin, False)
                    if press_time is not None and not is_held:
                        logger.info(f"✓ Button clicked (EDGE): {BUTTON_NAMES[pin]}")
                        if pin in self.callbacks:
                            try:
                                self.callbacks[pin](is_held=False)
                            except Exception as e:
                                logger.error(f"Error in callback for {BUTTON_NAMES[pin]}: {e}")
            
            # ============================================
            # LEVEL DETECTION (for continuous buttons)
            # ============================================
            elif pin in self.LEVEL_BUTTONS:
                # Trigger while button is held (LOW)
                if current_state == GPIO.LOW:
                    time_since_last = current_time - self.last_press_time[pin]
                    
                    # Rate limiting: trigger every 50ms while held
                    if time_since_last > 0.05:  # 50ms repeat interval
                        self.last_press_time[pin] = current_time
                        
                        logger.debug(f"✓ Button held (LEVEL): {BUTTON_NAMES[pin]}")
                        
                        # Trigger callback if registered
                        if pin in self.callbacks:
                            try:
                                self.callbacks[pin]()
                            except Exception as e:
                                logger.error(f"Error in callback for {BUTTON_NAMES[pin]}: {e}")
            
            # Update last state AFTER checking
            self.last_state[pin] = current_state
    
    def check_hold_buttons(self, hold_interval=0.05):
        """
        Check if buttons are being HELD (LEVEL detection)
        Returns set of ButtonPin that are currently pressed (LOW)
        
        This allows continuous action while holding button (for rods and pressure)
        
        Args:
            hold_interval: Minimum interval between repeated actions (default 50ms)
            
        Returns:
            set: Set of ButtonPin currently pressed
        """
        current_time = time.time()
        pressed_buttons = set()
        
        for pin in ButtonPin:
            current_state = GPIO.input(pin)
            
            # Check if button is pressed (LOW) and interval passed
            if current_state == GPIO.LOW:
                if current_time - self.last_press_time[pin] > hold_interval:
                    pressed_buttons.add(pin)
                    self.last_press_time[pin] = current_time
        
        return pressed_buttons
    
    def is_button_pressed(self, button_pin):
        """
        Check if specific button is currently pressed (without callback)
        
        Args:
            button_pin: ButtonPin enum value
            
        Returns:
            bool: True if button pressed, False otherwise
        """
        return GPIO.input(button_pin) == GPIO.LOW
    
    def cleanup(self):
        """Cleanup GPIO resources by cleaning up only the pins used by this handler."""
        logger.info("Cleaning up GPIO pins for Button Handler...")
        for pin in ButtonPin:
            try:
                GPIO.cleanup(pin)
            except Exception as e:
                logger.error(f"Error cleaning up GPIO pin {pin}: {e}")
        logger.info("GPIO Button Handler cleaned up")

# ============================================
# Test Function
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("  PLTN Control Panel Button Test")
    print("="*60)
    print("Press any button to test. Ctrl+C to exit.")
    print()
    
    handler = ButtonHandler()
    
    try:
        while True:
            handler.check_all_buttons()
            time.sleep(0.01)  # 10ms polling
            
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        handler.cleanup()
