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

try:
    from .servo_controller import ServoController
    from .motor_controller import MotorController
except ImportError:
    from servo_controller import ServoController
    from motor_controller import MotorController

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

class ActuatorManager:
    HUMIDIFIER_PINS = {
        'ct1': 2,
        'ct2': 3,
        'ct3': 9,
        'ct4': 10
    }

    def __init__(self):
        self.hardware_active = GPIO_AVAILABLE
        
        # Initialize sub-controllers
        self.servos = ServoController(safety_pin=23, shim_pin=24, reg_pin=25)
        self.motors = MotorController()
        
        if self.hardware_active:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                
                # Initialize humidifier pins
                for pin in self.HUMIDIFIER_PINS.values():
                    GPIO.setup(pin, GPIO.OUT)
                    # Relay modules are Active-HIGH in this setup. Default to LOW (OFF).
                    GPIO.output(pin, GPIO.LOW)
                
                logger.info(f"ActuatorManager: Hardware mode active. Humidifiers on pins: {list(self.HUMIDIFIER_PINS.values())}")
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
        # Servos are managed by pigpio independently of RPi.GPIO
        self.servos.set_rods(state.safety_rod, state.shim_rod, state.regulating_rod)
        
        # Motors are also managed by pigpio
        # Calculate smooth speed during transition (3.0 seconds duration, as in raspi_main_panel)
        def calc_speed(status, transition_start):
            if status == 0:  # OFF
                return 0.0
            elif status == 2:  # ON
                return 100.0
            
            # For STARTING (1) and SHUTTING_DOWN (3)
            current_time = time.time()
            if transition_start == 0:
                return 0.0 if status == 1 else 100.0
                
            progress = (current_time - transition_start) / 3.0
            progress = max(0.0, min(1.0, progress))
            
            if status == 1:  # STARTING: 0 to 100%
                return progress * 100.0
            elif status == 3:  # SHUTTING_DOWN: 100 to 0%
                return (1.0 - progress) * 100.0
            return 0.0

        prim_speed = calc_speed(state.pump_primary_status, state.pump_primary_transition_start)
        sec_speed = calc_speed(state.pump_secondary_status, state.pump_secondary_transition_start)
        tert_speed = calc_speed(state.pump_tertiary_status, state.pump_tertiary_transition_start)
        
        self.motors.set_speed('pump_primary', prim_speed)
        self.motors.set_speed('pump_secondary', sec_speed)
        self.motors.set_speed('pump_tertiary', tert_speed)
        self.motors.set_speed('turbine', state.turbine_speed)
        
        if not self.hardware_active:
            # In mock mode, we don't do anything physical for standard GPIO.
            return

        try:
            # Physical relay control for Humidifiers (Active-High)
            GPIO.output(self.HUMIDIFIER_PINS['ct1'], GPIO.HIGH if getattr(state, 'humid_ct1_cmd', 0) else GPIO.LOW)
            GPIO.output(self.HUMIDIFIER_PINS['ct2'], GPIO.HIGH if getattr(state, 'humid_ct2_cmd', 0) else GPIO.LOW)
            GPIO.output(self.HUMIDIFIER_PINS['ct3'], GPIO.HIGH if getattr(state, 'humid_ct3_cmd', 0) else GPIO.LOW)
            GPIO.output(self.HUMIDIFIER_PINS['ct4'], GPIO.HIGH if getattr(state, 'humid_ct4_cmd', 0) else GPIO.LOW)
        except Exception as e:
            logger.error(f"ActuatorManager: Error updating hardware: {e}")

    def cleanup(self):
        """Cleanup GPIO pins on exit."""
        self.servos.cleanup()
        self.motors.cleanup()
        
        if self.hardware_active:
            try:
                GPIO.cleanup()
                logger.info("ActuatorManager: Cleaned up GPIO.")
            except Exception as e:
                logger.error(f"ActuatorManager: Cleanup error: {e}")
