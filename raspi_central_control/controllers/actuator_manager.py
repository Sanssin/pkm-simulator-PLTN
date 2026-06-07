"""
Unified Actuator Manager for PLTN Simulator.
Handles direct control of all Raspberry Pi hardware actuators:
- Servos (for control rods)
- PWM Motors (for pumps)
- Relays (for other systems)

Implements graceful degradation: if hardware is not connected or libraries are missing,
it will print debug messages instead of crashing.
"""

import logging
import time

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

class ActuatorManager:
    def __init__(self):
        self.hardware_active = GPIO_AVAILABLE
        
        if self.hardware_active:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                # Initialize pins here later
                logger.info("ActuatorManager: Hardware mode active.")
            except Exception as e:
                logger.warning(f"ActuatorManager: Failed to initialize GPIO: {e}. Falling back to Mock mode.")
                self.hardware_active = False
        else:
            logger.info("ActuatorManager: Running in Mock mode (No RPi.GPIO available).")

    def update_actuators(self, state):
        """
        Updates all physical actuators based on the current state.
        This is called periodically (e.g., every 10ms) from the control logic thread.
        """
        if not self.hardware_active:
            # In mock mode, we don't do anything physical.
            # The state is already updated in the state_manager, which will be exported to the UI.
            return

        try:
            # TODO: Implement physical hardware control here
            # e.g., rod_servo.set_angle(state.shim_rod)
            pass
        except Exception as e:
            logger.error(f"ActuatorManager: Error updating hardware: {e}")

    def cleanup(self):
        """Cleanup GPIO pins on exit."""
        if self.hardware_active:
            try:
                GPIO.cleanup()
                logger.info("ActuatorManager: Cleaned up GPIO.")
            except Exception as e:
                logger.error(f"ActuatorManager: Cleanup error: {e}")
